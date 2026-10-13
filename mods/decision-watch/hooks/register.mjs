// decision-watch: SHADOW mode. Runs the Stop-time decision watch (hooks/decision_watch.py) with the
// session's own model login, and writes the verdict to a log. It never blocks, never messages,
// and never changes the Stop result.
//
// classic.Stop  returns next(e) at once. The judging runs in the background and is skipped when
//               stop_hook_active is set.
// /dw           runs the same judgment on the latest turn and shows the result.
//
// The python script has two phases: --emit-prompt prints the prompt when a model call is due,
// then --model-text or --model-error finishes the verdict. This mod makes the model call between.
// The mod runs the script with its own state folder, so it never mutes the real hook's
// "already judged" cache. The log holds the verdict line and timings, never the prompt.
//
// The host reads on(...) and $.noun.method(...) from source, so they are spelled literally.

let lastStop; // the last classic.Stop input this session, for /dw

const msg = (err) => String((err && err.message) || err).slice(0, 300);
// $.model.complete returns {isAnswered, text, usage}. Accept a plain string too.
const textOf = (r) => (typeof r === "string" ? r : String((r && r.text) ?? ""));

export function register(on) {
  on("session.start", async ($, e, next) => {
    await $.command.register({
      name: "dw",
      description: "Run the decision watch on the latest turn with this session's own model login",
    });
    return next(e);
  });

  on("command.run", { command: "dw" }, async ($, e) => {
    const lines = [];
    try {
      const stop = lastStop ?? (await deriveStop($));
      lines.push(`stop input: session ${stop.session_id}`);
      const out = await judge($, stop);
      lines.push(...out.trace, `RESULT: ${out.result}`);
    } catch (err) {
      lines.push(`RESULT: UNKNOWN (mod error): ${msg(err)}`);
    }
    return { text: lines.join("\n") };
  });

  // SHADOW. Returns next(e) at once. The judging is fire-and-forget.
  on("classic.Stop", async ($, e, next) => {
    lastStop = stopOf(e);
    if (!e.stop_hook_active) {
      void shadow($, lastStop);
    }
    return next(e);
  });
}

function stopOf(e) {
  return {
    session_id: e.session_id,
    transcript_path: e.transcript_path,
    cwd: e.cwd,
    hook_event_name: "Stop",
    stop_hook_active: false,
  };
}

async function configDir($) {
  const given = await $.env.get("CLAUDE_CONFIG_DIR");
  if (given) return given;
  const home = (await $.env.get("USERPROFILE")) || (await $.env.get("HOME"));
  return `${home}/.claude`;
}

// No Stop seen yet: rebuild transcript_path from the session id and cwd the way the app names it.
async function deriveStop($) {
  const id = await $.session.id();
  const cwd = await $.session.cwd();
  const path = `${await configDir($)}/projects/${cwd.replace(/[^A-Za-z0-9]/g, "-")}/${id}.jsonl`;
  if (!(await $.fs.exists(path))) throw new Error("no Stop seen yet and no transcript found for this session");
  return { session_id: id, transcript_path: path, cwd, hook_event_name: "Stop", stop_hook_active: false };
}

// First python on PATH that is not the WindowsApps Store stub (settings.json's launcher does the same).
async function pickPython($) {
  for (const argv of [["where.exe", "python3", "python"], ["which", "-a", "python3", "python"]]) {
    try {
      const r = await $.process.run(argv, { timeoutMs: 5000 });
      const hit = r.stdout.split(/\r?\n/).map((s) => s.trim()).find((s) => s && !/WindowsApps/i.test(s));
      if (r.exitCode === 0 && hit) return hit;
    } catch {
      // try the next finder
    }
  }
  throw new Error("no python on PATH other than the WindowsApps stub");
}

async function dwRun($, stop, extra) {
  const cfg = await configDir($);
  const py = await pickPython($);
  const t0 = Date.now();
  const r = await $.process.run([py, "-I", `${cfg}/hooks/decision_watch.py`, ...extra], {
    stdin: JSON.stringify(stop),
    env: { CLAUDE_CONFIG_DIR: stateDir(cfg) },
    timeoutMs: 60000,
  });
  return { ...r, ms: Date.now() - t0 };
}

const stateDir = (cfg) => `${cfg}/decision-watch-mod`;

// Two phases. Every failure is UNKNOWN, never a pass: the python side prints the same
// "Decision watch: UNKNOWN ..." text for a model error it is handed with --model-error.
async function judge($, stop) {
  const trace = [];
  const p1 = await dwRun($, stop, ["--emit-prompt"]);
  trace.push(`phase 1 (python, cheap path): exit ${p1.exitCode}, ${p1.ms} ms`);
  if (p1.exitCode !== 0) {
    return { trace, result: `UNKNOWN: decision_watch exited ${p1.exitCode}: ${p1.stderr.slice(0, 200)}` };
  }
  const raw = p1.stdout.trim();
  if (raw === "") return { trace, result: "nothing to say (no protected change, no model call)" };
  let out;
  try {
    out = JSON.parse(raw);
  } catch {
    return { trace, result: `UNKNOWN: phase 1 output was not JSON: ${raw.slice(0, 200)}` };
  }
  if (!out.needs_model) return { trace, result: `message from the cheap path: ${out.systemMessage ?? raw.slice(0, 300)}` };

  trace.push(`model due: ${out.model}, prompt ${out.prompt.length} chars`);
  let args;
  let modelFailed = false;
  const t0 = Date.now();
  try {
    const text = textOf(await $.model.complete({ model: out.model, prompt: out.prompt, maxTokens: 512 }));
    if (text === "") throw new Error("the model reply carried no text");
    trace.push(`model call: OK ${Date.now() - t0} ms, reply ${text.length} chars`);
    args = ["--model-text", text.slice(0, 4000)];
  } catch (err) {
    modelFailed = true;
    trace.push(`model call: FAIL ${Date.now() - t0} ms`);
    args = ["--model-error", `model call: ${msg(err)}`];
  }
  const p2 = await dwRun($, stop, args);
  trace.push(`phase 2 (python, verdict): exit ${p2.exitCode}, ${p2.ms} ms`);
  if (p2.exitCode !== 0) {
    return { trace, result: `UNKNOWN: decision_watch exited ${p2.exitCode} in phase 2: ${p2.stderr.slice(0, 200)}` };
  }
  let msgOut = "";
  try {
    msgOut = p2.stdout.trim() === "" ? "" : JSON.parse(p2.stdout).systemMessage ?? "";
  } catch {
    return { trace, result: `UNKNOWN: phase 2 output was not JSON: ${p2.stdout.slice(0, 200)}` };
  }
  if (msgOut === "" && modelFailed) {
    return { trace, result: "UNKNOWN: the model call failed and the script printed nothing" };
  }
  return { trace, result: msgOut === "" ? "ALLOW (silent)" : msgOut };
}

async function shadow($, stop) {
  await log($, `START ${stop.session_id}`);
  let line;
  try {
    const out = await judge($, stop);
    line = `END ${stop.session_id} | ${out.trace.join(" | ")} | ${out.result}`;
  } catch (err) {
    line = `END ${stop.session_id} | MOD ERROR, reads as UNKNOWN: ${msg(err)}`;
  }
  await log($, line);
}

async function log($, line) {
  try {
    const dir = stateDir(await configDir($));
    const file = `${dir}/shadow.log`;
    if (typeof $.fs.mkdir === "function") await $.fs.mkdir(dir, { recursive: true });
    const old = (await $.fs.exists(file)) ? await $.fs.read(file) : "";
    await $.fs.write(file, `${old}${new Date().toISOString()} ${line}\n`);
  } catch {
    // shadow mode never fails the Stop
  }
}

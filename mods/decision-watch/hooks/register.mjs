// decision-watch: runs the Stop-time decision watch (hooks/decision_watch.py) with the session's
// own model login, and writes the verdict to a log. A FLAG or UNKNOWN shows in the session with
// $.ui.toast, the text the Stop hook showed. An ALLOW, and any other text such as a config notice,
// goes to the log only. It never blocks and never changes the Stop result.
//
// classic.Stop  returns next(e) at once. The judging runs in the background and is skipped when
//               stop_hook_active is set.
// /dw           runs the same judgment on the latest turn and shows the result.
//
// The python script has two phases: --emit-prompt prints the prompt when a model call is due,
// then --model-text or --model-error finishes the verdict. This mod makes the model call between.
// Phase 1 prints a "key" for the evidence it judged. Phase 2 gets it back as --key after the reply,
// so evidence that moved between the phases reads UNKNOWN, never a silent ALLOW. No key reads UNKNOWN.
// The mod runs the script with its own state folder, so it never mutes the real hook's
// "already judged" cache. The log holds the verdict line and timings, never the prompt.
//
// The host reads on(...) and $.noun.method(...) from source, so they are spelled literally.

let lastStop; // the last classic.Stop input this session, for /dw
let busy = false; // true while a background judge runs

// The prefix of every UNKNOWN this mod makes itself; python's own UNKNOWN text comes through as printed.
const UNKNOWN = "Decision watch: UNKNOWN, ";
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
      const out = await judge($, stop, "dw");
      lines.push(...out.trace, `RESULT: ${out.result}`);
    } catch (err) {
      lines.push(`RESULT: UNKNOWN (mod error): ${msg(err)}`);
    }
    lines.push(`Stops seen: ${await stopsSeen($)}`);
    return { text: lines.join("\n") };
  });

  // Background judge. Waits at most STOP_WAIT_MS for one "STOP seen" line, then returns next(e).
  // The judging is fire-and-forget, one judge at a time. A Stop that finds one running logs "SKIP busy".
  on("classic.Stop", async ($, e, next) => {
    lastStop = stopOf(e);
    const note = e.stop_hook_active ? " (stop_hook_active, no judge)" : "";
    try {
      await within(log($, `STOP seen ${e.session_id}${note}`), STOP_WAIT_MS);
    } catch {
      // the log never holds a Stop
    }
    if (!e.stop_hook_active) {
      if (busy) {
        void log($, `SKIP busy ${e.session_id}`);
      } else {
        busy = true;
        void shadow($, lastStop).finally(() => {
          busy = false;
        });
      }
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

// ASCII-only JSON: python -I may read stdin in a legacy code page, so escape every non-ASCII character.
const asciiJson = (v) => JSON.stringify(v).replace(/[\u0080-￿]/g, (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));

// The background judge and /dw each get their own state folder, so neither mutes the other's cache.
// Neither is the real config folder, so the real hook's cache is never touched.
const stateDir = (cfg, who) => `${cfg}/decision-watch-${who}`;

async function dwRun($, stop, extra, who) {
  const cfg = await configDir($);
  const py = await pickPython($);
  const t0 = Date.now();
  const r = await $.process.run([py, "-I", `${cfg}/hooks/decision_watch.py`, ...extra], {
    stdin: asciiJson(stop),
    env: { CLAUDE_CONFIG_DIR: stateDir(cfg, who) },
    timeoutMs: 60000,
  });
  return { ...r, ms: Date.now() - t0 };
}

// Two phases. Every failure is UNKNOWN, never a pass: the python side prints the same
// "Decision watch: UNKNOWN ..." text for a model error it is handed with --model-error.
async function judge($, stop, who) {
  const trace = [];
  const p1 = await dwRun($, stop, ["--emit-prompt"], who);
  trace.push(`phase 1 (python, cheap path): exit ${p1.exitCode}, ${p1.ms} ms`);
  if (p1.exitCode !== 0) return unknown(trace, `decision_watch exited ${p1.exitCode}: ${p1.stderr.slice(0, 200)}`);
  const raw = p1.stdout.trim();
  if (raw === "") return { trace, result: "nothing to say (no protected change, no model call)" };
  let out;
  try {
    out = JSON.parse(raw);
  } catch {
    return unknown(trace, `phase 1 output was not JSON: ${raw.slice(0, 200)}`);
  }
  if (!out.needs_model) {
    const shown = typeof out.systemMessage === "string" ? out.systemMessage : "";
    return { trace, result: `message from the cheap path: ${shown || raw.slice(0, 300)}`, shown };
  }
  if (typeof out.key !== "string" || out.key === "") {
    return unknown(trace, "phase 1 printed no key, so the reply cannot be tied to the evidence judged (an old decision_watch.py?)");
  }

  trace.push(`model due: ${out.model}, prompt ${out.prompt.length} chars`);
  let args;
  let modelFailed = false;
  const t0 = Date.now();
  try {
    // The host's timeoutMs is unproven, so the mod enforces the limit itself: the race rejects, phase 2
    // gets --model-error, and the one-judge slot frees. A late reply is dropped.
    const reply = await deadline($.model.complete({ model: out.model, prompt: out.prompt, maxTokens: 512, timeoutMs: MODEL_MS }), MODEL_MS);
    const text = textOf(reply);
    if (text === "") throw new Error("the model reply carried no text");
    trace.push(`model call: OK ${Date.now() - t0} ms, reply ${text.length} chars`);
    args = ["--model-text", text.slice(0, 4000)];
  } catch (err) {
    modelFailed = true;
    trace.push(`model call: FAIL ${Date.now() - t0} ms`);
    args = ["--model-error", `model call: ${msg(err)}`];
  }
  const p2 = await dwRun($, stop, [...args, "--key", out.key], who);
  trace.push(`phase 2 (python, verdict): exit ${p2.exitCode}, ${p2.ms} ms`);
  if (p2.exitCode !== 0) return unknown(trace, `decision_watch exited ${p2.exitCode} in phase 2: ${p2.stderr.slice(0, 200)}`);
  let msgOut = "";
  try {
    msgOut = p2.stdout.trim() === "" ? "" : JSON.parse(p2.stdout).systemMessage ?? "";
  } catch {
    return unknown(trace, `phase 2 output was not JSON: ${p2.stdout.slice(0, 200)}`);
  }
  if (msgOut === "" && modelFailed) return unknown(trace, "the model call failed and the script printed nothing");
  return { trace, result: msgOut === "" ? "ALLOW (silent)" : msgOut, shown: msgOut };
}

// A failure the mod itself sees is UNKNOWN, and it shows like the script's own UNKNOWN.
function unknown(trace, why) {
  return { trace, result: `UNKNOWN: ${why}`, shown: UNKNOWN + why };
}

async function shadow($, stop) {
  await log($, `START ${stop.session_id}`);
  let line;
  let shown = "";
  try {
    const out = await judge($, stop, "shadow");
    line = `END ${stop.session_id} | ${out.trace.join(" | ")} | ${out.result}`;
    shown = out.shown;
  } catch (err) {
    line = `END ${stop.session_id} | MOD ERROR, reads as UNKNOWN: ${msg(err)}`;
    shown = UNKNOWN + `the mod raised (${msg(err)})`;
  }
  await log($, line);
  // Only a FLAG or UNKNOWN toasts. Other text (an ALLOW turn's config notice) stays in the log.
  if (/^Decision watch: (FLAG|UNKNOWN)/.test(shown)) {
    try {
      await $.ui.toast(shown);
    } catch (err) {
      await log($, `TOAST FAILED ${stop.session_id} | ${msg(err)} | text: ${shown}`);
    }
  } else if (shown) {
    await log($, `NOT SHOWN ${stop.session_id} | not a FLAG or UNKNOWN | text: ${shown}`);
  }
}

const MAX_LOG_LINES = 500;
const MAX_LINE = 2000;
const LOG_WAIT_MS = 2000;
const STOP_WAIT_MS = 500;
const MODEL_MS = 50000;

// Like within, but a late promise rejects, so the caller can fail the step and free its slot.
async function deadline(work, ms) {
  let timer;
  try {
    return await Promise.race([work, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`no reply within ${ms} ms`)), ms); })]);
  } finally {
    clearTimeout(timer);
  }
}

// Race a promise against a timer, and free the timer either way.
async function within(work, ms) {
  let timer;
  try {
    return await Promise.race([work, new Promise((resolve) => { timer = setTimeout(resolve, ms); })]);
  } finally {
    clearTimeout(timer);
  }
}

async function logFile($) {
  return `${stateDir(await configDir($), "shadow")}/shadow.log`;
}

// Writes go one at a time, so two lines never read the same old file. $.fs.write makes a missing folder.
// The file keeps its newest MAX_LOG_LINES lines. A file the host will not read (too big) starts over.
let logChain = Promise.resolve();
function log($, line) {
  const work = async () => {
    try {
      const file = await logFile($);
      let old = [];
      try {
        if (await $.fs.exists(file)) old = String(await $.fs.read(file)).split("\n").filter(Boolean);
      } catch {
        old = [];
      }
      const next = `${new Date().toISOString()} ${line}`.slice(0, MAX_LINE);
      await $.fs.write(file, [...old.slice(-(MAX_LOG_LINES - 1)), next].join("\n") + "\n");
    } catch {
      // the log never fails the Stop
    }
  };
  const done = logChain.then(() => within(work(), LOG_WAIT_MS));
  logChain = done;
  return done;
}

async function stopsSeen($) {
  try {
    const file = await logFile($);
    if (!(await $.fs.exists(file))) return 0;
    return String(await $.fs.read(file)).split("\n").filter((l) => l.includes("STOP seen")).length;
  } catch {
    return "unknown";
  }
}

// decision-watch: runs the Stop-time decision watch (hooks/decision_watch.py) with the session's
// own model login, and writes the verdict to a log. A FLAG or UNKNOWN verdict shows in the session
// with $.ui.toast. An ALLOW verdict shows nothing. Each config notice shows as its own toast, marked
// as a notice (decision decision-watch-mod-limits). It never blocks and never changes the Stop result.
//
// turn.complete returns next(e) at once. The judging runs in the background, one judge at a time, and is
//               skipped on a subagent turn (agentId set). The app's sec-default mod reroutes every classic.*
//               event past user mods, so a classic.Stop handler never ran; turn.* events pass. The event
//               carries no transcript path, so the judge finds it the way /dw does (deriveStop).
// /dw           runs the same judgment on the latest turn and shows the result.
//
// The python script has two phases: --emit-prompt prints the prompt when a model call is due,
// then --model-text or --model-error finishes the verdict. This mod makes the model call between.
// Phase 1 prints a "key" for the evidence it judged. Phase 2 gets it back as --key after the reply,
// so evidence that moved between the phases reads UNKNOWN, never a silent ALLOW. No key reads UNKNOWN.
// The script prints `verdict` and `notices` apart, so the mod never parses joined text.
// The log holds the verdict line, the notices and timings, never the prompt.
//
// The host reads on(...) and $.noun.method(...) from source, so they are spelled literally.

let lastStop; // the last Stop-shaped input built from a main-loop turn, for /dw
let keptId; // the session id read at session.start, the fallback when $.session.id() fails later
let busy = false; // true while a background judge runs
let foundPy; // the python path pickPython found, kept for the module's life; cleared when a run with it is rejected

// The prefix of every UNKNOWN this mod makes itself; python's own UNKNOWN text comes through as printed.
const UNKNOWN = "Decision watch: UNKNOWN, ";
// The mark on a config notice toast. It never matches a FLAG or UNKNOWN verdict.
const NOTICE = "Decision watch notice: ";
const NOTHING = "nothing to say (no protected change, no model call)";
const msg = (err) => String((err && err.message) || err).slice(0, 300);
// $.model.complete returns {isAnswered, text, usage}. Accept a plain string too.
const textOf = (r) => (typeof r === "string" ? r : String((r && r.text) ?? ""));

export function register(on) {
  on("session.start", async ($, e, next) => {
    try {
      keptId = await $.session.id();
    } catch {
      // deriveStop asks again on each turn
    }
    await $.command.register({
      name: "dw",
      description: "Run the decision watch on the latest turn with this session's own model login",
    });
    return next(e);
  });

  on("command.run", { command: "dw" }, async ($, e) => {
    const lines = [];
    try {
      let stop = lastStop;
      if (!stop) {
        const d = await deriveStop($);
        if (!d.found) throw new Error("no turn seen yet and no transcript found for this session");
        stop = d.stop;
      }
      lines.push(`stop input: session ${stop.session_id}`);
      const out = await judge($, stop, "dw");
      lines.push(...out.trace, `RESULT: ${out.result}`, ...out.notices.map((n) => `NOTICE: ${n}`));
    } catch (err) {
      lines.push(`RESULT: UNKNOWN (mod error): ${msg(err)}`);
    }
    lines.push(`Stops seen: ${await stopsSeen($)}`);
    return { text: lines.join("\n") };
  });

  // Background judge. Waits at most STOP_WAIT_MS for the lookup and again for one "STOP seen" line, then
  // returns next(e). The judging is fire-and-forget, one judge at a time. A turn that finds one running
  // logs "SKIP busy". A turn with no transcript logs a SKIP line and judges nothing.
  on("turn.complete", async ($, e, next) => {
    if (!e.agentId) {
      try {
        const d = await within(deriveStop($), STOP_WAIT_MS);
        if (d) {
          await within(log($, `STOP seen ${d.stop.session_id}`), STOP_WAIT_MS);
          if (!d.found) {
            void log($, `SKIP no transcript ${d.stop.session_id} | ${d.stop.transcript_path}`);
          } else {
            lastStop = d.stop;
            if (busy) {
              void log($, `SKIP busy ${d.stop.session_id}`);
            } else {
              busy = true;
              void shadow($, d.stop).finally(() => {
                busy = false;
              });
            }
          }
        }
      } catch (err) {
        void log($, `SKIP no session | ${msg(err)}`);
      }
    }
    return next(e);
  });
}

async function configDir($) {
  const given = await $.env.get("CLAUDE_CONFIG_DIR");
  if (given) return given;
  const home = (await $.env.get("USERPROFILE")) || (await $.env.get("HOME"));
  return `${home}/.claude`;
}

// The one lookup for a turn's transcript, used by turn.complete and /dw: rebuild transcript_path from the
// session id and cwd the way the app names it. found says whether the file is there.
async function deriveStop($) {
  let id;
  try {
    id = await $.session.id();
  } catch (err) {
    if (!keptId) throw err;
    id = keptId;
  }
  const cwd = await $.session.cwd();
  const path = `${await configDir($)}/projects/${cwd.replace(/[^A-Za-z0-9]/g, "-")}/${id}.jsonl`;
  return {
    stop: { session_id: id, transcript_path: path, cwd, hook_event_name: "Stop", stop_hook_active: false },
    found: await $.fs.exists(path),
  };
}

// First python on PATH that is not the WindowsApps Store stub (settings.json's launcher does the same).
async function pickPython($) {
  for (const argv of [["where.exe", "python3", "python"], ["which", "-a", "python3", "python"]]) {
    try {
      const r = await deadline($.process.run(argv, { timeoutMs: FIND_MS }), FIND_MS + 1000);
      const hit = r.stdout.split(/\r?\n/).map((s) => s.trim()).find((s) => s && !/WindowsApps/i.test(s));
      if (r.exitCode === 0 && hit) return hit;
    } catch {
      // try the next finder
    }
  }
  throw new Error("no python on PATH other than the WindowsApps stub");
}

// ASCII-only JSON: python -I may read stdin in a legacy code page, so escape every non-ASCII character.
const asciiJson = (v) => JSON.stringify(v).replace(/[\u0080-\uffff]/g, (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));

// The background judge and /dw each get their own state folder, so neither mutes the other's
// "already judged" cache.
const stateDir = (cfg, who) => `${cfg}/decision-watch-${who}`;

async function dwRun($, stop, extra, who) {
  const cfg = await configDir($);
  const t0 = Date.now();
  const spawn = (py) =>
    // The mod's own timer frees the slot if the host does not stop the child. It does not kill the child.
    deadline($.process.run([py, "-I", `${cfg}/hooks/decision_watch.py`, ...extra], {
      stdin: asciiJson(stop),
      env: { CLAUDE_CONFIG_DIR: stateDir(cfg, who), DW_REAL_CONFIG_DIR: cfg },
      timeoutMs: PY_MS,
    }), PY_MS + 1000);
  let r;
  if (foundPy) {
    const tried = foundPy;
    try {
      r = await spawn(tried);
      // A non-zero exit from a file that is gone is a failed start too (the shell reports a missing file that way).
      // A failed exists check counts as gone. The async wrapper turns a synchronous throw into a rejection, so r is kept.
      if (r.exitCode !== 0 && !(await (async () => $.fs.exists(tried))().catch(() => false)) && foundPy === tried) foundPy = undefined;
    } catch (err) {
      // A rejected run (failed start or timeout) drops the cached path, so the next run looks again. This run is
      // not repeated: a hung python would hold the slot twice as long. A python that exits non-zero resolves and keeps it.
      if (foundPy === tried) foundPy = undefined;
      throw err;
    }
  } else {
    const py = await pickPython($);
    r = await spawn(py);
    foundPy = py;
  }
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
  if (raw === "") return { trace, result: NOTHING, shown: "", notices: [] };
  let out;
  try {
    out = JSON.parse(raw);
  } catch {
    return unknown(trace, `phase 1 output was not JSON: ${raw.slice(0, 200)}`);
  }
  if (!out.needs_model) {
    const { verdict, notices } = partsOf(out);
    const result = verdict ? `message from the cheap path: ${verdict}` : notices.length ? NOTHING : `message from the cheap path: ${raw.slice(0, 300)}`;
    return { trace, result, shown: verdict, notices };
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
    if (text === "") throw new Error(`the model reply carried no text${reply && reply.reason ? ` (${reply.reason})` : ""}`);
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
  let parts = { verdict: "", notices: [] };
  try {
    if (p2.stdout.trim() !== "") parts = partsOf(JSON.parse(p2.stdout));
  } catch {
    return unknown(trace, `phase 2 output was not JSON: ${p2.stdout.slice(0, 200)}`);
  }
  if (parts.verdict === "" && modelFailed) return unknown(trace, "the model call failed and the script printed no verdict", parts.notices);
  return { trace, result: parts.verdict === "" ? "ALLOW (silent)" : parts.verdict, shown: parts.verdict, notices: parts.notices };
}

// The script prints `verdict` and `notices` under a split flag. Output with no `notices` array
// (a script that prints systemMessage only) is all verdict.
function partsOf(o) {
  if (Array.isArray(o.notices)) {
    return { verdict: typeof o.verdict === "string" ? o.verdict : "", notices: o.notices.filter((n) => typeof n === "string" && n) };
  }
  return { verdict: typeof o.systemMessage === "string" ? o.systemMessage : "", notices: [] };
}

// A failure the mod itself sees is UNKNOWN, and it shows like the script's own UNKNOWN.
function unknown(trace, why, notices = []) {
  return { trace, result: `UNKNOWN: ${why}`, shown: UNKNOWN + why, notices };
}

async function shadow($, stop) {
  await log($, `START ${stop.session_id}`);
  let line;
  let shown = "";
  let notices = [];
  try {
    const out = await judge($, stop, "shadow");
    // Each notice goes on its own log lines, before END, so the END cut at MAX_LINE never drops one.
    // A longer notice is split over several lines with the same prefix. The pieces, joined, give the notice with
    // its whitespace folded. A cut never splits a surrogate pair, and no piece after the first starts with a space,
    // because log() would fold that space into the prefix. Whitespace at the very start of a notice is lost.
    const prefix = `NOTICE ${stop.session_id} | NOTICE: `;
    const room = Math.max(MAX_LINE - TIME_LEN - 1 - prefix.length, 100);
    for (const n of out.notices) {
      const text = n.replace(/\s+/g, " ");
      let i = 0;
      do {
        let j = Math.min(i + room, text.length);
        while (j < text.length && j > i + 1 && (text[j] === " " || /[\uDC00-\uDFFF]/.test(text[j]))) j--;
        await log($, prefix + text.slice(i, j));
        i = j;
      } while (i < text.length);
    }
    line = `END ${stop.session_id} | ${out.trace.join(" | ")} | ${out.result}`;
    shown = out.shown;
    notices = out.notices;
  } catch (err) {
    line = `END ${stop.session_id} | MOD ERROR, reads as UNKNOWN: ${msg(err)}`;
    shown = UNKNOWN + `the mod raised (${msg(err)})`;
  }
  await log($, line);
  // A FLAG or UNKNOWN verdict toasts. An ALLOW verdict is silent. Each notice toasts on its own line.
  if (/^Decision watch: (FLAG|UNKNOWN)/.test(shown)) {
    await toast($, stop, shown);
  } else if (shown) {
    await log($, `NOT SHOWN ${stop.session_id} | not a FLAG or UNKNOWN | text: ${shown}`);
  }
  for (const n of notices) await toast($, stop, NOTICE + n);
}

async function toast($, stop, text) {
  try {
    await deadline(Promise.resolve($.ui.toast(text)), TOAST_MS);
  } catch (err) {
    await log($, `TOAST FAILED ${stop.session_id} | ${msg(err)} | text: ${text}`);
  }
}

const MAX_LOG_LINES = 500;
const MAX_LINE = 2000;
const TIME_LEN = 24; // length of an ISO timestamp, the start of each log line
const LOG_WAIT_MS = 2000;
const STOP_WAIT_MS = 500;
const MODEL_MS = 50000;
const PY_MS = 30000; // each python run (unmeasured; split mode calls no model); the mod's timer adds 1 s
const FIND_MS = 5000; // each python finder; the mod's timer adds 1 s
const TOAST_MS = 5000;

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
      // Whitespace is folded, as guard_core.log_cut does, so no text can forge a second log line.
      const next = `${new Date().toISOString()} ${line.replace(/\s+/g, " ")}`.slice(0, MAX_LINE);
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
    return String(await $.fs.read(file)).split("\n").filter((l) => /^\S+ STOP seen /.test(l)).length;
  } catch {
    return "unknown";
  }
}

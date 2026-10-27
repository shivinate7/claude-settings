// decision-watch pins. Run: node mods/decision-watch/decision-watch.test.mjs  (stdlib only; exit 1 on any FAIL)
// The mod is hooks/register.mjs, driven through a fake host ($). Each case loads a fresh copy.
// The python side is a fake of decision_watch.py's entry points. Its "already judged" cache is keyed on
// the child's CLAUDE_CONFIG_DIR and the stdin session_id, as the real cache is:
//   --emit-prompt        silent on a cache hit; else {needs_model, prompt, model}
//   --model-text TEXT    FLAG as systemMessage, ALLOW as silence, UNKNOWN otherwise; FLAG and ALLOW mark the cache
//                        on a cache hit: "verdict lost" (the python marker this lane adds)
//   --model-error TEXT   UNKNOWN, or "verdict lost" on a cache hit
// hooks/test_decision_watch.py pins the python side. This file pins what the mod does with it.
// Guessed contract points: /dw registers in a session.start handler; a judgment ends with a shadow-log
// write holding END; each main-loop turn.complete writes a "STOP seen" line; /dw's last output line is "Stops seen: N";
// the host's fs.read refuses a file over 4 MiB; the child state folder differs from the real config folder;
// a config notice is its own toast and contains the word "notice" (any case), and the verdict toast holds the
// verdict text exactly; a judge slot held by a python call that never returns frees within 60 s.
// The two-phase model-call fields (timeoutMs is pinned on its own).
// The trigger is turn.complete, never classic.Stop: the app's sec-default mod reroutes every classic.* event past
// user-tier mods, so a classic.Stop handler never runs. turn.complete carries no session id, cwd or transcript path,
// so the judge derives them the way /dw does: $.session.id(), $.session.cwd() and the config folder's projects layout.
// Guessed contract point, HOLE 12 cases only: the real child's env is the host env merged with the env register.mjs
// passes (the host may replace it instead). Those cases run the real hooks/decision_watch.py, not the fake.
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { mock } from 'node:test'
// The scanners are shared: lint/test_scanner_traps.mjs runs their self-tests. Two source checks below use them.
import { codeNouns, machinePaths } from '../../lint/test_scanner_traps.mjs'

const REGISTER = fileURLToPath(new URL('./hooks/register.mjs', import.meta.url))
const REAL_CFG = '/cfg/real'
const SCRIPT = REAL_CFG + '/hooks/decision_watch.py'
const PY = '/usr/bin/python3'
const SID = 'aaaaaaaa-1111-2222-3333-444444444444'
const CWD = '/work/repo'
// The transcript the app names for CWD: every non-alphanumeric character of the cwd becomes "-".
const TRANSCRIPT = REAL_CFG + '/projects/-work-repo/' + SID + '.jsonl'
const SENTINEL = 'PROMPT-SENTINEL-ALPHA-7'
const PROMPT = 'Judge this turn. ' + SENTINEL
const ALLOW_REPLY = '{"verdict": "ALLOW"}'
const FLAG_REPLY = '{"verdict": "FLAG", "why": "reversed silently"}'
// The message texts are read from the script, so the fake python prints what the Stop hook prints today.
const SCRIPT_SRC = fileURLToPath(new URL('../../hooks/decision_watch.py', import.meta.url))
const MODEL_CAP = fileURLToPath(new URL('../../docs/decisions/subagent-model-cap.md', import.meta.url))
const scriptSource = readFileSync(SCRIPT_SRC, 'utf8')
const pyConst = name => {
  const m = scriptSource.match(new RegExp('^' + name + ' = "(.*)"$', 'm'))
  if (!m) throw new Error(name + ' is not a plain string in hooks/decision_watch.py')
  return m[1]
}
const UNKNOWN = pyConst('UNKNOWN_PREFIX')
const FLAG_PREFIX = pyConst('FLAG_PREFIX')
const FLAG = FLAG_PREFIX + 'the judge model reported: "reversed silently"'
const LOST = UNKNOWN + 'verdict lost: the model reply was not used (the watch ended before the model step).'
const FOUR_MIB = 4 * 1024 * 1024

const norm = p => String(p).replace(/\\/g, '/')
const clone = v => JSON.parse(JSON.stringify(v))
const same = (got, want, why) => assert.deepEqual(got, want, `${why}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`)
// The real timers, read before any case fakes setTimeout. A case on fake timers still reads its guards from these,
// so a regression fails that case and does not hang the run.
const realSetTimeout = globalThis.setTimeout
const realClearTimeout = globalThis.clearTimeout
const settle = (ms = 20) => new Promise(r => realSetTimeout(r, ms))
const within = (p, ms, why) => {
  let t
  const late = new Promise((_, rej) => { t = realSetTimeout(() => rej(new Error(`timed out after ${ms} ms: ${why}`)), ms) })
  return Promise.race([p, late]).finally(() => realClearTimeout(t))
}
// Drains the microtasks of a fake-host judge. setImmediate is not faked (only setTimeout is).
const flush = () => new Promise(r => setImmediate(r))

const results = []
const unhandled = []
process.on('unhandledRejection', e => unhandled.push(e))
async function test(name, fn) {
  try {
    await fn()
    results.push(`PASS ${name}`)
  } catch (e) {
    results.push(`FAIL ${name}: ${String(e && e.message ? e.message : e).split('\n')[0]}`)
  }
}

// ---- the mod file

await test('module: hooks/register.mjs exists and exports register', async () => {
  const mod = await import(pathToFileURL(REGISTER).href + '?probe=1')
  assert.equal(typeof mod.register, 'function', 'register export')
})

await test('source: no machine path anywhere in hooks/register.mjs, comments included', () => {
  same(machinePaths(readFileSync(REGISTER, 'utf8')), [], 'machine paths in the mod')
})

await test('source: the host reads $.model.complete( and the event names as literal spellings', () => {
  const text = readFileSync(REGISTER, 'utf8')
  assert.ok(text.includes('$.model.complete('), 'missing the $.model.complete( literal')
  assert.ok(text.includes('"turn.complete"'), 'missing the "turn.complete" literal')
  assert.ok(text.includes('"command.run"'), 'missing the "command.run" literal')
})

// A raw U+FFFF (a noncharacter) in the file can be dropped or mangled by an editor
// or a transfer, and then the asciiJson range end changes with no sign. The escape \uFFFF is plain ASCII.
// This is a character-presence check, not a scan of strings and comments, so it needs no opener cases.
await test('source: hooks/register.mjs holds no raw U+FFFF character, the asciiJson range end is an escape', () => {
  assert.ok(!readFileSync(REGISTER, 'utf8').includes('\uFFFF'), 'a raw U+FFFF character is in hooks/register.mjs')
})

// Item 1. The validator rejects a $ noun read as a value. $.fs.write makes folders, so there is no mkdir.
// Code only: a comment that names the call is not a use.
await test('source: no $.noun.method is read without a call in the mod code, so $.fs.mkdir is not there even as typeof', () => {
  same(codeNouns(readFileSync(REGISTER, 'utf8')), [], 'bare $.noun.method reads in the mod code')
})

// ---- the fake host and its python

const out = obj => ({ exitCode: 0, stdout: JSON.stringify(obj) + '\n', stderr: '' })
const UNKNOWN_REPLY = out({ systemMessage: UNKNOWN + 'the model judgment could not be completed (model result carried no JSON verdict).' })

function verdictOf(text) {
  const m = String(text).match(/\{.*\}/s)
  try {
    const v = m ? JSON.parse(m[0]).verdict : null
    return v === 'FLAG' || v === 'ALLOW' ? v : null
  } catch {
    return null
  }
}

function replyOut(h, key, text) {
  if (h.seen.has(key)) return out({ systemMessage: LOST })
  const v = verdictOf(text)
  if (v) h.seen.add(key)
  if (v === 'FLAG') return out({ systemMessage: FLAG })
  if (v === 'ALLOW') return { exitCode: 0, stdout: '', stderr: '' }
  return UNKNOWN_REPLY
}

// The evidence key: phase 1 prints it, and phase 2 is given it back with --key. A key the live
// evidence no longer gives reads UNKNOWN (HOLE 1 of decision decision-watch-mod-limits).
const keyOf = h => 'key:' + h.evidence
const keyArg = argv => (argv.indexOf('--key') >= 0 ? argv[argv.indexOf('--key') + 1] : undefined)
const moved = (h, argv) => keyArg(argv) !== undefined && keyArg(argv) !== keyOf(h)
const MOVED = UNKNOWN + 'the evidence changed between the two phases, so the reply was not used.'

function defaultPython(h, argv, o) {
  const stdin = JSON.parse(o.stdin || '{}')
  const key = `${o.env && o.env.CLAUDE_CONFIG_DIR}|${stdin.session_id}`
  if (argv.includes('--emit-prompt')) {
    if (h.seen.has(key)) return { exitCode: 0, stdout: '', stderr: '' } // the "already judged" cache
    return out({ needs_model: true, prompt: PROMPT, model: 'haiku', key: keyOf(h) })
  }
  const i = argv.indexOf('--model-text')
  const j = argv.indexOf('--model-error')
  if (i >= 0) return moved(h, argv) ? out({ systemMessage: MOVED }) : replyOut(h, key, argv[i + 1])
  if (j >= 0) {
    if (moved(h, argv)) return out({ systemMessage: MOVED })
    if (h.seen.has(key)) return out({ systemMessage: LOST })
    return out({ systemMessage: UNKNOWN + 'the model judgment could not be completed (' + argv[j + 1] + ').' })
  }
  return { exitCode: 2, stdout: '', stderr: 'fake python: unknown argv' }
}

let loads = 0

// Where the app keeps this host's session transcript: the config folder, then projects/<cwd with every
// non-alphanumeric character as "-">/<session id>.jsonl. The fake fs.exists answers true for it, so a turn.complete
// that carries no transcript path can find its transcript. Read at call time, so a case may change h.cwd, h.sid or h.env.
const transcriptOf = h => {
  const cfg = h.env.CLAUDE_CONFIG_DIR || `${h.env.USERPROFILE || h.env.HOME}/.claude`
  return `${cfg}/projects/${h.cwd.replace(/[^A-Za-z0-9]/g, '-')}/${h.sid}.jsonl`
}

function host(opts = {}) {
  const h = {
    sid: SID, cwd: CWD, env: { CLAUDE_CONFIG_DIR: REAL_CFG, HOME: '/home/u' },
    finder: null, finderThrow: false, py1: undefined, py2: undefined,
    model: () => ({ isAnswered: true, text: ALLOW_REPLY, usage: {} }),
    sessionThrow: false,
    hooks: [], procs: [], modelReqs: [], writes: [], files: new Map(), registered: [], uiLogs: [], toasts: [],
    evidence: 'E1', // the live evidence the fake python keys on; a test moves it to model a change
    seen: new Set(), waiters: [],
    ...opts,
  }
  h.endLogged = new Promise(res => { h.resolveEnd = res })
  h.$ = {
    process: {
      run: async (argv, o = {}) => {
        h.procs.push({ argv, opts: o })
        if (/^(where(\.exe)?|which)$/.test(argv[0])) {
          if (h.finderThrow) throw new Error('finder failed')
          if (typeof h.finder === 'function') return h.finder(argv)
          return h.finder ?? { exitCode: 0, stdout: PY + '\r\n', stderr: '' }
        }
        const phase = argv.includes('--emit-prompt') ? h.py1 : h.py2
        const r = typeof phase === 'function' ? await phase(argv, o) : phase
        return r ?? defaultPython(h, argv, o)
      },
    },
    model: {
      complete: async req => { h.modelReqs.push(clone(req)); return h.model(req) },
    },
    fs: {
      exists: async p => h.files.has(p) || p === transcriptOf(h),
      read: async p => {
        const t = h.files.get(p)
        if (t !== undefined && t.length > FOUR_MIB) throw new Error('file is over the 4 MiB read limit')
        return t
      },
      write: async (p, data) => {
        const s = String(data)
        h.writes.push({ path: p, data: s })
        h.files.set(p, s)
        if (/\bEND\b/.test(s)) h.resolveEnd(s)
        h.waiters = h.waiters.filter(w => {
          if (!w.re.test(s)) return true
          w.resolve(s)
          return false
        })
      },
    },
    env: { get: async k => h.env[k] },
    session: {
      id: async () => { if (h.sessionThrow) throw new Error('no session'); return h.sid },
      cwd: async () => h.cwd,
    },
    command: { register: async s => { h.registered.push(s.name) } },
    ui: {
      log: text => { h.uiLogs.push(String(text)) },
      // The in-session surface: desktop-statusline shows its own notices this way.
      toast: (text, opts) => { h.toasts.push(String(text)); void opts },
    },
  }
  return h
}

async function load(h) {
  const register = (await import(pathToFileURL(REGISTER).href + '?case=' + ++loads)).register
  register((event, a, b) => {
    h.hooks.push(b === undefined ? { event, matcher: {}, fn: a } : { event, matcher: a, fn: b })
    return { catch() { return this } }
  })
  return h
}

const stopEvent = (extra = {}) => ({
  session_id: SID, transcript_path: TRANSCRIPT, cwd: CWD, hook_event_name: 'Stop', stop_hook_active: false, ...extra,
})

// A turn.complete as the host raises it (TurnCompleteInput): no session id, cwd or transcript path. agentId is set
// on a subagent's turn and absent on the main loop.
const turnEvent = (extra = {}) => ({ answer: 'done', durationMs: 1000, isAborted: false, turnId: 't1', reason: 'answer', ...extra })

async function fire(h, event, e = {}, nextValue) {
  const hook = h.hooks.find(x => x.event === event && Object.entries(x.matcher).every(([k, v]) => e[k] === v))
  if (!hook) throw new Error(`no handler for ${event}`)
  // A handler that waits on its judge would hang every later case, so it fails here instead, fast and named.
  return within(Promise.resolve(hook.fn(h.$, e, () => nextValue)), 3000, `the ${event} handler did not return`)
}

const judged = h => within(h.endLogged, 3000, 'the shadow log END line')
const pyCalls = h => h.procs.filter(p => p.argv[1] === '-I')
const allLog = h => h.writes.map(w => w.data).join('')
const dwRun = h => within(fire(h, 'command.run', { command: 'dw', args: '' }), 3000, 'the /dw judge')
const shown = (h, r) => [typeof r === 'string' ? r : r && r.text, ...h.uiLogs].filter(Boolean).join('\n')
const tail = text => JSON.stringify(text.slice(-160))
// A write whose text matches re, awaited from now on. Registered before the Stop that makes it.
const waitLog = (h, re, ms = 3000) => {
  let resolve
  const got = new Promise(r => { resolve = r })
  h.waiters.push({ re, resolve })
  return within(got, ms, `a log write matching ${re}`)
}
const logPath = h => (h.writes.find(w => /STOP seen|START|END/.test(w.data)) || {}).path

// One Stop, judged in the background, so /dw has a latest turn. Clears the calls it made.
async function primed(h) {
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  h.procs.length = 0
  h.modelReqs.length = 0
}

// ---- the trigger: turn.complete, shadow only
// The app's sec-default mod reroutes every classic.* event past user-tier mods, so the old classic.Stop trigger never
// ran. turn.* events pass. The five "trigger" cases below pin the move; every other case drives its judge through
// turn.complete too.

const emits = h => pyCalls(h).filter(p => p.argv.includes('--emit-prompt'))

await test('turn.complete trigger 1: a main-loop turn (no agentId) starts one judge, on the transcript /dw derives', async () => {
  const h = await load(host())
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  same(emits(h).length, 1, 'phase 1 runs')
  same(h.modelReqs.length, 1, 'model calls')
  const stdin = JSON.parse(emits(h)[0].opts.stdin)
  same(stdin.session_id, SID, 'stdin session_id, from $.session.id()')
  same(stdin.cwd, CWD, 'stdin cwd, from $.session.cwd()')
  same(stdin.transcript_path, TRANSCRIPT, 'stdin transcript_path, the one /dw derives')
})

await test('turn.complete trigger 2: a subagent turn (agentId set) starts no judge and returns next(e); the main turn after it judges', async () => {
  const h = await load(host())
  const NEXT = { text: 'sub answer' }
  assert.equal(await within(fire(h, 'turn.complete', turnEvent({ agentId: 'agent-7' }), NEXT), 1000, 'the subagent turn'), NEXT)
  await settle(60)
  same(h.procs.length, 0, 'process calls')
  same(h.modelReqs.length, 0, 'model calls')
  same(h.writes.filter(w => /START|END/.test(w.data)).length, 0, 'START or END log writes')
  // Same host, same transcript. The main turn does judge, so the skip came from agentId, and the slot was left free.
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  same(emits(h).length, 1, 'phase 1 runs for the main turn')
  assert.doesNotMatch(allLog(h), /SKIP busy/, 'the subagent turn held the judge slot')
})

// A mod with no classic.Stop handler passes. A mod that keeps one must still return next(e) and judge nothing.
// The control turn.complete at the end shows the host is live, so a pass is not an empty host.
await test('turn.complete trigger 3: classic.Stop starts no judge, with stop_hook_active false or true', async () => {
  const NEXT = { decision: 'pass' }
  for (const active of [false, true]) {
    const h = await load(host())
    const stop = h.hooks.find(x => x.event === 'classic.Stop')
    if (stop) assert.equal(await within(stop.fn(h.$, stopEvent({ stop_hook_active: active }), () => NEXT), 1000, 'classic.Stop'), NEXT)
    await settle(60)
    same(h.procs.length, 0, `process calls after classic.Stop (stop_hook_active ${active})`)
    same(h.modelReqs.length, 0, `model calls after classic.Stop (stop_hook_active ${active})`)
    same(h.writes.filter(w => /START|END/.test(w.data)).length, 0, `START or END log writes after classic.Stop (stop_hook_active ${active})`)
    await fire(h, 'turn.complete', turnEvent(), {})
    await judged(h)
    same(emits(h).length, 1, 'phase 1 runs for the turn.complete control')
  }
})

await test('turn.complete trigger 4: passes next(e) through and returns while the judge is still running', async () => {
  const h = await load(host({ model: () => new Promise(() => {}) }))
  // The mod's model deadline is a timer. Fake it, so the hung call cannot hold the run open for 50 s.
  mock.timers.enable({ apis: ['setTimeout'] })
  try {
    const hook = h.hooks.find(x => x.event === 'turn.complete')
    assert.ok(hook, 'no turn.complete handler')
    const e = turnEvent()
    const before = clone(e)
    const NEXT = { text: 'the answer' }
    const nexts = []
    const got = await within(hook.fn(h.$, e, async (...a) => { nexts.push(a); return NEXT }), 1000, 'turn.complete waited for the judge')
    assert.equal(got, NEXT, 'the handler returns the object next() resolved to')
    same(nexts.length, 1, 'next calls')
    assert.equal(nexts[0][0], e, 'next was given the event')
    same(e, before, 'turn.complete event')
    await flush()
    same(h.modelReqs.length, 1, 'model calls in flight: the judge was not running when the handler returned, so the case proves nothing')
  } finally {
    // Drain the background judge first: a deadline made after the reset would be a real 50 s timer.
    await flush()
    mock.timers.reset()
  }
})

await test('turn.complete trigger 5: a second turn while a judge runs starts no second judge; the slot frees when the judge ends', async () => {
  let release
  const gate = new Promise(r => { release = r })
  const h = await load(host({ model: () => gate.then(() => ({ isAnswered: true, text: ALLOW_REPLY, usage: {} })) }))
  try {
    await fire(h, 'turn.complete', turnEvent({ turnId: 't1' }), {})
    await settle(20)
    same(emits(h).length, 1, 'phase 1 runs for the first turn')
    const NEXT = { text: 'second answer' }
    assert.equal(await within(fire(h, 'turn.complete', turnEvent({ turnId: 't2' }), NEXT), 1000, 'the second turn waited for the running judge'), NEXT)
    await settle(60)
    same(emits(h).length, 1, 'phase 1 runs: the second turn started a second judge')
    same(h.modelReqs.length, 1, 'model calls in flight')
  } finally {
    release()
  }
  await judged(h)
  await settle(60)
  await fire(h, 'turn.complete', turnEvent({ turnId: 't3' }), {})
  await settle(60)
  same(emits(h).length, 2, 'phase 1 runs after the first judge ended: the slot never freed')
})

// A turn that cannot be judged leaves a SKIP line, never silence. skipLogged is registered before the turn that
// writes the line, and answers true or false so a missing line fails with its own message.
const skipLogged = (h, ms) => waitLog(h, /^\S+ SKIP /m, ms).then(() => true, () => false)
// Only the transcript lookup hangs, so the log (which also asks $.fs.exists) still works.
const slowLookup = h => {
  const exists = h.$.fs.exists
  h.$.fs.exists = p => (p === transcriptOf(h) ? new Promise(() => {}) : exists(p))
}

await test('turn.complete trigger 6: a transcript lookup slower than its 500 ms bound still writes a SKIP line and judges nothing', async () => {
  const h = await load(host())
  slowLookup(h)
  const skipped = skipLogged(h, 2000)
  await fire(h, 'turn.complete', turnEvent(), {})
  assert.ok(await skipped, 'no SKIP line was written: the turn left no trace in the log')
  await settle(60)
  same(emits(h).length, 0, 'phase 1 runs for a turn whose transcript was never found')
  same(h.modelReqs.length, 0, 'model calls')
})

// Owner ruling 2026-10-21 22:21 CDT: the handler may hold the turn up to SEEN_WAIT_MS (500 ms, the same as the lookup
// bound), so the STOP seen or SKIP line lands before the turn ends. A hung lookup holds it for that bound, no longer,
// and its SKIP line is already in the log when next(e) returns. A fast lookup is not held, and its STOP seen line is.
await test('turn.complete trigger 7: a hung transcript lookup holds next(e) until its SKIP line is written, within about 600 ms; a fast lookup returns with its STOP seen line written', async () => {
  const hung = await load(host())
  slowLookup(hung)
  const NEXT = { text: 'the answer' }
  const t0 = Date.now()
  assert.equal(await within(fire(hung, 'turn.complete', turnEvent(), NEXT), 600, 'turn.complete held past about 600 ms by the hung lookup'), NEXT)
  const held = Date.now() - t0
  assert.match(allLog(hung), /^\S+ SKIP /m, `next(e) returned after ${held} ms with no SKIP line in the log: the handler did not wait for the lookup's 500 ms bound`)
  const fast = await load(host())
  const t1 = Date.now()
  assert.equal(await within(fire(fast, 'turn.complete', turnEvent(), NEXT), 400, 'a fast lookup was held for the full wait'), NEXT)
  assert.match(allLog(fast), /^\S+ STOP seen /m, 'a fast lookup returned with no STOP seen line in the log')
  assert.doesNotMatch(allLog(fast), /SKIP /, `a fast lookup wrote a SKIP line (returned after ${Date.now() - t1} ms)`)
})

// /clear gives the process a new session id with no session.start (SessionEndInput and the session.start note in the
// host types). A kept id is then the OLD session's, whose transcript is still on disk, so a fallback to it would judge
// the wrong session.
await test('turn.complete trigger 8: after a /clear, a failed per-turn $.session.id() judges nothing (no fallback to the session.start id) and logs a SKIP line', async () => {
  const h = await load(host())
  await fire(h, 'session.start', {}, {}) // the id read here is SID
  const OLD = TRANSCRIPT
  h.files.set(OLD, '{}\n') // the old session's transcript stays on disk after /clear
  h.sid = 'bbbbbbbb-1111-2222-3333-444444444444'
  h.sessionThrow = true
  const skipped = skipLogged(h, 1000)
  await fire(h, 'turn.complete', turnEvent(), {})
  const ok = await skipped
  await settle(60)
  same(emits(h).length, 0, "phase 1 runs: the old session's transcript was judged from the id kept at session.start")
  same(h.modelReqs.length, 0, 'model calls')
  assert.ok(ok, 'no SKIP line was written: the turn left no trace in the log')
  // Control: with the id readable again, the new session judges, on its own transcript.
  h.sessionThrow = false
  await fire(h, 'turn.complete', turnEvent({ turnId: 't2' }), {})
  await judged(h)
  same(emits(h).length, 1, 'phase 1 runs for the new session')
  const stdin = JSON.parse(emits(h)[0].opts.stdin)
  same(stdin.session_id, h.sid, 'stdin session_id')
  same(stdin.transcript_path, transcriptOf(h), 'stdin transcript_path')
})

// Owner default 2026-10-21 17:00 CDT: skip turns with no full answer. Each condition is set alone, so a handler that
// reads only isAborted, or only the reason, fails the case for the one it ignores.
for (const [label, extra] of [
  ['isAborted true', { isAborted: true }],
  ["reason 'aborted'", { reason: 'aborted' }],
  ["reason 'error'", { reason: 'error' }],
  ["reason 'refusal'", { reason: 'refusal' }],
]) {
  await test(`turn.complete skip: a turn with ${label} starts no judge and logs a SKIP line; a reason 'answer' turn after it judges`, async () => {
    const h = await load(host())
    const skipped = skipLogged(h, 1000)
    const NEXT = { text: 'the answer' }
    assert.equal(await within(fire(h, 'turn.complete', turnEvent(extra), NEXT), 1000, 'the turn'), NEXT)
    const ok = await skipped
    await settle(60)
    same(emits(h).length, 0, 'phase 1 runs: a turn with no full answer was judged')
    same(h.modelReqs.length, 0, 'model calls')
    assert.ok(ok, 'no SKIP line was written: the turn left no trace in the log')
    // Control: the skip did not hold the judge slot, and a reason 'answer' turn judges.
    await fire(h, 'turn.complete', turnEvent({ turnId: 't2', reason: 'answer', isAborted: false }), {})
    await judged(h)
    same(emits(h).length, 1, 'phase 1 runs for the reason answer turn')
    assert.doesNotMatch(allLog(h), /SKIP busy/, 'the skipped turn held the judge slot')
  })
}

await test('turn: a FLAG never changes the turn.complete result', async () => {
  const h = await load(host({ model: () => ({ isAnswered: true, text: FLAG_REPLY, usage: {} }) }))
  const e = turnEvent()
  const before = clone(e)
  const NEXT = { text: 'the answer' }
  assert.equal(await within(fire(h, 'turn.complete', e, NEXT), 1000, 'turn.complete'), NEXT)
  await judged(h)
  same(e, before, 'turn.complete event')
  same(NEXT, { text: 'the answer' }, 'next result')
})

await test('turn: never throws when every host call throws, and still returns next(e)', async () => {
  const boom = () => { throw new Error('host down') }
  const h = await load(host({ finderThrow: true, sessionThrow: true, model: boom, py1: boom, py2: boom }))
  h.$.fs.exists = async () => { throw new Error('fs down') }
  h.$.fs.write = async () => { throw new Error('fs down') }
  h.$.env.get = async () => { throw new Error('env down') }
  const NEXT = { decision: 'pass' }
  assert.equal(await within(fire(h, 'turn.complete', turnEvent(), NEXT), 1000, 'Stop'), NEXT)
  await settle()
})

// Item 7. The STOP seen line is written before the turn.complete handler returns, so a viewer can tell the mod ran.
await test('turn: a STOP seen line is written before turn.complete returns next(e)', async () => {
  const h = await load(host({ model: () => new Promise(() => {}) }))
  mock.timers.enable({ apis: ['setTimeout'] }) // the model deadline is a timer: fake it, as in the case above
  try {
    const NEXT = { decision: 'pass' }
    assert.equal(await within(fire(h, 'turn.complete', turnEvent(), NEXT), 1500, 'Stop'), NEXT)
    assert.ok(h.writes.some(w => /STOP seen/.test(w.data)), 'no STOP seen line was written before Stop returned')
  } finally {
    await flush() // as in the case above: the background judge's deadline must be made while the mock is on
    mock.timers.reset()
  }
})

// A write that never returns cannot hold the turn.
await test('turn: a STOP seen write that never returns cannot hold turn.complete past 1.5 s', async () => {
  const h = await load(host())
  h.$.fs.write = () => new Promise(() => {})
  const NEXT = { decision: 'pass' }
  assert.equal(await within(fire(h, 'turn.complete', turnEvent(), NEXT), 1500, 'Stop held by a hung write'), NEXT)
})

// ---- the two phases and the model call

await test('two-phase: phase 1 emits the prompt; the model call takes it with maxTokens 512 and phase 1 model; phase 2 gets the reply', async () => {
  const h = await load(host())
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  const py = pyCalls(h)
  same(py.length, 2, 'python calls: phase 1 and phase 2')
  same(py[0].argv, [PY, '-I', SCRIPT, '--emit-prompt'], 'phase 1 argv')
  same(py[1].argv.slice(0, 3), [PY, '-I', SCRIPT], 'phase 2 argv head')
  same(py[1].argv[3], '--model-text', 'phase 2 flag')
  same(py[1].argv[4], ALLOW_REPLY, 'phase 2 reply')
  // timeoutMs is pinned on its own, in the case below.
  same(h.modelReqs.map(({ timeoutMs, ...rest }) => rest), [{ model: 'haiku', prompt: PROMPT, maxTokens: 512 }], 'model call fields')
  same(JSON.parse(py[0].opts.stdin).session_id, SID, 'phase 1 stdin is the Stop JSON')
  same(JSON.parse(py[1].opts.stdin).transcript_path, TRANSCRIPT, 'phase 2 stdin is the same Stop JSON')
})

// The model call's limit is enforced by the mod's own deadline (see the busy cases below), not by a request field.

await test('model error: phase 2 gets --model-error with the message, and no --model-text', async () => {
  const h = await load(host({ model: () => { throw new Error('model down') } }))
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  const argv = pyCalls(h)[1].argv
  assert.ok(argv.includes('--model-error'), 'phase 2 has --model-error')
  assert.ok(!argv.includes('--model-text'), 'phase 2 has no --model-text')
  assert.ok(String(argv[argv.indexOf('--model-error') + 1]).includes('model down'), 'the message carries the error')
})

await test('model error: the shadow log reads UNKNOWN, never ALLOW', async () => {
  const h = await load(host({ model: () => { throw new Error('model down') } }))
  await fire(h, 'turn.complete', turnEvent(), {})
  const endData = await judged(h)
  assert.match(endData, /UNKNOWN/, 'log holds no UNKNOWN')
  assert.doesNotMatch(endData, /ALLOW/, 'log holds ALLOW for a failed judgment')
})

// An aborted call returns no text and a reason. The reply still goes to python
// as --model-error (a reason is not a verdict reply), and the error and the log name the reason.
await test('model error: an aborted reply with a reason and no text goes as --model-error, and the log names the reason', async () => {
  const h = await load(host({ model: () => ({ isAnswered: false, reason: 'aborted by user', usage: {} }) }))
  await fire(h, 'turn.complete', turnEvent(), {})
  const endData = await judged(h)
  const argv = pyCalls(h)[1].argv
  assert.ok(argv.includes('--model-error'), 'phase 2 has --model-error')
  assert.ok(!argv.includes('--model-text'), 'phase 2 has no --model-text: the reason is not a reply')
  assert.ok(String(argv[argv.indexOf('--model-error') + 1]).includes('aborted by user'), 'the error names the reason')
  assert.match(endData, /UNKNOWN/, 'log holds no UNKNOWN')
  assert.match(endData, /aborted by user/, 'log does not name the reason')
})

// ---- HOLE 1 (decision decision-watch-mod-limits): phase 2 is given the phase-1 key.

// With no phase-1 key, the moved evidence is judged afresh and reads a silent ALLOW.
await test('HOLE 1: evidence moved between the phases reads UNKNOWN, never a silent ALLOW', async () => {
  let h
  h = await load(host({
    model: () => {
      h.evidence = 'E2' // the protected file changed while the model call was in flight
      return { isAnswered: true, text: ALLOW_REPLY, usage: {} }
    },
  }))
  await fire(h, 'turn.complete', turnEvent(), {})
  const endData = await judged(h)
  assert.doesNotMatch(endData, /ALLOW/, 'ALLOW for a verdict on evidence that moved')
  assert.match(endData, /UNKNOWN/, 'the log holds no UNKNOWN')
})

await test('HOLE 1: phase 2 is given the key phase 1 printed, as --key after the reply', async () => {
  const h = await load(host())
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  const p2 = pyCalls(h)[1].argv
  assert.ok(p2.includes('--key'), `phase 2 has no --key: ${JSON.stringify(p2)}`)
  same(p2[p2.indexOf('--key') + 1], 'key:E1', 'phase 2 key, from phase 1')
})

// A phase 1 with no key (an old decision_watch.py) cannot be tied to the evidence, so it reads UNKNOWN.
await test('HOLE 1: no key from phase 1 reads UNKNOWN, never ALLOW', async () => {
  const h = await load(host({ py1: () => out({ needs_model: true, prompt: PROMPT, model: 'haiku' }) }))
  await fire(h, 'turn.complete', turnEvent(), {})
  const endData = await judged(h)
  assert.doesNotMatch(endData, /ALLOW/, 'ALLOW for a verdict that cannot be tied to the evidence')
  assert.match(endData, /UNKNOWN/, 'the log holds no UNKNOWN')
})

// ---- what shows in the session: the Stop hook's own systemMessage text, through $.ui.toast.
// desktop-statusline shows its notices with $.ui.toast(text, { timeoutMs }), so that is the surface.

await test('shown: a FLAG shows the Stop hook text exactly, once', async () => {
  const h = await load(host({ model: () => ({ isAnswered: true, text: FLAG_REPLY, usage: {} }) }))
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  await settle(60)
  same(h.toasts, [FLAG], 'toasts')
})

await test('shown: the FLAG wording is the one hooks/decision_watch.py prints today', () => {
  assert.ok(scriptSource.includes('FLAG_PREFIX + \'the judge model reported: "%s"\''), 'the script no longer prints this FLAG wording')
})

await test('shown: an UNKNOWN from the judge shows its exact text, once', async () => {
  const h = await load(host({ model: () => { throw new Error('model down') } }))
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  await settle(60)
  same(h.toasts, [UNKNOWN + 'the model judgment could not be completed (model call: model down).'], 'toasts')
})

await test('shown: a message from the cheap path shows its exact text, with no prefix added', async () => {
  const CHEAP = UNKNOWN + 'the transcript could not be read (no such file).'
  const h = await load(host({ py1: () => out({ systemMessage: CHEAP }) }))
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  await settle(60)
  same(h.toasts, [CHEAP], 'toasts')
})

// Guard: an ALLOW stays silent in the session. A toast on every Stop would teach the reader to skip it.
await test('shown: an ALLOW shows nothing', async () => {
  const h = await load(host())
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  await settle(60)
  same(h.toasts, [], 'toasts')
})

// ---- the config notice. decision_watch.py joins config_report() text onto its message, after the verdict, with
// " ".join at main, so a notice rides on every verdict, ALLOW included, and on a cheap-path message too.
// Each config notice is its own toast line, apart from the verdict, and is marked as a notice. An ALLOW
// verdict itself stays silent. The notice's marker is the word "notice" (any case).
const CONFIG_LINE = pyConst('CONFIG_MESSAGE').replace('%s', '.claude/settings.json')
const CONFIG_NOTICE = CONFIG_LINE + pyConst('TAIL')
// What decision_watch.py prints under a split flag (the mod's own call): systemMessage is the joined text,
// verdict is the judgment alone ("" for none), and notices holds one string per kind, each ending in TAIL.
// The joined text is verdict and notices joined with a space, as main() joins them.
const splitOut = (verdict, notices) => out({
  systemMessage: [verdict, ...notices].filter(Boolean).join(' '),
  verdict,
  notices,
})

// The notice toast names the notice, is marked as one, and is not a verdict.
const noticeToast = t => {
  assert.ok(t.includes(CONFIG_LINE), `not the config notice: ${JSON.stringify(t.slice(0, 160))}`)
  assert.match(t, /notice/i, `the config notice toast is not marked as a notice: ${JSON.stringify(t.slice(0, 160))}`)
  assert.doesNotMatch(t, /^Decision watch: (FLAG|UNKNOWN|ALLOW)/, 'the config notice toast reads as a verdict')
}

// Case 1: an ALLOW turn that carries a notice: one toast, the notice, and no verdict toast. Two paths reach it.
const ALLOW_NOTICE_ROWS = [
  ['phase 2 ALLOW with a config notice', { py2: splitOut('', [CONFIG_NOTICE]) }],
  ['cheap path, no model due, with a config notice', { py1: splitOut('', [CONFIG_NOTICE]) }],
]
for (const [label, opts] of ALLOW_NOTICE_ROWS) {
  await test(`config notice: an ALLOW turn shows the notice as its own toast (${label})`, async () => {
    const h = await load(host(opts))
    await fire(h, 'turn.complete', turnEvent(), {})
    await judged(h)
    await settle(60)
    same(h.toasts.length, 1, 'toast count')
    noticeToast(h.toasts[0])
  })
}

// Case 2: a FLAG that carries a notice: two toasts, the FLAG text exactly and the notice, kept apart.
await test('config notice: a FLAG with a config notice shows two toasts, the FLAG and the notice', async () => {
  const h = await load(host({ py2: splitOut(FLAG, [CONFIG_NOTICE]) }))
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  await settle(60)
  same(h.toasts.length, 2, 'toast count')
  assert.ok(h.toasts.includes(FLAG), `no toast holds the FLAG text exactly: ${JSON.stringify(h.toasts.map(t => t.slice(0, 80)))}`)
  noticeToast(h.toasts.find(t => t !== FLAG))
})

// The same holds for an UNKNOWN verdict: the UNKNOWN text exactly, and the notice as its own toast.
await test('config notice: an UNKNOWN with a config notice shows two toasts, the UNKNOWN and the notice', async () => {
  const TEXT = UNKNOWN + 'the model judgment could not be completed (model call: model down).'
  const h = await load(host({ py2: splitOut(TEXT, [CONFIG_NOTICE]) }))
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  await settle(60)
  same(h.toasts.length, 2, 'toast count')
  assert.ok(h.toasts.includes(TEXT), `no toast holds the UNKNOWN text exactly: ${JSON.stringify(h.toasts.map(t => t.slice(0, 80)))}`)
  noticeToast(h.toasts.find(t => t !== TEXT))
})

// A toast that throws is logged, never silent. The verdict line is written before the toast, so the log keeps it.
await test('toast failure: a FLAG whose toast throws is logged, and a log line names the toast failure', async () => {
  const h = await load(host({ model: () => ({ isAnswered: true, text: FLAG_REPLY, usage: {} }) }))
  h.$.ui.toast = async () => { throw new Error('toast host down') }
  const logged = waitLog(h, /toast/i)
  logged.catch(() => {})
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  assert.match(await logged, /toast/i, 'no log line names the toast failure')
})

// ---- the model table (decision subagent-model-cap): a mod that calls a model has a row

await test('model table: a row names mods/decision-watch, and that row names haiku', () => {
  const rows = readFileSync(MODEL_CAP, 'utf8').split('\n').filter(l => l.startsWith('|'))
  const row = rows.find(l => l.includes('mods/decision-watch'))
  assert.ok(row, 'no model-table row names mods/decision-watch')
  assert.match(row, /\bhaiku\b/, 'the mods/decision-watch row does not name haiku')
})

// ---- the ping bug: $.model.complete returns { isAnswered, text, usage }

await test('ping: a model object reply reaches python as its .text, and a string reply works too', async () => {
  const replies = [
    ['object', { isAnswered: true, text: FLAG_REPLY, usage: {} }],
    ['string', FLAG_REPLY],
  ]
  for (const [label, reply] of replies) {
    const h = await load(host({ model: () => reply }))
    await fire(h, 'turn.complete', turnEvent(), {})
    await judged(h)
    same(pyCalls(h)[1].argv[4], FLAG_REPLY, `${label}: reply text sent to python`)
    assert.ok(!h.procs.some(p => p.argv.some(a => String(a).includes('[object Object]'))), `${label}: [object Object] reached python`)
  }
})

await test('ping: a model object with no text never sends [object Object], and reads as UNKNOWN', async () => {
  const h = await load(host({ model: () => ({ isAnswered: false, usage: {} }) }))
  await fire(h, 'turn.complete', turnEvent(), {})
  const endData = await judged(h)
  assert.ok(!h.procs.some(p => p.argv.some(a => String(a).includes('[object Object]'))), '[object Object] reached python')
  assert.match(endData, /UNKNOWN/, 'log holds no UNKNOWN')
  assert.doesNotMatch(endData, /ALLOW/, 'log holds ALLOW for a reply with no text')
})

// ---- python: which, and the script path

await test('python: the first python on PATH that is not under WindowsApps', async () => {
  const h = await load(host({ finder: { exitCode: 0, stdout: '/store/WindowsApps/python3.exe\r\n' + PY + '\r\n', stderr: '' } }))
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  const first = pyCalls(h)[0].argv[0]
  assert.ok(!/WindowsApps/i.test(first), `spawned the store stub: ${first}`)
  same(first, PY, 'python spawned')
})

// Stock macOS has python3 and no python. which -a, like where.exe, exits 1 when any name it was given is missing,
// even after it printed a path for the others. Each name is looked up on its own, so one missing name hides no python.
const MAC_PATHS = { python3: ['/usr/bin/python3'] }
const macFinder = argv => {
  if (argv[0] !== 'which') throw new Error(`spawn ${argv[0]} ENOENT`)
  const names = argv.slice(1).filter(a => !a.startsWith('-'))
  const hits = names.flatMap(n => MAC_PATHS[n] || [])
  return { exitCode: names.every(n => MAC_PATHS[n]) ? 0 : 1, stdout: hits.map(x => x + '\n').join(''), stderr: '' }
}

await test('python: on a Mac with python3 and no python, the judge runs python3', async () => {
  const h = await load(host({ finder: macFinder }))
  await fire(h, 'turn.complete', turnEvent(), {})
  const endData = await judged(h)
  assert.doesNotMatch(endData, /no python on PATH/, 'a Mac with python3 read as no python')
  same(pyCalls(h)[0] && pyCalls(h)[0].argv[0], '/usr/bin/python3', 'python spawned')
})

await test('script path: CLAUDE_CONFIG_DIR/hooks/decision_watch.py', async () => {
  const h = await load(host({ env: { CLAUDE_CONFIG_DIR: 'D:/cfg/alt', HOME: '/home/u' } }))
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  same(norm(pyCalls(h)[0].argv[2]), 'D:/cfg/alt/hooks/decision_watch.py', 'script path')
})

await test('script path: with no CLAUDE_CONFIG_DIR, HOME/.claude/hooks/decision_watch.py', async () => {
  const h = await load(host({ env: { HOME: '/home/u' } }))
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  same(norm(pyCalls(h)[0].argv[2]), '/home/u/.claude/hooks/decision_watch.py', 'script path')
})

// ---- the state folder: never the real config folder

await test('state folder: the child runs with its own CLAUDE_CONFIG_DIR, never the real one, and the log lives under it', async () => {
  const h = await load(host())
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  const [p1, p2] = pyCalls(h)
  const state = norm(p1.opts.env && p1.opts.env.CLAUDE_CONFIG_DIR)
  assert.ok(state && state !== 'undefined', 'child env has CLAUDE_CONFIG_DIR')
  assert.notEqual(state, norm(REAL_CFG), 'child uses the real config folder')
  same(norm(p2.opts.env && p2.opts.env.CLAUDE_CONFIG_DIR), state, 'phase 2 state folder')
  const logWrite = h.writes.find(w => /\bEND\b/.test(w.data))
  assert.ok(logWrite && norm(logWrite.path).startsWith(state), `log path ${logWrite && logWrite.path} is not under ${state}`)
})

// ---- item 2: one cache, shared by the shadow judge and /dw. Its defect shows as "nothing to say".

await test('/dw after a shadow FLAG on the same turn still shows the FLAG, not nothing to say', async () => {
  const h = await load(host({ model: () => ({ isAnswered: true, text: FLAG_REPLY, usage: {} }) }))
  await primed(h)
  const text = shown(h, await dwRun(h))
  assert.match(text, /FLAG/, `no FLAG shown; the result ends ${tail(text)}`)
  assert.doesNotMatch(text, /nothing to say/, 'the shadow verdict muted /dw')
})

// The cache stays. A second Stop on an unchanged turn makes no second model call.
await test('cache kept: a second shadow Stop on an unchanged turn makes no second model call', async () => {
  const h = await load(host())
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  await settle(60)
  await fire(h, 'turn.complete', turnEvent(), {})
  await settle(60)
  same(h.modelReqs.length, 1, 'model calls for one unchanged turn')
})

// ---- item 3: a lost verdict is never a pass. The python marker is the one signal.

// The mod shows the python marker. The python file pins the marker itself.
await test('lost verdict: a model FLAG whose phase 2 finds the verdict already recorded shows verdict lost, never ALLOW', async () => {
  let h
  h = await load(host({
    model: () => {
      // a second judge records this turn while the model call is in flight
      const state = pyCalls(h).at(-1).opts.env.CLAUDE_CONFIG_DIR
      h.seen.add(`${state}|${SID}`)
      return { isAnswered: true, text: FLAG_REPLY, usage: {} }
    },
  }))
  await fire(h, 'turn.complete', turnEvent(), {})
  const endData = await judged(h)
  assert.match(endData, /UNKNOWN/, 'no UNKNOWN')
  assert.match(endData, /verdict lost/, 'no verdict lost')
  assert.doesNotMatch(endData, /ALLOW/, 'ALLOW for a lost FLAG')
})

// Green guard: a valid ALLOW with a silent phase 2 is still ALLOW. A "silent means lost" rule would break this.
await test('ALLOW guard: a model ALLOW with a silent phase 2 still reads ALLOW, never verdict lost', async () => {
  const h = await load(host())
  await fire(h, 'turn.complete', turnEvent(), {})
  const endData = await judged(h)
  assert.match(endData, /ALLOW \(silent\)/, 'ALLOW lost')
  assert.doesNotMatch(endData, /verdict lost/, 'a valid ALLOW read as lost')
})

// ---- item 4: the JSON on python's stdin is ASCII-only. python -I reads stdin as cp1252 on this PC.

await test('stdin: the JSON sent to python is ASCII-only, and a non-ASCII path round-trips', async () => {
  const cwd = '/work/café/repo'
  // U+FFFF is the top of the escaped range: it must escape, and round-trip. The app names the transcript folder from the
  // cwd with every non-alphanumeric character as "-", so the non-ASCII path comes from the config folder.
  const h = await load(host({ cwd, env: { CLAUDE_CONFIG_DIR: '/cfg/café\uFFFF', HOME: '/home/u' } }))
  const transcript = transcriptOf(h)
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  assert.ok(pyCalls(h).length > 0, 'no python call')
  for (const p of pyCalls(h)) {
    assert.ok(/^[\x00-\x7f]*$/.test(p.opts.stdin), `non-ASCII on stdin: ${p.opts.stdin}`)
    same(JSON.parse(p.opts.stdin).cwd, cwd, 'cwd round trip')
    same(JSON.parse(p.opts.stdin).transcript_path, transcript, 'path round trip')
  }
})

// ---- item 5: one shadow judge at a time. The busy slot is freed on success and on failure.

await test('busy: one shadow judge at a time; a Stop during a judge logs SKIP busy and returns at once', async () => {
  let release
  const gate = new Promise(r => { release = r })
  const h = await load(host({ model: () => gate.then(() => ({ isAnswered: true, text: ALLOW_REPLY, usage: {} })) }))
  try {
    await fire(h, 'turn.complete', turnEvent(), {})
    await settle(20)
    const skipped = waitLog(h, /SKIP busy/)
    skipped.catch(() => {})
    const NEXT = { decision: 'pass' }
    assert.equal(await within(fire(h, 'turn.complete', turnEvent(), NEXT), 1000, 'the second Stop waited for the busy judge'), NEXT)
    await skipped
    same(pyCalls(h).filter(p => p.argv.includes('--emit-prompt')).length, 1, 'phase 1 runs for the busy judge only')
    same(h.modelReqs.length, 1, 'model calls in flight')
  } finally {
    release()
  }
})

// Green guard: a failed judge frees the slot. The next Stop judges again, and never reads SKIP busy.
await test('busy guard: a failed judge frees the slot, so the next Stop judges again', async () => {
  let calls = 0
  const h = await load(host({
    model: () => {
      calls++
      if (calls === 1) throw new Error('model down')
      return { isAnswered: true, text: ALLOW_REPLY, usage: {} }
    },
  }))
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  await settle(60)
  await fire(h, 'turn.complete', turnEvent(), {})
  await settle(60)
  same(calls, 2, 'model calls after a failed judge')
  assert.ok(!/SKIP busy/.test(allLog(h)), 'the slot was never freed')
})

// HOLE 5 (decision decision-watch-mod-limits): the one-judge slot has no watchdog. A model call that never
// resolves must free the slot at the mod's own limit, log UNKNOWN, and let the next Stop judge. The limit is a
// timer, so the case runs on fake timers and ticks past MODEL_CEILING_MS. The mod's limit is 50 s, so any
// limit up to 60 s passes this case.
const MODEL_CEILING_MS = 60000
const logNow = h => String(h.files.get(logPath(h)) ?? '')

await test('busy: a model call that never resolves frees the slot at the mod limit, logs UNKNOWN, and the next Stop judges', async () => {
  const h = await load(host({ model: () => new Promise(() => {}) }))
  mock.timers.enable({ apis: ['setTimeout'] })
  try {
    await fire(h, 'turn.complete', turnEvent(), {})
    await flush()
    assert.match(logNow(h), /START /, 'the first judge did not start')
    mock.timers.tick(MODEL_CEILING_MS)
    await flush()
    assert.match(logNow(h), /UNKNOWN/, 'no UNKNOWN after the limit: the slot is held by the hung model call')
    h.model = () => ({ isAnswered: true, text: ALLOW_REPLY, usage: {} })
    await fire(h, 'turn.complete', turnEvent(), {})
    await flush()
    assert.doesNotMatch(logNow(h), /SKIP busy/, 'the next Stop was skipped as busy')
    same((logNow(h).match(/START /g) || []).length, 2, 'judges started')
  } finally {
    mock.timers.reset()
  }
})

// The python side of the same hole: a python call that never returns (the finder, or either phase) holds the slot.
// The slot must free within 60 s (a ceiling this file guesses, as MODEL_CEILING_MS is). Steps of 5 s, each with a
// flush, so a deadline that starts after a microtask still fires inside the run.
const HUNG = () => new Promise(() => {})
const HUNG_ROWS = [
  ['pickPython: the finder never resolves', { finder: HUNG() }],
  ['phase 1: the python call never resolves', { py1: HUNG }],
  ['phase 2: the python call never resolves after an ALLOW reply', { py2: HUNG }],
]
for (const [label, opts] of HUNG_ROWS) {
  await test(`busy: a hung python call frees the slot within 60 s, and the next Stop judges (${label})`, async () => {
    const h = await load(host(opts))
    mock.timers.enable({ apis: ['setTimeout'] })
    try {
      await fire(h, 'turn.complete', turnEvent(), {})
      await flush()
      assert.match(logNow(h), /START /, 'the first judge did not start')
      for (let i = 0; i < MODEL_CEILING_MS / 5000; i++) {
        mock.timers.tick(5000)
        await flush()
      }
      assert.match(logNow(h), /UNKNOWN/, 'no UNKNOWN after 60 s: the slot is held by the hung python call')
      h.finder = null
      h.py1 = undefined
      h.py2 = undefined
      await fire(h, 'turn.complete', turnEvent(), {})
      await flush()
      assert.doesNotMatch(logNow(h), /SKIP busy/, 'the next Stop was skipped as busy')
      same((logNow(h).match(/START /g) || []).length, 2, 'judges started')
    } finally {
      mock.timers.reset()
    }
  })
}

// ---- item 6: the log stays bounded.

const logLine = i => `2020-01-01T00:00:00.000Z old line ${i}`

await test('log: over 500 lines, the file keeps the newest 500 and ends with the new END line', async () => {
  const h = await load(host())
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  await settle(20)
  const path = logPath(h)
  h.files.set(path, Array.from({ length: 600 }, (_, i) => logLine(i) + '\n').join(''))
  await fire(h, 'turn.complete', turnEvent(), {})
  await settle(60)
  const lines = (h.files.get(path) || '').split('\n').filter(Boolean)
  assert.ok(lines.length <= 500, `log holds ${lines.length} lines`)
  assert.match(lines[lines.length - 1], /\bEND\b/, 'the last line is not the new END')
  assert.ok(!lines.some(l => l.endsWith('old line 0')), 'the oldest line was kept')
})

await test('log: past the 4 MiB read limit, the new END line is still written and the file stays bounded', async () => {
  const h = await load(host())
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  await settle(20)
  const path = logPath(h)
  h.files.set(path, Array.from({ length: 500 }, (_, i) => 'x'.repeat(10000) + ' big ' + i + '\n').join(''))
  await fire(h, 'turn.complete', turnEvent(), {})
  await settle(60)
  const text = h.files.get(path) || ''
  assert.ok(text.length <= FOUR_MIB, `log is ${text.length} characters`)
  const lines = text.split('\n').filter(Boolean)
  assert.ok(lines.length <= 500, `log holds ${lines.length} lines`)
  assert.match(lines[lines.length - 1] || '', /\bEND\b/, 'the new END line was not written')
})

// ---- item 7: /dw ends with the count of Stops seen, from the log.

await test('/dw ends with "Stops seen: N", where N counts the STOP seen lines in the log', async () => {
  const h = await load(host())
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  await settle(20)
  await fire(h, 'turn.complete', turnEvent(), {})
  await settle(60)
  const r = await dwRun(h)
  const text = String(r && r.text !== undefined ? r.text : r).trim()
  const count = (h.files.get(logPath(h)) || '').split('\n').filter(l => /STOP seen/.test(l)).length
  same(count, 2, 'STOP seen lines in the log')
  same(text.split('\n').pop(), `Stops seen: ${count}`, '/dw last line')
})

// ---- failures read UNKNOWN, never a pass. Shown through /dw, after one judged Stop.

const FAILURES = [
  ['no python: finder throws', { finderThrow: true }],
  ['no python: only the WindowsApps stub', { finder: { exitCode: 0, stdout: '/store/WindowsApps/python3.exe\r\n', stderr: '' } }],
  ['phase 1 exits 1', { py1: { exitCode: 1, stdout: '', stderr: 'boom' } }],
  ['phase 1 prints no JSON', { py1: { exitCode: 0, stdout: 'not json', stderr: '' } }],
  ['phase 1 call throws (timeout)', { py1: () => { throw new Error('timed out') } }],
  ['model call throws', { model: () => { throw new Error('model down') } }],
  ['model reply has no text', { model: () => ({ isAnswered: false, usage: {} }) }],
  ['phase 2 exits 1', { py2: { exitCode: 1, stdout: '', stderr: 'boom' } }],
  ['phase 2 prints no JSON', { py2: { exitCode: 0, stdout: 'garbage', stderr: '' } }],
  ['model failed and phase 2 printed nothing', { model: () => { throw new Error('model down') }, py2: { exitCode: 0, stdout: '', stderr: '' } }],
]

for (const [label, opts] of FAILURES) {
  await test(`failure reads UNKNOWN, never ALLOW: ${label}`, async () => {
    const h = await load(host(opts))
    await primed(h)
    const text = shown(h, await dwRun(h))
    assert.match(text, /UNKNOWN/, `no UNKNOWN shown; the result ends ${tail(text)}`)
    assert.doesNotMatch(text, /ALLOW/, 'ALLOW shown for a failed judgment')
  })
}

// ---- /dw

await test('command: /dw is registered at session start', async () => {
  const h = await load(host())
  const start = h.hooks.find(x => x.event === 'session.start')
  assert.ok(start, 'no session.start handler')
  await start.fn(h.$, {}, () => undefined)
  assert.ok(h.registered.includes('dw'), `registered: ${JSON.stringify(h.registered)}`)
})

await test('/dw: runs the judge on the latest turn, shows the result, and never shows the prompt', async () => {
  const h = await load(host())
  await primed(h)
  const text = shown(h, await dwRun(h))
  same(JSON.parse(pyCalls(h)[0].opts.stdin).transcript_path, TRANSCRIPT, 'latest turn')
  assert.match(text, /ALLOW/, `no verdict shown; the result ends ${tail(text)}`)
  assert.ok(!text.includes(SENTINEL), 'the prompt was shown')
})

await test('/dw: shows a FLAG', async () => {
  const h = await load(host({ model: () => ({ isAnswered: true, text: FLAG_REPLY, usage: {} }) }))
  await primed(h)
  const text = shown(h, await dwRun(h))
  assert.match(text, /FLAG/, `no FLAG shown; the result ends ${tail(text)}`)
})

// ---- the log: verdict line and timings, never the prompt

await test('log: holds the verdict line and timings, never the prompt text', async () => {
  const h = await load(host({ model: () => ({ isAnswered: true, text: FLAG_REPLY, usage: {} }) }))
  await fire(h, 'turn.complete', turnEvent(), {})
  const endData = await judged(h)
  assert.ok(!allLog(h).includes(SENTINEL), 'the prompt text reached the log')
  assert.match(endData, /\d+ ms/, 'timings missing')
  assert.match(endData, /FLAG/, 'verdict line missing')
})

// ---- HOLE 12 (decision decision-watch-mod-limits): unread-subject notices under the mod. register.mjs runs python
// with CLAUDE_CONFIG_DIR set to the mod's state folder, so collect_unread reads guard.log there, not in the real
// config folder. These cases run the real decision_watch.py with the env register.mjs passes.

const REPO_PY = fileURLToPath(new URL('../../hooks/decision_watch.py', import.meta.url))
const SUBJECT = 'UNREAD-SUBJECT-ALPHA-3'
const pad = n => String(n).padStart(2, '0')
// A naive local stamp, the form guard_core writes into guard.log.
const localStamp = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`

// The first python on PATH that runs. The Store stub prints a message and exits non-zero. null when none runs.
function pythonCmd() {
  for (const c of ['python', 'python3']) {
    const r = spawnSync(c, ['--version'], { encoding: 'utf8' })
    if (r.status === 0 && !/WindowsApps/i.test(`${r.stdout}${r.stderr}`)) return c
  }
  return null
}
const PY_CMD = pythonCmd()

// A real child, started as register.mjs starts it: the mod's argv, with the script path set to this repo's script.
function realRun(argv, o) {
  const rest = argv.slice(1).map(a => (/hooks[\\/]decision_watch\.py$/.test(a) ? REPO_PY : a))
  const r = spawnSync(argv[0], rest, { input: o.stdin, env: { ...process.env, ...o.env }, encoding: 'utf8', timeout: o.timeoutMs || 30000 })
  return { exitCode: r.status ?? -1, stdout: r.stdout || '', stderr: r.stderr || (r.error ? String(r.error) : '') }
}

// A real transcript (one human turn, one reply after it), a clean git repo as cwd, and a guard.log in the real config
// folder holding one unread-subject line from this turn.
function unreadFixture() {
  const root = mkdtempSync(join(tmpdir(), 'dw-unread-'))
  const cfg = join(root, 'real-config')
  const repo = join(root, 'repo')
  mkdirSync(cfg)
  mkdirSync(repo)
  spawnSync('git', ['init', '-q'], { cwd: repo })
  spawnSync('git', ['-c', 'user.name=test', '-c', 'user.email=test@example.invalid', 'commit', '-q', '--allow-empty', '-m', 'base'], { cwd: repo })
  // At the path the mod derives for this session: <config folder>/projects/<cwd, non-alphanumerics as "-">/<session id>.jsonl
  const transcript = join(cfg, 'projects', repo.replace(/[^A-Za-z0-9]/g, '-'), SID + '.jsonl')
  mkdirSync(dirname(transcript), { recursive: true })
  const records = [
    { type: 'user', timestamp: new Date(Date.now() - 60000).toISOString(), message: { role: 'user', content: 'check the record folders' } },
    { type: 'assistant', timestamp: new Date().toISOString(), message: { role: 'assistant', content: [{ type: 'text', text: 'done' }] } },
  ]
  writeFileSync(transcript, records.map(r => JSON.stringify(r)).join('\n') + '\n')
  // guard.log fields: when, tool, decision, rule, matched, session
  writeFileSync(join(cfg, 'guard.log'), [localStamp(new Date()), 'Bash', 'noted', 'subject-unread', SUBJECT, SID].join('\t') + '\n')
  return { cfg, repo, transcript }
}

// The Stop judge through register.mjs, with the python call run for real. h.runs records each child.
async function realStop(fx) {
  const h = await load(host({
    env: { CLAUDE_CONFIG_DIR: fx.cfg },
    cwd: fx.repo,
    finder: { exitCode: 0, stdout: PY_CMD + '\n', stderr: '' },
  }))
  const fake = h.$.process.run
  h.runs = []
  h.$.process.run = async (argv, o = {}) => {
    if (argv[0] !== PY_CMD || argv[1] !== '-I') return fake(argv, o)
    const r = realRun(argv, o)
    h.runs.push(r)
    return r
  }
  return h
}

await test('HOLE 12: under the mod env, a real python run shows the unread subject from the real config folder', async () => {
  assert.ok(PY_CMD, 'no python on PATH, so the real-python case cannot run')
  const fx = unreadFixture()
  const h = await realStop(fx)
  await fire(h, 'turn.complete', turnEvent(), {})
  await within(h.endLogged, 30000, 'the shadow log END line')
  await settle(60)
  assert.ok(h.runs.length > 0 && h.runs.every(r => r.exitCode === 0), `python did not run clean: ${JSON.stringify(h.runs.map(r => r.stderr.slice(0, 300)))}`)
  const notices = h.toasts.filter(t => /notice/i.test(t))
  same(notices.length, 1, 'notice toasts')
  assert.ok(notices[0].includes(SUBJECT), `the notice does not name the unread subject: ${JSON.stringify(notices[0].slice(0, 200))}`)
})

// The control: the same fixture, read with the real folder as CLAUDE_CONFIG_DIR. It must pass on the old code too,
// so a red above comes from the state folder and not from the fixture.
await test('HOLE 12 control: the same log, read under the real folder, gives one notice', async () => {
  assert.ok(PY_CMD, 'no python on PATH, so the real-python case cannot run')
  const fx = unreadFixture()
  const r = realRun([PY_CMD, '-I', fx.cfg + '/hooks/decision_watch.py', '--emit-prompt'], {
    stdin: JSON.stringify(stopEvent({ transcript_path: fx.transcript, cwd: fx.repo })),
    env: { CLAUDE_CONFIG_DIR: fx.cfg },
  })
  same(r.exitCode, 0, `python exit code, stderr ${JSON.stringify(r.stderr.slice(0, 200))}`)
  const out = JSON.parse(r.stdout)
  same(out.notices.length, 1, 'notices under the real folder')
  assert.ok(out.notices[0].includes(SUBJECT), `the notice does not name the unread subject: ${JSON.stringify(out.notices[0])}`)
})

// HOLE 13 (same decision): the END line is cut at MAX_LINE (2000 characters), so a notice past the cut leaves the log
// (its toast still shows). The normal flow cannot reach 3000 characters, so a 3000-character verdict stands in for a
// long trace. The check reads every log write, not only END, so a fix may shorten or split lines.
await test('HOLE 13: the END log keeps every notice when the line runs 3000 characters', async () => {
  const LONG = 'v'.repeat(3000)
  const MERGE = pyConst('MERGE_MESSAGE').replace('%s', 'PR #9') + pyConst('TAIL')
  const h = await load(host({ py1: splitOut(LONG, [CONFIG_NOTICE, MERGE]) }))
  await fire(h, 'turn.complete', turnEvent(), {})
  await judged(h)
  await settle(60)
  const logged = allLog(h)
  for (const n of [CONFIG_NOTICE, MERGE]) {
    assert.ok(logged.includes('NOTICE: ' + n), `the log lost a notice: ${JSON.stringify(n.slice(0, 80))}`)
  }
})

// ---- dw-unread-dir. Guessed contract points, as the HOLE cases above: a config
// notice is written as its own NOTICE line, `<stamp> NOTICE <sid> | NOTICE: <text>`; the mod does not cap a notice, so
// a long one reaches the log whole; a newline in a notice must not start a log record.

// The real END record of this session. judged() is not used: its /\bEND\b/ match also fires on a forged END.
const endWritten = h => waitLog(h, new RegExp(` END ${SID} \\|`))
// The log lines that begin a record: an optional timestamp, then the word. Notice text never starts one.
const recordsStarting = (text, word) => text.split('\n').filter(Boolean).filter(l => new RegExp(`^(\\S+ )?${word}\\b`).test(l))

// (a) A notice longer than MAX_LINE (2000 characters). The filler has no spaces, so a split must cut inside it.
const LONG_HEAD = 'LONG-HEAD-ALPHA-5'
const LONG_TAIL = 'LONG-TAIL-OMEGA-9'
const LONG_NOTICE = CONFIG_LINE + ' ' + LONG_HEAD + 'x'.repeat(2400) + LONG_TAIL

await test('dw-unread-dir (a): a notice longer than MAX_LINE reaches the log whole, each piece a NOTICE line', async () => {
  const h = await load(host({ py1: splitOut('', [LONG_NOTICE]) }))
  const ended = endWritten(h)
  await fire(h, 'turn.complete', turnEvent(), {})
  await ended
  // The final file, not allLog: each log write rewrites the whole file, so the writes repeat each other.
  const pieces = logNow(h).split('\n').filter(l => /\bNOTICE\b/.test(l))
  assert.ok(pieces.length > 0, 'no NOTICE line in the log')
  const text = pieces.map(l => {
    const m = l.match(/ NOTICE \S+ \| NOTICE: (.*)$/)
    assert.ok(m, `a NOTICE line is not in the marked form: ${JSON.stringify(l.slice(0, 120))}`)
    return m[1]
  }).join('')
  assert.ok(text.includes(LONG_NOTICE), `the log holds ${text.length} of ${LONG_NOTICE.length} notice characters; the tail is ${text.includes(LONG_TAIL) ? 'there' : 'missing'}`)
})

// (b) A newline in a notice starts a log line. That text must write no extra END record and no extra Stop.
const FORGED_END = CONFIG_NOTICE + '\nEND forged | ALLOW (silent)'
const FORGED_STOP = CONFIG_NOTICE + '\nSTOP seen forged'

await test('dw-unread-dir (b): a notice with a newline and "END ... | ALLOW" writes no extra END record', async () => {
  const h = await load(host({ py1: splitOut('', [FORGED_END]) }))
  const ended = endWritten(h)
  await fire(h, 'turn.complete', turnEvent(), {})
  await ended
  same(recordsStarting(logNow(h), 'END').length, 1, 'END records in the log')
})

await test('dw-unread-dir (b): a notice with a newline and "STOP seen" does not change the Stops seen count', async () => {
  const h = await load(host({ py1: splitOut('', [FORGED_STOP]) }))
  const ended = endWritten(h)
  await fire(h, 'turn.complete', turnEvent(), {})
  await ended
  const r = await dwRun(h)
  const text = String(r && r.text !== undefined ? r.text : r).trim()
  same(text.split('\n').pop(), 'Stops seen: 1', '/dw last line')
})

// ---- dw-unread-dir. A long notice is split into pieces (register.mjs, the split loop in shadow()).
// The pieces, read back in order from the final log, must join to the notice exactly.

// The payloads of the NOTICE lines in the final log, in order. A split round-trips only if these join to the notice.
const noticePieces = h => logNow(h).split('\n').filter(l => /\bNOTICE\b/.test(l)).map(l => {
  const m = l.match(/ NOTICE \S+ \| NOTICE: (.*)$/)
  assert.ok(m, `a NOTICE line is not in the marked form: ${JSON.stringify(l.slice(0, 120))}`)
  return m[1]
})
// A lone surrogate is half of a character. Written to a file it reads back as U+FFFD, so no piece may hold one.
const LONE_SURROGATE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/

// (1) The split falls between the two halves of a surrogate pair: 1920 characters, then an emoji, then TAIL.
const EMOJI_NOTICE = 'x'.repeat(1920) + '😀' + 'TAIL'

await test('dw-unread-dir round 2 (1): a split long notice cuts no surrogate pair, and the pieces join back to the notice', async () => {
  const h = await load(host({ py1: splitOut('', [EMOJI_NOTICE]) }))
  const ended = endWritten(h)
  await fire(h, 'turn.complete', turnEvent(), {})
  await ended
  const pieces = noticePieces(h)
  assert.ok(pieces.length > 0, 'no NOTICE line in the log')
  for (const p of pieces) assert.doesNotMatch(p, LONE_SURROGATE, `a piece holds half a surrogate pair, ends ${JSON.stringify(p.slice(-6))}`)
  same(pieces.join(''), EMOJI_NOTICE, 'the joined pieces')
})

// (2) The split falls on a space. The space starts the second piece, and log() folds whitespace on every line,
// so the space must survive the fold for the pieces to join back to the notice.
const SPACE_NOTICE = 'x'.repeat(1921) + ' next ' + 'y'.repeat(50)

await test('dw-unread-dir round 2 (2): a space at a piece boundary survives the whitespace fold, so the pieces join back', async () => {
  const h = await load(host({ py1: splitOut('', [SPACE_NOTICE]) }))
  const ended = endWritten(h)
  await fire(h, 'turn.complete', turnEvent(), {})
  await ended
  const pieces = noticePieces(h)
  assert.ok(pieces.length > 0, 'no NOTICE line in the log')
  same(pieces.join(''), SPACE_NOTICE, 'the joined pieces')
})

// ---- python is found once per module load
// The scope is the module load. A /clear gives the process a new session id with no session.start and no reload
// (SessionEndInput in the host types), and the module's variables survive it. A reload starts them over. The path
// is a fact of the machine, so a new session id does not look again.
// "Fails to start" is a rejected $.process.run. A host may resolve a failed start with a non-zero exit instead, so a
// non-zero exit from a cached path whose file is gone ($.fs.exists false) also counts. A python that exits
// non-zero from a file that exists has started.

const FINDER = /^(where(\.exe)?|which)$/
const finds = h => h.procs.filter(p => FINDER.test(p.argv[0]))
const endLines = h => (logNow(h).match(/^\S+ END /gm) || []).length
const PY2 = '/opt/py312/python3'
const SID2 = 'bbbbbbbb-1111-2222-3333-444444444444'

// One Stop, then wait for its judge to log END and free the one-judge slot, so the next Stop judges too.
async function turnJudged(h) {
  const want = endLines(h) + 1
  await fire(h, 'turn.complete', turnEvent(), {})
  const t0 = Date.now()
  while (endLines(h) < want && Date.now() - t0 < 3000) await settle(5)
  same(endLines(h), want, 'END lines after the Stop: the judge never finished')
  await settle(10)
  assert.ok(!/SKIP busy/.test(logNow(h)), 'a Stop was skipped as busy, so it never judged')
}

await test('python once: two Stops run the finder once, and the second Stop spawns the found path', async () => {
  const h = await load(host())
  await turnJudged(h)
  const afterFirst = pyCalls(h).length
  await turnJudged(h)
  same(finds(h).length, 1, 'finder calls for two Stops')
  assert.ok(pyCalls(h).length > afterFirst, 'the second Stop never reached python, so the finder count proves nothing')
  same([...new Set(pyCalls(h).map(p => p.argv[0]))], [PY], 'paths python was spawned with')
})

await test('python once: a Stop and a /dw share the one finder call', async () => {
  const h = await load(host())
  await turnJudged(h)
  const afterStop = pyCalls(h).length
  await dwRun(h)
  same(finds(h).length, 1, 'finder calls for a Stop and a /dw')
  assert.ok(pyCalls(h).length > afterStop, '/dw never reached python, so the finder count proves nothing')
  same([...new Set(pyCalls(h).map(p => p.argv[0]))], [PY], 'paths python was spawned with')
})

await test('python once: a cached path that fails to start is tried first, then the finder runs again and its new path is used', async () => {
  const h = await load(host())
  await turnJudged(h)
  await turnJudged(h)
  // The machine changes: the cached path is gone, and the finder now answers PY2.
  const gone = argv => { if (argv[0] === PY) throw new Error(`spawn ${PY} ENOENT`) }
  h.py1 = gone
  h.py2 = gone
  h.finder = { exitCode: 0, stdout: PY2 + '\r\n', stderr: '' }
  const mark = h.procs.length
  await turnJudged(h)
  await turnJudged(h)
  const after = h.procs.slice(mark)
  same(after[0].argv[0], PY, 'the first call after the path broke: the cached path, not the finder')
  same(after.filter(p => p.argv[0] === PY).length, 1, 'tries of the dead path')
  same(finds(h).length, 2, 'finder calls: one at the start, one after the cached path failed')
  same(pyCalls(h).at(-1).argv[0], PY2, 'path of the last python call')
})

// The host resolves a failed start with a non-zero exit, and the cached file is gone.
await test('python once: a non-zero exit from a cached path whose file is gone sends the next Stop to the finder, and its new path is used', async () => {
  const h = await load(host())
  h.files.set(PY, '')
  await turnJudged(h)
  h.files.delete(PY)
  const gone = argv => (argv[0] === PY ? { exitCode: 127, stdout: '', stderr: 'cannot start ' + PY } : undefined)
  h.py1 = gone
  h.py2 = gone
  h.finder = { exitCode: 0, stdout: PY2 + '\r\n', stderr: '' }
  const mark = h.procs.length
  await turnJudged(h)
  await turnJudged(h)
  const after = h.procs.slice(mark)
  same(after[0].argv[0], PY, 'the first call after the file was deleted: the cached path, not the finder')
  same(finds(h).length, 2, 'finder calls: one at the start, one after the cached file was deleted')
  same(after.filter(p => p.argv[0] === PY).length, 1, 'tries of the deleted path')
  same(pyCalls(h).at(-1).argv[0], PY2, 'path of the last python call')
})

// A failed $.fs.exists leaves the file unknown, and an unknown file reads as gone: a kept dead path would stick.
// The run's own result still reaches the judge, whichever way the check fails.
for (const [label, broken] of [
  ['rejects', p => Promise.reject(new Error('exists rejected for ' + p))],
  ['throws synchronously', p => { throw new Error('exists threw for ' + p) }],
]) {
  await test(`python once: a non-zero exit from a cached path when $.fs.exists ${label} keeps that run's result and sends the next Stop to the finder`, async () => {
    const h = await load(host())
    h.files.set(PY, '')
    await turnJudged(h)
    const exists = h.$.fs.exists
    h.$.fs.exists = p => (p === PY ? broken(p) : exists(p))
    const gone = argv => (argv[0] === PY ? { exitCode: 127, stdout: '', stderr: 'cannot start ' + PY } : undefined)
    h.py1 = gone
    h.py2 = gone
    h.finder = { exitCode: 0, stdout: PY2 + '\r\n', stderr: '' }
    const mark = h.procs.length
    await turnJudged(h)
    const endLine = logNow(h).split('\n').filter(l => /^\S+ END /.test(l)).at(-1)
    assert.match(endLine, /decision_watch exited 127/, `the run's exit 127 never reached the judge: ${endLine}`)
    assert.doesNotMatch(endLine, /MOD ERROR/, 'the failed check discarded the run result')
    await turnJudged(h)
    const after = h.procs.slice(mark)
    same(after[0].argv[0], PY, 'the first call after the break: the cached path, not the finder')
    same(finds(h).length, 2, 'finder calls: one at the start, one after the check failed')
    same(after.filter(p => p.argv[0] === PY).length, 1, 'tries of the cached path')
    same(pyCalls(h).at(-1).argv[0], PY2, 'path of the last python call')
  })
}

await test('python once: a python that exits non-zero from a file that exists keeps the path, so the next Stop does not run the finder', async () => {
  const h = await load(host())
  h.files.set(PY, '')
  await turnJudged(h)
  h.py1 = { exitCode: 1, stdout: '', stderr: 'script error' }
  await turnJudged(h)
  await turnJudged(h)
  same(finds(h).length, 1, 'finder calls when python started and the script failed')
})

// A find that fails has no result to keep. A cached failure would hold until the app restarts.
for (const [label, opts] of [
  ['the finder throws', { finderThrow: true }],
  ['only the WindowsApps stub is on PATH', { finder: { exitCode: 0, stdout: '/store/WindowsApps/python3.exe\r\n', stderr: '' } }],
]) {
  await test(`python once: a find that failed is not kept, so the next Stop looks again (${label})`, async () => {
    const h = await load(host(opts))
    await turnJudged(h)
    same(pyCalls(h).length, 0, 'python calls while no python was found')
    const before = finds(h).length
    h.finderThrow = false
    h.finder = null
    await turnJudged(h)
    assert.ok(finds(h).length > before, 'the next Stop never ran the finder again')
    same(pyCalls(h).at(-1).argv[0], PY, 'path of the python call once one is found')
  })
}

await test('python once: separate module loads each run the finder once', async () => {
  const a = await load(host())
  const b = await load(host())
  await turnJudged(a)
  await turnJudged(b)
  await turnJudged(a)
  await turnJudged(b)
  same(finds(a).length, 1, 'finder calls, first load')
  same(finds(b).length, 1, 'finder calls, second load')
})

await test('python once: a new session id in the same load (a /clear) reuses the path', async () => {
  const h = await load(host())
  await turnJudged(h)
  const afterFirst = pyCalls(h).length
  h.sid = SID2
  await turnJudged(h)
  assert.ok(pyCalls(h).length > afterFirst, 'the new session never reached python, so the finder count proves nothing')
  same(finds(h).length, 1, 'finder calls across a session id change')
})

// ---- the background judge never leaks an unhandled rejection

await test('no unhandled rejection escaped a background judge', async () => {
  await settle(50)
  same(unhandled.map(String), [], 'unhandled rejections')
})

const fails = results.filter(r => r.startsWith('FAIL')).length
console.log(results.join('\n'))
console.log(`decision-watch pins: ${results.length - fails} pass, ${fails} fail of ${results.length}`)
if (fails) process.exitCode = 1

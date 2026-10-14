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
// write holding END; each Stop writes a "STOP seen" line; /dw's last output line is "Stops seen: N";
// the host's fs.read refuses a file over 4 MiB; the child state folder differs from the real config folder;
// a config notice is its own toast and contains the word "notice" (any case), and the verdict toast holds the
// verdict text exactly; a judge slot held by a python call that never returns frees within 60 s.
// Amended in review round 2 (were pins of e40df46): the two-phase model-call fields (timeoutMs is pinned
// on its own) and the stop_hook_active case (a STOP seen write is allowed).
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { mock } from 'node:test'

const REGISTER = fileURLToPath(new URL('./hooks/register.mjs', import.meta.url))
const REAL_CFG = '/cfg/real'
const SCRIPT = REAL_CFG + '/hooks/decision_watch.py'
const PY = '/usr/bin/python3'
const SID = 'aaaaaaaa-1111-2222-3333-444444444444'
const CWD = '/work/repo'
const TRANSCRIPT = REAL_CFG + '/projects/repo/' + SID + '.jsonl'
const SENTINEL = 'PROMPT-SENTINEL-ALPHA-7'
const PROMPT = 'Judge this turn. ' + SENTINEL
const ALLOW_REPLY = '{"verdict": "ALLOW"}'
const FLAG_REPLY = '{"verdict": "FLAG", "why": "reversed silently"}'
// The message texts are read from the script, so the fake python prints what the Stop hook prints today.
const SCRIPT_SRC = fileURLToPath(new URL('../../hooks/decision_watch.py', import.meta.url))
const MODEL_CAP = fileURLToPath(new URL('../../decisions/subagent-model-cap.md', import.meta.url))
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

// Machine-path scan over the whole text, comments included, on purpose: it does not parse the source.
const MACHINE = [
  /(?<![A-Za-z])[A-Za-z]:(?!\/\/)[\\/]/,
  /ShivamSemwal|SHIVAM~1|AppData|Clones|claude-settings|scratchpad|C--Users/,
  /\/Users\/|\/home\//,
  /\\Users\\/,
]
const machinePaths = text => MACHINE.map(re => text.match(re)).filter(Boolean).map(m => m[0])

// Code only: comments are dropped, and string and template text are blanked. A ${...} inside a template
// is code, so it is kept. A small lexer for the shapes the scanner rule names: comment openers inside
// strings, multi-line template literals, and a lone quote in text.
function codeOf(src) {
  const out = []
  const frames = [{ tpl: false, braces: 0, interp: false }]
  let i = 0
  while (i < src.length) {
    const top = frames[frames.length - 1]
    const c = src[i]
    const d = src[i + 1]
    if (top.tpl) {
      if (c === '\\') { out.push('  '); i += 2; continue }
      if (c === '`') { frames.pop(); i++; continue }
      if (c === '$' && d === '{') { frames.push({ tpl: false, braces: 0, interp: true }); out.push('  '); i += 2; continue }
      out.push(c === '\n' ? '\n' : ' ')
      i++
      continue
    }
    if (c === '/' && d === '/') { while (i < src.length && src[i] !== '\n') i++; continue }
    if (c === '/' && d === '*') { const end = src.indexOf('*/', i + 2); i = end < 0 ? src.length : end + 2; out.push(' '); continue }
    if (c === '"' || c === "'") {
      let j = i + 1
      while (j < src.length && src[j] !== c && src[j] !== '\n') j += src[j] === '\\' ? 2 : 1
      out.push(' ')
      i = j + 1
      continue
    }
    if (c === '`') { frames.push({ tpl: true, braces: 0, interp: false }); i++; continue }
    if (c === '{') { top.braces++; out.push(c); i++; continue }
    if (c === '}') {
      if (top.interp && top.braces === 0) { frames.pop(); i++; continue }
      top.braces--
      out.push(c)
      i++
      continue
    }
    out.push(c)
    i++
  }
  return out.join('')
}

// Bare noun reads: $.noun.method that is not called. The \b stops a longer name matching a prefix.
const BARE_NOUN = /\$\.[A-Za-z_]\w*\.[A-Za-z_]\w*\b(?!\s*\()/g
const bareNouns = text => [...text.matchAll(BARE_NOUN)].map(m => m[0])
const codeNouns = text => bareNouns(codeOf(text))

// ---- the scanners, on the shapes the scanner rule names

await test('machine-path scan: flags a path after // in a string, in a multi-line template literal, and beside a lone quote', () => {
  assert.ok(machinePaths('const u = "http://a.test/"; const p = "D:/work/x"').length > 0, 'path after // in a string')
  assert.ok(machinePaths('const t = `first\nD:/work/x\nlast`').length > 0, 'path in a multi-line template literal')
  assert.ok(machinePaths("const q = \"<p>Don't</p>\"; const p = 'C:\\\\Work\\\\y'").length > 0, 'path beside a lone quote')
})

await test('machine-path scan: passes clean text, a lone quote in text, and the WindowsApps store name', () => {
  same(machinePaths("const s = \"<p>Don't</p>\"; const w = 'WindowsApps'"), [], 'clean text')
})

await test('code-only scan: a line comment, a block comment, and template text hide a bare noun; code and ${} do not', () => {
  same(codeNouns('// do not call $.fs.mkdir here\nconst x = 1'), [], 'line comment')
  same(codeNouns('/* $.fs.mkdir */ const x = 1'), [], 'block comment')
  same(codeNouns('const t = `text $.fs.mkdir text`'), [], 'template text')
  same(codeNouns('const t = `${$.fs.mkdir}`'), ['$.fs.mkdir'], 'interpolation is code')
})

await test('code-only scan: comment openers inside strings do not hide a bare noun in the code after them', () => {
  same(codeNouns('const u = "http://a.test/"; typeof $.fs.mkdir'), ['$.fs.mkdir'], 'after // in a string')
  same(codeNouns('const s = "/* not a comment"; $.fs.mkdir'), ['$.fs.mkdir'], '/* inside a string')
})

await test('code-only scan: a multi-line template literal keeps its text out of code, and its interpolation in', () => {
  same(codeNouns('const t = `first\n$.fs.mkdir text\nlast ${$.fs.mkdir}`'), ['$.fs.mkdir'], 'only the interpolation')
})

await test('code-only scan: a lone quote in a comment or in a string does not hide the code after it', () => {
  same(codeNouns("// Don't call it\ntypeof $.fs.mkdir"), ['$.fs.mkdir'], 'lone quote in a comment')
  same(codeNouns('const q = "<p>Don\'t</p>"; typeof $.fs.mkdir'), ['$.fs.mkdir'], 'lone quote in a string')
  same(codeNouns("await $.fs.write(file, text); // Don't\n"), [], 'called method and a comment with a quote')
})

await test('code-only scan: a called $.fs.write and a called $.model.complete are not bare reads', () => {
  same(codeNouns('await $.fs.write(file, text); await $.model.complete({ model });'), [], 'called methods')
})

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
  assert.ok(text.includes('"classic.Stop"'), 'missing the "classic.Stop" literal')
  assert.ok(text.includes('"command.run"'), 'missing the "command.run" literal')
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
      exists: async p => h.files.has(p),
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

async function fire(h, event, e = {}, nextValue) {
  const hook = h.hooks.find(x => x.event === event && Object.entries(x.matcher).every(([k, v]) => e[k] === v))
  if (!hook) throw new Error(`no handler for ${event}`)
  return hook.fn(h.$, e, () => nextValue)
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
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  h.procs.length = 0
  h.modelReqs.length = 0
}

// ---- Stop: shadow only

await test('stop: returns next(e) at once while the model call hangs, and the Stop event is untouched', async () => {
  const h = await load(host({ model: () => new Promise(() => {}) }))
  // The mod's model deadline is a timer. Fake it, so the hung call cannot hold the run open for 50 s.
  mock.timers.enable({ apis: ['setTimeout'] })
  try {
    const e = stopEvent()
    const before = clone(e)
    const NEXT = { decision: 'pass' }
    const got = await within(fire(h, 'classic.Stop', e, NEXT), 1000, 'Stop waited for the judge')
    assert.equal(got, NEXT, 'Stop returns the object next() returned')
    same(e, before, 'Stop event')
  } finally {
    // Drain the background judge first: a deadline made after the reset would be a real 50 s timer.
    await flush()
    mock.timers.reset()
  }
})

await test('stop: a FLAG never changes the Stop result', async () => {
  const h = await load(host({ model: () => ({ isAnswered: true, text: FLAG_REPLY, usage: {} }) }))
  const e = stopEvent()
  const before = clone(e)
  const NEXT = { decision: 'pass' }
  assert.equal(await within(fire(h, 'classic.Stop', e, NEXT), 1000, 'Stop'), NEXT)
  await judged(h)
  same(e, before, 'Stop event')
  same(NEXT, { decision: 'pass' }, 'next result')
})

await test('stop: never throws when every host call throws, and still returns next(e)', async () => {
  const boom = () => { throw new Error('host down') }
  const h = await load(host({ finderThrow: true, sessionThrow: true, model: boom, py1: boom, py2: boom }))
  h.$.fs.exists = async () => { throw new Error('fs down') }
  h.$.fs.write = async () => { throw new Error('fs down') }
  h.$.env.get = async () => { throw new Error('env down') }
  const NEXT = { decision: 'pass' }
  assert.equal(await within(fire(h, 'classic.Stop', stopEvent(), NEXT), 1000, 'Stop'), NEXT)
  await settle()
})

// Amended (review round 2): a STOP seen line is allowed; no judge may start.
await test('stop: stop_hook_active skips the judge: no process call, no model call, no START or END line', async () => {
  const h = await load(host())
  const NEXT = { decision: 'pass' }
  assert.equal(await within(fire(h, 'classic.Stop', stopEvent({ stop_hook_active: true }), NEXT), 1000, 'Stop'), NEXT)
  await settle()
  same(h.procs.length, 0, 'process calls')
  same(h.modelReqs.length, 0, 'model calls')
  same(h.writes.filter(w => !/STOP seen/.test(w.data)).length, 0, 'log writes other than STOP seen')
})

// Item 7. The STOP seen line is written before Stop returns, so a viewer can tell the mod ran.
await test('stop: a STOP seen line is written before Stop returns next(e)', async () => {
  const h = await load(host({ model: () => new Promise(() => {}) }))
  mock.timers.enable({ apis: ['setTimeout'] }) // the model deadline is a timer: fake it, as in the case above
  try {
    const NEXT = { decision: 'pass' }
    assert.equal(await within(fire(h, 'classic.Stop', stopEvent(), NEXT), 1500, 'Stop'), NEXT)
    assert.ok(h.writes.some(w => /STOP seen/.test(w.data)), 'no STOP seen line was written before Stop returned')
  } finally {
    await flush() // as in the case above: the background judge's deadline must be made while the mock is on
    mock.timers.reset()
  }
})

// Item 7 guard: a write that never returns cannot hold Stop. Green on e40df46, which writes nothing before Stop returns.
await test('stop: a STOP seen write that never returns cannot hold Stop past 1.5 s', async () => {
  const h = await load(host())
  h.$.fs.write = () => new Promise(() => {})
  const NEXT = { decision: 'pass' }
  assert.equal(await within(fire(h, 'classic.Stop', stopEvent(), NEXT), 1500, 'Stop held by a hung write'), NEXT)
})

// ---- the two phases and the model call

await test('two-phase: phase 1 emits the prompt; the model call takes it with maxTokens 512 and phase 1 model; phase 2 gets the reply', async () => {
  const h = await load(host())
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  const py = pyCalls(h)
  same(py.length, 2, 'python calls: phase 1 and phase 2')
  same(py[0].argv, [PY, '-I', SCRIPT, '--emit-prompt'], 'phase 1 argv')
  same(py[1].argv.slice(0, 3), [PY, '-I', SCRIPT], 'phase 2 argv head')
  same(py[1].argv[3], '--model-text', 'phase 2 flag')
  same(py[1].argv[4], ALLOW_REPLY, 'phase 2 reply')
  // Amended: timeoutMs is pinned on its own, in the case below.
  same(h.modelReqs.map(({ timeoutMs, ...rest }) => rest), [{ model: 'haiku', prompt: PROMPT, maxTokens: 512 }], 'model call fields')
  same(JSON.parse(py[0].opts.stdin).session_id, SID, 'phase 1 stdin is the Stop JSON')
  same(JSON.parse(py[1].opts.stdin).transcript_path, TRANSCRIPT, 'phase 2 stdin is the same Stop JSON')
})

// The model call's limit is enforced by the mod's own deadline (see the busy cases below), not by a request field.

await test('model error: phase 2 gets --model-error with the message, and no --model-text', async () => {
  const h = await load(host({ model: () => { throw new Error('model down') } }))
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  const argv = pyCalls(h)[1].argv
  assert.ok(argv.includes('--model-error'), 'phase 2 has --model-error')
  assert.ok(!argv.includes('--model-text'), 'phase 2 has no --model-text')
  assert.ok(String(argv[argv.indexOf('--model-error') + 1]).includes('model down'), 'the message carries the error')
})

await test('model error: the shadow log reads UNKNOWN, never ALLOW', async () => {
  const h = await load(host({ model: () => { throw new Error('model down') } }))
  await fire(h, 'classic.Stop', stopEvent(), {})
  const endData = await judged(h)
  assert.match(endData, /UNKNOWN/, 'log holds no UNKNOWN')
  assert.doesNotMatch(endData, /ALLOW/, 'log holds ALLOW for a failed judgment')
})

// ---- HOLE 1 (decision decision-watch-mod-limits): phase 2 is given the phase-1 key.

// Red on main: main passes no key, so the moved evidence is judged afresh and reads a silent ALLOW.
await test('HOLE 1: evidence moved between the phases reads UNKNOWN, never a silent ALLOW', async () => {
  let h
  h = await load(host({
    model: () => {
      h.evidence = 'E2' // the protected file changed while the model call was in flight
      return { isAnswered: true, text: ALLOW_REPLY, usage: {} }
    },
  }))
  await fire(h, 'classic.Stop', stopEvent(), {})
  const endData = await judged(h)
  assert.doesNotMatch(endData, /ALLOW/, 'ALLOW for a verdict on evidence that moved')
  assert.match(endData, /UNKNOWN/, 'the log holds no UNKNOWN')
})

await test('HOLE 1: phase 2 is given the key phase 1 printed, as --key after the reply', async () => {
  const h = await load(host())
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  const p2 = pyCalls(h)[1].argv
  assert.ok(p2.includes('--key'), `phase 2 has no --key: ${JSON.stringify(p2)}`)
  same(p2[p2.indexOf('--key') + 1], 'key:E1', 'phase 2 key, from phase 1')
})

// A phase 1 with no key (an old decision_watch.py) cannot be tied to the evidence, so it reads UNKNOWN.
await test('HOLE 1: no key from phase 1 reads UNKNOWN, never ALLOW', async () => {
  const h = await load(host({ py1: () => out({ needs_model: true, prompt: PROMPT, model: 'haiku' }) }))
  await fire(h, 'classic.Stop', stopEvent(), {})
  const endData = await judged(h)
  assert.doesNotMatch(endData, /ALLOW/, 'ALLOW for a verdict that cannot be tied to the evidence')
  assert.match(endData, /UNKNOWN/, 'the log holds no UNKNOWN')
})

// ---- what shows in the session: the Stop hook's own systemMessage text, through $.ui.toast.
// desktop-statusline shows its notices with $.ui.toast(text, { timeoutMs }), so that is the surface.

await test('shown: a FLAG shows the Stop hook text exactly, once', async () => {
  const h = await load(host({ model: () => ({ isAnswered: true, text: FLAG_REPLY, usage: {} }) }))
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  await settle(60)
  same(h.toasts, [FLAG], 'toasts')
})

await test('shown: the FLAG wording is the one hooks/decision_watch.py prints today', () => {
  assert.ok(scriptSource.includes('FLAG_PREFIX + \'the judge model reported: "%s"\''), 'the script no longer prints this FLAG wording')
})

await test('shown: an UNKNOWN from the judge shows its exact text, once', async () => {
  const h = await load(host({ model: () => { throw new Error('model down') } }))
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  await settle(60)
  same(h.toasts, [UNKNOWN + 'the model judgment could not be completed (model call: model down).'], 'toasts')
})

await test('shown: a message from the cheap path shows its exact text, with no prefix added', async () => {
  const CHEAP = UNKNOWN + 'the transcript could not be read (no such file).'
  const h = await load(host({ py1: () => out({ systemMessage: CHEAP }) }))
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  await settle(60)
  same(h.toasts, [CHEAP], 'toasts')
})

// Guard: an ALLOW stays silent in the session. A toast on every Stop would teach the reader to skip it.
await test('shown: an ALLOW shows nothing', async () => {
  const h = await load(host())
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  await settle(60)
  same(h.toasts, [], 'toasts')
})

// ---- the config notice. decision_watch.py joins config_report() text onto its message, after the verdict, with
// " ".join at main, so a notice rides on every verdict, ALLOW included, and on a cheap-path message too.
// Arbiter ruling, 2026-10-14 00:09 CDT: each config notice is its own toast line, apart from the verdict, and is
// marked as a notice. An ALLOW verdict itself stays silent. The notice's marker is the word "notice" (any case).
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
    await fire(h, 'classic.Stop', stopEvent(), {})
    await judged(h)
    await settle(60)
    same(h.toasts.length, 1, 'toast count')
    noticeToast(h.toasts[0])
  })
}

// Case 2: a FLAG that carries a notice: two toasts, the FLAG text exactly and the notice, kept apart.
await test('config notice: a FLAG with a config notice shows two toasts, the FLAG and the notice', async () => {
  const h = await load(host({ py2: splitOut(FLAG, [CONFIG_NOTICE]) }))
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  await settle(60)
  same(h.toasts.length, 2, 'toast count')
  assert.ok(h.toasts.includes(FLAG), `no toast holds the FLAG text exactly: ${JSON.stringify(h.toasts.map(t => t.slice(0, 80)))}`)
  noticeToast(h.toasts.find(t => t !== FLAG))
})

// Same ruling for an UNKNOWN verdict: the UNKNOWN text exactly, and the notice as its own toast.
await test('config notice: an UNKNOWN with a config notice shows two toasts, the UNKNOWN and the notice', async () => {
  const TEXT = UNKNOWN + 'the model judgment could not be completed (model call: model down).'
  const h = await load(host({ py2: splitOut(TEXT, [CONFIG_NOTICE]) }))
  await fire(h, 'classic.Stop', stopEvent(), {})
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
  await fire(h, 'classic.Stop', stopEvent(), {})
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
    await fire(h, 'classic.Stop', stopEvent(), {})
    await judged(h)
    same(pyCalls(h)[1].argv[4], FLAG_REPLY, `${label}: reply text sent to python`)
    assert.ok(!h.procs.some(p => p.argv.some(a => String(a).includes('[object Object]'))), `${label}: [object Object] reached python`)
  }
})

await test('ping: a model object with no text never sends [object Object], and reads as UNKNOWN', async () => {
  const h = await load(host({ model: () => ({ isAnswered: false, usage: {} }) }))
  await fire(h, 'classic.Stop', stopEvent(), {})
  const endData = await judged(h)
  assert.ok(!h.procs.some(p => p.argv.some(a => String(a).includes('[object Object]'))), '[object Object] reached python')
  assert.match(endData, /UNKNOWN/, 'log holds no UNKNOWN')
  assert.doesNotMatch(endData, /ALLOW/, 'log holds ALLOW for a reply with no text')
})

// ---- python: which, and the script path

await test('python: the first python on PATH that is not under WindowsApps', async () => {
  const h = await load(host({ finder: { exitCode: 0, stdout: '/store/WindowsApps/python3.exe\r\n' + PY + '\r\n', stderr: '' } }))
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  const first = pyCalls(h)[0].argv[0]
  assert.ok(!/WindowsApps/i.test(first), `spawned the store stub: ${first}`)
  same(first, PY, 'python spawned')
})

await test('script path: CLAUDE_CONFIG_DIR/hooks/decision_watch.py', async () => {
  const h = await load(host({ env: { CLAUDE_CONFIG_DIR: 'D:/cfg/alt', HOME: '/home/u' } }))
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  same(norm(pyCalls(h)[0].argv[2]), 'D:/cfg/alt/hooks/decision_watch.py', 'script path')
})

await test('script path: with no CLAUDE_CONFIG_DIR, HOME/.claude/hooks/decision_watch.py', async () => {
  const h = await load(host({ env: { HOME: '/home/u' } }))
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  same(norm(pyCalls(h)[0].argv[2]), '/home/u/.claude/hooks/decision_watch.py', 'script path')
})

// ---- the state folder: never the real config folder

await test('state folder: the child runs with its own CLAUDE_CONFIG_DIR, never the real one, and the log lives under it', async () => {
  const h = await load(host())
  await fire(h, 'classic.Stop', stopEvent(), {})
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

// Green guard on e40df46: the cache stays. A second Stop on an unchanged turn makes no second model call.
await test('cache kept: a second shadow Stop on an unchanged turn makes no second model call', async () => {
  const h = await load(host())
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  await settle(60)
  await fire(h, 'classic.Stop', stopEvent(), {})
  await settle(60)
  same(h.modelReqs.length, 1, 'model calls for one unchanged turn')
})

// ---- item 3: a lost verdict is never a pass. The python marker is the one signal.

// Green pass-through on e40df46: the mod shows the python marker. The red for this is in the python file.
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
  await fire(h, 'classic.Stop', stopEvent(), {})
  const endData = await judged(h)
  assert.match(endData, /UNKNOWN/, 'no UNKNOWN')
  assert.match(endData, /verdict lost/, 'no verdict lost')
  assert.doesNotMatch(endData, /ALLOW/, 'ALLOW for a lost FLAG')
})

// Green guard: a valid ALLOW with a silent phase 2 is still ALLOW. A "silent means lost" rule would break this.
await test('ALLOW guard: a model ALLOW with a silent phase 2 still reads ALLOW, never verdict lost', async () => {
  const h = await load(host())
  await fire(h, 'classic.Stop', stopEvent(), {})
  const endData = await judged(h)
  assert.match(endData, /ALLOW \(silent\)/, 'ALLOW lost')
  assert.doesNotMatch(endData, /verdict lost/, 'a valid ALLOW read as lost')
})

// ---- item 4: the JSON on python's stdin is ASCII-only. python -I reads stdin as cp1252 on this PC.

await test('stdin: the JSON sent to python is ASCII-only, and a non-ASCII path round-trips', async () => {
  const cwd = '/work/café/repo'
  const transcript = REAL_CFG + '/projects/café/' + SID + '.jsonl'
  const h = await load(host())
  await fire(h, 'classic.Stop', stopEvent({ cwd, transcript_path: transcript }), {})
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
    await fire(h, 'classic.Stop', stopEvent(), {})
    await settle(20)
    const skipped = waitLog(h, /SKIP busy/)
    skipped.catch(() => {})
    const NEXT = { decision: 'pass' }
    assert.equal(await within(fire(h, 'classic.Stop', stopEvent(), NEXT), 1000, 'the second Stop waited for the busy judge'), NEXT)
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
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  await settle(60)
  await fire(h, 'classic.Stop', stopEvent(), {})
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
    await fire(h, 'classic.Stop', stopEvent(), {})
    await flush()
    assert.match(logNow(h), /START /, 'the first judge did not start')
    mock.timers.tick(MODEL_CEILING_MS)
    await flush()
    assert.match(logNow(h), /UNKNOWN/, 'no UNKNOWN after the limit: the slot is held by the hung model call')
    h.model = () => ({ isAnswered: true, text: ALLOW_REPLY, usage: {} })
    await fire(h, 'classic.Stop', stopEvent(), {})
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
      await fire(h, 'classic.Stop', stopEvent(), {})
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
      await fire(h, 'classic.Stop', stopEvent(), {})
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
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  await settle(20)
  const path = logPath(h)
  h.files.set(path, Array.from({ length: 600 }, (_, i) => logLine(i) + '\n').join(''))
  await fire(h, 'classic.Stop', stopEvent(), {})
  await settle(60)
  const lines = (h.files.get(path) || '').split('\n').filter(Boolean)
  assert.ok(lines.length <= 500, `log holds ${lines.length} lines`)
  assert.match(lines[lines.length - 1], /\bEND\b/, 'the last line is not the new END')
  assert.ok(!lines.some(l => l.endsWith('old line 0')), 'the oldest line was kept')
})

await test('log: past the 4 MiB read limit, the new END line is still written and the file stays bounded', async () => {
  const h = await load(host())
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  await settle(20)
  const path = logPath(h)
  h.files.set(path, Array.from({ length: 500 }, (_, i) => 'x'.repeat(10000) + ' big ' + i + '\n').join(''))
  await fire(h, 'classic.Stop', stopEvent(), {})
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
  await fire(h, 'classic.Stop', stopEvent(), {})
  await judged(h)
  await settle(20)
  await fire(h, 'classic.Stop', stopEvent(), {})
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
  await fire(h, 'classic.Stop', stopEvent(), {})
  const endData = await judged(h)
  assert.ok(!allLog(h).includes(SENTINEL), 'the prompt text reached the log')
  assert.match(endData, /\d+ ms/, 'timings missing')
  assert.match(endData, /FLAG/, 'verdict line missing')
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

// decision-watch pins. Run: node mods/decision-watch/decision-watch.test.mjs  (stdlib only; exit 1 on any FAIL)
// The mod is hooks/register.mjs. It is driven through a fake host ($), and each case loads a fresh copy.
// The python side is a fake that answers as decision_watch.py does on its three entry points:
//   --emit-prompt        {needs_model, prompt, model} when a model call is due, else the normal output
//   --model-text TEXT    FLAG as a systemMessage, ALLOW as silence, anything else as UNKNOWN
//   --model-error TEXT   UNKNOWN, always
// hooks/test_decision_watch.py pins the python side. This file pins what the mod does with it.
// Contract points the brief leaves open, guessed here: /dw is registered in a session.start handler;
// a judgment ends with a shadow-log write that holds END; the child's state folder is any folder
// other than the real config folder, and the log lives under it.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'

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
const UNKNOWN = 'Decision watch: UNKNOWN, '
const FLAG = 'Decision watch: FLAG, the judge model reported: "reversed silently".'

const norm = p => String(p).replace(/\\/g, '/')
const clone = v => JSON.parse(JSON.stringify(v))
const same = (got, want, why) => assert.deepEqual(got, want, `${why}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`)
const settle = (ms = 20) => new Promise(r => setTimeout(r, ms))
const within = (p, ms, why) => {
  let t
  const late = new Promise((_, rej) => { t = setTimeout(() => rej(new Error(`timed out after ${ms} ms: ${why}`)), ms) })
  return Promise.race([p, late]).finally(() => clearTimeout(t))
}

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

// ---- the machine-path scanner, on the four shapes the scanner rule names

await test('machine-path scan: flags a path after // in a string, in a multi-line template literal, and beside a lone quote', () => {
  assert.ok(machinePaths('const u = "http://a.test/"; const p = "D:/work/x"').length > 0, 'path after // in a string')
  assert.ok(machinePaths('const t = `first\nD:/work/x\nlast`').length > 0, 'path in a multi-line template literal')
  assert.ok(machinePaths("const q = \"<p>Don't</p>\"; const p = 'C:\\\\Work\\\\y'").length > 0, 'path beside a lone quote')
})

await test('machine-path scan: passes clean text, a lone quote in text, and the WindowsApps store name', () => {
  same(machinePaths("const s = \"<p>Don't</p>\"; const w = 'WindowsApps'"), [], 'clean text')
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

// ---- the fake host and its python

const out = obj => ({ exitCode: 0, stdout: JSON.stringify(obj) + '\n', stderr: '' })
const UNKNOWN_REPLY = out({ systemMessage: UNKNOWN + 'the model judgment could not be completed (model result carried no JSON verdict).' })

function replyOut(text) {
  const m = String(text).match(/\{.*\}/s)
  let v = null
  try { v = m ? JSON.parse(m[0]) : null } catch { v = null }
  if (v && v.verdict === 'FLAG') return out({ systemMessage: FLAG })
  if (v && v.verdict === 'ALLOW') return { exitCode: 0, stdout: '', stderr: '' }
  return UNKNOWN_REPLY
}

function defaultPython(argv) {
  if (argv.includes('--emit-prompt')) return out({ needs_model: true, prompt: PROMPT, model: 'haiku' })
  const i = argv.indexOf('--model-text')
  const j = argv.indexOf('--model-error')
  if (i >= 0) return replyOut(argv[i + 1])
  if (j >= 0) return out({ systemMessage: UNKNOWN + 'the model judgment could not be completed (' + argv[j + 1] + ').' })
  return { exitCode: 2, stdout: '', stderr: 'fake python: unknown argv' }
}

let loads = 0

function host(opts = {}) {
  const h = {
    sid: SID, cwd: CWD, env: { CLAUDE_CONFIG_DIR: REAL_CFG, HOME: '/home/u' },
    finder: null, finderThrow: false, py1: undefined, py2: undefined,
    model: () => ({ isAnswered: true, text: ALLOW_REPLY, usage: {} }),
    sessionThrow: false,
    hooks: [], procs: [], modelReqs: [], writes: [], files: new Map(), registered: [], uiLogs: [],
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
        return r ?? defaultPython(argv)
      },
    },
    model: {
      complete: async req => { h.modelReqs.push(clone(req)); return h.model(req) },
    },
    fs: {
      exists: async p => h.files.has(p),
      read: async p => h.files.get(p),
      write: async (p, data) => {
        h.writes.push({ path: p, data: String(data) })
        h.files.set(p, data)
        if (/\bEND\b/.test(String(data))) h.resolveEnd(String(data))
      },
    },
    env: { get: async k => h.env[k] },
    session: {
      id: async () => { if (h.sessionThrow) throw new Error('no session'); return h.sid },
      cwd: async () => h.cwd,
    },
    command: { register: async s => { h.registered.push(s.name) } },
    ui: { log: text => { h.uiLogs.push(String(text)) } },
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
  const e = stopEvent()
  const before = clone(e)
  const NEXT = { decision: 'pass' }
  const got = await within(fire(h, 'classic.Stop', e, NEXT), 1000, 'Stop waited for the judge')
  assert.equal(got, NEXT, 'Stop returns the object next() returned')
  same(e, before, 'Stop event')
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

await test('stop: stop_hook_active skips the judge: no process call, no model call, no log write', async () => {
  const h = await load(host())
  const NEXT = { decision: 'pass' }
  assert.equal(await within(fire(h, 'classic.Stop', stopEvent({ stop_hook_active: true }), NEXT), 1000, 'Stop'), NEXT)
  await settle()
  same(h.procs.length, 0, 'process calls')
  same(h.modelReqs.length, 0, 'model calls')
  same(h.writes.length, 0, 'log writes')
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
  same(h.modelReqs, [{ model: 'haiku', prompt: PROMPT, maxTokens: 512 }], 'model call')
  same(JSON.parse(py[0].opts.stdin).session_id, SID, 'phase 1 stdin is the Stop JSON')
  same(JSON.parse(py[1].opts.stdin).transcript_path, TRANSCRIPT, 'phase 2 stdin is the same Stop JSON')
})

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
    assert.match(text, /UNKNOWN/, 'no UNKNOWN shown')
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
  assert.match(text, /ALLOW/, 'no verdict shown')
  assert.ok(!text.includes(SENTINEL), 'the prompt was shown')
})

await test('/dw: shows a FLAG', async () => {
  const h = await load(host({ model: () => ({ isAnswered: true, text: FLAG_REPLY, usage: {} }) }))
  await primed(h)
  assert.match(shown(h, await dwRun(h)), /FLAG/, 'no FLAG shown')
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

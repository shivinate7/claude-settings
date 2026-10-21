// desktop-statusline git-read pins. Run: node mods/desktop-statusline/desktop-statusline.test.mjs  (stdlib only; exit 1 on any FAIL)
// Needs Node 22.13 or later: hooks/register.tsx is loaded with node:module stripTypeScriptTypes. Its ui.render handler
// (the JSX) is cut off first, so a render change is not covered here. The host module 'claude-code' is a stub, and the
// host is a fake with a fake clock: advance(h, ms) fires every() and after() timers at their own times.
// Pinned: an idle session reads git at a turn end and on attach, and otherwise about every 5 minutes. The band's own
// snapshot (idle time, limit countdowns) still refreshes each minute.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as nodeModule from 'node:module'

const NOW = 1_800_000_000_000
const results = []
async function test(name, fn) {
  try {
    await fn()
    results.push(`PASS ${name}`)
  } catch (e) {
    results.push(`FAIL ${name}: ${String(e && e.message ? e.message : e).split('\n')[0]}`)
  }
}
const same = (got, want, why) => assert.deepEqual(got, want, `${why}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`)

// ---- load register.tsx with a stub host module

const SRC = readFileSync(new URL('./hooks/register.tsx', import.meta.url), 'utf8')
const RENDER = "\n  on('ui.render'"
const STUB = `
const store = new Map()
export const atom = (key, init) => ({ id: JSON.stringify(key), init })
export const read = async (_$, a) => (store.has(a.id) ? store.get(a.id) : a.init)
export const update = async (_$, a, fn) => { store.set(a.id, fn(await read(_$, a))) }
`
let js = null
let setupError = null
try {
  if (typeof nodeModule.stripTypeScriptTypes !== 'function') throw new Error('node:module has no stripTypeScriptTypes (Node 22.13 or later is needed)')
  const cut = SRC.indexOf(RENDER)
  if (cut < 0 || SRC.indexOf(RENDER, cut + 1) >= 0) throw new Error('register.tsx: the ui.render handler is not found exactly once')
  if ((SRC.slice(cut).match(/\n  on\(/g) ?? []).length !== 1) throw new Error('register.tsx: another handler follows ui.render and would be cut off')
  js = nodeModule.stripTypeScriptTypes(SRC.slice(0, cut) + '\n}\n', { mode: 'strip' })
  if (!js.includes("from 'claude-code'")) throw new Error("register.tsx: no import from 'claude-code' to stub")
} catch (e) {
  setupError = e
}

let loads = 0
async function load() {
  const n = ++loads
  const stubUrl = 'data:text/javascript,' + encodeURIComponent(STUB + '\n// case ' + n)
  const code = js.replace("from 'claude-code'", 'from ' + JSON.stringify(stubUrl)) + '\n// case ' + n
  const mod = await import('data:text/javascript,' + encodeURIComponent(code))
  return { register: mod.register, stub: await import(stubUrl) }
}

// ---- fake host

async function start() {
  const { register, stub } = await load()
  const h = { now: NOW, hooks: [], beats: [], timers: [], gitCalls: [], stub, status: '# branch.head main\n# branch.ab +0 -0\n', gitFail: null }
  const git = argv => {
    h.gitCalls.push(argv)
    if (h.gitFail === 'throw') throw new Error('git timed out')
    if (h.gitFail === 'exit') return { exitCode: 128, stdout: '', stderr: 'fatal: not a git repository' }
    const out = argv.includes('status') ? h.status : '.git\n.git\n'
    return { exitCode: 0, stdout: out, stderr: '' }
  }
  h.$ = {
    session: {
      surfaces: async () => ['desktop'],
      usage: async () => ({ startedAt: NOW - 600_000, rateLimits: [], cost: null }),
      cwd: async () => '/home/u/repo',
      turns: async () => 3,
    },
    clock: {
      now: async () => h.now,
      every: (ms, fn) => { const b = { fn, ms, next: h.now + ms, live: true }; h.beats.push(b); return { cancel() { b.live = false } } },
      after: (ms, fn) => { const t = { fn, at: h.now + ms, live: true }; h.timers.push(t); return { cancel() { t.live = false } } },
    },
    agent: { list: async () => [] },
    process: { run: async argv => (argv[0] === 'git' ? git(argv) : { exitCode: 1, stdout: '', stderr: '' }) },
    ui: { toast: () => {} },
  }
  register((event, a, b) => {
    h.hooks.push(b === undefined ? { event, matcher: {}, fn: a } : { event, matcher: a, fn: b })
    return { catch() { return this } }
  }, { cache_ttl: '1h' })
  return h
}

const fire = (h, event, e = {}) => {
  const hook = h.hooks.find(x => x.event === event && Object.entries(x.matcher).every(([k, v]) => e[k] === v))
  if (!hook) throw new Error(`no handler for ${event}`)
  return hook.fn(h.$, e, async x => x)
}
const settle = () => new Promise(r => setTimeout(r, 5))
async function advance(h, ms) {
  const end = h.now + ms
  for (;;) {
    const next = Math.min(...h.beats.filter(b => b.live).map(b => b.next), ...h.timers.filter(t => t.live).map(t => t.at))
    if (!(next <= end)) break
    h.now = Math.max(h.now, next)
    for (const b of h.beats) if (b.live && b.next <= h.now) { b.next += b.ms; b.fn() }
    for (const t of h.timers) if (t.live && t.at <= h.now) { t.live = false; t.fn() }
    await settle()
  }
  h.now = end
}
// One read is one `git status`: a read may also cache its `rev-parse`.
const statusReads = h => h.gitCalls.filter(argv => argv.includes('status')).length
const snapshot = h => h.stub.read(null, { id: JSON.stringify({ plugin: 'desktop-statusline', key: 'snap' }), init: null })

const T = (name, fn) => test(name, async () => {
  if (setupError) throw setupError
  await fn()
})

// ---- git reads

await T('idle: no git call of any kind for 4.5 minutes after the session starts', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  const before = h.gitCalls.length
  await advance(h, 270_000)
  same(h.gitCalls.length - before, 0, 'git calls over 4.5 idle minutes')
})

await T('idle: the band snapshot still refreshes each minute, so idle time and limit countdowns stay current', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  await advance(h, 270_000)
  const snap = await snapshot(h)
  assert.ok(snap && h.now - snap.at <= 60_000, `snapshot stamped ${snap && snap.at}, ${snap && h.now - snap.at} ms before now`)
})

// The host raises session.measure after each main-thread turn, so one turn end is turn.complete plus session.measure.
await T('turn end: turn.complete and the session.measure after it run one git read', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  await advance(h, 100_000)
  const before = statusReads(h)
  await fire(h, 'turn.complete', { durationMs: 500, isAborted: false, turnId: 't1' })
  await fire(h, 'session.measure', { rateLimits: [] })
  same(statusReads(h) - before, 1, 'git status reads at one turn end')
})

await T('attach: a desktop client attaching runs one git read', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  await advance(h, 100_000)
  const before = statusReads(h)
  await fire(h, 'session.attach', { surface: 'desktop', clientId: 'desktop:default' })
  same(statusReads(h) - before, 1, 'git status reads at one attach')
})

await T('idle: a session that stays idle reads git again after the back-off, and not before', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  const before = statusReads(h)
  const readsAfter = async ms => { await advance(h, ms); return statusReads(h) - before }
  same(await readsAfter(270_000), 0, 'git status reads by 4.5 min')
  same(await readsAfter(90_000), 1, 'git status reads by 6 min')
  same(await readsAfter(210_000), 1, 'git status reads by 9.5 min')
  same(await readsAfter(150_000), 2, 'git status reads by 12 min')
})

// ---- a failed git read (exit code not 0, or a timeout) is not a reading: the last good reading stands and the next tick reads again

const GOOD = '# branch.head main\n# branch.ab +2 -0\n1 .M x\n1 .M y\n1 .M z\n'
const RECOVERED = '# branch.head feature\n# branch.ab +0 -0\n1 .M x\n'
const FAILURES = ['exit', 'throw']
const turnEnd = h => fire(h, 'turn.complete', { durationMs: 500, isAborted: false, turnId: 't1' })

await T('failed read: the band keeps the last good branch and counts, not an empty reading', async () => {
  for (const mode of FAILURES) {
    const h = await start()
    h.status = GOOD
    await fire(h, 'session.start', {})
    await advance(h, 100_000)
    h.gitFail = mode
    await turnEnd(h)
    const snap = await snapshot(h)
    same([snap.branch, snap.ahead, snap.changed], ['main', 2, 3], `branch, ahead and changed after a failed turn-end read (${mode})`)
  }
})

await T('failed read: the next tick reads again, at the first start and at a turn end, and shows the recovered reading', async () => {
  for (const mode of FAILURES) {
    for (const failsAt of ['session start', 'turn end']) {
      const h = await start()
      h.gitFail = failsAt === 'session start' ? mode : null
      await fire(h, 'session.start', {})
      if (failsAt === 'turn end') {
        await advance(h, 100_000)
        h.gitFail = mode
        await turnEnd(h)
      }
      h.gitFail = null
      h.status = RECOVERED
      const before = statusReads(h)
      await advance(h, failsAt === 'session start' ? 60_000 : 20_000) // one timer tick
      same(statusReads(h) - before, 1, `git status reads at the next tick after a failure (${mode}, at ${failsAt})`)
      const snap = await snapshot(h)
      same([snap.branch, snap.changed], ['feature', 1], `band after the recovered read (${mode}, at ${failsAt})`)
    }
  }
})

await T('failed read: a good read after a failure is cached for the back-off, as after any good read', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  await advance(h, 100_000)
  h.gitFail = 'exit'
  await turnEnd(h)
  h.gitFail = null
  await advance(h, 10_000)
  await fire(h, 'session.attach', { surface: 'desktop', clientId: 'desktop:default' }) // a good read at 110 s
  const before = statusReads(h)
  await advance(h, 270_000)
  same(statusReads(h) - before, 0, 'git status reads in the 4.5 minutes after the good read')
  await advance(h, 90_000)
  same(statusReads(h) - before, 1, 'git status reads by 6 minutes after the good read')
})

const fails = results.filter(r => r.startsWith('FAIL')).length
console.log(results.join('\n'))
console.log(`desktop-statusline pins: ${results.length - fails} pass, ${fails} fail of ${results.length}`)
if (fails) process.exitCode = 1

// session-board pins. Run: node mods/session-board/session-board.test.mjs  (stdlib only; exit 1 on any FAIL)
// Pure helpers are tested against hooks/lib.mjs. Handlers are driven through hooks/register.mjs with a
// fake host (store, clock, git, claude agents, python, ui, prompt). The clock is fixed at NOW.
// register.mjs keeps state at module level, so each host case loads a fresh copy of it.
import assert from 'node:assert/strict'
import { fileURLToPath, pathToFileURL } from 'node:url'
import * as lib from './hooks/lib.mjs'

const REGISTER = fileURLToPath(new URL('./hooks/register.mjs', import.meta.url))
const NOW = 1_800_000_000_000
const ID = 'aaaaaaaa-1111-2222-3333-444444444444'
const OTHER = 'bbbbbbbb-1111-2222-3333-444444444444'
const NOMOD = 'cccccccc-1111-2222-3333-444444444444'
const PANE = 'session-board'
const HANDOFF = '/home/u/.claude/handoffs/' + ID + '.md'
const PROMPT = '/home/u/.claude/hooks/prompt.md'
const sid = n => 'ses' + String(n).padStart(5, '0')
const utf8 = o => new TextEncoder().encode(JSON.stringify(o)).length // the host has no Buffer
const THROWS = Symbol('store read throws')
const kids = t => (t == null ? [] : Array.isArray(t) ? t.flatMap(kids) : t.props ? [t, ...kids(t.props.children)] : [])
const paneTexts = tree => kids(tree).filter(n => n.name === 'Text').map(n => n.props.children)
const raw = (over = {}) => ({ v: 1, repo: 'repo', branch: 'main', state: 'waiting', ask: false, dirty: 0, unpushed: 0, agents: 0, spawns: {}, ctx: 10, at: NOW, ...over })
const fresh = (n, over) => [sid(n), lib.readEntry(raw(over))]
const rowsFor = (agentRows, entries) => lib.mergeRows(agentRows, new Map(entries), NOW)
const ready = over => lib.isUpdateReady(lib.readEntry(raw(over)))
const same = (got, want, why) => assert.deepEqual(got, want, `${why}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`)

const results = []
async function test(name, fn) {
  try {
    await fn()
    results.push(`PASS ${name}`)
  } catch (e) {
    results.push(`FAIL ${name}: ${String(e && e.message ? e.message : e).split('\n')[0]}`)
  }
}

// ---- entries (lib.mjs)

await test('entry: fields and values come from the session', () => {
  const e = lib.buildEntry({ repo: 'repo', branch: 'main', working: true, ask: false, dirty: 2, unpushed: 1, agents: 1, spawns: { Explore: 2 }, ctx: 42, now: NOW })
  same(Object.keys(e).sort(), ['agents', 'ask', 'at', 'branch', 'ctx', 'dirty', 'repo', 'spawns', 'state', 'unpushed', 'v'], 'field set')
  same([e.repo, e.branch, e.state, e.dirty, e.unpushed, e.agents, e.spawns, e.ctx, e.at, e.v], ['repo', 'main', 'working', 2, 1, 1, { Explore: 2 }, 42, NOW, 1], 'values')
})

await test('entry: state is waiting unless a turn runs with no permission ask', () => {
  same(lib.buildEntry({ working: false, now: NOW }).state, 'waiting', 'idle session')
  same(lib.buildEntry({ working: true, ask: true, now: NOW }).state, 'waiting', 'permission ask')
  same(lib.buildEntry({ working: true, now: NOW }).state, 'working', 'running turn')
})

await test('entry: an unknown unpushed or dirty count stays null, never zero', () => {
  const e = lib.buildEntry({ now: NOW })
  same([e.unpushed, e.dirty], [null, null], 'unknown counts')
})

await test('entry: under 1 KB (UTF-8) with 5000-char emoji names and 30 spawn types', () => {
  const spawns = Object.fromEntries(Array.from({ length: 30 }, (_, i) => ['🚀'.repeat(20) + i, 9999]))
  const e = lib.buildEntry({ repo: '🚀'.repeat(5000), branch: 'é'.repeat(5000), working: true, dirty: 9999, unpushed: 9999, agents: 99, spawns, ctx: 100, now: NOW })
  assert.ok(utf8(e) <= 1024, `entry is ${utf8(e)} bytes`)
})

await test('entry: under 1 KB (UTF-8) with 5000-char ASCII names and 30 spawn types', () => {
  const spawns = Object.fromEntries(Array.from({ length: 30 }, (_, i) => ['agent-' + 'x'.repeat(300) + i, 9999]))
  const e = lib.buildEntry({ repo: 'r'.repeat(5000), branch: 'b'.repeat(5000), working: false, spawns, now: NOW })
  assert.ok(utf8(e) <= 1024, `entry is ${utf8(e)} bytes`)
})

await test('entry: readEntry gives back repo, branch, state and unpushed', () => {
  const e = lib.readEntry(JSON.parse(JSON.stringify(lib.buildEntry({ repo: 'repo', branch: 'feat/x', working: false, unpushed: 2, dirty: 0, agents: 0, now: NOW }))))
  same([e.repo, e.branch, e.state, e.unpushed], ['repo', 'feat/x', 'waiting', 2], 'round trip')
})

await test('store read: a non-object, null, wrong version or missing updatedAt gives no entry', () => {
  for (const bad of ['junk', 42, null, [], { v: 2, at: NOW }, { v: 1 }, { v: 1, at: '2026-01-01' }, undefined]) {
    same(lib.readEntry(bad), null, `readEntry(${JSON.stringify(bad)})`)
  }
})

// ---- staleness

await test('stale: an entry exactly 2 minutes old shows; 1 ms more is hidden', () => {
  assert.equal(lib.isFresh({ at: NOW - 120_000 }, NOW), true, 'exactly 2 min old should show')
  assert.equal(lib.isFresh({ at: NOW - 120_001 }, NOW), false, '2 min 0.001 s old should be hidden')
})

await test('stale: a missing updatedAt is never fresh and never a row', () => {
  const e = lib.readEntry(raw({ at: undefined }))
  same(e, null, 'readEntry without at')
  same(rowsFor([], [[ID, e]]), [], 'rows')
})

await test('clock skew: an entry stamped up to 2 min ahead shows; further ahead is hidden', () => {
  assert.equal(lib.isFresh({ at: NOW + 120_000 }, NOW), true, 'exactly 2 min ahead should show')
  assert.equal(lib.isFresh({ at: NOW + 120_001 }, NOW), false, 'just over 2 min ahead should be hidden')
  same(rowsFor([], [fresh(1, { at: NOW + 3_600_000 })]), [], 'an hour ahead gives no row')
})

// ---- band text

await test('band: shape is working, waiting, update-ready n of m', () => {
  const es = []
  for (let i = 1; i <= 5; i++) es.push(fresh(i, { state: 'working' }))
  for (let i = 6; i <= 9; i++) es.push(fresh(i, { state: 'waiting' }))
  es.push(fresh(10, { state: 'waiting', dirty: 3 }), fresh(11, { state: 'waiting', unpushed: 1 }))
  same(lib.bandText(rowsFor([], es)), '5 working, 6 waiting, update-ready 4 of 11', 'band')
})

await test('band: zero sessions says so', () => {
  same(lib.bandText([]), 'No sessions found', 'band')
})

await test('band: one working session reads as a digit (the band has no plural form)', () => {
  same(lib.bandText(rowsFor([], [fresh(1, { state: 'working' })])), '1 working, 0 waiting, update-ready 0 of 1', 'band')
})

await test('band: all waiting, some ready', () => {
  same(lib.bandText(rowsFor([], [fresh(1, {}), fresh(2, {}), fresh(3, { dirty: 1 })])), '0 working, 3 waiting, update-ready 2 of 3', 'band')
})

await test('band: unknown state and no-detail counts follow the update mark', () => {
  const agents = lib.parseAgentsJson(JSON.stringify([{ sessionId: sid(1), cwd: '/x/a', status: 'weird' }]))
  same(lib.bandText(rowsFor(agents, [])), '0 working, 0 waiting, update-ready 0 of 1, 1 unknown, 1 no detail', 'band')
})

// ---- merging claude agents rows with store entries

await test('merge: an agent row with no store entry shows as no detail', () => {
  const [row] = rowsFor(lib.parseAgentsJson(JSON.stringify([{ sessionId: sid(1), cwd: '/x/app', status: 'idle' }])), [])
  same([row.detail, row.ready, row.state], [false, null, 'waiting'], 'row')
  const text = lib.rowText(row, 80)
  assert.ok(text.includes('no detail'), `row reads ${JSON.stringify(text)}`)
})

await test('merge: a store entry with no agent row still shows', () => {
  const rows = rowsFor([], [fresh(1, { repo: 'solo', state: 'working' })])
  same(rows.map(r => [r.id, r.repo, r.state, r.detail]), [[sid(1), 'solo', 'working', true]], 'row')
})

await test('merge: the store entry wins over the agent row with the same session id', () => {
  const agents = lib.parseAgentsJson(JSON.stringify([{ sessionId: sid(1), cwd: '/x/from-agents', status: 'busy' }]))
  const [row] = rowsFor(agents, [fresh(1, { repo: 'from-store', state: 'waiting' })])
  same([row.repo, row.state, row.detail], ['from-store', 'waiting', true], 'merged row')
})

await test('merge: duplicate session ids give one row', () => {
  const agents = lib.parseAgentsJson(JSON.stringify([{ sessionId: sid(1), cwd: '/a', status: 'busy' }, { sessionId: sid(1), cwd: '/a', status: 'idle' }]))
  same(rowsFor(agents, []).length, 1, 'rows, agents only')
  same(rowsFor(agents, [fresh(1, {})]).length, 1, 'rows, with an entry')
})

await test('merge: rows sort working, waiting, unknown', () => {
  const agents = lib.parseAgentsJson(JSON.stringify([{ sessionId: sid(3), status: 'weird' }]))
  const rows = rowsFor(agents, [fresh(1, { state: 'waiting', repo: 'b' }), fresh(2, { state: 'working', repo: 'z' })])
  same(rows.map(r => r.state), ['working', 'waiting', 'unknown'], 'order')
})

await test('rows: a context of 100% is shown whole', () => {
  const [row] = rowsFor([], [fresh(1, { ctx: 100 })])
  const text = lib.rowText(row, 80)
  assert.ok(text.includes('100%'), `ctx cell reads ${JSON.stringify(text)}`)
})

await test('agents json: malformed rows are dropped, valid rows kept', () => {
  const text = JSON.stringify([null, 5, 'x', {}, { sessionId: 3 }, { sessionId: 'short' }, { sessionId: 'has space here' }, { sessionId: sid(2), cwd: '/x/ok', status: 'idle' }])
  same(lib.parseAgentsJson(text).map(r => r.id), [sid(2)], 'ids')
})

await test('agents json: non-array, empty or invalid text gives no rows', () => {
  for (const t of ['', 'not json', '{"sessionId":"ses00001"}', 'null']) same(lib.parseAgentsJson(t), [], `parseAgentsJson(${JSON.stringify(t)})`)
})

await test('agents json: busy is working, idle is waiting, anything else is unknown', () => {
  const text = JSON.stringify([{ sessionId: sid(1), status: 'busy' }, { sessionId: sid(2), status: 'idle' }, { sessionId: sid(3), status: 'running' }, { sessionId: sid(4) }])
  same(lib.parseAgentsJson(text).map(r => r.state), ['working', 'waiting', 'unknown', 'unknown'], 'states')
})

// ---- update-ready

await test('update-ready: waiting, no agents, nothing unpushed, clean tree is ready', () => {
  same(ready({}), true, 'all four terms hold')
  same(lib.isUpdateReady(undefined), false, 'no entry')
})

await test('update-ready: any one failing term means not ready', () => {
  // The README omits the permission-ask term. The code has it, so the test pins the code.
  const cases = { 'a running agent': { agents: 1 }, 'a working state': { state: 'working' }, 'an unpushed commit': { unpushed: 1 }, 'a dirty tree': { dirty: 1 }, 'a pending permission ask': { ask: true } }
  for (const [why, over] of Object.entries(cases)) same(ready(over), false, why)
})

await test('update-ready: unknown unpushed or dirty is never ready', () => {
  same(ready({ unpushed: undefined }), false, 'unknown unpushed')
  same(ready({ dirty: undefined }), false, 'unknown dirty')
})

await test('update-ready: an entry with no usable state is not ready', () => {
  same(ready({ state: undefined }), false, 'missing state')
})

await test('status: no upstream gives unpushed unknown, not zero', () => {
  same(lib.parseStatus('# branch.head main\n').unpushed, null, 'unpushed with no upstream')
  same(lib.parseStatus('# branch.head main\n# branch.ab +2 -0\n').unpushed, 2, 'ahead 2')
})

await test('status: detached HEAD and the dirty count', () => {
  const s = lib.parseStatus('# branch.head (detached)\n1 .M N... 100644 100644 100644 a b f.ts\n? new.txt\n')
  same([s.branch, s.dirty], ['detached', 2], 'status')
})

// ---- sanitising and size caps

await test('sanitise: markup characters become underscores', () => {
  same(lib.clean('<b>&"`x'), '_b____x', 'clean')
})

await test('sanitise: control characters become spaces and ESC never survives', () => {
  const s = lib.clean('a\x1b[2Jb')
  same(s, 'a [2Jb', 'clean')
  assert.ok(!s.includes('\x1b'), 'ESC reached the output')
})

await test('sanitise: a bidi override (U+202E) becomes a space', () => {
  same(lib.clean('evil\u202Egnp.exe'), 'evil gnp.exe', 'clean')
})

await test('sanitise: a newline in a name becomes a space', () => {
  same(lib.clean('feat\nx'), 'feat x', 'clean')
})

await test('sanitise: a 5000-character name is cut to 40 characters with an ellipsis', () => {
  const s = lib.clean('x'.repeat(5000), 40)
  same([Array.from(s).length, s.endsWith('…')], [40, true], 'cut name')
})

await test('sanitise: an emoji name stays whole, and a cut never splits a surrogate pair', () => {
  same(lib.clean('🚀 repo'), '🚀 repo', 'emoji name')
  const s = lib.clean('🚀'.repeat(50), 40)
  const lone = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(s)
  same([Array.from(s).length, lone], [40, false], 'cut emoji name')
})

await test('sanitise: comment openers and a lone quote are plain text', () => {
  same(lib.clean("it's // /* # ok"), "it's // /* # ok", 'text')
})

await test('sanitise: a long run of combining marks goes, a single mark stays', () => {
  same(lib.clean('e' + '\u0301'.repeat(5)), 'e', 'five marks')
  same(lib.clean('e\u0301'), 'e\u0301', 'one mark')
})

await test('bytes: byteLen matches the UTF-8 size of the JSON text, multi-byte included', () => {
  const samples = [{ a: 'é' }, { a: '🚀' }, { a: 'x\ny\t' }, { a: '\u0001' }, { a: '\ud800' }, { a: 'é'.repeat(100), b: ['🚀', 1, null] }]
  for (const o of samples) same(lib.byteLen(o), utf8(o), `bytes of ${JSON.stringify(o)}`)
  same([lib.byteLen('é'), lib.byteLen('🚀')], [4, 6], 'quoted é and 🚀')
})

// ---- detail record and the tracker

await test('detail: keeps the last five tool targets', () => {
  const recent = Array.from({ length: 8 }, (_, i) => ({ t: 'Tool' + i, f: 'f' + i + '.ts' }))
  same(lib.buildDetail({ now: NOW, recent }).recent.map(r => r.t), ['Tool3', 'Tool4', 'Tool5', 'Tool6', 'Tool7'], 'last five')
})

await test('detail: worst case stays under about 3 KB (UTF-8)', () => {
  const d = lib.buildDetail({
    now: NOW,
    files: 99999,
    recent: Array.from({ length: 8 }, () => ({ t: '🚀'.repeat(30), f: '🚀'.repeat(50) })),
    agents: Array.from({ length: 8 }, () => ({ type: '🚀'.repeat(30), status: 'running' })),
    spawns: Object.fromEntries(Array.from({ length: 20 }, (_, i) => ['🚀'.repeat(20) + i, 9999])),
    perm: { ask: 99999, deny: 99999, wait: 99 },
    receipt: { sec: 999999, tools: 99999, edits: 99999, asks: 99999, aborted: true },
  })
  assert.ok(utf8(d) <= 3072, `detail is ${utf8(d)} bytes`)
})

await test('tracker: detail keeps file names only, for the last five edits', () => {
  const t = lib.makeTracker()
  for (let i = 1; i <= 8; i++) t.toolCheck({ tool: 'Edit', input: { file_path: `C:\\work\\secret\\f${i}.ts` }, id: 'tu' + i, verdict: 'allow' })
  const d = t.detail(NOW)
  same(d.recent.map(r => r.f), ['f4.ts', 'f5.ts', 'f6.ts', 'f7.ts', 'f8.ts'], 'recent file names')
  same(d.files, 8, 'files touched')
  const text = JSON.stringify(d)
  assert.ok(!text.includes('secret') && !text.includes('work'), `a directory name reached the detail: ${text.slice(0, 200)}`)
})

await test('tracker: a Bash command is never stored, only the tool name', () => {
  const t = lib.makeTracker()
  t.toolCheck({ tool: 'Bash', input: { command: 'curl -H "X-Key: TOKEN-XYZ" host' }, id: 'b1', verdict: 'allow' })
  const d = t.detail(NOW)
  same(d.recent, [{ t: 'Bash', f: '' }], 'recent')
  assert.ok(!JSON.stringify(d).includes('TOKEN-XYZ'), 'command text reached the detail')
})

await test('tracker: spawns count Agent and Task allow checks by type; a deny is not a spawn', () => {
  const t = lib.makeTracker()
  t.toolCheck({ tool: 'Agent', input: { subagent_type: 'Explore' }, id: 'a1', verdict: 'allow' })
  t.toolCheck({ tool: 'Agent', input: { subagent_type: 'Explore' }, id: 'a2', verdict: 'deny' })
  t.toolCheck({ tool: 'Task', input: {}, id: 'a3', verdict: 'allow' })
  same(t.entry(NOW).spawns, { Explore: 1, 'general-purpose': 1 }, 'spawn counts')
})

await test('tracker: a spawn of a type named like an Object.prototype key is counted', () => {
  const t = lib.makeTracker()
  t.toolCheck({ tool: 'Agent', input: { subagent_type: 'constructor' }, id: 'c1', verdict: 'allow' })
  same(t.entry(NOW).spawns, { constructor: 1 }, 'spawn counts')
})

await test('tracker: a tool check with no id is skipped', () => {
  const t = lib.makeTracker()
  t.toolCheck({ tool: 'Edit', input: { file_path: '/a/b.ts' }, verdict: 'allow' })
  same([t.detail(NOW).recent, t.detail(NOW).files], [[], 0], 'nothing counted')
})

await test('tracker: a pending permission ask shows until the call starts', () => {
  const t = lib.makeTracker()
  t.turnStart()
  t.toolCheck({ tool: 'Edit', input: { file_path: '/a/b.ts' }, id: 'p1', verdict: 'ask' })
  same([t.entry(NOW).ask, t.entry(NOW).state], [true, 'waiting'], 'while asking')
  t.toolCall('p1')
  same([t.entry(NOW).ask, t.entry(NOW).state], [false, 'working'], 'after the call starts')
})

await test('tracker: the receipt counts the last turn and flags an early stop', () => {
  const t = lib.makeTracker()
  t.turnStart()
  t.toolCheck({ tool: 'Edit', input: { file_path: '/a/x.ts' }, id: 'r1', verdict: 'allow' })
  t.toolCheck({ tool: 'Bash', input: { command: 'ls' }, id: 'r2', verdict: 'allow' })
  t.toolCheck({ tool: 'Edit', input: { file_path: '/a/y.ts' }, id: 'r3', verdict: 'allow' })
  t.turnComplete({ durationMs: 4200, isAborted: true })
  same(t.detail(NOW).receipt, { sec: 4, tools: 3, edits: 2, asks: 0, aborted: true }, 'receipt')
})

await test('safe-stop text: a plan with a missing item says nothing was sent', () => {
  const p = lib.safeStopPlan(null, ['python with x'])
  assert.ok(p.endsWith('Missing: python with x. Nothing was sent.'), `plan ends: ${JSON.stringify(p.slice(-80))}`)
  assert.ok(!p.includes('Prompt:'), 'a plan with no prompt still shows one')
})

// ---- host-driven cases: register.mjs with a fake host

let loads = 0
function host(opts) {
  const h = {
    now: NOW, sid: ID, cwd: '/home/u/secret/repo/sub', repoRoot: '/home/u/secret/repo',
    git: '# branch.head main\n# branch.ab +0 -0\n', agents: [], agentsExit: 0, liveAgents: [],
    python: null, context: { window: 1000, percent: 42 }, env: {}, placed: true,
    hooks: [], registered: [], opened: [], submitted: [], pythonCalls: [],
    ...opts,
  }
  h.store = new Map(opts.seed ?? [])
  const clone = v => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)))
  const ctor = name => props => ({ name, props })
  h.$ = {
    store: {
      get: async k => { const v = h.store.get(k); if (v === THROWS) throw new Error('store read failed'); return clone(v) },
      set: async (k, v) => { h.store.set(k, clone(v)) },
      delete: async k => { h.store.delete(k) },
      keys: async () => [...h.store.keys()],
    },
    clock: { now: async () => h.now, every: () => ({ cancel() {} }), after: () => ({ cancel() {} }) },
    session: { id: async () => h.sid, cwd: async () => h.cwd, repo: async () => ({ root: h.repoRoot }), usage: async () => ({ context: h.context }) },
    agent: { list: async () => h.liveAgents },
    process: {
      run: async argv => {
        if (argv[0] === 'git') return { exitCode: 0, stdout: h.git, stderr: '' }
        if (argv[0] === 'claude') return { exitCode: h.agentsExit, stdout: typeof h.agents === 'string' ? h.agents : JSON.stringify(h.agents), stderr: '' }
        h.pythonCalls.push(argv)
        if (!h.python) throw Object.assign(new Error(`spawn ${argv[0]} ENOENT`), { code: 'ENOENT' })
        return h.python(argv)
      },
    },
    command: { register: async s => { h.registered.push(s.name) } },
    ui: {
      open: async o => { h.opened.push(o); return { isPlaced: h.placed } },
      invalidate: () => {},
      resolve: () => ({ Box: ctor('Box'), Text: ctor('Text'), Button: ctor('Button') }),
      log: () => {},
    },
    env: { get: async k => h.env[k] },
    prompt: { submit: async o => { h.submitted.push(o.text); return {} } },
  }
  return h
}

async function start(opts = {}) {
  const h = host(opts)
  const register = (await import(pathToFileURL(REGISTER).href + '?case=' + ++loads)).register
  register((event, a, b) => {
    h.hooks.push(b === undefined ? { event, matcher: {}, fn: a } : { event, matcher: a, fn: b })
    return { catch() { return this } }
  })
  return h
}

// next() returns { decision } for tool.check, as the rest of the host chain does.
async function fire(h, event, e = {}, decision) {
  const hook = h.hooks.find(x => x.event === event && Object.entries(x.matcher).every(([k, v]) => e[k] === v))
  if (!hook) throw new Error(`no handler for ${event}`)
  return hook.fn(h.$, e, async () => (decision === undefined ? undefined : { decision }))
}
const pane = h => fire(h, 'ui.render', { surface: 'terminal', component: 'Pane', requestId: PANE, bodyColumns: 80 })
const boardText = async h => (await fire(h, 'command.run', { command: 'board', args: 'text' })).text
const lines = async h => (await boardText(h)).split('\n')
const pyOk = (handoff = HANDOFF, prompt = PROMPT) => argv => ({ exitCode: 0, stdout: JSON.stringify({ handoff, prompt }) + '\n', stderr: '' })
const safe = (h, args) => fire(h, 'command.run', { command: 'safe-stop', args })

await test('register: session start writes the repo folder and branch, and no path', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  const e = h.store.get('sess:' + ID)
  same([e && e.repo, e && e.branch], ['repo', 'main'], 'repo and branch')
  const all = JSON.stringify([...h.store.entries()])
  assert.ok(!all.includes('secret') && !all.includes('/home'), `a path reached the store: ${all.slice(0, 160)}`)
})

await test('register: prompt text, a Bash command and an Agent prompt never reach the store', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  await fire(h, 'turn.start', { text: 'PROMPT-SECRET-1', turnId: 't1' })
  await fire(h, 'tool.check', { tool: 'Bash', input: { command: 'curl BASH-SECRET-2' }, tool_use_id: 'b1' }, 'allow')
  await fire(h, 'tool.check', { tool: 'Agent', input: { subagent_type: 'Explore', prompt: 'AGENT-SECRET-3' }, tool_use_id: 'a1' }, 'allow')
  await fire(h, 'turn.complete', { durationMs: 1000, isAborted: false, turnId: 't1' })
  const all = JSON.stringify([...h.store.values()])
  for (const s of ['PROMPT-SECRET-1', 'BASH-SECRET-2', 'AGENT-SECRET-3']) assert.ok(!all.includes(s), `${s} reached the store`)
})

await test('register: Agent spawns are counted per type from tool checks; a denied spawn is not', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  await fire(h, 'turn.start', { text: '', turnId: 't1' })
  await fire(h, 'tool.check', { tool: 'Agent', input: { subagent_type: 'Explore' }, tool_use_id: 'a1' }, 'allow')
  await fire(h, 'tool.check', { tool: 'Agent', input: { subagent_type: 'Explore' }, tool_use_id: 'a2' }, 'deny')
  await fire(h, 'turn.complete', { durationMs: 1000, isAborted: false, turnId: 't1' })
  same(h.store.get('sess:' + ID).spawns, { Explore: 1 }, 'spawns in the entry')
})

await test('board: a tool check that asks shows permission until the call starts', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  await fire(h, 'turn.start', { text: '', turnId: 't1' })
  await fire(h, 'tool.check', { tool: 'Edit', input: { file_path: '/r/a.ts' }, tool_use_id: 'e1' }, 'ask')
  const asking = await lines(h)
  assert.ok(asking[2].includes('permission'), `row while asking: ${asking[2]}`)
  await fire(h, 'tool.call', { tool: 'Edit', tool_use_id: 'e1' })
  const after = await lines(h)
  assert.ok(after[2].includes('working') && !after[2].includes('permission'), `row after the call: ${after[2]}`)
})

await test('board: band and rows from the store, the agent list and a session with no mod', async () => {
  const h = await start({
    agents: [{ sessionId: ID, cwd: '/x/repo', status: 'busy' }, { sessionId: OTHER, cwd: '/x/other', status: 'idle' }, { sessionId: NOMOD, cwd: '/x/nomod', status: 'idle' }],
    seed: [['sess:' + OTHER, raw({ repo: 'other', state: 'working' })]],
  })
  await fire(h, 'session.start', {})
  const l = await lines(h)
  same(l[0], '1 working, 2 waiting, update-ready 1 of 3, 1 no detail', 'band')
  same(l.slice(2).map(x => x.trim().split(/\s+/)[0]), ['other', 'nomod', 'repo'], 'row order')
})

await test('board: an entry 2 minutes old shows; one older than that is hidden', async () => {
  const h = await start({ seed: [['sess:' + sid(1), raw({ repo: 'edge-one', at: NOW - 120_000 })], ['sess:' + sid(2), raw({ repo: 'stale-one', at: NOW - 120_001 })]] })
  const text = await boardText(h)
  assert.ok(text.includes('edge-one') && !text.includes('stale-one'), `board: ${JSON.stringify(text)}`)
})

await test('board: 200 entries plus corrupt ones (junk, null, huge, a read that throws) still render', async () => {
  const huge = { v: 1, at: NOW, repo: 'R'.repeat(2_000_000), branch: 'b', state: 'working', spawns: Object.fromEntries(Array.from({ length: 10_000 }, (_, i) => ['k' + i, 1])) }
  const seed = [['sess:corrupt1', 'junk'], ['sess:corrupt2', null], ['sess:hugeone1', huge], ['sess:corruptx', THROWS]]
  for (let i = 1; i <= 200; i++) seed.push(['sess:' + sid(i), raw({ repo: 'r' + i })])
  const h = await start({ seed })
  const text = await boardText(h)
  assert.match(text, /^\d+ working, \d+ waiting, update-ready \d+ of \d+/, `band: ${text.split('\n')[0]}`)
  assert.ok(!text.includes('R'.repeat(18)), 'the huge repo name was not cut')
  assert.ok(paneTexts(await pane(h)).length > 0, 'pane rendered nothing')
})

await test('pane: shows 40 rows and says how many more it does not show', async () => {
  const seed = Array.from({ length: 45 }, (_, i) => ['sess:' + sid(i + 1), raw({ repo: 'r' + (i + 1) })])
  const h = await start({ seed })
  await boardText(h)
  const tree = await pane(h)
  same(kids(tree).filter(n => n.name === 'Button' && String(n.props.key).startsWith('row-')).length, 40, 'row buttons')
  assert.ok(paneTexts(tree).includes('+5 more not shown'), `pane texts: ${paneTexts(tree).join(' | ')}`)
})

await test('pane: 200 fresh entries give the true count of rows not shown', async () => {
  const seed = Array.from({ length: 200 }, (_, i) => ['sess:' + sid(i + 1), raw({ repo: 'r' + (i + 1) })])
  const h = await start({ seed })
  await boardText(h)
  const texts = paneTexts(await pane(h))
  assert.ok(texts.includes('+160 more not shown'), `pane says ${JSON.stringify(texts.filter(t => t.includes('more')))}, want +160`)
})

await test('board: a branch with markup, a control character and a bidi override shows as plain text', async () => {
  const h = await start({ git: '# branch.head <b>x</b>&"`\u202Egnp\x1b[2J\n# branch.ab +0 -0\n' })
  await fire(h, 'session.start', {})
  const text = await boardText(h)
  for (const bad of ['<', '>', '&', '"', '`', '\u202E', '\x1b']) assert.ok(!text.includes(bad), `board holds ${JSON.stringify(bad)}`)
})

await test('board: no upstream means unpushed is unknown, so the session is not update-ready', async () => {
  const h = await start({ git: '# branch.head main\n' })
  await fire(h, 'session.start', {})
  same((await lines(h))[0], '0 working, 1 waiting, update-ready 0 of 1', 'band')
})

await test('board: the one-session view lists file names and counts, not paths', async () => {
  const h = await start({
    seed: [
      ['sess:' + OTHER, raw({ repo: 'other', state: 'working' })],
      ['detail:' + OTHER, { v: 1, at: NOW, recent: [{ t: 'Edit', f: 'a.ts' }], files: 3, agents: [], spawns: {}, perm: { ask: 1, deny: 0, wait: 0 }, receipt: null }],
    ],
  })
  await fire(h, 'command.run', { command: 'board', args: '' })
  const button = kids(await pane(h)).find(n => n.name === 'Button' && n.props.key === 'row-' + OTHER)
  assert.ok(button, 'no row button for the other session')
  await button.props.onPress()
  await new Promise(r => setImmediate(r))
  const texts = paneTexts(await pane(h))
  assert.ok(texts.some(t => t.includes('Files touched 3')), `view: ${texts.join(' | ')}`)
  assert.ok(texts.some(t => t.startsWith('Recent: Edit a.ts')), `no recent line: ${texts.join(' | ')}`)
})

await test('register: session end removes both records of this session', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  await fire(h, 'session.end', { sessionId: ID, reason: 'other' })
  same([h.store.has('sess:' + ID), h.store.has('detail:' + ID)], [false, false], 'records left after session end')
})

await test('register: session start deletes records a day old and keeps younger ones', async () => {
  const h = await start({
    seed: [
      ['sess:' + OTHER, raw({ at: NOW - 86_400_001 })],
      ['detail:' + OTHER, { v: 1, at: NOW - 86_400_001 }],
      ['sess:' + sid(3), raw({ at: NOW - 86_000_000 })],
    ],
  })
  await fire(h, 'session.start', {})
  same([h.store.has('sess:' + OTHER), h.store.has('detail:' + OTHER), h.store.has('sess:' + sid(3))], [false, false, true], 'store keys')
})

await test('board: a failed claude agents call keeps the store rows and says so', async () => {
  const h = await start({ agentsExit: 1, seed: [['sess:' + OTHER, raw({ repo: 'other', state: 'working' })]] })
  const text = await boardText(h)
  assert.ok(text.includes('claude agents failed: shown from the store only'), `no note in: ${text}`)
  assert.ok(text.includes('other'), `store row missing in: ${text}`)
})

await test('command: /board text prints without a pane; /board opens one', async () => {
  const h = await start({ seed: [['sess:' + OTHER, raw({ repo: 'other', state: 'working' })]] })
  const t = await fire(h, 'command.run', { command: 'board', args: 'text' })
  same([h.opened.length, t.text.split('\n')[0]], [0, '1 working, 0 waiting, update-ready 0 of 1'], 'text path')
  const p = await fire(h, 'command.run', { command: 'board', args: '' })
  same([h.opened, p.text], [[{ id: PANE, title: 'Session board' }], 'Session board opened.'], 'pane path')
})

await test('register: session start registers /board and /safe-stop', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  same(h.registered, ['board', 'safe-stop'], 'commands')
})

await test('safe-stop plan: prints the plan, names the handoff file, sends nothing', async () => {
  const h = await start({ python: pyOk(), env: { HOME: '/home/u' } })
  const out = await safe(h, 'plan')
  assert.ok(out.text.includes('Prompt: Safe stop.') && out.text.includes(HANDOFF), `plan: ${out.text}`)
  assert.ok(out.text.endsWith('Plan only: nothing was sent.'), `plan footer: ${out.text.slice(-60)}`)
  same(h.submitted.length, 0, 'prompts sent')
  same(h.pythonCalls[0][h.pythonCalls[0].length - 1], 'plan', 'python mode argument')
})

await test('safe-stop: sends one prompt that names the handoff file', async () => {
  const h = await start({ python: pyOk(), env: { HOME: '/home/u' } })
  const out = await safe(h, '')
  same(h.submitted.length, 1, 'prompts sent')
  assert.ok(h.submitted[0].startsWith('Safe stop.') && h.submitted[0].includes(HANDOFF), `sent: ${h.submitted[0]}`)
  assert.ok(out.text.startsWith('Safe stop sent.') && out.text.includes(HANDOFF), `reply: ${out.text}`)
  same(h.pythonCalls[0][h.pythonCalls[0].length - 1], 'run', 'python mode argument')
})

await test('safe-stop: with no python, prints what is missing and sends nothing', async () => {
  const h = await start({ env: { HOME: '/home/u' } })
  const out = await safe(h, '')
  assert.ok(out.text.includes('Missing: python with /home/u/.claude/hooks/precompact_handoff.py'), `missing line: ${out.text}`)
  assert.ok(out.text.includes('python3:') && out.text.includes('python:'), `interpreters not named: ${out.text}`)
  assert.ok(out.text.endsWith('Nothing was sent.'), `footer: ${out.text.slice(-60)}`)
  same([h.submitted.length, h.pythonCalls.map(a => a[0])], [0, ['python3', 'python']], 'prompts sent, interpreters tried')
})

await test('safe-stop: no usable session id sends nothing and runs no python', async () => {
  const h = await start({ sid: 'bad', python: pyOk(), env: { HOME: '/home/u' } })
  const out = await safe(h, '')
  assert.ok(out.text.includes('Missing: this session id') && out.text.endsWith('Nothing was sent.'), `text: ${out.text}`)
  same([h.submitted.length, h.pythonCalls.length], [0, 0], 'prompts sent, python calls')
})

await test('safe-stop: a handoff path with "&" is named as the real path', async () => {
  const amp = '/home/Tom & Jerry/.claude/handoffs/' + ID + '.md'
  const h = await start({ python: pyOk(amp), env: { HOME: '/home/u' } })
  const out = await safe(h, 'plan')
  assert.ok(out.text.includes(amp), `plan does not name the real handoff path: ${out.text}`)
})

await test('safe-stop: a handoff path over 300 characters is named whole', async () => {
  const long = '/home/u/' + 'deep-folder-name/'.repeat(20) + ID + '.md'
  const h = await start({ python: pyOk(long), env: { HOME: '/home/u' } })
  const out = await safe(h, 'plan')
  assert.ok(out.text.includes(long), `plan cuts the handoff path: ${out.text.slice(0, 120)}`)
})

const fails = results.filter(r => r.startsWith('FAIL')).length
console.log(results.join('\n'))
console.log(`session-board pins: ${results.length - fails} pass, ${fails} fail of ${results.length}`)
if (fails) process.exitCode = 1

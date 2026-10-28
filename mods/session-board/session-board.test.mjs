// session-board pins. Run: node mods/session-board/session-board.test.mjs  (stdlib only; exit 1 on any FAIL)
// Pure helpers are tested against hooks/lib.mjs. Handlers are driven through hooks/register.mjs with a
// fake host (store, clock, git, claude agents, python, ui, prompt). The clock is fixed at NOW, except in a host
// started with `fake: true`: advance(h, ms) moves it and fires every() beats and after() timers in due order.
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

// A stamp more than 30 s ahead of now is not fresh.
await test('clock skew: an entry stamped up to 30 s ahead shows; more than 30 s ahead is not fresh', () => {
  assert.equal(lib.isFresh({ at: NOW + 30_000 }, NOW), true, 'exactly 30 s ahead should show')
  assert.equal(lib.isFresh({ at: NOW + 30_001 }, NOW), false, 'just over 30 s ahead should not be fresh')
  same(rowsFor([], [fresh(1, { at: NOW + 3_600_000 })]), [], 'an hour ahead gives no row')
})

// ---- band text

await test('band: counts follow the shape: working, waiting, update-ready n of m; all waiting; unknown and no-detail', () => {
  // Rows, one band text each: a mixed shape; all waiting with some ready; an unknown state with no detail.
  const es = []
  for (let i = 1; i <= 5; i++) es.push(fresh(i, { state: 'working' }))
  for (let i = 6; i <= 9; i++) es.push(fresh(i, { state: 'waiting' }))
  es.push(fresh(10, { state: 'waiting', dirty: 3 }), fresh(11, { state: 'waiting', unpushed: 1 }))
  const unknown = lib.parseAgentsJson(JSON.stringify([{ sessionId: sid(1), cwd: '/x/a', status: 'weird' }]))
  const rows = [
    [rowsFor([], es), '5 working, 6 waiting, update-ready 4 of 11'],
    [rowsFor([], [fresh(1, {}), fresh(2, {}), fresh(3, { dirty: 1 })]), '0 working, 3 waiting, update-ready 2 of 3'],
    [rowsFor(unknown, []), '0 working, 0 waiting, update-ready 0 of 1, 1 unknown, 1 no detail'],
  ]
  for (const [input, want] of rows) same(lib.bandText(input), want, 'band')
})

await test('band: zero sessions says so', () => {
  same(lib.bandText([]), 'No sessions found', 'band')
})

await test('band: one working session reads as a digit (the band has no plural form)', () => {
  same(lib.bandText(rowsFor([], [fresh(1, { state: 'working' })])), '1 working, 0 waiting, update-ready 0 of 1', 'band')
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

await test('agents json: a row keeps its name, so a SendMessage to a name can find its busy state', () => {
  const [row] = lib.parseAgentsJson(JSON.stringify([{ sessionId: sid(1), cwd: '/x/app', status: 'busy', name: 'worker-a' }]))
  same(row.name, 'worker-a', 'name from claude agents --json')
})

// ---- receiverState: the state of the one row named like a SendMessage `to`

const namedRows = json => lib.parseAgentsJson(json)

await test('receiver: busy, idle and waiting by name', () => {
  const rows = namedRows(JSON.stringify([
    { sessionId: sid(1), cwd: '/x/a', name: 'a', status: 'busy' },
    { sessionId: sid(2), cwd: '/x/b', name: 'b', status: 'idle' },
    { sessionId: sid(3), cwd: '/x/c', name: 'c', status: 'waiting' },
  ]))
  same([lib.receiverState(rows, 'a'), lib.receiverState(rows, 'b'), lib.receiverState(rows, 'c')], ['busy', 'idle', 'waiting'], 'states')
})

await test('receiver: no row with the name is unseen', () => {
  const rows = namedRows(JSON.stringify([{ sessionId: sid(1), cwd: '/x/a', name: 'a', status: 'busy' }]))
  same(lib.receiverState(rows, 'zzz'), 'unseen', 'no match')
  same(lib.receiverState(rows, ''), 'unseen', 'empty name')
  same(lib.receiverState(null, 'a'), 'unseen', 'no rows')
})

await test('receiver: two rows with the same name are unseen, busy or not', () => {
  const rows = namedRows(JSON.stringify([
    { sessionId: sid(1), cwd: '/x/a', name: 'a', status: 'busy' },
    { sessionId: sid(2), cwd: '/x/b', name: 'a', status: 'idle' },
  ]))
  same(lib.receiverState(rows, 'a'), 'unseen', 'duplicate name')
})

await test('receiver: an unknown status is unseen, not busy', () => {
  const rows = namedRows(JSON.stringify([{ sessionId: sid(1), cwd: '/x/a', name: 'u', status: 'running' }]))
  same(lib.receiverState(rows, 'u'), 'unseen', 'unknown status')
})

// Name shapes, one table, one assertion. Each case: the rows (name, status), the to values asked, and the states.
// Shapes: angle brackets; a 45-char name; two spaces; a [ref] suffix on a bare name (ListAgents prints `name [ref]`
// for a clash); a real name that ends in brackets (the ref strip must not drop it); two 49-char names sharing their
// first 39 chars, each to reads its own row (agentRows cuts a name to 40 chars, so a full to matches the whole name);
// a 49-char to with no row, sharing 39 chars with a busy row, is unseen.
const SHARED39 = 'worker-' + 'x'.repeat(32) // 39 chars, the part a 40-char cut keeps
const shapeCases = [
  ['angle brackets', [['lane <a>', 'busy']], ['lane <a>'], ['busy']],
  ['45 characters', [['worker-' + 'x'.repeat(38), 'busy']], ['worker-' + 'x'.repeat(38)], ['busy']],
  ['two spaces', [['a  b', 'busy']], ['a  b'], ['busy']],
  ['[ref] suffix reads the bare name', [['worker-a', 'busy']], ['worker-a [a1b2]'], ['busy']],
  ['name ending in brackets', [['lane-2 [a]', 'busy']], ['lane-2 [a]'], ['busy']],
  ['two 49-char names sharing 39 chars', [[SHARED39 + 'alpha-0001', 'busy'], [SHARED39 + 'beta-00002', 'idle']],
    [SHARED39 + 'alpha-0001', SHARED39 + 'beta-00002'], ['busy', 'idle']],
  ['49-char to with no row, sharing 39 chars with a busy row', [[SHARED39 + 'alpha-0001', 'busy']],
    [SHARED39 + 'gamma-0003'], ['unseen']],
]

await test('receiver: a name of any shape is found by its full to, and a to with no row is unseen', () => {
  for (const [shape, specs, tos, want] of shapeCases) {
    const rows = namedRows(JSON.stringify(specs.map(([name, status], i) => ({ sessionId: sid(i + 1), cwd: `/x/${i}`, name, status }))))
    same(tos.map(to => lib.receiverState(rows, to)), want, shape)
  }
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
    git: '# branch.head main\n# branch.ab +0 -0\n', gitFail: null, agents: [], agentsExit: 0, liveAgents: [],
    agentListThrow: false, usageThrow: false, hang: false, submitFails: false,
    python: null, context: { window: 1000, percent: 42 }, env: {}, placed: true,
    hooks: [], beats: [], registered: [], opened: [], logs: [], submitted: [], pythonCalls: [], pythonOpts: [], agentCalls: [], writes: [], gitCalls: [], gitHang: false,
    gitManual: false, gitPending: [], hangStore: false, hangId: false, holdStore: false, held: [], gitDelayMs: 0, timers: [], fake: false,
    ...opts,
  }
  h.store = new Map(opts.seed ?? [])
  const clone = v => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)))
  const ctor = name => props => ({ name, props })
  const never = () => new Promise(() => {})
  h.$ = {
    store: {
      get: async k => { const v = h.store.get(k); if (v === THROWS) throw new Error('store read failed'); return clone(v) },
      set: async (k, v) => {
        h.writes.push(k)
        if (h.hangStore) return never()
        if (h.holdStore) await new Promise(go => h.held.push({ go })) // held until the test releases it, then lands
        h.store.set(k, clone(v))
      },
      delete: async k => { h.store.delete(k) },
      keys: async () => [...h.store.keys()],
    },
    clock: {
      now: async () => h.now,
      every: (ms, fn) => { const b = { fn, ms, next: h.now + ms, live: true }; h.beats.push(b); return { cancel() { b.live = false } } },
      after: (ms, fn) => {
        if (!h.fake) { const t = setTimeout(fn, ms); return { cancel() { clearTimeout(t) } } }
        const t = { fn, at: h.now + ms, live: true }
        h.timers.push(t)
        return { cancel() { t.live = false } }
      },
    },
    session: {
      id: async () => { if (h.hangId) return never(); return h.sid }, cwd: async () => h.cwd, repo: async () => ({ root: h.repoRoot }),
      usage: async () => { if (h.hang) return never(); if (h.usageThrow) throw new Error('usage read failed'); return { context: h.context } },
    },
    agent: { list: async () => { if (h.hang) return never(); if (h.agentListThrow) throw new Error('agent list failed'); return h.liveAgents } },
    process: {
      run: async (argv, opts) => {
        if (h.hang) return never()
        if (argv[0] === 'git') {
          h.gitCalls.push(argv)
          if (h.gitHang) return never() // a stuck reader: the read starts and never answers
          if (h.gitManual) return new Promise(resolve => h.gitPending.push({ resolve })) // held until the test lands it
          if (h.gitFail === 'throw') throw new Error('git timed out')
          if (h.gitFail === 'exit') return { exitCode: 128, stdout: '', stderr: 'fatal: not a git repository' }
          h.now += h.gitDelayMs // a slow read moves the clock while it runs
          return { exitCode: 0, stdout: h.git, stderr: '' }
        }
        if (argv[0] === 'claude') { h.agentCalls.push(argv); return { exitCode: h.agentsExit, stdout: typeof h.agents === 'string' ? h.agents : JSON.stringify(h.agents), stderr: '' } }
        h.pythonCalls.push(argv)
        h.pythonOpts.push(opts ?? {})
        if (!h.python) throw Object.assign(new Error(`spawn ${argv[0]} ENOENT`), { code: 'ENOENT' })
        return h.python(argv)
      },
    },
    command: { register: async s => { h.registered.push(s.name) } },
    ui: {
      open: async o => { h.opened.push(o); return { isPlaced: h.placed } },
      invalidate: () => {},
      resolve: () => ({ Box: ctor('Box'), Text: ctor('Text'), Button: ctor('Button') }),
      log: (text, o) => { h.logs.push({ text: String(text), opts: o }) },
    },
    env: { get: async k => h.env[k] },
    prompt: { submit: async o => { if (h.submitFails) throw new Error('no session to take the prompt'); h.submitted.push(o.text); return {} } },
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
const NEW_ID = 'dddddddd-1111-2222-3333-444444444444'
const settle = () => new Promise(r => setTimeout(r, 5))
const tickBeat = async h => { for (const b of h.beats.filter(x => x.live)) b.fn(); await settle() } // one heartbeat, then let its async work finish
// Fake clock, for a host started with `fake: true`: each due beat or timer fires at its own time, in order, and its async work settles first.
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
// A pane close, as the host raises it (ui.close, origin person). No hook for it means the close is ignored.
const closePane = async h => {
  const hook = h.hooks.find(x => x.event === 'ui.close')
  if (hook) await hook.fn(h.$, { id: PANE, origin: { kind: 'person' } }, async e => e)
}
// Resolves 'done' if p settles within ms, else 'late'.
async function within(ms, p) {
  let timer
  const late = new Promise(r => { timer = setTimeout(() => r('late'), ms) })
  const won = await Promise.race([p.then(() => 'done', e => 'error: ' + e.message), late])
  clearTimeout(timer)
  return won
}
// The detail record after one tool check, for the target rules.
const runTarget = (tool, input) => {
  const t = lib.makeTracker()
  t.toolCheck({ tool, input, id: 'x1', verdict: 'allow' })
  const d = t.detail(NOW)
  return { rec: d.recent[0], text: JSON.stringify(d) }
}

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

// ---- permission order, git readiness, hook speed, targets, safe-stop, agents, polling, writes

await test('permission: an approved ask clears when the tool call resolves, not before', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  await fire(h, 'turn.start', { text: '', turnId: 't1' })
  const input = { file_path: '/r/a.ts' }
  const callHook = h.hooks.find(x => x.event === 'tool.call')
  let during = ''
  // Real host order: the tool.call hooks wrap the permission check, which runs inside next().
  await callHook.fn(h.$, { tool: 'Edit', input, tool_use_id: 'e1' }, async () => {
    await fire(h, 'tool.check', { tool: 'Edit', input, tool_use_id: 'e1' }, 'ask')
    during = (await lines(h))[2]
  })
  assert.ok(during.includes('permission'), `while asking, row reads: ${during}`)
  const after = (await lines(h))[2]
  assert.ok(!after.includes('permission') && after.includes('working'), `after the approved call, row reads: ${after}`)
})

await test('git: a failed readiness read makes the reading unknown, so no update-ready mark', async () => {
  for (const mode of ['throw', 'exit']) {
    const h = await start()
    await fire(h, 'session.start', {})
    h.gitFail = mode
    await fire(h, 'turn.complete', { durationMs: 500, isAborted: false, turnId: 't1' })
    same((await lines(h))[0], '0 working, 1 waiting, update-ready 0 of 1', `band after git ${mode}`)
  }
})

// The boundary is pinned on readiness(); the host case uses a stuck reader.
// An idle session reads git again only after about 5 minutes, so a reading must count for the back-off plus one beat.
await test('git: a reading at the max age still counts; 1 ms older is unknown; the max covers a 5 minute back-off and one beat (pure)', () => {
  const e = lib.readEntry(raw({ rt: NOW }))
  const max = lib.READ_MAX_AGE_MS
  same([lib.readiness(e, NOW + max - 1_000), lib.readiness(e, NOW + max)], [true, true], 'reading 1 s under the max and at the max')
  same(lib.readiness(e, NOW + max + 1), 'unknown', 'reading 1 ms over the max')
  assert.ok(max >= 330_000, `max reading age is ${max} ms: an idle session that reads git every 5 minutes would read unknown, never update-ready`)
})

await test('git: a stuck reader leaves the reading to age out; 1 s past the max age it is unknown, so no update-ready', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  h.gitHang = true
  h.now = NOW + lib.READ_MAX_AGE_MS + 1_000
  await tickBeat(h) // a beat that finds the back-off over starts the stuck read, and waits on it
  await tickBeat(h) // the next beat skips the read in flight and writes the entry
  same((await lines(h))[0], '0 working, 1 waiting, update-ready 0 of 1', 'reading past the max age, reader stuck')
})

await test('hooks: session start returns within 200 ms when git, agents and usage never answer', async () => {
  const h = await start({ hang: true })
  same(await within(200, fire(h, 'session.start', {})), 'done', 'session.start return')
})

await test('hooks: turn complete returns within 200 ms when git, agents and usage never answer', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  h.hang = true
  same(await within(200, fire(h, 'turn.complete', { durationMs: 500, isAborted: false, turnId: 't1' })), 'done', 'turn.complete return')
})

await test('debug: failed git, agent and usage reads each write a debug note', async () => {
  const h = await start({ gitFail: 'throw', agentListThrow: true, usageThrow: true })
  await fire(h, 'session.start', {})
  await settle()
  const notes = h.logs.filter(l => l.opts && l.opts.to === 'debug' && l.text.startsWith('session-board'))
  assert.ok(notes.length >= 3, `debug notes: ${notes.length}, want at least 3`)
  for (const [src, re] of [['git', /git/i], ['agents', /agent/i], ['usage', /usage|context/i]]) {
    assert.ok(notes.some(n => re.test(n.text)), `no debug note names ${src}`)
  }
})

await test('targets: file tools store the file name only', () => {
  const cases = [['Read', { file_path: '/home/u/work/app.ts' }], ['Edit', { file_path: '/home/u/work/app.ts' }], ['Write', { file_path: '/home/u/work/app.ts' }], ['MultiEdit', { file_path: '/home/u/work/app.ts' }], ['NotebookEdit', { notebook_path: '/home/u/work/app.ts' }]]
  for (const [tool, input] of cases) {
    const { rec, text } = runTarget(tool, input)
    same(rec.f, 'app.ts', `${tool} target`)
    assert.ok(!text.includes('/home/u'), `${tool} stored a folder: ${text.slice(0, 120)}`)
  }
})

await test('targets: an MCP tool stores no target, even when its input has a path', () => {
  const { rec, text } = runTarget('mcp__compass__hr_read', { path: 'Compass/HR/Terminations-2026' })
  same(rec.f, '', 'target name')
  assert.ok(!text.includes('Terminations'), `MCP path reached the detail: ${text.slice(0, 160)}`)
})

await test('targets: a folder path stores no name (Grep)', () => {
  const { rec, text } = runTarget('Grep', { path: '/Users/jdoe', pattern: 'TODO' })
  same(rec.f, '', 'target name')
  assert.ok(!text.includes('jdoe'), `folder path reached the detail: ${text.slice(0, 160)}`)
})

await test('targets: a tool outside the file-tool allow-list stores no target', () => {
  const { rec, text } = runTarget('Lsp', { file_path: '/repo/private/plan.md' })
  same(rec.f, '', 'target name')
  assert.ok(!text.includes('plan.md'), `name reached the detail: ${text.slice(0, 160)}`)
})

// Names follow plain-diff's isSecretPath, with the exceptions below.
await test('targets: names that look secret are stored as (secret file)', () => {
  const names = ['.env', '.env.production', 'server.pem', 'api.key', 'id_rsa', 'id_ed25519', 'credentials.json', '.npmrc', '.netrc', 'secrets.yaml', 'cert.p12', 'cert.pfx', '.git-credentials', 'prod.tfvars']
  for (const n of names) same(runTarget('Read', { file_path: '/repo/' + n }).rec.f, '(secret file)', `name ${n}`)
})

await test('targets: plain-diff exceptions keep their names (.env.example, .env.sample, .env.template, credentials.ts)', () => {
  for (const n of ['.env.example', '.env.sample', '.env.template', 'credentials.ts']) same(runTarget('Read', { file_path: '/repo/' + n }).rec.f, n, `name ${n}`)
})

await test('safe-stop: a run from a plugin or another non-user origin does nothing', async () => {
  for (const kind of ['plugin', 'peer', 'coordinator', 'scheduled-trigger', 'auto-continuation']) {
    const h = await start({ python: pyOk(), env: { HOME: '/home/u' } })
    await fire(h, 'command.run', { command: 'safe-stop', args: '', origin: { kind, name: 'other-plugin' } })
    same([h.submitted.length, h.pythonCalls.length], [0, 0], `origin ${kind}: prompts sent, python calls`)
  }
})

await test('safe-stop: the person\'s own run (composer origin) still sends', async () => {
  const h = await start({ python: pyOk(), env: { HOME: '/home/u' } })
  await fire(h, 'command.run', { command: 'safe-stop', args: '', origin: { kind: 'composer' } })
  same(h.submitted.length, 1, 'composer origin: prompts sent')
})

await test('safe-stop: a rejected prompt submit says could not send, not sent', async () => {
  const h = await start({ python: pyOk(), env: { HOME: '/home/u' }, submitFails: true })
  const out = await safe(h, '')
  assert.ok(out.text.includes('could not send') && !out.text.includes('Safe stop sent'), `reply: ${out.text}`)
})

await test('safe-stop: the reply says the prompt is queued until the session is idle', async () => {
  const h = await start({ python: pyOk(), env: { HOME: '/home/u' } })
  const out = await safe(h, '')
  assert.ok(/queued|idle/i.test(out.text), `reply: ${out.text}`)
})

// Real row shape: pid, sessionId, cwd, status; a waiting row also has waitingFor.
await test('agents json: status waiting is waiting with a permission ask, not unknown', () => {
  const rows = []
  for (let i = 1; i <= 4; i++) rows.push({ pid: i, sessionId: sid(i), cwd: '/x/a', status: 'busy' })
  for (let i = 5; i <= 10; i++) rows.push({ pid: i, sessionId: sid(i), cwd: '/x/a', status: 'idle' })
  rows.push({ pid: 11, sessionId: sid(11), cwd: '/x/a', status: 'waiting', waitingFor: 'Bash permission' })
  const parsed = lib.parseAgentsJson(JSON.stringify(rows))
  const count = s => parsed.filter(r => r.state === s).length
  same([count('working'), count('waiting'), count('unknown')], [4, 7, 0], 'states of the 11 rows')
  same(parsed.filter(r => r.ask).map(r => r.id), [sid(11)], 'the one ask row')
  const [asked] = rowsFor(parsed, []).filter(r => r.ask)
  same([asked && asked.state, asked && lib.rowText(asked, 80).includes('permission')], ['waiting', true], 'merged row')
})

await test('polling: heartbeats stop calling claude agents once the pane closes', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  await fire(h, 'command.run', { command: 'board', args: '' })
  await closePane(h)
  h.agentCalls.length = 0
  for (let i = 0; i < 5; i++) { h.now += 30_000; await tickBeat(h) }
  same(h.agentCalls.length, 0, 'claude agents calls after the pane closed')
})

// Backstop when no close arrives: N = 10 refreshes with no /board call.
await test('polling: with no close and no /board call, board refreshes stop after 10 beats', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  await fire(h, 'command.run', { command: 'board', args: '' })
  h.agentCalls.length = 0
  for (let i = 0; i < 30; i++) { h.now += 30_000; await tickBeat(h) }
  assert.ok(h.agentCalls.length >= 1 && h.agentCalls.length <= 10, `claude agents calls over 30 beats: ${h.agentCalls.length}, want 1 to 10`)
})

await test('clear: a flush before the new session id binds does not recreate the old entry', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  await fire(h, 'session.end', { sessionId: ID, reason: 'clear' })
  h.now += 30_000
  await tickBeat(h) // the host still answers the old id
  same(h.store.has('sess:' + ID), false, 'old entry written again before the new id bound')
  h.sid = NEW_ID
  h.now += 30_000
  await tickBeat(h)
  same(h.store.has('sess:' + NEW_ID), true, 'new entry once the new id binds')
})

await test('heartbeat: with only the stamp changed, detail is not rewritten; sess at most once a beat', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  h.writes.length = 0
  for (let i = 0; i < 4; i++) { h.now += 30_000; await tickBeat(h) }
  same(h.writes.filter(k => !k.startsWith('sess:')), [], 'writes outside sess: over 4 beats')
  assert.ok(h.writes.length <= 4, `store writes over 4 beats: ${h.writes.length}, want at most 4`)
})

await test('read cap: all 200 entries appear in the board', async () => {
  const seed = Array.from({ length: 200 }, (_, i) => ['sess:' + sid(i + 1), raw({ repo: 'r' + (i + 1) })])
  const h = await start({ seed })
  same((await lines(h)).length, 202, 'board lines: band, header, 200 rows')
})

await test('read cap: above 200, the pane gives the true count not shown and never drops the newest live rows', async () => {
  const seed = []
  for (let i = 1; i <= 245; i++) seed.push(['sess:' + sid(i), raw({ repo: 'old-' + i, at: NOW - 60_000 - i })])
  for (let i = 1; i <= 5; i++) seed.push(['sess:' + sid(900 + i), raw({ repo: 'live-' + i, at: NOW })])
  const h = await start({ seed })
  const text = await boardText(h)
  for (let i = 1; i <= 5; i++) assert.ok(text.includes('live-' + i), `live-${i} is missing from the board`)
  const texts = paneTexts(await pane(h))
  assert.ok(texts.includes('+210 more not shown'), `pane says ${JSON.stringify(texts.filter(t => t.includes('more')))}, want +210`)
})

// ---- heartbeat git reads while idle

await test('heartbeat: an idle session with a working git reader stays update-ready on every beat of 10 minutes, with a few git reads', async () => {
  const h = await start({ fake: true })
  await fire(h, 'session.start', {})
  const before = h.gitCalls.length
  for (let i = 1; i <= 20; i++) {
    await advance(h, 30_000)
    same((await lines(h))[0], '0 working, 1 waiting, update-ready 1 of 1', `band after ${i * 30} s idle`)
  }
  const reads = h.gitCalls.length - before
  assert.ok(reads >= 1 && reads <= 3, `git reads over 20 idle beats: ${reads}, want 1 to 3`)
})

// An idle session reads git at a turn end and on attach. Otherwise it waits about 5 minutes between reads, and it
// still writes its entry on every beat. The windows are literal: no read before 4.5 minutes, one by 6 minutes.
await test('idle back-off: an idle session runs no git read for 4.5 minutes, and its entry stays fresh', async () => {
  const h = await start({ fake: true })
  await fire(h, 'session.start', {})
  const before = h.gitCalls.length
  await advance(h, 270_000)
  same(h.gitCalls.length - before, 0, 'git reads over 4.5 idle minutes')
  const e = h.store.get('sess:' + ID)
  assert.ok(e && lib.isFresh(e, h.now), `entry stamped ${e && e.at}, not fresh at ${h.now}`)
})

await test('idle back-off: a turn end runs one git read', async () => {
  const h = await start({ fake: true })
  await fire(h, 'session.start', {})
  await advance(h, 100_000)
  const before = h.gitCalls.length
  await fire(h, 'turn.start', { text: '', turnId: 't1' })
  await fire(h, 'turn.complete', { durationMs: 500, isAborted: false, turnId: 't1' })
  same(h.gitCalls.length - before, 1, 'git reads at one turn end')
})

await test('idle back-off: a client attaching runs one git read', async () => {
  const h = await start({ fake: true })
  await fire(h, 'session.start', {})
  await advance(h, 100_000)
  const before = h.gitCalls.length
  await fire(h, 'session.attach', { surface: 'desktop', clientId: 'desktop:default' })
  await settle()
  same(h.gitCalls.length - before, 1, 'git reads at one attach')
})

await test('idle back-off: a session that stays idle reads git again after the back-off, and not before', async () => {
  const h = await start({ fake: true })
  await fire(h, 'session.start', {})
  const before = h.gitCalls.length
  const readsAfter = async ms => { await advance(h, ms); return h.gitCalls.length - before }
  same(await readsAfter(270_000), 0, 'git reads by 4.5 min')
  same(await readsAfter(90_000), 1, 'git reads by 6 min')
  same(await readsAfter(210_000), 1, 'git reads by 9.5 min')
  same(await readsAfter(150_000), 2, 'git reads by 12 min')
})

await test('heartbeat: a working session starts no git read on the beat', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  await fire(h, 'turn.start', { text: '', turnId: 't1' })
  const before = h.gitCalls.length
  for (let i = 0; i < 3; i++) { h.now += 30_000; await tickBeat(h) }
  same(h.gitCalls.length - before, 0, 'git reads started over 3 beats while working')
})

await test('heartbeat: one git read at a time; with a stuck reader, 3 beats start one read', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  h.gitHang = true
  h.now += 300_000 // past the idle back-off: the next beat reads
  const before = h.gitCalls.length
  for (let i = 0; i < 3; i++) { h.now += 30_000; await tickBeat(h) }
  same(h.gitCalls.length - before, 1, 'git reads started over 3 beats with one in flight')
})

await test('heartbeat: a failing git read makes the reading unknown, so no update-ready', async () => {
  for (const mode of ['throw', 'exit']) {
    const h = await start()
    await fire(h, 'session.start', {})
    h.gitFail = mode
    h.now += 330_000 // past the idle back-off: this beat reads
    await tickBeat(h)
    same((await lines(h))[0], '0 working, 1 waiting, update-ready 0 of 1', `band after a ${mode} on the beat`)
  }
})

// ---- safe-stop, hook speed, resume, late git reads, sweep

const CLEAN_REPLY = { exitCode: 0, stdout: '# branch.head main\n# branch.ab +0 -0\n', stderr: '' }
const DIRTY_REPLY = { exitCode: 0, stdout: '# branch.head main\n# branch.ab +0 -0\n1 .M N... 100644 100644 100644 a b a.ts\n', stderr: '' }

await test('safe-stop: python runs isolated (-I) with its cwd at the config folder, plan and run', async () => {
  for (const args of ['plan', '']) {
    const h = await start({ python: pyOk(), env: { HOME: '/home/u' } })
    await safe(h, args)
    const argv = h.pythonCalls[0] ?? []
    assert.ok(argv.includes('-I'), `argv has no -I (args ${JSON.stringify(args)}): ${argv.join(' ')}`)
    same((h.pythonOpts[0] ?? {}).cwd, '/home/u/.claude', `init cwd (args ${JSON.stringify(args)})`)
  }
})

await test('turn start and a permission ask return within 200 ms when a store write or the session id never answers', async () => {
  for (const flag of ['hangStore', 'hangId']) {
    const h = await start()
    await fire(h, 'session.start', {})
    h[flag] = true
    same(await within(200, fire(h, 'turn.start', { text: '', turnId: 't1' })), 'done', `turn.start with ${flag}`)
  }
  for (const flag of ['hangStore', 'hangId']) {
    const h = await start()
    await fire(h, 'session.start', {})
    h[flag] = true
    same(await within(200, fire(h, 'tool.check', { tool: 'Edit', input: { file_path: '/r/a.ts' }, tool_use_id: 'e1' }, 'ask')), 'done', `ask with ${flag}`)
  }
})

await test('resume: after a resume end the beat keeps running and writes under the new id; entry fresh at 130 s', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  await fire(h, 'session.end', { sessionId: ID, reason: 'resume' })
  h.sid = NEW_ID
  for (let i = 0; i < 4; i++) { h.now += 30_000; await tickBeat(h) }
  h.now += 10_000 // 130 s after the resume; the last beat was at 120 s
  const e = h.store.get('sess:' + NEW_ID)
  assert.ok(e, 'no entry under the new id')
  assert.ok(lib.isFresh(e, h.now), `entry stamped ${e && e.at}, not fresh at ${h.now}`)
})

await test('git: a read started before the latest turn start is dropped when it lands late', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  h.gitManual = true
  h.now += 330_000
  await tickBeat(h) // idle beat past the back-off: a clean read starts and is held
  const cleanRead = h.gitPending[0]
  await fire(h, 'turn.start', { text: '', turnId: 't1' })
  await fire(h, 'tool.check', { tool: 'Edit', input: { file_path: '/r/a.ts' }, tool_use_id: 'e1' }, 'allow')
  await fire(h, 'turn.complete', { durationMs: 500, isAborted: false, turnId: 't1' }) // turn-end read starts and is held
  h.gitPending[1].resolve(DIRTY_REPLY) // the dirty read lands first
  await settle()
  cleanRead.resolve(CLEAN_REPLY) // the old clean read lands last
  await settle()
  same(h.store.get('sess:' + ID).dirty, 1, 'final entry dirty count')
  same((await lines(h))[0], '0 working, 1 waiting, update-ready 0 of 1', 'band after the late landing')
})

await test('session end: a read in flight when the session ends writes neither record', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  h.gitManual = true
  h.now += 330_000
  await tickBeat(h) // beat read held
  await fire(h, 'turn.complete', { durationMs: 500, isAborted: false, turnId: 't1' }) // turn-end read held
  await fire(h, 'session.end', { sessionId: ID, reason: 'other' })
  h.gitPending[0].resolve(CLEAN_REPLY)
  h.gitPending[1].resolve(DIRTY_REPLY)
  await settle()
  same([h.store.has('sess:' + ID), h.store.has('detail:' + ID)], [false, false], 'records after the late landings')
})

await test('sweep: an entry and detail past a day stay while claude agents lists that session', async () => {
  const h = await start({
    agents: [{ sessionId: OTHER, cwd: '/x/other', status: 'busy' }],
    seed: [
      ['sess:' + OTHER, raw({ repo: 'other', at: NOW - 86_400_001 })],
      ['detail:' + OTHER, { v: 1, at: NOW - 86_400_001, recent: [], files: 0, agents: [], spawns: {}, perm: { ask: 0, deny: 0, wait: 0 }, receipt: null }],
    ],
  })
  await boardText(h)
  same([h.store.has('sess:' + OTHER), h.store.has('detail:' + OTHER)], [true, true], 'live session records after the sweep')
})

await test('sweep: when the sweep removes this session\'s detail, the next beat writes it again', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  h.now += 2 * 86_400_000 // the own entry is now a day past its last beat
  await boardText(h) // the sweep removes the own entry and detail
  same(h.store.has('detail:' + ID), false, 'sweep removed the detail')
  h.now += 30_000
  await tickBeat(h)
  same(h.store.has('detail:' + ID), true, 'detail written again on the next beat')
})

await test('safe-stop: a prompt path past the 4000-character cap is not reported as sent without saying it was cut', async () => {
  const longPrompt = '/home/u/' + 'p'.repeat(4500) + '.md'
  const h = await start({ python: pyOk(HANDOFF, longPrompt), env: { HOME: '/home/u' } })
  const out = await safe(h, '')
  if (out.text.startsWith('Safe stop sent')) {
    assert.ok(/cut|truncat|shortened/i.test(out.text), `sent without saying the prompt was cut: ${out.text.slice(0, 120)}`)
  }
})

await test('permission ask with no tool id writes nothing to the store', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  h.writes.length = 0
  await fire(h, 'tool.check', { tool: 'Edit', input: { file_path: '/r/a.ts' } }, 'ask')
  same(h.writes, [], 'store writes for an ask with no id')
})

// ---- sweep, clear, git back-off, config folder

// A pure helper the module must export.
const need = name => {
  if (!(name in lib)) throw new Error(`missing export ${name}`)
  return lib[name]
}
const DAY_OLD_SEED = () => [
  ['sess:' + OTHER, raw({ repo: 'other', at: NOW - 86_400_001 })],
  ['detail:' + OTHER, { v: 1, at: NOW - 86_400_001, recent: [], files: 0, agents: [], spawns: {}, perm: { ask: 0, deny: 0, wait: 0 }, receipt: null }],
]

await test('sweep: unusable claude agents output with exit 0 removes nothing', async () => {
  for (const out of ['Update available\n[]', '', '{"sessions":[]}', '"[]"', '5']) {
    const h = await start({ agents: out, seed: DAY_OLD_SEED() })
    await boardText(h)
    same([h.store.has('sess:' + OTHER), h.store.has('detail:' + OTHER)], [true, true], `records after output ${JSON.stringify(out)}`)
  }
})

await test('sweep: a valid empty array is a real list with no live session, so day-old records go', async () => {
  const h = await start({ agents: [], seed: DAY_OLD_SEED() })
  await boardText(h)
  same([h.store.has('sess:' + OTHER), h.store.has('detail:' + OTHER)], [false, false], 'records after []')
})

await test('clear: a flush that holds the old id and lands after the clear does not recreate the old entry', async () => {
  const h = await start()
  await fire(h, 'session.start', {})
  h.holdStore = true
  const turn = fire(h, 'turn.start', { text: '', turnId: 't1' }) // its flush holds at the store write
  await settle()
  same(h.held.length, 1, 'flushes held at a write')
  await fire(h, 'session.end', { sessionId: ID, reason: 'clear' })
  for (const g of h.held) g.go() // the held write lands after the clear
  await turn
  await settle()
  same(h.store.has('sess:' + ID), false, 'old entry after the held flush landed')
})

await test('git back-off: a turn-end read restarts the idle window; the next idle read comes 5 to 6 minutes after the turn end', async () => {
  const h = await start({ fake: true })
  await fire(h, 'session.start', {})
  await advance(h, 240_000)
  const before = h.gitCalls.length
  await fire(h, 'turn.start', { text: '', turnId: 't1' })
  await fire(h, 'turn.complete', { durationMs: 500, isAborted: false, turnId: 't1' })
  same(h.gitCalls.length - before, 1, 'git reads at the turn end')
  await advance(h, 270_000)
  same(h.gitCalls.length - before, 1, 'git reads 4.5 min after the turn end')
  await advance(h, 90_000)
  same(h.gitCalls.length - before, 2, 'git reads 6 min after the turn end')
})

// Config folder for safe-stop: CLAUDE_CONFIG_DIR, else USERPROFILE, else HOME on Windows.
await test('config folder: on win32, USERPROFILE is used before the MSYS-style HOME', () => {
  const configDir = need('configDir')
  const got = configDir({ HOME: '/c/Users/x', USERPROFILE: 'C:\\Users\\x' }, 'win32')
  assert.match(String(got), /^C:[\\/]Users[\\/]x[\\/]\.claude$/, `configDir on win32 is ${JSON.stringify(got)}`)
})

await test('config folder: CLAUDE_CONFIG_DIR wins; a posix HOME gives HOME/.claude', () => {
  const configDir = need('configDir')
  same(configDir({ CLAUDE_CONFIG_DIR: 'D:\\cfg', HOME: '/c/Users/x', USERPROFILE: 'C:\\Users\\x' }, 'win32'), 'D:\\cfg', 'CLAUDE_CONFIG_DIR')
  same(configDir({ HOME: '/home/u' }, 'linux'), '/home/u/.claude', 'posix HOME')
})

// ---- the question-box check: AskUserQuestion is refused while this session's own work runs

// The AskUserQuestion check alone, matched on its tool (the observer's tool.check matches every tool).
async function askBox(h, e = {}, decision = 'allow') {
  const hook = h.hooks.find(x => x.event === 'tool.check' && x.matcher.tool === 'AskUserQuestion')
  if (!hook) throw new Error('no AskUserQuestion check')
  return hook.fn(h.$, { tool: 'AskUserQuestion', input: { questions: [] }, tool_use_id: 'q1', ...e }, async () => ({ decision }))
}
async function bashBackground(h, useId, taskId) {
  const hook = h.hooks.find(x => x.event === 'tool.call')
  await hook.fn(h.$, { tool: 'Bash', input: { command: 'make test', run_in_background: true }, tool_use_id: useId }, async () => ({ result: { stdout: '', stderr: '', interrupted: false, backgroundTaskId: taskId } }))
}
const notice = (taskId, status = 'completed') => `<task-notification>\n<task-id>${taskId}</task-id>\n<status>${status}</status>\n<summary>done</summary>\n</task-notification>`
async function receive(h, text, kind = 'task-notification') {
  const hook = h.hooks.find(x => x.event === 'session.receive')
  if (!hook) throw new Error('no session.receive hook')
  return hook.fn(h.$, { origin: { kind }, text }, async e => e)
}
async function stopWith(h, tasks, agentId) {
  const hook = h.hooks.find(x => x.event === 'classic.Stop')
  if (!hook) throw new Error('no classic.Stop hook')
  return hook.fn(h.$, { hook_event_name: 'Stop', session_id: ID, background_tasks: tasks, ...(agentId ? { agent_id: agentId } : {}) }, async () => ({}))
}
const PYOK = () => ({ exitCode: 0, stdout: '', stderr: '' })
const guardLines = h => h.pythonCalls.filter(a => a.some(x => String(x).includes('guard_core')))

await test('question box: a live agent refuses it, and the refusal says what to do instead', async () => {
  const h = await start({ liveAgents: [{ id: 'ag1', type: 'Explore', status: 'running', description: 'x' }], python: PYOK, env: { HOME: '/home/u' } })
  await fire(h, 'session.start', {})
  const r = await askBox(h)
  same(r && r.decision, 'deny', 'verdict')
  assert.match(r.reason, /1 agent/, 'the reason counts the agents')
  assert.match(r.reason, /reply/i, 'the reason says to ask in the reply')
  assert.match(r.reason, /waiting page/i, 'the reason names the waiting page')
  assert.match(r.reason, /keep working/i, 'the reason says to keep working')
  await settle()
  same(guardLines(h).length, 1, 'one guard.log line per refusal')
  assert.ok(guardLines(h)[0].includes('deny'), 'the guard.log line is a deny')
})

await test('question box: a live background command refuses it, until its notice arrives', async () => {
  const h = await start({ python: PYOK, env: { HOME: '/home/u' } })
  await fire(h, 'session.start', {})
  await bashBackground(h, 'b1', 'task1')
  const r = await askBox(h)
  same(r && r.decision, 'deny', 'verdict while it runs')
  assert.match(r.reason, /1 background task/, 'the reason counts the tasks')
  same((await receive(h, notice('task1'))).text, notice('task1'), 'the notice passes on unchanged')
  same((await askBox(h)).decision, 'allow', 'verdict after its notice')
})

await test('question box: the turn-end list of background work replaces what the check tracked', async () => {
  const h = await start({ python: PYOK, env: { HOME: '/home/u' } })
  await fire(h, 'session.start', {})
  await bashBackground(h, 'b1', 'task1')
  await stopWith(h, [])
  same((await askBox(h)).decision, 'allow', 'an empty list clears a missed notice')
  await stopWith(h, [{ id: 'task9', type: 'shell', status: 'running', description: 'x' }])
  same((await askBox(h)).decision, 'deny', 'a listed shell task refuses')
  await stopWith(h, [], 'sub1')
  same((await askBox(h)).decision, 'deny', "an agent's turn end leaves the session's list alone")
})

await test('question box: a background workflow refuses it, from its start and from the turn-end list', async () => {
  const h = await start({ python: PYOK, env: { HOME: '/home/u' } })
  await fire(h, 'session.start', {})
  const hook = h.hooks.find(x => x.event === 'tool.call')
  await hook.fn(h.$, { tool: 'Workflow', input: {}, tool_use_id: 'w1' }, async () => ({ result: { status: 'async_launched', taskId: 'wf1' } }))
  same((await askBox(h)).decision, 'deny', 'verdict after its start')
  await receive(h, notice('wf1'))
  same((await askBox(h)).decision, 'allow', 'verdict after its notice')
  await stopWith(h, [{ id: 'wf2', type: 'workflow', status: 'running', description: 'x' }, { id: 'm1', type: 'monitor', status: 'running', description: 'x' }])
  const r = await askBox(h)
  same(r.decision, 'deny', 'a listed workflow refuses')
  assert.match(r.reason, /1 background task\b/, 'a monitor does not count')
})

await test('question box: nothing running lets it through', async () => {
  const h = await start({ liveAgents: [{ id: 'ag1', type: 'Explore', status: 'completed', description: 'x' }, { id: 'ag2', type: 'x', status: 'idle', description: 'x' }] })
  await fire(h, 'session.start', {})
  same((await askBox(h)).decision, 'allow', 'ended and idle agents do not count')
  same(h.pythonCalls.length, 0, 'an allowed box starts no process')
})

await test('question box: the asking agent does not count itself', async () => {
  const h = await start({ liveAgents: [{ id: 'ag1', type: 'x', status: 'running', description: 'x' }] })
  await fire(h, 'session.start', {})
  same((await askBox(h, { agentId: 'ag1' })).decision, 'allow', 'its own loop')
})

await test('question box: an unreadable agent list fails open and says unknown', async () => {
  const h = await start({ agentListThrow: true, python: PYOK, env: { HOME: '/home/u' } })
  await fire(h, 'session.start', {})
  same((await askBox(h)).decision, 'allow', 'verdict')
  await settle()
  assert.ok(h.logs.some(l => /unknown/.test(l.text)), 'the debug log says unknown')
  same(guardLines(h).length, 1, 'one guard.log line')
  assert.ok(guardLines(h)[0].includes('noted') && guardLines(h)[0].some(x => /unknown/.test(String(x))), 'it is a noted unknown line')
})

await test('question box: a hung agent list fails open within its read budget', async () => {
  const h = await start({ fake: false })
  await fire(h, 'session.start', {})
  h.$.agent.list = () => new Promise(() => {})
  same(await within(lib.READ_BUDGET_MS + 1500, askBox(h)), 'done', 'the check returns')
})

await test('question box: an earlier deny stands and costs no read', async () => {
  const h = await start({ liveAgents: [] })
  await fire(h, 'session.start', {})
  let reads = 0
  h.$.agent.list = async () => { reads++; return [] }
  same((await askBox(h, {}, 'deny')).decision, 'deny', 'verdict')
  same(reads, 0, 'no agent read')
})

// One tool call through the tool.call hook; `answer` is what the rest of the chain returns, or throws.
async function callTool(h, tool, answer) {
  const hook = h.hooks.find(x => x.event === 'tool.call')
  try { await hook.fn(h.$, { tool, input: {}, tool_use_id: 'u-' + tool }, async () => { if (answer instanceof Error) throw answer; return answer }) } catch { /* the call failed */ }
}
const STARTED = { result: { content: [{ type: 'text', text: 'session_x started' }] } }

for (const tool of ['mcp__ccd_session__start_session', 'mcp__claude-code-remote__create_session']) {
  await test(`question box: a session that started a session is refused, with nothing running (${tool})`, async () => {
    const h = await start({ liveAgents: [], python: PYOK, env: { HOME: '/home/u' } })
    await fire(h, 'session.start', {})
    await callTool(h, tool, STARTED)
    const r = await askBox(h)
    same(r && r.decision, 'deny', 'verdict')
    assert.match(r.reason, /started 1 session\b/, 'the reason counts the started sessions')
    assert.match(r.reason, /waiting page/i, 'the reason names the waiting page')
    assert.match(r.reason, /keep working/i, 'the reason says to keep working')
    await callTool(h, tool, STARTED)
    assert.match((await askBox(h)).reason, /started 2 sessions/, 'a second start counts')
    await settle()
    assert.ok(guardLines(h).length >= 1 && guardLines(h)[0].some(x => /started=1/.test(String(x))), 'the guard.log line counts the starts')
  })
}

await test("question box: the desktop start tool is the guard's own SESSION_TOOL", async () => {
  const { readFileSync } = await import('node:fs')
  const guard = readFileSync(fileURLToPath(new URL('../../hooks/guard.py', import.meta.url)), 'utf8')
  const m = /^SESSION_TOOL = "([^"]+)"$/m.exec(guard)
  assert.ok(m && lib.startsSession(m[1]), `guard.py SESSION_TOOL ${m && m[1]} is not a start`)
})

await test('question box: a failed or refused session start leaves it open', async () => {
  const h = await start({ liveAgents: [] })
  await fire(h, 'session.start', {})
  await callTool(h, 'mcp__ccd_session__start_session', { result: 'no such repo', isError: true, text: 'no such repo' })
  await callTool(h, 'mcp__claude-code-remote__create_session', { deny: 'refused' })
  await callTool(h, 'mcp__claude-code-remote__create_session', new Error('host failed'))
  same((await askBox(h)).decision, 'allow', 'verdict')
})

await test('question box: a tool that only looks like a session start leaves it open', async () => {
  const h = await start({ liveAgents: [] })
  await fire(h, 'session.start', {})
  for (const tool of ['mcp__claude-code-remote__create_session_tags', 'mcp__claude-code-remote__send_message', 'mcp__claude-code-remote__set_session_tags', 'mcp__other__start_session', 'mcp__other__create_session', 'mcp__ccd_session__start_sessions', 'Agent', 'start_session']) {
    await callTool(h, tool, STARTED)
  }
  same((await askBox(h)).decision, 'allow', 'verdict')
})

await test('question box: the start count lives in the board record and survives a mod reload', async () => {
  const h = await start({ liveAgents: [] })
  await fire(h, 'session.start', {})
  await callTool(h, 'mcp__ccd_session__start_session', STARTED)
  await settle()
  same(h.store.get('sess:' + ID).started, 1, 'the board record holds the count')
  const h2 = await start({ liveAgents: [], seed: [...h.store] }) // a reload: fresh module, same store
  await fire(h2, 'session.start', {})
  await settle()
  same((await askBox(h2)).decision, 'deny', 'verdict after the reload')
  same(h2.store.get('sess:' + ID).started, 1, 'the next write keeps the count')
})

await test("question box: GUARD_PY writes one guard.log line through the real guard_core writer", async () => {
  const { spawnSync } = await import('node:child_process')
  const { mkdtempSync, readFileSync, rmSync } = await import('node:fs')
  const { tmpdir } = await import('node:os')
  const { join } = await import('node:path')
  const hooks = fileURLToPath(new URL('../../hooks', import.meta.url))
  const cfg = mkdtempSync(join(tmpdir(), 'sb-guardlog-'))
  try {
    const r = spawnSync(process.platform === 'win32' ? 'python' : 'python3', ['-I', '-B', '-c', lib.GUARD_PY, hooks, ID, 'deny', lib.QUESTION_RULE, 'agents=1 tasks=0'], { cwd: cfg, env: { ...process.env, CLAUDE_CONFIG_DIR: cfg }, encoding: 'utf8' })
    same(r.status, 0, 'python exit: ' + r.stderr)
    const fields = readFileSync(join(cfg, 'guard.log'), 'utf8').trim().split('\t')
    same(fields.slice(1), ['AskUserQuestion', 'deny', 'question-box-while-work', 'agents=1 tasks=0', ID], 'guard.log fields after the time')
  } finally { rmSync(cfg, { recursive: true, force: true }) }
})

const fails = results.filter(r => r.startsWith('FAIL')).length
console.log(results.join('\n'))
console.log(`session-board pins: ${results.length - fails} pass, ${fails} fail of ${results.length}`)
if (fails) process.exitCode = 1

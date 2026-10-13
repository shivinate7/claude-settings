// Pure helpers for session-board. No host calls here, so node can test them.

export const STALE_MS = 120_000
export const HEARTBEAT_MS = 30_000
export const ENTRY_MAX_BYTES = 1024
export const DETAIL_MAX_BYTES = 3072
export const MAX_KEYS = 100
export const GC_MS = 86_400_000 // an entry this long past its last beat is deleted
export const MAX_RECENT = 5
export const MAX_AGENTS = 8
export const MAX_SPAWN_TYPES = 6
export const MAX_FILES = 2000
export const AGENTS_TIMEOUT_MS = 10_000
export const GIT_TIMEOUT_MS = 5000
const EDIT_TOOLS = new Set(['Edit', 'Write', 'MultiEdit', 'NotebookEdit'])
const SPAWN_TOOLS = new Set(['Agent', 'Task'])
const LIVE = new Set(['pending', 'running', 'waiting'])

// Plain text for anything shown. Control, format and bidi characters become spaces. Markup
// characters become "_". Long runs of combining marks go. The result is short and inert.
export function clean(v, max = 40) {
  let s = typeof v === 'string' ? v : v == null ? '' : String(v)
  s = s.replace(/[\p{C}]/gu, ' ').replace(/[<>&"`]/g, '_')
  s = s.replace(/\p{M}{3,}/gu, '').replace(/\s+/g, ' ').trim()
  const chars = Array.from(s)
  return chars.length > max ? chars.slice(0, Math.max(0, max - 1)).join('') + '…' : s
}

// A whole number in [lo, hi], else null.
export const num = (v, lo = 0, hi = 999_999) =>
  typeof v === 'number' && Number.isFinite(v) ? Math.min(hi, Math.max(lo, Math.round(v))) : null

export const baseName = p => String(p ?? '').split(/[\\/]/).filter(Boolean).pop() ?? ''
// UTF-8 size of the JSON text. The mod runs where there is no Node, so no Buffer.
export function byteLen(o) {
  let n = 0
  for (const ch of JSON.stringify(o)) {
    const c = ch.codePointAt(0)
    n += c < 0x80 ? 1 : c < 0x800 ? 2 : c < 0x10000 ? 3 : 4
  }
  return n
}
const isId = v => typeof v === 'string' && /^[0-9a-zA-Z_-]{8,64}$/.test(v)
export const isSessionId = isId

// The one git call per turn. Hooks, the optional lock and fsmonitor stay off.
export const gitArgs = () => ['git', '-c', 'core.fsmonitor=false', '--no-optional-locks', 'status', '--porcelain=v2', '--branch']

// `git status --porcelain=v2 --branch`. unpushed is null when git gives no ahead count
// (no upstream): unknown, never zero.
export function parseStatus(text) {
  let branch = ''
  let ahead = null
  let dirty = 0
  for (const line of String(text ?? '').split('\n')) {
    if (line.startsWith('# branch.head ')) branch = line.slice(14).trim()
    else if (line.startsWith('# branch.ab ')) {
      const m = line.match(/\+(\d+) -(\d+)/)
      if (m) ahead = Number(m[1])
    } else if (line && line[0] !== '#') dirty++
  }
  return { branch: branch === '(detached)' ? 'detached' : branch, dirty: Math.min(dirty, 9999), unpushed: ahead === null ? null : Math.min(ahead, 9999) }
}

// What one tool call adds to the recent list: the tool name and a file name, nothing else.
export function toolTarget(tool, input) {
  const i = input && typeof input === 'object' ? input : {}
  const path = i.file_path ?? i.notebook_path ?? i.path
  return { t: clean(tool, 24), f: typeof path === 'string' ? clean(baseName(path), 40) : '', edit: EDIT_TOOLS.has(tool), path: typeof path === 'string' ? path : '' }
}

export const spawnType = input => clean(input && typeof input === 'object' ? input.subagent_type || 'general-purpose' : 'general-purpose', 24)

function capSpawns(spawns) {
  const out = {}
  let other = 0
  const list = Object.entries(spawns ?? {}).map(([k, n]) => [clean(k, 24), num(n, 0, 9999) ?? 0]).filter(([k, n]) => k && n > 0).sort((a, b) => b[1] - a[1])
  list.forEach(([k, n], i) => {
    if (i < MAX_SPAWN_TYPES) out[k] = (out[k] ?? 0) + n
    else other += n
  })
  if (other) out.other = (out.other ?? 0) + other
  return out
}

// Shrink until the JSON fits the cap: spawn types first, then the long text fields.
function fit(obj, cap, steps) {
  for (const step of steps) {
    if (byteLen(obj) <= cap) return obj
    step(obj)
  }
  return byteLen(obj) <= cap ? obj : { v: 1, at: obj.at }
}
const half = (o, k) => { o[k] = Array.from(o[k]).slice(0, Math.max(1, Math.floor(Array.from(o[k]).length / 2))).join('') }

// The `sess:<id>` entry. Under 1 KB. Repo name and branch only: no prompt, no path.
export function buildEntry(s) {
  const e = {
    v: 1,
    repo: clean(s.repo, 40),
    branch: clean(s.branch, 60),
    state: s.ask || !s.working ? 'waiting' : 'working',
    ask: !!s.ask,
    dirty: num(s.dirty, 0, 9999),
    unpushed: num(s.unpushed, 0, 9999),
    agents: num(s.agents, 0, 99) ?? 0,
    spawns: capSpawns(s.spawns),
    ctx: num(s.ctx, 0, 100),
    at: s.now,
  }
  const dropSpawn = o => { const k = Object.keys(o.spawns).pop(); if (k) delete o.spawns[k] }
  return fit(e, ENTRY_MAX_BYTES, [...Array(MAX_SPAWN_TYPES + 1).fill(dropSpawn), o => half(o, 'branch'), o => half(o, 'branch'), o => half(o, 'repo'), o => half(o, 'repo'), o => half(o, 'repo')])
}

// The `detail:<id>` record. About 3 KB. File names only.
export function buildDetail(s) {
  const d = {
    v: 1,
    at: s.now,
    recent: (s.recent ?? []).slice(-MAX_RECENT).map(r => ({ t: clean(r.t, 24), f: clean(r.f, 40) })),
    files: num(s.files, 0, 99_999) ?? 0,
    agents: (s.agents ?? []).slice(0, MAX_AGENTS).map(a => ({ t: clean(a.type, 24), s: clean(a.status, 12) })),
    spawns: capSpawns(s.spawns),
    perm: { ask: num(s.perm?.ask, 0, 99_999) ?? 0, deny: num(s.perm?.deny, 0, 99_999) ?? 0, wait: num(s.perm?.wait, 0, 99) ?? 0 },
    receipt: s.receipt ? { sec: num(s.receipt.sec, 0, 999_999) ?? 0, tools: num(s.receipt.tools, 0, 99_999) ?? 0, edits: num(s.receipt.edits, 0, 99_999) ?? 0, asks: num(s.receipt.asks, 0, 99_999) ?? 0, aborted: !!s.receipt.aborted } : null,
  }
  return fit(d, DETAIL_MAX_BYTES, [o => { o.agents.length = Math.min(o.agents.length, 3) }, o => { o.recent = o.recent.slice(-2) }, o => { o.agents = [] }, o => { o.recent = [] }, o => { o.spawns = {} }])
}

// Read back from the store: another writer on the machine may have put anything there.
export function readEntry(raw) {
  if (!raw || typeof raw !== 'object' || raw.v !== 1) return null
  const at = num(raw.at, 0, 8.64e15)
  if (at === null) return null
  const spawns = capSpawns(raw.spawns && typeof raw.spawns === 'object' ? raw.spawns : {})
  return {
    repo: clean(raw.repo, 40),
    branch: clean(raw.branch, 60),
    state: raw.state === 'working' ? 'working' : 'waiting',
    ask: raw.ask === true,
    dirty: num(raw.dirty, 0, 9999),
    unpushed: num(raw.unpushed, 0, 9999),
    agents: num(raw.agents, 0, 99) ?? 0,
    spawns,
    ctx: num(raw.ctx, 0, 100),
    at,
  }
}
export function readDetail(raw) {
  if (!raw || typeof raw !== 'object' || raw.v !== 1) return null
  return buildDetail({
    now: num(raw.at, 0, 8.64e15) ?? 0,
    recent: Array.isArray(raw.recent) ? raw.recent.filter(r => r && typeof r === 'object').map(r => ({ t: r.t, f: r.f })) : [],
    files: raw.files,
    agents: Array.isArray(raw.agents) ? raw.agents.filter(a => a && typeof a === 'object').map(a => ({ type: a.t, status: a.s })) : [],
    spawns: raw.spawns && typeof raw.spawns === 'object' ? raw.spawns : {},
    perm: raw.perm && typeof raw.perm === 'object' ? raw.perm : {},
    receipt: raw.receipt && typeof raw.receipt === 'object' ? raw.receipt : null,
  })
}

// Hidden after 2 minutes without a heartbeat. An entry stamped in the future is not fresh.
export const isFresh = (entry, now) => !!entry && entry.at <= now + STALE_MS && now - entry.at <= STALE_MS

// Update-ready: no running agents, waiting, no unpushed commits, clean tree. Unknown is not ready.
export const isUpdateReady = e => !!e && e.agents === 0 && e.state === 'waiting' && !e.ask && e.unpushed === 0 && e.dirty === 0

// `claude agents --json` text to rows. Anything else gives [].
export function parseAgentsJson(text) {
  let list
  try { list = JSON.parse(text) } catch { return [] }
  if (!Array.isArray(list)) return []
  return list
    .filter(r => r && typeof r === 'object' && isId(r.sessionId))
    .map(r => ({ id: r.sessionId, repo: clean(baseName(r.cwd), 40), state: r.status === 'busy' ? 'working' : r.status === 'idle' ? 'waiting' : 'unknown' }))
}

// Rows for the board: `claude agents` rows seeded first, then fresh store entries merged in by
// session id. A session without an entry shows as "no detail". entries: Map id -> readEntry().
export function mergeRows(agentRows, entries, now) {
  const rows = new Map()
  for (const a of agentRows ?? []) rows.set(a.id, { id: a.id, repo: a.repo, branch: '', state: a.state, ask: false, ready: null, ctx: null, agents: null, detail: false })
  for (const [id, e] of entries ?? []) {
    if (!isFresh(e, now) || !isId(id)) continue
    rows.set(id, { id, repo: e.repo, branch: e.branch, state: e.state, ask: e.ask, ready: isUpdateReady(e), ctx: e.ctx, agents: e.agents, detail: true })
  }
  const order = { working: 0, waiting: 1, unknown: 2 }
  return [...rows.values()].sort((a, b) => order[a.state] - order[b.state] || a.repo.localeCompare(b.repo) || a.branch.localeCompare(b.branch) || a.id.localeCompare(b.id))
}

export function bandText(rows) {
  if (!rows.length) return 'No sessions found'
  const n = s => rows.filter(r => r.state === s).length
  const parts = [`${n('working')} working`, `${n('waiting')} waiting`, `update-ready ${rows.filter(r => r.ready === true).length} of ${rows.length}`]
  if (n('unknown')) parts.push(`${n('unknown')} unknown`)
  const blind = rows.filter(r => !r.detail).length
  if (blind) parts.push(`${blind} no detail`)
  return parts.join(', ')
}

const pad = (s, n) => { const c = Array.from(s); return c.length > n ? c.slice(0, n - 1).join('') + '…' : s + ' '.repeat(n - c.length) }
const stateLabel = r => (r.state === 'waiting' && r.ask ? 'permission' : r.state)
const readyLabel = r => (r.ready === null ? 'no detail' : r.ready ? 'ready' : 'not ready')
function widths(cols) {
  const c = num(cols, 40, 400) ?? 80
  return { repo: 18, branch: Math.max(8, Math.min(24, c - 52)), state: 10, ready: 9 }
}
export function headerText(cols) {
  const w = widths(cols)
  return [pad('repo', w.repo), pad('branch', w.branch), pad('state', w.state), pad('update', w.ready), 'ctx', 'ag'].join(' ')
}
export function rowText(r, cols) {
  const w = widths(cols)
  return [pad(r.repo, w.repo), pad(r.branch || '-', w.branch), pad(stateLabel(r), w.state), pad(readyLabel(r), w.ready), pad(r.ctx === null ? '-' : `${r.ctx}%`, 3), r.agents === null ? '-' : String(r.agents)].join(' ')
}

export const ago = (now, at) => {
  const s = Math.max(0, Math.round((now - at) / 1000))
  return s < 90 ? `${s} s ago` : `${Math.round(s / 60)} min ago`
}

// Lines for the per-session view. row: a mergeRows row; detail: readDetail() or null.
export function detailLines(row, detail, now) {
  const out = [`${clean(row.repo, 24)}  ${clean(row.branch, 32) || '-'}  ${stateLabel(row)}  ${readyLabel(row)}`]
  if (!row.detail || !detail) {
    out.push(row.detail ? 'Detail record not found yet.' : 'No detail: this session does not run the session-board mod.')
    return out
  }
  const spawns = Object.entries(detail.spawns).map(([k, n]) => `${k} ${n}`).join(', ')
  out.push(`Context ${row.ctx === null ? '-' : row.ctx + '%'}   Files touched ${detail.files}   Updated ${ago(now, detail.at)}`)
  out.push(`Agents running ${row.agents ?? 0}: ${detail.agents.map(a => `${a.t} ${a.s}`).join(', ') || 'none'}`)
  out.push(`Spawned: ${spawns || 'none'}`)
  out.push(`Permission checks: ${detail.perm.ask} asked, ${detail.perm.deny} denied, ${detail.perm.wait} waiting now`)
  out.push(`Recent: ${detail.recent.map(r => (r.f ? `${r.t} ${r.f}` : r.t)).join(' | ') || 'none'}`)
  const r = detail.receipt
  out.push(r ? `Last turn: ${r.sec} s, ${r.tools} tool calls, ${r.edits} edits, ${r.asks} permission checks${r.aborted ? ', stopped early' : ''}` : 'Last turn: none yet')
  return out
}

// /safe-stop. The text goes to the session as a prompt. The handoff hook's own prompt file holds
// the rules for the file itself. No handoff writer lives in this mod.
export const safeStopMessage = (prompt, handoff) =>
  `Safe stop. Finish or park the step you are on. Start no new work and no new agent. Then follow ${prompt} and rewrite your handoff at ${handoff}: the whole file, never append. When done, reply with one line: branch, uncommitted files, unpushed commits, running agents.`

export function safeStopPlan(text, missing) {
  const steps = ["/safe-stop would: (1) ask the installed handoff hook (hooks/precompact_handoff.py) for this session's handoff and prompt paths; (2) send this session one prompt."]
  if (text) steps.push('Prompt: ' + text)
  if (missing.length) steps.push('Missing: ' + missing.join('; ') + '. Nothing was sent.')
  else steps.push('Plan only: nothing was sent.')
  return steps.join('\n')
}

// One session's running record. The hooks feed it; entry() and detail() read it.
export function makeTracker() {
  let t
  const reset = () => {
    t = { inTurn: false, pending: new Set(), spawns: {}, recent: [], files: new Set(), ask: 0, deny: 0, turn: { tools: 0, edits: 0, asks: 0 }, receipt: null, git: { branch: '', dirty: null, unpushed: null }, agents: [], ctx: null, repo: '' }
  }
  reset()
  const live = () => t.agents.filter(a => LIVE.has(a.status))
  return {
    reset,
    turnStart() { t.inTurn = true; t.pending.clear(); t.turn = { tools: 0, edits: 0, asks: 0 } },
    turnComplete({ durationMs, isAborted }) {
      t.inTurn = false
      t.pending.clear()
      t.receipt = { sec: Math.round((durationMs ?? 0) / 1000), ...t.turn, aborted: !!isAborted }
    },
    // verdict: what the rest of the chain decided: allow, ask or deny. A query has no id: skipped.
    toolCheck({ tool, input, id, verdict }) {
      if (!id) return
      const g = toolTarget(tool, input)
      t.recent.push({ t: g.t, f: g.f })
      t.recent = t.recent.slice(-MAX_RECENT)
      t.turn.tools++
      if (verdict === 'deny') { t.deny++; return }
      if (g.edit) { t.turn.edits++; if (g.path && t.files.size < MAX_FILES) t.files.add(g.path) }
      if (SPAWN_TOOLS.has(tool)) { const k = spawnType(input); t.spawns[k] = (t.spawns[k] ?? 0) + 1 }
      if (verdict === 'ask') { t.ask++; t.turn.asks++; t.pending.add(id) }
    },
    toolCall(id) { return t.pending.delete(id) },
    setGit(g) { t.git = g },
    setAgents(list) { t.agents = (list ?? []).map(a => ({ type: a.type, status: a.status })) },
    setCtx(p) { t.ctx = p },
    setRepo(r) { t.repo = r },
    entry(now) {
      return buildEntry({ repo: t.repo, branch: t.git.branch, working: t.inTurn, ask: t.pending.size > 0, dirty: t.git.dirty, unpushed: t.git.unpushed, agents: live().length, spawns: t.spawns, ctx: t.ctx, now })
    },
    detail(now) {
      return buildDetail({ now, recent: t.recent, files: t.files.size, agents: live(), spawns: t.spawns, perm: { ask: t.ask, deny: t.deny, wait: t.pending.size }, receipt: t.receipt })
    },
  }
}

// Pure helpers for session-board. No host calls here, so node can test them.

export const STALE_MS = 120_000
export const HEARTBEAT_MS = 30_000
export const ENTRY_MAX_BYTES = 1024
export const DETAIL_MAX_BYTES = 3072
export const MAX_KEYS = 200 // entries read per refresh, newest key first
export const GC_MS = 86_400_000 // an entry this long past its last beat is deleted
export const SKEW_MS = 30_000 // a stamp further ahead than this is not fresh
export const READ_MAX_AGE_MS = 330_000 // a git reading older than this is unknown: the idle read interval plus one beat
export const MAX_POLLS = 10 // board refreshes on the heartbeat with no /board call
export const GRACE_MS = 100 // most a hook waits for its refresh
export const READ_BUDGET_MS = 3000 // most one host read may take
export const MAX_PATH = 4000
export const TO_MAX = 300 // a session name is kept and matched to this length (review round 2 of judge-scope), never the 40-char display cap
export const GIT_IDLE_MS = 300_000 // an idle session reads git at most this often (a turn end or an attach reads too)
export const MAX_RECENT = 5
export const MAX_AGENTS = 8
export const MAX_SPAWN_TYPES = 6
export const MAX_FILES = 2000
export const AGENTS_TIMEOUT_MS = 8000
export const GIT_TIMEOUT_MS = 5000
const EDIT_TOOLS = new Set(['Edit', 'Write', 'MultiEdit', 'NotebookEdit'])
const FILE_TOOLS = new Set(['Read', 'Edit', 'Write', 'MultiEdit', 'NotebookEdit', 'Glob', 'Grep'])
const SPAWN_TOOLS = new Set(['Agent', 'Task'])
const LIVE = new Set(['pending', 'running', 'waiting'])
// Runs of /safe-stop that do not come from the person. Not a list of who may run it: the
// desktop app can arrive as "unclassified", so only these are refused.
const NON_USER_ORIGINS = new Set(['plugin', 'peer', 'peer-send-message', 'projects-relay', 'channel', 'coordinator', 'observer', 'observer-activity', 'task-notification', 'scheduled-trigger', 'auto-continuation'])
export const isUserOrigin = origin => !(origin && typeof origin === 'object' && NON_USER_ORIGINS.has(origin.kind))

// Plain text for anything shown. Control, format and bidi characters become spaces. Markup
// characters become "_". Long runs of combining marks go. The result is short and inert.
export function clean(v, max = 40) {
  let s = typeof v === 'string' ? v : v == null ? '' : String(v)
  s = s.replace(/[\p{C}]/gu, ' ').replace(/[<>&"`]/g, '_')
  s = s.replace(/\p{M}{3,}/gu, '').replace(/\s+/g, ' ').trim()
  const chars = Array.from(s)
  return chars.length > max ? chars.slice(0, Math.max(0, max - 1)).join('') + '…' : s
}

// A path or file path shown or sent whole: control and bidi characters go, nothing else changes.
// Not for names on the board: those go through clean().
export function cleanPath(v) {
  const s = typeof v === 'string' ? v : ''
  return Array.from(s.replace(/\p{C}/gu, '')).slice(0, MAX_PATH).join('')
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

// Names that say they hold secrets. The same rule as isSecretPath in mods/plain-diff, copied
// on purpose: each mod stands alone and neither imports the other.
export function isSecretName(name) {
  const b = String(name).replace(/\\/g, '/').split('/').pop().toLowerCase()
  return (
    (/^\.env(\..*)?$/.test(b) && !/\.(example|sample|template|dist)$/.test(b)) ||
    /\.(env|pem|key|p12|pfx|jks|keystore|ppk|asc|tfvars)$/.test(b) ||
    /^\.(envrc|npmrc|netrc|pgpass|pypirc|htpasswd|git-credentials)$/.test(b) ||
    b === '_netrc' ||
    /^id_(rsa|dsa|ecdsa|ed25519)$/.test(b) ||
    /^(application_default_)?credentials(\.(json|ya?ml|toml|ini|xml|csv|txt))?$/.test(b) ||
    /^secrets?\.(json|ya?ml|md|txt|env|toml)$/.test(b) ||
    /^service-account.*\.json$/.test(b)
  )
}

// What one tool call adds to the recent list: the tool name and, for a file tool only, a file
// name. An MCP tool, a Bash command and any tool off the list give no name. A Grep or Glob path
// counts only when its last part has an extension: a folder path never shows.
// ponytail: a folder named like a file (v1.2) still passes. Upgrade: ask the file system.
export function toolTarget(tool, input) {
  const i = input && typeof input === 'object' ? input : {}
  const out = { t: clean(tool, 24), f: '', edit: EDIT_TOOLS.has(tool), path: '' }
  if (!FILE_TOOLS.has(tool)) return out
  const path = tool === 'NotebookEdit' ? i.notebook_path : tool === 'Glob' || tool === 'Grep' ? i.path : i.file_path
  if (typeof path !== 'string' || !path) return out
  const name = baseName(path)
  if ((tool === 'Glob' || tool === 'Grep') && !/\.[^.\s]+$/.test(name)) return out
  out.f = isSecretName(name) ? '(secret file)' : clean(name, 40)
  if (out.edit) out.path = path
  return out
}

export const spawnType = input => clean(input && typeof input === 'object' ? input.subagent_type || 'general-purpose' : 'general-purpose', 24)

// Spawn counts as a plain object, from a Map or an object. A type named like an
// Object.prototype key (constructor, __proto__) is an own key here, never the inherited one.
const put = (o, k, n) => Object.defineProperty(o, k, { value: n, enumerable: true, writable: true, configurable: true })
function capSpawns(spawns) {
  const out = {}
  const sums = new Map()
  for (const [k, n] of spawns instanceof Map ? spawns : Object.entries(spawns ?? {})) {
    const key = clean(k, 24)
    const count = num(n, 0, 9999) ?? 0
    if (key && count > 0) sums.set(key, (sums.get(key) ?? 0) + count)
  }
  let other = 0
  ;[...sums].sort((a, b) => b[1] - a[1]).forEach(([k, n], i) => {
    if (i < MAX_SPAWN_TYPES) put(out, k, n)
    else other += n
  })
  if (other) put(out, 'other', (Object.prototype.hasOwnProperty.call(out, 'other') ? out.other : 0) + other)
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
  // When the git counts were read. Absent for an entry that has no reading time.
  if (num(s.rt, 0, 8.64e15) !== null) e.rt = num(s.rt, 0, 8.64e15)
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
  const e = {
    repo: clean(raw.repo, 40),
    branch: clean(raw.branch, 60),
    // A missing or odd state is unknown, never waiting: waiting would let it count as ready.
    state: raw.state === 'working' || raw.state === 'waiting' ? raw.state : 'unknown',
    ask: raw.ask === true,
    dirty: num(raw.dirty, 0, 9999),
    unpushed: num(raw.unpushed, 0, 9999),
    agents: num(raw.agents, 0, 99) ?? 0,
    spawns,
    ctx: num(raw.ctx, 0, 100),
    at,
  }
  const rt = num(raw.rt, 0, 8.64e15)
  if (rt !== null) e.rt = rt
  return e
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

// Hidden after 2 minutes without a heartbeat. A stamp more than 30 s ahead of now is not fresh.
export const isFresh = (entry, now) => !!entry && entry.at <= now + SKEW_MS && now - entry.at <= STALE_MS

// Update-ready: no running agents, waiting, no permission ask, no unpushed commits, clean tree.
// true, false, or 'unknown' when a git count is missing or its reading (e.rt) is older than
// 330 s or stamped ahead. Only true counts as ready. Without `now`, the reading time is not checked.
export function readiness(e, now) {
  if (!e || e.agents !== 0 || e.state !== 'waiting' || e.ask) return false
  if (e.dirty === null || e.unpushed === null) return 'unknown'
  if (typeof e.rt === 'number' && typeof now === 'number' && (now - e.rt > READ_MAX_AGE_MS || e.rt - now > SKEW_MS)) return 'unknown'
  return e.dirty === 0 && e.unpushed === 0
}
export const isUpdateReady = (e, now) => readiness(e, now) === true

// `claude agents --json` text to rows. Anything else gives []. A "waiting" row is a session
// that waits on a permission answer.
export function parseAgentsJson(text) {
  let list
  try { list = JSON.parse(text) } catch { return [] }
  return agentRows(list)
}

// Rows from an already parsed `claude agents --json` list. Not an array gives [].
export function agentRows(list) {
  if (!Array.isArray(list)) return []
  const state = s => (s === 'busy' ? 'working' : s === 'idle' || s === 'waiting' ? 'waiting' : 'unknown')
  return list
    .filter(r => r && typeof r === 'object' && isId(r.sessionId))
    .map(r => ({ id: r.sessionId, name: typeof r.name === 'string' ? clean(r.name, TO_MAX) : '', repo: clean(baseName(r.cwd), 40), state: state(r.status), ask: r.status === 'waiting' }))
}

// The `claude agents` state of the one row named `name`: busy, idle or waiting (on a permission
// answer). 'unseen' when no row, or more than one row, has that name, or its state is unknown.
export function receiverState(rows, name) {
  const find = n => (rows ?? []).filter(r => n && r.name === n)
  const full = typeof name === 'string' ? clean(name, TO_MAX) : ''
  let hits = find(full)
  // ListAgents prints `name [ref]` when names clash. Only when the full name matches nothing, drop the ref.
  if (!hits.length && typeof name === 'string') hits = find(clean(name.replace(/ \[[^\]]*\]$/, ''), TO_MAX))
  if (hits.length !== 1) return 'unseen'
  const r = hits[0]
  return r.state === 'working' ? 'busy' : r.state !== 'waiting' ? 'unseen' : r.ask ? 'waiting' : 'idle'
}

// Rows for the board: `claude agents` rows seeded first, then fresh store entries merged in by
// session id. A session without an entry shows as "no detail". entries: Map id -> readEntry().
export function mergeRows(agentRows, entries, now) {
  const rows = new Map()
  for (const a of agentRows ?? []) rows.set(a.id, { id: a.id, repo: a.repo, branch: '', state: a.state, ask: !!a.ask, ready: null, ctx: null, agents: null, detail: false })
  for (const [id, e] of entries ?? []) {
    if (!isFresh(e, now) || !isId(id)) continue
    rows.set(id, { id, repo: e.repo, branch: e.branch, state: e.state, ask: e.ask, ready: readiness(e, now), ctx: e.ctx, agents: e.agents, detail: true, at: e.at })
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
const readyLabel = r => (r.ready === null ? 'no detail' : r.ready === 'unknown' ? 'unknown' : r.ready ? 'ready' : 'not ready')
function widths(cols) {
  const c = num(cols, 40, 400) ?? 80
  return { repo: 18, branch: Math.max(8, Math.min(24, c - 52)), state: 10, ready: 9 }
}
export function headerText(cols) {
  const w = widths(cols)
  return [pad('repo', w.repo), pad('branch', w.branch), pad('state', w.state), pad('update', w.ready), pad('ctx', 4), 'ag'].join(' ')
}
export function rowText(r, cols) {
  const w = widths(cols)
  return [pad(r.repo, w.repo), pad(r.branch || '-', w.branch), pad(stateLabel(r), w.state), pad(readyLabel(r), w.ready), pad(r.ctx === null ? '-' : `${r.ctx}%`, 4), r.agents === null ? '-' : String(r.agents)].join(' ')
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
  out.push(`Context ${row.ctx === null ? '-' : row.ctx + '%'}   Files touched ${detail.files}   Updated ${ago(now, row.at ?? detail.at)}`)
  out.push(`Agents running ${row.agents ?? 0}: ${detail.agents.map(a => `${a.t} ${a.s}`).join(', ') || 'none'}`)
  out.push(`Spawned: ${spawns || 'none'}`)
  out.push(`Permission checks: ${detail.perm.ask} asked, ${detail.perm.deny} denied, ${detail.perm.wait} waiting now`)
  out.push(`Recent: ${detail.recent.map(r => (r.f ? `${r.t} ${r.f}` : r.t)).join(' | ') || 'none'}`)
  const r = detail.receipt
  out.push(r ? `Last turn: ${r.sec} s, ${r.tools} tool calls, ${r.edits} edits, ${r.asks} permission checks${r.aborted ? ', stopped early' : ''}` : 'Last turn: none yet')
  return out
}

// The Claude config folder: CLAUDE_CONFIG_DIR, else the home folder plus .claude. On win32 the
// home folder is USERPROFILE before HOME: under Git Bash HOME is an MSYS path (/c/Users/x) that
// a Windows program cannot use. env holds CLAUDE_CONFIG_DIR, USERPROFILE and HOME, as set.
export function configDir(env, platform) {
  const e = env ?? {}
  if (e.CLAUDE_CONFIG_DIR) return e.CLAUDE_CONFIG_DIR
  const win = platform === 'win32'
  const home = win ? e.USERPROFILE || e.HOME : e.HOME || e.USERPROFILE
  return home ? home + (win ? '\\' : '/') + '.claude' : ''
}

// The question-box check (rule questions-go-to-owner). A box stops the session until the owner
// answers, and running work goes on with no brake. The agent list is the host's; the background
// tasks (commands and workflows) are the ones this mod saw start and not yet end.
export const QUESTION_RULE = 'question-box-while-work'

// Python that writes one guard.log line through hooks/guard_core.py's own locked writer.
// argv: hooks folder, session id, decision, rule, matched.
export const GUARD_PY = [
  'import sys',
  'sys.path.append(sys.argv[1])',
  'import guard_core as g',
  'g.set_log_session(sys.argv[2])',
  'g.record("AskUserQuestion", sys.argv[3], sys.argv[4], sys.argv[5])',
].join('\n')

// Live agents in the host's list, the asking loop left out: it cannot wait on itself.
export function liveAgentCount(list, selfId) {
  return (Array.isArray(list) ? list : []).filter(a => a && LIVE.has(a.status) && !(selfId && a.id === selfId)).length
}

// The task id and status of a task notice, or null for any other text.
export function taskNotice(text) {
  const s = typeof text === 'string' ? text : ''
  const id = /<task-id>([^<\s]{1,200})<\/task-id>/.exec(s)
  const status = /<status>([^<\s]{1,40})<\/status>/.exec(s)
  return id ? { id: id[1], status: status ? status[1] : '' } : null
}

// The id a TaskStop call stopped: the output's task_id, else the input's task_id or deprecated shell_id,
// else the id in the output message "Successfully stopped task: <id>" (hooks/stall_watch.py STOPPED).
export function stoppedTaskId(out, input) {
  const pick = ...vals => vals.find(v => typeof v === 'string' && v)
  const msg = out && typeof out.message === 'string' ? /^\s*Successfully stopped task: (\S+)/.exec(out.message) : null
  return pick(out && out.task_id, input && input.task_id, input && input.shell_id, msg && msg[1])
}

const plural = (n, one) => `${n} ${one}${n === 1 ? '' : 's'}`

// A tool call that starts another session: the desktop start (hooks/guard.py SESSION_TOOL) or the
// cloud start. The guard is Python, so its name is copied here. Exact MCP names only: a lookalike
// such as create_session_tags or another server's start_session is not a start.
export const SESSION_START_TOOLS = ['mcp__ccd_session__start_session', 'mcp__claude-code-remote__create_session']
export const startsSession = tool => SESSION_START_TOOLS.includes(tool)

// A tool.call result that answered without error: a deny or an error result is no start.
export const answered = r => !!r && typeof r === 'object' && 'result' in r && !r.deny && r.isError !== true

// The count a start record (store key started:<id>, { n, at }) holds, 0 when it holds none.
export const startedCount = raw => (raw && typeof raw === 'object' ? num(raw.n, 0, 999) ?? 0 : 0)

// The refusal text, or null when nothing runs and no session was started. A started session may
// wait on this one for as long as this one lives.
export function questionRefusal(agents, tasks, started = 0) {
  if (!agents && !tasks && !started) return null
  const why = []
  if (agents || tasks) why.push([agents ? plural(agents, 'agent') : '', tasks ? plural(tasks, 'background task') : ''].filter(Boolean).join(' and ') + ' of this session still run')
  if (started) why.push(`this session started ${plural(started, 'session')}, which may wait on it`)
  return `Question box refused: ${why.join(', and ')}. A box stops the session until the owner answers. Ask in your reply instead; if the owner has not answered in 5 minutes, send the question to the waiting page's writer. Then keep working on what does not depend on the answer (rule questions-go-to-owner).`
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
    t = { inTurn: false, pending: new Set(), spawns: new Map(), recent: [], files: new Set(), ask: 0, deny: 0, turn: { tools: 0, edits: 0, asks: 0 }, receipt: null, git: { branch: '', dirty: null, unpushed: null, rt: null }, agents: [], ctx: null, repo: '' }
  }
  reset()
  const live = () => t.agents.filter(a => LIVE.has(a.status))
  return {
    reset,
    isIdle: () => !t.inTurn,
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
      if (SPAWN_TOOLS.has(tool)) { const k = spawnType(input); t.spawns.set(k, (t.spawns.get(k) ?? 0) + 1) }
      if (verdict === 'ask') { t.ask++; t.turn.asks++; t.pending.add(id) }
    },
    toolCall(id) { return t.pending.delete(id) },
    // g: parseStatus() output read at time `at`; null: the read failed, so the counts are unknown.
    setGit(g, at) { t.git = g ? { ...g, rt: at ?? null } : { branch: t.git.branch, dirty: null, unpushed: null, rt: null } },
    setAgents(list) { t.agents = (list ?? []).map(a => ({ type: a.type, status: a.status })) },
    setCtx(p) { t.ctx = p },
    setRepo(r) { t.repo = r },
    entry(now) {
      return buildEntry({ repo: t.repo, branch: t.git.branch, working: t.inTurn, ask: t.pending.size > 0, dirty: t.git.dirty, unpushed: t.git.unpushed, agents: live().length, spawns: t.spawns, ctx: t.ctx, rt: t.git.rt, now })
    },
    detail(now) {
      return buildDetail({ now, recent: t.recent, files: t.files.size, agents: live(), spawns: t.spawns, perm: { ask: t.ask, deny: t.deny, wait: t.pending.size }, receipt: t.receipt })
    },
  }
}

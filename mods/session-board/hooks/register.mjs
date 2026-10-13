// session-board: one entry per session in the shared store, a pane that reads them, and /safe-stop.
// Every host call sits in a try: a mod error never breaks a session. No model call anywhere.
// The host reads on(...) and $.noun.method(...) from source, so they are spelled literally,
// and helpers that take $ are top-level functions.
import {
  AGENTS_TIMEOUT_MS, GC_MS, GIT_BACKOFF_MAX_MS, GIT_SLOW_MS, GIT_TIMEOUT_MS, GRACE_MS, HEARTBEAT_MS, MAX_KEYS, MAX_PATH, MAX_POLLS, READ_BUDGET_MS,
  bandText, baseName, clean, cleanPath, detailLines, gitArgs, headerText, isSessionId, isUserOrigin, makeTracker,
  mergeRows, num, parseAgentsJson, parseStatus, readDetail, readEntry, rowText, safeStopMessage, safeStopPlan,
} from './lib.mjs'

const PANE = 'session-board'
const tracker = makeTracker()
let beat = null // the heartbeat timer
let sid = '' // this session's id, read again on every write (a /clear changes it)
let staleId = '' // after /clear: the id the host may still answer until the new one binds
let watching = false // /board ran and its pane is open: the heartbeat also refreshes the board
let polls = 0 // board refreshes on the heartbeat since the last /board
let gitBusy = false // a heartbeat git read is running
let gen = 0 // counts turn starts: a git read that began in an earlier count is dropped when it lands
let ended = false // the session ended: nothing is written after that
let gitEvery = HEARTBEAT_MS // idle git read interval: doubles after a slow read, back to 30 s on a quick one
let gitNextAt = 0
let lastDetail = '' // the detail record as last written, without its stamp
let board = null // { rows, band, note, now, hidden }
let view = { id: null, detail: null } // id null: all-sessions view

export function register(on) {
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    try { await startUp($) } catch (err) { note($, 'start failed: ' + (err && err.message)) } // never breaks a session
    return result
  })

  on('session.end', async ($, e, next) => {
    try {
      if (e.reason !== 'clear' && e.reason !== 'resume') ended = true // first: no write lands between the deletes and the flag
      if (isSessionId(e.sessionId)) {
        await $.store.delete('sess:' + e.sessionId)
        await $.store.delete('detail:' + e.sessionId)
      }
      if (e.reason === 'clear' || e.reason === 'resume') {
        // The process goes on under a new id and no session.start fires. The heartbeat keeps
        // running and reads the id again each beat. Until the new id binds the host still
        // answers the old one: write nothing for it.
        staleId = e.sessionId
        lastDetail = ''
        tracker.reset()
        await setRepo($)
        $.clock.after(1500, () => { void (async () => { await refreshGit($); await tick($) })() })
      } else {
        if (beat) beat.cancel()
        beat = null
        tracker.reset()
      }
    } catch (err) { note($, 'end failed: ' + (err && err.message)) } // a killed session leaves its entry: the 2-minute rule hides it
    return next(e)
  })

  on('turn.start', async ($, e, next) => {
    const result = await next(e)
    if (!e.agentId) {
      gen++
      tracker.turnStart()
      await soon($, flush($, false)) // the write runs on its own; the hook waits at most GRACE_MS
    }
    return result
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    try {
      if (!e.agentId) tracker.turnComplete(e)
      await soon($, refreshAll($, !e.agentId))
    } catch (err) { note($, 'turn end failed: ' + (err && err.message)) }
    return result
  })

  // Observes only. The verdict is the rest of the chain's: an "ask" is the waiting signal.
  on('tool.check', async ($, e, next) => {
    const result = await next(e)
    try {
      const verdict = result && typeof result === 'object' ? result.decision : undefined
      tracker.toolCheck({ tool: e.tool, input: e.input, id: e.tool_use_id, verdict })
      if (verdict === 'ask' && e.tool_use_id) await soon($, flush($, false))
    } catch { /* observing never changes the verdict */ }
    return result
  }).catch(($, e, next) => next(e)) // a failure here lets the tool run as the others decided

  // The host runs the permission check inside next(): the ask is answered once next() returns.
  on('tool.call', async ($, e, next) => {
    try {
      return await next(e)
    } finally {
      try { if (tracker.toolCall(e.tool_use_id)) await soon($, flush($, false)) } catch { /* ignore */ }
    }
  }).catch(($, e, next) => next(e))

  on('command.run', { command: 'board' }, async ($, e) => {
    try {
      view = { id: null, detail: null }
      polls = 0
      await loadBoard($)
      if (String(e.args).trim() === 'text') return { text: boardText() } // no pane: plain text, also for -p
      watching = true
      const opened = await $.ui.open({ id: PANE, title: 'Session board' })
      $.ui.invalidate('ui.render')
      return { text: opened && opened.isPlaced ? 'Session board opened.' : boardText() }
    } catch (err) {
      return { text: 'board: could not open: ' + clean(err && err.message, 100) }
    }
  })

  on('command.run', { command: 'safe-stop' }, async ($, e) => {
    try {
      if (!isUserOrigin(e.origin)) return { text: 'safe-stop: ignored. Only the person starts it, not a plugin, a peer, or a schedule.' }
      return { text: await safeStop($, e.args) }
    } catch (err) {
      return { text: 'safe-stop: failed, nothing sent: ' + clean(err && err.message, 100) }
    }
  })

  // The pane closed: stop refreshing the board on the heartbeat.
  on('ui.close', async ($, e, next) => {
    if (e && e.id === PANE) watching = false
    return next(e)
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'Pane', requestId: PANE }, ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    return paneTree($, e, Box, Text, Button)
  })
}

async function startUp($) {
  tracker.reset()
  staleId = ''
  ended = false
  lastDetail = ''
  await $.command.register({ name: 'board', description: 'Show every session on this machine: state, update-ready, agents', argumentHint: '[text]' })
  await $.command.register({ name: 'safe-stop', description: 'Reach a stopping point and write this session\'s handoff', argumentHint: '[plan]' })
  await setRepo($)
  if (beat) beat.cancel()
  beat = $.clock.every(HEARTBEAT_MS, () => { void tick($) })
  // The first reading and the sweep of killed sessions' entries share one wait of GRACE_MS.
  await soon($, Promise.all([refreshAll($, true), sweepAll($)]))
}

async function setRepo($) {
  try {
    const repo = await $.session.repo()
    tracker.setRepo(baseName(repo && repo.root ? repo.root : await $.session.cwd()))
  } catch { /* the repo name stays empty */ }
}

// A failure leaves one line in the debug log (claude --debug) and nothing else.
function note($, text) {
  try { $.ui.log('session-board: ' + clean(text, 160), { to: 'debug' }) } catch { /* nothing to do */ }
}

// One host read, at most READ_BUDGET_MS: a hung read never holds the rest.
function bounded($, p, ms = READ_BUDGET_MS) {
  return new Promise((resolve, reject) => {
    const timer = $.clock.after(ms, () => reject(new Error('timed out')))
    p.then(v => { timer.cancel(); resolve(v) }, err => { timer.cancel(); reject(err) })
  })
}

// Git (turn end only), agents, context, then the write. Never throws.
async function refreshAll($, withGit) {
  if (withGit) await refreshGit($)
  await Promise.all([refreshAgents($), refreshCtx($)])
  await flush($, true)
}

// The work (a refresh, a store write) runs on its own. A hook waits for it at most GRACE_MS, so
// a slow or hung read or write never holds a hook, and a quick one is done before the hook returns.
async function soon($, work) {
  const w = Promise.resolve(work).catch(() => {})
  let timer
  const grace = new Promise(resolve => { timer = $.clock.after(GRACE_MS, resolve) })
  await Promise.race([w, grace])
  timer.cancel()
}

// Heartbeat. While the session waits, it reads git again, so an idle session keeps a fresh
// reading. One read at a time: a beat that finds the last read still running skips it. This
// runs from a timer, never inside a hook. A failed read makes the counts unknown.
async function tick($) {
  try {
    if (tracker.isIdle() && !gitBusy && (gitEvery <= HEARTBEAT_MS || (await $.clock.now()) >= gitNextAt)) {
      gitBusy = true
      try {
        const started = await $.clock.now()
        const { slow } = await refreshGit($)
        // A read that needed over 5 s: wait twice as long before the next one, up to 5 minutes.
        // A quick read: back to every beat.
        gitEvery = slow ? Math.min(gitEvery * 2, GIT_BACKOFF_MAX_MS) : HEARTBEAT_MS
        gitNextAt = started + gitEvery
      } finally { gitBusy = false }
    }
    await refreshAll($, false)
    if (watching) {
      if (++polls > MAX_POLLS) watching = false // no /board call for 10 beats: stop polling
      else await refreshBoard($)
    }
  } catch { /* the next beat tries again */ }
}

async function ident($) {
  try { sid = await $.session.id() } catch { /* keep the last id */ }
  return sid
}

// The entry always; the detail record at turn end and on a beat, only when its content changed.
async function flush($, withDetail) {
  if (ended) return // the session ended: a refresh that lands now writes nothing
  try {
    const id = await ident($)
    if (ended) return
    if (!isSessionId(id)) return note($, 'no usable session id: entry not written')
    if (id === staleId) return // /clear ran and the new id is not bound yet
    staleId = ''
    const now = await $.clock.now()
    if (ended) return
    await $.store.set('sess:' + id, tracker.entry(now))
    if (withDetail && !ended) {
      const detail = tracker.detail(now)
      const key = id + JSON.stringify({ ...detail, at: 0 })
      if (key !== lastDetail) {
        await $.store.set('detail:' + id, detail)
        lastDetail = key
      }
    }
  } catch (err) { note($, 'store write failed: ' + (err && err.message)) } // the entry goes stale and hides: the safe failure
}

// One cheap git call per turn end and per idle beat. A failed or slow read makes the counts
// unknown. A read that began before the latest turn start is dropped when it lands: it may
// describe the tree from before the turn. Gives { slow }: the read took GIT_SLOW_MS or more.
async function refreshGit($) {
  const mine = gen
  let slow = false
  try {
    const started = await $.clock.now()
    const cwd = await bounded($, $.session.cwd())
    const r = await bounded($, $.process.run(gitArgs(), { cwd, timeoutMs: GIT_TIMEOUT_MS }), GIT_TIMEOUT_MS + 1000)
    const at = await $.clock.now()
    slow = at - started >= GIT_SLOW_MS
    if (mine !== gen) return { slow }
    if (r.exitCode !== 0) throw new Error('git exited ' + r.exitCode)
    tracker.setGit(parseStatus(r.stdout), at)
  } catch (err) {
    slow = slow || (err && err.message === 'timed out')
    if (mine === gen) {
      tracker.setGit(null)
      note($, 'git read failed: ' + (err && err.message))
    }
  }
  return { slow }
}

async function refreshAgents($) {
  try { tracker.setAgents(await bounded($, $.agent.list())) } catch (err) { note($, 'agent list read failed: ' + (err && err.message)) }
}

async function refreshCtx($) {
  try {
    const { context } = await bounded($, $.session.usage())
    if (context && context.window) tracker.setCtx(num(context.percent ?? ((context.tokens ?? 0) / context.window) * 100, 0, 100))
  } catch (err) { note($, 'usage read failed: ' + (err && err.message)) }
}

// Store entries by session id, newest key first, at most MAX_KEYS. total counts every entry key,
// read or not. old lists the ids of entries a day past their last beat: sweep() decides on those.
async function readEntries($) {
  const entries = new Map()
  const old = []
  const now = await $.clock.now()
  const keys = (await $.store.keys()).filter(k => typeof k === 'string' && k.startsWith('sess:'))
  const newest = keys.slice().reverse().slice(0, MAX_KEYS)
  await Promise.all(newest.map(async k => {
    try {
      const e = readEntry(await $.store.get(k))
      if (!e) return
      if (now - e.at > GC_MS) old.push(k.slice(5))
      else entries.set(k.slice(5), e)
    } catch { /* one bad key hides one row */ }
  }))
  return { entries, old, total: keys.length, read: newest.length }
}

// Removes the records of sessions a day past their last beat, except a session that
// `claude agents` lists as live. live: a Set of ids, or null when that list is unknown: then
// nothing is removed. Removing this session's own detail makes the next beat write it again.
async function sweep($, old, live) {
  if (!live) return
  for (const id of old) {
    if (live.has(id)) continue
    try {
      await $.store.delete('sess:' + id)
      await $.store.delete('detail:' + id)
      if (id === sid) lastDetail = ''
    } catch { /* the next sweep tries again */ }
  }
}

async function sweepAll($) {
  const [agents, store] = await Promise.all([readAgents($), readEntries($)])
  await sweep($, store.old, agents.ok ? new Set(agents.rows.map(r => r.id)) : null)
}

// One process call to `claude agents --json`. Never fatal: the note says what is missing.
async function readAgents($) {
  try {
    const r = await bounded($, $.process.run(['claude', 'agents', '--json'], { timeoutMs: AGENTS_TIMEOUT_MS }), AGENTS_TIMEOUT_MS + 1000)
    if (r.exitCode !== 0) return { rows: [], ok: false, note: 'claude agents failed: shown from the store only' }
    return { rows: parseAgentsJson(r.stdout), ok: true, note: '' }
  } catch {
    return { rows: [], ok: false, note: 'claude agents unavailable: shown from the store only' }
  }
}

async function loadBoard($) {
  const [agents, store, now] = await Promise.all([readAgents($), readEntries($), $.clock.now()])
  const rows = mergeRows(agents.rows, store.entries, now)
  board = { rows, band: bandText(rows), note: agents.note, now, hidden: store.total - store.read }
  await sweep($, store.old, agents.ok ? new Set(agents.rows.map(r => r.id)) : null)
  if (view.id) await loadDetail($, view.id, rows)
}

async function refreshBoard($) {
  try { await loadBoard($) } catch { /* keep the last board */ }
  $.ui.invalidate('ui.render')
}

async function loadDetail($, id, rows) {
  const now = await $.clock.now()
  let detail = null
  if (id === sid) detail = tracker.detail(now)
  else detail = readDetail(await $.store.get('detail:' + id))
  view = { id, detail, row: rows.find(r => r.id === id) ?? null }
}

function boardText() {
  if (!board) return 'No board yet.'
  const hidden = board.hidden > 0 ? `+${board.hidden} more entries not read` : ''
  return [board.band, headerText(80), ...board.rows.map(r => rowText(r, 80)), hidden, board.note].filter(Boolean).join('\n')
}

function paneTree($, e, Box, Text, Button) {
  const cols = e.bodyColumns ?? 80
  const line = (s, dim) => Text({ dimColor: !!dim, children: s })
  const refresh = Button({ key: 'refresh', label: 'Refresh', hotkey: 'r', onPress: () => { void refreshBoard($) } })
  if (!board) return Box({ flexDirection: 'column', children: [line('Loading...', true), refresh] })
  if (view.id) {
    const row = view.row ?? { id: view.id, repo: '?', branch: '', state: 'unknown', ask: false, ready: null, ctx: null, agents: null, detail: false }
    const back = Button({ key: 'back', label: 'Back to all sessions', hotkey: 'b', onPress: () => { view = { id: null, detail: null }; $.ui.invalidate('ui.render') } })
    return Box({ flexDirection: 'column', children: [...detailLines(row, view.detail, board.now).map(s => line(s)), back, refresh] })
  }
  const rows = board.rows.slice(0, 40).map((r, i) => Button({
    key: 'row-' + r.id,
    label: rowText(r, cols),
    ...(i < 9 ? { hotkey: String(i + 1) } : {}),
    onPress: () => { void openSession($, r.id) },
  }))
  const unseen = Math.max(0, board.rows.length - 40) + Math.max(0, board.hidden)
  const more = unseen > 0 ? [line(`+${unseen} more not shown`, true)] : []
  return Box({
    flexDirection: 'column',
    children: [line(board.band), line(headerText(cols), true), ...rows, ...more, ...(board.note ? [line(board.note, true)] : []), line('Press a number or a row to open one session.', true), refresh],
  })
}

async function openSession($, id) {
  try { await loadDetail($, id, board ? board.rows : []) } catch { view = { id, detail: null, row: null } }
  $.ui.invalidate('ui.render')
}

// Python that reuses the installed handoff hook's own path functions, so no second copy of
// the handoff path rules lives here. argv: hooks folder, session id, mode ("plan" makes no folder).
const HANDOFF_PY = [
  'import sys, json',
  'sys.path.append(sys.argv[1])',
  'import precompact_handoff as p',
  'if sys.argv[3] != "plan": p.ensure_handoff_dir(sys.argv[2])',
  'print(json.dumps({"handoff": p.handoff_path(sys.argv[2]), "prompt": p.prompt_path()}))',
].join('\n')

async function safeStop($, args) {
  const plan = String(args ?? '').trim() === 'plan'
  const id = await ident($)
  if (!isSessionId(id)) return safeStopPlan(null, ['this session id'])
  const home = (await $.env.get('HOME')) || (await $.env.get('USERPROFILE')) || ''
  const config = (await $.env.get('CLAUDE_CONFIG_DIR')) || home + '/.claude'
  const why = []
  let paths = null
  for (const py of ['python3', 'python']) {
    try {
      // -I: no current-folder or user-site imports. cwd is the config folder, never the session's:
      // a json.py or datetime.py in a repo must not run.
      const r = await $.process.run([py, '-I', '-B', '-c', HANDOFF_PY, config + '/hooks', id, plan ? 'plan' : 'run'], { cwd: config, timeoutMs: 10_000 })
      const o = r.exitCode === 0 ? JSON.parse(String(r.stdout).trim().split('\n').pop()) : null
      if (o && typeof o.handoff === 'string' && typeof o.prompt === 'string') { paths = o; break }
      why.push(`${py}: ${clean(String(r.stderr).trim().split('\n').pop(), 100) || 'no usable output'}`)
    } catch (err) {
      why.push(`${py}: ${clean(err && err.message, 100)}`)
    }
  }
  if (!paths) return safeStopPlan(null, [`python with ${config}/hooks/precompact_handoff.py (${why.join('; ')})`])
  for (const p of [paths.handoff, paths.prompt]) {
    // A path is shown and sent whole or not at all: never a cut path.
    if (Array.from(p).length > MAX_PATH) return `Safe stop: a path from the handoff hook is over ${MAX_PATH} characters. Nothing was sent.`
  }
  const handoff = cleanPath(paths.handoff)
  const text = safeStopMessage(cleanPath(paths.prompt), handoff)
  if (plan) return safeStopPlan(text, [])
  try {
    const sent = await $.prompt.submit({ text })
    if (sent && sent.drop) throw new Error('dropped: ' + clean(sent.drop, 80))
  } catch (err) {
    return 'Safe stop: could not send (' + clean(err && err.message, 100) + '). Nothing was sent.'
  }
  return 'Safe stop sent. The prompt is queued until this session is idle. It then rewrites its handoff at ' + handoff + '.'
}

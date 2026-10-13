// plain-diff: /plain-diff opens a pane. Each changed file gets a plain-English note above its diff.
// No always-on UI. Nothing is written to $.store. File text leaves only through $.model.complete.
//
// Note sources, in order: Claude's own turn text (free), one small-model call (max 5 at a time,
// shared by all runs), else "No note" with a short reason. A model error never blocks the pane.
// A secret file (by name or by content) is never sent to a model and never shown.
//
// The host reads on(...) and $.noun.method(...) from source, so they are spelled literally.

import { atom, read, update } from 'claude-code'
import {
  MAX_FILES,
  MAX_MODEL_CALLS,
  SECRET_NOTE,
  SHOW_LINES,
  TOO_LARGE_NOTE,
  applyNote,
  cacheKey,
  cutLines,
  diffBase,
  isSecretPath,
  isTooLargeForModel,
  looksSecret,
  makeLimiter,
  modelFailNote,
  modelPrompt,
  modelText,
  noteFromMessages,
  parseDiff,
  sanitizeForCode,
  trimNote,
} from './lib.mjs'

const PANE = 'plain-diff'
const EMPTY = { entries: [], files: 0, add: 0, del: 0, hiddenFiles: 0, error: '' }
const report = atom({ plugin: 'plain-diff', key: 'report' }, EMPTY)
const open = atom({ plugin: 'plain-diff', key: 'open' }, [])

// Notes kept for the session, by file path plus diff hash. Lost on a reload of the mod: fine.
const cache = new Map()
// One cap for every run. Overlapping runs share calls for the same file and diff.
const limiter = makeLimiter(MAX_MODEL_CALLS)

export function register(on) {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'plain-diff',
      description: 'Show the changed files with a plain-English note for each',
    })
    return next(e)
  })

  on('command.run', { command: 'plain-diff' }, async $ => {
    await update($, report, () => ({ ...EMPTY, error: 'Reading the changes...' }))
    await update($, open, () => [])
    await $.ui.open({ id: PANE, title: 'Plain diff' })

    const built = await build($)
    await update($, report, () => built.report)
    await fillFromModel($, built)
    return { text: built.report.error || `Plain diff: ${built.report.files} file(s).` }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Code, Markdown, Text } = $.ui.resolve(e)
    const r = await read($, report)
    const opened = await read($, open)
    if (r.error) return h(Text, { dimColor: true }, r.error)
    if (r.entries.length === 0) return h(Text, { dimColor: true }, 'No changes against HEAD.')

    const rows = [h(Text, { bold: true }, `${r.files} files changed, +${r.add} -${r.del}`)]
    if (r.hiddenFiles > 0) {
      rows.push(h(Text, { dimColor: true }, `Showing the first ${MAX_FILES} files. ${r.hiddenFiles} more not shown.`))
    }
    r.entries.forEach((f, i) => {
      rows.push(h(Box, { marginTop: 1 }, h(Text, { bold: true }, `${f.label}  `), h(Text, { dimColor: true }, `+${f.add} -${f.del}`)))
      if (f.source === 'secret') {
        rows.push(h(Text, { dimColor: true }, SECRET_NOTE))
        return
      }
      if (f.source === 'pending') rows.push(h(Text, { dimColor: true }, 'Writing a note...'))
      else if (f.source === 'none' || f.source === 'large') rows.push(h(Text, { dimColor: true }, f.note || 'No note'))
      else rows.push(h(Markdown, { text: f.note }))
      if (f.source === 'model') rows.push(h(Text, { dimColor: true }, '(summarised by a model)'))
      const long = f.lines > SHOW_LINES
      const isShown = !long || opened.includes(f.path)
      if (long) {
        rows.push(
          h(Button, {
            key: `f${i}`,
            label: isShown ? 'Hide diff' : `Show diff (${f.lines} lines)`,
            onPress: () => update($, open, l => (l.includes(f.path) ? l.filter(p => p !== f.path) : [...l, f.path])),
          }),
        )
      }
      if (isShown && f.diff) {
        rows.push(h(Code, { source: f.diff, format: 'diff', path: f.path }))
        if (f.isCut) rows.push(h(Text, { dimColor: true }, `Diff cut at ${f.diff.split('\n').length} of ${f.lines} lines.`))
      } else if (isShown) {
        rows.push(h(Text, { dimColor: true }, 'No line changes to show (binary file, rename, or mode change).'))
      }
    })
    return h(Box, { flexDirection: 'column' }, ...rows)
  })
}

const failed = text => ({ report: { ...EMPTY, error: text }, todo: [] })

// Read git, pair each file with a note from Claude's own turn text or the cache.
async function build($) {
  let hasHead = false
  let root = ''
  let out
  try {
    hasHead = (await $.process.run(['git', 'rev-parse', '--verify', '--quiet', 'HEAD'])).exitCode === 0
    const top = await $.process.run(['git', 'rev-parse', '--show-toplevel'])
    if (top.exitCode === 0) root = top.stdout.trim()
    out = await $.process.run(['git', '-c', 'core.quotepath=off', 'diff', diffBase(hasHead), '--no-color', '--no-ext-diff'])
  } catch (err) {
    return failed(`Could not run git: ${String(err && err.message ? err.message : err)}`)
  }
  if (out.exitCode !== 0) return failed(`git diff failed: ${out.stderr.trim().split('\n')[0]}`)

  const all = parseDiff(out.stdout)
  let messages = []
  try {
    messages = await $.session.messages()
  } catch {
    // No transcript: every file falls through to the model or to "No note".
  }
  const todo = []
  const entries = all.slice(0, MAX_FILES).map(f => {
    const entry = { path: f.path, label: f.label, key: '', add: f.add, del: f.del, lines: 0, diff: '', isCut: false, note: '', source: 'none' }
    // Privacy first: a secret file is not read further. No diff is kept, shown, or sent.
    if (isSecretPath(f.path) || isSecretPath(f.oldPath) || looksSecret(f.diff)) {
      return { ...entry, note: SECRET_NOTE, source: 'secret' }
    }
    const clean = sanitizeForCode(f.diff)
    const cut = cutLines(clean)
    entry.diff = cut.text
    entry.isCut = cut.isCut
    entry.lines = cut.lines
    entry.key = cacheKey(f.path, clean)
    const own = noteFromMessages(messages, root, f.path)
    if (own) {
      entry.note = own
      entry.source = 'turn'
    } else if (cache.has(entry.key)) {
      entry.note = cache.get(entry.key)
      entry.source = 'model'
    } else if (clean && isTooLargeForModel(clean)) {
      entry.note = TOO_LARGE_NOTE
      entry.source = 'large'
    } else if (clean && todo.length < MAX_MODEL_CALLS) {
      entry.source = 'pending'
      todo.push({ path: f.path, key: entry.key, diff: clean })
    } else if (clean) {
      entry.note = 'No note: model limit reached'
    }
    return entry
  })
  const rep = {
    entries,
    files: all.length,
    add: all.reduce((n, f) => n + f.add, 0),
    del: all.reduce((n, f) => n + f.del, 0),
    hiddenFiles: Math.max(0, all.length - MAX_FILES),
    error: '',
  }
  return { report: rep, todo }
}

// One small-model call per file with no note. The shared limiter caps the calls.
// A late answer lands only on the entry that still holds its key. Any failure leaves "No note: reason".
async function fillFromModel($, built) {
  await Promise.all(
    built.todo.map(async t => {
      let note = ''
      let fail = ''
      try {
        const r = await limiter.run(t.key, () => $.model.complete({ model: 'haiku', prompt: modelPrompt(t.path, t.diff), timeoutMs: 20000 }))
        if (r === null) fail = 'No note: model limit reached'
        else {
          note = trimNote(modelText(r))
          if (!note) fail = modelFailNote(r)
        }
      } catch (err) {
        fail = modelFailNote(err)
      }
      if (note) cache.set(t.key, note)
      await update($, report, rep => ({
        ...rep,
        entries: applyNote(rep.entries, t.key, note || fail, note ? 'model' : 'none'),
      }))
    }),
  )
}

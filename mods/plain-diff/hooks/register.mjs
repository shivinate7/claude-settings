// plain-diff: /plain-diff opens a pane. Each changed file gets a plain-English note above its diff.
// No always-on UI. Nothing is written to $.store. File text leaves only through $.model.complete.
//
// Note sources, in order: Claude's own turn text (free), one small-model call (max 5 per run),
// else "No note". A model error never blocks the pane.
//
// The host reads on(...) and $.noun.method(...) from source, so they are spelled literally.

import { atom, read, update } from 'claude-code'
import {
  MAX_FILES,
  MAX_MODEL_CALLS,
  SHOW_LINES,
  cacheKey,
  cutLines,
  modelPrompt,
  modelText,
  noteFromMessages,
  parseDiff,
  trimNote,
} from './lib.mjs'

const PANE = 'plain-diff'
const EMPTY = { entries: [], files: 0, add: 0, del: 0, hiddenFiles: 0, error: '' }
const report = atom({ plugin: 'plain-diff', key: 'report' }, EMPTY)
const open = atom({ plugin: 'plain-diff', key: 'open' }, [])

// Notes kept for the session, by file path plus diff hash. Lost on a reload of the mod: fine.
const cache = new Map()

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

    const rows = [
      h(Text, { bold: true }, `${r.files} files changed, +${r.add} -${r.del}`),
    ]
    if (r.hiddenFiles > 0) {
      rows.push(h(Text, { dimColor: true }, `Showing the first ${MAX_FILES} files. ${r.hiddenFiles} more not shown.`))
    }
    r.entries.forEach((f, i) => {
      const long = f.lines > SHOW_LINES
      const isShown = !long || opened.includes(f.path)
      rows.push(h(Box, { marginTop: 1 }, h(Text, { bold: true }, `${f.path}  `), h(Text, { dimColor: true }, `+${f.add} -${f.del}`)))
      if (f.source === 'pending') rows.push(h(Text, { dimColor: true }, 'Writing a note...'))
      else if (f.source === 'none') rows.push(h(Text, { dimColor: true }, 'No note'))
      else rows.push(h(Markdown, { text: f.note }))
      if (f.source === 'model') rows.push(h(Text, { dimColor: true }, '(summarised by a model)'))
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
        rows.push(h(Text, { dimColor: true }, 'No text diff (binary file or mode change).'))
      }
    })
    return h(Box, { flexDirection: 'column' }, ...rows)
  })
}

// Read git, pair each file with a note from Claude's own turn text or the cache.
async function build($) {
  let out
  try {
    out = await $.process.run(['git', '-c', 'core.quotepath=off', 'diff', 'HEAD', '--no-color', '--no-ext-diff'])
  } catch (err) {
    return { report: { ...EMPTY, error: `Could not run git: ${String(err && err.message ? err.message : err)}` }, todo: [] }
  }
  if (out.exitCode !== 0) {
    return { report: { ...EMPTY, error: `git diff failed: ${out.stderr.trim().split('\n')[0]}` }, todo: [] }
  }
  const all = parseDiff(out.stdout)
  let messages = []
  try {
    messages = await $.session.messages()
  } catch {
    // No transcript: every file falls through to the model or to "No note".
  }
  const todo = []
  const entries = all.slice(0, MAX_FILES).map(f => {
    const cut = cutLines(f.diff)
    const entry = { path: f.path, add: f.add, del: f.del, lines: cut.lines, diff: cut.text, isCut: cut.isCut, note: '', source: 'none' }
    const key = cacheKey(f.path, f.diff)
    const own = noteFromMessages(messages, f.path)
    if (own) {
      entry.note = own
      entry.source = 'turn'
    } else if (cache.has(key)) {
      entry.note = cache.get(key)
      entry.source = 'model'
    } else if (f.diff && todo.length < MAX_MODEL_CALLS) {
      entry.source = 'pending'
      todo.push({ path: f.path, key, diff: f.diff })
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

// One small-model call per file with no note, at most MAX_MODEL_CALLS. Any failure leaves "No note".
async function fillFromModel($, built) {
  await Promise.all(
    built.todo.map(async t => {
      let note = ''
      try {
        const r = await $.model.complete({ model: 'haiku', prompt: modelPrompt(t.path, t.diff), timeoutMs: 20000 })
        note = trimNote(modelText(r))
      } catch {
        // A model error never blocks the pane.
      }
      if (note) cache.set(t.key, note)
      await update($, report, rep => ({
        ...rep,
        entries: rep.entries.map(f =>
          f.path === t.path && f.source === 'pending'
            ? { ...f, note, source: note ? 'model' : 'none' }
            : f,
        ),
      }))
    }),
  )
}

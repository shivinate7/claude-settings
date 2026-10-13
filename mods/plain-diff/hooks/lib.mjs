// Pure helpers for plain-diff. No host calls here, so `node check.mjs` can test them.

export const MAX_FILES = 30
export const MAX_MODEL_CALLS = 5
export const MODEL_DIFF_CHARS = 6000
export const SHOW_LINES = 40
export const CUT_LINES = 400
const EDIT_TOOLS = new Set(['Edit', 'Write', 'MultiEdit', 'NotebookEdit'])

// Split `git diff` output into files. Keeps hunks only (from the first @@).
export function parseDiff(text) {
  const files = []
  for (const part of String(text).split(/^diff --git /m).slice(1)) {
    const head = part.split('\n', 1)[0]
    const m = head.match(/^"?a\/(.*?)"? "?b\/(.*?)"?$/)
    const path = m ? m[2] : head
    const at = part.search(/^@@ /m)
    const diff = at < 0 ? '' : part.slice(at).replace(/\n+$/, '')
    let add = 0
    let del = 0
    for (const l of diff.split('\n')) {
      if (l.startsWith('+')) add++
      else if (l.startsWith('-')) del++
    }
    files.push({ path, add, del, diff, isBinary: at < 0 && /^Binary files /m.test(part) })
  }
  return files
}

// Cut a diff at a line boundary. A diff cut mid-hunk does not parse, so cut by whole lines.
export function cutLines(diff, max = CUT_LINES) {
  const lines = diff.split('\n')
  return lines.length <= max
    ? { text: diff, isCut: false, lines: lines.length }
    : { text: lines.slice(0, max).join('\n'), isCut: true, lines: lines.length }
}

// Cut text to about `max` characters, at a line boundary.
export function clipChars(text, max = MODEL_DIFF_CHARS) {
  if (text.length <= max) return text
  const cut = text.slice(0, max)
  return cut.slice(0, Math.max(cut.lastIndexOf('\n'), 1)) + '\n[cut]'
}

// FNV-1a, 32 bit. Enough for a cache key. Not for security.
export function hash(text) {
  let h = 0x811c9dc5
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return h.toString(16)
}
export const cacheKey = (path, diff) => `${path}\n${hash(diff)}`

// Plain text from Claude's turn text: no code fences, no markup, 2 sentences, 300 chars.
export function trimNote(text) {
  const plain = String(text)
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`/g, '')
    .replace(/\*\*|__/g, '')
    .replace(/^\s*(#+|[-*>]|\d+\.)\s+/gm, '')
    .replace(/\s+/g, ' ')
    .trim()
  const out = plain.split(/(?<=[.!?])\s+/).slice(0, 2).join(' ')
  return out.length > 300 ? out.slice(0, 297).replace(/\s+\S*$/, '') + '...' : out
}

const norm = p => String(p).replace(/\\/g, '/').toLowerCase()

// Claude's own words about one file: the text of the last assistant turn that edited it.
// `messages` is $.session.messages(): rows of { role, text, toolUses, toolResults? }.
export function noteFromMessages(messages, relPath) {
  const rel = norm(relPath)
  let found = ''
  messages.forEach((m, i) => {
    if (m.role !== 'assistant') return
    const hit = (m.toolUses || []).some(
      u =>
        EDIT_TOOLS.has(u.tool) &&
        [u.input?.file_path, u.input?.notebook_path, u.input?.path].some(p => {
          if (typeof p !== 'string') return false
          const abs = norm(p)
          return abs === rel || abs.endsWith('/' + rel)
        }),
    )
    if (!hit) return
    // The words may sit in this row or in an earlier row of the same turn.
    for (let j = i; j >= 0; j--) {
      const r = messages[j]
      if (r.role === 'user' && !(r.toolResults && r.toolResults.length)) break
      if (r.role === 'assistant' && r.text && r.text.trim()) {
        const note = trimNote(r.text)
        if (note) found = note
        break
      }
    }
  })
  return found
}

// $.model.complete resolves { isAnswered, text } in this build; the older types said a string.
export function modelText(r) {
  if (typeof r === 'string') return r
  if (r && r.isAnswered === true && typeof r.text === 'string') return r.text
  return ''
}

export function modelPrompt(path, diff) {
  return [
    'You explain a code change to a person who does not read code.',
    'Write 1 or 2 short sentences in plain English: what changed, and why it matters.',
    'Use everyday words. No jargon. No contractions. Do not quote code. Reply with the note only.',
    `File: ${path}`,
    'Diff:',
    clipChars(diff),
  ].join('\n')
}

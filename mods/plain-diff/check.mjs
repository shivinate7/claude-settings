// Self-check for the pure helpers. Run: node mods/plain-diff/check.mjs  (stdlib only)
import assert from 'node:assert/strict'
import { cacheKey, clipChars, cutLines, modelText, noteFromMessages, parseDiff, trimNote } from './hooks/lib.mjs'

// parseDiff: two files, counts, binary, header stripped
const raw = `diff --git a/a.txt b/a.txt
index 111..222 100644
--- a/a.txt
+++ b/a.txt
@@ -1,2 +1,2 @@
-old
+new
 same
diff --git a/img.png b/img.png
index 1..2 100644
Binary files a/img.png and b/img.png differ
diff --git a/x/old.js b/x/new.js
similarity index 90%
rename from x/old.js
rename to x/new.js
@@ -1 +1,2 @@
 a
+b
`
const f = parseDiff(raw)
assert.equal(f.length, 3)
assert.deepEqual([f[0].path, f[0].add, f[0].del], ['a.txt', 1, 1])
assert.ok(f[0].diff.startsWith('@@') && !f[0].diff.includes('index 111'))
assert.equal(f[1].isBinary, true)
assert.equal(f[1].diff, '')
assert.deepEqual([f[2].path, f[2].add, f[2].del], ['x/new.js', 1, 0])
assert.deepEqual(parseDiff(''), [])

// trimNote: strips markup, keeps 2 sentences, caps length
assert.equal(trimNote('**Fixed** the `login` bug. It crashed. Third one. Fourth.'), 'Fixed the login bug. It crashed.')
assert.equal(trimNote('```js\nx\n```\nDone.'), 'Done.')
assert.ok(trimNote('word '.repeat(200)).length <= 300)

// noteFromMessages: matches by path, abs or rel, either slash; last edit wins; words from an earlier row of the same turn
const edit = (tool, p) => ({ role: 'assistant', text: '', toolUses: [{ tool, input: { file_path: p } }] })
const msgs = [
  { role: 'user', text: 'fix it', toolUses: [] },
  { role: 'assistant', text: 'I will fix the login check.', toolUses: [] },
  edit('Edit', 'C:\\repo\\src\\login.js'),
  { role: 'user', text: '', toolUses: [], toolResults: [{ tool_use_id: '1', text: 'ok' }] },
  { role: 'assistant', text: 'Then I will tidy the readme.', toolUses: [{ tool: 'Write', input: { file_path: '/repo/README.md' } }] },
  { role: 'user', text: 'thanks', toolUses: [] },
  edit('Edit', '/repo/other.js'), // no words in its turn
]
assert.equal(noteFromMessages(msgs, 'src/login.js'), 'I will fix the login check.')
assert.equal(noteFromMessages(msgs, 'README.md'), 'Then I will tidy the readme.')
assert.equal(noteFromMessages(msgs, 'other.js'), '')
assert.equal(noteFromMessages(msgs, 'login.js'), 'I will fix the login check.') // basename of a nested path still ends-with
assert.equal(noteFromMessages(msgs, 'gin.js'), '') // no partial-name match
assert.equal(noteFromMessages([], 'a'), '')

// truncation
assert.equal(clipChars('abc', 10), 'abc')
const clipped = clipChars('line\n'.repeat(5000))
assert.ok(clipped.length < 6100 && clipped.endsWith('[cut]'))
const c = cutLines('x\n'.repeat(999).trimEnd(), 400)
assert.deepEqual([c.isCut, c.lines, c.text.split('\n').length], [true, 999, 400])
assert.equal(cutLines('a\nb').isCut, false)

// cache key: same input same key; a changed diff or path changes it
assert.equal(cacheKey('a', 'd'), cacheKey('a', 'd'))
assert.notEqual(cacheKey('a', 'd'), cacheKey('a', 'e'))
assert.notEqual(cacheKey('a', 'd'), cacheKey('b', 'd'))

// model result: object, string, failure
assert.equal(modelText({ isAnswered: true, text: 'hi', usage: {} }), 'hi')
assert.equal(modelText('hi'), 'hi')
assert.equal(modelText({ isAnswered: false, reason: 'api-error' }), '')
assert.equal(modelText(undefined), '')

console.log('plain-diff check: all pass')

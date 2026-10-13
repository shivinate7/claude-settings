// Review round 1 (PR 375) pins for plain-diff. Run: node mods/plain-diff/plain-diff.test.mjs  (stdlib only)
// Seams the builder must add. Names fixed here.
//   hooks/lib.mjs
//     isSecretPath(path) -> boolean
//     looksSecret(diffText) -> boolean
//     sanitizeForCode(text) -> string           removes C0 controls except \t \n \r
//     makeLimiter(max) -> { run(key, call) }    run() resolves call()'s value, or null when the cap refuses.
//                                               A key already in flight shares its call. The budget counts
//                                               calls while any call is in flight; it resets when none is.
//     isTooLargeForModel(diff) -> boolean       true when any one line is over MODEL_DIFF_CHARS / 2
//     TOO_LARGE_NOTE = 'No note: change too large'
//     modelFailNote(r) -> string                r: model result object or Error. Returns 'No note: <reason>'.
//     applyNote(entries, key, note) -> entries  sets the note only where entry.key === key and source is 'pending'
//     EMPTY_TREE = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
//     diffBase(hasHead) -> 'HEAD' | EMPTY_TREE
//     noteFromMessages(messages, repoRoot, relPath)   repoRoot is the new 2nd argument
//     parseDiff(text): each file gains `label` ('old.txt -> new.txt' for a pure rename, else the path)
//   hooks/register.mjs, driven through its real command.run and ui.render handlers:
//     entries carry `key`; sources 'secret' and 'large' are added
//     a secret file shows the row 'Skipped: secret file' and no Code block
//     one module-level limiter shared by all runs; git base = diffBase(rev-parse HEAD succeeds)
// Decisions pinned here: match is case-sensitive; drive letter and slashes normalised;
// a trailing slash on repoRoot is ignored; docs/secrets-policy.md is not flagged by name.
import assert from 'node:assert/strict'
import { register as registerHooks } from 'node:module'
import * as lib from './hooks/lib.mjs'

const r1 = []
async function test(name, fn) {
  try {
    await fn()
    r1.push(`PASS ${name}`)
  } catch (e) {
    r1.push(`FAIL ${name}: ${String(e && e.message ? e.message : e).split('\n')[0]}`)
  }
}
const need = name => {
  if (!(name in lib)) throw new Error(`missing export ${name}`)
  return lib[name]
}

// Secret fixtures are built at run time, so no secret-looking literal sits contiguous in the source.
const AWS = 'AK' + 'IA' + 'ABCDEFGHIJKLMNOP' // AKIA + 16 chars
const GHP = 'gh' + 'p_' + 'A'.repeat(36)
const SK = 'sk-' + 'ant-' + 'api03-' + 'x'.repeat(40)
const XOXB = 'xo' + 'xb-' + '1111111111-2222222222-' + 'abcdefghijklmnop'
const PEM = '-----BEGIN ' + 'PRIVATE KEY-----'
const OSSH = '-----BEGIN ' + 'OPENSSH PRIVATE KEY-----'
const EMPTY_TREE = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
const fileDiff = (path, added) =>
  `diff --git a/${path} b/${path}\nindex 1..2 100644\n--- a/${path}\n+++ b/${path}\n@@ -1 +1 @@\n-old\n+${added}\n`
const count = (s, sub) => s.split(sub).length - 1

// F1 privacy: pure
await test('F1 isSecretPath flags secret file names', () => {
  const f = need('isSecretPath')
  for (const p of [
    '.env', '.env.local', '.env.production', 'config/.env', 'config\\.env', 'deploy/key.pem',
    'certs/server.key', 'id_rsa', 'home/id_ed25519', 'credentials.json', '.npmrc', '.netrc',
    'secrets.json', 'secrets.md', 'cert.p12', 'bundle.pfx', '.aws/credentials', 'service-account-prod.json',
  ]) assert.equal(f(p), true, p)
})
await test('F1 isSecretPath passes plain names; docs/secrets-policy.md is not flagged by name', () => {
  const f = need('isSecretPath')
  for (const p of ['environment.md', 'keyboard.ts', 'docs/secrets-policy.md', 'src/key.ts', 'README.md', 'config/env.js']) {
    assert.equal(f(p), false, p)
  }
})
await test('F1 looksSecret flags key material under an innocent file name', () => {
  const f = need('looksSecret')
  for (const body of [PEM, OSSH, AWS, GHP, SK, XOXB]) {
    assert.equal(f(fileDiff('notes.txt', body)), true, body.slice(0, 24))
  }
})
await test('F1 looksSecret: a key after // in a string, or inside a template literal, is still flagged', () => {
  const f = need('looksSecret')
  assert.equal(f(`+const u = "http://a.example/"; const id = "${AWS}"`), true)
  assert.equal(f(`+const s = "/* not a comment"; const k = "${GHP}"`), true)
  assert.equal(f(['+const t = `/* open', `+${PEM}`, '+`;'].join('\n')), true)
})
await test('F1 looksSecret: a lone quote in text, plain code and a short AKIA are not flagged', () => {
  const f = need('looksSecret')
  assert.equal(f("+<p>Don't</p>"), false)
  assert.equal(f('+const x = "it\'s"'), false)
  assert.equal(f('+const keyboard = 1'), false)
  assert.equal(f('+const id = "AKIASHORT"'), false)
})

// F2 wrong note: pure
const nfm = (...a) => need('noteFromMessages')(...a)
const editedAt = (file_path, text) => [
  { role: 'user', text: 'go', toolUses: [] },
  { role: 'assistant', text, toolUses: [{ tool: 'Edit', input: { file_path } }] },
]
await test('F2 a repo-relative edit gets its note; the root index.js does not', () => {
  const m = editedAt('/repo/src/index.js', 'I fixed the parser.')
  assert.equal(nfm(m, '/repo', 'src/index.js'), 'I fixed the parser.')
  assert.equal(nfm(m, '/repo', 'index.js'), '')
})
await test("F2 another repo's README.md does not note this repo's README.md", () => {
  const m = editedAt('/other-repo/README.md', 'I rewrote the readme.')
  assert.equal(nfm(m, '/other-repo', 'README.md'), 'I rewrote the readme.')
  assert.equal(nfm(m, '/repo', 'README.md'), '')
})
await test('F2 backslash paths and drive-letter case still match the right file', () => {
  const m = editedAt('C:\\repo\\src\\login.js', 'I fixed the login check.')
  assert.equal(nfm(m, 'c:/repo', 'src/login.js'), 'I fixed the login check.')
  assert.equal(nfm(m, 'C:\\repo', 'src/login.js'), 'I fixed the login check.')
  assert.equal(nfm(m, 'c:/repo', 'login.js'), '')
})
await test('F2 match is case-sensitive (README.md vs Readme.md); trailing slash on repoRoot ignored', () => {
  const m = editedAt('/repo/README.md', 'I tidied the readme.')
  assert.equal(nfm(m, '/repo', 'README.md'), 'I tidied the readme.')
  assert.equal(nfm(m, '/repo/', 'README.md'), 'I tidied the readme.')
  assert.equal(nfm(m, '/repo', 'Readme.md'), '')
})

// F3 control characters: pure
await test('F3 sanitizeForCode drops ESC and NUL, keeps tab, newline, CR', () => {
  assert.equal(need('sanitizeForCode')('a\x1b[31mred\x00\tb\r\nc'), 'a[31mred\tb\r\nc')
})
await test('F3 sanitizeForCode: ESC inside a quoted string keeps the quotes and the text', () => {
  assert.equal(need('sanitizeForCode')('const s = "\x1bhi"; // Don\'t\x1b'), 'const s = "hi"; // Don\'t')
})

// F4 stale note: pure
await test('F4 applyNote sets a note only on the pending entry with the same key', () => {
  const a = need('applyNote')
  const entries = [{ path: 'a.js', key: 'K2', source: 'pending', note: '' }]
  assert.deepEqual(a(entries, 'K1', 'Note one.'), entries)
  assert.equal(a(entries, 'K2', 'Note two.')[0].note, 'Note two.')
})

// F5 huge line: pure
await test('F5 isTooLargeForModel: one huge line is too large; many short lines are not', () => {
  const t = need('isTooLargeForModel')
  assert.equal(t('@@ -1 +1 @@\n+' + 'x'.repeat(5995)), true)
  const many = '@@ -0,0 +1,700 @@\n' + Array.from({ length: 700 }, (_, i) => `+line ${i}`).join('\n')
  assert.ok(many.length > 6000)
  assert.equal(t(many), false)
})
await test('F5 TOO_LARGE_NOTE is the row text', () => {
  assert.equal(lib.TOO_LARGE_NOTE, 'No note: change too large')
})

// F6 markup in notes: pure
await test('F6 trimNote: a markdown link becomes its label and plain URL, with no link syntax', () => {
  const o = lib.trimNote('[click](http://evil.example) now.')
  assert.ok(o.includes('click') && o.includes('evil.example'), o)
  assert.ok(!/[[\]]/.test(o) && !o.includes(']('), o)
})
await test('F6 trimNote: HTML is escaped, no raw angle brackets', () => {
  const o = lib.trimNote('<img src=x onerror=alert(1)>Fixed it.')
  assert.ok(!/[<>]/.test(o), o)
  assert.ok(o.includes('&lt;img'), o)
})
await test('F6 trimNote: table pipes are removed', () => {
  assert.ok(!lib.trimNote('| a | b |\n|---|---|\nDone.').includes('|'))
})
await test("F6 trimNote keeps an apostrophe intact (guard, green on head)", () => {
  assert.equal(lib.trimNote("Don't panic."), "Don't panic.")
})

// F7 shared cap: pure
await test('F7 makeLimiter: cap while in flight, same key shares a call, budget resets when idle', async () => {
  const L = need('makeLimiter')(2)
  let n = 0
  const slowCall = v => () => {
    n++
    return new Promise(r => setTimeout(() => r(v), 5))
  }
  const pa = L.run('a', slowCall('A'))
  const pb = L.run('b', slowCall('B'))
  const pc = L.run('c', slowCall('C')) // refused: 2 already in flight
  const pa2 = L.run('a', slowCall('A2')) // in flight: shares the call
  assert.equal(await pc, null)
  assert.equal(await pa, 'A')
  assert.equal(await pa2, 'A')
  assert.equal(await pb, 'B')
  assert.equal(n, 2)
  assert.equal(await L.run('d', slowCall('D')), 'D') // idle again: fresh budget
  assert.equal(n, 3)
})

// F8 parse, base, failure text: pure
await test('F8 parseDiff: a directory with a space gives path x b/y.txt', () => {
  const raw =
    'diff --git a/x b/y.txt b/x b/y.txt\nindex 1..2 100644\n--- a/x b/y.txt\n+++ b/x b/y.txt\n@@ -1 +1 @@\n-a\n+b\n'
  assert.equal(lib.parseDiff(raw)[0].path, 'x b/y.txt')
})
await test('F8 parseDiff: a pure rename has label old.txt -> new.txt and is not binary', () => {
  const raw = 'diff --git a/old.txt b/new.txt\nsimilarity index 100%\nrename from old.txt\nrename to new.txt\n'
  const f = lib.parseDiff(raw)[0]
  assert.equal(f.label, 'old.txt -> new.txt')
  assert.equal(f.isBinary, false)
  assert.equal(f.path, 'new.txt')
})
await test('F8 diffBase: no commits diffs against the empty tree; with HEAD it is HEAD', () => {
  assert.equal(need('diffBase')(false), EMPTY_TREE)
  assert.equal(need('diffBase')(true), 'HEAD')
  assert.equal(lib.EMPTY_TREE, EMPTY_TREE)
})
await test("F8 modelFailNote: 'No note: <reason>' for a result object and for an Error", () => {
  const m = need('modelFailNote')
  assert.equal(m({ isAnswered: false, reason: 'api-error' }), 'No note: api-error')
  assert.equal(m(new Error('timed out')), 'No note: timed out')
})

// register harness: the real register.mjs; host module 'claude-code' is stubbed by an inline data: hook
const STUB = `
const store = globalThis.__plainDiffStore ??= new Map()
const id = a => JSON.stringify(a)
export const atom = (key, init) => ({ id: id(key), init })
export const read = async (_$, a) => (store.has(a.id) ? store.get(a.id) : a.init)
export const update = async (_$, a, fn) => { store.set(a.id, fn(await read(_$, a))) }
`
const HOOK = `
const STUB_URL = ${JSON.stringify('data:text/javascript,' + encodeURIComponent(STUB))}
export async function resolve(specifier, context, nextResolve) {
  if (specifier === 'claude-code') return { url: STUB_URL, shortCircuit: true }
  return nextResolve(specifier, context)
}
`
registerHooks('data:text/javascript,' + encodeURIComponent(HOOK), import.meta.url)
globalThis.h = (type, props, ...children) => ({ type, props: props ?? {}, children })
const plugin = await import('./hooks/register.mjs')

const quick = async () => ({ isAnswered: true, text: 'A plain note.' })
async function gitRun(argv, st) {
  const ok = stdout => ({ exitCode: 0, stdout, stderr: '' })
  if (argv.includes('rev-parse')) {
    return st.hasHead ? ok('HEAD\n') : { exitCode: 128, stdout: '', stderr: 'fatal: Needed a single revision\n' }
  }
  if (argv.includes('diff')) {
    if (argv.includes('HEAD') && !st.hasHead) {
      return { exitCode: 128, stdout: '', stderr: "fatal: ambiguous argument 'HEAD': unknown revision\n" }
    }
    return ok(st.diff)
  }
  return ok('')
}
function allText(tree) {
  const got = []
  const go = n => {
    if (n == null || typeof n === 'boolean') return
    if (typeof n === 'string' || typeof n === 'number') return void got.push(String(n))
    if (Array.isArray(n)) return void n.forEach(go)
    if (n.props && typeof n.props.text === 'string') got.push(n.props.text)
    go(n.children)
  }
  go(tree)
  return got.join('\n')
}
function codeSources(tree) {
  const got = []
  const go = n => {
    if (n == null || typeof n !== 'object') return
    if (Array.isArray(n)) return void n.forEach(go)
    if (n.type === 'Code') got.push(n.props.source)
    go(n.children)
  }
  go(tree)
  return got
}
function host(init = {}) {
  const st = { diff: '', hasHead: true, messages: [], model: quick, ...init }
  const calls = []
  const $ = {
    command: { register: async () => {} },
    ui: {
      open: async () => {},
      resolve: () => ({ Box: 'Box', Button: 'Button', Code: 'Code', Markdown: 'Markdown', Text: 'Text' }),
    },
    process: { run: async argv => gitRun(argv, st) },
    session: { messages: async () => st.messages },
    model: {
      complete: async req => {
        calls.push(req)
        return st.model(req)
      },
    },
  }
  const hs = []
  plugin.register((event, a, b) => hs.push({ event, fn: typeof a === 'function' ? a : b }))
  const find = ev => hs.find(x => x.event === ev).fn
  const pane = () => find('ui.render')($, { component: 'Pane', requestId: 'plain-diff' })
  return {
    st,
    calls,
    run: () => find('command.run')($),
    rows: async () => allText(await pane()),
    codes: async () => codeSources(await pane()),
  }
}
const deferred = () => {
  let resolve
  const promise = new Promise(r => (resolve = r))
  return { promise, resolve }
}
const slow = async () => {
  await new Promise(r => setTimeout(r, 30))
  return { isAnswered: true, text: 'A note.' }
}

// F1 privacy: register
await test('F1 register: secret files make no model call; rows say Skipped: secret file; no Code block for them', async () => {
  const t = host({
    diff: fileDiff('.env', 'TOKEN=abc') + fileDiff('config/.env', 'X=1') + fileDiff('notes.txt', AWS) + fileDiff('src/app.js', 'const a = 1'),
  })
  await t.run()
  assert.equal(t.calls.length, 1, `calls: ${t.calls.map(c => c.prompt.split('\n')[0]).join(' | ')}`)
  assert.ok(t.calls[0].prompt.includes('File: src/app.js'))
  const sent = JSON.stringify(t.calls)
  for (const s of ['TOKEN=abc', 'X=1', AWS]) assert.ok(!sent.includes(s), `leaked ${s} to model`)
  assert.equal(count(await t.rows(), 'Skipped: secret file'), 3)
  const shown = (await t.codes()).join('\n')
  for (const s of ['TOKEN=abc', 'X=1', AWS]) assert.ok(!shown.includes(s), `secret diff block shown: ${s}`)
})

// F3 control characters: register
await test('F3 register: the Code row holds no ESC or NUL, keeps tab', async () => {
  const t = host({ diff: fileDiff('ctl.txt', 'a\x1b[1m\x00\tb') })
  await t.run()
  const src = await t.codes()
  assert.equal(src.length, 1)
  assert.ok(!/[\x00\x1b]/.test(src[0]), JSON.stringify(src[0]))
  assert.ok(src[0].includes('\t'))
})

// F4 stale note: register. Order: v1 starts, v2 starts, v1 answers, v2 answers.
await test('F4 register: a late answer for version one never shows above version two', async () => {
  const oneSeen = deferred()
  const twoSeen = deferred()
  const gate1 = deferred()
  const gate2 = deferred()
  const t = host({
    model: req => {
      if (req.prompt.includes('+one')) {
        oneSeen.resolve()
        return gate1.promise
      }
      twoSeen.resolve()
      return gate2.promise
    },
  })
  t.st.diff = fileDiff('stale.js', 'one')
  const runA = t.run()
  await oneSeen.promise
  t.st.diff = fileDiff('stale.js', 'two')
  const runB = t.run()
  await twoSeen.promise
  gate1.resolve({ isAnswered: true, text: 'Note for version one.' })
  await runA
  gate2.resolve({ isAnswered: true, text: 'Note for version two.' })
  await runB
  const text = await t.rows()
  assert.ok(text.includes('Note for version two.'), text)
  assert.ok(!text.includes('Note for version one.'), text)
})

// F5 huge line: register
await test('F5 register: a huge changed line makes no model call and its row says too large', async () => {
  const t = host({ diff: fileDiff('big.txt', 'x'.repeat(5995)) })
  await t.run()
  assert.equal(t.calls.length, 0)
  assert.ok((await t.rows()).includes('No note: change too large'))
})
await test('F5 register: many short lines over the cap still get one model call', async () => {
  let d = 'diff --git a/many.txt b/many.txt\nindex 1..2 100644\n--- a/many.txt\n+++ b/many.txt\n@@ -0,0 +1,700 @@\n'
  for (let i = 0; i < 700; i++) d += `+line ${i}\n`
  const t = host({ diff: d })
  await t.run()
  assert.equal(t.calls.length, 1)
  assert.ok(t.calls[0].prompt.includes('+line 0'))
})

// F7 shared cap: register
const eight = Array.from({ length: 8 }, (_, i) => fileDiff(`lim/f${i}.txt`, `v${i}`)).join('')
await test('F7 register: one run over 8 files makes at most 5 calls', async () => {
  const t = host({ diff: eight, model: slow })
  await t.run()
  assert.ok(t.calls.length <= 5, `calls: ${t.calls.length}`)
})
await test('F7 register: two overlapping runs over the same 8 files make at most 5 calls, one per file', async () => {
  const t = host({ diff: eight, model: slow })
  await Promise.all([t.run(), t.run()])
  assert.ok(t.calls.length <= 5, `calls: ${t.calls.length}`)
  const paths = t.calls.map(c => c.prompt.match(/File: (.*)/)[1])
  assert.equal(new Set(paths).size, paths.length, `repeat calls: ${paths.join(',')}`)
})
await test('F7 register: the same single file in two overlapping runs makes one call', async () => {
  const t = host({ diff: fileDiff('lim/solo.txt', 'solo'), model: slow })
  await Promise.all([t.run(), t.run()])
  assert.equal(t.calls.length, 1)
})
await test('F7 register: after overlapping runs settle, a later run still makes calls (not a lifetime cap)', async () => {
  const three = Array.from({ length: 3 }, (_, i) => fileDiff(`lim/late${i}.txt`, `late${i}`)).join('')
  const t = host({ diff: three, model: slow })
  await t.run()
  assert.equal(t.calls.length, 3)
})

// F8 parse, base, failure text: register
await test('F8 register: no commits shows the file, not an ambiguous-HEAD error', async () => {
  const t = host({ diff: fileDiff('fresh.txt', 'hello'), hasHead: false })
  const res = await t.run()
  assert.equal(res.text, 'Plain diff: 1 file(s).')
  assert.ok((await t.rows()).includes('fresh.txt'))
})
await test("F8 register: a model failure shows 'No note: api-error'", async () => {
  const t = host({ diff: fileDiff('err.txt', 'x'), model: async () => ({ isAnswered: false, reason: 'api-error' }) })
  await t.run()
  assert.ok((await t.rows()).includes('No note: api-error'))
})

const r1Failed = r1.filter(r => r.startsWith('FAIL')).length
console.log(r1.join('\n'))
console.log(`plain-diff review-1 pins: ${r1.length - r1Failed} pass, ${r1Failed} fail of ${r1.length}`)
if (r1Failed) process.exitCode = 1

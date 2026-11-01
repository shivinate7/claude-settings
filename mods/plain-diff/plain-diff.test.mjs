// Pins for plain-diff. Run: node mods/plain-diff/plain-diff.test.mjs  (stdlib only)
// Seams the mod exposes. Names fixed here.
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
// Pins R2-1 .. R2-8. More seams:
//   hooks/lib.mjs
//     gitDiffArgs(base) -> argv after 'git'; must carry '--src-prefix=a/' and '--dst-prefix=b/'
//     headerLine({ files, add, del, truncated }) -> string; truncated gives 'Diff truncated: some files are not shown'
//     makeLimiter(max, { timeoutMs }); a call still running after timeoutMs is freed and resolves null
//     trimNote also strips ESC, BEL and bidi overrides (U+202A..U+202E, U+2066..U+2069)
//     parseDiff: a no-prefix header 'P P' gives P; a quoted rename name is unquoted (C-style escapes)
//     isSecretPath: new names flagged; .env.example, .env.sample, .env.template and credentials.ts are not
//     looksSecret: Stripe, ASIA, JWT, postgres URL, Bearer, AIza, PGP block, key=value assignments
//     noteFromMessages returns '' for a turn text that holds a secret shape
//   hooks/register.mjs: reads isStdoutTruncated into report.truncated; passes gitDiffArgs to git
//   README.md: wording 'at most 5 calls per run, shared by overlapping runs'; names the empty tree
// Known limit, not pinned: a rename that git shows as a new file (no 'rename from' line).
import '../../lint/_test_git.mjs'  // test-run signing opt-out (lint/_test_git.mjs)
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
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
await test('F1 looksSecret: a key inside a multi-line template literal is still flagged', () => {
  const f = need('looksSecret')
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
  if (argv.includes('--show-toplevel')) return ok('/repo\n')
  if (argv.includes('rev-parse')) {
    return st.hasHead ? ok('HEAD\n') : { exitCode: 128, stdout: '', stderr: 'fatal: Needed a single revision\n' }
  }
  if (argv.includes('diff')) {
    if (argv.includes('HEAD') && !st.hasHead) {
      return { exitCode: 128, stdout: '', stderr: "fatal: ambiguous argument 'HEAD': unknown revision\n" }
    }
    return { ...ok(st.diff), isStdoutTruncated: !!st.truncated }
  }
  return ok('')
}
// A real git in a temp repo, for the prefix pins.
function realRun(dir) {
  return argv => {
    const r = spawnSync(argv[0], argv.slice(1), { cwd: dir, encoding: 'utf8' })
    return { exitCode: r.status ?? 1, stdout: r.stdout ?? '', stderr: r.stderr ?? '', isStdoutTruncated: false }
  }
}
function gitIn(dir, args) {
  const r = spawnSync('git', args, { cwd: dir, encoding: 'utf8' })
  if (r.status !== 0) throw new Error(`git ${args.join(' ')}: ${r.stderr}`)
  return r.stdout
}
// A repo with committed files, then changed files, then git config keys.
function repoWith(initial, changed, config) {
  const dir = mkdtempSync(join(tmpdir(), 'plain-diff-r2-'))
  gitIn(dir, ['init', '-q'])
  gitIn(dir, ['config', 'user.name', 'test'])
  gitIn(dir, ['config', 'user.email', 'test@example.com'])
  gitIn(dir, ['config', 'commit.gpgsign', 'false'])
  for (const [p, c] of Object.entries(initial)) writeFileSync(join(dir, p), c)
  gitIn(dir, ['add', '-A'])
  gitIn(dir, ['commit', '-q', '-m', 'init'])
  for (const [p, c] of Object.entries(changed)) writeFileSync(join(dir, p), c)
  for (const [k, v] of Object.entries(config)) gitIn(dir, ['config', k, v])
  return dir
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
  const st = { diff: '', hasHead: true, messages: [], model: quick, truncated: false, run: null, ...init }
  const calls = []
  const argvs = []
  const $ = {
    command: { register: async () => {} },
    ui: {
      open: async () => {},
      resolve: () => ({ Box: 'Box', Button: 'Button', Code: 'Code', Markdown: 'Markdown', Text: 'Text' }),
    },
    process: {
      run: async argv => {
        argvs.push(argv)
        return st.run ? st.run(argv) : gitRun(argv, st)
      },
    },
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
    argvs,
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
await test('F3 register: the Code row holds no ESC or NUL, keeps tab; an ESC in a quoted string keeps the quotes', async () => {
  const t = host({ diff: fileDiff('ctl.txt', 'a\x1b[1m\x00\tb') })
  await t.run()
  const src = await t.codes()
  assert.equal(src.length, 1)
  assert.ok(!/[\x00\x1b]/.test(src[0]), JSON.stringify(src[0]))
  assert.ok(src[0].includes('\t'))
  // Second input: a quoted string with a lone quote in a comment. The ESC goes, the quotes stay.
  const q = host({ diff: fileDiff('quoted.js', 'const s = "\x1bhi"; // Don\'t\x1b') })
  await q.run()
  const qsrc = await q.codes()
  assert.equal(qsrc.length, 1)
  assert.ok(qsrc[0].includes('const s = "hi"; // Don\'t'), JSON.stringify(qsrc[0]))
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

// ---------- R2 pins ----------
// Failure messages stay ASCII, so the verdict tool can print them on any console.
const show = s => JSON.stringify(s).replace(/[^\x20-\x7e]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'))
const BEARER = 'Bearer ' + 'abcdefghij' + 'klmnopqrst' // Bearer + 20 token chars
const STRIPE = 'sk' + '_live_' + 'A1b2C3d4E5f6G7h8I9j0K1l2' // sk_live_ + 24
const ASIA = 'AS' + 'IA' + 'ABCDEFGHIJKLMNOP' // ASIA + 16
const JWT = 'ey' + 'JhbGciOiJIUzI1NiJ9' + '.' + 'ey' + 'JzdWIiOiIxMjM0In0' + '.' + 'sig_abc123XYZ'
const PG_URL = 'postgres' + '://' + 'user:pass' + '@' + 'db.example.com:5432/app'
const AIZA = 'AI' + 'za' + 'Sy' + 'D'.repeat(33) // AIza + 35
const PGP = '-----BEGIN ' + 'PGP PRIVATE KEY BLOCK-----'

// R2-1 privacy: prefixes. The argv always fixes the prefixes; a no-prefix header still parses.
await test('R2-1 gitDiffArgs(HEAD) carries --src-prefix=a/ and --dst-prefix=b/', () => {
  const args = need('gitDiffArgs')('HEAD')
  assert.ok(args.includes('--src-prefix=a/'), args.join(' '))
  assert.ok(args.includes('--dst-prefix=b/'), args.join(' '))
  assert.ok(args.includes('HEAD'), args.join(' '))
})
await test('R2-1 register: every git diff call carries the fixed prefixes', async () => {
  const t = host({ diff: fileDiff('p.txt', 'x') })
  await t.run()
  const diffCalls = t.argvs.filter(a => a.includes('diff'))
  assert.ok(diffCalls.length >= 1, 'no diff call')
  for (const a of diffCalls) {
    assert.ok(a.includes('--src-prefix=a/'), a.join(' '))
    assert.ok(a.includes('--dst-prefix=b/'), a.join(' '))
  }
})
await test("R2-1 parseDiff: a header with no prefixes ('diff --git .env .env') still gives .env", () => {
  const raw = 'diff --git .env .env\nindex 1..2 100644\n--- .env\n+++ .env\n@@ -1 +1 @@\n-a\n+b\n'
  const f = lib.parseDiff(raw)[0]
  assert.equal(f.path, '.env')
  assert.equal(need('isSecretPath')(f.path), true)
})
await test('R2-1 real repo, diff.noprefix: a root .env change is skipped, with no model call for it', async () => {
  const dir = repoWith({ '.env': 'A=1\n', 'keep.txt': 'x\n' }, { '.env': 'A=2\n', 'keep.txt': 'y\n' }, { 'diff.noprefix': 'true' })
  try {
    const t = host({ run: realRun(dir) })
    await t.run()
    assert.equal(t.calls.length, 1, JSON.stringify(t.calls.map(c => c.prompt.split('\n')[4])))
    assert.equal(t.calls[0].prompt.split('\n')[4], 'File: keep.txt')
    assert.ok(!JSON.stringify(t.calls).includes('A=2'), 'secret text sent')
    assert.equal(count(await t.rows(), 'Skipped: secret file'), 1)
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})
await test('R2-1 real repo, diff.mnemonicPrefix: a.txt keeps its path; a root .env change is still skipped', async () => {
  const dir = repoWith({ 'a.txt': 'one\n', '.env': 'A=1\n' }, { 'a.txt': 'two\n', '.env': 'A=2\n' }, { 'diff.mnemonicPrefix': 'true' })
  try {
    const t = host({ run: realRun(dir) })
    await t.run()
    assert.equal(t.calls.length, 1, JSON.stringify(t.calls.map(c => c.prompt.split('\n')[4])))
    assert.equal(t.calls[0].prompt.split('\n')[4], 'File: a.txt')
    assert.ok(!JSON.stringify(t.calls).includes('A=2'), 'secret text sent')
    const rows = await t.rows()
    assert.ok(rows.includes('a.txt'), rows)
    assert.equal(count(rows, 'Skipped: secret file'), 1)
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})

// R2-2 names: more secret file names; false alarms must stay unflagged; quoted rename names unquoted.
await test('R2-2 isSecretPath flags more secret file names', () => {
  const f = need('isSecretPath')
  for (const p of [
    '.envrc', 'prod.env', '.git-credentials', '_netrc', '.pypirc', 'terraform.tfvars', '.htpasswd',
    'application_default_credentials.json', 'key.ppk', 'signing.asc',
  ]) assert.equal(f(p), true, p)
})
await test('R2-2 isSecretPath does not flag names that only look like secrets', () => {
  const f = need('isSecretPath')
  for (const p of ['credentials.ts', 'credentials.test.js', '.env.example', '.env.sample', '.env.template', 'environment.md', 'keyboard.ts']) {
    assert.equal(f(p), false, p)
  }
})
await test('R2-2 a quoted rename source is unquoted before the check', () => {
  // git writes a tab in a name as the two characters \t inside quotes
  const raw = 'diff --git "a/we\\tird/.env" "b/new.txt"\nsimilarity index 90%\nrename from "we\\tird/.env"\nrename to new.txt\n@@ -1 +1 @@\n-a\n+b\n'
  const f = lib.parseDiff(raw)[0]
  assert.equal(f.oldPath, 'we\tird/.env')
  assert.equal(f.path, 'new.txt')
  assert.equal(need('isSecretPath')(f.oldPath), true)
})

// R2-3 body shapes: flagged; prose and key-like names not flagged.
await test('R2-3 looksSecret flags more key shapes under an innocent name', () => {
  const f = need('looksSecret')
  for (const body of [STRIPE, ASIA, JWT, PG_URL, BEARER, AIZA, PGP, 'API_KEY=abcdef1234567890', 'SECRET_KEY: "abcdefghijkl"', 'password = "longvalue"']) {
    assert.equal(f(fileDiff('notes.txt', body)), true, body.slice(0, 24))
  }
})
await test('R2-3 looksSecret does not flag prose or key-like names', () => {
  const f = need('looksSecret')
  for (const body of ['the API key is rotated every quarter', 'api_key_name = column', '  See password_policy.md for the rules.']) {
    assert.equal(f(fileDiff('notes.txt', body)), false, body)
  }
})

// R2-4 turn text: a note holding a secret shape is not shown.
await test('R2-4 noteFromMessages: a turn text holding a secret shape gives no note; prose still does', () => {
  const nf = need('noteFromMessages')
  assert.equal(nf(editedAt('/repo/src/keys.js', 'I set the key to ' + AWS + ' in the file.'), '/repo', 'src/keys.js'), '')
  assert.equal(nf(editedAt('/repo/src/x.js', 'I rotated the API key.'), '/repo', 'src/x.js'), 'I rotated the API key.')
})
await test('R2-4 register: a secret-shaped turn note is not shown; the row says No note', async () => {
  const t = host({
    diff: fileDiff('src/keys.js', 'const k = 1'),
    messages: editedAt('/repo/src/keys.js', 'I set the key to ' + AWS + ' in the file.'),
    model: async () => ({ isAnswered: false, reason: 'empty' }),
  })
  await t.run()
  const rows = await t.rows()
  assert.ok(!rows.includes(AWS), 'secret shown in pane')
  assert.ok(rows.includes('No note'), rows)
})

// R2-5 limiter honesty: a hung call is freed by the limiter's timeout, so a later call is admitted.
await test('R2-5 makeLimiter timeoutMs: a hung call is freed, so a later run is admitted and the hung run gives null', async () => {
  const L = need('makeLimiter')(1, { timeoutMs: 20 })
  const hung = L.run('a', () => new Promise(() => {}))
  assert.equal(await L.run('b', async () => 'B'), null) // still busy at once
  await new Promise(r => setTimeout(r, 60))
  assert.equal(await L.run('c', async () => 'C'), 'C')
  assert.equal(await Promise.race([hung, new Promise(r => setTimeout(() => r('still hung'), 100))]), null)
})

// R2-6 control characters in notes: ESC, BEL, bidi overrides removed from turn and model notes.
const CTRL = /[\x00-\x08\x0b\x0c\x0e-\x1f‪-‮⁦-⁩]/
await test('R2-6 a turn-text note with BEL or a bidi override is cleaned too', () => {
  const o = need('noteFromMessages')(editedAt('/repo/src/bel.js', 'Turn\x07 note.‮'), '/repo', 'src/bel.js')
  assert.ok(!CTRL.test(o), show(o))
  assert.ok(o.includes('Turn'), show(o))
})
await test('R2-6 register: a model note with ESC, BEL or a bidi override is shown without them', async () => {
  // Rows: the note text carries an ESC, a BEL and a bidi override.
  const t = host({ diff: fileDiff('esc.txt', 'z'), model: async () => ({ isAnswered: true, text: 'Model\x1b[1m note\x07‮ here.' }) })
  await t.run()
  const rows = await t.rows()
  assert.ok(!CTRL.test(rows), show(rows))
  assert.ok(rows.includes('Model'), show(rows))
  assert.ok(rows.includes('note') && rows.includes('here'), show(rows))
})

// R2-7 truncation: the header says so, and does not present the count as complete.
await test('R2-7 headerLine: truncated says some files are not shown, and is not the complete form', () => {
  const h = need('headerLine')({ files: 3, add: 1, del: 1, truncated: true })
  assert.ok(h.includes('Diff truncated: some files are not shown'), h)
  assert.notEqual(h, '3 files changed, +1 -1')
})
await test('R2-7 register: a truncated git result shows the truncation line in the pane', async () => {
  const t = host({ diff: fileDiff('t.txt', 'x'), truncated: true })
  await t.run()
  assert.ok((await t.rows()).includes('Diff truncated: some files are not shown'))
})


// ---------- R3 pins ----------
// More seams:
//   hooks/lib.mjs: looksSecret rewritten without catastrophic backtracking; it must accept lines with
//     trailing text (';', ',', '#', '//') and a quoted value, and must still skip `const API_KEY = process.env.API_KEY;`.
//     gitDiffArgs(base) carries '-c', 'core.fsmonitor=false' and '--no-textconv' and '--no-ext-diff'.
//   hooks/register.mjs: every git call gets the same '-c core.fsmonitor=false' pair; the secret scan
//     runs on sanitizeForCode(diff), the same text the model gets.
// Timing runs in a child process with a wall-clock cap, so a hang is a failure, not a stall.
const SCAN_CHILD = `
const { looksSecret, sanitizeForCode, isTooLargeForModel } = await import(process.argv[1]);
const one = { a: 'a'.repeat(80000), deadbeef: 'deadbeef'.repeat(10000), API_KEY: 'API_KEY'.repeat(20000), 'a.a.': 'a.a.'.repeat(20000) };
const kind = process.argv[2];
const text = kind === 'mixed' ? Array.from({ length: 3 }, () => Object.values(one).join('\\n')).join('\\n') : one[kind];
const t0 = performance.now();
looksSecret(sanitizeForCode(text));
isTooLargeForModel(text);
console.log(JSON.stringify({ ms: performance.now() - t0, chars: text.length }));
`
function timeScan(kind, capMs) {
  const url = new URL('./hooks/lib.mjs', import.meta.url).href
  const r = spawnSync(process.execPath, ['--input-type=module', '-e', SCAN_CHILD, url, kind], { encoding: 'utf8', timeout: capMs })
  if (r.error || r.signal) return { hung: true }
  if (r.status !== 0) return { error: String(r.stderr).split('\n')[0] }
  return JSON.parse(String(r.stdout).trim().split('\n').pop())
}

// R3-1 freeze
for (const [label, kind] of [
  ['a', 'a'],
  ['deadbeef', 'deadbeef'],
  ['API_KEY repeated 20000 times', 'API_KEY'],
  ['a.a. repeated', 'a.a.'],
]) {
  await test(`R3-1 freeze: looksSecret on one line of ${label} takes under 150 ms`, () => {
    const r = timeScan(kind, 2500)
    assert.ok(!r.hung, 'hung: no result within 2.5 s')
    assert.ok(!r.error, r.error)
    assert.ok(r.ms < 150, `took ${Math.round(r.ms)} ms`)
  })
}
await test('R3-1 freeze: looksSecret on a 1 MB input of those lines takes under 1 s', () => {
  const r = timeScan('mixed', 3000)
  assert.ok(!r.hung, 'hung: no result within 3 s')
  assert.ok(!r.error, r.error)
  assert.ok(r.chars >= 1000000, `input ${r.chars} chars`)
  assert.ok(r.ms < 1000, `took ${Math.round(r.ms)} ms`)
})

// R3-2 missed secrets: the five lines flagged; the two code and name lines not flagged.
for (const line of [
  '+const SECRET = "abcdEFGH12345678";',
  '+  "apiKey": "AbCdEf1234567890",',
  '+SECRET_KEY = "abcdef1234567890"  # prod',
  '+define("DB_PASSWORD", "abcdef1234567890");',
  "+password: 'abcdef1234567890' // note",
]) {
  await test(`R3-2 looksSecret flags: ${line}`, () => {
    assert.equal(need('looksSecret')(line), true)
  })
}
await test('R3-2 looksSecret does not flag const API_KEY = process.env.API_KEY, or api_key_name = "name"', () => {
  const f = need('looksSecret')
  assert.equal(f('+const API_KEY = process.env.API_KEY;'), false)
  assert.equal(f('+api_key_name = "name"'), false)
})

// R3-3 git argv: no textconv, no external diff, no fsmonitor command.
await test('R3-3 gitDiffArgs carries --no-textconv and --no-ext-diff', () => {
  const a = need('gitDiffArgs')('HEAD')
  assert.ok(a.includes('--no-textconv'), a.join(' '))
  assert.ok(a.includes('--no-ext-diff'), a.join(' '))
})
await test('R3-3 gitDiffArgs carries -c core.fsmonitor=false', () => {
  const a = need('gitDiffArgs')('HEAD')
  const i = a.indexOf('core.fsmonitor=false')
  assert.ok(i > 0 && a[i - 1] === '-c', a.join(' '))
})
await test('R3-3 register: every git call (rev-parse and diff) carries -c core.fsmonitor=false', async () => {
  const t = host({ diff: fileDiff('g.txt', 'x') })
  await t.run()
  assert.ok(t.argvs.length >= 3, `only ${t.argvs.length} git calls`)
  for (const a of t.argvs) {
    const i = a.indexOf('core.fsmonitor=false')
    assert.ok(i > 0 && a[i - 1] === '-c', a.join(' '))
  }
})
await test('R3-3 real repo: a textconv driver and a core.fsmonitor command do not run during the mod diff', async () => {
  const dir = repoWith(
    { '.gitattributes': '* diff=evil\n', 'a.txt': 'one\n' },
    { 'a.txt': 'two\n' },
    { 'diff.evil.textconv': 'touch textconv-ran.marker && cat', 'core.fsmonitor': 'touch fsmonitor-ran.marker' },
  )
  try {
    assert.deepEqual(
      [existsSync(join(dir, 'textconv-ran.marker')), existsSync(join(dir, 'fsmonitor-ran.marker'))],
      [false, false],
      'a marker exists before the run',
    )
    const t = host({ run: realRun(dir) })
    await t.run()
    assert.equal(existsSync(join(dir, 'textconv-ran.marker')), false, 'textconv driver ran')
    assert.equal(existsSync(join(dir, 'fsmonitor-ran.marker')), false, 'fsmonitor command ran')
    assert.ok((await t.rows()).includes('a.txt'), 'a.txt row missing')
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})

// R3-4 scan what the model gets: a control character inside a key must not hide it.
await test('R3-4 register: a control character inside a key value is still skipped; zero model calls for that file', async () => {
  const t = host({ diff: fileDiff('config.txt', 'key = sk-ant-abcdefghij\x01klmnopqrstuvwxyz') + fileDiff('ok.js', 'const a = 1') })
  await t.run()
  assert.equal(t.calls.length, 1, `calls: ${t.calls.length}`)
  assert.ok(t.calls[0].prompt.includes('File: ok.js'), t.calls[0].prompt.split('\n')[4])
  assert.ok(!JSON.stringify(t.calls).includes('sk-ant'), 'secret text sent to the model')
  assert.equal(count(await t.rows(), 'Skipped: secret file'), 1)
})
await test('R3-4 looksSecret on the sanitized line is true (the scan may run after sanitizeForCode)', () => {
  assert.equal(need('looksSecret')(lib.sanitizeForCode('+key = sk-ant-abcdefghij\x01klmnopqrstuvwxyz')), true)
})

const r1Failed = r1.filter(r => r.startsWith('FAIL')).length
console.log(r1.join('\n'))
console.log(`plain-diff pins (review 1 and 2): ${r1.length - r1Failed} pass, ${r1Failed} fail of ${r1.length}`)
if (r1Failed) process.exitCode = 1

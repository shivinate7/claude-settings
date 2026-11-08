// MAP11, the tested-by line. A test named on a `  - Tested by: ` line of a map line must load that map line's code file. It does so when
// it imports the file (a type-only import does not count), or imports one `index.*` or `__init__.py` that re-exports the file (one hop),
// or holds a string literal that is the file's path. A comment or a docstring never counts (rule `building-scanner-respects-strings`).
//
// Fixture: `tests/fixture/`. Its tested-by lines (docs/map/core.md) name src/home.spec.ts and src/pkg.spec.ts for src/home.ts, and
// src/retry_check.py and src/run_retry_check.py for src/retry.py. Each failing case edits its own scratch copy of the fixture, and each
// run goes through `scripts/map-check.mjs`. The spec file for T9 (the 4 to 5 upgrade) is format-version.test.mjs, case 2d: one home for the step.
//
// Red on the old code. The fixture holds formatVersion 5, and the old validator refuses a newer map before any check runs. So each case
// goes red on that refusal, and its output names it. Once the skill reads version 5, each case goes red on its own MAP11 verdict, which
// the old code never prints. Every MAP11 failure assertion names the page, the test and the file it is about.
//
// The picks. Decision `map-tested-by-line` (the tested-by line ruling, docs/decisions/map-tested-by-line.md) records each rule these
// cases read:
//   - the line's form and placement (T7d to T7f), `import pkgpy` through its `__init__.py` (T8d, T8e), and an optional line (T1b).
//   - a join whose anchor is a string literal reads that literal as its first piece (T10e), and `posixpath.dirname` counts as
//     `os.path.dirname` (T10m).
//   - the known places of T11, in JS and Python, and a file is a place too (T11j, T11ah, T11ai). A join from a Python file place is a place
//     only under an outer normpath, abspath or realpath (T11ab, T11ag, T11ak, T11al, T11n). The bare join names nothing (T11aa, T11af, T11aj).
//   - a `/` piece resets `path.resolve`, so the call names nothing (T10aa).
// The `URL` rule is in decision `map-tested-by-line`: a `URL` imported from `node:url` is the global and counts (T11am), a `URL`
// imported from another module does not (T11an), and a `URL` that the file shadows does not count (T11ao).
//
// Cases:
//   T1   the clean fixture passes. T1b: no tested-by line at all passes. T1c, T1d: full size, 40 tests on one line, all pass; one that does not load the file fails.
//   T2   a test that does not load the file fails, and names the page, the test and the file. T2b: one hop only, so a test that reaches the file
//        through the file that imports it fails.
//   T3   a missing test file fails (T3a). An untracked one fails (T3b). Tracked, it passes (T3c, the control).
//   T4   a type-only import fails (T4a, T4b). A value import passes (T4c).
//   T5   scanner traps. A path only in a TS comment (T5a) or a Python docstring (T5b) fails. `//` (T5c) and `#` (T5d) inside a string,
//        before a real import on the same line, pass. A lone quote in a comment, TS (T5e) and Python (T5f), passes. A multi-line template
//        literal that holds the import as text fails (T5g). The same template before a real import passes (T5h).
//   T6   a shell test fails as an unknown read (T6a). With no python3 on PATH, a Python test fails as an unknown read, and with python3 it passes (T6b).
//   T7   placement and form. A tested-by line under a table line (T7a), a screen line (T7b) or a home (T7c) fails. Unindented (T7d), with no
//        backticks (T7e), or with a `;` separator (T7f), it fails. Under a map line after a decisions line (T7g), it passes.
//        Under a backtick line in a Notes section it is an orphan and fails (T7h): a tested-by line is valid only under a Code files map line.
//   T8   one hop. Through `src/pkg/index.ts`, the test passes (T8a). Without the re-export, it fails (T8b). Two hops fail (T8c).
//        Through `src/pkgpy/__init__.py`, the test passes (T8d). Without the re-export, it fails (T8e).
//   T10  a join of literal pieces loads the file when its anchor is a known place: `__dirname`, `os.path.dirname(__file__)`,
//        `Path(__file__).parent`, or a module-level name bound to one of those, with literal pieces after it. The tail resolves from the
//        anchor's real place only. Loads: os.path.join, posixpath.join, pathlib, path.join, path.posix.join, resolve (T10b to T10d, T10m,
//        T10n, T10p, T10w, T10z); T10e loads from a literal anchor (decision `map-tested-by-line`). T10p keeps path.join's leading-slash piece.
//        Not a load, a FAIL: an anchor that is no known place (T10a, T10o, T10r, T10s, T10t, T10u, T10y), a tail that names no tracked
//        file from the real place (T10h, T10q), a name or a starred piece (T10f, T10j), an absolute piece (T10i), a `/` piece that resets
//        `path.resolve` (T10aa), an array join (T10g),
//        a join from another module (T10k, T10v, T10x), a join in a comment, docstring or string (T10l).
//   T11  known places the rule's list does not name yet. Loads, red on the old code: a JS folder from `path.dirname(fileURLToPath(import.meta.url))`
//        (`url.fileURLToPath` too), `import.meta.dirname`, `path.dirname(import.meta.filename)`, `path.dirname(__filename)`,
//        `fileURLToPath(new URL('.', import.meta.url))`, or a bare `dirname` from 'node:path' (T11a to T11f, T11t); a relative URL literal
//        on the file's own URL, `fileURLToPath(new URL('../src', import.meta.url))` (T11x), a `URL` imported from `node:url` (T11am), and the
//        empty literal, which is the file itself (T11ai); a file, from `fileURLToPath(import.meta.url)`, inline or bound (T11j, T11ah); a Python
//        folder from `os.path.normpath` (T11l), `Path(__file__).resolve().parents[1]` (T11m) or `Path(__file__).parents[1]` (T11u); a file, from
//        `normpath(os.path.join(__file__, ...))` (T11ab, T11ag), from `normpath(Path(__file__) / ...)` (T11ak), or from
//        `abspath(os.path.join(__file__, ...))` (T11al); a folder from `Path(__file__).parent.parent` (T11ac). Each Python wrapper has its own
//        pin: normpath (T11ag, T11ak), abspath (T11al), realpath (T11n). T11ab keeps an abspath anchor under normpath. The repo pairs read this repository's own files through readFacts: the loads fact of
//        skills/waiting-page/tests/page.test.mjs names its page (T11v), and that of lint/test_stale_cites.py names bin/ste-changed (T11w).
//        T11n is the realpath pin: realpath wraps a join from the file, which is no place without it.
//        Not a load, a FAIL, green on the old code and the guard of the allow side: the twins of those forms with an anchor that is shadowed
//        (T11g), a temp folder (T11h, T11p, T11r), a foreign function (T11i), a function-local name (T11k), a parameter (T11o),
//        a name bound twice (T11q), a place outside the repository (T11s), a URL on another base (T11y), a `URL` from another module (T11an),
//        a `URL` the file shadows (T11ao), a `file:` scheme (T11z), a negative index (T11ad), a parameter under normpath (T11ae), or a bare join from `__file__`, or a bare pathlib chain from it,
//        which keeps `..` (T11aa, T11af, T11aj).
//   C0   control, green on the old code: the import reader MAP11 uses reads the fixture's imports the way these cases assume.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, readFileSync, symlinkSync, writeFileSync } from 'node:fs';
import { delimiter, dirname, join, posix } from 'node:path';
import { pathToFileURL } from 'node:url';
import { FIXTURE, POSIX_ONLY, ROOT, SKILL, gitIn, needFile, run, scratchRepo, tmpFolder } from './helpers.mjs';

const REL = 'scripts/map-check.mjs';
const CHECK = join(SKILL, 'scripts', 'map-check.mjs');
const CORE = 'docs/map/core.md';
const HOMES = 'docs/map/homes.md';
const MANY = Array.from({ length: 40 }, (_, i) => `src/many/t${i}.spec.ts`);

// ---- Scratch edits. Each edit names the line it changes and fails when that line is not there, so no case runs on a page it did not set.
const readAt = (dir, rel) => readFileSync(join(dir, rel), 'utf8');
const writeAt = (dir, rel, text) => { mkdirSync(dirname(join(dir, rel)), { recursive: true }); writeFileSync(join(dir, rel), text); };
const linesAt = (dir, rel) => readAt(dir, rel).split('\n');
const putLines = (dir, rel, ls) => writeFileSync(join(dir, rel), ls.join('\n'));
const onlyLine = (ls, prefix, rel) => {
  const hits = ls.flatMap((l, i) => (l.startsWith(prefix) ? [i] : []));
  assert.equal(hits.length, 1, `${rel} must hold one line that starts with ${prefix}; it holds ${hits.length}`);
  return hits[0];
};
/** A tested-by line of these paths, indented under a map line as the format needs. */
const tested = (...paths) => `  - Tested by: ${paths.map((p) => `\`${p}\``).join(', ')}`;

/** Sets the tested-by line under the map line of `file` in docs/map/core.md. `text` replaces that line, `null` drops it, and a missing line is added at the end of the block. */
const setTestedBy = (dir, file, text) => {
  const ls = linesAt(dir, CORE);
  const start = onlyLine(ls, `- \`${file}\` `, CORE);
  let end = start + 1;
  while (end < ls.length && ls[end].startsWith('  ')) end++;
  const at = ls.slice(start + 1, end).findIndex((l) => l.includes('Tested by:'));
  if (at >= 0) {
    if (text === null) ls.splice(start + 1 + at, 1);
    else ls[start + 1 + at] = text;
  } else if (text !== null) ls.splice(end, 0, text);
  putLines(dir, CORE, ls);
};

/** Adds `text` as the line right after the one line of `rel` that starts with `prefix`. */
const insertAfter = (dir, rel, prefix, text) => {
  const ls = linesAt(dir, rel);
  ls.splice(onlyLine(ls, prefix, rel) + 1, 0, text);
  putLines(dir, rel, ls);
};

const findOnPath = (name, path) => (path ?? '').split(delimiter).map((d) => join(d, name)).find((p) => existsSync(p)) ?? null;

// ---- Check runs.
const check = (dir, env) => run([CHECK], dir, undefined, env);
/** The MAP11 verdict line of a run, or '' when the run prints none. */
const map11 = (r) => r.out.split('\n').find((l) => /^\[(PASS|FAIL|SKIP)\] MAP11\b/.test(l)) ?? '';
const shown = (r) => r.out.slice(0, 1500);
/** MAP11 fails, the failure line names each of `names`, and the command exits non-zero. */
const mustFail = (r, ...names) => {
  const line = map11(r);
  assert.match(line, /^\[FAIL\] MAP11\b/, `MAP11 must FAIL on this map\n${shown(r)}`);
  for (const n of names) assert.ok(line.includes(n), `the MAP11 failure must name ${n}\n${line}`);
  assert.notEqual(r.status, 0, `the command must exit non-zero on a FAIL\n${shown(r)}`);
};
const mustPass = (r) => assert.match(map11(r), /^\[PASS\] MAP11\b/, `MAP11 must PASS on this map\n${shown(r)}`);

// ---- Cases.
test('T1. on the clean fixture MAP11 passes, and the command exits 0', () => {
  needFile(REL);
  const r = check(scratchRepo());
  mustPass(r);
  assert.equal(r.status, 0, `the clean fixture must exit 0\n${shown(r)}`);
});

test('T1b. a map line with no tested-by line passes: the line is optional', () => {
  needFile(REL);
  const dir = scratchRepo();
  setTestedBy(dir, 'src/home.ts', null);
  setTestedBy(dir, 'src/retry.py', null);
  // The scope first: the page holds no tested-by line at all, or the pass says nothing about the optional line.
  assert.ok(!readAt(dir, CORE).includes('Tested by:'), 'the scratch page must hold no tested-by line');
  mustPass(check(dir));
});

test('T1c. full size: 40 tests on one tested-by line, each loading src/home.ts, pass', () => {
  needFile(REL);
  const dir = scratchRepo();
  for (const f of MANY) writeAt(dir, f, "import { homeTitle } from '../home';\n");
  gitIn(dir, 'add', '-N', 'src/many');
  setTestedBy(dir, 'src/home.ts', tested(...MANY));
  mustPass(check(dir));
});

test('T1d. full size: the same 40 tests, one of which does not load the file, fails and names that one', () => {
  needFile(REL);
  const dir = scratchRepo();
  for (const f of MANY) writeAt(dir, f, "import { homeTitle } from '../home';\n");
  gitIn(dir, 'add', '-N', 'src/many');
  writeAt(dir, MANY[7], '// no import here\nexport {};\n');
  setTestedBy(dir, 'src/home.ts', tested(...MANY));
  mustFail(check(dir), CORE, MANY[7]);
});

test('T2. a test that does not load the file fails, and the output names the page, the test and the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  // The scope first: the named test must not load src/retry.py, or the FAIL says nothing about the link.
  assert.doesNotMatch(readAt(dir, 'src/home.spec.ts'), /\.\/retry/, 'src/home.spec.ts must not import retry');
  setTestedBy(dir, 'src/retry.py', tested('src/home.spec.ts'));
  mustFail(check(dir), CORE, 'src/home.spec.ts', 'src/retry.py');
});

test('T2b. one hop only: a test that reaches a file through the file that imports it fails', () => {
  needFile(REL);
  const dir = scratchRepo();
  // The scope first: home.ts imports notes.ts, and the test imports home.ts alone. So the chain is the one this case names.
  assert.match(readAt(dir, 'src/home.ts'), /from '\.\/notes'/, 'src/home.ts must import notes');
  assert.doesNotMatch(readAt(dir, 'src/home.spec.ts'), /\.\/notes/, 'src/home.spec.ts must not import notes');
  setTestedBy(dir, 'src/notes.ts', tested('src/home.spec.ts'));
  mustFail(check(dir), CORE, 'src/home.spec.ts', 'src/notes.ts');
});

test('T3a. a tested-by line that names a test file which does not exist fails, and names it', () => {
  needFile(REL);
  const dir = scratchRepo();
  assert.ok(!existsSync(join(dir, 'src/gone.spec.ts')), 'the scratch repo must not hold src/gone.spec.ts');
  setTestedBy(dir, 'src/notes.ts', tested('src/gone.spec.ts'));
  mustFail(check(dir), CORE, 'src/gone.spec.ts');
});

test('T3b. a test file that exists but is not tracked fails, and names it', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/fresh.spec.ts', "import { notes } from './notes';\n");
  // The scope first: the file is on disk and not in the index, or the FAIL is for another cause.
  assert.ok(!gitIn(dir, 'ls-files').split('\n').includes('src/fresh.spec.ts'), 'src/fresh.spec.ts must be untracked');
  setTestedBy(dir, 'src/notes.ts', tested('src/fresh.spec.ts'));
  mustFail(check(dir), CORE, 'src/fresh.spec.ts');
});

test('T3c. control: the same test, once tracked, loads notes.ts and passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/fresh.spec.ts', "import { notes } from './notes';\n");
  gitIn(dir, 'add', '-N', 'src/fresh.spec.ts');
  setTestedBy(dir, 'src/notes.ts', tested('src/fresh.spec.ts'));
  mustPass(check(dir));
});

test('T4a. a test whose only import is a type-only import fails, and names the test', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/home.spec.ts', "import type { homeTitle } from './home';\n");
  // The scope first: the test's only import is the type import.
  assert.match(readAt(dir, 'src/home.spec.ts'), /^import type /m, 'the test must hold a type import');
  setTestedBy(dir, 'src/home.ts', tested('src/home.spec.ts'));
  mustFail(check(dir), CORE, 'src/home.spec.ts');
});

test('T4b. a test whose only import names every binding as type (`{ type x }`) fails, and names the test', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/home.spec.ts', "import { type homeTitle } from './home';\n");
  assert.match(readAt(dir, 'src/home.spec.ts'), /\{ type homeTitle \}/, 'the test must hold an all-type import');
  setTestedBy(dir, 'src/home.ts', tested('src/home.spec.ts'));
  mustFail(check(dir), CORE, 'src/home.spec.ts');
});

test('T4c. control: the same test with a value import passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/home.spec.ts', "import { homeTitle } from './home';\n");
  setTestedBy(dir, 'src/home.ts', tested('src/home.spec.ts'));
  mustPass(check(dir));
});

test('T5a. a path that appears only in a TS comment fails, and names the test and the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/home.spec.ts', "// import { homeTitle } from './home';\nexport {};\n");
  // The scope first: the test holds no import statement, only the comment.
  assert.doesNotMatch(readAt(dir, 'src/home.spec.ts'), /^import /m, 'the test must hold no import');
  setTestedBy(dir, 'src/home.ts', tested('src/home.spec.ts'));
  mustFail(check(dir), 'src/home.spec.ts', 'src/home.ts');
});

test('T5b. a path that appears only in a Python docstring fails, and names the test and the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/retry_check.py', '"""Tests the retry wait. It runs src/retry.py and reads retry, in this docstring only."""\n\n\ndef test_wait():\n    assert True\n');
  assert.doesNotMatch(readAt(dir, 'src/retry_check.py'), /^(import|from) /m, 'the test must hold no import');
  setTestedBy(dir, 'src/retry.py', tested('src/retry_check.py'));
  mustFail(check(dir), 'src/retry_check.py', 'src/retry.py');
});

test('T5c. control: a `//` inside a string, before a real import on the same line, is no comment: the import counts and the test passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/home.spec.ts', "const site = \"http://localhost:3000\"; import { homeTitle } from './home';\n");
  setTestedBy(dir, 'src/home.ts', tested('src/home.spec.ts'));
  mustPass(check(dir));
});

test('T5d. control: a `#` inside a string, before a real import on the same line, is no comment: the import counts and the test passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/retry_check.py', 'marker = "#"; import retry\n\n\ndef test_wait():\n    assert retry.RETRY_WAIT_S == 30\n');
  setTestedBy(dir, 'src/retry.py', tested('src/retry_check.py'));
  mustPass(check(dir));
});

test('T5e. control: a lone quote in a TS comment does not open a string that hides the import on the next line: the test passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/home.spec.ts', "// don't stop here: the import is on the next line\nimport { homeTitle } from './home';\n");
  setTestedBy(dir, 'src/home.ts', tested('src/home.spec.ts'));
  mustPass(check(dir));
});

test('T5f. control: a lone quote in a Python comment does not hide the import on the next line: the test passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/retry_check.py', "# don't stop here: the import is on the next line\nimport retry\n\n\ndef test_wait():\n    assert retry.RETRY_WAIT_S == 30\n");
  setTestedBy(dir, 'src/retry.py', tested('src/retry_check.py'));
  mustPass(check(dir));
});

test('T5g. a multi-line TS template literal that holds the import as text, and no real import, fails', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/home.spec.ts', "const doc = `\nimport { homeTitle } from './home';\n// src/home.ts\n`;\nexport { doc };\n");
  // The scope first: the import text sits inside the template, and no import statement is outside it.
  assert.match(readAt(dir, 'src/home.spec.ts'), /^const doc = `$/m, 'the template must open on its own line');
  setTestedBy(dir, 'src/home.ts', tested('src/home.spec.ts'));
  mustFail(check(dir), 'src/home.spec.ts', 'src/home.ts');
});

test('T5h. control: the same multi-line template literal, then a real import after it, passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/home.spec.ts', "const doc = `\nimport { homeTitle } from './home';\n// src/home.ts\n`;\nimport { homeTitle } from './home';\nexport { doc, homeTitle };\n");
  setTestedBy(dir, 'src/home.ts', tested('src/home.spec.ts'));
  mustPass(check(dir));
});

test('T6a. a shell test fails MAP11 as an unknown read, and names the test', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/retry_check.sh', '#!/bin/sh\npython3 src/retry.py\n');
  gitIn(dir, 'add', '-N', 'src/retry_check.sh');
  setTestedBy(dir, 'src/retry.py', tested('src/retry_check.sh'));
  const r = check(dir);
  mustFail(r, 'src/retry_check.sh');
  assert.match(map11(r), /unknown|could not read/i, `the shell test must fail as an unknown read\n${map11(r)}`);
});

test('T6b. with no python3 on PATH, a Python test fails MAP11 as an unknown read that names it; with python3 on PATH it passes', POSIX_ONLY, () => {
  needFile(REL);
  const dir = scratchRepo();
  const git = findOnPath('git', process.env.PATH);
  assert.ok(git, 'git must be on PATH for the stripped run');
  // The scope first: python3 resolves on the normal PATH, and not on the stripped one. Else the no-python3 run says nothing about python3.
  assert.ok(findOnPath('python3', process.env.PATH), 'python3 must be on PATH for the control run');
  const bin = tmpFolder('pemap-tb-bin-');
  symlinkSync(git, join(bin, 'git'));
  assert.equal(findOnPath('python3', bin), null, 'the stripped PATH must hold no python3');
  const r = check(dir, { PATH: bin });
  const line = map11(r);
  assert.match(line, /^\[FAIL\] MAP11\b/, `MAP11 must FAIL with no python3 on PATH\n${shown(r)}`);
  assert.ok(line.includes('src/retry_check.py'), `the failure must name the Python test\n${line}`);
  assert.match(line, /unknown|could not read/i, `the failure must say the read is unknown\n${line}`);
  mustPass(check(dir));
});

test('T7a. a tested-by line under a table line fails, and the output names the page', () => {
  needFile(REL);
  const dir = scratchRepo();
  insertAfter(dir, CORE, '- `notes` ', tested('src/home.spec.ts'));
  mustFail(check(dir), CORE);
});

test('T7b. a tested-by line under a screen line fails, and the output names the page', () => {
  needFile(REL);
  const dir = scratchRepo();
  insertAfter(dir, CORE, '- `home` ', tested('src/home.spec.ts'));
  mustFail(check(dir), CORE);
});

test('T7c. a tested-by line under a home fails, and the output names the page', () => {
  needFile(REL);
  const dir = scratchRepo();
  insertAfter(dir, HOMES, '- the saved notes', tested('src/home.spec.ts'));
  mustFail(check(dir), HOMES);
});

test('T7d. an unindented tested-by line fails, and the output names the page', () => {
  needFile(REL);
  const dir = scratchRepo();
  setTestedBy(dir, 'src/retry.py', '- Tested by: `src/retry_check.py`');
  mustFail(check(dir), CORE);
});

test('T7e. a tested-by line with no backticks fails, and the output names the page', () => {
  needFile(REL);
  const dir = scratchRepo();
  setTestedBy(dir, 'src/retry.py', '  - Tested by: src/retry_check.py');
  mustFail(check(dir), CORE);
});

test('T7f. a tested-by line whose paths are joined by `;` fails, and the output names the page', () => {
  needFile(REL);
  const dir = scratchRepo();
  setTestedBy(dir, 'src/retry.py', '  - Tested by: `src/retry_check.py`; `src/run_retry_check.py`');
  mustFail(check(dir), CORE);
});

test('T7g. control: a tested-by line after a decisions line under a map line passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  insertAfter(dir, CORE, '  - The title counts', '  - Decisions: `D7`');
  // The scope first: the decisions line sits above the tested-by line of the same map line.
  const ls = linesAt(dir, CORE);
  assert.ok(ls.findIndex((l) => l.startsWith('  - Decisions:')) < ls.findIndex((l) => l.includes('Tested by:')), 'the decisions line must come first');
  mustPass(check(dir));
});

test('T7h. a tested-by line under a backtick line in a Notes section is an orphan: MAP11 fails, and names the page and the test', () => {
  needFile(REL);
  const dir = scratchRepo();
  // The scope first: the test loads home.ts, so the only fault left in the case is where the line sits.
  assert.match(readAt(dir, 'src/home.spec.ts'), /from '\.\/home'/, 'src/home.spec.ts must load home.ts');
  writeAt(dir, CORE, `${readAt(dir, CORE).trimEnd()}\n\n## Notes\n\n- \`src/home.ts\` — A note that names the file.\n${tested('src/home.spec.ts')}\n`);
  assert.match(readAt(dir, CORE), /^## Notes$/m, 'the page must hold a Notes section');
  mustFail(check(dir), CORE, 'src/home.spec.ts');
});

test('T8a. one hop: a test that imports the package passes when the package re-exports the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  // The scope first: the package re-exports home.ts, and the test imports the package alone.
  assert.match(readAt(dir, 'src/pkg/index.ts'), /from '\.\.\/home'/, 'src/pkg/index.ts must re-export home');
  assert.doesNotMatch(readAt(dir, 'src/pkg.spec.ts'), /from '\.\/home'/, 'src/pkg.spec.ts must not import home');
  setTestedBy(dir, 'src/home.ts', tested('src/pkg.spec.ts'));
  mustPass(check(dir));
});

test('T8b. one hop without the re-export: the package no longer re-exports the file, and the test fails and is named', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/pkg/index.ts', 'export const other = 1;\n');
  assert.doesNotMatch(readAt(dir, 'src/pkg/index.ts'), /home/, 'the package must not name home');
  mustFail(check(dir), CORE, 'src/pkg.spec.ts');
});

test('T8c. two hops fail: a test that reaches the file through two re-exports is not a load', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/deep/index.ts', "export { homeTitle } from '../pkg';\n");
  writeAt(dir, 'src/deep.spec.ts', "import { homeTitle } from './deep';\n");
  gitIn(dir, 'add', '-N', 'src/deep', 'src/deep.spec.ts');
  // The scope first: deep re-exports the package, and the package re-exports home. Neither re-exports home directly.
  assert.match(readAt(dir, 'src/pkg/index.ts'), /from '\.\.\/home'/, 'src/pkg/index.ts must re-export home');
  assert.doesNotMatch(readAt(dir, 'src/deep/index.ts'), /'\.\.\/home'/, 'src/deep/index.ts must not re-export home directly');
  setTestedBy(dir, 'src/home.ts', tested('src/deep.spec.ts'));
  mustFail(check(dir), CORE, 'src/deep.spec.ts');
});

test('T8d. one hop, Python: a test that imports a package passes when its __init__.py re-exports the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/pkgpy/__init__.py', 'from retry import RETRY_WAIT_S\n');
  writeAt(dir, 'src/pkgpy_check.py', 'import pkgpy\n\n\ndef test_wait():\n    assert pkgpy.RETRY_WAIT_S == 30\n');
  gitIn(dir, 'add', '-N', 'src/pkgpy', 'src/pkgpy_check.py');
  setTestedBy(dir, 'src/retry.py', tested('src/pkgpy_check.py'));
  mustPass(check(dir));
});

test('T8e. one hop, Python, without the re-export: the __init__.py no longer re-exports the file, and the test fails and is named', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'src/pkgpy/__init__.py', 'OTHER = 1\n');
  writeAt(dir, 'src/pkgpy_check.py', 'import pkgpy\n\n\ndef test_wait():\n    assert pkgpy.RETRY_WAIT_S == 30\n');
  gitIn(dir, 'add', '-N', 'src/pkgpy', 'src/pkgpy_check.py');
  assert.doesNotMatch(readAt(dir, 'src/pkgpy/__init__.py'), /retry/, 'the __init__.py must not name retry');
  setTestedBy(dir, 'src/retry.py', tested('src/pkgpy_check.py'));
  mustFail(check(dir), CORE, 'src/pkgpy_check.py');
});

test('C0. control, green on the old code: the import reader MAP11 uses reads the fixture imports the way these cases assume', async () => {
  needFile('scripts/lib/import-reader.mjs');
  const { importTargets } = await import(pathToFileURL(join(SKILL, 'scripts', 'lib', 'import-reader.mjs')).href);
  const tracked = new Set(['src/home.ts', 'src/notes.ts', 'src/home.spec.ts', 'src/pkg/index.ts', 'src/pkg.spec.ts']);
  const of = (f, src = readAt(FIXTURE, f)) => importTargets(f, src, tracked, { types: false });
  assert.deepEqual(of('src/home.spec.ts'), ['src/home.ts'], 'home.spec.ts loads home.ts, and not notes.ts');
  assert.deepEqual(of('src/pkg.spec.ts'), ['src/pkg/index.ts'], 'pkg.spec.ts loads the package, and reaches home.ts only through it: one hop');
  assert.deepEqual(of('src/pkg/index.ts'), ['src/home.ts'], 'the package re-exports home.ts');
  assert.deepEqual(of('src/home.spec.ts', "import type { homeTitle } from './home';\n"), [], 'a type-only import loads nothing');
});

// ---- T10. A join of pieces. MAP11's `loads` op reads a join call as a load of the file that its pieces name (py-facts.py `joined_strings`,
// fact-readers.mjs `joinedStrings`). The callee is os.path.join or posixpath.join, a pathlib `/` chain, or, in JS, path.join, path.resolve,
// path.posix.join, or a bare join or resolve imported from 'path' or 'node:path'. The first argument is the anchor. It must be a known place:
// `__dirname`; `os.path.dirname(__file__)` or `os.path.dirname(os.path.abspath(__file__))`; `Path(__file__).parent` with `.parent` or
// `.resolve()` after it; or a module-level name bound to one of those, optionally joined with literal pieces (`..` included). Any other
// anchor yields nothing: an imported name, a parameter, a name bound to something that is no known place, or a spread. Every later argument
// is a plain string literal. The literal pieces, joined with `/`, resolve from the anchor's real place only.
// Each case writes its test under `tests/`.

/**
 * Writes `text` as the test `testFile` in a scratch repository, tracks it with `git add -N`, and names it on the tested-by line of `file`.
 * The scope comes first: the test is tracked, each literal of `literals` is quoted in the text, and none resolves to a tracked path,
 * from the test's folder or from the root. So a verdict below comes from the join alone.
 */
const pieceCase = (testFile, text, file, literals) => {
  const dir = scratchRepo();
  writeAt(dir, testFile, text);
  gitIn(dir, 'add', '-N', testFile);
  const tracked = gitIn(dir, 'ls-files').split('\n').map((l) => l.trim());
  assert.ok(tracked.includes(testFile), `${testFile} must be tracked, or a verdict on it says nothing about the join`);
  for (const s of literals) {
    assert.ok(text.includes(`'${s}'`) || text.includes(`"${s}"`), `${testFile} must hold the literal ${JSON.stringify(s)} in quotes`);
    const hits = [posix.normalize(posix.join(posix.dirname(testFile), s)), posix.normalize(s)].filter((c) => tracked.includes(c));
    assert.deepEqual(hits, [], `no literal of ${testFile} may resolve to a tracked path, but ${JSON.stringify(s)} resolves to ${hits.join(', ')}`);
  }
  setTestedBy(dir, file, tested(testFile));
  return dir;
};

/** MAP11 passes, so the join of `testFile` loads `file`. On main this is red: MAP11 fails and its line names the test and the file. `why` names the anchor form the case holds. */
const mustLoad = (r, testFile, file, why = '') =>
  assert.match(map11(r), /^\[PASS\] MAP11\b/, `MAP11 must PASS: ${testFile} loads ${file} through a join of its pieces${why ? ` (${why})` : ''}\n${shown(r)}`);

/** MAP11 fails on the page, the test and the file, and the cause is that the test does not load the file. `why` names the rule the case holds. */
const mustNotLoad = (r, page, testFile, file, why = 'the test does not load the file') => {
  assert.match(map11(r), /^\[FAIL\] MAP11\b/, `MAP11 must FAIL: ${why}\n${shown(r)}`);
  for (const n of [page, testFile, file]) assert.ok(map11(r).includes(n), `the MAP11 failure must name ${n}\n${map11(r)}`);
  assert.ok(map11(r).includes('does not load the file'), `the MAP11 failure must say that ${testFile} does not load ${file}\n${map11(r)}`);
  assert.notEqual(r.status, 0, `the command must exit non-zero on a FAIL\n${shown(r)}`);
};

test('T10a. os.path.join(ROOT, "src", "retry.py") with ROOT bound nowhere in the test: ROOT is no known place, so the join is no load: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/join_root.py';
  const text = `import os


def test_wait():
    path = os.path.join(ROOT, "src", "retry.py")
    assert os.path.isfile(path)
`;
  // The scope first: no line binds ROOT, so the verdict is about an unbound anchor. The bound form is T10w.
  assert.doesNotMatch(text, /^ROOT\s*=/m, 'the test must not bind ROOT');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'ROOT is bound nowhere, so it is no known place and the join is no load');
});

test('T10b. pj(os.path.dirname(__file__), "..", "src", "retry.py") with `from os.path import join as pj` loads src/retry.py: MAP11 passes', () => {
  needFile(REL);
  const testFile = 'tests/join_here.py';
  const dir = pieceCase(testFile, `import os
from os.path import join as pj


def test_wait():
    path = pj(os.path.dirname(__file__), "..", "src", "retry.py")
    assert os.path.isfile(path)
`, 'src/retry.py', ['..', 'src', 'retry.py']);
  mustLoad(check(dir), testFile, 'src/retry.py');
});

test('T10c. Path(__file__).parent.parent / "src" / "retry.py" loads src/retry.py: MAP11 passes', () => {
  needFile(REL);
  const testFile = 'tests/join_lib.py';
  const dir = pieceCase(testFile, `from pathlib import Path


def test_wait():
    path = Path(__file__).parent.parent / "src" / "retry.py"
    assert path.is_file()
`, 'src/retry.py', ['src', 'retry.py']);
  mustLoad(check(dir), testFile, 'src/retry.py');
});

test("T10d. path.join(__dirname, '..', 'src', 'home.ts') with `import path from 'node:path'` loads src/home.ts: MAP11 passes", () => {
  needFile(REL);
  const testFile = 'tests/join.spec.ts';
  const dir = pieceCase(testFile, `import path from 'node:path';

export const page = path.join(__dirname, '..', 'src', 'home.ts');
`, 'src/home.ts', ['node:path', '..', 'src', 'home.ts']);
  mustLoad(check(dir), testFile, 'src/home.ts');
});

// A literal anchor is the first piece, per decision `map-tested-by-line`.
test("T10e. resolve('src', 'home.ts') with `import { resolve } from 'path'` loads src/home.ts: MAP11 passes", () => {
  needFile(REL);
  const testFile = 'tests/resolve.spec.ts';
  const dir = pieceCase(testFile, `import { resolve } from 'path';

export const page = resolve('src', 'home.ts');
`, 'src/home.ts', ['path', 'src', 'home.ts']);
  mustLoad(check(dir), testFile, 'src/home.ts');
});

test('T10f. control, green on main: os.path.join(ROOT, "src", NAME) has a name as its last piece, so MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/join_name.py';
  const dir = pieceCase(testFile, `import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "retry.py"


def test_wait():
    path = os.path.join(ROOT, "src", NAME)
    assert os.path.isfile(path)
`, 'src/retry.py', ['src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py');
});

test("T10g. control, green on main: ['..', 'src', 'home.ts'].join('/') is an array join, not a path join, so MAP11 fails and names the page, the test and the file", () => {
  needFile(REL);
  const testFile = 'tests/array_join.spec.ts';
  const dir = pieceCase(testFile, `export const page = ['..', 'src', 'home.ts'].join('/');
`, 'src/home.ts', ['..', 'src', 'home.ts', '/']);
  mustNotLoad(check(dir), CORE, testFile, 'src/home.ts');
});

test('T10h. control, green on main: os.path.join(ROOT, "vendor", "src", "retry.py") with no tracked vendor/src/retry.py does not load src/retry.py: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/join_deep.py';
  const dir = pieceCase(testFile, `import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_wait():
    path = os.path.join(ROOT, "vendor", "src", "retry.py")
    assert os.path.isfile(path)
`, 'src/retry.py', ['vendor', 'src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py');
});

test('T10i. control, green on the built join: os.path.join(ROOT, "src", "/retry.py") has an absolute piece, which resets the join, so the call is no load: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/join_slash.py';
  const dir = pieceCase(testFile, `import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_wait():
    path = os.path.join(ROOT, "src", "/retry.py")
    assert os.path.isfile(path)
`, 'src/retry.py', ['src', '/retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'an absolute piece after the anchor resets os.path.join, so the call is no load');
});

test('T10j. control, green on the built join: os.path.join(*base, "src", "retry.py") has a starred anchor, so the call is no literal join: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/join_star.py';
  const dir = pieceCase(testFile, `import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
base = [ROOT]


def test_wait():
    path = os.path.join(*base, "src", "retry.py")
    assert os.path.isfile(path)
`, 'src/retry.py', ['src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'a starred argument makes the call no literal join');
});

test("T10k. control, green on the built join: a bare join imported from './utils' is no path join, so join(ROOT, 'src', 'home.ts') is no load: MAP11 fails and names the page, the test and the file", () => {
  needFile(REL);
  const testFile = 'tests/join_bare.spec.ts';
  const dir = pieceCase(testFile, `import { join } from './utils';

const ROOT = __dirname;

export const page = join(ROOT, 'src', 'home.ts');
`, 'src/home.ts', ['./utils', 'src', 'home.ts']);
  mustNotLoad(check(dir), CORE, testFile, 'src/home.ts', 'a join imported from another module is no path join');
});

test('T10l. control, green on the built join: a join written in a comment, a docstring or a plain string is no call: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/join_text.py';
  const dir = pieceCase(testFile, `"""Reads os.path.join(ROOT, "src", "retry.py") in this docstring, and in no code."""
# os.path.join(ROOT, "src", "retry.py") in a comment
NOTE = "os.path.join(ROOT, 'src', 'retry.py')"


def test_wait():
    assert NOTE
`, 'src/retry.py', ['src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'a join in a comment, a docstring or a plain string is no call');
});

// posixpath is os.path on POSIX, and decision `map-tested-by-line` names `posixpath` as the same.
test('T10m. posixpath.join(ROOT, "src", "retry.py") with `import posixpath` loads src/retry.py: MAP11 passes', () => {
  needFile(REL);
  const testFile = 'tests/posix_join.py';
  const dir = pieceCase(testFile, `import posixpath

ROOT = posixpath.dirname(posixpath.dirname(posixpath.abspath(__file__)))


def test_wait():
    path = posixpath.join(ROOT, "src", "retry.py")
    assert posixpath.isfile(path)
`, 'src/retry.py', ['src', 'retry.py']);
  mustLoad(check(dir), testFile, 'src/retry.py');
});

test("T10n. path.posix.join(__dirname, '..', 'src', 'home.ts') with `import path from 'node:path'` loads src/home.ts: MAP11 passes", () => {
  needFile(REL);
  const testFile = 'tests/posix.spec.ts';
  const dir = pieceCase(testFile, `import path from 'node:path';

export const page = path.posix.join(__dirname, '..', 'src', 'home.ts');
`, 'src/home.ts', ['node:path', '..', 'src', 'home.ts']);
  mustLoad(check(dir), testFile, 'src/home.ts');
});

test('T10o. tmp_path / "src" / "retry.py" in a test that takes tmp_path: tmp_path is a parameter, which is no known place, so the chain is no load: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/tmp_chain.py';
  const dir = pieceCase(testFile, `def test_wait(tmp_path):
    path = tmp_path / "src" / "retry.py"
    assert path.name == "retry.py"
`, 'src/retry.py', ['src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'tmp_path is a parameter, which is no known place, so the chain is no load');
});

test("T10p. path.join(ROOT, '..', 'src', '/home.ts') with ROOT = __dirname loads src/home.ts: Node's path.join does not reset on a leading '/', so MAP11 passes", () => {
  needFile(REL);
  const testFile = 'tests/join_slash.spec.ts';
  const dir = pieceCase(testFile, `import path from 'node:path';

const ROOT = __dirname;

export const page = path.join(ROOT, '..', 'src', '/home.ts');
`, 'src/home.ts', ['node:path', '..', 'src', '/home.ts']);
  mustLoad(check(dir), testFile, 'src/home.ts');
});

test('T10q. CFG = os.path.join(ROOT, "cfg") with ROOT at the root, then os.path.join(CFG, "src", "retry.py") reads cfg/src/retry.py, which is no tracked file: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/join_cfg.py';
  const dir = pieceCase(testFile, `import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "cfg")


def test_wait():
    path = os.path.join(CFG, "src", "retry.py")
    assert os.path.isfile(path)
`, 'src/retry.py', ['cfg', 'src', 'retry.py']);
  // The scope first: the root holds src/retry.py, so the verdict is about cfg/src/retry.py, and no cfg/src/retry.py may be tracked.
  const tracked = gitIn(dir, 'ls-files').split('\n');
  assert.ok(tracked.includes('src/retry.py'), 'src/retry.py must be tracked, or the case proves nothing about the root candidate');
  assert.ok(!tracked.includes('cfg/src/retry.py') && !tracked.includes('tests/cfg/src/retry.py'), 'no cfg/src/retry.py may be tracked');
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'the tail resolves from the anchor real place only, and cfg/src/retry.py is no tracked file');
});

test('T10r. p = Path(tmp_path), then p / "src" / "retry.py": p is bound to Path(tmp_path), which is no known place, so the chain is no load: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/tmp_path_name.py';
  const dir = pieceCase(testFile, `from pathlib import Path


def test_wait(tmp_path):
    p = Path(tmp_path)
    path = p / "src" / "retry.py"
    assert path.name == "retry.py"
`, 'src/retry.py', ['src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'p is bound to Path(tmp_path), which is no known place, so the chain is no load');
});

test('T10s. repo = tmp_path / "repo", then repo / "src" / "retry.py": repo is bound to a join of a parameter, which is no known place, so the chain is no load: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/tmp_repo.py';
  const dir = pieceCase(testFile, `def test_wait(tmp_path):
    repo = tmp_path / "repo"
    path = repo / "src" / "retry.py"
    assert path.name == "retry.py"
`, 'src/retry.py', ['repo', 'src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'repo is bound to a join of a parameter, which is no known place, so the chain is no load');
});

test("T10t. d is set in beforeEach to fs.mkdtempSync('x'), then path.join(d, 'src', 'home.ts'): d is no known place, so the join is no load: MAP11 fails and names the page, the test and the file", () => {
  needFile(REL);
  const testFile = 'tests/tmp_before.spec.ts';
  const dir = pieceCase(testFile, `import fs from 'node:fs';
import path from 'node:path';
import { beforeEach } from 'node:test';

let d;
beforeEach(() => {
  d = fs.mkdtempSync('x');
});

export const page = path.join(d, 'src', 'home.ts');
`, 'src/home.ts', ['src', 'home.ts']);
  mustNotLoad(check(dir), CORE, testFile, 'src/home.ts', 'd is set in a beforeEach hook, which is no known place, so the join is no load');
});

test('T10u. ROOT imported from conftest, then os.path.join(ROOT, "src", "retry.py"): an imported name is no known place, so the join is no load: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/join_import.py';
  const text = `import os

from conftest import ROOT


def test_wait():
    path = os.path.join(ROOT, "src", "retry.py")
    assert os.path.isfile(path)
`;
  // The scope first: ROOT is imported, not bound here, so the verdict is about an imported anchor.
  assert.match(text, /^from conftest import ROOT$/m, 'the test must import ROOT from conftest');
  assert.doesNotMatch(text, /^ROOT\s*=/m, 'the test must not bind ROOT');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'an imported name is no known place, so the join is no load');
});

test('T10v. ROOT bound as in T10w, then join(ROOT, "src", "retry.py") with `from mylib import join`: the bare join is no os.path.join, so the call is no load: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/join_foreign.py';
  const dir = pieceCase(testFile, `import os
from mylib import join

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_wait():
    path = join(ROOT, "src", "retry.py")
    assert os.path.isfile(path)
`, 'src/retry.py', ['src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'a join imported from another module is no path join');
});

test('T10w. ROOT bound at module level to os.path.dirname(os.path.dirname(os.path.abspath(__file__))), then os.path.join(ROOT, "src", "retry.py") in tests/x.py loads src/retry.py: MAP11 passes', () => {
  needFile(REL);
  const testFile = 'tests/x.py';
  const dir = pieceCase(testFile, `import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_wait():
    path = os.path.join(ROOT, "src", "retry.py")
    assert os.path.isfile(path)
`, 'src/retry.py', ['src', 'retry.py']);
  mustLoad(check(dir), testFile, 'src/retry.py');
});

test("T10x. join(__dirname, '..', 'src', 'home.ts') with `import { join } from './utils'`, beside `import path from 'node:path'`: the bare join is no path join, so the call is no load: MAP11 fails and names the page, the test and the file", () => {
  needFile(REL);
  const testFile = 'tests/join_utils.spec.ts';
  const dir = pieceCase(testFile, `import path from 'node:path';
import { join } from './utils';

export const page = join(__dirname, '..', 'src', 'home.ts');
`, 'src/home.ts', ['..', 'src', 'home.ts']);
  mustNotLoad(check(dir), CORE, testFile, 'src/home.ts', 'a join imported from another module is no path join');
});

test("T10y. path.join(...base, 'src', 'home.ts') with base = [__dirname, '..']: a spread anchor is no known place, so the call is no load: MAP11 fails and names the page, the test and the file", () => {
  needFile(REL);
  const testFile = 'tests/join_spread.spec.ts';
  const dir = pieceCase(testFile, `import path from 'node:path';

const base = [__dirname, '..'];

export const page = path.join(...base, 'src', 'home.ts');
`, 'src/home.ts', ['src', 'home.ts']);
  mustNotLoad(check(dir), CORE, testFile, 'src/home.ts', 'a spread anchor is no known place, so the call is no load');
});

test('T10z. HERE bound at module level to Path(__file__).parent, then HERE / ".." / "src" / "retry.py" loads src/retry.py: MAP11 passes', () => {
  needFile(REL);
  const testFile = 'tests/pathlib_here.py';
  const dir = pieceCase(testFile, `from pathlib import Path

HERE = Path(__file__).parent


def test_wait():
    path = HERE / ".." / "src" / "retry.py"
    assert path.is_file()
`, 'src/retry.py', ['..', 'src', 'retry.py']);
  mustLoad(check(dir), testFile, 'src/retry.py');
});

test("T10aa. path.resolve(path.dirname(__dirname), '/home.ts') in src/sub: the '/' piece resets resolve to the absolute path /home.ts, which is no repo file, so the call is no load: MAP11 fails and names the page, the test and the file", () => {
  needFile(REL);
  const testFile = 'src/sub/resolve_reset.spec.ts';
  const text = `import path from 'node:path';

export const page = path.resolve(path.dirname(__dirname), '/home.ts');
`;
  // The scope first: the anchor is the folder above the test, src, and a kept slash would join it to src/home.ts. A reset does not.
  assert.match(text, /path\.resolve\(path\.dirname\(__dirname\), '\/home\.ts'\)/, 'the test must resolve a "/" piece from the folder above the test');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['/home.ts']);
  mustNotLoad(check(dir), CORE, testFile, 'src/home.ts', 'path.resolve resets at a leading "/" piece, so the call names no repo file');
});

// ---- T11. Known places the rule's list does not name yet. A JS folder is `path.dirname(fileURLToPath(import.meta.url))` (`url.fileURLToPath`
// too), `path.dirname(import.meta.filename)`, `path.dirname(__filename)`, `import.meta.dirname`, `fileURLToPath(new URL('.', import.meta.url))`,
// or `fileURLToPath(new URL('<literal>', import.meta.url))` with a relative literal, which is that literal from the file's folder (T11x).
// A Python folder is `os.path.normpath(...)` of a known place, `Path(__file__).resolve().parents[n]` with a literal n, or
// `Path(__file__).parent.parent` (T11ac). A file (`__filename`, `import.meta.filename`, `fileURLToPath(import.meta.url)`, the empty URL
// `fileURLToPath(new URL('', import.meta.url))` (T11ai), Python's `__file__`) is a place too. A JS join from it resolves as node's path.join
// does, the file's name being one segment, so its first `..` reaches the file's folder (T11j, T11ah). A Python join from `__file__` keeps `..`
// as written, so it is a place only when an outer normpath, abspath or realpath wraps it (T11ab, T11ag, T11ak); the bare join names nothing
// (T11aa, T11af, T11aj). A negative index is no known place (T11ad).
// Each allow case (T11g to T11i, T11k, T11o to T11s, T11y, T11an, T11ao, T11z, T11aa, T11ad, T11ae, T11af, T11aj) is the twin of a should-name form, with the anchor unbound,
// shadowed, rebound, a temp folder, a foreign function, a function-local name, outside the repository, on another URL base (T11y), a `URL` the file shadows (T11ao), a `file:` scheme (T11z),
// a bare join or chain from `__file__` with no outer wrap (T11aa, T11af, T11aj), a negative index (T11ad), or a parameter under normpath (T11ae).
// The forms of these cases are known places in decision `map-tested-by-line`.

test("T11a. const HERE = path.dirname(fileURLToPath(import.meta.url)), with path from 'node:path' and fileURLToPath from 'node:url': path.join(HERE, '..', 'src', 'home.ts') loads src/home.ts: MAP11 passes", () => {
  needFile(REL);
  const testFile = 'tests/here_url.spec.ts';
  const text = `import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));

export const page = path.join(HERE, '..', 'src', 'home.ts');
`;
  assert.match(text, /^const HERE = path\.dirname\(fileURLToPath\(import\.meta\.url\)\);$/m, 'the test must hold the dirname form');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['..', 'src', 'home.ts']);
  mustLoad(check(dir), testFile, 'src/home.ts', 'the anchor is a top-level const bound to path.dirname(fileURLToPath(import.meta.url))');
});

test("T11b. const HERE = path.dirname(url.fileURLToPath(import.meta.url)), with url from 'node:url': path.join(HERE, '..', 'src', 'home.ts') loads src/home.ts: MAP11 passes", () => {
  needFile(REL);
  const testFile = 'tests/here_url_ns.spec.ts';
  const text = `import path from 'node:path';
import url from 'node:url';

const HERE = path.dirname(url.fileURLToPath(import.meta.url));

export const page = path.join(HERE, '..', 'src', 'home.ts');
`;
  assert.match(text, /^const HERE = path\.dirname\(url\.fileURLToPath\(import\.meta\.url\)\);$/m, 'the test must hold the namespace form');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['..', 'src', 'home.ts']);
  mustLoad(check(dir), testFile, 'src/home.ts', 'the anchor is a top-level const bound to path.dirname(url.fileURLToPath(import.meta.url))');
});

test("T11c. path.join(import.meta.dirname, '..', 'src', 'home.ts') loads src/home.ts: MAP11 passes", () => {
  needFile(REL);
  const testFile = 'tests/meta_dirname.spec.ts';
  const text = `import path from 'node:path';

export const page = path.join(import.meta.dirname, '..', 'src', 'home.ts');
`;
  assert.match(text, /import\.meta\.dirname/, 'the test must read import.meta.dirname');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['..', 'src', 'home.ts']);
  mustLoad(check(dir), testFile, 'src/home.ts', 'the anchor is import.meta.dirname itself');
});

test("T11d. const HERE = path.dirname(import.meta.filename) loads src/home.ts through path.join(HERE, '..', 'src', 'home.ts'): MAP11 passes", () => {
  needFile(REL);
  const testFile = 'tests/meta_filename.spec.ts';
  const text = `import path from 'node:path';

const HERE = path.dirname(import.meta.filename);

export const page = path.join(HERE, '..', 'src', 'home.ts');
`;
  assert.match(text, /^const HERE = path\.dirname\(import\.meta\.filename\);$/m, 'the test must hold the dirname of import.meta.filename');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['..', 'src', 'home.ts']);
  mustLoad(check(dir), testFile, 'src/home.ts', 'the anchor is the dirname of import.meta.filename');
});

test("T11e. const HERE = path.dirname(__filename) loads src/home.ts through path.join(HERE, '..', 'src', 'home.ts'): MAP11 passes", () => {
  needFile(REL);
  const testFile = 'tests/filename_dirname.spec.ts';
  const text = `import path from 'node:path';

const HERE = path.dirname(__filename);

export const page = path.join(HERE, '..', 'src', 'home.ts');
`;
  assert.match(text, /^const HERE = path\.dirname\(__filename\);$/m, 'the test must hold the dirname of __filename');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['..', 'src', 'home.ts']);
  mustLoad(check(dir), testFile, 'src/home.ts', 'the anchor is the dirname of __filename');
});

test("T11f. const HERE = fileURLToPath(new URL('.', import.meta.url)), the folder URL, loads src/home.ts through path.join(HERE, '..', 'src', 'home.ts'): MAP11 passes", () => {
  needFile(REL);
  const testFile = 'tests/folder_url.spec.ts';
  const text = `import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = fileURLToPath(new URL('.', import.meta.url));

export const page = path.join(HERE, '..', 'src', 'home.ts');
`;
  assert.match(text, /^const HERE = fileURLToPath\(new URL\('\.', import\.meta\.url\)\);$/m, "the test must hold the folder URL form");
  const dir = pieceCase(testFile, text, 'src/home.ts', ['..', 'src', 'home.ts']);
  mustLoad(check(dir), testFile, 'src/home.ts', "the anchor is fileURLToPath of new URL('.', import.meta.url)");
});

test("T11g. the same HERE as T11a, and a parameter also named HERE in another function: HERE is bound twice, so it is no known place and path.join(HERE, '..', 'src', 'home.ts') names nothing: MAP11 fails and names the page, the test and the file", () => {
  needFile(REL);
  const testFile = 'tests/here_shadow.spec.ts';
  const text = `import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));

export function elsewhere(HERE) {
  return HERE;
}

export const page = path.join(HERE, '..', 'src', 'home.ts');
`;
  // The scope first: HERE is declared at module level and again as a parameter, so the verdict is about a name bound twice.
  assert.match(text, /^const HERE = path\.dirname/m, 'the test must bind HERE at module level');
  assert.match(text, /elsewhere\(HERE\)/, 'the test must bind HERE again as a parameter');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['..', 'src', 'home.ts']);
  mustNotLoad(check(dir), CORE, testFile, 'src/home.ts', 'HERE is bound twice, so it is no known place and the join is no load');
});

test("T11h. HERE = path.dirname(fs.mkdtempSync(...)) is the dirname of a temp folder, which is no known place: path.join(HERE, 'src', 'home.ts') names nothing: MAP11 fails and names the page, the test and the file", () => {
  needFile(REL);
  const testFile = 'tests/here_tmp.spec.ts';
  const text = `import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const HERE = path.dirname(fs.mkdtempSync(path.join(os.tmpdir(), 'x')));

export const page = path.join(HERE, 'src', 'home.ts');
`;
  assert.match(text, /mkdtempSync/, 'the test must make its folder with mkdtempSync');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['x', 'src', 'home.ts']);
  mustNotLoad(check(dir), CORE, testFile, 'src/home.ts', 'the dirname of a temp folder is no known place, so the join is no load');
});

test("T11i. HERE = dirname(fileURLToPath(import.meta.url)) with dirname imported from './utils', not from 'node:path': the call is no path dirname, so path.join(HERE, '..', 'src', 'home.ts') names nothing: MAP11 fails and names the page, the test and the file", () => {
  needFile(REL);
  const testFile = 'tests/here_foreign.spec.ts';
  const text = `import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { dirname } from './utils';

const HERE = dirname(fileURLToPath(import.meta.url));

export const page = path.join(HERE, '..', 'src', 'home.ts');
`;
  assert.match(text, /^import \{ dirname \} from '\.\/utils';$/m, "the test must import dirname from './utils'");
  const dir = pieceCase(testFile, text, 'src/home.ts', ['..', 'src', 'home.ts', './utils']);
  mustNotLoad(check(dir), CORE, testFile, 'src/home.ts', 'a dirname imported from another module is no path dirname, so the join is no load');
});

test("T11j. const FILE = fileURLToPath(import.meta.url), the test's own file: path.join(FILE, '..', '..', 'src', 'home.ts') loads src/home.ts, since two '..' from the file reach the root: MAP11 passes", () => {
  needFile(REL);
  const testFile = 'tests/file_anchor.spec.ts';
  const text = `import path from 'node:path';
import { fileURLToPath } from 'node:url';

const FILE = fileURLToPath(import.meta.url);

export const page = path.join(FILE, '..', '..', 'src', 'home.ts');
`;
  assert.match(text, /^const FILE = fileURLToPath\(import\.meta\.url\);$/m, 'the test must bind FILE to the file path');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['..', 'src', 'home.ts']);
  mustLoad(check(dir), testFile, 'src/home.ts', 'the anchor is the file itself, and a join from it resolves from its path');
});

test("T11k. HERE = path.dirname(fileURLToPath(import.meta.url)) bound inside a function, not at module level: the name is no module-level const, so path.join(HERE, '..', 'src', 'home.ts') names nothing: MAP11 fails and names the page, the test and the file", () => {
  needFile(REL);
  const testFile = 'tests/here_in_function.spec.ts';
  const text = `import path from 'node:path';
import { fileURLToPath } from 'node:url';

export function page() {
  const HERE = path.dirname(fileURLToPath(import.meta.url));
  return path.join(HERE, '..', 'src', 'home.ts');
}
`;
  assert.match(text, /^ {2}const HERE = path\.dirname/m, 'the test must bind HERE inside a function');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['..', 'src', 'home.ts']);
  mustNotLoad(check(dir), CORE, testFile, 'src/home.ts', 'a name set in a function is no module-level const, so the join is no load');
});

test("T11l. ROOT = os.path.normpath(os.path.join(HERE, '..')) with HERE = os.path.dirname(os.path.abspath(__file__)), then os.path.join(ROOT, 'src', 'retry.py') loads src/retry.py: MAP11 passes", () => {
  needFile(REL);
  const testFile = 'tests/normpath_root.py';
  const text = `import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))


def test_wait():
    path = os.path.join(ROOT, "src", "retry.py")
    assert os.path.isfile(path)
`;
  assert.match(text, /^ROOT = os\.path\.normpath\(os\.path\.join\(HERE, "\.\."\)\)$/m, 'the test must bind ROOT to a normpath of a join of HERE');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['..', 'src', 'retry.py']);
  mustLoad(check(dir), testFile, 'src/retry.py', 'the anchor is a module-level name bound to normpath of a join of a known place');
});

test('T11m. ROOT = Path(__file__).resolve().parents[1] at module level, then ROOT / "src" / "retry.py" loads src/retry.py: MAP11 passes', () => {
  needFile(REL);
  const testFile = 'tests/parents_root.py';
  const text = `from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wait():
    path = ROOT / "src" / "retry.py"
    assert path.is_file()
`;
  assert.match(text, /^ROOT = Path\(__file__\)\.resolve\(\)\.parents\[1\]$/m, 'the test must bind ROOT to parents[1] of the file');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['src', 'retry.py']);
  mustLoad(check(dir), testFile, 'src/retry.py', 'the anchor is a module-level name bound to Path(__file__).resolve().parents[1]');
});

// The realpath pin: a realpath around a join from the file keeps its place. Red on a realpath that stops wrapping.
test('T11n. the realpath pin: HERE = os.path.abspath(__file__) and ROOT = os.path.realpath(os.path.join(HERE, "..", "..")) loads src/retry.py through ROOT: MAP11 passes', () => {
  needFile(REL);
  const testFile = 'tests/realpath_root.py';
  const text = `import os

HERE = os.path.abspath(__file__)
ROOT = os.path.realpath(os.path.join(HERE, "..", ".."))


def test_wait():
    path = os.path.join(ROOT, "src", "retry.py")
    assert os.path.isfile(path)
`;
  // The scope first: ROOT is a realpath around a join from the file itself, so the verdict is about that wrap and no other.
  assert.match(text, /^ROOT = os\.path\.realpath\(os\.path\.join\(HERE, "\.\.", "\.\."\)\)$/m, 'the test must wrap a join from the file in realpath');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['..', 'src', 'retry.py']);
  mustLoad(check(dir), testFile, 'src/retry.py', 'realpath wraps a join from the file, so its ".." resolves');
});

test('T11o. the twin of T11l with the anchor a parameter: os.path.join(os.path.normpath(os.path.join(tmp_path, "..")), "src", "retry.py") names nothing, since tmp_path is no known place: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/normpath_param.py';
  const text = `import os


def test_wait(tmp_path):
    path = os.path.join(os.path.normpath(os.path.join(tmp_path, "..")), "src", "retry.py")
    assert os.path.isfile(path)
`;
  assert.match(text, /def test_wait\(tmp_path\):/, 'the test must take tmp_path as a parameter');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['..', 'src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'normpath around a parameter is still no known place, so the join is no load');
});

test('T11p. the twin of T11l with the anchor a temp folder: os.path.join(os.path.normpath(tempfile.mkdtemp()), "src", "retry.py") names nothing: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/normpath_mkdtemp.py';
  const text = `import os
import tempfile


def test_wait():
    path = os.path.join(os.path.normpath(tempfile.mkdtemp()), "src", "retry.py")
    assert os.path.isfile(path)
`;
  assert.match(text, /tempfile\.mkdtemp\(\)/, 'the test must make its folder with tempfile.mkdtemp');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'normpath around a temp folder is still no known place, so the join is no load');
});

test('T11q. the twin of T11l with HERE bound twice: ROOT = os.path.normpath(os.path.join(HERE, "..")) names nothing, since HERE is bound at module level twice: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/normpath_rebound.py';
  const text = `import os

HERE = os.path.dirname(os.path.abspath(__file__))
HERE = os.getcwd()
ROOT = os.path.normpath(os.path.join(HERE, ".."))


def test_wait():
    path = os.path.join(ROOT, "src", "retry.py")
    assert os.path.isfile(path)
`;
  // The scope first: HERE is bound twice at module level, so the verdict is about a name bound twice.
  assert.equal(text.match(/^HERE = /gm).length, 2, 'the test must bind HERE twice at module level');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['..', 'src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'HERE is bound twice, so it is no known place and the join is no load');
});

test('T11r. the twin of T11m with the anchor a temp folder: Path(tmp_path).parents[1] / "src" / "retry.py" names nothing, since tmp_path is no known place: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/parents_tmp.py';
  const text = `from pathlib import Path


def test_wait(tmp_path):
    path = Path(tmp_path).parents[1] / "src" / "retry.py"
    assert path.is_file()
`;
  assert.match(text, /Path\(tmp_path\)\.parents\[1\]/, 'the test must take parents[1] of a temp folder');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'parents of a temp folder is no known place, so the chain is no load');
});

test('T11s. the twin of T11m out of the repository: ROOT = Path(__file__).parents[2] climbs past the repository root, so ROOT / "src" / "retry.py" names nothing: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/parents_outside.py';
  const text = `from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_wait():
    path = ROOT / "src" / "retry.py"
    assert path.is_file()
`;
  assert.match(text, /^ROOT = Path\(__file__\)\.parents\[2\]$/m, 'the test must bind ROOT to parents[2] of the file');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'parents[2] of tests/x.py is above the repository, so the chain is no load');
});

test("T11t. the positive twin of T11i: import { dirname, join } from 'node:path', then const HERE = dirname(fileURLToPath(import.meta.url)) and join(HERE, '..', 'src', 'home.ts') loads src/home.ts: MAP11 passes", () => {
  needFile(REL);
  const testFile = 'tests/here_bare.spec.ts';
  const text = `import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));

export const page = join(HERE, '..', 'src', 'home.ts');
`;
  assert.match(text, /^import \{ dirname, join \} from 'node:path';$/m, "the test must import dirname and join from 'node:path'");
  const dir = pieceCase(testFile, text, 'src/home.ts', ['..', 'src', 'home.ts']);
  mustLoad(check(dir), testFile, 'src/home.ts', 'a bare dirname and join imported from node:path');
});

test('T11u. the positive twin of T11s: ROOT = Path(__file__).parents[1] at module level, then ROOT / "src" / "retry.py" loads src/retry.py: MAP11 passes', () => {
  needFile(REL);
  const testFile = 'tests/parents_plain.py';
  const text = `from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_wait():
    path = ROOT / "src" / "retry.py"
    assert path.is_file()
`;
  assert.match(text, /^ROOT = Path\(__file__\)\.parents\[1\]$/m, 'the test must bind ROOT to parents[1] of the file');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['src', 'retry.py']);
  mustLoad(check(dir), testFile, 'src/retry.py', 'the anchor is a module-level name bound to Path(__file__).parents[1]');
});

// The repo pairs read this repository's own files, so they need its tracked list (`git ls-files`). They are the real examples of the two
// gaps, read in place: the case goes red when the repo's own code keeps the form the gap is about, and the reader names nothing for it.
test("T11v. repo pair, read in place: skills/waiting-page/tests/page.test.mjs builds its page path as path.join(HERE, '..', 'page.html') with HERE = path.dirname(fileURLToPath(import.meta.url)), so the loads fact of this repo names skills/waiting-page/page.html", async () => {
  needFile('scripts/lib/fact-readers.mjs');
  const repoTest = 'skills/waiting-page/tests/page.test.mjs';
  // The scope first: the repo file must hold the form, or the case proves nothing about it.
  const text = readFileSync(join(ROOT, repoTest), 'utf8');
  assert.match(text, /^const HERE = path\.dirname\(fileURLToPath\(import\.meta\.url\)\);$/m, `${repoTest} must hold the dirname form`);
  assert.match(text, /path\.join\(HERE, "\.\.", "page\.html"\)/, `${repoTest} must join HERE with ".." and "page.html"`);
  const { readFacts } = await import(pathToFileURL(join(SKILL, 'scripts', 'lib', 'fact-readers.mjs')).href);
  const tracked = gitIn(ROOT, 'ls-files').split('\n').filter((l) => l !== '');
  assert.ok(tracked.includes('skills/waiting-page/page.html'), 'skills/waiting-page/page.html must be tracked, or the pair names nothing to find');
  const [got] = readFacts([{ file: repoTest, op: 'loads' }], ROOT, { tracked });
  assert.equal(got.ok, true, `the loads fact of ${repoTest} must read: ${got.reason ?? 'no reason given'}`);
  assert.ok(got.value.named.includes('skills/waiting-page/page.html'), `${repoTest} loads skills/waiting-page/page.html, so the fact must name it; it names ${JSON.stringify(got.value.named)}`);
});

test("T11w. repo pair, read in place: lint/test_stale_cites.py sets ROOT = os.path.normpath(os.path.join(HERE, '..')) and joins bin/ste-changed from it, so the loads fact of this repo names bin/ste-changed", async () => {
  needFile('scripts/lib/fact-readers.mjs');
  const repoTest = 'lint/test_stale_cites.py';
  // The scope first: the repo file must hold the normpath form and the join from ROOT, or the case proves nothing about it.
  const text = readFileSync(join(ROOT, repoTest), 'utf8');
  assert.match(text, /^ROOT = os\.path\.normpath\(os\.path\.join\(HERE, "\.\."\)\)$/m, `${repoTest} must hold the normpath form`);
  assert.match(text, /os\.path\.join\(ROOT, "bin", "ste-changed"\)/, `${repoTest} must join bin/ste-changed from ROOT`);
  const { readFacts } = await import(pathToFileURL(join(SKILL, 'scripts', 'lib', 'fact-readers.mjs')).href);
  const tracked = gitIn(ROOT, 'ls-files').split('\n').filter((l) => l !== '');
  assert.ok(tracked.includes('bin/ste-changed'), 'bin/ste-changed must be tracked, or the pair names nothing to find');
  const [got] = readFacts([{ file: repoTest, op: 'loads' }], ROOT, { tracked });
  assert.equal(got.ok, true, `the loads fact of ${repoTest} must read: ${got.reason ?? 'no reason given'}`);
  assert.ok(got.value.named.includes('bin/ste-changed'), `${repoTest} loads bin/ste-changed, so the fact must name it; it names ${JSON.stringify(got.value.named)}`);
});

// T11x to T11z. The JS URL form: `fileURLToPath(new URL('<literal>', import.meta.url))` is the literal resolved from the file's folder, so a
// join from it lands on the folder the literal names (T11x). A URL on another base (T11y), or a `file:` scheme, which is an absolute URL, is no such place (T11z).
// The empty literal is the exception: node resolves '' to the file itself, not to its folder (T11ai).
test("T11x. const SRC = fileURLToPath(new URL('../src', import.meta.url)), a relative URL literal on the file's own URL, then path.join(SRC, 'home.ts') loads src/home.ts: MAP11 passes", () => {
  needFile(REL);
  const testFile = 'tests/url_literal.spec.ts';
  const text = `import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = fileURLToPath(new URL('../src', import.meta.url));

export const page = path.join(SRC, 'home.ts');
`;
  assert.match(text, /^const SRC = fileURLToPath\(new URL\('\.\.\/src', import\.meta\.url\)\);$/m, 'the test must hold the relative URL literal on import.meta.url');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['../src', 'home.ts']);
  mustLoad(check(dir), testFile, 'src/home.ts', "the anchor is fileURLToPath of new URL('../src', import.meta.url), a relative literal from the file's folder");
});

test("T11y. const SRC = fileURLToPath(new URL('../src', pathToFileURL(process.cwd()))): the URL's base is no import.meta.url, so SRC is no known place and path.join(SRC, 'home.ts') names nothing: MAP11 fails and names the page, the test and the file", () => {
  needFile(REL);
  const testFile = 'tests/url_other_base.spec.ts';
  const text = `import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const SRC = fileURLToPath(new URL('../src', pathToFileURL(process.cwd())));

export const page = path.join(SRC, 'home.ts');
`;
  // The scope first: the URL is built on a base that is no import.meta.url, so the verdict is about that base.
  assert.match(text, /new URL\('\.\.\/src', pathToFileURL\(process\.cwd\(\)\)\)/, 'the test must build the URL on pathToFileURL(process.cwd())');
  assert.doesNotMatch(text, /import\.meta\.url/, 'the test must not read import.meta.url');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['../src', 'home.ts']);
  mustNotLoad(check(dir), CORE, testFile, 'src/home.ts', 'the base of the URL is no import.meta.url, so the anchor is no known place and the join is no load');
});

test("T11z. const SRC = fileURLToPath(new URL('file:/../../src', import.meta.url)): a file: scheme makes an absolute URL, which is /src on disk and no place of the repository, so path.join(SRC, 'home.ts') names nothing: MAP11 fails and names the page, the test and the file", () => {
  needFile(REL);
  const testFile = 'tests/url_file_literal.spec.ts';
  const text = `import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = fileURLToPath(new URL('file:/../../src', import.meta.url));

export const page = path.join(SRC, 'home.ts');
`;
  assert.match(text, /new URL\('file:\/\.\.\/\.\.\/src', import\.meta\.url\)/, 'the test must hold the file: literal on import.meta.url');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['file:/../../src', 'home.ts']);
  mustNotLoad(check(dir), CORE, testFile, 'src/home.ts', 'a file: literal is an absolute URL, so the anchor is no place of the repository and the join is no load');
});

// T11aa to T11ak. The Python forms of `__file__`. `os.path.join` keeps `..` as written, so `<file>/..` is no folder and the bare join
// names nothing (T11aa, and T11af at the root). An outer normpath resolves the `..`, so the same join is the place it names (T11ab, T11ag).
// T11aa and T11af are the bare joins that the wrap rule of decision `map-tested-by-line` refuses. T11aj and T11ak are the pathlib twins of T11af and T11ag.
// `Path(__file__).parent.parent` is the folder above the test's folder (T11ac). A negative index is no known place (T11ad), and neither is a
// normpath of a parameter (T11ae). A sibling join is masked in the test's own folder: a plain "x.py" string there already names the file
// (namedFiles), so the case would stay green without the join. The one-`..` cases sit at the root, where no literal names the sibling (T11af, T11ag).
test('T11aa. os.path.join(__file__, "..", "..", "src", "retry.py") names nothing: os.path.join keeps ".." as written, so `<file>/..` is no folder: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/join_file.py';
  const text = `import os


def test_wait():
    path = os.path.join(__file__, "..", "..", "src", "retry.py")
    assert os.path.isfile(path)
`;
  // The scope first: no outer normpath, abspath or realpath wraps the join, so the verdict is about the bare join.
  assert.doesNotMatch(text, /normpath|abspath|realpath/, 'the test must not wrap the join');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['..', 'src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'a bare os.path.join from __file__ keeps ".." as written, so it is no load');
});

test('T11ab. normpath(join(abspath(__file__), "..", "..", "src", "retry.py")) loads src/retry.py: abspath keeps the file place and normpath keeps the join: MAP11 passes', () => {
  needFile(REL);
  const testFile = 'tests/join_file_wrapped.py';
  const dir = pieceCase(testFile, `import os


def test_wait():
    path = os.path.normpath(os.path.join(os.path.abspath(__file__), "..", "..", "src", "retry.py"))
    assert os.path.isfile(path)
`, 'src/retry.py', ['..', 'src', 'retry.py']);
  mustLoad(check(dir), testFile, 'src/retry.py', 'the anchor is abspath(__file__), and normpath wraps the join');
});

test('T11ac. Path(__file__).parent.parent / "retry.py" in src/sub/parent_join.py loads src/retry.py: the folder above the test folder is src, and "/" joins from it: MAP11 passes', () => {
  needFile(REL);
  const testFile = 'src/sub/parent_join.py';
  const text = `from pathlib import Path


def test_wait():
    path = Path(__file__).parent.parent / "retry.py"
    assert path.is_file()
`;
  // The scope first: the chain is two parents and one piece, with the test one folder below src.
  assert.match(text, /Path\(__file__\)\.parent\.parent \/ "retry\.py"/, 'the test must join "retry.py" from Path(__file__).parent.parent');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['retry.py']);
  mustLoad(check(dir), testFile, 'src/retry.py', 'the anchor is Path(__file__).parent.parent, which is the folder src');
});

test('T11ad. ROOT = Path(__file__).parents[-1], then ROOT / "src" / "retry.py": the last parent is the filesystem root, which is no known place, so the chain names nothing: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/parents_negative.py';
  const text = `from pathlib import Path

ROOT = Path(__file__).parents[-1]


def test_wait():
    path = ROOT / "src" / "retry.py"
    assert path.is_file()
`;
  assert.match(text, /^ROOT = Path\(__file__\)\.parents\[-1\]$/m, 'the test must bind ROOT to parents[-1] of the file');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'parents[-1] is the filesystem root, which is no known place, so the chain is no load');
});

test('T11ae. os.path.join(os.path.normpath(root), "src", "retry.py") with root a parameter: normpath of a parameter is no known place, so the join names nothing: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'tests/normpath_param_bare.py';
  const text = `import os


def test_wait(root):
    path = os.path.join(os.path.normpath(root), "src", "retry.py")
    assert os.path.isfile(path)
`;
  assert.match(text, /def test_wait\(root\):/, 'the test must take root as a parameter');
  assert.match(text, /os\.path\.normpath\(root\)/, 'the test must normpath the parameter itself');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'normpath of a parameter is still no known place, so the join is no load');
});

test('T11af. os.path.join(__file__, "..", "src", "retry.py") in a test at the repository root names nothing: os.path.join keeps ".." as written, so `<file>/..` is no folder: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'join_beside.py';
  const text = `import os


def test_wait():
    path = os.path.join(__file__, "..", "src", "retry.py")
    assert os.path.isfile(path)
`;
  // The scope first: no outer normpath, abspath or realpath wraps the join, so the verdict is about the bare join.
  assert.doesNotMatch(text, /normpath|abspath|realpath/, 'the test must not wrap the join');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'a bare os.path.join from __file__ keeps ".." as written, so it is no load');
});

test('T11ag. os.path.normpath(os.path.join(__file__, "..", "src", "retry.py")) in a test at the repository root loads src/retry.py: the outer normpath resolves the "..", so the join reaches the folder beside the file: MAP11 passes', () => {
  needFile(REL);
  const testFile = 'join_beside_wrapped.py';
  const text = `import os


def test_wait():
    path = os.path.normpath(os.path.join(__file__, "..", "src", "retry.py"))
    assert os.path.isfile(path)
`;
  // The scope first: the join is the one of T11af, wrapped in an outer normpath and nothing else.
  assert.match(text, /os\.path\.normpath\(os\.path\.join\(__file__, "\.\.", "src", "retry\.py"\)\)/, 'the test must wrap the join in normpath');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['src', 'retry.py']);
  mustLoad(check(dir), testFile, 'src/retry.py', 'the anchor is __file__, and an outer normpath wraps the join');
});

test("T11ah. path.join(fileURLToPath(import.meta.url), '..', 'src', 'home.ts') in a test at the repository root loads src/home.ts: node's path.join normalizes, so the file's one '..' reaches the folder beside it: MAP11 passes", () => {
  needFile(REL);
  const testFile = 'join_inline_url.spec.mjs';
  const text = `import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const page = path.join(fileURLToPath(import.meta.url), '..', 'src', 'home.ts');
`;
  // The scope first: the file URL is joined inline, with no const between it and the join.
  assert.match(text, /path\.join\(fileURLToPath\(import\.meta\.url\), '\.\.', 'src', 'home\.ts'\)/, 'the test must join the file URL inline');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['..', 'src', 'home.ts']);
  mustLoad(check(dir), testFile, 'src/home.ts', 'the anchor is fileURLToPath(import.meta.url) itself, and node path.join normalizes the join');
});

test("T11ai. path.join(fileURLToPath(new URL('', import.meta.url)), '..', 'src', 'home.ts') in a test at the repository root loads src/home.ts: the empty URL is the file itself, one segment, so its '..' reaches the root: MAP11 passes", () => {
  needFile(REL);
  const testFile = 'join_empty_url.spec.mjs';
  const text = `import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const page = path.join(fileURLToPath(new URL('', import.meta.url)), '..', 'src', 'home.ts');
`;
  // The scope first: the URL literal is the empty string on import.meta.url, so the verdict is about that literal.
  assert.match(text, /new URL\('', import\.meta\.url\)/, "the test must hold the empty URL literal on import.meta.url");
  const dir = pieceCase(testFile, text, 'src/home.ts', ['..', 'src', 'home.ts']);
  mustLoad(check(dir), testFile, 'src/home.ts', "the anchor is fileURLToPath(new URL('', import.meta.url)), which is the file and not its folder");
});

test("T11am. const SRC = fileURLToPath(new URL('../src', import.meta.url)) with URL imported from 'node:url', beside fileURLToPath, then path.join(SRC, 'home.ts') loads src/home.ts: the URL is the global, so the place counts: MAP11 passes", () => {
  needFile(REL);
  const testFile = 'tests/url_import.spec.ts';
  const text = `import path from 'node:path';
import { fileURLToPath, URL } from 'node:url';

const SRC = fileURLToPath(new URL('../src', import.meta.url));

export const page = path.join(SRC, 'home.ts');
`;
  // The scope first: URL is imported from node:url, so the URL in the place is that import and no other binding.
  assert.match(text, /^import \{ fileURLToPath, URL \} from 'node:url';$/m, 'the test must import URL from node:url');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['../src', 'home.ts']);
  mustLoad(check(dir), testFile, 'src/home.ts', 'URL imported from node:url is the same global as a bare URL, so the fileURLToPath place counts');
});

test("T11an. the twin of T11am: const SRC = fileURLToPath(new URL('../src', import.meta.url)) with URL imported from './utils', not from 'node:url': that URL is no global, so SRC is no known place and path.join(SRC, 'home.ts') names nothing: MAP11 fails and names the page, the test and the file", () => {
  needFile(REL);
  const testFile = 'tests/url_local.spec.ts';
  const text = `import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { URL } from './utils';

const SRC = fileURLToPath(new URL('../src', import.meta.url));

export const page = path.join(SRC, 'home.ts');
`;
  // The scope first: URL comes from another module, so the URL in the place is no node:url URL.
  assert.match(text, /^import \{ URL \} from '\.\/utils';$/m, 'the test must import URL from another module');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['../src', 'home.ts']);
  mustNotLoad(check(dir), CORE, testFile, 'src/home.ts', 'a URL imported from another module is no node:url URL, so the call is no load');
});

test("T11ao. const URL = class {} in a function shadows the URL that the file imports from node:url, so new URL('../src/retry.mjs', import.meta.url) there is no global, and path.join(fileURLToPath(...), '..', 'home.ts') names nothing: MAP11 fails and names the page, the test and the file", () => {
  needFile(REL);
  const testFile = 'tests/url_shadow.spec.mjs';
  const text = `import path from 'node:path';
import { fileURLToPath, URL } from 'node:url';

export function page() {
  const URL = class {};
  return path.join(fileURLToPath(new URL('../src/retry.mjs', import.meta.url)), '..', 'home.ts');
}
`;
  // The scope first: URL is imported from node:url, and a function of the file shadows it, so the URL that the join builds is the shadow.
  assert.match(text, /^import \{ fileURLToPath, URL \} from 'node:url';$/m, 'the test must import URL from node:url');
  assert.match(text, /^  const URL = class \{\};$/m, 'the test must shadow URL in a function');
  const dir = pieceCase(testFile, text, 'src/home.ts', ['../src/retry.mjs', '..', 'home.ts']);
  mustNotLoad(check(dir), CORE, testFile, 'src/home.ts', 'a URL that the file shadows is no node:url global, so the call is no load');
});

// T11aj and T11ak, the pathlib twins of T11af and T11ag. `Path(__file__) / ".." / ...` is a bare chain: it keeps
// `..` as written, so it names nothing (T11aj). An outer normpath resolves the `..`, so the same chain names the file's sibling folder (T11ak).
test('T11aj. Path(__file__) / ".." / "src" / "retry.py" in a test at the repository root names nothing: the pathlib chain keeps ".." as written, so `<file>/..` is no folder: MAP11 fails and names the page, the test and the file', () => {
  needFile(REL);
  const testFile = 'pathlib_beside.py';
  const text = `from pathlib import Path


def test_wait():
    path = Path(__file__) / ".." / "src" / "retry.py"
    assert path.is_file()
`;
  // The scope first: no outer normpath, abspath or realpath wraps the chain, so the verdict is about the bare chain.
  assert.doesNotMatch(text, /normpath|abspath|realpath/, 'the test must not wrap the chain');
  assert.match(text, /Path\(__file__\) \/ "\.\." \/ "src" \/ "retry\.py"/, 'the test must join "retry.py" from a chain of "/" that starts at Path(__file__)');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['..', 'src', 'retry.py']);
  mustNotLoad(check(dir), CORE, testFile, 'src/retry.py', 'a bare pathlib chain from __file__ keeps ".." as written, so it is no load');
});

test('T11ak. os.path.normpath(Path(__file__) / ".." / "src" / "retry.py") in a test at the repository root loads src/retry.py: the outer normpath resolves the "..", so the chain reaches the folder beside the file: MAP11 passes', () => {
  needFile(REL);
  const testFile = 'pathlib_beside_wrapped.py';
  const text = `import os
from pathlib import Path


def test_wait():
    path = os.path.normpath(Path(__file__) / ".." / "src" / "retry.py")
    assert os.path.isfile(path)
`;
  // The scope first: the chain is the one of T11aj, wrapped in an outer normpath and nothing else.
  assert.match(text, /os\.path\.normpath\(Path\(__file__\) \/ "\.\." \/ "src" \/ "retry\.py"\)/, 'the test must wrap the chain in normpath');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['..', 'src', 'retry.py']);
  mustLoad(check(dir), testFile, 'src/retry.py', 'the anchor is Path(__file__), and an outer normpath wraps the chain');
});

test('T11al. os.path.abspath(os.path.join(__file__, "..", "..", "src", "retry.py")) in tests/join_file_abspath.py loads src/retry.py: abspath is the only wrap, and it resolves the ".." as normpath does: MAP11 passes', () => {
  needFile(REL);
  const testFile = 'tests/join_file_abspath.py';
  const text = `import os


def test_wait():
    path = os.path.abspath(os.path.join(__file__, "..", "..", "src", "retry.py"))
    assert os.path.isfile(path)
`;
  // The scope first: abspath is the one wrap of the join, so a verdict on the join is a verdict on abspath.
  assert.match(text, /os\.path\.abspath\(os\.path\.join\(__file__, "\.\.", "\.\.", "src", "retry\.py"\)\)/, 'the test must wrap the join in abspath');
  assert.doesNotMatch(text, /normpath|realpath/, 'the test must not wrap the join in another function');
  const dir = pieceCase(testFile, text, 'src/retry.py', ['..', 'src', 'retry.py']);
  mustLoad(check(dir), testFile, 'src/retry.py', 'the anchor is __file__, and an outer abspath wraps the join');
});

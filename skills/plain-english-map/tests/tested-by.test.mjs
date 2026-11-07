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
// Assumed. The spec names the cases but not the messages, so these read the spec's own claims:
//   - an unindented tested-by line, a line with no backticks, and a `;` separator each fail, and the failure names the page (T7d to T7f).
//   - `import pkgpy` loads `pkgpy/__init__.py` by its package name (T8d, T8e).
//   - a map line whose tested-by line is missing passes: the line is optional (T1b).
//   - a present tsconfig.json that does not parse makes an alias read unknown, and the message starts `unknown read: could not read <test>: tsconfig.json` (T11d).
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
//   T11  a test that imports by a tsconfig path alias (`@/`). T11a: a comment, trailing commas, baseUrl and paths: the alias loads home.ts.
//        T11b: an `extends` chain, whose paths resolve from the base file. T11c, T11c2: a matched pattern with no hit, and a bare specifier
//        with no pattern: both FAIL. T11d: a truncated tsconfig makes the read unknown. T11e, T11f: controls. No tsconfig keeps main's FAIL,
//        and a broken tsconfig with relative imports only passes.
//        Red on main: T11a, T11b, T11d. T11c and T11c2 are controls: main skips every bare specifier, so both FAIL there too. Their proofs
//        after the build are two mutants: T11c fails on a baseUrl fallback after a pattern match, and T11c2 fails on an implicit `~/` alias
//        (to `src/`, or to the importer's folder). Green on main: T11c, T11c2, T11e, T11f.
//        T11g: an unknown compiler option is no unreadable tsconfig, so the alias loads home.ts. T11h, T11i, T11j: a test that loads the
//        file by a relative import passes, even when the tsconfig is unreadable and the test also imports a package, `node:fs`, or a type
//        from a package. T11k: an unreadable tsconfig with an alias-only test is unknown, and its message names `npm ci`.
//   C0   control, green on the old code: the import reader MAP11 uses reads the fixture's imports the way these cases assume.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, readFileSync, symlinkSync, writeFileSync } from 'node:fs';
import { delimiter, dirname, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { FIXTURE, POSIX_ONLY, SKILL, gitIn, needFile, run, scratchRepo, tmpFolder } from './helpers.mjs';

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

// ---- T11. A test that imports by a tsconfig path alias (decision map-tested-by-line).
// The host's tsconfig.json is read: comments, trailing commas and an `extends` chain. Then `paths`: the longest prefix, one `*`, an exact
// name wins, targets are tried in order, and a matched pattern with no hit is null, with no baseUrl fallback. Then `baseUrl`.
// A missing tsconfig keeps main's behaviour. A present one that cannot be read makes a read unknown, but only when the test holds no
// relative import that already loads the file. An unknown compiler option is an option error, not an unreadable tsconfig: its paths still read.
// The scanner traps of a JSON text: `/*` inside the string "@/*" (T11a), and a lone quote in a `//` comment (T11a). A JSON text holds
// no template literal, so that trap has no case here.
const TSCONFIG = 'tsconfig.json';
const ALIAS = 'src/alias.spec.ts';
const RELATIVE = 'src/relative.spec.ts';
const T11A_TSCONFIG = `{
  // the host's path aliases
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {"@/*": ["./src/*"],},
  },
}
`;
const T11B_ROOT = '{\n  "extends": "./config/base.json"\n}\n';
const T11B_BASE = '{\n  "compilerOptions": {\n    "paths": {"@/*": ["../src/*"]}\n  }\n}\n';
const T11C_TSCONFIG = '{\n  "compilerOptions": {\n    "baseUrl": ".",\n    "paths": {"src/*": ["./lib/*"]}\n  }\n}\n';
const T11_TRUNCATED = '{\n  "compilerOptions": {\n    "baseUrl": ".",\n    "paths": {"@/*": ["./src/*"]\n';

/** True when `text` reads as JSON. A tsconfig with a comment or a trailing comma does not. */
const parses = (text) => { try { JSON.parse(text); return true; } catch { return false; } };
/** The module specifiers of the `from '...'` imports of a TS file. */
const specifiersOf = (text) => [...text.matchAll(/from ['"]([^'"]+)['"]/g)].map((m) => m[1]);
/** The test paths named in backticks on the tested-by lines of docs/map/core.md. */
const testedPaths = (dir) => readAt(dir, CORE).split('\n').filter((l) => l.includes('Tested by:')).flatMap((l) => [...l.matchAll(/`([^`]+)`/g)].map((m) => m[1]));
/** Writes `rel` into `dir` and tracks it, so `git ls-files` lists it. */
const addTracked = (dir, rel, text) => { writeAt(dir, rel, text); gitIn(dir, 'add', '-N', rel); };
/** Adds the map line of a new test file under the code files of docs/map/core.md, as each test of the fixture has one. Else MAP1 fails on the new file. */
const mapTest = (dir, rel, prose) => insertAfter(dir, CORE, '- `src/home.spec.ts` ', `- \`${rel}\` — ${prose}`);
/** A test that imports `specifier` and nothing else, tracked and mapped. */
const writeAliasSpec = (dir, specifier) => {
  addTracked(dir, ALIAS, `import { homeTitle } from '${specifier}';\n\nexport const title = homeTitle;\n`);
  mapTest(dir, ALIAS, 'Tests the home title by an alias.');
};
/** The scope of a case: the file `rel` imports by `prefix`, such as `@/`. */
const importsBy = (dir, rel, prefix) => assert.ok(readAt(dir, rel).includes(`'${prefix}`), `${rel} must import by ${prefix}`);

test('T11a. a tsconfig with a comment, trailing commas, baseUrl and paths: the alias import loads home.ts, so MAP11 passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  addTracked(dir, TSCONFIG, T11A_TSCONFIG);
  writeAliasSpec(dir, '@/home');
  setTestedBy(dir, 'src/home.ts', tested(ALIAS));
  // The scope first: the tsconfig exists, it is JSONC (a comment, trailing commas, and a lone quote in the comment), it maps `@/*`, and the test imports by the alias.
  assert.ok(existsSync(join(dir, TSCONFIG)), 'tsconfig.json must exist');
  assert.ok(!parses(readAt(dir, TSCONFIG)), 'the tsconfig must not parse as JSON: it holds a comment and trailing commas');
  assert.ok(readAt(dir, TSCONFIG).includes("host's"), 'the tsconfig must hold a lone quote in its comment');
  assert.ok(readAt(dir, TSCONFIG).includes('"@/*"'), 'the tsconfig must map "@/*"');
  importsBy(dir, ALIAS, '@/');
  mustPass(check(dir));
});

test('T11b. a tsconfig that extends a base file, whose paths resolve from the base: the alias import loads home.ts, so MAP11 passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  addTracked(dir, TSCONFIG, T11B_ROOT);
  addTracked(dir, 'config/base.json', T11B_BASE);
  writeAliasSpec(dir, '@/home');
  setTestedBy(dir, 'src/home.ts', tested(ALIAS));
  // The scope first: the root holds no paths, the base holds no baseUrl, and its target climbs out of config/ to src/.
  assert.ok(existsSync(join(dir, TSCONFIG)), 'tsconfig.json must exist');
  assert.ok(!readAt(dir, TSCONFIG).includes('paths'), 'the root tsconfig must hold no paths');
  assert.ok(!readAt(dir, 'config/base.json').includes('baseUrl'), 'config/base.json must hold no baseUrl');
  assert.ok(readAt(dir, 'config/base.json').includes('"../src/*"'), 'config/base.json must map to ../src/*');
  importsBy(dir, ALIAS, '@/');
  mustPass(check(dir));
});

/** The MAP11 run of a scratch repository under T11C_TSCONFIG, whose alias test imports `specifier`. */
const pathMissRun = (specifier) => {
  const dir = scratchRepo();
  addTracked(dir, TSCONFIG, T11C_TSCONFIG);
  writeAliasSpec(dir, specifier);
  setTestedBy(dir, 'src/home.ts', tested(ALIAS));
  return { dir, r: check(dir) };
};

test('T11c. control: a matched paths pattern with no hit is null, with no baseUrl fallback, so `src/home` FAILs MAP11 and names the page, the test and the file', () => {
  needFile(REL);
  const { dir, r } = pathMissRun('src/home');
  // The scope first: no lib folder holds the pattern target, and src/home.ts exists, so a baseUrl fallback would reach it.
  assert.ok(existsSync(join(dir, TSCONFIG)), 'tsconfig.json must exist');
  assert.ok(!existsSync(join(dir, 'lib')), 'no lib folder may exist, or the pattern target would hit');
  assert.ok(existsSync(join(dir, 'src/home.ts')), 'src/home.ts must exist, so a baseUrl fallback would hit it');
  importsBy(dir, ALIAS, 'src/');
  mustFail(r, CORE, ALIAS, 'src/home.ts');
});

test('T11c2. control: a bare specifier with no matching pattern is null, so `~/home` FAILs MAP11 and names the page, the test and the file', () => {
  needFile(REL);
  const { dir, r } = pathMissRun('~/home');
  // The scope first: the tsconfig exists, and the test imports by `~/`, which no pattern of it matches.
  assert.ok(existsSync(join(dir, TSCONFIG)), 'tsconfig.json must exist');
  importsBy(dir, ALIAS, '~/');
  mustFail(r, CORE, ALIAS, 'src/home.ts');
});

test('T11d. a tsconfig that is present but truncated: the alias read is unknown, so MAP11 FAILs with `unknown read: could not read src/alias.spec.ts: tsconfig.json`', () => {
  needFile(REL);
  const dir = scratchRepo();
  addTracked(dir, TSCONFIG, T11_TRUNCATED);
  writeAliasSpec(dir, '@/home');
  setTestedBy(dir, 'src/home.ts', tested(ALIAS));
  // The scope first: the tsconfig is on disk and does not parse, and the test imports by the alias.
  assert.ok(existsSync(join(dir, TSCONFIG)), 'tsconfig.json must exist');
  assert.ok(!parses(readAt(dir, TSCONFIG)), 'the tsconfig must not parse');
  importsBy(dir, ALIAS, '@/');
  const r = check(dir);
  mustFail(r, ALIAS);
  assert.match(map11(r), /unknown read: could not read src\/alias\.spec\.ts: tsconfig\.json/, `the unreadable tsconfig must make the alias read unknown, and name the test and tsconfig.json\n${map11(r)}`);
});

test('T11e. control: with no tsconfig.json, the alias import loads nothing, so MAP11 FAILs as on main, and the read is not unknown', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAliasSpec(dir, '@/home');
  setTestedBy(dir, 'src/home.ts', tested(ALIAS));
  // The scope first: no tsconfig.json exists, and the test imports by the alias.
  assert.ok(!existsSync(join(dir, TSCONFIG)), 'the scratch repository must hold no tsconfig.json');
  importsBy(dir, ALIAS, '@/');
  const r = check(dir);
  mustFail(r, CORE, ALIAS, 'src/home.ts');
  assert.doesNotMatch(map11(r), /unknown read/, `a missing tsconfig keeps main's read: a FAIL with no unknown read\n${map11(r)}`);
});

test('T11f. control: a tsconfig that does not parse, with only relative imports, reads no alias, so MAP11 passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  addTracked(dir, TSCONFIG, T11_TRUNCATED);
  addTracked(dir, RELATIVE, "import { homeTitle } from './home';\n\nexport const title = homeTitle;\n");
  mapTest(dir, RELATIVE, 'Tests the home title by a relative import.');
  setTestedBy(dir, 'src/home.ts', tested(RELATIVE));
  // The scope first: the tsconfig does not parse, the test imports by relative paths only, and every TS test named on a tested-by line does too.
  assert.ok(existsSync(join(dir, TSCONFIG)), 'tsconfig.json must exist');
  assert.ok(!parses(readAt(dir, TSCONFIG)), 'the tsconfig must not parse');
  assert.ok(specifiersOf(readAt(dir, RELATIVE)).length > 0, 'the test must import something');
  for (const t of testedPaths(dir).filter((p) => /\.(ts|tsx|mjs|js)$/.test(p)))
    assert.ok(specifiersOf(readAt(dir, t)).every((s) => s.startsWith('.')), `${t} must import by relative paths only`);
  mustPass(check(dir));
});

const T11G_TSCONFIG = '{\n  "compilerOptions": {\n    "baseUrl": ".",\n    "fooBarFuture": true,\n    "paths": {"@/*": ["./src/*"]}\n  }\n}\n';
const T11H_TSCONFIG = '{\n  "extends": "@acme/tsconfig-base"\n}\n';
const MIXED = 'src/mixed.spec.ts';
const NODE_SPEC = 'src/node.spec.ts';
const TYPES_SPEC = 'src/types.spec.ts';

test('T11g. a tsconfig with an unknown compiler option and valid paths: an option error is no unreadable tsconfig, so the alias import loads home.ts and MAP11 passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  addTracked(dir, TSCONFIG, T11G_TSCONFIG);
  writeAliasSpec(dir, '@/home');
  setTestedBy(dir, 'src/home.ts', tested(ALIAS));
  // The scope first: the tsconfig exists and parses as JSON, so the option is its only fault. It names that option and maps `@/*`, and the test imports by the alias.
  assert.ok(existsSync(join(dir, TSCONFIG)), 'tsconfig.json must exist');
  assert.ok(parses(readAt(dir, TSCONFIG)), 'the tsconfig must parse as JSON');
  assert.ok(readAt(dir, TSCONFIG).includes('"fooBarFuture": true'), 'the tsconfig must name the unknown option');
  assert.ok(readAt(dir, TSCONFIG).includes('"@/*"'), 'the tsconfig must map "@/*"');
  importsBy(dir, ALIAS, '@/');
  mustPass(check(dir));
});

test('T11h. a tsconfig that extends a missing package, and a test that loads the file by a relative import and imports a package: the link is found another way, so MAP11 passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  addTracked(dir, TSCONFIG, T11H_TSCONFIG);
  addTracked(dir, MIXED, "import { homeTitle } from './home';\nimport { something } from 'some-pkg';\n\nexport const title = [homeTitle, something];\n");
  mapTest(dir, MIXED, 'Tests the home title and a package.');
  setTestedBy(dir, 'src/home.ts', tested(MIXED));
  // The scope first: the tsconfig extends a package that is not installed, and the test loads home.ts by a relative import and imports a package too.
  assert.ok(existsSync(join(dir, TSCONFIG)), 'tsconfig.json must exist');
  assert.ok(!existsSync(join(dir, 'node_modules', '@acme')), 'the extended package must not be installed');
  assert.ok(readAt(dir, TSCONFIG).includes('"extends": "@acme/tsconfig-base"'), 'the tsconfig must extend @acme/tsconfig-base');
  assert.ok(readAt(dir, MIXED).includes("from './home'"), 'the test must load home.ts by a relative import');
  assert.ok(readAt(dir, MIXED).includes("from 'some-pkg'"), 'the test must import a package');
  mustPass(check(dir));
});

test('T11i. a truncated tsconfig, and a test that loads the file by a relative import and imports node:fs: the link is found another way, so MAP11 passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  addTracked(dir, TSCONFIG, T11_TRUNCATED);
  addTracked(dir, NODE_SPEC, "import fs from 'node:fs';\nimport { homeTitle } from './home';\n\nexport const title = [fs, homeTitle];\n");
  mapTest(dir, NODE_SPEC, 'Tests the home title and the file system.');
  setTestedBy(dir, 'src/home.ts', tested(NODE_SPEC));
  // The scope first: the tsconfig does not parse, and the test loads home.ts by a relative import and imports node:fs.
  assert.ok(existsSync(join(dir, TSCONFIG)), 'tsconfig.json must exist');
  assert.ok(!parses(readAt(dir, TSCONFIG)), 'the tsconfig must not parse');
  assert.ok(readAt(dir, NODE_SPEC).includes("from 'node:fs'"), "the test must import 'node:fs'");
  assert.ok(readAt(dir, NODE_SPEC).includes("from './home'"), 'the test must load home.ts by a relative import');
  mustPass(check(dir));
});

test('T11j. a truncated tsconfig, and a test that loads the file by a relative import and holds a type-only import of a package: the link is found another way, so MAP11 passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  addTracked(dir, TSCONFIG, T11_TRUNCATED);
  addTracked(dir, TYPES_SPEC, "import type { X } from 'some-pkg';\nimport { homeTitle } from './home';\n\nexport type Shape = X;\nexport const title = homeTitle;\n");
  mapTest(dir, TYPES_SPEC, 'Tests the home title and a package type.');
  setTestedBy(dir, 'src/home.ts', tested(TYPES_SPEC));
  // The scope first: the tsconfig does not parse, and the test holds a type-only import of a package and a relative import of home.ts.
  assert.ok(existsSync(join(dir, TSCONFIG)), 'tsconfig.json must exist');
  assert.ok(!parses(readAt(dir, TSCONFIG)), 'the tsconfig must not parse');
  assert.ok(readAt(dir, TYPES_SPEC).includes("import type { X } from 'some-pkg'"), 'the test must hold a type-only import of a package');
  assert.ok(readAt(dir, TYPES_SPEC).includes("from './home'"), 'the test must load home.ts by a relative import');
  mustPass(check(dir));
});

test('T11k. a tsconfig that extends a missing package, and an alias-only test: the alias read is unknown, and MAP11 FAILs with an unknown read whose message names npm ci', () => {
  needFile(REL);
  const dir = scratchRepo();
  addTracked(dir, TSCONFIG, T11H_TSCONFIG);
  writeAliasSpec(dir, '@/home');
  setTestedBy(dir, 'src/home.ts', tested(ALIAS));
  // The scope first: the tsconfig exists and parses, it extends a package that is not installed, and the test imports by the alias only.
  assert.ok(existsSync(join(dir, TSCONFIG)), 'tsconfig.json must exist');
  assert.ok(parses(readAt(dir, TSCONFIG)), 'the tsconfig must parse as JSON: the missing package is the fault');
  assert.ok(!existsSync(join(dir, 'node_modules', '@acme')), 'the extended package must not be installed');
  importsBy(dir, ALIAS, '@/');
  const r = check(dir);
  mustFail(r, ALIAS);
  assert.match(map11(r), /unknown read: could not read src\/alias\.spec\.ts: .*npm ci/, `the unreadable tsconfig must make the alias read unknown, and its message must name npm ci\n${map11(r)}`);
});

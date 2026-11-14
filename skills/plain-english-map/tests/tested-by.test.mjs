// MAP11, the tested-by line. A test named on a `  - Tested by: ` line of a map line must load that map line's code file. It does so when
// it imports the file (a type-only import does not count), or imports one `index.*` or `__init__.py` that re-exports the file (one hop),
// or holds a string literal that is the file's path. A comment or a docstring never counts (rule `building-scanner-respects-strings`).
//
// Fixture: `tests/fixture/`. Its tested-by lines (docs/map/core.md) name src/home.spec.ts and src/pkg.spec.ts for src/home.ts, and
// src/retry_check.py and src/run_retry_check.py for src/retry.py. Each failing case edits its own scratch copy of the fixture, and each
// run goes through `scripts/map-check.mjs`. The spec file for T9 (the 4 to 5 upgrade) is format-version.test.mjs, case 2d: one home for the step.
//
// Red on the old code. The fixture holds formatVersion 6, and the old validator refuses a newer map before any check runs. So each case
// goes red on that refusal, and its output names it. Once the skill reads version 6, each case goes red on its own MAP11 verdict, which
// the old code never prints. Every MAP11 failure assertion names the page, the test and the file it is about.
//
// Assumed. The spec names the cases but not the messages, so these read the spec's own claims:
//   - an unindented tested-by line, a line with no backticks, and a `;` separator each fail, and the failure names the page (T7d to T7f).
//   - `import pkgpy` loads `pkgpy/__init__.py` by its package name (T8d, T8e).
//   - a map line whose tested-by line is missing passes: the line is optional (T1b).
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
//   T6   a shell test is read through its quoted string literals. A literal path passes (T6a, T6g, T6h). A `#` inside a string (T6c), a lone
//        quote in a comment (T6e) and a string that spans two lines (T6f) hide no path. A path only in a comment does not load the file (T6d).
//        A bare word (T6i) and a `$VAR` prefix (T6j) do not load the file: pinned gaps of debt `map-tested-by-no-shell`. A lone apostrophe in
//        a comment (T6k) and a path in a heredoc body (T6l, with the control T6m after its end line) follow the shell scanner.
//        With no python3 on PATH, a Python test fails as an unknown read, and with python3 it passes (T6b).
//   T7   placement and form. A tested-by line under a table line (T7a), a screen line (T7b) or a home (T7c) fails. Unindented (T7d), with no
//        backticks (T7e), or with a `;` separator (T7f), it fails. Under a map line after a decisions line (T7g), it passes.
//        Under a backtick line in a Notes section it is an orphan and fails (T7h): a tested-by line is valid only under a Code files map line.
//   T8   one hop. Through `src/pkg/index.ts`, the test passes (T8a). Without the re-export, it fails (T8b). Two hops fail (T8c).
//        Through `src/pkgpy/__init__.py`, the test passes (T8d). Without the re-export, it fails (T8e).
//   T10  an import by a tsconfig path alias. An alias that a `paths` entry maps passes (T10a). An alias no entry maps does not load the
//        file (T10b), and a type-only import by an alias does not count (T10c). A tsconfig with comments, trailing commas, and `//` and
//        `/*` inside a string still maps (T10d).
//   T11  a path built by `path.join` or `os.path.join` from literal pieces. A join that names the file passes (T11a, T11b), and a lone quote
//        in a comment before it hides nothing (T11e). A join of another file (T11c) and a join in a comment (T11d) do not load the file.
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

// A shell test is read through its string literals: `blankShell` keeps each string's text and blanks every comment.
const shellTest = (dir, body) => {
  writeAt(dir, 'src/retry_check.sh', body);
  gitIn(dir, 'add', '-N', 'src/retry_check.sh');
  setTestedBy(dir, 'src/retry.py', tested('src/retry_check.sh'));
};

test('T6a. a shell test that runs the file by its double-quoted literal path passes MAP11', () => {
  needFile(REL);
  const dir = scratchRepo();
  shellTest(dir, '#!/bin/sh\npython3 "src/retry.py"\n');
  // The scope first: the test names the file in a quoted string, from the repository root.
  assert.match(readAt(dir, 'src/retry_check.sh'), /python3 "src\/retry\.py"/, 'the shell test must run src/retry.py by a quoted path');
  mustPass(check(dir));
});

test('T6c. a # inside a string, before the quoted path on the same line, is no comment: the test passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  shellTest(dir, '#!/bin/sh\necho "#" && python3 "src/retry.py"\n');
  assert.match(readAt(dir, 'src/retry_check.sh'), /echo "#" && python3 "src\/retry\.py"/, 'the shell test must hold a # inside a string before the path');
  mustPass(check(dir));
});

test('T6d. a path that appears only in a shell comment does not load the file: MAP11 fails as a read that does not load, and names the test and the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  shellTest(dir, '#!/bin/sh\n# python3 "src/retry.py"\necho done\n');
  // The scope first: the path sits in the comment alone, and no line outside a comment names it.
  assert.doesNotMatch(readAt(dir, 'src/retry_check.sh').replace(/^#.*$/gm, ''), /src\/retry\.py/, 'the path must sit only in the comment');
  const r = check(dir);
  mustFail(r, 'src/retry_check.sh', 'src/retry.py');
  assert.doesNotMatch(map11(r), /unknown/, `the comment-only test must fail as a read that does not load, not as an unknown read\n${map11(r)}`);
});

test("T6e. a lone quote in a shell comment does not open a string that hides the path on the next line: the test passes", () => {
  needFile(REL);
  const dir = scratchRepo();
  shellTest(dir, "#!/bin/sh\n# one ' here: the path is on the next line\npython3 \"src/retry.py\"\n");
  assert.match(readAt(dir, 'src/retry_check.sh'), /^# one ' here/m, 'the comment must hold a lone quote');
  mustPass(check(dir));
});

test('T6f. a double-quoted string over two lines, whose second line starts with #, is text: the call after the string loads the file, and the test passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  shellTest(dir, '#!/bin/sh\nmsg="one\n# two"; python3 "src/retry.py"\n');
  assert.match(readAt(dir, 'src/retry_check.sh'), /^# two"; python3 "src\/retry\.py"$/m, 'the second line must open with # inside the string');
  mustPass(check(dir));
});

test('T6g. a shell test in src/ that runs `python3 "retry.py"` loads the file: the quoted path is read from the test folder', () => {
  needFile(REL);
  const dir = scratchRepo();
  shellTest(dir, '#!/bin/sh\npython3 "retry.py"\n');
  // The scope first: the quoted word is the file's name alone, so only the folder of the test can resolve it.
  assert.match(readAt(dir, 'src/retry_check.sh'), /python3 "retry\.py"/, 'the shell test must name the file from its own folder');
  mustPass(check(dir));
});

test("T6h. a shell test that runs `python3 'src/retry.py'` passes: a single-quoted literal is a string literal too", () => {
  needFile(REL);
  const dir = scratchRepo();
  shellTest(dir, "#!/bin/sh\npython3 'src/retry.py'\n");
  assert.match(readAt(dir, 'src/retry_check.sh'), /python3 'src\/retry\.py'/, 'the shell test must run src/retry.py by a single-quoted path');
  mustPass(check(dir));
});

// Known gap, debt `map-tested-by-no-shell`: the shell reader takes quoted strings only.
// A bare word does not load the file, so this case pins the gap. Once the reader reads bare words, this case goes red.
test('T6i. known gap: a bare word, `python3 src/retry.py`, does not load the file. MAP11 fails as a read that does not load', () => {
  needFile(REL);
  const dir = scratchRepo();
  shellTest(dir, '#!/bin/sh\npython3 src/retry.py\n');
  // The scope first: the path is a bare word, and no quoted string names it.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^python3 src\/retry\.py$/m, 'the shell test must run src/retry.py by a bare word');
  const r = check(dir);
  mustFail(r, 'src/retry_check.sh', 'src/retry.py');
  assert.match(map11(r), /does not load/, `the bare-word test must fail as a read that does not load\n${map11(r)}`);
  assert.doesNotMatch(map11(r), /unknown/, `the bare-word test must not fail as an unknown read\n${map11(r)}`);
});

// Known gap, the same debt: the reader does not expand a `$VAR` prefix, so this string names no tracked file.
test('T6j. known gap: a variable prefix, `"$ROOT/src/retry.py"`, does not load the file. MAP11 fails as a read that does not load', () => {
  needFile(REL);
  const dir = scratchRepo();
  shellTest(dir, '#!/bin/sh\npython3 "$ROOT/src/retry.py"\n');
  // The scope first: the only string of the test holds the variable form.
  assert.match(readAt(dir, 'src/retry_check.sh'), /python3 "\$ROOT\/src\/retry\.py"/, 'the shell test must run the file through a variable prefix');
  const r = check(dir);
  mustFail(r, 'src/retry_check.sh', 'src/retry.py');
  assert.match(map11(r), /does not load/, `the variable-prefix test must fail as a read that does not load\n${map11(r)}`);
  assert.doesNotMatch(map11(r), /unknown/, `the variable-prefix test must not fail as an unknown read\n${map11(r)}`);
});

test("T6k. a lone apostrophe in a shell comment opens no string. The single-quoted path on the next line is code, and the test passes", () => {
  needFile(REL);
  const dir = scratchRepo();
  shellTest(dir, "#!/bin/sh\n# the file's path is set below\npython3 'src/retry.py'\n");
  // The scope first: the comment holds an apostrophe, and the path sits on the line after it.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^# the file's path is set below$/m, 'the comment must hold an apostrophe');
  assert.match(readAt(dir, 'src/retry_check.sh'), /^python3 'src\/retry\.py'$/m, 'the shell test must run src/retry.py by a single-quoted path');
  mustPass(check(dir));
});

test('T6l. a quoted path in a heredoc body does not count. The body is text, so the test does not load the file, and MAP11 fails', () => {
  needFile(REL);
  const dir = scratchRepo();
  shellTest(dir, '#!/bin/sh\ncat <<EOF\npython3 "src/retry.py"\nEOF\necho done\n');
  // The scope first: the path sits in the heredoc body alone.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^cat <<EOF\npython3 "src\/retry\.py"\nEOF$/m, 'the heredoc body must hold the quoted path');
  const r = check(dir);
  mustFail(r, 'src/retry_check.sh', 'src/retry.py');
  assert.match(map11(r), /does not load/, `the heredoc-only test must fail as a read that does not load\n${map11(r)}`);
});

test('T6m. control: a quoted path after a heredoc end line is code. The test passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  shellTest(dir, '#!/bin/sh\ncat <<EOF\npython3 "src/retry.py"\nEOF\npython3 "src/retry.py"\n');
  // The scope first: the same heredoc as T6l, then the path again after its end line.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^EOF\npython3 "src\/retry\.py"$/m, 'the path must sit after the heredoc end line');
  mustPass(check(dir));
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

// A host with a tsconfig.json that maps `@/*` to the root. The file is tracked, so the check reads it as a host file would be read.
const aliasRepo = () => {
  const dir = scratchRepo();
  writeAt(dir, 'tsconfig.json', `${JSON.stringify({ compilerOptions: { paths: { '@/*': ['./*'] } } })}\n`);
  gitIn(dir, 'add', '-N', 'tsconfig.json');
  return dir;
};

test("T10a. a test that imports the file by a tsconfig path alias passes MAP11: '@/src/home' maps to src/home.ts through `paths`", () => {
  needFile(REL);
  const dir = aliasRepo();
  writeAt(dir, 'src/home.spec.ts', "import { homeTitle } from '@/src/home';\n");
  // The scope first: the test imports home.ts by the alias alone, and the tsconfig maps the alias.
  assert.match(readAt(dir, 'src/home.spec.ts'), /from '@\/src\/home'/, 'the test must import by the alias');
  assert.match(readAt(dir, 'tsconfig.json'), /"@\/\*"/, 'tsconfig.json must map @/*');
  setTestedBy(dir, 'src/home.ts', tested('src/home.spec.ts'));
  mustPass(check(dir));
});

test("T10b. control: an alias that no `paths` entry maps does not load the file, so the test fails MAP11 and is named", () => {
  needFile(REL);
  const dir = aliasRepo();
  writeAt(dir, 'src/home.spec.ts', "import { homeTitle } from '@lib/src/home';\n");
  assert.doesNotMatch(readAt(dir, 'tsconfig.json'), /@lib/, 'tsconfig.json must not map @lib');
  setTestedBy(dir, 'src/home.ts', tested('src/home.spec.ts'));
  mustFail(check(dir), CORE, 'src/home.spec.ts', 'src/home.ts');
});

test("T10c. control: a type-only import by an alias does not load the file, so the test fails MAP11 and is named", () => {
  needFile(REL);
  const dir = aliasRepo();
  writeAt(dir, 'src/home.spec.ts', "import type { homeTitle } from '@/src/home';\n");
  // The scope first: the test's only import is the type import, through the alias the tsconfig maps.
  assert.match(readAt(dir, 'src/home.spec.ts'), /^import type \{ homeTitle \} from '@\/src\/home';$/m, 'the test must hold the type-only alias import');
  setTestedBy(dir, 'src/home.ts', tested('src/home.spec.ts'));
  mustFail(check(dir), CORE, 'src/home.spec.ts');
});

// A tsconfig.json as a person writes it, with comments and trailing commas.
// The reader must read it, including `//` and `/*` inside a string value.
const COMMENTED_TSCONFIG = [
  '{',
  "  // the host's alias is set here",
  '  "compilerOptions": {',
  '    /* the root is the base */',
  '    "baseUrl": ".",',
  '    "paths": {',
  '      "@/*": ["./*"], // the alias maps the root',
  '    },',
  '  },',
  '  "note": "see https://example.test/* and // here",',
  '}',
  '',
].join('\n');

test("T10d. control: a tsconfig with comments, trailing commas, and `//` and `/*` in a string still maps the alias. An import by it passes MAP11", () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'tsconfig.json', COMMENTED_TSCONFIG);
  gitIn(dir, 'add', '-N', 'tsconfig.json');
  writeAt(dir, 'src/home.spec.ts', "import { homeTitle } from '@/src/home';\n");
  // The scope first: the file holds comments, a trailing comma and both openers in a string, and the test imports by the alias.
  assert.match(readAt(dir, 'tsconfig.json'), /"note": "see https:\/\/example\.test\/\* and \/\/ here",/, 'the string value must hold // and /*');
  assert.match(readAt(dir, 'tsconfig.json'), /^  \/\/ the host's alias is set here$/m, 'the comment must hold an apostrophe');
  assert.match(readAt(dir, 'tsconfig.json'), /\],[^\n]*\/\/ the alias maps the root\n    \},/, 'the paths object must end in a trailing comma');
  assert.match(readAt(dir, 'src/home.spec.ts'), /from '@\/src\/home'/, 'the test must import by the alias');
  setTestedBy(dir, 'src/home.ts', tested('src/home.spec.ts'));
  mustPass(check(dir));
});

test('T11a. a Python test that builds the file path by os.path.join("src", "retry.py") loads the file: MAP11 passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'tests/retry_join.py', 'import os\nimport subprocess\nimport sys\n\n\ndef test_runs_retry():\n    subprocess.run([sys.executable, os.path.join("src", "retry.py")], check=True)\n');
  gitIn(dir, 'add', '-N', 'tests/retry_join.py');
  // The scope first: the test imports no retry module, and no piece of the join names a file beside the test, so only the joined path can link retry.py.
  assert.doesNotMatch(readAt(dir, 'tests/retry_join.py'), /^(import|from) retry\b/m, 'the test must not import retry');
  assert.equal(existsSync(join(dir, 'tests', 'retry.py')), false, 'no file beside the test may be named retry.py');
  setTestedBy(dir, 'src/retry.py', tested('tests/retry_join.py'));
  mustPass(check(dir));
});

test("T11b. a TypeScript test that builds the file path by path.join('src', 'home.ts') loads the file: MAP11 passes", () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'tests/join.spec.ts', "import path from 'node:path';\n\nexport const homeFile = path.join('src', 'home.ts');\n");
  gitIn(dir, 'add', '-N', 'tests/join.spec.ts');
  // The scope first: the test imports no home module, and no piece of the join names a file beside the test, so only the joined path can link home.ts.
  assert.doesNotMatch(readAt(dir, 'tests/join.spec.ts'), /from '\.\/home'/, 'the test must not import home');
  assert.equal(existsSync(join(dir, 'tests', 'home.ts')), false, 'no file beside the test may be named home.ts');
  setTestedBy(dir, 'src/home.ts', tested('tests/join.spec.ts'));
  mustPass(check(dir));
});

test('T11c. control: a Python join that names another file, os.path.join("src", "retry_check.py"), does not load retry.py: MAP11 fails and names the test', () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'tests/retry_join.py', 'import os\n\n\ndef test_other():\n    assert os.path.join("src", "retry_check.py")\n');
  gitIn(dir, 'add', '-N', 'tests/retry_join.py');
  assert.match(readAt(dir, 'tests/retry_join.py'), /os\.path\.join\("src", "retry_check\.py"\)/, 'the test must join the other file');
  setTestedBy(dir, 'src/retry.py', tested('tests/retry_join.py'));
  mustFail(check(dir), CORE, 'tests/retry_join.py', 'src/retry.py');
});

test("T11d. control: a join in a TypeScript comment, // path.join('src', 'home.ts'), does not load the file: MAP11 fails and names the test", () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'tests/join.spec.ts', "// path.join('src', 'home.ts') is only a comment here\nexport {};\n");
  gitIn(dir, 'add', '-N', 'tests/join.spec.ts');
  assert.doesNotMatch(readAt(dir, 'tests/join.spec.ts').replace(/^\/\/.*$/gm, ''), /home\.ts/, 'the join must sit only in the comment');
  setTestedBy(dir, 'src/home.ts', tested('tests/join.spec.ts'));
  mustFail(check(dir), CORE, 'tests/join.spec.ts', 'src/home.ts');
});

test("T11e. a lone quote in a TypeScript comment does not hide the join on the next line: the test passes", () => {
  needFile(REL);
  const dir = scratchRepo();
  writeAt(dir, 'tests/join.spec.ts', "// one ' here: the join is on the next line\nimport path from 'node:path';\nexport const homeFile = path.join('src', 'home.ts');\n");
  gitIn(dir, 'add', '-N', 'tests/join.spec.ts');
  assert.match(readAt(dir, 'tests/join.spec.ts'), /^\/\/ one ' here/m, 'the comment must hold a lone quote');
  setTestedBy(dir, 'src/home.ts', tested('tests/join.spec.ts'));
  mustPass(check(dir));
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

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
//   T6   a shell test loads the file when it runs it by a literal path from the root (T6a) or from its own folder (T6c), or by a
//        variable anchor bound to a folder, then a literal tail (T6i, T6m, T6t, T6u, T6v). An unbound name, or one bound to a mktemp
//        folder, is no anchor (T6r, T6s). The tail resolves from the bound place only (T6x). A literal path bound to NAME loads it (T6w).
//        A `#` in a string, a comment or heredoc with a lone quote, `$#`, and a string over
//        two lines do not hide the call (T6e, T6g, T6h, T6l, T6o). A path only in a comment (T6d) or a heredoc body (T6f), no path (T6k),
//        or a non-literal tail (T6n), or a single-quoted word that stays literal (T6p), fails as a read that does not load, not as an
//        unknown read. A `.zsh` test with a lone quote in its first-line comment is read as a shell test (T6q). A Ruby test stays an unknown read (T6j).
//        With no python3 on PATH, a Python test fails as an unknown read, and with python3 it passes (T6b).
//        A bound anchor counts: a two-step binding (T6y), a default-value word `${NAME:-$REPO_ROOT/x}` (T6z), `export`, `readonly`,
//        `dirname --` and a copied alias (T6aa to T6ae). `${0%/*}`, `${BASH_SOURCE...}`, `pwd -P`, a `$OTHER/..` chain and a .zsh
//        binding (T6af to T6ai, T6aj, T6an) count too. An environment name (T6ak), a function argument (T6al) and a name bound on
//        two branches to two places (T6am) count for nothing.
//        The edges of the bound-anchor rule: a bind to a mktemp folder after a known place counts for nothing (T6ao), a default
//        value in a bind counts (T6ap), two places for one name count for nothing (T6aq), a use before the bind does not count (T6ar),
//        a bind inside a string, on its own line (T6as) or after `;` in a string (T6at), and a bare `$BASH_SOURCE` base counts (T6au).
//        A literal default `${NAME:-src/retry.py}` counts as that literal path (T6av). A rebind by `local`, `for`, `read`, or by
//        `NAME=$OTHER` after `&&` or `||`, counts for nothing, even when it names the same place (T6aw to T6ba). `cd --`, `dirname`
//        of a bound name (its parent place), `readlink -f` and `realpath` of a bound place count as that place (T6bb to T6bf).
//   T7   placement and form. A tested-by line under a table line (T7a), a screen line (T7b) or a home (T7c) fails. Unindented (T7d), with no
//        backticks (T7e), or with a `;` separator (T7f), it fails. Under a map line after a decisions line (T7g), it passes.
//        Under a backtick line in a Notes section it is an orphan and fails (T7h): a tested-by line is valid only under a Code files map line.
//   T8   one hop. Through `src/pkg/index.ts`, the test passes (T8a). Without the re-export, it fails (T8b). Two hops fail (T8c).
//        Through `src/pkgpy/__init__.py`, the test passes (T8d). Without the re-export, it fails (T8e).
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
/** MAP11 passes. `cause`, when given, names the one form the test checks, and is the message on a FAIL. */
const mustPass = (r, cause = 'MAP11 must PASS on this map') => assert.match(map11(r), /^\[PASS\] MAP11\b/, `${cause}\n${shown(r)}`);
/** MAP11 fails on `rel` and says the test does not load the file. An unknown read is a different failure, and it fails this check first. `cause`, when given, names the form the case checks, and is the message when the verdict is not a FAIL. */
const mustNotLoad = (r, rel, cause = 'MAP11 must FAIL on this map') => {
  assert.match(map11(r), /^\[FAIL\] MAP11\b/, `${cause}\n${shown(r)}`);
  mustFail(r, rel);
  const line = map11(r);
  assert.doesNotMatch(line, /unknown read|could not read/, `MAP11 must judge ${rel} as a read that loads nothing, not as an unknown read\n${line}`);
  assert.match(line, /does not load/, `MAP11 must say ${rel} does not load the file\n${line}`);
};
/** Writes the test file `rel` of a scratch repository, marks it `git add -N`, and names it alone on the tested-by line of src/retry.py. */
const soleTest = (dir, rel, body) => {
  writeAt(dir, rel, body);
  gitIn(dir, 'add', '-N', rel);
  setTestedBy(dir, 'src/retry.py', tested(rel));
};

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

test('T6a. a shell test that runs the file by its literal path from the repository root passes MAP11', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\npython3 src/retry.py\n');
  // The scope first: the shell test runs the file by the path from the root, and the file is the only line that names it.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^python3 src\/retry\.py$/m, 'the shell test must run src/retry.py by its root path');
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

test('T6c. a shell test in src/ that runs `python3 "retry.py"` passes: the word is the path from the test folder, and quotes are removed', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\npython3 "retry.py"\n');
  // The scope first: `retry.py` names the file only from the test's folder src/, so the root must hold no retry.py.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^python3 "retry\.py"$/m, 'the shell test must run "retry.py" in quotes');
  assert.equal(existsSync(join(dir, 'retry.py')), false, 'the root must hold no retry.py');
  mustPass(check(dir));
});

test('T6d. a shell test that names the file only in a comment does not load it: MAP11 fails as a read that does not load', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\n# runs src/retry.py later\necho ok\n');
  // The scope first: the path sits in a comment line, and no line outside a comment names it.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^# runs src\/retry\.py later$/m, 'the path must sit in a comment');
  assert.doesNotMatch(readAt(dir, 'src/retry_check.sh').split('\n').filter((l) => !l.startsWith('#')).join('\n'), /retry\.py/, 'no line outside a comment may name the file');
  mustNotLoad(check(dir), 'src/retry_check.sh');
});

test('T6e. a shell test with `echo "#"; python3 src/retry.py` passes: a # inside a string is no comment, so the call after it loads the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\necho "#"; python3 src/retry.py\n');
  assert.match(readAt(dir, 'src/retry_check.sh'), /^echo "#"; python3 src\/retry\.py$/m, 'the # must sit in a string before the call');
  mustPass(check(dir));
});

test('T6f. a shell test that names the file only in a quoted heredoc body does not load it: MAP11 fails as a read that does not load', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', "#!/bin/sh\ncat <<'EOF'\npython3 src/retry.py\nEOF\n");
  // The scope first: the path is the body of a heredoc, and no line after its end runs it.
  assert.match(readAt(dir, 'src/retry_check.sh'), /<<'EOF'\npython3 src\/retry\.py\nEOF\n/, 'the path must be the body of a quoted heredoc');
  mustNotLoad(check(dir), 'src/retry_check.sh');
});

test('T6g. a shell test with a heredoc that holds a lone quote, then `python3 src/retry.py` after its end, passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', "#!/bin/sh\ncat <<EOF\ndon't\nEOF\npython3 src/retry.py\n");
  assert.match(readAt(dir, 'src/retry_check.sh'), /<<EOF\ndon't\nEOF\npython3 src\/retry\.py\n/, 'the lone quote must sit in a heredoc body, before the call');
  mustPass(check(dir));
});

test('T6h. a shell test with a comment that holds a lone quote, then `python3 src/retry.py`, passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', "#!/bin/sh\n# don't\npython3 src/retry.py\n");
  assert.match(readAt(dir, 'src/retry_check.sh'), /^# don't\npython3 src\/retry\.py$/m, 'the lone quote must sit in a comment, on the line before the call');
  mustPass(check(dir));
});

test('T6i. a shell test with `ROOT=$(dirname "$0")/..` then `python3 "$ROOT/src/retry.py"` passes: ROOT is bound to the test folder, and the tail resolves from the root', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nROOT=$(dirname "$0")/..\npython3 "$ROOT/src/retry.py"\n');
  // The scope first: ROOT is bound by an assignment, and the tail resolves from the root only. src/src/retry.py must not exist, or the pass says nothing about the root.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^ROOT=\$\(dirname "\$0"\)\/\.\.$/m, 'ROOT must be bound to the test folder and its parent');
  assert.match(readAt(dir, 'src/retry_check.sh'), /^python3 "\$ROOT\/src\/retry\.py"$/m, 'the shell test must run the file through $ROOT');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustPass(check(dir));
});

test('T6j. control: a Ruby test that names the file in a string still fails MAP11 as an unknown read: the shell reader does not cover Ruby', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.rb', 'system("python3 src/retry.py")\n');
  // The scope first: the path sits in a string, so a reader that took any string would pass this test.
  assert.match(readAt(dir, 'src/retry_check.rb'), /system\("python3 src\/retry\.py"\)/, 'the Ruby test must name the file in a string');
  const r = check(dir);
  mustFail(r, 'src/retry_check.rb');
  assert.match(map11(r), /unknown read: could not read src\/retry_check\.rb/, `MAP11 must judge the Ruby test as an unknown read\n${map11(r)}`);
});

test('T6k. a shell test that names no file does not load it: MAP11 fails as a read that does not load', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\necho ok\n');
  // The scope first: no line of the test names the file or its name.
  assert.doesNotMatch(readAt(dir, 'src/retry_check.sh'), /retry/, 'the shell test must name no retry file');
  mustNotLoad(check(dir), 'src/retry_check.sh');
});

test('T6l. a shell test with `[ $# -eq 0 ] && python3 src/retry.py` passes: $# is a parameter count, not a comment, so the call after it loads the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\n[ $# -eq 0 ] && python3 src/retry.py\n');
  assert.match(readAt(dir, 'src/retry_check.sh'), /^\[ \$# -eq 0 \] && python3 src\/retry\.py$/m, 'the $# must sit before the call');
  mustPass(check(dir));
});

test('T6m. a shell test in src/ with `here=$(dirname "$0")` then `python3 "${here}/retry.py"` passes: here is bound to the test folder, and the tail resolves from it', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nhere=$(dirname "$0")\npython3 "${here}/retry.py"\n');
  // The scope first: here is bound by an assignment, and the tail resolves from the test folder src/ only, so the root must hold no retry.py.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^here=\$\(dirname "\$0"\)$/m, 'here must be bound to the test folder');
  assert.match(readAt(dir, 'src/retry_check.sh'), /^python3 "\$\{here\}\/retry\.py"$/m, 'the shell test must run the file through ${here}');
  assert.equal(existsSync(join(dir, 'retry.py')), false, 'the root must hold no retry.py');
  mustPass(check(dir));
});

test('T6n. a shell test with `python3 "$ROOT/$NAME"` does not load the file: a variable tail is not a literal path, so MAP11 fails as a read that does not load', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\npython3 "$ROOT/$NAME"\n');
  // The scope first: no literal retry name is in the test, so only a variable tail could reach the file.
  assert.doesNotMatch(readAt(dir, 'src/retry_check.sh'), /retry/, 'the shell test must name no retry file literally');
  mustNotLoad(check(dir), 'src/retry_check.sh');
});

test('T6o. a shell test with a double-quoted string over two lines, its second line starting with #, then `; python3 src/retry.py`, passes: the # is inside the string', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\necho "one\n# two"; python3 src/retry.py\n');
  // The scope first: the second line starts with #, and that # sits inside the string opened on the line before.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^echo "one\n# two"; python3 src\/retry\.py$/m, 'the # must start a line inside a string that began on the line before');
  mustPass(check(dir));
});

test("T6p. a shell test with `python3 '$ROOT/src/retry.py'` does not load the file: single quotes keep the text literal, so the word is not a path, and MAP11 fails as a read that does not load", () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', "#!/bin/sh\npython3 '$ROOT/src/retry.py'\n");
  // The scope first: the call is single-quoted, so no expansion of $ROOT takes place.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^python3 '\$ROOT\/src\/retry\.py'$/m, 'the shell test must run the file through single quotes');
  mustNotLoad(check(dir), 'src/retry_check.sh');
});

test("T6q. a .zsh shell test whose first line is a comment with a lone quote, then `python3 src/retry.py`, passes: the shell reader reads .zsh", () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.zsh', "# don't\npython3 src/retry.py\n");
  // The scope first: the lone quote is on the first line, in a comment, and the call follows it.
  assert.match(readAt(dir, 'src/retry_check.zsh'), /^# don't\npython3 src\/retry\.py$/m, 'the lone quote must sit in a comment on the first line');
  mustPass(check(dir));
});

test('T6r. a shell test that binds `$dir` by mktemp and writes `$dir/src/retry.py` does not load the file: the name is no folder anchor, so MAP11 fails as a read that does not load', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\ndir=$(mktemp -d); printf x > "$dir/src/retry.py"\n');
  // The scope first: src/retry.py exists, so a tail resolved from the root would load it. The shell test writes through $dir.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^dir=\$\(mktemp -d\); printf x > "\$dir\/src\/retry\.py"$/m, 'the shell test must write through $dir');
  assert.ok(existsSync(join(dir, 'src/retry.py')), 'src/retry.py must exist, so the tail would resolve from the root');
  mustNotLoad(check(dir), 'src/retry_check.sh');
});

test('T6s. a shell test with `python3 "$ROOT/src/retry.py"` and no ROOT assignment does not load the file: an unbound name is no anchor, so MAP11 fails as a read that does not load', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\npython3 "$ROOT/src/retry.py"\n');
  // The scope first: no line of the test assigns ROOT, and the tail would resolve from the root, where src/retry.py is.
  assert.doesNotMatch(readAt(dir, 'src/retry_check.sh'), /ROOT=/, 'the shell test must not assign ROOT');
  assert.ok(existsSync(join(dir, 'src/retry.py')), 'src/retry.py must exist, so the tail would resolve from the root');
  mustNotLoad(check(dir), 'src/retry_check.sh');
});

test('T6t. a shell test in src/ with `here=$(cd "$(dirname "$0")" && pwd); python3 "$here/retry.py"` passes: here is bound to the test folder, and the tail resolves from it', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nhere=$(cd "$(dirname "$0")" && pwd); python3 "$here/retry.py"\n');
  // The scope first: the root must hold no retry.py, so only the test folder src/ can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^here=\$\(cd "\$\(dirname "\$0"\)" && pwd\); python3 "\$here\/retry\.py"$/m, 'the shell test must bind here and run the file through it');
  assert.equal(existsSync(join(dir, 'retry.py')), false, 'the root must hold no retry.py');
  mustPass(check(dir));
});

test('T6u. a shell test in src/ with `ROOT=$(cd "$(dirname "$0")/.." && pwd); python3 "$ROOT/src/retry.py"` passes: ROOT is bound to the root, and the tail resolves from it', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nROOT=$(cd "$(dirname "$0")/.." && pwd); python3 "$ROOT/src/retry.py"\n');
  // The scope first: src/src/retry.py must not exist, so only the root can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^ROOT=\$\(cd "\$\(dirname "\$0"\)\/\.\." && pwd\); python3 "\$ROOT\/src\/retry\.py"$/m, 'the shell test must bind ROOT and run the file through it');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustPass(check(dir));
});

test('T6v. a shell test in src/ with `ROOT="$(dirname "$0")/.."; python3 "$ROOT/src/retry.py"` passes: ROOT is bound to the root, and the tail resolves from it', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nROOT="$(dirname "$0")/.."; python3 "$ROOT/src/retry.py"\n');
  // The scope first: src/src/retry.py must not exist, so only the root can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^ROOT="\$\(dirname "\$0"\)\/\.\."; python3 "\$ROOT\/src\/retry\.py"$/m, 'the shell test must bind ROOT and run the file through it');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustPass(check(dir));
});

test('T6w. a shell test in src/ with `SCRIPT=src/retry.py; python3 "$SCRIPT"` passes: the assignment value is a literal path word, and the NAME= drop reads it as that path', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nSCRIPT=src/retry.py; python3 "$SCRIPT"\n');
  // The scope first: SCRIPT is bound to a literal path, not to a folder, and src/src/retry.py must not exist, so the path resolves from the root only.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^SCRIPT=src\/retry\.py; python3 "\$SCRIPT"$/m, 'the shell test must bind SCRIPT to a literal path');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustPass(check(dir));
});

test('T6x. a shell test in src/ with `here=$(dirname "$0")` then `python3 "$here/src/retry.py"` does not load the file: the tail resolves from the bound folder only, so the root path src/retry.py is no candidate', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nhere=$(dirname "$0")\npython3 "$here/src/retry.py"\n');
  // The scope first: src/retry.py exists, so a tail resolved from the root would load it, and src/src/retry.py does not exist.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^python3 "\$here\/src\/retry\.py"$/m, 'the shell test must run the file through $here/src');
  assert.ok(existsSync(join(dir, 'src/retry.py')), 'src/retry.py must exist, so the root path would load it');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustNotLoad(check(dir), 'src/retry_check.sh');
});

test('T6y. a shell test with `HERE=$(cd "$(dirname "$0")" && pwd)`, then `REPO_ROOT="$(cd "$HERE/.." && pwd)"`, then `cp "$REPO_ROOT/src/retry.py" ...` passes: REPO_ROOT is HERE plus `/..`, so the tail resolves from the root', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="$(cd "$(dirname "$0")" && pwd)"\nREPO_ROOT="$(cd "$HERE/.." && pwd)"\ncp "$REPO_ROOT/src/retry.py" "$HERE/retry_copy.py"\n');
  // The scope first: the two-step binding is in the test, and src/src/retry.py must not exist, or a tail from HERE would pass for the wrong reason.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^REPO_ROOT="\$\(cd "\$HERE\/\.\." && pwd\)"$/m, 'REPO_ROOT must be bound to HERE with a literal /..');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustPass(check(dir), 'REPO_ROOT, bound to HERE plus /.., must count as the root: the tail $REPO_ROOT/src/retry.py loads the file');
});

test('T6z. a shell test with `SETUP_SH="${CLOUD_SETUP_SH_UNDER_TEST:-$REPO_ROOT/src/retry.py}"`, then `python3 "$SETUP_SH"`, passes: the default-value word names the root path (the shape of hooks/test_cloud_setup.sh)', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nREPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"\nSETUP_SH="${CLOUD_SETUP_SH_UNDER_TEST:-$REPO_ROOT/src/retry.py}"\npython3 "$SETUP_SH"\n');
  // The scope first: REPO_ROOT is bound directly, so only the default-value word is new here. src/src/retry.py must not exist.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^SETUP_SH="\$\{CLOUD_SETUP_SH_UNDER_TEST:-\$REPO_ROOT\/src\/retry\.py\}"$/m, 'the shell test must default SETUP_SH to $REPO_ROOT/src/retry.py');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustPass(check(dir), 'a ${NAME:-$REPO_ROOT/src/retry.py} default must count as the load of its path: the word after :- is the root path, and SETUP_SH is run');
});

test('T6aa. a shell test with `export ROOT="$(dirname "$0")/.."`, then `python3 "$ROOT/src/retry.py"`, passes: export is an assignment, so ROOT is bound to the root', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nexport ROOT="$(dirname "$0")/.."\npython3 "$ROOT/src/retry.py"\n');
  // The scope first: the line starts with export, and src/src/retry.py must not exist, so only the root can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^export ROOT="\$\(dirname "\$0"\)\/\.\."$/m, 'the shell test must export ROOT');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustPass(check(dir), 'export ROOT=... must bind ROOT the way a plain ROOT=... does, so the tail $ROOT/src/retry.py loads the file');
});

test('T6ab. a shell test with `readonly HERE="$(dirname "$0")"`, then `python3 "$HERE/retry.py"`, passes: readonly is an assignment, so HERE is bound to the test folder', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nreadonly HERE="$(dirname "$0")"\npython3 "$HERE/retry.py"\n');
  // The scope first: the line starts with readonly, and the root must hold no retry.py, so only the test folder can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^readonly HERE="\$\(dirname "\$0"\)"$/m, 'the shell test must make HERE readonly');
  assert.equal(existsSync(join(dir, 'retry.py')), false, 'the root must hold no retry.py');
  mustPass(check(dir), 'readonly HERE=... must bind HERE the way a plain HERE=... does, so the tail $HERE/retry.py loads the file');
});

test('T6ac. a shell test with `HERE="$(dirname -- "$0")"`, then `python3 "$HERE/retry.py"`, passes: the `--` ends the options, so HERE is bound to the test folder', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="$(dirname -- "$0")"\npython3 "$HERE/retry.py"\n');
  // The scope first: the dirname call carries --, and the root must hold no retry.py, so only the test folder can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^HERE="\$\(dirname -- "\$0"\)"$/m, 'the shell test must call dirname with --');
  assert.equal(existsSync(join(dir, 'retry.py')), false, 'the root must hold no retry.py');
  mustPass(check(dir), 'a $(dirname -- "$0") binding must count as the test folder, as $(dirname "$0") does: the tail $HERE/retry.py loads the file');
});

test('T6ad. a shell test with `HERE="$(dirname "$0")"`, `B=$HERE`, then `python3 "$B/retry.py"`, passes: B is an alias of the bound HERE', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="$(dirname "$0")"\nB=$HERE\npython3 "$B/retry.py"\n');
  // The scope first: B is set from HERE with no tail, and the root must hold no retry.py, so only the test folder can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^B=\$HERE$/m, 'the shell test must set B from HERE');
  assert.equal(existsSync(join(dir, 'retry.py')), false, 'the root must hold no retry.py');
  mustPass(check(dir), 'an unquoted alias B=$HERE of a bound name must bind B to the same place: the tail $B/retry.py loads the file');
});

test('T6ae. a shell test with `HERE="$(dirname "$0")"`, `B="$HERE"`, then `python3 "$B/retry.py"`, passes: B is a quoted alias of the bound HERE', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="$(dirname "$0")"\nB="$HERE"\npython3 "$B/retry.py"\n');
  // The scope first: B is set from HERE in double quotes, and the root must hold no retry.py, so only the test folder can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^B="\$HERE"$/m, 'the shell test must set B to "$HERE"');
  assert.equal(existsSync(join(dir, 'retry.py')), false, 'the root must hold no retry.py');
  mustPass(check(dir), 'a quoted alias B="$HERE" of a bound name must bind B to the same place: the tail $B/retry.py loads the file');
});

test('T6af. control, green on the old code and the new: a shell test with `HERE="${0%/*}"`, then `python3 "$HERE/retry.py"`, passes: ${0%/*} is the test folder', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="${0%/*}"\npython3 "$HERE/retry.py"\n');
  // The scope first: the root must hold no retry.py, so only the test folder can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^HERE="\$\{0%\/\*\}"$/m, 'the shell test must bind HERE to ${0%/*}');
  assert.equal(existsSync(join(dir, 'retry.py')), false, 'the root must hold no retry.py');
  mustPass(check(dir));
});

test('T6ag. control, green: a shell test with `HERE="$(dirname "${BASH_SOURCE[0]}")"`, then `python3 "$HERE/retry.py"`, passes: BASH_SOURCE[0] stands for $0', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/bash\nHERE="$(dirname "${BASH_SOURCE[0]}")"\npython3 "$HERE/retry.py"\n');
  // The scope first: the root must hold no retry.py, so only the test folder can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^HERE="\$\(dirname "\$\{BASH_SOURCE\[0\]\}"\)"$/m, 'the shell test must bind HERE through BASH_SOURCE[0]');
  assert.equal(existsSync(join(dir, 'retry.py')), false, 'the root must hold no retry.py');
  mustPass(check(dir));
});

test('T6ah. control, green: a shell test with `HERE="${BASH_SOURCE%/*}"`, then `python3 "$HERE/retry.py"`, passes: BASH_SOURCE stands for $0 in ${BASH_SOURCE%/*}', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/bash\nHERE="${BASH_SOURCE%/*}"\npython3 "$HERE/retry.py"\n');
  // The scope first: the root must hold no retry.py, so only the test folder can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^HERE="\$\{BASH_SOURCE%\/\*\}"$/m, 'the shell test must bind HERE to ${BASH_SOURCE%/*}');
  assert.equal(existsSync(join(dir, 'retry.py')), false, 'the root must hold no retry.py');
  mustPass(check(dir));
});

test('T6ai. control, green: a shell test with `HERE="$(cd "$(dirname "$0")" && pwd -P)"`, then `python3 "$HERE/retry.py"`, passes: pwd -P gives the test folder', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="$(cd "$(dirname "$0")" && pwd -P)"\npython3 "$HERE/retry.py"\n');
  // The scope first: the root must hold no retry.py, so only the test folder can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^HERE="\$\(cd "\$\(dirname "\$0"\)" && pwd -P\)"$/m, 'the shell test must bind HERE with pwd -P');
  assert.equal(existsSync(join(dir, 'retry.py')), false, 'the root must hold no retry.py');
  mustPass(check(dir));
});

test('T6aj. control, green: a shell test with `HERE="$(dirname "$0")"`, `UP="$HERE/.."`, then `python3 "$UP/src/retry.py"`, passes: UP chains up one folder from HERE', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="$(dirname "$0")"\nUP="$HERE/.."\npython3 "$UP/src/retry.py"\n');
  // The scope first: UP is HERE plus /.., and src/src/retry.py must not exist, so only the root can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^UP="\$HERE\/\.\."$/m, 'the shell test must bind UP to HERE plus /..');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustPass(check(dir));
});

test('T6ak. control, green: a shell test with `python3 "$TMPDIR/src/retry.py"` and no TMPDIR assignment does not load the file: an environment name is no anchor, so MAP11 fails as a read that does not load', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\npython3 "$TMPDIR/src/retry.py"\n');
  // The scope first: no line assigns TMPDIR, and src/retry.py exists, so a tail resolved from the root would load it.
  assert.doesNotMatch(readAt(dir, 'src/retry_check.sh'), /TMPDIR=/, 'the shell test must not assign TMPDIR');
  assert.ok(existsSync(join(dir, 'src/retry.py')), 'src/retry.py must exist, so the tail would resolve from the root');
  mustNotLoad(check(dir), 'src/retry_check.sh');
});

test('T6al. control, green: a shell test whose function sets `ROOT="$1"`, called as `use "$(dirname "$0")"`, does not load the file: a function argument is no anchor, so MAP11 fails as a read that does not load', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nuse() {\n  ROOT="$1"\n  python3 "$ROOT/src/retry.py"\n}\nuse "$(dirname "$0")"\n');
  // The scope first: ROOT is set from the first argument, which is the test folder. src/src/retry.py must not exist, so the file is not loaded.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^ {2}ROOT="\$1"$/m, 'the shell test must set ROOT from its first argument');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustNotLoad(check(dir), 'src/retry_check.sh');
});

test('T6am. a shell test that binds ROOT to the test folder on one branch and to the root on the other, then `python3 "$ROOT/src/retry.py"`, does not load the file: a name with two places is no static anchor', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nif [ "$1" = up ]; then\n  ROOT="$(dirname "$0")"\nelse\n  ROOT="$(dirname "$0")/.."\nfi\npython3 "$ROOT/src/retry.py"\n');
  // The scope first: each branch binds ROOT to a different place, and src/src/retry.py must not exist, so one branch does not load the file.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^ {2}ROOT="\$\(dirname "\$0"\)"$/m, 'the then branch must bind ROOT to the test folder');
  assert.match(readAt(dir, 'src/retry_check.sh'), /^ {2}ROOT="\$\(dirname "\$0"\)\/\.\."$/m, 'the else branch must bind ROOT to the root');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  const r = check(dir);
  assert.match(map11(r), /^\[FAIL\] MAP11\b/, `ROOT bound to two places on two branches counts for nothing, so MAP11 must FAIL: the reader loaded the file from the else branch\n${shown(r)}`);
  mustNotLoad(r, 'src/retry_check.sh');
});

test('T6an. control, green: a .zsh shell test with `HERE="$(cd "$(dirname "$0")" && pwd)"`, then `python3 "$HERE/retry.py"`, passes: the bound-anchor rule reads .zsh as shell', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.zsh', '#!/bin/zsh\nHERE="$(cd "$(dirname "$0")" && pwd)"\npython3 "$HERE/retry.py"\n');
  // The scope first: the root must hold no retry.py, so only the test folder can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.zsh'), /^HERE="\$\(cd "\$\(dirname "\$0"\)" && pwd\)"$/m, 'the .zsh test must bind HERE to the test folder');
  assert.equal(existsSync(join(dir, 'retry.py')), false, 'the root must hold no retry.py');
  mustPass(check(dir));
});

test('T6ao. a name bound to a known place, then bound to `$(mktemp -d)`, counts for nothing: a shell test with `ROOT="$(dirname "$0")/.."`, `ROOT=$(mktemp -d)`, then `python3 "$ROOT/src/retry.py"` does not load the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nROOT="$(dirname "$0")/.."\nROOT=$(mktemp -d)\npython3 "$ROOT/src/retry.py"\n');
  // The scope first: the first bind names the root, which holds src/retry.py, so that bind alone would load the file.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^ROOT="\$\(dirname "\$0"\)\/\.\."$/m, 'the first bind must name the root');
  assert.match(readAt(dir, 'src/retry_check.sh'), /^ROOT=\$\(mktemp -d\)$/m, 'the second bind must name a mktemp folder');
  assert.ok(existsSync(join(dir, 'src/retry.py')), 'src/retry.py must exist, so the first bind would load it');
  mustNotLoad(check(dir), 'src/retry_check.sh', 'ROOT has a bind to no known place, so it counts for nothing and MAP11 must FAIL: the reader kept the first bind');
});

test('T6ap. a default inside a bind value counts: a shell test with `HERE="$(dirname "$0")"`, `ROOT=${CLOUD_ROOT:-$HERE/..}`, then `python3 "$ROOT/src/retry.py"` passes: the default resolves from HERE, so ROOT is the root', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="$(dirname "$0")"\nROOT=${CLOUD_ROOT:-$HERE/..}\npython3 "$ROOT/src/retry.py"\n');
  // The scope first: the default sits in the bind, and src/src/retry.py must not exist, so only the root can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^ROOT=\$\{CLOUD_ROOT:-\$HERE\/\.\.\}$/m, 'ROOT must be bound to a default that names HERE');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustPass(check(dir), 'a default ${X:-$HERE/..} in a bind value must bind ROOT to the root, so the tail $ROOT/src/retry.py loads the file');
});

test('T6aq. two places for one name count for nothing: a shell test that binds ROOT to the root, then to the test folder, then runs `$ROOT/src/retry.py` and `$ROOT/retry.py`, does not load the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nROOT="$(dirname "$0")/.."\nROOT="$(dirname "$0")"\npython3 "$ROOT/src/retry.py"\npython3 "$ROOT/retry.py"\n');
  // The scope first: each place reaches src/retry.py by one of the two calls, so a first-bind or a last-bind reading would load it.
  assert.equal(readAt(dir, 'src/retry_check.sh').match(/^ROOT=/gm)?.length, 2, 'ROOT must be bound twice');
  assert.ok(existsSync(join(dir, 'src/retry.py')), 'src/retry.py must exist, so the test-folder place would load it');
  assert.equal(existsSync(join(dir, 'retry.py')), false, 'the root must hold no retry.py, so the second call reaches src/retry.py only from the test folder');
  mustNotLoad(check(dir), 'src/retry_check.sh', 'ROOT names two places, so it counts for nothing and MAP11 must FAIL: the reader took one of the two binds');
});

test('T6ar. a use before the bind does not count: a shell test with `python3 "$HERE/retry.py"`, then `HERE="$(dirname "$0")"`, does not load the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\npython3 "$HERE/retry.py"\nHERE="$(dirname "$0")"\n');
  // The scope first: the call comes before the bind, and src/retry.py exists, so the bind alone would load the file from the test folder.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^python3 "\$HERE\/retry\.py"\nHERE=/m, 'the call must come before the bind');
  assert.ok(existsSync(join(dir, 'src/retry.py')), 'src/retry.py must exist');
  mustNotLoad(check(dir), 'src/retry_check.sh', 'HERE is bound only after the call, so the call has no anchor and MAP11 must FAIL: the reader counted the later bind');
});

test(`T6as. a bind inside a multi-line single-quoted string is text: a shell test whose \`echo\` string holds \`HERE="$(dirname "$0")"\` on its own line, then \`python3 "$HERE/retry.py"\`, does not load the file`, () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', `#!/bin/sh\necho '\nHERE="$(dirname "$0")"\n'\npython3 "$HERE/retry.py"\n`);
  // The scope first: the bind sits inside a single-quoted string over three lines, and src/retry.py exists, so a counted bind would load it.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^echo '\nHERE="\$\(dirname "\$0"\)"\n'$/m, 'the bind must sit inside a string over three lines');
  assert.ok(existsSync(join(dir, 'src/retry.py')), 'src/retry.py must exist');
  mustNotLoad(check(dir), 'src/retry_check.sh', 'a bind inside a multi-line string is text, so HERE has no bind and MAP11 must FAIL: the reader took the string line as a bind');
});

test('T6at. a bind after `;` inside a single-quoted string is text: a shell test whose `echo` string holds a `;` then `HERE=...`, then `python3 "$HERE/retry.py"`, does not load the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', `#!/bin/sh\necho 'a; HERE="$(dirname "$0")"; b'\npython3 "$HERE/retry.py"\n`);
  // The scope first: the bind follows a ; inside the string, and src/retry.py exists, so a counted bind would load it.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^echo 'a; HERE="\$\(dirname "\$0"\)"; b'$/m, 'the bind must sit after a ; inside the string');
  assert.ok(existsSync(join(dir, 'src/retry.py')), 'src/retry.py must exist');
  mustNotLoad(check(dir), 'src/retry_check.sh', 'a bind after ; inside a string is text, so HERE has no bind and MAP11 must FAIL: the reader took the string text as a bind');
});

test('T6au. a bare `$BASH_SOURCE` base counts as the test folder: a shell test with `HERE="$(dirname "$BASH_SOURCE")"`, then `python3 "$HERE/retry.py"`, passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', `#!/bin/bash\nHERE="$(dirname "$BASH_SOURCE")"\npython3 "$HERE/retry.py"\n`);
  // The scope first: the root must hold no retry.py, so only the test folder can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^HERE="\$\(dirname "\$BASH_SOURCE"\)"$/m, 'HERE must be bound to a bare $BASH_SOURCE');
  assert.equal(existsSync(join(dir, 'retry.py')), false, 'the root must hold no retry.py');
  mustPass(check(dir), 'a bare $BASH_SOURCE stands for $0, so HERE is the test folder and the tail $HERE/retry.py loads the file');
});

test('T6av. a literal default counts as its literal path: a shell test with `SETUP_SH="${CLOUD_SETUP_SH_UNDER_TEST:-src/retry.py}"`, then `python3 "$SETUP_SH"`, passes, as Python os.environ.get with that default does', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nSETUP_SH="${CLOUD_SETUP_SH_UNDER_TEST:-src/retry.py}"\npython3 "$SETUP_SH"\n');
  // The scope first: the default is a literal path with no variable, and src/src/retry.py must not exist, so the path resolves from the root only.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^SETUP_SH="\$\{CLOUD_SETUP_SH_UNDER_TEST:-src\/retry\.py\}"$/m, 'SETUP_SH must default to the literal path src/retry.py');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustPass(check(dir), 'a literal default ${X:-src/retry.py} must count as the path src/retry.py, so SETUP_SH loads the file');
});

test('T6aw. a rebind by `local` counts for nothing, even at the same place: a shell test that binds HERE to the test folder, then rebinds it with `local` in a function, then `python3 "$HERE/retry.py"`, does not load the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/bash\nHERE="$(dirname "$0")"\nf() {\n  local HERE="$(dirname "$0")"\n  python3 "$HERE/retry.py"\n}\nf\n');
  // The scope first: the local rebind names the same place as the first bind, and src/retry.py exists, so the first bind alone would load it.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^  local HERE="\$\(dirname "\$0"\)"$/m, 'the function must rebind HERE with local');
  assert.ok(existsSync(join(dir, 'src/retry.py')), 'src/retry.py must exist');
  mustNotLoad(check(dir), 'src/retry_check.sh', 'a local rebind of HERE counts for nothing, so MAP11 must FAIL: the reader kept the first bind');
});

test('T6ax. a rebind by `for` counts for nothing, even at the same place: a shell test that binds HERE, then loops `for HERE in "$(dirname "$0")"`, then `python3 "$HERE/retry.py"`, does not load the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="$(dirname "$0")"\nfor HERE in "$(dirname "$0")"; do :; done\npython3 "$HERE/retry.py"\n');
  // The scope first: the loop rebinds HERE to the same place, and src/retry.py exists, so the first bind alone would load it.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^for HERE in "\$\(dirname "\$0"\)"; do :; done$/m, 'the loop must rebind HERE');
  assert.ok(existsSync(join(dir, 'src/retry.py')), 'src/retry.py must exist');
  mustNotLoad(check(dir), 'src/retry_check.sh', 'a for rebind of HERE counts for nothing, so MAP11 must FAIL: the reader kept the first bind');
});

test('T6ay. a rebind by `read` counts for nothing: a shell test that binds HERE, then `read HERE`, then `python3 "$HERE/retry.py"`, does not load the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="$(dirname "$0")"\nread HERE\npython3 "$HERE/retry.py"\n');
  // The scope first: the read rebinds HERE from input, and src/retry.py exists, so the first bind alone would load it.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^read HERE$/m, 'the shell test must rebind HERE with read');
  assert.ok(existsSync(join(dir, 'src/retry.py')), 'src/retry.py must exist');
  mustNotLoad(check(dir), 'src/retry_check.sh', 'a read rebind of HERE counts for nothing, so MAP11 must FAIL: the reader kept the first bind');
});

test('T6az. a rebind after `&&` counts for nothing, even at the same place: a shell test that binds HERE and ALT to the test folder, then `[ "$1" = up ] && HERE=$ALT`, then `python3 "$HERE/retry.py"`, does not load the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="$(dirname "$0")"\nALT="$(dirname "$0")"\n[ "$1" = up ] && HERE=$ALT\npython3 "$HERE/retry.py"\n');
  // The scope first: the && rebind names ALT, which is the same place as the first bind, and src/retry.py exists.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^\[ "\$1" = up \] && HERE=\$ALT$/m, 'the && branch must rebind HERE to ALT');
  assert.ok(existsSync(join(dir, 'src/retry.py')), 'src/retry.py must exist');
  mustNotLoad(check(dir), 'src/retry_check.sh', 'a rebind after && counts for nothing, so MAP11 must FAIL: the reader kept the first bind');
});

test('T6ba. a rebind after `||` counts for nothing, even at the same place: a shell test that binds HERE and ALT to the test folder, then `[ "$1" = up ] || HERE=$ALT`, then `python3 "$HERE/retry.py"`, does not load the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="$(dirname "$0")"\nALT="$(dirname "$0")"\n[ "$1" = up ] || HERE=$ALT\npython3 "$HERE/retry.py"\n');
  // The scope first: the || rebind names ALT, which is the same place as the first bind, and src/retry.py exists.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^\[ "\$1" = up \] \|\| HERE=\$ALT$/m, 'the || branch must rebind HERE to ALT');
  assert.ok(existsSync(join(dir, 'src/retry.py')), 'src/retry.py must exist');
  mustNotLoad(check(dir), 'src/retry_check.sh', 'a rebind after || counts for nothing, so MAP11 must FAIL: the reader kept the first bind');
});

test('T6bb. `$(cd -- "$HERE/.." && pwd)` names the root: a shell test that binds HERE to the test folder, then `ROOT="$(cd -- "$HERE/.." && pwd)"`, then `python3 "$ROOT/src/retry.py"`, passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="$(dirname "$0")"\nROOT="$(cd -- "$HERE/.." && pwd)"\npython3 "$ROOT/src/retry.py"\n');
  // The scope first: the cd carries --, and src/src/retry.py must not exist, so only the root can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^ROOT="\$\(cd -- "\$HERE\/\.\." && pwd\)"$/m, 'ROOT must be bound with cd --');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustPass(check(dir), 'cd -- to HERE/.. names the root, so ROOT is the root and the tail $ROOT/src/retry.py loads the file');
});

test('T6bc. `"$(dirname "$HERE")"` names the parent of a bound place: a shell test that binds HERE to the test folder, then `ROOT="$(dirname "$HERE")"`, then `python3 "$ROOT/src/retry.py"`, passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="$(dirname "$0")"\nROOT="$(dirname "$HERE")"\npython3 "$ROOT/src/retry.py"\n');
  // The scope first: src/src/retry.py must not exist, so a dirname that read HERE as its own place would not load the file.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^ROOT="\$\(dirname "\$HERE"\)"$/m, 'ROOT must be bound with dirname of HERE');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustPass(check(dir), 'dirname of the bound place HERE is its parent, the root, so ROOT is the root and the tail $ROOT/src/retry.py loads the file');
});

test('T6bd. an unquoted `ROOT=$(dirname "$HERE")` names the parent of a bound place: a shell test that binds HERE to the test folder, then `python3 "$ROOT/src/retry.py"`, passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="$(dirname "$0")"\nROOT=$(dirname "$HERE")\npython3 "$ROOT/src/retry.py"\n');
  // The scope first: the bind is unquoted, and src/src/retry.py must not exist, so only the parent place resolves the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^ROOT=\$\(dirname "\$HERE"\)$/m, 'ROOT must be bound with an unquoted dirname of HERE');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustPass(check(dir), 'an unquoted dirname of the bound place HERE is its parent, the root, so the tail $ROOT/src/retry.py loads the file');
});

test('T6be. `readlink -f` of a bound place counts as that place: a shell test that binds HERE to the test folder, then `ROOT="$(readlink -f "$HERE/..")"`, then `python3 "$ROOT/src/retry.py"`, passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="$(dirname "$0")"\nROOT="$(readlink -f "$HERE/..")"\npython3 "$ROOT/src/retry.py"\n');
  // The scope first: readlink carries the bound place, and src/src/retry.py must not exist, so only the root can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^ROOT="\$\(readlink -f "\$HERE\/\.\."\)"$/m, 'ROOT must be bound with readlink -f of HERE/..');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustPass(check(dir), 'readlink -f of the bound place HERE/.. is the root, so ROOT is the root and the tail $ROOT/src/retry.py loads the file');
});

test('T6bf. `realpath` of a bound place counts as that place: a shell test that binds HERE to the test folder, then `ROOT="$(realpath "$HERE/..")"`, then `python3 "$ROOT/src/retry.py"`, passes', () => {
  needFile(REL);
  const dir = scratchRepo();
  soleTest(dir, 'src/retry_check.sh', '#!/bin/sh\nHERE="$(dirname "$0")"\nROOT="$(realpath "$HERE/..")"\npython3 "$ROOT/src/retry.py"\n');
  // The scope first: realpath carries the bound place, and src/src/retry.py must not exist, so only the root can resolve the tail.
  assert.match(readAt(dir, 'src/retry_check.sh'), /^ROOT="\$\(realpath "\$HERE\/\.\."\)"$/m, 'ROOT must be bound with realpath of HERE/..');
  assert.equal(existsSync(join(dir, 'src', 'src', 'retry.py')), false, 'src/src/retry.py must not exist');
  mustPass(check(dir), 'realpath of the bound place HERE/.. is the root, so ROOT is the root and the tail $ROOT/src/retry.py loads the file');
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

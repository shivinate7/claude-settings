// Fact lines: the map says a fact in prose, and the check reads the cited symbol and fails when the two disagree (step c146, MAP9).
// The plan is `plans/c146-checked-prose-map.md` on origin/roadmap, section 3 and section 4 steps 2 to 8.
//
// THE API THE BUILDER IMPLEMENTS. The test-author fixes these names and shapes. Each case below calls them.
//
//   scripts/map-check.mjs
//     factLines(text) -> [ fact ]. A fact is one indented list line under a map line (a line that starts with a backtick path).
//       Its prose starts with a word, and its cite is the backtick text after " — " at the end of the line.
//       { kind: 'value', line, parent, prose, file, symbol, literal }   for `[file: ]SYMBOL = LITERAL`
//       { kind: 'uses',  line, parent, prose, file, symbol }             for `uses FILE[:SYMBOL]`; symbol is null when absent
//       line: 1-based. parent: the path of the nearest map line above, or null. For a value fact, file is the cited file,
//       or parent when the cite names none. literal: the literal text as written, e.g. '30' or '{"examples", "templates"}'.
//     homeLines(text) -> [ { line, capability, file, symbol } ], for the lines under a `## Homes` heading only.
//     mapCodePaths(text, re): unchanged. A fact line never counts as a map line.
//     mapChecks().MAP9(): one `[FAIL] MAP9 <message>` line in the run output. Causes are joined by "; ". Each cause names
//       `docs/map/<file>:<line>` of the fact or the home line. A value cause names the symbol and both values.
//       A number in prose matches only as a whole number, so cite 5 with prose 15 fails.
//       A numeric cite needs its number in the prose (owner pick 3a). A set or a list needs each item in the prose.
//
//   scripts/lib/fact-readers.mjs
//     readValues(requests, root) -> one result per request, in order. A request is { file, symbol }.
//       A result is { file, symbol, ok: true, value } or { file, symbol, ok: false, reason }.
//       .py   is read by scripts/lib/py-facts.py through one `python3 -I` child per call. Module-level Assign and AnnAssign only.
//       .json is read by the dotted path, with `[*]` for each element of a list. Its value is JSON.
//       .ts .tsx .mjs .js are read with the typescript parser, module-level declarations only.
//       Any other extension: a line regex over the text with comments AND strings blanked (the plan says blankComments;
//       the scanner rule needs strings too, and case R7 asserts it), then a literal parse.
//       A set comes back as an array, in any order. A missing python3 or a file that does not parse is ok: false, never ok: true.
//
//   scripts/map-check.mjs, MAP_FORMAT_VERSION in scripts/lib/map-config.mjs: 3 after the step 6 bump.
//   scripts/lib/map-config.mjs, validateMapConfig: the optional key `mapPaths`, a list of path prefixes. See map-paths.test.mjs.
//
// The fixture (tests/fixture/) gained: src/retry.py, src/caller.py, config.json, docs/map/homes.md, and fact lines in core.md.
// Its codeExtensions stay ["ts"]: the readers read .py and .json facts without them being code files. Adding them would change
// the upgrade of `/api/runs.json:1` (case 7a) and the config of case 4, which are green on main.
// Each case that edits the fixture edits a scratch copy in this run's temp folder, never the checkout.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { chmodSync, existsSync, mkdirSync, readFileSync, symlinkSync, writeFileSync } from 'node:fs';
import { delimiter, dirname, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { FIXTURE, SKILL, cleanEnv, expected, gitIn, needFile, run, scratchRepo, tmpFolder, verdicts } from './helpers.mjs';

const CHECK = join(SKILL, 'scripts', 'map-check.mjs');
const READERS = join(SKILL, 'scripts', 'lib', 'fact-readers.mjs');
const PY_FACTS = join(SKILL, 'scripts', 'lib', 'py-facts.py');
const CORE = 'docs/map/core.md';
const HOMES = 'docs/map/homes.md';
const TRACE = 'docs/map/traces/home.md';
const posix = process.platform !== 'win32';

const out1500 = (r) => r.out.slice(0, 1500);
const read = (dir, rel) => readFileSync(join(dir, rel), 'utf8');
const write = (dir, rel, text) => writeFileSync(join(dir, rel), text);

/** Replaces `from` with `to` in one file of `dir`. The text must hold `from`, or the case proves nothing. */
const edit = (dir, rel, from, to) => {
  const t = read(dir, rel);
  assert.ok(t.includes(from), `${rel} must hold ${JSON.stringify(from)} before the edit`);
  write(dir, rel, t.replace(from, to));
};

/** The 1-based line of the one line in `rel` that holds `needle`. */
const lineOf = (dir, rel, needle) => {
  const i = read(dir, rel).split('\n').findIndex((l) => l.includes(needle));
  assert.ok(i >= 0, `${rel} must hold a line with ${JSON.stringify(needle)}`);
  return i + 1;
};

/** Inserts `lines` in the code files part of docs/map/core.md, before the Tables heading. */
const insertCore = (dir, lines) => {
  const all = read(dir, CORE).split('\n');
  const at = all.indexOf('## Tables');
  assert.ok(at > 0, `${CORE} must hold a Tables heading`);
  all.splice(at, 0, ...lines, '');
  write(dir, CORE, all.join('\n'));
};

/** Adds a tracked code file with its map line and its fact lines (each `prose — cite`), to a scratch repository. */
const addCode = (dir, rel, body, facts = []) => {
  mkdirSync(dirname(join(dir, rel)), { recursive: true });
  write(dir, rel, body);
  gitIn(dir, 'add', '-N', rel);
  insertCore(dir, [`- \`${rel}\` — Holds the test values of this case.`, ...facts.map((f) => `  - ${f}`)]);
};

const check = (dir, env) => run([CHECK], dir, undefined, env);
/** The MAP9 line of a run output, or '' when the output has none. */
const mapLine = (out) => out.split('\n').find((l) => /^\[(PASS|FAIL|SKIP)\] MAP9\b/.test(l)) ?? '';

/** The named exports of map-check.mjs. A missing export fails here, by its name. */
const checkExports = async (...names) => {
  needFile('scripts/map-check.mjs');
  const mod = await import(pathToFileURL(CHECK).href);
  for (const n of names) assert.equal(typeof mod[n], 'function', `map-check.mjs must export ${n}()`);
  return mod;
};

/** The reader module. A missing file fails here, by its path. */
const readersModule = async () => {
  needFile('scripts/lib/fact-readers.mjs');
  const mod = await import(pathToFileURL(READERS).href);
  assert.equal(typeof mod.readValues, 'function', 'fact-readers.mjs must export readValues(requests, root)');
  return mod;
};

/** A new scratch folder with `files` ({ relative path: text }) written into it. */
const scratchFiles = (files) => {
  const dir = tmpFolder('pemap-facts-');
  for (const [rel, text] of Object.entries(files)) {
    mkdirSync(dirname(join(dir, rel)), { recursive: true });
    write(dir, rel, text);
  }
  return dir;
};

/** A folder with a link to git and no python3. On PATH it lets the command find git and no interpreter. */
const gitOnlyBin = () => {
  const onPath = (name) => (process.env.PATH ?? '').split(delimiter).map((d) => join(d, name)).find((p) => existsSync(p));
  assert.ok(onPath('python3'), 'python3 must be on this machine, or the no-python case proves nothing');
  const git = onPath('git');
  assert.ok(git, 'git must be on this machine');
  const bin = tmpFolder('pemap-nopy-');
  symlinkSync(git, join(bin, 'git'));
  assert.ok(!existsSync(join(bin, 'python3')), 'the bin folder must hold no python3');
  return bin;
};

/** A folder with a python3 shim first on PATH. The shim writes one line to the log for each start, then runs the real python3. */
const pyShim = () => {
  const real = (process.env.PATH ?? '').split(delimiter).map((d) => join(d, 'python3')).find((p) => existsSync(p));
  assert.ok(real, 'python3 must be on PATH for the cost case');
  const bin = tmpFolder('pemap-shim-');
  const log = join(bin, 'starts.log');
  const sh = join(bin, 'python3');
  writeFileSync(sh, '#!/bin/sh\necho start >> "$PY_SHIM_LOG"\nexec "$PY_SHIM_REAL" "$@"\n');
  chmodSync(sh, 0o755);
  writeFileSync(log, '');
  return { log, env: { PATH: `${bin}${delimiter}${process.env.PATH}`, PY_SHIM_LOG: log, PY_SHIM_REAL: real } };
};
const starts = (log) => readFileSync(log, 'utf8').split('\n').filter(Boolean).length;

// ---- Step 2: the fact-line parser and the home lines ----

test('F2a. factLines reads a value fact and a uses fact, with their line, parent map line, prose and cite', async () => {
  const { factLines } = await checkExports('factLines');
  const text = [
    '# Lint',
    '',
    '## Code files',
    '',
    '- `lint/find_copies.py` — Lists the copies of claude-settings things.',
    '  - A near-equal file needs 12 significant lines. — `MIN_LINES = 12`',
    '  - Starts git with no window, through the one home. — `uses hooks/_nowindow.py:run`',
    '  - The skill pins typescript to one version. — `package.json: dependencies.typescript = "~5.8.2"`',
    '  - Parent files under examples and templates are never copies. — `TEMPLATE_DIRS = {"examples", "templates"}`',
    '',
  ].join('\n');
  assert.deepEqual(factLines(text), [
    { kind: 'value', line: 6, parent: 'lint/find_copies.py', prose: 'A near-equal file needs 12 significant lines.', file: 'lint/find_copies.py', symbol: 'MIN_LINES', literal: '12' },
    { kind: 'uses', line: 7, parent: 'lint/find_copies.py', prose: 'Starts git with no window, through the one home.', file: 'hooks/_nowindow.py', symbol: 'run' },
    { kind: 'value', line: 8, parent: 'lint/find_copies.py', prose: 'The skill pins typescript to one version.', file: 'package.json', symbol: 'dependencies.typescript', literal: '"~5.8.2"' },
    { kind: 'value', line: 9, parent: 'lint/find_copies.py', prose: 'Parent files under examples and templates are never copies.', file: 'lint/find_copies.py', symbol: 'TEMPLATE_DIRS', literal: '{"examples", "templates"}' },
  ]);
});

test('F2b. a list line with no indent is no fact line, and an indented line that starts with a backtick is a map line', async () => {
  const { factLines, mapCodePaths } = await checkExports('factLines', 'mapCodePaths');
  const text = ['- `lint/find_copies.py` — Lists the copies.', '- Prose only — `MIN_LINES = 12`', '  - `lint/other.py` — Lists more.', ''].join('\n');
  assert.deepEqual(factLines(text), []);
  assert.deepEqual(mapCodePaths(text, /\.py$/), ['lint/find_copies.py', 'lint/other.py']);
});

test('F2c. mapCodePaths counts no fact line as a map line, even when the cite names a tracked file', async () => {
  const { mapCodePaths } = await checkExports('mapCodePaths');
  const text = [
    '- `src/caller.py` — Runs the caller.',
    '  - It reads the retry wait. — `uses src/retry.py:RETRY_WAIT_S`',
    '  - Holds the wait. — `src/retry.py: RETRY_WAIT_S = 30`',
    '',
  ].join('\n');
  assert.deepEqual(mapCodePaths(text, /\.py$/), ['src/caller.py']);
});

test('F2d. a fact prose holds a lone quote and a comment mark in text, and the cite still reads', async () => {
  const { factLines } = await checkExports('factLines');
  const text = "- `src/notes.ts` — Holds the notes.\n  - Each note's text keeps the // and # marks. — `MARK = \"#\"`\n";
  assert.deepEqual(factLines(text), [
    { kind: 'value', line: 2, parent: 'src/notes.ts', prose: "Each note's text keeps the // and # marks.", file: 'src/notes.ts', symbol: 'MARK', literal: '"#"' },
  ]);
});

test('F2e. homeLines reads the lines under a Homes heading only, as capability, file and symbol', async () => {
  const { homeLines } = await checkExports('homeLines');
  const text = [
    '# Homes',
    '',
    '## Homes',
    '',
    '- no-window child start — `hooks/_nowindow.py:run`',
    '- the saved notes — `src/notes.ts:notes`',
    '',
    '## Other',
    '',
    '- not a home — `src/gone.py:run`',
    '',
  ].join('\n');
  assert.deepEqual(homeLines(text), [
    { line: 5, capability: 'no-window child start', file: 'hooks/_nowindow.py', symbol: 'run' },
    { line: 6, capability: 'the saved notes', file: 'src/notes.ts', symbol: 'notes' },
  ]);
});

// ---- Step 3: the value readers ----

test('R0. the two reader files exist: scripts/lib/fact-readers.mjs and scripts/lib/py-facts.py', () => {
  needFile('scripts/lib/fact-readers.mjs');
  needFile('scripts/lib/py-facts.py');
  assert.ok(existsSync(PY_FACTS));
});

test('R1. the python reader returns 30 for RETRY_WAIT_S in src/retry.py, never the 99 in a string or the 7 in a comment', async () => {
  const { readValues } = await readersModule();
  const [r] = readValues([{ file: 'src/retry.py', symbol: 'RETRY_WAIT_S' }], FIXTURE);
  assert.deepEqual(r, { file: 'src/retry.py', symbol: 'RETRY_WAIT_S', ok: true, value: 30 });
});

test('R2. a name that is only in a string, a comment or a function is no module-level value, and the reader says so', async () => {
  const { readValues } = await readersModule();
  const dir = scratchFiles({
    'src/only.py': ['# Don\'t trust ONLY_HERE = 7 in a comment.', 'NOTE = "ONLY_HERE = 99"', 'DOC = """first line', 'ONLY_HERE = 3', '"""', '', '', 'def f():', '    ONLY_HERE = 5', ''].join('\n'),
  });
  // The scope first: the file holds the name as text, so a text search would still find it.
  assert.match(read(dir, 'src/only.py'), /ONLY_HERE = 99/, 'the scratch file must hold the name in a string');
  const [r] = readValues([{ file: 'src/only.py', symbol: 'ONLY_HERE' }], dir);
  assert.equal(r.ok, false, `the reader must not read a value from a string, a comment or a function. It returned ${JSON.stringify(r)}`);
  assert.equal(typeof r.reason, 'string', 'an unknown read must say why');
});

test('R3. the json reader returns 30 for the dotted path retry.wait_s of config.json', async () => {
  const { readValues } = await readersModule();
  const [r] = readValues([{ file: 'config.json', symbol: 'retry.wait_s' }], FIXTURE);
  assert.deepEqual(r, { file: 'config.json', symbol: 'retry.wait_s', ok: true, value: 30 });
});

test('R4. the json reader fans out a [*] step: crew[*].name is the list of names in config.json', async () => {
  const { readValues } = await readersModule();
  const [r] = readValues([{ file: 'config.json', symbol: 'crew[*].name' }], FIXTURE);
  assert.deepEqual(r, { file: 'config.json', symbol: 'crew[*].name', ok: true, value: ['alpha', 'beta'] });
});

test('R5. a json path that is not in the file is ok: false, never a value', async () => {
  const { readValues } = await readersModule();
  const [r] = readValues([{ file: 'config.json', symbol: 'retry.missing' }], FIXTURE);
  assert.equal(r.ok, false, `a missing path must not read as a value: ${JSON.stringify(r)}`);
});

test('R6. the typescript reader returns 12 for MIN_LINES in a .mjs file, never the 99 in a string or the 7 in a comment, and a lone quote in a comment hides nothing', async () => {
  const { readValues } = await readersModule();
  // A multi-line template literal holds the name at a line start, and a `//` and a `/*` in its text. Only the real value counts.
  const dir = scratchFiles({
    'lib/limits.mjs': ['const NOTE = "MIN_LINES = 99";', 'const DOC = `first line', 'MIN_LINES = 7', '// not a comment, MIN_LINES = 5', '/* nor this */`;', '// Don\'t use MIN_LINES = 7 here.', 'export const MIN_LINES = 12;', ''].join('\n'),
  });
  const [r] = readValues([{ file: 'lib/limits.mjs', symbol: 'MIN_LINES' }], dir);
  assert.deepEqual(r, { file: 'lib/limits.mjs', symbol: 'MIN_LINES', ok: true, value: 12 });
});

test('R7. the regex reader returns 30 for RETRY_WAIT_S in a .go file, and a `//` comment line is blanked before the match', async () => {
  const { readValues } = await readersModule();
  // A raw string runs over three lines and holds the name at a line start. The regex reader must read strings as text, so it is no value.
  const dir = scratchFiles({
    'src/retry.go': ['package retry', '', 'const RETRY_WAIT_S = 30', '// const RETRY_WAIT_S = 7', 'var NOTE = "RETRY_WAIT_S = 99"', 'var DOC = `first line', 'const RETRY_WAIT_S = 7', '// not a comment, RETRY_WAIT_S = 5', '`', ''].join('\n'),
  });
  assert.match(read(dir, 'src/retry.go'), /^const RETRY_WAIT_S = 7$/m, 'the raw string must hold the name at a line start');
  const [r] = readValues([{ file: 'src/retry.go', symbol: 'RETRY_WAIT_S' }], dir);
  assert.deepEqual(r, { file: 'src/retry.go', symbol: 'RETRY_WAIT_S', ok: true, value: 30 });
});

test('R8. with no python3 on PATH the python reader is ok: false and names python3, and never ok: true', async () => {
  await readersModule();
  const script = `const m = await import(${JSON.stringify(pathToFileURL(READERS).href)});
console.log(JSON.stringify(m.readValues([{ file: 'src/retry.py', symbol: 'RETRY_WAIT_S' }], ${JSON.stringify(FIXTURE)})));`;
  const r = run(['--input-type=module', '-'], FIXTURE, script, { PATH: gitOnlyBin() });
  assert.equal(r.status, 0, `the module must load and answer, with no python3\n${out1500(r)}`);
  const [res] = JSON.parse(r.stdout.trim().split('\n').pop());
  assert.equal(res.ok, false, `a python read with no python3 must be unknown: ${JSON.stringify(res)}`);
  assert.match(res.reason, /python3/, 'the reason must name python3');
});

// ---- Step 4: MAP9 ----

test('M0. on the fixture every check passes, MAP9 included, and the command exits 0', () => {
  needFile('scripts/map-check.mjs');
  const r = check(scratchRepo());
  assert.equal(verdicts(r.out), expected(), `each of MAP1 to MAP9 must print one PASS line\n${out1500(r)}`);
  assert.equal(r.status, 0, `the command must exit 0 on a clean fixture\n${out1500(r)}`);
});

test('M1. cause 1: RETRY_WAIT_S is 45 in the code and 30 in the map. MAP9 fails, names the map line, the symbol and both values, and every other check passes', () => {
  needFile('scripts/map-check.mjs');
  const dir = scratchRepo();
  edit(dir, 'src/retry.py', 'RETRY_WAIT_S = 30', 'RETRY_WAIT_S = 45');
  const r = check(dir);
  assert.equal(verdicts(r.out), expected({ MAP9: 'FAIL' }), `only MAP9 must fail\n${out1500(r)}`);
  assert.notEqual(r.status, 0, 'the command must exit non-zero when MAP9 fails');
  const at = `${CORE}:${lineOf(dir, CORE, 'A failed call waits 30 s')}`;
  const line = mapLine(r.out);
  assert.ok(line.includes(at), `MAP9 must name the map line ${at}\n${line}`);
  for (const s of ['RETRY_WAIT_S', '30', '45']) assert.ok(line.includes(s), `MAP9 must name ${s}\n${line}`);
});

test('M1b. cause 1 in json: retry.wait_s is 45 in config.json and 30 in the map, and MAP9 names the map line and both values', () => {
  needFile('scripts/map-check.mjs');
  const dir = scratchRepo();
  edit(dir, 'config.json', '"wait_s": 30', '"wait_s": 45');
  const r = check(dir);
  assert.equal(verdicts(r.out), expected({ MAP9: 'FAIL' }), `only MAP9 must fail\n${out1500(r)}`);
  const at = `${CORE}:${lineOf(dir, CORE, 'The file waits 30 s before a retry.')}`;
  const line = mapLine(r.out);
  assert.ok(line.includes(at), `MAP9 must name the map line ${at}\n${line}`);
  for (const s of ['retry.wait_s', '30', '45']) assert.ok(line.includes(s), `MAP9 must name ${s}\n${line}`);
});

test('M2. cause 2: the prose says 20 and the cite says 30. MAP9 fails and names the map line and both numbers', () => {
  needFile('scripts/map-check.mjs');
  const dir = scratchRepo();
  edit(dir, CORE, 'A failed call waits 30 s', 'A failed call waits 20 s');
  const r = check(dir);
  assert.equal(verdicts(r.out), expected({ MAP9: 'FAIL' }), `only MAP9 must fail\n${out1500(r)}`);
  const at = `${CORE}:${lineOf(dir, CORE, 'A failed call waits 20 s')}`;
  const line = mapLine(r.out);
  assert.ok(line.includes(at), `MAP9 must name the map line ${at}\n${line}`);
  for (const s of ['20', '30']) assert.ok(line.includes(s), `MAP9 must name ${s}\n${line}`);
});

test('M2b. a number matches as a whole number: cite 5 with prose 15 fails, cite 15 with prose 15 passes, and prose 115 never matches cite 15', () => {
  needFile('scripts/map-check.mjs');
  for (const [cite, prose, pass] of [[5, 15, false], [15, 15, true], [15, 115, false]]) {
    const dir = scratchRepo();
    addCode(dir, 'src/limits.py', `LIMIT = ${cite}\n`, [`The limit holds ${prose} items. — \`LIMIT = ${cite}\``]);
    const r = check(dir);
    const label = `cite ${cite}, prose ${prose}`;
    assert.equal(verdicts(r.out), expected(pass ? {} : { MAP9: 'FAIL' }), `${label}: the verdicts\n${out1500(r)}`);
    assert.match(mapLine(r.out), pass ? /^\[PASS\] MAP9/ : /^\[FAIL\] MAP9/, `${label}: MAP9 must ${pass ? 'pass' : 'fail'}`);
  }
});

test('M3. a set cite and a list cite: each item must appear in the prose, and a missing item fails with its name', () => {
  needFile('scripts/map-check.mjs');
  const cases = [
    ['TEMPLATE_DIRS = {"examples", "templates"}', 'Parent files under examples and templates are never copies.', true],
    ['TEMPLATE_DIRS = {"examples", "templates"}', 'Parent files under examples are never copies.', false],
    ['NAMES = ["alpha", "beta"]', 'The names are alpha and beta.', true],
    ['NAMES = ["alpha", "beta"]', 'The name is alpha.', false],
  ];
  for (const [body, prose, pass] of cases) {
    const dir = scratchRepo();
    const cite = body.slice(0, body.indexOf(' = '));
    addCode(dir, 'src/dirs.py', `${body}\n`, [`${prose} — \`${body}\``]);
    const r = check(dir);
    assert.equal(verdicts(r.out), expected(pass ? {} : { MAP9: 'FAIL' }), `${prose}\n${out1500(r)}`);
    const line = mapLine(r.out);
    assert.match(line, pass ? /^\[PASS\] MAP9/ : /^\[FAIL\] MAP9/, `${cite}: MAP9 must ${pass ? 'pass' : 'fail'}`);
    if (!pass) assert.match(line, /templates|beta/, `MAP9 must name the missing item\n${line}`);
  }
});

test('M4. cause 3: the symbol is gone from the code. MAP9 fails and names the map line and the symbol, and the string and the comment that still hold it do not count', () => {
  needFile('scripts/map-check.mjs');
  const dir = scratchRepo();
  edit(dir, 'src/retry.py', 'RETRY_WAIT_S = 30\n', '');
  // The scope first: the string and the comment still hold the name, so a text search would still find it.
  assert.match(read(dir, 'src/retry.py'), /RETRY_WAIT_S = 99/, 'the string with the name must remain');
  assert.match(read(dir, 'src/retry.py'), /# RETRY_WAIT_S = 7/, 'the comment with the name must remain');
  const r = check(dir);
  assert.equal(verdicts(r.out), expected({ MAP9: 'FAIL' }), `only MAP9 must fail\n${out1500(r)}`);
  const at = `${CORE}:${lineOf(dir, CORE, 'A failed call waits 30 s')}`;
  const line = mapLine(r.out);
  assert.ok(line.includes(at), `MAP9 must name the map line ${at}\n${line}`);
  assert.ok(line.includes('src/retry.py') && line.includes('RETRY_WAIT_S'), `MAP9 must name the file and the symbol\n${line}`);
});

test('M4b. a name assigned only inside a function is no module-level value, so MAP9 fails', () => {
  needFile('scripts/map-check.mjs');
  const dir = scratchRepo();
  edit(dir, 'src/retry.py', 'RETRY_WAIT_S = 30\n', 'def f():\n    RETRY_WAIT_S = 30\n');
  const r = check(dir);
  assert.match(mapLine(r.out), /^\[FAIL\] MAP9/, `a function-local name must not count\n${out1500(r)}`);
});

test('M5. cause 6: a digit outside backticks fails in a map line, a table line, a screen line and a trace step, and names the line and the digit', () => {
  needFile('scripts/map-check.mjs');
  const cases = [
    { what: 'map line', rel: CORE, from: 'Holds the saved notes (`notes`).', to: 'Holds the saved notes (`notes`), up to 30.', needle: 'up to 30.', digit: '30' },
    { what: 'table line', rel: CORE, from: 'One row for each saved note.', to: 'One row for each saved note, up to 50.', needle: 'up to 50.', digit: '50' },
    { what: 'screen line', rel: CORE, from: 'Shows the saved notes.', to: 'Shows 3 saved notes.', needle: 'Shows 3 saved notes.', digit: '3' },
    { what: 'trace step', rel: TRACE, from: 'counts (`notes`).', to: 'counts (`notes`), 3 times.', needle: '3 times.', digit: '3' },
  ];
  for (const c of cases) {
    const dir = scratchRepo();
    edit(dir, c.rel, c.from, c.to);
    const r = check(dir);
    assert.equal(verdicts(r.out), expected({ MAP9: 'FAIL' }), `${c.what}: only MAP9 must fail\n${out1500(r)}`);
    const line = mapLine(r.out);
    assert.ok(line.includes(`${c.rel}:${lineOf(dir, c.rel, c.needle)}`), `${c.what}: MAP9 must name the line\n${line}`);
    assert.ok(line.includes(c.digit), `${c.what}: MAP9 must name the digit ${c.digit}\n${line}`);
  }
});

test('M6. cause 6 controls: a digit in backticks, a fact line digit and a trace step number all pass', () => {
  needFile('scripts/map-check.mjs');
  // The fixture holds `localhost:3000` in backticks, a fact line with `30 s`, and trace steps numbered 1 and 2. All pass.
  assert.match(read(FIXTURE, CORE), /`localhost:3000`/, 'the fixture must hold a number in backticks');
  const r = check(scratchRepo());
  assert.equal(verdicts(r.out), expected(), `these numbers are no unchecked number\n${out1500(r)}`);
});

test('M7. cause 7: with no python3 on PATH, MAP9 fails as unknown, names python3, and never reads PASS', () => {
  needFile('scripts/map-check.mjs');
  const r = check(scratchRepo(), { PATH: gitOnlyBin() });
  assert.equal(verdicts(r.out), expected({ MAP9: 'FAIL' }), `only MAP9 must fail\n${out1500(r)}`);
  const line = mapLine(r.out);
  assert.match(line, /^\[FAIL\] MAP9/, `an unknown read must fail\n${out1500(r)}`);
  assert.match(line, /python3/, `MAP9 must name python3\n${line}`);
  assert.match(line, /could not read/, `MAP9 must say it could not read the facts\n${line}`);
  assert.notEqual(r.status, 0, 'the command must exit non-zero');
});

test('M7b. cause 7: a Python file that does not parse is unknown, so MAP9 fails and names the file', () => {
  needFile('scripts/map-check.mjs');
  const dir = scratchRepo();
  edit(dir, 'src/retry.py', 'RETRY_WAIT_S = 30', 'RETRY_WAIT_S = (30');
  const r = check(dir);
  const line = mapLine(r.out);
  assert.match(line, /^\[FAIL\] MAP9/, `a file that does not parse must fail\n${out1500(r)}`);
  assert.ok(line.includes('src/retry.py'), `MAP9 must name the file\n${line}`);
});

test('M8. owner pick 3a: a numeric cite needs its number in the prose, so prose with no number fails and names the cited number', () => {
  needFile('scripts/map-check.mjs');
  const dir = scratchRepo();
  edit(dir, CORE, 'A failed call waits 30 s before its next try.', 'A failed call waits before its next try.');
  const r = check(dir);
  assert.equal(verdicts(r.out), expected({ MAP9: 'FAIL' }), `only MAP9 must fail\n${out1500(r)}`);
  const line = mapLine(r.out);
  assert.ok(line.includes(`${CORE}:${lineOf(dir, CORE, 'A failed call waits before')}`), `MAP9 must name the fact line\n${line}`);
  assert.ok(line.includes('30'), `MAP9 must name the cited number 30\n${line}`);
});

test('M9. several causes at once make one MAP9 line, and the causes are joined by "; "', () => {
  needFile('scripts/map-check.mjs');
  const dir = scratchRepo();
  edit(dir, 'src/retry.py', 'RETRY_WAIT_S = 30', 'RETRY_WAIT_S = 45');
  edit(dir, 'src/caller.py', 'import retry\n', '');
  const r = check(dir);
  const lines =r.out.split('\n').filter((l) => /^\[(PASS|FAIL|SKIP)\] MAP9\b/.test(l));
  assert.equal(lines.length, 1, `MAP9 must print one line\n${out1500(r)}`);
  assert.match(lines[0], /^\[FAIL\] MAP9/, 'the one line must say FAIL');
  assert.match(lines[0], /; /, `the causes must be joined by "; "\n${lines[0]}`);
  assert.ok(lines[0].includes('45') && /no longer imports/.test(lines[0]), `the one line must hold both causes\n${lines[0]}`);
});

// ---- Step 5: relations and homes ----

test('U2. cause 4: caller.py no longer imports retry.py. MAP9 fails and names the map line, the two files and the broken import', () => {
  needFile('scripts/map-check.mjs');
  const dir = scratchRepo();
  edit(dir, 'src/caller.py', 'import retry\n', '');
  const r = check(dir);
  assert.equal(verdicts(r.out), expected({ MAP9: 'FAIL' }), `only MAP9 must fail\n${out1500(r)}`);
  const at = `${CORE}:${lineOf(dir, CORE, 'The caller reads the retry wait')}`;
  const line = mapLine(r.out);
  assert.ok(line.includes(at), `MAP9 must name the map line ${at}\n${line}`);
  assert.ok(line.includes('src/caller.py') && line.includes('src/retry.py'), `MAP9 must name both files\n${line}`);
  assert.match(line, /no longer imports/, 'MAP9 must say the import is gone');
});

test('U3. cause 4: caller.py still imports retry.py but never uses RETRY_WAIT_S. MAP9 fails and says so', () => {
  needFile('scripts/map-check.mjs');
  const dir = scratchRepo();
  edit(dir, 'src/caller.py', 'return retry.RETRY_WAIT_S', 'return 0');
  const r = check(dir);
  assert.equal(verdicts(r.out), expected({ MAP9: 'FAIL' }), `only MAP9 must fail\n${out1500(r)}`);
  assert.match(mapLine(r.out), /never uses RETRY_WAIT_S/, 'MAP9 must say the file never uses the symbol');
});

test('U4. cause 4 in typescript: home.ts no longer imports notes.ts. MAP9 fails and names the import', () => {
  needFile('scripts/map-check.mjs');
  const dir = scratchRepo();
  edit(dir, 'src/home.ts', "import { notes } from './notes';\n", '');
  const r = check(dir);
  // The trace page reads the same import, so MAP8 may fail too. This case asserts MAP9 only.
  const line = mapLine(r.out);
  assert.match(line, /^\[FAIL\] MAP9/, `MAP9 must fail\n${out1500(r)}`);
  assert.ok(line.includes('src/home.ts') && line.includes('src/notes.ts'), `MAP9 must name both files\n${line}`);
  assert.match(line, /no longer imports/, 'MAP9 must say the import is gone');
});

test('H1. cause 5: a home names a file git does not track. MAP9 fails and names the home line and the file', () => {
  needFile('scripts/map-check.mjs');
  const dir = scratchRepo();
  edit(dir, HOMES, '`src/retry.py:RETRY_WAIT_S`', '`src/gone.py:run`');
  const r = check(dir);
  assert.equal(verdicts(r.out), expected({ MAP9: 'FAIL' }), `only MAP9 must fail\n${out1500(r)}`);
  const line = mapLine(r.out);
  assert.ok(line.includes(`${HOMES}:${lineOf(dir, HOMES, 'the retry wait')}`), `MAP9 must name the home line\n${line}`);
  assert.ok(line.includes('src/gone.py') && /is not tracked/.test(line), `MAP9 must say the home is not tracked\n${line}`);
});

test('H2. cause 5: a home names a symbol the file does not have. MAP9 fails and names the symbol', () => {
  needFile('scripts/map-check.mjs');
  const dir = scratchRepo();
  edit(dir, HOMES, '`src/retry.py:RETRY_WAIT_S`', '`src/retry.py:RETRY_DELAY`');
  const r = check(dir);
  assert.equal(verdicts(r.out), expected({ MAP9: 'FAIL' }), `only MAP9 must fail\n${out1500(r)}`);
  const line = mapLine(r.out);
  assert.ok(line.includes(`${HOMES}:${lineOf(dir, HOMES, 'the retry wait')}`), `MAP9 must name the home line\n${line}`);
  assert.match(line, /has no (module-level )?RETRY_DELAY/, 'MAP9 must say the file has no such symbol');
});

test('H3. a cite outside the Homes heading is no home, so a bad one there does not fail MAP9', () => {
  needFile('scripts/map-check.mjs');
  const dir = scratchRepo();
  write(dir, HOMES, `${read(dir, HOMES)}\n## Other\n\n- not a home — \`src/gone.py:run\`\n`);
  const r = check(dir);
  assert.equal(verdicts(r.out), expected(), `a cite outside Homes must not be read as a home\n${out1500(r)}`);
});

// ---- Step 8: the cost of the Python reader ----

const POSIX_ONLY = { skip: posix ? false : 'a POSIX shell shim is run by PATH lookup, and Windows has no such shim here' };

test('C1. the python3 shim logs each start and runs the real interpreter, so the cost case below counts real starts', POSIX_ONLY, () => {
  const shim = pyShim();
  const r = spawnSync('python3', ['-I', '-c', 'print(7)'], { env: { ...cleanEnv(), ...shim.env }, encoding: 'utf8' });
  assert.equal(r.status, 0, `the shim must run the real python3\n${r.stderr}`);
  assert.equal(r.stdout.trim(), '7', 'the shim must answer the real interpreter output');
  assert.equal(starts(shim.log), 1, 'the shim must log exactly one start');
});

test('C2. cost: a map with 5 Python facts across 3 files starts python3 exactly once for the whole check', POSIX_ONLY, () => {
  const shim = pyShim();
  const dir = scratchRepo();
  addCode(dir, 'src/a.py', 'A1 = 1\nA2 = 2\n', ['The first limit is 1. — `A1 = 1`', 'The second limit is 2. — `A2 = 2`']);
  addCode(dir, 'src/b.py', 'B1 = 3\nB2 = 4\n', ['The third limit is 3. — `B1 = 3`', 'The fourth limit is 4. — `B2 = 4`']);
  addCode(dir, 'src/c.py', 'C1 = 5\n', ['The fifth limit is 5. — `C1 = 5`']);
  const r = run([CHECK], dir, undefined, shim.env);
  // The scope first: the five facts are read on this run, so MAP9 passes and the one start is the read of them.
  assert.equal(verdicts(r.out), expected(), `all five facts must read and pass\n${out1500(r)}`);
  assert.equal(starts(shim.log), 1, `python3 must start once for the whole run, and it started ${starts(shim.log)} time(s)`);
});

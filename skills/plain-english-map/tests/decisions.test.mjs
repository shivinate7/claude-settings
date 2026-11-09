// The decision ids of the plain-English map: the `decisionsDir` and `decisionIdPattern` keys, MAP10, and `scripts/map-fix.mjs`.
// Fixture: `tests/fixture-decisions/`. Its records sit in `docs/records/`, because `decisionsDir` is a config key. The ruling-kind
// guard judges any path with a `decisions` folder segment, and these fixture records are not rulings (a possible false alarm).
//
// The design, as the builder implements it:
//   - Config: both keys or neither. One key alone is a config error that names the missing key (assumed: the design says only "a config error").
//   - A record is a `.md` file directly in `decisionsDir`. An id names a record when the file stem equals the id or starts with `id-`.
//     A digit run compares by value: D7 names `D007-retry-wait.md`.
//   - A decisions line sits right under a map line: `  - Decisions: ` and backticked ids joined by `, `.
//   - MAP10 runs only when both keys are set. Otherwise it prints a SKIP line. It fails when a comment of a mapped code file cites an id
//     that names a record and the map line has no decisions line with that id, and when a decisions line names an id with no record.
//     An id the file no longer cites is fine.
//   - Comments are read through `scripts/lib/source-text.mjs`: `blankComments` for JS and TS, `blankShell` for `.sh`, and a Python reader
//     the builder adds there. A string is never a cite, including a Python triple-quoted string.
//   - `scripts/map-fix.mjs` adds the missing ids and never removes or reorders one. With no flag it prints each id it would add, one line
//     per id that names the file (assumed: the design does not give the layout), and it writes nothing. A second `--write` changes no byte.
//
// Red on the old code. Every config at version 6 (the fixture, and each case that writes one) is refused by the old validator before any
// check runs. So each MAP10 case goes red on its missing `MAP10` verdict, and the validator message shows in its output. The config, upgrade and
// map-fix cases assert their own effect, and they go red on it. Controls (C3, K-*) hold on both the old code and the new.
//
// Cases:
//   C1, C2   one key alone is a config error that names the missing key. C3 (control): a version 2 map asks for the upgrade.
//   V1-V7    version 6 loads with both keys; version 6 loads with no decision keys; version 3 asks for the upgrade; version 5 asks for the
//            upgrade; the upgrade from 3 and from 5 sets 6 and writes no map page; a second run changes no byte.
//   M1       the fixture is green. M2 (a) a cite with no decisions line. M3 (b) a decisions line naming an id with no record.
//   M4       an id the file no longer cites is fine. M5 zero-padding: D7 names D007 by value. M6 D1 names no record (D018 is 18).
//   E1       an empty decisions folder: each decisions line fails and names its id.
//   S-*      scanner traps for JS and TS: an id in a string is no cite; `/*` and `//` in strings; a template literal; a lone quote in JSX.
//   P-*      Python: `# D7` is a cite; an id in a Python string, and `# D18` inside a triple-quoted string, are no cite.
//   SH-*     shell: `# D7` is a cite; an id in a double-quoted shell string is no cite.
//   K-*      controls: the existing readers blank the comment and keep the string, as the scanner traps need.
//   SK       with neither key, MAP10 prints a SKIP line that names the decision setting.
//   F1       map-fix with no flag names the file and the id on one line, and writes no byte.
//   F2       map-fix --write creates the decisions line right under the map line, and MAP10 then passes.
//   W2       map-fix --write adds the missing id and keeps the ids already on the line, in their order.
//   W3       a second map-fix --write changes no byte.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { HERE, SKILL, run, scratchRepo, setSubLine, subLineIds, tail } from './helpers.mjs';
import { loadMapConfig } from '../scripts/lib/map-config.mjs';
import { blankComments, blankShell } from '../scripts/lib/source-text.mjs';

const CHECK = join(SKILL, 'scripts', 'map-check.mjs');
const UPGRADE = join(SKILL, 'scripts', 'map-upgrade.mjs');
const MAPFIX = join(SKILL, 'scripts', 'map-fix.mjs');
const FIXTURE = join(HERE, 'fixture-decisions');
const CONFIG = 'map.config.json';
const MAP = 'docs/map/core.md';
const RECORDS = 'docs/records';
const TRACKED = [CONFIG, MAP, `${RECORDS}/D007-retry-wait.md`, `${RECORDS}/D018-cache-size.md`, 'src/retry.ts', 'src/page.tsx', 'src/comments.py', 'src/run.sh'];
const BASE = { title: 'Decisions fixture', codeExtensions: ['ts', 'tsx', 'py', 'sh'] };

const repo = () => scratchRepo({ fixture: FIXTURE, track: TRACKED });
const read = (dir, rel) => readFileSync(join(dir, rel), 'utf8');
const write = (dir, rel, text) => writeFileSync(join(dir, rel), text);
const writeConfig = (dir, cfg) => write(dir, CONFIG, `${JSON.stringify(cfg, null, 2)}\n`);
const configFile = (dir) => join(dir, CONFIG);
const runCheck = (dir) => run([CHECK], dir);
// The MAP10 verdict line of a run, or '' when the run prints none.
const ten = (out) => out.split('\n').find((l) => /^\[(PASS|FAIL|SKIP)\] MAP10\b/.test(l)) ?? '';

// ---- The map page: a decisions line is a sub-line of its map line (helpers.mjs holds the one reader and the one setter).
/** The ids on the decisions line of `file`, or [] when it has none. */
const decisionIds = (dir, file) => subLineIds(dir, MAP, file, 'Decisions');
/** Sets the decisions line of `file` to `ids`, or removes it when `ids` is null. Edits the map page only. */
const setDecisions = (dir, file, ids) => setSubLine(dir, MAP, file, 'Decisions', ids);

// ---- Config: both keys or neither.
test('C1. decisionsDir alone is a config error, and the error names decisionIdPattern', () => {
  const dir = repo();
  writeConfig(dir, { formatVersion: 6, ...BASE, decisionsDir: `${RECORDS}/` });
  assert.throws(() => loadMapConfig(configFile(dir), dir), /decisionIdPattern/, 'a config with decisionsDir and no decisionIdPattern must name decisionIdPattern');
});

test('C2. decisionIdPattern alone is a config error, and the error names decisionsDir', () => {
  const dir = repo();
  writeConfig(dir, { formatVersion: 6, ...BASE, decisionIdPattern: 'D\\d+' });
  assert.throws(() => loadMapConfig(configFile(dir), dir), /decisionsDir/, 'a config with decisionIdPattern and no decisionsDir must name decisionsDir');
});

test('C3. control: a version 2 map asks for the upgrade, on the old code and on the new', () => {
  const dir = repo();
  writeConfig(dir, { formatVersion: 2, ...BASE });
  assert.throws(() => loadMapConfig(configFile(dir), dir), /map-upgrade\.mjs/, 'a version 2 map must be refused with the upgrade command');
});

// ---- Format version.
test('V1. format version 6 loads, with both decision keys', () => {
  const dir = repo();
  assert.match(read(dir, CONFIG), /"formatVersion": 6/, 'scope: the fixture config is version 6');
  assert.doesNotThrow(() => loadMapConfig(configFile(dir), dir), 'a version 6 config with both keys must load');
});

test('V2. format version 3 asks for the upgrade: the validator refuses it, and the message names map-upgrade.mjs', () => {
  const dir = repo();
  writeConfig(dir, { formatVersion: 3, ...BASE });
  assert.throws(() => loadMapConfig(configFile(dir), dir), /map-upgrade\.mjs/, 'a version 3 map must be refused with the upgrade command');
});

test('V5. format version 5 asks for the upgrade: the validator refuses it, and the message names map-upgrade.mjs', () => {
  const dir = repo();
  writeConfig(dir, { formatVersion: 5, ...BASE });
  assert.throws(() => loadMapConfig(configFile(dir), dir), /map-upgrade\.mjs/, 'a version 5 map must be refused with the upgrade command');
});

test('V6. format version 6 loads with no decision keys', () => {
  const dir = repo();
  writeConfig(dir, { formatVersion: 6, ...BASE });
  assert.doesNotThrow(() => loadMapConfig(configFile(dir), dir), 'a version 6 config with no decision keys must load');
});

test('V7. map-upgrade from version 5 sets formatVersion to 6, and writes no map page', () => {
  const dir = repo();
  writeConfig(dir, { formatVersion: 5, ...BASE });
  const pageBefore = read(dir, MAP);
  const r = run([UPGRADE], dir);
  assert.equal(JSON.parse(read(dir, CONFIG)).formatVersion, 6, `map-upgrade must set formatVersion to 6\n${tail(r.out)}`);
  assert.equal(read(dir, MAP), pageBefore, 'the upgrade from version 5 changes no map page');
});

test('V3. map-upgrade from version 3 sets formatVersion to 6, and writes no map page', () => {
  const dir = repo();
  writeConfig(dir, { formatVersion: 3, ...BASE });
  const pageBefore = read(dir, MAP);
  const r = run([UPGRADE], dir);
  assert.equal(JSON.parse(read(dir, CONFIG)).formatVersion, 6, `map-upgrade must set formatVersion to 6\n${tail(r.out)}`);
  assert.equal(read(dir, MAP), pageBefore, 'the upgrade from version 3 changes no map page');
});

test('V4. a second map-upgrade run changes no byte of the config or the map page', () => {
  const dir = repo();
  writeConfig(dir, { formatVersion: 3, ...BASE });
  run([UPGRADE], dir);
  assert.equal(JSON.parse(read(dir, CONFIG)).formatVersion, 6, 'the first run must set formatVersion to 6');
  const configOnce = read(dir, CONFIG), pageOnce = read(dir, MAP);
  run([UPGRADE], dir);
  assert.equal(read(dir, CONFIG), configOnce, 'the second run must change no byte of map.config.json');
  assert.equal(read(dir, MAP), pageOnce, 'the second run must change no byte of the map page');
});

// ---- MAP10 on the decisions lines.
test('M1. the fixture with both keys and every line matching: MAP10 passes, no check fails, and the command exits 0', () => {
  const dir = repo();
  const r = runCheck(dir);
  assert.match(ten(r.out), /^\[PASS\] MAP10$/, `MAP10 must pass when every cite has its decisions line\n${tail(r.out)}`);
  assert.doesNotMatch(r.out, /^\[FAIL\]/m, `no check may fail on the fixture\n${tail(r.out)}`);
  assert.equal(r.status, 0, `the command must exit 0 on the fixture\n${tail(r.out)}`);
});

test('M2. (a) a comment cite with no decisions line fails MAP10, and the output names the file and the id', () => {
  const dir = repo();
  assert.match(read(dir, 'src/retry.ts'), /\bD7\b/, 'scope: the comment in src/retry.ts cites D7');
  setDecisions(dir, 'src/retry.ts', null);
  assert.deepEqual(decisionIds(dir, 'src/retry.ts'), [], 'scope: the decisions line is gone');
  const line = ten(runCheck(dir).out);
  assert.match(line, /^\[FAIL\] MAP10/, `MAP10 must fail on a cite with no decisions line\n${tail(line)}`);
  assert.match(line, /src\/retry\.ts/, `the MAP10 failure must name src/retry.ts\n${line}`);
  assert.match(line, /\bD7\b/, `the MAP10 failure must name the id D7\n${line}`);
});

test('M3. (b) a decisions line that names an id with no record fails MAP10, and the output names that id', () => {
  const dir = repo();
  setDecisions(dir, 'src/cache.ts', ['D18', 'D99']);
  assert.ok(!readdirSync(join(dir, RECORDS)).some((f) => f.startsWith('D99')), 'scope: no record D99 exists');
  const line = ten(runCheck(dir).out);
  assert.match(line, /^\[FAIL\] MAP10/, `MAP10 must fail on a decisions line whose id names no record\n${line}`);
  assert.match(line, /\bD99\b/, `the MAP10 failure must name the id D99\n${line}`);
});

test('M4. an id on a decisions line that the file no longer cites is fine: MAP10 passes', () => {
  const dir = repo();
  assert.match(read(dir, 'src/retry.ts'), /\bD7\b/, 'scope: the comment cites D7 before the edit');
  write(dir, 'src/retry.ts', 'export const RETRY_WAIT_S = 30;\n');
  assert.deepEqual(decisionIds(dir, 'src/retry.ts'), ['D7'], 'scope: the decisions line still holds D7');
  assert.match(ten(runCheck(dir).out), /^\[PASS\] MAP10$/, 'MAP10 must pass: D7 names a record, and the file no longer cites it');
});

test('M5. zero-padding: D7 names D007-retry-wait.md by value, so without that record its decisions line fails (b) and names D7', () => {
  const dir = repo();
  const record = join(dir, RECORDS, 'D007-retry-wait.md');
  assert.ok(existsSync(record), 'scope: the record D007-retry-wait.md exists before the edit');
  rmSync(record);
  const line = ten(runCheck(dir).out);
  assert.match(line, /^\[FAIL\] MAP10/, `MAP10 must fail when D7 names no record\n${line}`);
  assert.match(line, /\bD7\b/, `the MAP10 failure must name the id D7\n${line}`);
});

test('M6. D1 names no record: the record D018-cache-size.md holds 18, so a decisions line D1 fails (b) and names D1', () => {
  const dir = repo();
  setDecisions(dir, 'src/labels.py', ['D1']);
  const line = ten(runCheck(dir).out);
  assert.match(line, /^\[FAIL\] MAP10/, `MAP10 must fail on a decisions line D1 that names no record\n${line}`);
  assert.match(line, /\bD1\b/, `the MAP10 failure must name the id D1\n${line}`);
});

test('E1. an empty decisions folder: each decisions line fails (b), and the output names D7 and D18', () => {
  const dir = repo();
  for (const f of ['D007-retry-wait.md', 'D018-cache-size.md']) {
    assert.ok(existsSync(join(dir, RECORDS, f)), `scope: the record ${f} exists before the edit`);
    rmSync(join(dir, RECORDS, f));
  }
  const line = ten(runCheck(dir).out);
  assert.match(line, /^\[FAIL\] MAP10/, `MAP10 must fail when no record exists\n${line}`);
  assert.match(line, /\bD7\b/, `the MAP10 failure must name D7\n${line}`);
  assert.match(line, /\bD18\b/, `the MAP10 failure must name D18\n${line}`);
});

// ---- Scanner traps, JS and TS. A string is never a cite.
test('S-js. an id in a JS string literal is no cite: MAP10 passes', () => {
  const dir = repo();
  assert.match(read(dir, 'src/strings.ts'), /"decision D7"/, 'scope: the string holds D7');
  assert.match(ten(runCheck(dir).out), /^\[PASS\] MAP10$/, 'MAP10 must pass: an id in a string is no cite');
});

test('S-openers. "/*" and "//" inside string literals open no comment, so an id after them is no cite: MAP10 passes', () => {
  const dir = repo();
  assert.match(read(dir, 'src/openers.ts'), /"\/\*"[\s\S]*"see \/\/ D18"/, 'scope: the file holds "/*" and "see // D18" in strings');
  assert.match(ten(runCheck(dir).out), /^\[PASS\] MAP10$/, 'MAP10 must pass: the ids are inside strings');
});

test('S-template. an id in a multi-line template literal, on a line that starts with // or /*, is no cite: MAP10 passes', () => {
  const dir = repo();
  assert.match(read(dir, 'src/template.ts'), /^\/\/ D18 appears in the page text$/m, 'scope: the template holds a line that starts with //');
  assert.match(ten(runCheck(dir).out), /^\[PASS\] MAP10$/, 'MAP10 must pass: a template literal holds no comment');
});

test('S-jsx. a lone quote in JSX text does not hide the // D7 comment after it: MAP10 fails without its decisions line', () => {
  const dir = repo();
  assert.match(read(dir, 'src/page.tsx'), /<p>Don't<\/p>; \/\/ D7/, "scope: the comment after the apostrophe cites D7");
  setDecisions(dir, 'src/page.tsx', null);
  const line = ten(runCheck(dir).out);
  assert.match(line, /^\[FAIL\] MAP10/, `MAP10 must fail on the cite after a JSX apostrophe\n${line}`);
  assert.match(line, /src\/page\.tsx/, `the MAP10 failure must name src/page.tsx\n${line}`);
  assert.match(line, /\bD7\b/, `the MAP10 failure must name the id D7\n${line}`);
});

// ---- Python: a `#` comment is a cite; a string, a triple-quoted string included, is not.
test('P-cite. a # D7 comment in a .py file is a cite: without its decisions line MAP10 fails, and names the file and D7', () => {
  const dir = repo();
  assert.match(read(dir, 'src/comments.py'), /^# .*\bD7\b/m, 'scope: the comment in src/comments.py cites D7');
  setDecisions(dir, 'src/comments.py', null);
  const line = ten(runCheck(dir).out);
  assert.match(line, /^\[FAIL\] MAP10/, `MAP10 must fail on a Python # cite with no decisions line\n${line}`);
  assert.match(line, /src\/comments\.py/, `the MAP10 failure must name src/comments.py\n${line}`);
  assert.match(line, /\bD7\b/, `the MAP10 failure must name the id D7\n${line}`);
});

test('P-string. an id inside a Python string, "# D7" included, is no cite: MAP10 passes', () => {
  const dir = repo();
  assert.match(read(dir, 'src/labels.py'), /"see # D7"/, 'scope: the string holds # D7');
  assert.match(ten(runCheck(dir).out), /^\[PASS\] MAP10$/, 'MAP10 must pass: a # inside a string is no comment');
});

test('P-triple. a # D18 line inside a triple-quoted Python string is no cite: MAP10 passes', () => {
  const dir = repo();
  assert.match(read(dir, 'src/docs.py'), /"""\n# D18 appears in the text\n"""/, 'scope: the triple-quoted string holds a # D18 line');
  assert.match(ten(runCheck(dir).out), /^\[PASS\] MAP10$/, 'MAP10 must pass: a triple-quoted string is text');
});

// ---- Shell: a `#` comment is a cite; a double-quoted string is not.
test('SH-cite. a # D7 comment in a .sh file is a cite: without its decisions line MAP10 fails, and names the file and D7', () => {
  const dir = repo();
  assert.match(read(dir, 'src/run.sh'), /^# .*\bD7\b/m, 'scope: the comment in src/run.sh cites D7');
  setDecisions(dir, 'src/run.sh', null);
  const line = ten(runCheck(dir).out);
  assert.match(line, /^\[FAIL\] MAP10/, `MAP10 must fail on a shell # cite with no decisions line\n${line}`);
  assert.match(line, /src\/run\.sh/, `the MAP10 failure must name src/run.sh\n${line}`);
  assert.match(line, /\bD7\b/, `the MAP10 failure must name the id D7\n${line}`);
});

test('SH-string. an id inside a double-quoted shell string, "# D18" included, is no cite: MAP10 passes', () => {
  const dir = repo();
  assert.match(read(dir, 'src/run.sh'), /echo "# D18 is text"/, 'scope: the shell string holds # D18');
  assert.match(ten(runCheck(dir).out), /^\[PASS\] MAP10$/, 'MAP10 must pass: a # inside a shell string is no comment');
});

// ---- Controls: the existing readers, which the traps above depend on. Each holds on the old code and the new.
test('K-jsx. control: the existing reader blanks the comment after a JSX apostrophe and keeps the element', () => {
  const dir = repo();
  const out = blankComments(read(dir, 'src/page.tsx'), 'src/page.tsx');
  assert.match(out, /<p>Don't<\/p>/, 'the JSX text must be kept as written');
  assert.doesNotMatch(out, /D7/, 'the comment after the apostrophe must be blanked');
});

test('K-openers. control: the existing reader keeps the strings that hold "/*" and "//"', () => {
  const dir = repo();
  const out = blankComments(read(dir, 'src/openers.ts'), 'src/openers.ts');
  assert.match(out, /"decision D7"/, 'the string after "/*" must be kept');
  assert.match(out, /"see \/\/ D18"/, 'the string holding "//" must be kept');
});

test('K-template. control: the existing reader keeps a multi-line template literal whole', () => {
  const dir = repo();
  const out = blankComments(read(dir, 'src/template.ts'), 'src/template.ts');
  assert.match(out, /\/\/ D18 appears in the page text/, 'the template text must be kept');
});

test('K-sh. control: the existing shell reader blanks the shell comment and the text of the string', () => {
  const dir = repo();
  const out = blankShell(read(dir, 'src/run.sh'));
  assert.doesNotMatch(out, /D7/, 'the shell comment must be blanked');
  assert.doesNotMatch(out, /D18/, 'the id inside the double-quoted string must be blanked');
});

// ---- Skip.
test('SK. with neither decision key, MAP10 prints a SKIP line that names the decision setting, and the command exits 0', () => {
  const dir = repo();
  writeConfig(dir, { formatVersion: 6, ...BASE });
  const r = runCheck(dir);
  assert.match(ten(r.out), /^\[SKIP\] MAP10 .*decision/, `MAP10 must print a SKIP line when no decision key is set\n${tail(r.out)}`);
  assert.equal(r.status, 0, `a SKIP is no failure, so the command must exit 0\n${tail(r.out)}`);
});

// ---- map-fix: add-only.
test('F1. map-fix with no flag prints one line that names src/retry.ts and D7, and writes no byte', () => {
  const dir = repo();
  setDecisions(dir, 'src/retry.ts', null);
  const before = read(dir, MAP);
  const r = run([MAPFIX], dir);
  assert.ok(r.out.split('\n').some((l) => l.includes('src/retry.ts') && /\bD7\b/.test(l)), `the preview must print one line that names src/retry.ts and D7\n${tail(r.out)}`);
  assert.equal(read(dir, MAP), before, 'the preview must write no byte of docs/map/core.md');
});

test('F2. map-fix --write creates the decisions line right under the map line of src/retry.ts, and MAP10 then passes', () => {
  const dir = repo();
  setDecisions(dir, 'src/retry.ts', null);
  run([MAPFIX, '--write'], dir);
  assert.deepEqual(decisionIds(dir, 'src/retry.ts'), ['D7'], '--write must add a decisions line with D7 right under the map line');
  // The position, asserted again: the line directly under the map line of src/retry.ts is the decisions line.
  const lines = read(dir, MAP).split('\n');
  const at = lines.findIndex((l) => l.startsWith('- `src/retry.ts` '));
  assert.ok(at >= 0, `scope: the map page holds the map line of src/retry.ts\n${tail(read(dir, MAP))}`);
  assert.match(lines[at + 1] ?? '', /^ {2}- Decisions: `D7`$/, '--write must put the decisions line directly under the map line of src/retry.ts');
  assert.match(ten(runCheck(dir).out), /^\[PASS\] MAP10$/, 'MAP10 must pass after --write');
});

test('W2. map-fix --write adds the missing D7, and keeps the ids already on the line (D99, D18) in their order', () => {
  const dir = repo();
  setDecisions(dir, 'src/retry.ts', ['D99', 'D18']);
  run([MAPFIX, '--write'], dir);
  const ids = decisionIds(dir, 'src/retry.ts');
  assert.ok(ids.includes('D7'), `--write must add the missing D7. The line holds ${ids.join(', ')}`);
  assert.ok(ids.includes('D99') && ids.includes('D18'), `--write must never remove an id. The line holds ${ids.join(', ')}`);
  assert.ok(ids.indexOf('D99') < ids.indexOf('D18'), `--write must never reorder an id. The line holds ${ids.join(', ')}`);
});

test('W3. a second map-fix --write changes no byte of docs/map/core.md', () => {
  const dir = repo();
  setDecisions(dir, 'src/retry.ts', null);
  run([MAPFIX, '--write'], dir);
  assert.deepEqual(decisionIds(dir, 'src/retry.ts'), ['D7'], 'the first --write must add D7');
  const once = read(dir, MAP);
  run([MAPFIX, '--write'], dir);
  assert.equal(read(dir, MAP), once, 'the second --write must change no byte of the map page');
});

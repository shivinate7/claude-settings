// The non-code files that a record names on the plain-English map: a decision record (in `decisionsDir`) and a debt record
// (in the debts folder that lint/layout.json gives).
// Fixture: `tests/fixture-decisions/`, copied into a scratch repository. Each case writes its own files, records and map lines into that copy.
//
// The design, as pinned by the brief and the coordinator's ruling (the builder implements it):
//   - A record names a file only by a backticked token that equals a tracked repo path exactly. A bare name, a prefix or a suffix names nothing.
//   - A tracked file that a record names needs a map line (MAP1), still filtered by `mapPaths`.
//   - Files in the decisions folder, in the debts folder, docs/map/ pages and map.config.json never need one.
//   - A non-code file's map line carries `  - Decisions: ` with the id of each naming decision record (the leading match of
//     decisionIdPattern on the record stem), and `  - Debts: ` with the slug (file stem) of each naming debt record.
//   - The debt records are the .md files directly in the debts folder, except notes.md and README.md.
//   - A code file keeps today's behaviour: no id is required of it from a record.
//   - The debts folder comes from lint/layout.json through lint/layout.py `path()`. map.config.json has no key for it.
//
// Assumed, not pinned by the brief: the non-code map lines sit under `## Code files`; the cases read any `[FAIL]` line for a bad
// id or slug, since the check that owns the Debts line is not named; a debt that names a code file adds no requirement (DB9).
//
// Red on the old code. The scratch config is written at MAP_FORMAT_VERSION, so on the old code (version 5) it loads, and each red case
// fails on its own missing line, id or slug. Green on the old code, by design: the stays-out and mapPaths-filter cases
// (N5, N6, N7, N8, N11, N13, DB5, DB6, DB9, DB10). Each names the mutant that turns it red.
//
// Cases:
//   N1       a .png a decision record names needs a map line: MAP1 fails and names it.
//   N2       its map line needs the record's id: MAP10 names the .png and D021, and no D18 from the bytes (the bytes hold `# D18`).
//   N3       an extensionless LICENSE a record names needs a map line.
//   N4       a JSON manifest a record names (exact path) needs a map line.
//   N5       near miss: a bare `app.json` names data/app.json and app.json.bak no more; MAP1 passes.   [green]
//   N6       a record that names another record: the named record needs no map line.                   [green]
//   N7       an unnamed .png needs no map line.                                                         [green]
//   N8       control: a code file a record names needs no record id on its map line.                    [green]
//   N9       map-fix --write adds the record's id to the .png's map line, and no id from the bytes.
//   N10      map-show prints the map line and the Decisions line of a .png a record names.
//   N11      control: with no decision keys, no record is read, and a .png a record names needs no line. [green]
//   N12      full size: two records name one .png, and its map line must hold both ids.
//   N13      mapPaths filters a named .png out: under src/ only, MAP1 passes.                           [green]
//   N14      mapPaths includes assets/: the named .png needs a map line.
//   N15      a README.md in decisionsDir is no record: a file only it names needs no map line.
//   N16      map-show <decision-id> lists a non-code file whose Decisions line carries that id.
//   N17      a notes.md directly in decisionsDir is no record: a file only it names needs no map line.
//   N18      README and notes under a slug-style decisionIdPattern: an id of either names no record, and MAP10 fails on each by name.   [green]
//   N19      map-show README and notes name no record: exit 1, nothing on stdout, and no record file printed.                          [green]
//   N20      a tracked .svg inside decisionsDir, and no record, that a decision record names needs a map line: MAP1 fails and names it.
//   N21      a record that names README.md or notes.md in decisionsDir asks for no map line: MAP1 passes.                                 [green]
//   N22      a record that names a nested .md under decisionsDir asks for a map line: MAP1 fails and names it.                          [green]
//   DB1      a .svg a debt record names needs a map line: MAP1 fails and names it.
//   DB2      its map line needs a Debts line with the slug: the failure names the file and the slug.
//   DB3      control: a map line with `  - Debts: ` naming the slug: no check fails.                     [green]
//   DB4      a Debts line that names notes (notes.md is no debt) or a slug with no file fails.
//   DB5      notes.md and README.md in the debts folder that name a file are no debt: no map line.       [green]
//   DB6      a Debts line whose slug names a debt that no longer names the file: fine (exists-only).     [green]
//   DB7      map-fix --write adds the missing slug to the .svg's map line.
//   DB8      map-show prints the Debts line of a .svg a debt record names.
//   DB9      control: a debt that names a code file adds no requirement.                                 [green]
//   DB10     empty state: no debts folder at all, no check fails, and nothing reads a missing folder.    [green]
//   DB11     full size: two debt records name one .svg, and its map line must hold both slugs.
//   DB12     a tracked .svg inside the debts folder, and no debt, that a debt names needs a map line: MAP1 fails and names it.
//   DB13     a debt that names README.md or notes.md in the debts folder asks for no map line: MAP1 passes.                              [green]
//   DB14     a debt that names a nested .md under the debts folder asks for a map line: MAP1 fails and names it.                        [green]
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { HERE, SKILL, debtsDirOf, failLines, gitIn, readIn, run, scratchRepo, setSubLine, subLineIds, tail, verdictOf, writeIn } from './helpers.mjs';
import { MAP_FORMAT_VERSION, loadMapConfig } from '../scripts/lib/map-config.mjs';

const CHECK = join(SKILL, 'scripts', 'map-check.mjs');
const MAPFIX = join(SKILL, 'scripts', 'map-fix.mjs');
const SHOW = join(SKILL, 'scripts', 'map-show.mjs');
const FIXTURE = join(HERE, 'fixture-decisions');
const CONFIG = 'map.config.json';
const MAP = 'docs/map/core.md';
const RECORDS = 'docs/records';
const LAYOUT_EXTRAS = '.claude/layout-extras.json';
const BASE = { title: 'Named fixture', codeExtensions: ['ts', 'tsx', 'py', 'sh'] };
const TRACK = [CONFIG, MAP, `${RECORDS}/D007-retry-wait.md`, `${RECORDS}/D018-cache-size.md`, 'src/retry.ts', 'src/strings.ts'];
const PNG_PATH = 'assets/logo.png';
const SVG_PATH = 'assets/badge.svg';

// Bytes that are not UTF-8, with the text `# D18` inside. A reader that took the bytes for code would find the cite.
const PNG = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0xff, 0x00]), Buffer.from('# D18 tEXt\n'), Buffer.from([0x00, 0xfe, 0xc3])]);
const SVG = '<svg xmlns="http://www.w3.org/2000/svg"/>\n';

/** A record of the given heading that names each path in backticks: the only form that names a file. */
const record = (heading, names) => `# ${heading}\n\n${names.map((n) => `Names \`${n}\`.`).join('\n')}\n`;
/** A map line for `file`, with a plain sentence that holds no digit (MAP9 reads a number outside backticks). */
const mapLine = (file, sentence) => `- \`${file}\` — ${sentence}`;

/**
 * A scratch repository on the decisions fixture. Its config is at MAP_FORMAT_VERSION, and its layout is rolled out, so the debts folder is the one
 * lint/layout.json gives. `keys: false` leaves out both decision keys. `mapPaths` adds that key. `idPattern` is the decision id pattern, D\d+ by default.
 */
const scratch = ({ keys = true, mapPaths, idPattern = 'D\\d+' } = {}) => {
  const dir = scratchRepo({ fixture: FIXTURE, track: TRACK });
  const cfg = {
    formatVersion: MAP_FORMAT_VERSION,
    ...BASE,
    ...(keys ? { decisionsDir: `${RECORDS}/`, decisionIdPattern: idPattern } : {}),
    ...(mapPaths ? { mapPaths } : {}),
  };
  writeIn(dir, CONFIG, `${JSON.stringify(cfg, null, 2)}\n`);
  mkdirSync(join(dir, '.claude'), { recursive: true });
  writeIn(dir, LAYOUT_EXTRAS, '{"rolled-out": true, "kinds": {}}\n');
  // A `mapPaths` entry must name a tracked file, so its cases check the config after they add their files.
  if (!mapPaths) assert.doesNotThrow(() => loadMapConfig(join(dir, CONFIG), dir), 'scope: the scratch config loads at the skill version');
  return dir;
};

/** Writes a file into the scratch repository and lists it, so `git ls-files` and every check see it. */
const addFile = (dir, rel, body) => {
  mkdirSync(dirname(join(dir, rel)), { recursive: true });
  writeIn(dir, rel, body);
  gitIn(dir, 'add', '-N', rel);
  assert.ok(gitIn(dir, 'ls-files').split('\n').includes(rel), `scope: ${rel} is tracked`);
};

/** Appends map lines to `docs/map/core.md`, which ends in its `## Code files` list. */
const addMapLines = (dir, lines) => writeIn(dir, MAP, `${readIn(dir, MAP).replace(/\n*$/, '\n')}${lines.join('\n')}\n`);

/** True when a `[FAIL]` line of `out` names check `id` and `text`. */
const failed = (out, id, text) => failLines(out).some((l) => new RegExp(`^\\[FAIL\\] ${id}\\b`).test(l) && l.includes(text));

const DECISION = `${RECORDS}/D021-logo-art.md`;

// ---- Decision records: a non-code file that a decision record names needs a map line, and the record's id on it.

test('N1. a binary .png that a decision record names needs a map line: MAP1 fails and names the file', () => {
  const dir = scratch();
  addFile(dir, PNG_PATH, PNG);
  addFile(dir, DECISION, record('D021 Logo art', [PNG_PATH]));
  assert.doesNotMatch(readIn(dir, MAP), /assets\/logo\.png/, 'scope: the map page has no line for the .png');
  const out = run([CHECK], dir).out;
  assert.ok(failed(out, 'MAP1', PNG_PATH), `MAP1 must fail on a .png that D021 names, with no map line\n${tail(out)}`);
});

test('N2. the map line of a .png a record names needs the record id: MAP10 names the file and D021, and no D18 from the bytes', () => {
  const dir = scratch();
  addFile(dir, PNG_PATH, PNG);
  addFile(dir, DECISION, record('D021 Logo art', [PNG_PATH]));
  addMapLines(dir, [mapLine(PNG_PATH, 'Holds the logo art.')]);
  assert.deepEqual(subLineIds(dir, MAP, PNG_PATH, 'Decisions'), [], 'scope: the map line has no Decisions line');
  assert.match(readIn(dir, PNG_PATH), /# D18/, 'scope: the bytes hold the text # D18, and no record names the .png with D018');
  const out = run([CHECK], dir).out;
  assert.ok(failLines(out).some((l) => l.includes(PNG_PATH) && /\bD021\b/.test(l)), `MAP10 must fail naming the .png and D021\n${tail(out)}`);
  assert.ok(!/\bD0?18\b/.test(failLines(out).join('\n')), `the failure must name no D18: the bytes are not read\n${tail(out)}`);
});

test('N3. an extensionless LICENSE that a record names needs a map line: MAP1 fails and names it', () => {
  const dir = scratch();
  addFile(dir, 'LICENSE', 'MIT License\n');
  addFile(dir, `${RECORDS}/D022-licence.md`, record('D022 Licence', ['LICENSE']));
  assert.doesNotMatch(readIn(dir, MAP), /`LICENSE`/, 'scope: the map page has no line for LICENSE');
  const out = run([CHECK], dir).out;
  assert.ok(failed(out, 'MAP1', 'LICENSE'), `MAP1 must fail on an extensionless LICENSE that D022 names\n${tail(out)}`);
});

test('N4. a JSON manifest that a record names by its exact path needs a map line: MAP1 fails and names it', () => {
  const dir = scratch();
  addFile(dir, 'web/manifest.json', '{"name": "logo"}\n');
  addFile(dir, `${RECORDS}/D023-manifest.md`, record('D023 Manifest', ['web/manifest.json']));
  assert.doesNotMatch(readIn(dir, MAP), /web\/manifest\.json/, 'scope: the map page has no line for the manifest');
  const out = run([CHECK], dir).out;
  assert.ok(failed(out, 'MAP1', 'web/manifest.json'), `MAP1 must fail on a manifest that D023 names by its exact path\n${tail(out)}`);
});

test('N5. near miss: a bare app.json that a record writes names data/app.json and app.json.bak no more, so MAP1 passes', () => {
  const dir = scratch();
  addFile(dir, 'data/app.json', '{"a": 1}\n');
  addFile(dir, 'app.json.bak', '{"a": 2}\n');
  addFile(dir, `${RECORDS}/D024-app-json.md`, record('D024 App json', ['app.json']));
  assert.ok(readIn(dir, `${RECORDS}/D024-app-json.md`).includes('`app.json`'), 'scope: the record writes the bare name app.json');
  const out = run([CHECK], dir).out;
  assert.equal(verdictOf(out, 'MAP1'), 'PASS', `MAP1 must pass: a bare name names no file\n${tail(out)}`);
  assert.ok(failLines(out).every((l) => !l.includes('app.json')), `no check may name data/app.json or app.json.bak\n${tail(out)}`);
});

test('N6. a decision record that names another record needs no map line for it: MAP1 passes and names no D018 file', () => {
  const dir = scratch();
  addFile(dir, `${RECORDS}/D025-names-record.md`, record('D025 Names a record', [`${RECORDS}/D018-cache-size.md`]));
  assert.match(readIn(dir, `${RECORDS}/D025-names-record.md`), /D018-cache-size\.md/, 'scope: D025 names the record D018');
  const out = run([CHECK], dir).out;
  assert.equal(verdictOf(out, 'MAP1'), 'PASS', `MAP1 must pass: a record is never a file that needs a map line\n${tail(out)}`);
  assert.ok(failLines(out).every((l) => !l.includes('D018-cache-size')), `no check may name the record D018\n${tail(out)}`);
});

test('N7. a .png that no record names needs no map line: MAP1 passes', () => {
  const dir = scratch();
  addFile(dir, 'assets/unused.png', PNG);
  const out = run([CHECK], dir).out;
  assert.equal(verdictOf(out, 'MAP1'), 'PASS', `MAP1 must pass: no record names the .png\n${tail(out)}`);
});

test('N8. control: a code file that a record names needs no record id on its map line: MAP10 passes', () => {
  const dir = scratch();
  addFile(dir, `${RECORDS}/D026-strings.md`, record('D026 Strings', ['src/strings.ts']));
  assert.deepEqual(subLineIds(dir, MAP, 'src/strings.ts', 'Decisions'), [], 'scope: the map line of src/strings.ts has no Decisions line');
  const out = run([CHECK], dir).out;
  assert.equal(verdictOf(out, 'MAP10'), 'PASS', `MAP10 must pass: a code file keeps today's behaviour\n${tail(out)}`);
});

test('N9. map-fix --write adds D021 to the map line of the .png, and adds no id from the bytes', () => {
  const dir = scratch();
  addFile(dir, PNG_PATH, PNG);
  addFile(dir, DECISION, record('D021 Logo art', [PNG_PATH]));
  addMapLines(dir, [mapLine(PNG_PATH, 'Holds the logo art.')]);
  assert.deepEqual(subLineIds(dir, MAP, PNG_PATH, 'Decisions'), [], 'scope: the map line has no Decisions line');
  const r = run([MAPFIX, '--write'], dir);
  assert.deepEqual(subLineIds(dir, MAP, PNG_PATH, 'Decisions'), ['D021'], `map-fix --write must add D021, and only D021, to the .png's map line\n${tail(r.out)}`);
});

test('N10. map-show prints the map line and the Decisions line of a .png that a record names', () => {
  const dir = scratch();
  addFile(dir, PNG_PATH, PNG);
  addFile(dir, DECISION, record('D021 Logo art', [PNG_PATH]));
  addMapLines(dir, [mapLine(PNG_PATH, 'Holds the logo art.'), '  - Decisions: `D021`']);
  assert.deepEqual(subLineIds(dir, MAP, PNG_PATH, 'Decisions'), ['D021'], 'scope: the map page holds the Decisions line');
  const r = run([SHOW, PNG_PATH], dir);
  assert.equal(r.status, 0, `map-show must find the .png's map line\n${tail(r.out)}`);
  assert.ok(r.stdout.includes('Holds the logo art.'), `map-show must print the map line of the .png\n${tail(r.out)}`);
  assert.match(r.stdout, /Decisions:.*\bD021\b/, `map-show must print the Decisions line of the .png with D021\n${tail(r.out)}`);
});

test('N11. control: with no decision keys, no record is read, and a .png a record names needs no map line', () => {
  const dir = scratch({ keys: false });
  addFile(dir, PNG_PATH, PNG);
  addFile(dir, DECISION, record('D021 Logo art', [PNG_PATH]));
  assert.equal(JSON.parse(readIn(dir, CONFIG)).decisionsDir, undefined, 'scope: the config has no decisionsDir');
  const out = run([CHECK], dir).out;
  assert.equal(verdictOf(out, 'MAP1'), 'PASS', `MAP1 must pass: with no decisionsDir no record is read\n${tail(out)}`);
  assert.equal(verdictOf(out, 'MAP10'), 'SKIP', `MAP10 must skip with no decision keys\n${tail(out)}`);
});

test('N12. full size: two records name one .png, and its map line must hold both ids: a missing one fails by name', () => {
  const dir = scratch();
  addFile(dir, PNG_PATH, PNG);
  addFile(dir, DECISION, record('D021 Logo art', [PNG_PATH]));
  addFile(dir, `${RECORDS}/D027-logo-brand.md`, record('D027 Logo brand', [PNG_PATH]));
  addMapLines(dir, [mapLine(PNG_PATH, 'Holds the logo art.'), '  - Decisions: `D021`']);
  assert.deepEqual(subLineIds(dir, MAP, PNG_PATH, 'Decisions'), ['D021'], 'scope: the map line holds D021 only');
  const out = run([CHECK], dir).out;
  assert.ok(failLines(out).some((l) => l.includes(PNG_PATH) && /\bD027\b/.test(l)), `MAP10 must fail naming the .png and D027\n${tail(out)}`);
});

test('N13. mapPaths filters out a .png that a record names: under src/ only, MAP1 passes', () => {
  const dir = scratch({ mapPaths: ['src/'] });
  addFile(dir, PNG_PATH, PNG);
  addFile(dir, DECISION, record('D021 Logo art', [PNG_PATH]));
  assert.doesNotThrow(() => loadMapConfig(join(dir, CONFIG), dir), 'scope: the config loads, with mapPaths naming a tracked file');
  assert.deepEqual(JSON.parse(readIn(dir, CONFIG)).mapPaths, ['src/'], 'scope: mapPaths is src/ only');
  const out = run([CHECK], dir).out;
  assert.equal(verdictOf(out, 'MAP1'), 'PASS', `MAP1 must pass: assets/ is outside mapPaths\n${tail(out)}`);
});

test('N14. mapPaths includes assets/: the .png that a record names needs a map line, and MAP1 names it', () => {
  const dir = scratch({ mapPaths: ['assets/'] });
  addFile(dir, PNG_PATH, PNG);
  addFile(dir, DECISION, record('D021 Logo art', [PNG_PATH]));
  assert.doesNotThrow(() => loadMapConfig(join(dir, CONFIG), dir), 'scope: the config loads, with mapPaths naming a tracked file');
  assert.deepEqual(JSON.parse(readIn(dir, CONFIG)).mapPaths, ['assets/'], 'scope: mapPaths is assets/');
  const out = run([CHECK], dir).out;
  assert.ok(failed(out, 'MAP1', PNG_PATH), `MAP1 must fail on a .png under mapPaths that D021 names\n${tail(out)}`);
});

test('N15. a README.md directly in decisionsDir is no record: a file only it names needs no map line, and a file a real record names still does', () => {
  const dir = scratch();
  addFile(dir, PNG_PATH, PNG);
  addFile(dir, DECISION, record('D021 Logo art', [PNG_PATH]));
  addFile(dir, 'assets/notes-only.png', PNG);
  addFile(dir, `${RECORDS}/README.md`, record('Readme', ['assets/notes-only.png']));
  assert.match(readIn(dir, `${RECORDS}/README.md`), /notes-only\.png/, 'scope: the README in the decisions folder names the .png');
  const out = run([CHECK], dir).out;
  assert.ok(failed(out, 'MAP1', PNG_PATH), `MAP1 must fail on the .png that the record D021 names\n${tail(out)}`);
  assert.ok(failLines(out).every((l) => !l.includes('notes-only')), `no check may name the file that only README.md names\n${tail(out)}`);
});

test('N16. map-show <decision-id> lists a non-code file whose Decisions line carries that id, with its map line', () => {
  const dir = scratch();
  addFile(dir, PNG_PATH, PNG);
  addFile(dir, DECISION, record('D021 Logo art', [PNG_PATH]));
  addMapLines(dir, [mapLine(PNG_PATH, 'Holds the logo art.'), '  - Decisions: `D021`']);
  assert.deepEqual(subLineIds(dir, MAP, PNG_PATH, 'Decisions'), ['D021'], 'scope: the map page holds the Decisions line of the .png');
  const r = run([SHOW, 'D021'], dir);
  assert.equal(r.status, 0, `map-show D021 must list the .png, which carries D021\n${tail(r.out)}`);
  assert.ok(r.stdout.includes(`${PNG_PATH} — Holds the logo art.`), `map-show D021 must print the map line of the .png\n${tail(r.out)}`);
});

test('N17. a notes.md directly in decisionsDir is no record: a file only it names needs no map line', () => {
  const dir = scratch();
  addFile(dir, 'assets/notes-only.png', PNG);
  addFile(dir, `${RECORDS}/notes.md`, record('Notes', ['assets/notes-only.png']));
  assert.match(readIn(dir, `${RECORDS}/notes.md`), /notes-only\.png/, 'scope: the notes.md in the decisions folder names the .png');
  const out = run([CHECK], dir).out;
  assert.equal(verdictOf(out, 'MAP1'), 'PASS', `MAP1 must pass: a notes.md in the decisions folder is no record\n${tail(out)}`);
});

// A slug-style id: the pattern accepts `README` and `notes` as ids, so only the record readers' skip stops either one naming a record.
const SLUG_ID = '[A-Za-z][A-Za-z0-9-]*';

/** A README.md and a notes.md in the decisions folder, the files a record reader must skip. */
const addNonRecords = (dir) => {
  addFile(dir, `${RECORDS}/README.md`, '# Records\n\nThe index of this folder.\n');
  addFile(dir, `${RECORDS}/notes.md`, '# Notes\n\nA note, and no record.\n');
};

test('N18. README and notes are no record: an id of either on a Decisions line names none, and MAP10 fails on each by name', () => {
  const dir = scratch({ idPattern: SLUG_ID });
  addNonRecords(dir);
  setSubLine(dir, MAP, 'src/strings.ts', 'Decisions', ['README', 'notes']);
  // The scope first: the folder holds notes.md, and the decisions line of the code file holds both ids.
  assert.ok(existsSync(join(dir, RECORDS, 'notes.md')), 'scope: the decisions folder holds notes.md');
  assert.deepEqual(subLineIds(dir, MAP, 'src/strings.ts', 'Decisions'), ['README', 'notes'], 'scope: the decisions line of src/strings.ts holds README and notes');
  const out = run([CHECK], dir).out;
  assert.ok(failed(out, 'MAP10', 'lists README, and no record in docs/records/ names it'), `MAP10 must fail on the id README: no record names it\n${tail(out)}`);
  assert.ok(failed(out, 'MAP10', 'lists notes, and no record in docs/records/ names it'), `MAP10 must fail on the id notes: no record names it\n${tail(out)}`);
});

test('N19. map-show README and notes name no record: each exits 1 with nothing on stdout, and no record file is printed', () => {
  const dir = scratch({ idPattern: SLUG_ID });
  addNonRecords(dir);
  setSubLine(dir, MAP, 'src/strings.ts', 'Decisions', ['README', 'notes']);
  // The scope first: under the slug pattern a real id still prints its citing line, or "no record" holds for a command that printed nothing.
  const scope = run([SHOW, 'D18'], dir);
  assert.equal(scope.status, 0, `the real id D18 must exit 0 under the slug pattern\n${tail(scope.out)}`);
  assert.ok(scope.stdout.includes('src/cache.ts'), `D18 must print the map line of src/cache.ts\n${tail(scope.out)}`);
  for (const id of ['README', 'notes']) {
    const r = run([SHOW, id, '--full'], dir);
    assert.equal(r.status, 1, `${id} names no record, so map-show must exit 1\n${tail(r.out)}`);
    assert.equal(r.stdout.trim(), '', `${id} names no record, so nothing may print on stdout\n${tail(r.out)}`);
    assert.equal(r.out.trim(), `no record names ${id} in docs/records/`, `stderr must hold one line: no record names ${id}\n${tail(r.out)}`);
  }
});

// The target side of `recordIn`: a folder's README.md and notes.md are no record, so a record that names one asks for no map line.
test('N21. a record that names README.md or notes.md in decisionsDir asks for no map line: MAP1 passes', () => {
  const dir = scratch();
  addFile(dir, `${RECORDS}/README.md`, '# Records\n\nThe index of this folder.\n');
  addFile(dir, `${RECORDS}/notes.md`, '# Notes\n\nA note, and no record.\n');
  addFile(dir, `${RECORDS}/D033-index.md`, record('D033 Index', [`${RECORDS}/README.md`, `${RECORDS}/notes.md`]));
  // The scope first: D033 names both files by their backticked paths, and the map page has no line for either.
  assert.ok(readIn(dir, `${RECORDS}/D033-index.md`).includes(`\`${RECORDS}/README.md\``), 'scope: D033 names README.md by its backticked path');
  assert.ok(readIn(dir, `${RECORDS}/D033-index.md`).includes(`\`${RECORDS}/notes.md\``), 'scope: D033 names notes.md by its backticked path');
  assert.doesNotMatch(readIn(dir, MAP), /README\.md|notes\.md/, 'scope: the map page has no line for either file');
  const out = run([CHECK], dir).out;
  assert.equal(verdictOf(out, 'MAP1'), 'PASS', `MAP1 must pass: README.md and notes.md are no record, so a record that names them asks for no map line\n${tail(out)}`);
});

// The nested side of `recordIn`: only a file directly in decisionsDir is a record, so a record that names a nested file asks for a map line.
test('N22. a record that names a nested .md under decisionsDir asks for a map line: MAP1 fails and names it', () => {
  const dir = scratch();
  const nested = `${RECORDS}/sub/x.md`;
  addFile(dir, nested, '# A nested note\n\nA file under a sub-folder, and no record.\n');
  addFile(dir, `${RECORDS}/D034-nested.md`, record('D034 Nested', [nested]));
  // The scope first: the nested file has no map line, and D034 names it by its backticked path.
  assert.doesNotMatch(readIn(dir, MAP), /sub\/x\.md/, 'scope: the map page has no line for the nested file');
  assert.ok(readIn(dir, `${RECORDS}/D034-nested.md`).includes(`\`${nested}\``), 'scope: D034 names the nested file by its backticked path');
  const out = run([CHECK], dir).out;
  assert.ok(failed(out, 'MAP1', nested), `MAP1 must fail on the nested file that D034 names: only a file directly in decisionsDir is a record\n${tail(out)}`);
});

// A file inside the decisions folder that is no record: a decision record names it, so it needs a map line.
const DIAGRAM = `${RECORDS}/diagram.svg`;
const DIAGRAM_RECORD = `${RECORDS}/D031-diagram.md`;

test('N20. a tracked .svg inside decisionsDir, and no record, that a decision record names needs a map line: MAP1 fails and names it', () => {
  const dir = scratch();
  addFile(dir, DIAGRAM, SVG);
  addFile(dir, DIAGRAM_RECORD, record('D031 Diagram', [DIAGRAM]));
  // The scope first: the svg has no map line, and D031 names it by its backticked path.
  assert.doesNotMatch(readIn(dir, MAP), /diagram\.svg/, 'scope: the map page has no line for the svg');
  assert.ok(readIn(dir, DIAGRAM_RECORD).includes(`\`${DIAGRAM}\``), 'scope: D031 names the svg by its backticked path');
  const out = run([CHECK], dir).out;
  assert.ok(failed(out, 'MAP1', DIAGRAM), `MAP1 must fail on the svg inside the decisions folder that D031 names, with no map line\n${tail(out)}`);
});

// ---- Debt records: a non-code file that a debt record names needs a map line, and the debt's slug on a Debts line.

test('DB1. a .svg that a debt record names needs a map line: MAP1 fails and names the file', () => {
  const dir = scratch();
  addFile(dir, SVG_PATH, SVG);
  addFile(dir, `${debtsDirOf(dir)}/retry-backoff.md`, record('Retry backoff', [SVG_PATH]));
  assert.doesNotMatch(readIn(dir, MAP), /badge\.svg/, 'scope: the map page has no line for the .svg');
  const out = run([CHECK], dir).out;
  assert.ok(failed(out, 'MAP1', SVG_PATH), `MAP1 must fail on a .svg that the debt retry-backoff names\n${tail(out)}`);
});

test('DB2. the map line of a .svg a debt names needs a Debts line: the failure names the file and the slug', () => {
  const dir = scratch();
  addFile(dir, SVG_PATH, SVG);
  addFile(dir, `${debtsDirOf(dir)}/retry-backoff.md`, record('Retry backoff', [SVG_PATH]));
  addMapLines(dir, [mapLine(SVG_PATH, 'Holds the badge.')]);
  assert.deepEqual(subLineIds(dir, MAP, SVG_PATH, 'Debts'), [], 'scope: the map line has no Debts line');
  const out = run([CHECK], dir).out;
  assert.ok(failLines(out).some((l) => l.includes(SVG_PATH) && l.includes('retry-backoff')), `a check must fail naming the .svg and the slug retry-backoff\n${tail(out)}`);
});

test('DB3. control: a map line whose Debts line names the slug: no check fails', () => {
  const dir = scratch();
  addFile(dir, SVG_PATH, SVG);
  addFile(dir, `${debtsDirOf(dir)}/retry-backoff.md`, record('Retry backoff', [SVG_PATH]));
  addMapLines(dir, [mapLine(SVG_PATH, 'Holds the badge.'), '  - Debts: `retry-backoff`']);
  assert.deepEqual(subLineIds(dir, MAP, SVG_PATH, 'Debts'), ['retry-backoff'], 'scope: the Debts line names retry-backoff');
  const out = run([CHECK], dir).out;
  assert.deepEqual(failLines(out), [], `no check may fail when the slug is on the Debts line\n${tail(out)}`);
});

test('DB4. a Debts line that names notes (notes.md is no debt) or a slug with no debt file fails, and names both', () => {
  const dir = scratch();
  const debts = debtsDirOf(dir);
  addFile(dir, SVG_PATH, SVG);
  addFile(dir, `${debts}/retry-backoff.md`, record('Retry backoff', [SVG_PATH]));
  addFile(dir, `${debts}/notes.md`, '# Notes\n\nA note, and no debt.\n');
  addMapLines(dir, [mapLine(SVG_PATH, 'Holds the badge.'), '  - Debts: `retry-backoff`, `notes`, `missing-debt`']);
  assert.ok(existsSync(join(dir, debts, 'notes.md')), 'scope: the debts folder holds notes.md');
  const out = run([CHECK], dir).out;
  const fails = failLines(out).join('\n');
  assert.match(fails, /\bnotes\b/, `a Debts line naming notes must fail, since notes.md is no debt\n${tail(out)}`);
  assert.match(fails, /\bmissing-debt\b/, `a Debts line naming a slug with no debt file must fail\n${tail(out)}`);
});

test('DB5. notes.md and README.md in the debts folder that name a file are no debt: the file needs no map line', () => {
  const dir = scratch();
  const debts = debtsDirOf(dir);
  addFile(dir, SVG_PATH, SVG);
  addFile(dir, `${debts}/notes.md`, record('Notes', [SVG_PATH]));
  addFile(dir, `${debts}/README.md`, record('Readme', [SVG_PATH]));
  assert.doesNotMatch(readIn(dir, MAP), /badge\.svg/, 'scope: the map page has no line for the .svg');
  const out = run([CHECK], dir).out;
  assert.equal(verdictOf(out, 'MAP1'), 'PASS', `MAP1 must pass: notes.md and README.md are no debt record\n${tail(out)}`);
});

test('DB6. a Debts line whose slug names a debt that no longer names the file is fine: no check names the slug', () => {
  const dir = scratch();
  const debts = debtsDirOf(dir);
  addFile(dir, SVG_PATH, SVG);
  addFile(dir, `${debts}/retry-backoff.md`, '# Retry backoff\n\nThe debt no longer names a file.\n');
  addMapLines(dir, [mapLine(SVG_PATH, 'Holds the badge.'), '  - Debts: `retry-backoff`']);
  assert.ok(!readIn(dir, `${debts}/retry-backoff.md`).includes(SVG_PATH), 'scope: the debt no longer names the .svg');
  const out = run([CHECK], dir).out;
  assert.ok(failLines(out).every((l) => !l.includes('retry-backoff')), `a slug that exists is never a fail, though its debt no longer names the file\n${tail(out)}`);
});

test('DB7. map-fix --write adds the missing slug to the map line of the .svg', () => {
  const dir = scratch();
  addFile(dir, SVG_PATH, SVG);
  addFile(dir, `${debtsDirOf(dir)}/retry-backoff.md`, record('Retry backoff', [SVG_PATH]));
  addMapLines(dir, [mapLine(SVG_PATH, 'Holds the badge.')]);
  assert.deepEqual(subLineIds(dir, MAP, SVG_PATH, 'Debts'), [], 'scope: the map line has no Debts line');
  const r = run([MAPFIX, '--write'], dir);
  assert.deepEqual(subLineIds(dir, MAP, SVG_PATH, 'Debts'), ['retry-backoff'], `map-fix --write must add the slug retry-backoff to the .svg's map line\n${tail(r.out)}`);
});

test('DB8. map-show prints the Debts line of a .svg that a debt record names', () => {
  const dir = scratch();
  addFile(dir, SVG_PATH, SVG);
  addFile(dir, `${debtsDirOf(dir)}/retry-backoff.md`, record('Retry backoff', [SVG_PATH]));
  addMapLines(dir, [mapLine(SVG_PATH, 'Holds the badge.'), '  - Debts: `retry-backoff`']);
  assert.deepEqual(subLineIds(dir, MAP, SVG_PATH, 'Debts'), ['retry-backoff'], 'scope: the map page holds the Debts line');
  const r = run([SHOW, SVG_PATH], dir);
  assert.equal(r.status, 0, `map-show must find the .svg's map line\n${tail(r.out)}`);
  assert.ok(r.stdout.includes('Holds the badge.'), `map-show must print the map line of the .svg\n${tail(r.out)}`);
  assert.match(r.stdout, /Debts:.*\bretry-backoff\b/, `map-show must print the Debts line with retry-backoff\n${tail(r.out)}`);
});

test('DB9. control: a debt that names a code file adds no requirement: no check fails on the code file', () => {
  const dir = scratch();
  addFile(dir, `${debtsDirOf(dir)}/strings-labels.md`, record('Strings labels', ['src/strings.ts']));
  assert.deepEqual(subLineIds(dir, MAP, 'src/strings.ts', 'Debts'), [], 'scope: the map line of src/strings.ts has no Debts line');
  const out = run([CHECK], dir).out;
  assert.ok(failLines(out).every((l) => !l.includes('src/strings.ts')), `no check may require a Debts line of a code file\n${tail(out)}`);
});

test('DB10. empty state: no debts folder at all, no check fails, and no read of the missing folder is reported', () => {
  const dir = scratch();
  addFile(dir, SVG_PATH, SVG);
  assert.ok(!existsSync(join(dir, debtsDirOf(dir))), 'scope: the layout debts folder does not exist in the scratch repository');
  const out = run([CHECK], dir).out;
  assert.deepEqual(failLines(out), [], `no check may fail when the debts folder is absent\n${tail(out)}`);
  assert.ok(!/ENOENT/.test(out), `the missing debts folder must not be read as an error\n${tail(out)}`);
});

test('DB11. full size: two debt records name one .svg, and its map line must hold both slugs: a missing one fails by name', () => {
  const dir = scratch();
  const debts = debtsDirOf(dir);
  addFile(dir, SVG_PATH, SVG);
  addFile(dir, `${debts}/retry-backoff.md`, record('Retry backoff', [SVG_PATH]));
  addFile(dir, `${debts}/cache-warm.md`, record('Cache warm', [SVG_PATH]));
  addMapLines(dir, [mapLine(SVG_PATH, 'Holds the badge.'), '  - Debts: `retry-backoff`']);
  assert.deepEqual(subLineIds(dir, MAP, SVG_PATH, 'Debts'), ['retry-backoff'], 'scope: the Debts line holds retry-backoff only');
  const out = run([CHECK], dir).out;
  assert.ok(failLines(out).some((l) => l.includes(SVG_PATH) && l.includes('cache-warm')), `a check must fail naming the .svg and the missing slug cache-warm\n${tail(out)}`);
});

test('DB12. a tracked .svg inside the debts folder, and no debt, that a debt record names needs a map line: MAP1 fails and names it', () => {
  const dir = scratch();
  const debts = debtsDirOf(dir);
  const svg = `${debts}/diagram.svg`;
  addFile(dir, svg, SVG);
  addFile(dir, `${debts}/retry-backoff.md`, record('Retry backoff', [svg]));
  // The scope first: the svg has no map line, and the debt names it by its backticked path.
  assert.ok(!readIn(dir, MAP).includes(`\`${svg}\``), 'scope: the map page has no line for the svg');
  assert.ok(readIn(dir, `${debts}/retry-backoff.md`).includes(`\`${svg}\``), 'scope: retry-backoff names the svg by its backticked path');
  const out = run([CHECK], dir).out;
  assert.ok(failed(out, 'MAP1', svg), `MAP1 must fail on the svg inside the debts folder that retry-backoff names, with no map line\n${tail(out)}`);
});

test('DB13. a debt that names README.md or notes.md in the debts folder asks for no map line: MAP1 passes', () => {
  const dir = scratch();
  const debts = debtsDirOf(dir);
  addFile(dir, `${debts}/README.md`, '# Debts\n\nThe index of this folder.\n');
  addFile(dir, `${debts}/notes.md`, '# Notes\n\nA note, and no debt.\n');
  addFile(dir, `${debts}/retry-backoff.md`, record('Retry backoff', [`${debts}/README.md`, `${debts}/notes.md`]));
  // The scope first: retry-backoff names both files by their backticked paths, and the map page has no line for either.
  assert.ok(readIn(dir, `${debts}/retry-backoff.md`).includes(`\`${debts}/README.md\``), 'scope: retry-backoff names README.md by its backticked path');
  assert.ok(readIn(dir, `${debts}/retry-backoff.md`).includes(`\`${debts}/notes.md\``), 'scope: retry-backoff names notes.md by its backticked path');
  assert.doesNotMatch(readIn(dir, MAP), /README\.md|notes\.md/, 'scope: the map page has no line for either file');
  const out = run([CHECK], dir).out;
  assert.equal(verdictOf(out, 'MAP1'), 'PASS', `MAP1 must pass: README.md and notes.md in the debts folder are no record, so a debt that names them asks for no map line\n${tail(out)}`);
});

test('DB14. a debt that names a nested .md under the debts folder asks for a map line: MAP1 fails and names it', () => {
  const dir = scratch();
  const debts = debtsDirOf(dir);
  const nested = `${debts}/sub/x.md`;
  addFile(dir, nested, '# A nested note\n\nA file under a sub-folder, and no debt.\n');
  addFile(dir, `${debts}/retry-backoff.md`, record('Retry backoff', [nested]));
  // The scope first: the nested file has no map line, and retry-backoff names it by its backticked path.
  assert.doesNotMatch(readIn(dir, MAP), /sub\/x\.md/, 'scope: the map page has no line for the nested file');
  assert.ok(readIn(dir, `${debts}/retry-backoff.md`).includes(`\`${nested}\``), 'scope: retry-backoff names the nested file by its backticked path');
  const out = run([CHECK], dir).out;
  assert.ok(failed(out, 'MAP1', nested), `MAP1 must fail on the nested file that retry-backoff names: only a file directly in the debts folder is a debt\n${tail(out)}`);
});

// The map format version, and the one upgrade command. Plan: q_max `specs/map-skill-portable.md`, step 3.
//
// A host repository keeps its map between runs of the skill, and the skill changes. A run must bring the old map up in place,
// and must never rebuild it from nothing. `map.config.json` holds `formatVersion`, a whole number. A missing key means version 1.
// The skill holds `MAP_FORMAT_VERSION` in `scripts/lib/map-config.mjs`, and a list of upgrade steps, one for each version.
//
// THE REAL PAST CHANGE (step 1 of the list: version 1 to version 2). Source: the q_max history of `docs/map/`.
//   Version 1 map lines carried line references: `(`:153-186`)`, `stage1-budget.test.mjs:303-322`, `(`sliceCorpus`, `:492`)`.
//   Commit 2362597a6 wrote them. Commits b96ed7fc9 and 6d9a8f0b6 (both 2026-10-10) took them out, and gave the reason:
//   "a line number goes stale with the next edit". Version 2 map lines carry none.
//   The step is the mechanical part of those two commits, and nothing more:
//     - a parenthesis that holds only a line reference goes, with the space before it:  `x (`:26-36`). y` becomes `x. y`
//     - `file.ext:N` or `file.ext:N-M` in backticks loses its `:N` part:               `notes.ts:303-322` becomes `notes.ts`
//     - `, `:N`` goes from inside a parenthesis that has a name:                        `(`notes`, `:492`)` becomes `(`notes`)`
//   Those two commits also rewrote some references by hand (`:3502` became a route, `:280` became "with `RateBand`").
//   No step can reproduce that, so the fixtures hold no such form. A colon token that is no line reference must survive:
//   `localhost:3000` is in both fixtures.
//
// FIXTURES. `tests/fixture/` is the version 2 repository (`"formatVersion": 2`). `tests/fixture-v1/` holds the three files that
// differ in version 1: the config with no `formatVersion`, and the area page and the trace page with line references.
// After the upgrade, each of those files must equal the file of `tests/fixture/`. The test text is the whole expected output.
//
// The scanner rule: the step reads map text, not code. The text of a map line holds a lone quote (`note's`), and `//` and `#`
// inside backticks. A line has one line, so there is no multi-line case.
//
//   F0. `MAP_FORMAT_VERSION` is the whole number 2: one real step, from 1 to 2.
//   1a. `map-upgrade.mjs` on the version 1 repository: the files equal the version 2 files, the config is the version 2 config,
//       no other file changes, and the check command then passes.
//   1b. The same with CRLF line ends: the upgrade keeps each line end.
//   1c. The same through a junction to the skill folder, the way `~/.claude/skills/<name>` reaches it.
//   2a. A second run changes no file. The first run did change files.
//   2b. A run on a map of the current version changes no file, also where a sentence holds a line reference.
//   3a, 3b, 3c. A config with a newer `formatVersion` than the skill: the check command, the picture command and the upgrade
//       command each refuse, say to update the skill, exit non-zero, and write nothing.
//   4a, 4b. An older version (a missing key, and 1): the check command fails, names the upgrade command, and writes nothing.
//   5.  A `formatVersion` that is no whole number is an error that says so.
//
// A run writes nothing when every file in the repository has the same size, the same mtime and the same bytes after it, and no
// file was added or removed. `.git` is left out: git itself may refresh its index.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { FIXTURE, HERE, SKILL, expected, junction, needFile, run, scratchRepo, tmpFolder, verdicts } from './helpers.mjs';

const CHECK = join(SKILL, 'scripts', 'map-check.mjs');
const PICTURE = join(SKILL, 'scripts', 'map-picture.mjs');
const UPGRADE = join(SKILL, 'scripts', 'map-upgrade.mjs');
const CONFIG = join(SKILL, 'scripts', 'lib', 'map-config.mjs');
const V1 = join(HERE, 'fixture-v1');

// The three files that differ between version 1 and version 2.
const MAP_FILES = ['docs/map/core.md', 'docs/map/traces/home.md'];
const CHANGED = ['map.config.json', ...MAP_FILES];

// Far above any real version of the skill, so a case never goes stale when the skill gains a step.
const FUTURE = 99;

const lf = (s) => s.replace(/\r\n/g, '\n');
const readLf = (file) => lf(readFileSync(file, 'utf8'));
const eolOf = (s, eol) => lf(s).replace(/\n/g, eol);

/** One string for each file under `dir` (but `.git`), by relative path: size, mtime and a hash of the bytes. */
const snapshot = (dir) => {
  const out = new Map();
  const walk = (rel) => {
    for (const e of readdirSync(join(dir, rel), { withFileTypes: true })) {
      if (e.name === '.git') continue;
      const r = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) walk(r);
      else {
        const p = join(dir, r), s = statSync(p);
        out.set(r, `${s.size}|${s.mtimeMs}|${createHash('sha1').update(readFileSync(p)).digest('hex')}`);
      }
    }
  };
  walk('');
  return out;
};
const same = (a, b) => JSON.stringify([...a].sort()) === JSON.stringify([...b].sort());

/** A scratch repository in the state of a version 1 host: the config has no `formatVersion`, and the map holds line references. */
const v1Repo = ({ eol = '\n', commit = false } = {}) => {
  const dir = scratchRepo({ commit });
  for (const f of CHANGED) writeFileSync(join(dir, f), eolOf(readFileSync(join(V1, f), 'utf8'), eol));
  // The scope first: the repository must be a version 1 host, or a verdict below says nothing about an upgrade.
  assert.ok(!('formatVersion' in JSON.parse(readFileSync(join(dir, 'map.config.json'), 'utf8'))), 'the version 1 config must have no formatVersion');
  assert.match(readFileSync(join(dir, 'docs/map/core.md'), 'utf8'), /\(`:26-36`\)/, 'the version 1 map must hold line references');
  return dir;
};

/** Sets `formatVersion` in the config of `dir` to `v`, and keeps every other key. */
const withVersion = (dir, v) => {
  const p = join(dir, 'map.config.json');
  writeFileSync(p, `${JSON.stringify({ ...JSON.parse(readFileSync(p, 'utf8')), formatVersion: v }, null, 2)}\n`);
  return dir;
};

const out1500 = (r) => r.out.slice(0, 1500);

/** The map files of `dir` equal the files of the version 2 fixture, line ends set by `eol`. */
const assertVersion2Files = (dir, eol) => {
  for (const f of MAP_FILES)
    assert.equal(readFileSync(join(dir, f), 'utf8'), eolOf(readFileSync(join(FIXTURE, f), 'utf8'), eol), `${f} must equal the version 2 file, with each sentence kept`);
  assert.deepEqual(
    JSON.parse(readFileSync(join(dir, 'map.config.json'), 'utf8')),
    JSON.parse(readFileSync(join(FIXTURE, 'map.config.json'), 'utf8')),
    'the config must be the old config plus "formatVersion": 2'
  );
};

test('F0. map-config.mjs exports MAP_FORMAT_VERSION as the whole number 2', () => {
  needFile('scripts/lib/map-config.mjs');
  const script = `const m = await import(${JSON.stringify(pathToFileURL(CONFIG).href)});
console.log(JSON.stringify(m.MAP_FORMAT_VERSION ?? null));`;
  const r = run(['--input-type=module', '-'], scratchRepo(), script);
  assert.equal(r.status, 0, `the module must load\n${out1500(r)}`);
  assert.equal(JSON.parse(r.stdout.trim().split('\n').pop()), 2, 'MAP_FORMAT_VERSION must be 2: one real step, from 1 to 2, and the fixture is at 2');
});

test('1a. the upgrade command turns the version 1 map into the version 2 map, keeps each sentence, sets formatVersion, and the check then passes', () => {
  needFile('scripts/map-upgrade.mjs');
  const dir = v1Repo();
  const before = snapshot(dir);
  const r = run([UPGRADE], dir);
  assert.equal(r.signal, null, `the command died with a signal: ${r.signal}`);
  assert.equal(r.status, 0, `the upgrade must exit 0\n${out1500(r)}`);
  assertVersion2Files(dir, '\n');
  // Only the config and the two map pages change. No other file is written, added or removed.
  const after = snapshot(dir);
  assert.deepEqual([...after.keys()].sort(), [...before.keys()].sort(), 'the upgrade must add and remove no file');
  for (const [f, sig] of after) if (!CHANGED.includes(f)) assert.equal(sig, before.get(f), `the upgrade must not write ${f}`);
  const c = run([CHECK], dir);
  assert.equal(verdicts(c.out), expected(), `the check must print one PASS line for each of MAP1 to MAP8\n${out1500(c)}`);
  assert.equal(c.status, 0, `the check must exit 0 on the upgraded map\n${out1500(c)}`);
});

test('1b. with CRLF line ends the upgrade keeps each line end', () => {
  needFile('scripts/map-upgrade.mjs');
  const dir = v1Repo({ eol: '\r\n' });
  const r = run([UPGRADE], dir);
  assert.equal(r.status, 0, `the upgrade must exit 0\n${out1500(r)}`);
  assertVersion2Files(dir, '\r\n');
});

test('1c. run through a junction to the skill folder, the upgrade command upgrades the map', () => {
  needFile('scripts/map-upgrade.mjs');
  const script = join(junction(SKILL), 'scripts', 'map-upgrade.mjs');
  const dir = v1Repo();
  const r = run([script], dir);
  assert.equal(r.status, 0, `the upgrade must exit 0 through a junction\n${out1500(r)}`);
  assertVersion2Files(dir, '\n');
});

test('2a. a second run of the upgrade changes no file', () => {
  needFile('scripts/map-upgrade.mjs');
  const dir = v1Repo();
  const before = snapshot(dir);
  const first = run([UPGRADE], dir);
  assert.equal(first.status, 0, `the first run must exit 0\n${out1500(first)}`);
  const once = snapshot(dir);
  // The scope first: the first run changed the map, or "no change" holds for a command that does nothing.
  assert.ok(!same(before, once), 'the first run must change the version 1 map');
  const second = run([UPGRADE], dir);
  assert.equal(second.status, 0, `the second run must exit 0\n${out1500(second)}`);
  assert.ok(same(once, snapshot(dir)), 'the second run must write no file, add none and remove none');
});

test('2b. a run on a map of the current version changes no file, also where a sentence holds a line reference', () => {
  needFile('scripts/map-upgrade.mjs');
  const dir = scratchRepo();
  const p = join(dir, 'docs/map/core.md');
  writeFileSync(p, readFileSync(p, 'utf8').replace('from the saved notes.', 'from the saved notes (`:26-36`).'));
  // The scope first: the version 2 map holds a line reference now, so a step that always strips would change a file.
  assert.match(readFileSync(p, 'utf8'), /\(`:26-36`\)/, 'the map must hold a line reference');
  const before = snapshot(dir);
  const r = run([UPGRADE], dir);
  assert.equal(r.status, 0, `the run must exit 0\n${out1500(r)}`);
  assert.ok(same(before, snapshot(dir)), 'a step must run only for a map that is older than its target version');
});

// A refusal: exit non-zero, a message that says to update the skill and is no "unknown key" error, no PASS line, and no write.
const assertRefusesNewer = (r, dir, before) => {
  assert.equal(r.signal, null, `the command died with a signal: ${r.signal}`);
  assert.notEqual(r.status, 0, `the command must exit non-zero on a newer map\n${out1500(r)}`);
  assert.doesNotMatch(r.out, /unknown key/i, `the refusal must come from the version check, never from the key check\n${out1500(r)}`);
  assert.match(r.out, /\bupdate\b[^\n]*\bskill\b/i, `the message must say to update the skill\n${out1500(r)}`);
  assert.doesNotMatch(r.out, /\[PASS\]/, `no check may run on a newer map\n${out1500(r)}`);
  assert.ok(same(before, snapshot(dir)), 'a refusal must write nothing');
};

test('3a. a config with a newer formatVersion than the skill: the check command refuses, says to update the skill, and writes nothing', () => {
  needFile('scripts/map-check.mjs');
  const dir = withVersion(scratchRepo(), FUTURE);
  const before = snapshot(dir);
  assertRefusesNewer(run([CHECK], dir), dir, before);
});

test('3b. a config with a newer formatVersion than the skill: the picture command refuses, says to update the skill, and writes no page', () => {
  needFile('scripts/map-picture.mjs');
  const dir = withVersion(scratchRepo({ commit: true }), FUTURE);
  const before = snapshot(dir);
  const page = join(tmpFolder('pemap-page-'), 'map.html');
  const r = run([PICTURE, page], dir);
  assertRefusesNewer(r, dir, before);
  assert.ok(!existsSync(page), 'the picture command must write no page for a newer map');
});

test('3c. a config with a newer formatVersion than the skill: the upgrade command refuses, says to update the skill, and never writes a downgrade', () => {
  needFile('scripts/map-upgrade.mjs');
  const dir = withVersion(v1Repo(), FUTURE);
  const before = snapshot(dir);
  assertRefusesNewer(run([UPGRADE], dir), dir, before);
});

// An older map: the check fails, and the message names the upgrade command.
const assertFailsOlder = (r, dir, before) => {
  assert.equal(r.signal, null, `the command died with a signal: ${r.signal}`);
  assert.notEqual(r.status, 0, `the check must exit non-zero on an older map\n${out1500(r)}`);
  assert.doesNotMatch(r.out, /unknown key/i, `the failure must come from the version check, never from the key check\n${out1500(r)}`);
  assert.match(r.out, /^\[FAIL\]/m, `the check must print a FAIL line\n${out1500(r)}`);
  assert.match(r.out, /map-upgrade\.mjs/, `the message must name the upgrade command\n${out1500(r)}`);
  assert.doesNotMatch(r.out, /\[PASS\]/, `no check may pass before the upgrade\n${out1500(r)}`);
  assert.ok(same(before, snapshot(dir)), 'the check must never rewrite a file');
};

test('4a. a config with no formatVersion is version 1: the check command fails, names the upgrade command, and writes nothing', () => {
  needFile('scripts/map-check.mjs');
  const dir = v1Repo();
  const before = snapshot(dir);
  assertFailsOlder(run([CHECK], dir), dir, before);
});

test('4b. a config with "formatVersion": 1 gives the same result as a missing key', () => {
  needFile('scripts/map-check.mjs');
  const dir = withVersion(v1Repo(), 1);
  const before = snapshot(dir);
  assertFailsOlder(run([CHECK], dir), dir, before);
});

test('5. a formatVersion that is no whole number is an error that says so, and nothing is written', () => {
  needFile('scripts/map-check.mjs');
  for (const bad of [1.5, '2', true]) {
    const dir = withVersion(scratchRepo(), bad);
    const before = snapshot(dir);
    const r = run([CHECK], dir);
    assert.notEqual(r.status, 0, `formatVersion ${JSON.stringify(bad)} must make the check exit non-zero\n${out1500(r)}`);
    assert.match(r.out, /formatVersion/, `the message must name formatVersion (${JSON.stringify(bad)})\n${out1500(r)}`);
    assert.match(r.out, /whole number/i, `the message must say that formatVersion is a whole number (${JSON.stringify(bad)})\n${out1500(r)}`);
    assert.doesNotMatch(r.out, /\[PASS\]/, `no check may pass with formatVersion ${JSON.stringify(bad)}\n${out1500(r)}`);
    assert.ok(same(before, snapshot(dir)), `the check must write nothing (${JSON.stringify(bad)})`);
  }
});

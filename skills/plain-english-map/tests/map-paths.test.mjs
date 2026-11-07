// The scope key `mapPaths` of map.config.json (step 7 of c146). It is a list of path prefixes that MAP1 and MAP7 cover.
// MAP2 reads every tracked code file, unscoped. Its default is the whole repository, and a repository with no such key is checked as before.
//
//   P1. With `"mapPaths": ["src/"]`, a tracked code file outside src/ and with no map line is no MAP1 failure. Every check passes.
//   P2. With the same key, a tracked code file inside src/ and with no map line still fails MAP1, and the output names it.
//   P3. MAP2 is unscoped: with the same key, a tracked file outside src/ that has a map line passes MAP2. Every check passes.
//   P4. A `mapPaths` that is not a list is refused, the message names the key, and it is no "unknown key" error.
//   P5. With `"mapPaths": ["src/"]`, a tracked file outside src/ that holds an "In plain words" note is no MAP7 failure. Every check passes.
//   P6. MAP7 reads no file outside src/: with the same key, its body returns true, and the one file it reads is inside src/.
//   P7. The scope covers MAP7 for a file inside src/: a note there still fails MAP7, and the output names it.
//   P8. With no `mapPaths`, a note in a file outside src/ still fails MAP7, and the output names it.
//   P9. With `"mapPaths": ["src/", "lib/"]`, a note in lib/x.ts fails MAP7 and a tracked lib/y.ts with no map line fails MAP1: every prefix of the list is in scope.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { SKILL, expected, gitIn, needFile, run, scratchRepo, verdicts } from './helpers.mjs';
import { loadMapConfig } from '../scripts/lib/map-config.mjs';
import { mapChecks, plainWordsNotes, trackedCodeFiles } from '../scripts/map-check.mjs';

const CHECK = join(SKILL, 'scripts', 'map-check.mjs');
const CORE = 'docs/map/core.md';
const out1500 = (r) => r.out.slice(0, 1500);

/** Adds `extra` keys to the config of `dir`, and keeps every other key. */
const withConfig = (dir, extra) => {
  const p = join(dir, 'map.config.json');
  writeFileSync(p, `${JSON.stringify({ ...JSON.parse(readFileSync(p, 'utf8')), ...extra }, null, 2)}\n`);
  return dir;
};

/** Adds a tracked code file `rel` to `dir`. It holds `body`, or a plain export. A case adds a map line with `addMapLine` when it needs one. */
const addTracked = (dir, rel, body = 'export const extra = 1;\n') => {
  mkdirSync(dirname(join(dir, rel)), { recursive: true });
  writeFileSync(join(dir, rel), body);
  gitIn(dir, 'add', '-N', rel);
};

/** Appends a map line for `rel` to `docs/map/core.md` of `dir`, with the description `what`. */
const addMapLine = (dir, rel, what) => {
  const p = join(dir, CORE);
  writeFileSync(p, `${readFileSync(p, 'utf8').replace(/\n*$/, '\n')}- \`${rel}\` — ${what}\n`);
};

/** A code file's note, as MAP7 reads it: a comment whose text opens with the label. */
const NOTE = '// In plain words: this file holds a helper.\n';

test('P1. with mapPaths ["src/"], a tracked code file outside src/ with no map line is no MAP1 failure, and every check passes', () => {
  needFile('scripts/map-check.mjs');
  const dir = withConfig(scratchRepo(), { mapPaths: ['src/'] });
  addTracked(dir, 'tools/extra.ts');
  // The scope first: the file is tracked, has a code extension and no map line, so the default scope would fail MAP1.
  assert.ok(!readFileSync(join(dir, CORE), 'utf8').includes('tools/extra.ts'), 'no map line may name tools/extra.ts');
  const r = run([CHECK], dir);
  assert.equal(verdicts(r.out), expected(), `a file outside the scope must not fail MAP1\n${out1500(r)}`);
  assert.equal(r.status, 0, `the command must exit 0\n${out1500(r)}`);
});

test('P2. with mapPaths ["src/"], a tracked code file inside src/ with no map line still fails MAP1, and the output names it', () => {
  needFile('scripts/map-check.mjs');
  const dir = withConfig(scratchRepo(), { mapPaths: ['src/'] });
  addTracked(dir, 'src/extra.ts');
  const r = run([CHECK], dir);
  assert.equal(verdicts(r.out), expected({ MAP1: 'FAIL' }), `only MAP1 must fail\n${out1500(r)}`);
  assert.ok(r.out.includes('src/extra.ts'), `the output must name src/extra.ts\n${out1500(r)}`);
});

test('P3. MAP2 is unscoped: with mapPaths ["src/"], a tracked file outside src/ that has a map line passes MAP2, and every check passes', () => {
  needFile('scripts/map-check.mjs');
  const dir = withConfig(scratchRepo(), { mapPaths: ['src/'] });
  addTracked(dir, 'tools/extra.ts');
  addMapLine(dir, 'tools/extra.ts', 'Holds a helper.');
  // The scope first: the config names src/ alone, the file is tracked, and its map line names it, so MAP2 must read it outside the scope.
  assert.deepEqual(loadMapConfig(join(dir, 'map.config.json'), dir).mapPaths, ['src/'], 'the config must scope the check to src/');
  assert.ok(gitIn(dir, 'ls-files').split('\n').includes('tools/extra.ts'), 'the file must be tracked');
  assert.match(readFileSync(join(dir, CORE), 'utf8'), /`tools\/extra\.ts`/, 'the map line must name tools/extra.ts');
  const r = run([CHECK], dir);
  assert.equal(verdicts(r.out), expected(), `a map line for a file outside the scope must pass MAP2\n${out1500(r)}`);
  assert.equal(r.status, 0, `the command must exit 0\n${out1500(r)}`);
});

test('P4. a mapPaths that is not a list is refused: the message names mapPaths and is no "unknown key" error', () => {
  needFile('scripts/map-check.mjs');
  const dir = withConfig(scratchRepo(), { mapPaths: 'src/' });
  const r = run([CHECK], dir);
  assert.notEqual(r.status, 0, `a mapPaths that is not a list must exit non-zero\n${out1500(r)}`);
  assert.doesNotMatch(r.out, /unknown key/i, `mapPaths is a known key, so the refusal must say why it is refused\n${out1500(r)}`);
  assert.match(r.out, /mapPaths/, `the message must name mapPaths\n${out1500(r)}`);
});

test('P5. with mapPaths ["src/"], a tracked file outside src/ that holds an "In plain words" note is no MAP7 failure, and every check passes', () => {
  needFile('scripts/map-check.mjs');
  const dir = withConfig(scratchRepo(), { mapPaths: ['src/'] });
  addTracked(dir, 'tools/x.ts', `${NOTE}export const x = 1;\n`);
  // The scope first: the text must hold a note that MAP7 reads, or a pass below says nothing about the scope.
  assert.deepEqual(plainWordsNotes({ 'tools/x.ts': `${NOTE}export const x = 1;\n` }), ['tools/x.ts:1'], 'the text must hold a note that MAP7 reads');
  const r = run([CHECK], dir);
  assert.equal(verdicts(r.out), expected(), `a file outside the scope must not fail MAP7\n${out1500(r)}`);
  assert.equal(r.status, 0, `the command must exit 0\n${out1500(r)}`);
});

test('P6. MAP7 reads no file outside mapPaths: with ["src/"], it returns true, and the one file it reads is inside src/', () => {
  needFile('scripts/map-check.mjs');
  const dir = withConfig(scratchRepo(), { mapPaths: ['src/'] });
  // `loadMapConfig` validates against the scratch repository, so the config it returns is the one `mapChecks` takes as valid.
  const cfg = loadMapConfig(join(dir, 'map.config.json'), dir);
  const bodies = { 'src/x.ts': 'export const x = 1;\n', 'tools/x.ts': `${NOTE}export const x = 1;\n` };
  const files = () => Object.keys(bodies);
  // The scope first: the config names src/ alone, and both files are code files of the list.
  assert.deepEqual(cfg.mapPaths, ['src/'], 'the config must scope the check to src/');
  assert.deepEqual(trackedCodeFiles(files(), cfg), ['src/x.ts', 'tools/x.ts'], 'trackedCodeFiles must list both files: MAP2 reads it unscoped, and MAP7 applies mapPaths itself, through inMapPaths');
  const reads = [];
  const read = (f) => {
    reads.push(f);
    if (!f.startsWith('src/')) throw new Error(`MAP7 read ${f}, which is outside mapPaths`);
    return bodies[f];
  };
  let result;
  let thrown;
  try {
    result = mapChecks({ cfg, root: dir, read, files }).MAP7();
  } catch (e) {
    thrown = e;
  }
  assert.equal(thrown, undefined, `MAP7 must not throw\n${thrown?.message}`);
  assert.equal(result, true, 'MAP7 must return true when no file inside src/ holds a note');
  // The inside file must still be read, or MAP7 checks nothing and the pass above proves no scope.
  assert.ok(reads.includes('src/x.ts'), `MAP7 must still read the file inside src/\nreads: ${reads.join(', ')}`);
});

test('P7. the scope covers MAP7 for a file inside src/: a note in src/x.ts still fails MAP7, and the output names it', () => {
  needFile('scripts/map-check.mjs');
  const dir = withConfig(scratchRepo(), { mapPaths: ['src/'] });
  addTracked(dir, 'src/x.ts', `${NOTE}export const x = 1;\n`);
  addMapLine(dir, 'src/x.ts', 'Holds a helper.');
  const r = run([CHECK], dir);
  assert.equal(verdicts(r.out), expected({ MAP7: 'FAIL' }), `only MAP7 must fail\n${out1500(r)}`);
  assert.ok(r.out.includes('src/x.ts'), `the output must name src/x.ts\n${out1500(r)}`);
});

test('P8. with no mapPaths, a note in a file outside src/ still fails MAP7, and the output names it', () => {
  needFile('scripts/map-check.mjs');
  const dir = scratchRepo();
  addTracked(dir, 'tools/x.ts', `${NOTE}export const x = 1;\n`);
  addMapLine(dir, 'tools/x.ts', 'Holds a helper.');
  const r = run([CHECK], dir);
  assert.equal(verdicts(r.out), expected({ MAP7: 'FAIL' }), `only MAP7 must fail\n${out1500(r)}`);
  assert.ok(r.out.includes('tools/x.ts'), `the output must name tools/x.ts\n${out1500(r)}`);
});

test('P9. with mapPaths ["src/", "lib/"], a note in lib/x.ts fails MAP7 and a tracked lib/y.ts with no map line fails MAP1: every prefix of the list is in scope', () => {
  needFile('scripts/map-check.mjs');
  const dir = withConfig(scratchRepo(), { mapPaths: ['src/', 'lib/'] });
  addTracked(dir, 'lib/x.ts', `${NOTE}export const x = 1;\n`);
  addMapLine(dir, 'lib/x.ts', 'Holds a helper.');
  addTracked(dir, 'lib/y.ts');
  // The scope first: the list holds two prefixes, the note sits under the second, and no map line names lib/y.ts.
  assert.deepEqual(loadMapConfig(join(dir, 'map.config.json'), dir).mapPaths, ['src/', 'lib/'], 'the config must scope the check to src/ and lib/');
  assert.deepEqual(plainWordsNotes({ 'lib/x.ts': `${NOTE}export const x = 1;\n` }), ['lib/x.ts:1'], 'the text must hold a note that MAP7 reads');
  assert.doesNotMatch(readFileSync(join(dir, CORE), 'utf8'), /`lib\/y\.ts`/, 'no map line may name lib/y.ts');
  const r = run([CHECK], dir);
  assert.equal(verdicts(r.out), expected({ MAP1: 'FAIL', MAP7: 'FAIL' }), `only MAP1 and MAP7 must fail\n${out1500(r)}`);
  assert.ok(r.out.includes('lib/x.ts'), `the output must name lib/x.ts, the note\n${out1500(r)}`);
  assert.ok(r.out.includes('lib/y.ts'), `the output must name lib/y.ts, the missing map line\n${out1500(r)}`);
});

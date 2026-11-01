// The scope key `mapPaths` of map.config.json (step 7 of c146). It is a list of path prefixes that MAP1 and MAP2 cover.
// Its default is the whole repository, and a repository with no such key is checked as before.
//
//   P1. With `"mapPaths": ["src/"]`, a tracked code file outside src/ and with no map line is no MAP1 failure. Every check passes.
//   P2. With the same key, a tracked code file inside src/ and with no map line still fails MAP1, and the output names it.
//   P3. The scope covers MAP2 too: a map line that names a missing file inside src/ still fails MAP2.
//   P4. A `mapPaths` that is not a list is refused, the message names the key, and it is no "unknown key" error.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { SKILL, expected, gitIn, needFile, run, scratchRepo, verdicts } from './helpers.mjs';

const CHECK = join(SKILL, 'scripts', 'map-check.mjs');
const CORE = 'docs/map/core.md';
const out1500 = (r) => r.out.slice(0, 1500);

/** Adds `extra` keys to the config of `dir`, and keeps every other key. */
const withConfig = (dir, extra) => {
  const p = join(dir, 'map.config.json');
  writeFileSync(p, `${JSON.stringify({ ...JSON.parse(readFileSync(p, 'utf8')), ...extra }, null, 2)}\n`);
  return dir;
};

/** Adds a tracked file `rel` with no map line, to `dir`. */
const addUnmapped = (dir, rel) => {
  mkdirSync(dirname(join(dir, rel)), { recursive: true });
  writeFileSync(join(dir, rel), 'export const extra = 1;\n');
  gitIn(dir, 'add', '-N', rel);
};

test('P1. with mapPaths ["src/"], a tracked code file outside src/ with no map line is no MAP1 failure, and every check passes', () => {
  needFile('scripts/map-check.mjs');
  const dir = withConfig(scratchRepo(), { mapPaths: ['src/'] });
  addUnmapped(dir, 'tools/extra.ts');
  // The scope first: the file is tracked, has a code extension and no map line, so the default scope would fail MAP1.
  assert.ok(!readFileSync(join(dir, CORE), 'utf8').includes('tools/extra.ts'), 'no map line may name tools/extra.ts');
  const r = run([CHECK], dir);
  assert.equal(verdicts(r.out), expected(), `a file outside the scope must not fail MAP1\n${out1500(r)}`);
  assert.equal(r.status, 0, `the command must exit 0\n${out1500(r)}`);
});

test('P2. with mapPaths ["src/"], a tracked code file inside src/ with no map line still fails MAP1, and the output names it', () => {
  needFile('scripts/map-check.mjs');
  const dir = withConfig(scratchRepo(), { mapPaths: ['src/'] });
  addUnmapped(dir, 'src/extra.ts');
  const r = run([CHECK], dir);
  assert.equal(verdicts(r.out), expected({ MAP1: 'FAIL' }), `only MAP1 must fail\n${out1500(r)}`);
  assert.ok(r.out.includes('src/extra.ts'), `the output must name src/extra.ts\n${out1500(r)}`);
});

test('P3. the scope covers MAP2 too: a map line that names a missing file inside src/ still fails MAP2', () => {
  needFile('scripts/map-check.mjs');
  const dir = withConfig(scratchRepo(), { mapPaths: ['src/'] });
  const p = join(dir, CORE);
  writeFileSync(p, `${readFileSync(p, 'utf8').replace(/\n*$/, '\n')}- \`src/gone.ts\` — Holds nothing.\n`);
  const r = run([CHECK], dir);
  assert.equal(verdicts(r.out), expected({ MAP2: 'FAIL' }), `only MAP2 must fail\n${out1500(r)}`);
  assert.ok(r.out.includes('src/gone.ts'), `the output must name src/gone.ts\n${out1500(r)}`);
});

test('P4. a mapPaths that is not a list is refused: the message names mapPaths and is no "unknown key" error', () => {
  needFile('scripts/map-check.mjs');
  const dir = withConfig(scratchRepo(), { mapPaths: 'src/' });
  const r = run([CHECK], dir);
  assert.notEqual(r.status, 0, `a mapPaths that is not a list must exit non-zero\n${out1500(r)}`);
  assert.doesNotMatch(r.out, /unknown key/i, `mapPaths is a known key, so the refusal must say why it is refused\n${out1500(r)}`);
  assert.match(r.out, /mapPaths/, `the message must name mapPaths\n${out1500(r)}`);
});

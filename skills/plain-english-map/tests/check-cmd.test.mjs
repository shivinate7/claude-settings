// The check command of the skill, run on a small fixture repository (`tests/fixture/`).
//
// `node <skill>/scripts/map-check.mjs`, run from the root of a repository that has `map.config.json`, runs the 9 MAP checks.
// It prints one line for each: `[PASS] MAPn`, `[FAIL] MAPn <message>` or `[SKIP] MAPn <reason>`. It exits non-zero on a FAIL.
// Each case runs in a fresh copy of the fixture in this run's temp folder, so the checkout never changes. The child env has no `NODE_PATH`.
// So the command must find `typescript` by itself, from claude-settings' own `node_modules`.
//
// The fixture config names a screen keys file, so the validator parses it with `typescript` in every run.
// The fixture has no `modelSeam` and no `requireAllKeys`. Each check runs, and each one passes.
//
//   1a. A clean fixture: one PASS line for each of MAP1 to MAP9, and exit 0.
//   1b. One map line removed: MAP1 FAILS and names the file, the other 8 stay PASS, and the exit code is not 0.
//   1c, 1d. The same two runs through a junction to the skill folder. That is how `~/.claude/skills/<name>` reaches the skill.
//       A command that compares `import.meta.url` with the typed `process.argv[1]` prints nothing there, and exits 0.
//   A.  An import of the module from a stdin script (`node -`) never crashes, and it runs no command.
//   B1. The ids that the command prints equal the keys of `mapChecks`: one list.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { SKILL, dropMapLine, expected, junction, needFile, run, scratchRepo, verdicts } from './helpers.mjs';

const CLI = join(SKILL, 'scripts', 'map-check.mjs');
const REL = 'scripts/map-check.mjs';

test('1a. on a clean fixture the command prints one PASS line for each of MAP1 to MAP9 and exits 0', () => {
  needFile(REL);
  const r = run([CLI], scratchRepo());
  assert.equal(r.signal, null, `the command died with a signal: ${r.signal}`);
  assert.equal(verdicts(r.out), expected(), `each check must print one PASS line\n${r.out.slice(0, 1500)}`);
  assert.equal(r.status, 0, `the command must exit 0 on a clean fixture\n${r.out.slice(0, 1500)}`);
});

test('1b. with one map line removed the command exits non-zero, MAP1 fails, and the output names the file', () => {
  needFile(REL);
  const dir = scratchRepo();
  dropMapLine(dir, 'src/notes.ts');
  const r = run([CLI], dir);
  assert.equal(verdicts(r.out), expected({ MAP1: 'FAIL' }), `only MAP1 must fail\n${r.out.slice(0, 1500)}`);
  assert.ok(r.out.includes('src/notes.ts'), `the output must name src/notes.ts\n${r.out.slice(0, 1500)}`);
  assert.notEqual(r.status, 0, 'the command must exit non-zero when a check fails');
});

test('1c. run through a junction to the skill folder, the command prints 9 PASS lines and exits 0', () => {
  needFile(REL);
  const script = join(junction(SKILL), 'scripts', 'map-check.mjs');
  const r = run([script], scratchRepo());
  assert.equal(verdicts(r.out), expected(), `each check must print one PASS line\n${r.out.slice(0, 1500)}`);
  assert.equal(r.status, 0, `the command must exit 0 on a clean fixture\n${r.out.slice(0, 1500)}`);
});

test('1d. run through the junction with one map line removed, the command exits non-zero, MAP1 fails, and the output names the file', () => {
  needFile(REL);
  const script = join(junction(SKILL), 'scripts', 'map-check.mjs');
  const dir = scratchRepo();
  dropMapLine(dir, 'src/notes.ts');
  const r = run([script], dir);
  assert.equal(verdicts(r.out), expected({ MAP1: 'FAIL' }), `only MAP1 must fail\n${r.out.slice(0, 1500)}`);
  assert.ok(r.out.includes('src/notes.ts'), `the output must name src/notes.ts\n${r.out.slice(0, 1500)}`);
  assert.notEqual(r.status, 0, 'the command must exit non-zero when a check fails, also through a junction');
});

// A script on stdin runs as `node -`. There `process.argv[1]` is `-`, and it names no file.
test('A. importing the module from a stdin script exits 0, runs no command, and prints no MAP line', () => {
  needFile(REL);
  const dir = scratchRepo();
  const script = `import(${JSON.stringify(pathToFileURL(CLI).href)}).then((m) => console.log('imported ' + typeof m.runMapChecks));`;
  const r = run(['-'], dir, script);
  assert.equal(r.signal, null, `the stdin script died with a signal: ${r.signal}`);
  // The scope first: the import must have finished, or "no MAP line" holds for the wrong reason.
  assert.equal(r.status, 0, `an import must never crash. Exit ${r.status}\n${r.out.slice(0, 1500)}`);
  assert.equal(r.stdout.trim(), 'imported function', `the script must print only its own line\n${r.out.slice(0, 1500)}`);
  assert.doesNotMatch(r.out, /\[(PASS|FAIL|SKIP)\]|\bMAP\d+\b/, `an import must not run the command\n${r.out.slice(0, 1500)}`);
});

// `Object.keys(mapChecks(...))` builds closures and runs none, so a stub config is enough to read the keys.
// The id regex below is not `MAP[1-8]`, so a ninth id that the command prints is seen.
test('B1. the ids the command prints equal the keys of mapChecks', async () => {
  needFile(REL);
  const mod = await import(pathToFileURL(CLI).href);
  const keys = Object.keys(mod.mapChecks({ cfg: {}, root: '.', read: () => '' })).sort();
  assert.ok(keys.length > 0, 'mapChecks holds no check, so the scan reads the wrong object');
  const r = run([CLI], scratchRepo());
  const printed = [...r.out.matchAll(/^\[(?:PASS|FAIL|SKIP)\]\s+(\S+)/gm)].map((m) => m[1]).sort();
  assert.ok(printed.length > 0, `the command printed no verdict line\n${r.out.slice(0, 1500)}`);
  assert.deepEqual(printed, keys, `the command must run every check that mapChecks holds, from one list\n${r.out.slice(0, 1500)}`);
});

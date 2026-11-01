// The test temp folder of this suite (decision test-temp-standard). Each test process writes temp files only in its run folder.
//
//   T1. The sweep removes an old sibling run folder and keeps a new one, a folder that is no run folder, and the own folder.
//   T2. The first request of a process sweeps: a child process that makes its run folder removes an old sibling, keeps a new one,
//       and makes its own folder under the one temp root.
//   T3. tmpFolder() makes its folder inside this process's run folder, and never in the system temp dir itself.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, rmSync, utimesSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, isAbsolute, join, relative } from 'node:path';
import { pathToFileURL } from 'node:url';
import { HERE, run, tmpFolder } from './helpers.mjs';
import { TEMP_ROOT, runFolder, sweepRunFolders } from './temp-root.mjs';

const TWO_DAYS_MS = 2 * 24 * 60 * 60 * 1000;
const RUN = (n, c) => `${n}-${c.repeat(32)}`;
/** True when `p` is inside `dir`, both real paths of the one run. */
const inside = (dir, p) => {
  const rel = relative(dir, p);
  return rel !== '' && !rel.startsWith('..') && !isAbsolute(rel);
};

test('T1. the sweep removes an old sibling run folder and keeps a new one, a folder that is no run folder, and the own folder', () => {
  const root = tmpFolder('pemap-sweep-');
  const old = join(root, RUN(1, 'a')), fresh = join(root, RUN(2, 'b')), other = join(root, 'not-a-run-folder'), own = join(root, RUN(3, 'c'));
  for (const d of [old, fresh, other, own]) mkdirSync(d);
  const twoDaysAgo = new Date(Date.now() - TWO_DAYS_MS);
  utimesSync(old, twoDaysAgo, twoDaysAgo);
  utimesSync(other, twoDaysAgo, twoDaysAgo);
  utimesSync(own, twoDaysAgo, twoDaysAgo);
  // The scope first: the old folder is older than a day, so a sweep that removes nothing would show here.
  assert.ok(existsSync(old) && existsSync(fresh), 'the scratch siblings must exist before the sweep');
  sweepRunFolders(root, own);
  assert.ok(!existsSync(old), 'an old sibling run folder must be swept');
  assert.ok(existsSync(fresh), 'a new sibling run folder must stay');
  assert.ok(existsSync(other), 'a folder that is no run folder must stay');
  assert.ok(existsSync(own), 'the own run folder must stay');
});

test('T2. the first request of a process sweeps the one temp root: an old sibling goes, a new one stays, and the child makes its own folder there', () => {
  mkdirSync(TEMP_ROOT, { recursive: true });
  const old = join(TEMP_ROOT, RUN(999991, 'd')), fresh = join(TEMP_ROOT, RUN(999992, 'e'));
  const twoDaysAgo = new Date(Date.now() - TWO_DAYS_MS);
  mkdirSync(old);
  mkdirSync(fresh);
  utimesSync(old, twoDaysAgo, twoDaysAgo);
  let childOwn = null;
  try {
    const script = `const m = await import(${JSON.stringify(pathToFileURL(join(HERE, 'temp-root.mjs')).href)});
console.log(m.runFolder());`;
    const r = run(['--input-type=module', '-'], HERE, script);
    assert.equal(r.status, 0, `the child must make its run folder\n${r.out.slice(0, 1500)}`);
    childOwn = r.stdout.trim().split('\n').pop();
    assert.ok(inside(TEMP_ROOT, childOwn), `the child's run folder ${childOwn} must be inside the one temp root ${TEMP_ROOT}`);
    assert.ok(!existsSync(old), 'an old sibling run folder must be swept on the first request of the child');
    assert.ok(existsSync(fresh), 'a new sibling run folder must stay after the child sweeps');
    assert.ok(existsSync(childOwn), 'the child run folder must exist after the child exits');
  } finally {
    rmSync(fresh, { recursive: true, force: true });
    rmSync(old, { recursive: true, force: true });
    if (childOwn) rmSync(childOwn, { recursive: true, force: true });
  }
});

test('T3. tmpFolder() makes its folder inside this process run folder, and never in the system temp dir itself', () => {
  const d = tmpFolder('pemap-check-');
  assert.ok(inside(runFolder(), d), `tmpFolder() must make ${d} inside the run folder ${runFolder()}`);
  assert.ok(inside(TEMP_ROOT, runFolder()), 'the run folder must be inside the one temp root');
  assert.notEqual(dirname(d), tmpdir(), 'a helper folder must never sit in the system temp dir');
});

// The temp folder of the skill's test suites (decision test-temp-standard, docs/decisions/test-temp-standard.md).
//
// One temp root for this repository, and one run folder per test process, named `<pid>-<UUID>`. Every helper takes its
// folder from the run folder. The first request of a process removes sibling run folders older than one day, which
// crashed runs leave behind, and keeps newer ones, which parallel runs own. Teardown removes the run folder.
//
// The root and the folder name match `lint/_test_temp.py` and `lint/test_shoot.mjs`, so each sweep also clears the
// crashed runs of the other suites. This file is a second .mjs copy of that sweep. Its reason: `lint/test_shoot.mjs`
// holds its copy inside a test file, and a suite in `skills/` cannot import from it without running its tests.
// The name of this file matches no `node --test` pattern, so it is no test.
import { mkdirSync, readdirSync, rmSync, statSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

export const TEMP_ROOT = join(tmpdir(), 'claude-settings-test-temp');
const RUN_FOLDER = /^\d+-[0-9a-f]{32}$/;
const ONE_DAY_MS = 24 * 60 * 60 * 1000;

/** Removes each sibling run folder under `root` whose mtime is over a day old, at `now`. `own` stays, and a name that is no run folder stays. */
export const sweepRunFolders = (root, own, now = Date.now()) => {
  let names;
  try { names = readdirSync(root); } catch { return; }
  for (const name of names) {
    const dir = join(root, name);
    if (dir === own || !RUN_FOLDER.test(name)) continue;
    try {
      if (statSync(dir).isDirectory() && now - statSync(dir).mtimeMs > ONE_DAY_MS) rmSync(dir, { recursive: true, force: true });
    } catch { /* another run owns it */ }
  }
};

let own = null;

/** This process's run folder. The first call makes it and sweeps the old siblings. */
export const runFolder = () => {
  if (own) return own;
  mkdirSync(TEMP_ROOT, { recursive: true });
  const dir = join(TEMP_ROOT, `${process.pid}-${randomUUID().replaceAll('-', '')}`);
  mkdirSync(dir);
  own = dir;
  sweepRunFolders(TEMP_ROOT, dir);
  return dir;
};

/** Removes this process's run folder, when it was made. */
export const removeRunFolder = () => {
  if (!own) return;
  rmSync(own, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  own = null;
};

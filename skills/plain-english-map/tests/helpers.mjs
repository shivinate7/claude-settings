// Shared by the tests of the plain-english-map skill. This file is no test: its name matches no `node --test` pattern.
//
// Run the tests from this folder: `cd skills/plain-english-map/tests && node --test`.
//
// A child process gets the parent's env with every `GIT_*` variable and `NODE_PATH` removed. A `GIT_*` variable would
// win over the child's cwd, so `git init` in a scratch folder could hit the parent repository. `NODE_PATH` would hide
// where `typescript` is found, and the tests must see exactly that.
import { apply } from '../../../lint/_test_git.mjs';  // test-run signing opt-out (lint/_test_git.mjs)
import { after } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdtempSync, readFileSync, realpathSync, symlinkSync, unlinkSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { removeRunFolder, runFolder } from './temp-root.mjs';

export const HERE = dirname(fileURLToPath(import.meta.url));
export const SKILL = join(HERE, '..'); // skills/plain-english-map
export const ROOT = join(SKILL, '..', '..'); // the claude-settings root
export const FIXTURE = join(HERE, 'fixture');

/** Fail with the missing path, so a case that needs a skill file goes red for that reason and no other. */
export const needFile = (rel) => assert.ok(existsSync(join(SKILL, rel)), `skills/plain-english-map/${rel} is missing`);

/** The parent's env, with no `GIT_*` key and no `NODE_PATH`, and the test-run signing opt-out added back, so no child signs. */
export const cleanEnv = () => apply(Object.fromEntries(Object.entries(process.env).filter(([k]) => !/^(GIT_.*|NODE_PATH)$/i.test(k))));

/** A path in one comparable form. `native` expands 8.3 names such as SHIVAM~1. Windows paths compare in lower case. */
export const real = (p) => (process.platform === 'win32' ? realpathSync.native(p).toLowerCase() : realpathSync.native(p));

/** Runs node with `args`. The cwd is the folder the case names, and `input` goes to stdin. `env` adds to the clean env, or replaces a key of it. */
export const run = (args, cwd, input, env = {}) => {
  const r = spawnSync(process.execPath, args, { cwd, env: { ...cleanEnv(), ...env }, input, encoding: 'utf8', timeout: 120000, maxBuffer: 64 * 1024 * 1024 });
  return { status: r.status, signal: r.signal, stdout: r.stdout ?? '', out: `${r.stdout ?? ''}${r.stderr ?? ''}` };
};

const links = [];
after(() => {
  // A junction goes first, and by `unlinkSync`, so no remove ever walks through it into the folder it names.
  for (const l of links) { try { unlinkSync(l); } catch { /* already gone */ } }
  removeRunFolder();
});

/** A new folder in this process's run folder (test-temp-standard), removed when the file's tests end. Never a folder of the system temp dir itself. */
export const tmpFolder = (prefix) => mkdtempSync(join(runFolder(), prefix));

/** A junction (a symlink on POSIX) in its own tmp folder, to the folder `target`. It stands for the install link in ~/.claude/skills. */
export const junction = (target) => {
  const link = join(tmpFolder('pemap-link-'), 'skill');
  symlinkSync(target, link, 'junction');
  links.push(link);
  // The scope first: the link must reach the target, and its typed path must not be its real path. Else a case proves nothing about a link.
  assert.equal(real(link), real(target), 'the link must name the folder it was made for');
  assert.notEqual(realpathSync(link), link, 'the typed path of the link must differ from its real path');
  return link;
};

/** Runs git in `dir` and answers its stdout. The env has no `GIT_*` key, and the line-end setting is fixed, so a machine setting never changes a status. */
export const gitIn = (dir, ...a) =>
  execFileSync('git', ['-c', 'core.autocrlf=false', ...a], { cwd: dir, env: cleanEnv(), encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });

/**
 * A copy of `tests/fixture/` in a fresh git repository in tmp. `git add -N` lists each file for `git ls-files` and writes no object.
 * With `commit`, the files are committed too, so `git rev-parse HEAD` works. A host repository that builds a page has a commit.
 * The commit runs with an empty hooks folder, so no hook of the machine runs in the scratch repository.
 */
export const scratchRepo = ({ commit = false } = {}) => {
  const dir = tmpFolder('pemap-repo-');
  cpSync(FIXTURE, dir, { recursive: true });
  const git = (...a) => gitIn(dir, ...a);
  git('init', '-q');
  if (commit) {
    git('add', '.');
    git('-c', `core.hooksPath=${tmpFolder('pemap-nohooks-')}`, '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-q', '-m', 'fixture');
  } else git('add', '-N', '.');
  // The scope first: the copy must be a git repository that tracks the fixture, or a verdict below says nothing about the skill.
  const tracked = git('ls-files').split('\n').map((l) => l.trim());
  for (const f of ['map.config.json', 'src/home.ts', 'src/notes.ts', 'src/screens.ts', 'src/retry.py', 'src/caller.py', 'config.json', 'docs/map/core.md', 'docs/map/homes.md', 'docs/map/traces/home.md'])
    assert.ok(tracked.includes(f), `the scratch repository does not track ${f}`);
  if (commit) assert.match(git('rev-parse', 'HEAD').trim(), /^[0-9a-f]{40}$/, 'the scratch repository has no commit');
  return dir;
};

/** Removes the map line that names `file` from `docs/map/core.md` of a scratch repository. */
export const dropMapLine = (dir, file) => {
  const p = join(dir, 'docs', 'map', 'core.md');
  const lines = readFileSync(p, 'utf8').split('\n');
  const kept = lines.filter((l) => !l.includes(`\`${file}\``));
  assert.equal(lines.length - kept.length, 1, `docs/map/core.md must hold exactly one line for ${file}`);
  writeFileSync(p, kept.join('\n'));
};

export const IDS = ['MAP1', 'MAP2', 'MAP3', 'MAP4', 'MAP5', 'MAP6', 'MAP7', 'MAP8', 'MAP9'];

/** The verdict lines of a run as one string, such as `MAP1=PASS MAP2=FAIL`. A line looks like `[PASS] MAP1`. */
export const verdicts = (out) =>
  [...out.matchAll(/^\[(PASS|FAIL|SKIP)\]\s+(MAP\d+)\b/gm)].map((m) => `${m[2]}=${m[1]}`).join(' ');

/** What the verdict string says when every check in `IDS` passes, except the ids in `except`, which get the given verdict. */
export const expected = (except = {}) => IDS.map((id) => `${id}=${except[id] ?? 'PASS'}`).join(' ');

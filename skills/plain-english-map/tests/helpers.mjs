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
import { chmodSync, cpSync, existsSync, mkdtempSync, readdirSync, readFileSync, realpathSync, statSync, symlinkSync, unlinkSync, writeFileSync } from 'node:fs';
import { delimiter, dirname, join } from 'node:path';
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

// The files of `tests/fixture/` that the scratch repository must track.
const FIXTURE_TRACKED = ['map.config.json', 'src/home.ts', 'src/notes.ts', 'src/screens.ts', 'src/retry.py', 'src/caller.py', 'config.json', 'docs/map/core.md', 'docs/map/homes.md', 'docs/map/traces/home.md', 'src/home.spec.ts', 'src/pkg/index.ts', 'src/pkg.spec.ts','src/retry_check.py', 'src/run_retry_check.py'];
/** Commits every change of `dir`. With `epoch` (unix seconds) the author time is that epoch in UTC, which is what `git blame` and `git log %at` read. Without it, the commit has the current time. The commit runs with an empty hooks folder. */
export const commitAt = (dir, epoch, message) => {
  gitIn(dir, 'add', '-A');
  const date = epoch === undefined ? [] : [`--date=${epoch} +0000`];
  gitIn(dir, '-c', `core.hooksPath=${tmpFolder('pemap-nohooks-')}`, '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-q', ...date, '-m', message);
};

/** A case that puts an extensionless POSIX script on PATH skips on win32: CreateProcess runs no such script, and a `.cmd` needs a shell that these commands never use. */
export const POSIX_ONLY = { skip: process.platform === 'win32' ? 'an extensionless POSIX script on PATH: only POSIX PATH lookup runs it' : false };

/**
 * A git first on PATH. It appends each call whose arguments contain `match` (every call when `match` is '') to its log, one line per call,
 * then runs the real git. A cost case counts the lines of `log`. Its env is added to a run's env.
 */
export const gitShim = (match = '') => {
  const real = (process.env.PATH ?? '').split(delimiter).map((d) => join(d, 'git')).find((p) => existsSync(p));
  assert.ok(real, 'git must be on PATH for the shim');
  const bin = tmpFolder('pemap-gitshim-');
  const log = join(bin, 'git-calls.log');
  const sh = join(bin, 'git');
  writeFileSync(sh, '#!/bin/sh\ncase "$*" in *"$SHIM_GIT_MATCH"*) echo "$*" >> "$SHIM_GIT_LOG";; esac\nexec "$SHIM_GIT_REAL" "$@"\n');
  chmodSync(sh, 0o755);
  writeFileSync(log, '');
  return { log, env: { PATH: `${bin}${delimiter}${process.env.PATH}`, SHIM_GIT_LOG: log, SHIM_GIT_REAL: real, SHIM_GIT_MATCH: match } };
};

/**
 * A copy of `fixture` (default `tests/fixture/`) in a fresh git repository in tmp. `track` lists the files the copy must track.
 * `git add -N` lists each file for `git ls-files` and writes no object.
 * With `commit`, the files are committed too, so `git rev-parse HEAD` works. A host repository that builds a page has a commit.
 * The commit runs with an empty hooks folder, so no hook of the machine runs in the scratch repository.
 */
export const scratchRepo = ({ commit = false, fixture = FIXTURE, track = FIXTURE_TRACKED } = {}) => {
  const dir = tmpFolder('pemap-repo-');
  cpSync(fixture, dir, { recursive: true });
  // A Windows checkout (core.autocrlf) holds the fixture with CRLF. The cases edit it by `\n` and by exact text, so the copy is LF on every platform.
  // Every fixture file is text. The product reads CRLF fine, and format-version.test.mjs builds its CRLF repositories itself.
  for (const rel of readdirSync(dir, { recursive: true })) {
    const p = join(dir, rel);
    if (statSync(p).isFile()) writeFileSync(p, readFileSync(p, 'utf8').replace(/\r\n/g, '\n'));
  }
  const git = (...a) => gitIn(dir, ...a);
  git('init', '-q');
  if (commit) commitAt(dir, undefined, 'fixture');
  else git('add', '-N', '.');
  // The scope first: the copy must be a git repository that tracks the fixture, or a verdict below says nothing about the skill.
  const tracked = git('ls-files').split('\n').map((l) => l.trim());
  for (const f of track)
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

export const IDS = ['MAP1', 'MAP2', 'MAP3', 'MAP4', 'MAP5', 'MAP6', 'MAP7', 'MAP8', 'MAP9', 'MAP10', 'MAP11'];

// The verdict a check prints when the fixture leaves its setting out. MAP10 skips when no decision key is set.
const DEFAULT_VERDICT = { MAP10: 'SKIP' };

/** The verdict lines of a run as one string, such as `MAP1=PASS MAP2=FAIL`. A line looks like `[PASS] MAP1`. */
export const verdicts = (out) =>
  [...out.matchAll(/^\[(PASS|FAIL|SKIP)\]\s+(MAP\d+)\b/gm)].map((m) => `${m[2]}=${m[1]}`).join(' ');

/** What the verdict string says when every check in `IDS` passes, except the ids in `except`, which get the given verdict. */
export const expected = (except = {}) => IDS.map((id) => `${id}=${except[id] ?? DEFAULT_VERDICT[id] ?? 'PASS'}`).join(' ');

/** The verdict of one check in a run (`PASS`, `FAIL` or `SKIP`), or null when the run prints no line for it. */
export const verdictOf = (out, id) => out.match(new RegExp(`^\\[(PASS|FAIL|SKIP)\\] ${id}\\b`, 'm'))?.[1] ?? null;

/** The `[FAIL]` lines of a run. */
export const failLines = (out) => out.split('\n').filter((l) => l.startsWith('[FAIL]'));

/** The first 1500 characters of a run's output, for a failure message. */
export const tail = (out) => out.slice(0, 1500);

/** Reads a file of a scratch repository as text. */
export const readIn = (dir, rel) => readFileSync(join(dir, rel), 'utf8');

/** Writes a file of a scratch repository. The folder must exist. */
export const writeIn = (dir, rel, body) => writeFileSync(join(dir, rel), body);

// ---- Sub-lines of a map line: `  - Decisions: ` and `  - Debts: ` (one home, read and set by the decision and the record-named suites).
const SUB_LINE_RE = /^\s+[-*+]\s/; // an indented list line under a map line

const mapIndexOf = (lines, page, file) => {
  const found = lines.flatMap((l, i) => (l.startsWith(`- \`${file}\` `) ? [i] : []));
  assert.equal(found.length, 1, `${page} must hold exactly one map line for ${file}`);
  return found[0];
};

/** The ids on the sub-line labelled `label` under the map line of `file` on `page`, in order. [] when it has none. The label may sit at any position among the sub-lines. */
export const subLineIds = (dir, page, file, label) => {
  const lines = readIn(dir, page).split('\n');
  const labelled = new RegExp(`^\\s+[-*+]\\s+${label}:`);
  const ids = [];
  for (let j = mapIndexOf(lines, page, file) + 1; j < lines.length && SUB_LINE_RE.test(lines[j]); j++)
    if (labelled.test(lines[j])) ids.push(...[...lines[j].matchAll(/`([^`]+)`/g)].map((m) => m[1]));
  return ids;
};

/** Sets the sub-line labelled `label` under the map line of `file` to `ids`, or removes it when `ids` is null. Edits the page only. */
export const setSubLine = (dir, page, file, label, ids) => {
  const lines = readIn(dir, page).split('\n');
  const i = mapIndexOf(lines, page, file);
  const labelled = new RegExp(`^\\s+[-*+]\\s+${label}:`);
  for (let j = i + 1; j < lines.length && SUB_LINE_RE.test(lines[j]); ) {
    if (labelled.test(lines[j])) lines.splice(j, 1);
    else j++;
  }
  if (ids) lines.splice(i + 1, 0, `  - ${label}: ${ids.map((d) => `\`${d}\``).join(', ')}`);
  writeIn(dir, page, lines.join('\n'));
};

/** The debts folder of a repository, as lint/layout.py `path()` gives it. It is read from lint/layout.json by that one home, never written here. */
export const debtsDirOf = (dir) =>
  execFileSync('python3', ['-c', 'import sys; sys.path.insert(0, sys.argv[1]); import layout; print(layout.path(sys.argv[2], "debts"))', join(ROOT, 'lint'), dir], {
    cwd: dir, env: cleanEnv(), encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();

// map-stale.mjs lists the map lines whose cited file moved after the line was last written. It is advisory: it exits 0 in every case.
//
//   A map line's date is the newest `git blame` author time of the line and of its indented fact lines.
//   A file's date is the author time of its last commit.
//   A line is listed when its file's date is more than one day after its line's date. Each listed row gives the path, the line
//   date, the file date (YYYY-MM-DD, in that order) and the gap in days. Worst gap first. With none listed, it prints "nothing stale".
//   A shallow clone, or a folder with no git, prints an unknown line that says why. It never prints "nothing stale" there.
//
// The dates are fixed. `commitAt` sets each commit's author time to a given epoch, at noon UTC, so no zone moves a date.
// No case reads the clock. Each case checks its claim first, and the exit code last, so a failure names the claim.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { appendFileSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { POSIX_ONLY, SKILL, cleanEnv, commitAt, gitIn, gitShim, run, scratchRepo, tmpFolder } from './helpers.mjs';

const STALE = join(SKILL, 'scripts', 'map-stale.mjs');
const DAY = 86400;
const T0 = Date.UTC(2026, 9, 1, 12) / 1000; // The author time of the fixture's base commit, from which every map line is dated
const iso = (epoch) => new Date(epoch * 1000).toISOString().slice(0, 10);
const head = (r) => r.out.slice(0, 1500);

/** A scratch repository. The fixture is committed at T0, then each `[file, epoch]` adds a line to `file` in a commit at `epoch`. */
const history = (touches) => {
  const dir = scratchRepo();
  commitAt(dir, T0, 'fixture');
  for (const [file, epoch] of touches) {
    appendFileSync(join(dir, file), '\n');
    commitAt(dir, epoch, `change ${file}`);
  }
  return dir;
};

/** Rewords one fact line of docs/map/core.md in a commit at `epoch`. The old text must be there exactly once. */
const reword = (dir, from, to, epoch) => {
  const p = join(dir, 'docs', 'map', 'core.md');
  const text = readFileSync(p, 'utf8');
  assert.equal(text.split(from).length - 1, 1, `docs/map/core.md must hold this text once: ${from}`);
  writeFileSync(p, text.replace(from, to));
  commitAt(dir, epoch, 'reword a fact line');
};

/** The author time of the last commit that touched `file`, as `git log --format=%at` prints it. */
const lastCommit = (dir, file) => gitIn(dir, 'log', '-1', '--format=%at', '--', file).trim();

/** The line of `out` that names `path`, or undefined. */
const rowFor = (out, path) => out.split('\n').find((l) => l.includes(path));

/** True when `row` holds the number `n` as a whole number, so `5`, `5 days` and `5.0` count, and a 5 inside a date does not. */
const hasDays = (row, n) => new RegExp(`(?<![\\d.])${n}(?![\\d])`).test(row);

/** True when git reads `dir` as a repository. */
const isRepo = (dir) => {
  try {
    gitIn(dir, 'rev-parse', '--git-dir');
    return true;
  } catch {
    return false;
  }
};

test('ST1. a file committed 5 days after its map line is listed, with its path, both dates and gap 5', () => {
  const dir = history([['src/home.ts', T0 + 5 * DAY]]);
  // The scope first: the repository holds the date this case names, or the row below says nothing about the gap.
  assert.equal(lastCommit(dir, 'src/home.ts'), String(T0 + 5 * DAY));
  const r = run([STALE], dir);
  const row = rowFor(r.stdout, 'src/home.ts');
  assert.ok(row, `the listing must name src/home.ts, which was committed 5 days after its map line\n${head(r)}`);
  const lineAt = row.indexOf(iso(T0));
  const fileAt = row.indexOf(iso(T0 + 5 * DAY));
  assert.ok(lineAt >= 0 && fileAt > lineAt, `the row must hold the line date ${iso(T0)}, then the file date ${iso(T0 + 5 * DAY)}\n${row}`);
  assert.ok(hasDays(row, 5), `the row must give the gap as 5 days\n${row}`);
  assert.equal(r.status, 0, `the command is advisory and must exit 0\n${head(r)}`);
});

test('ST2. a file committed the same day as its map line is not listed', () => {
  const dir = history([['src/notes.ts', T0 + 6 * 3600], ['src/home.ts', T0 + 5 * DAY]]);
  // The scope first: the same-day file and the stale file hold the dates this case names.
  assert.equal(lastCommit(dir, 'src/notes.ts'), String(T0 + 6 * 3600));
  assert.equal(lastCommit(dir, 'src/home.ts'), String(T0 + 5 * DAY));
  const r = run([STALE], dir);
  // The control: the stale file is listed, so the run did its work, and the absence below is not an empty run.
  assert.ok(rowFor(r.stdout, 'src/home.ts'), `the control src/home.ts must be listed, or the run did no work\n${head(r)}`);
  assert.equal(rowFor(r.stdout, 'src/notes.ts'), undefined, `src/notes.ts was committed 6 hours after its map line, which is not more than one day, so it must not be listed\n${head(r)}`);
  assert.equal(r.status, 0, `the command is advisory and must exit 0\n${head(r)}`);
});

test('ST3. two stale lines rank worst gap first, not by path or by commit order', () => {
  // The worse gap sits on the later path and the later commit, so an alphabetical or commit-order listing fails here.
  const dir = history([['src/home.ts', T0 + 2 * DAY], ['src/notes.ts', T0 + 5 * DAY]]);
  // The scope first: the two files hold the dates this case names.
  assert.equal(lastCommit(dir, 'src/notes.ts'), String(T0 + 5 * DAY));
  assert.equal(lastCommit(dir, 'src/home.ts'), String(T0 + 2 * DAY));
  const r = run([STALE], dir);
  const lines = r.stdout.split('\n');
  const worst = lines.findIndex((l) => l.includes('src/notes.ts'));
  const next = lines.findIndex((l) => l.includes('src/home.ts'));
  assert.ok(worst >= 0 && next >= 0, `both stale lines must be listed\n${head(r)}`);
  assert.ok(worst < next, `src/notes.ts (gap 5) must be listed before src/home.ts (gap 2)\n${head(r)}`);
  assert.ok(hasDays(lines[worst], 5), `the src/notes.ts row must give gap 5\n${lines[worst]}`);
  assert.ok(hasDays(lines[next], 2), `the src/home.ts row must give gap 2\n${lines[next]}`);
  assert.equal(r.status, 0, `the command is advisory and must exit 0\n${head(r)}`);
});

test('ST4. a fact-line edit after the file commit makes its map line fresh', () => {
  const dir = history([['src/home.ts', T0 + 5 * DAY]]);
  // The control: before the fact line is edited, src/home.ts is listed with gap 5.
  const before = run([STALE], dir);
  assert.ok(rowFor(before.stdout, 'src/home.ts'), `the control src/home.ts must be listed before its fact line is edited\n${head(before)}`);
  reword(dir, 'The title counts the saved notes.', 'The title counts the notes that are saved.', T0 + 6 * DAY);
  const r = run([STALE], dir);
  assert.equal(rowFor(r.stdout, 'src/home.ts'), undefined, `src/home.ts must not be listed: its fact line was edited 6 days after the file commit, so the line date is the newer one\n${head(r)}`);
  assert.equal(r.status, 0, `the command is advisory and must exit 0\n${head(r)}`);
});

test('ST5. nothing stale prints the nothing line and exits 0', () => {
  const dir = history([]);
  // The scope first: the fixture is committed once, so every file date equals the line date.
  assert.equal(lastCommit(dir, 'src/home.ts'), String(T0));
  const r = run([STALE], dir);
  assert.match(r.stdout, /nothing stale/i, `with no stale line the command must print the nothing line\n${head(r)}`);
  assert.equal(r.status, 0, `the command is advisory and must exit 0\n${head(r)}`);
});

test('ST6. a shallow clone prints unknown with its reason, exits 0, and never prints nothing stale', () => {
  const source = history([['src/home.ts', T0 + 5 * DAY]]);
  const parent = tmpFolder('pemap-clone-');
  const clone = join(parent, 'clone');
  gitIn(parent, 'clone', '--depth', '1', pathToFileURL(source).href, clone);
  // The scope first: the clone must be shallow, or the unknown line below is not owed.
  assert.equal(gitIn(clone, 'rev-parse', '--is-shallow-repository').trim(), 'true', 'the clone must be shallow');
  const r = run([STALE], clone);
  assert.match(r.stdout, /unknown/i, `a shallow clone must print that the result is unknown\n${head(r)}`);
  assert.match(r.stdout, /shallow/i, `the unknown line must say why: the clone is shallow\n${head(r)}`);
  assert.doesNotMatch(r.stdout, /nothing stale/i, `a shallow clone must never print nothing stale\n${head(r)}`);
  assert.equal(r.status, 0, `the command is advisory and must exit 0\n${head(r)}`);
});

test('ST7. a folder that is not a git repository prints unknown with its reason, exits 0, and never prints nothing stale', () => {
  const dir = scratchRepo();
  rmSync(join(dir, '.git'), { recursive: true, force: true });
  // The scope first: the folder is no repository and still holds its map, so the unknown line is about the missing repository.
  assert.equal(isRepo(dir), false, 'the folder must not be a git repository');
  assert.ok(readdirSync(join(dir, 'docs', 'map')).includes('core.md'), 'the folder must still hold docs/map/core.md');
  const r = run([STALE], dir);
  assert.match(r.stdout, /unknown/i, `a folder with no git must print that the result is unknown\n${head(r)}`);
  assert.match(r.stdout, /git/i, `the unknown line must say why: there is no git repository\n${head(r)}`);
  assert.doesNotMatch(r.stdout, /nothing stale/i, `a folder with no git must never print nothing stale\n${head(r)}`);
  assert.equal(r.status, 0, `the command is advisory and must exit 0\n${head(r)}`);
});

test('ST8. with no git on PATH, the command prints unknown with its reason, exits 0, and never prints nothing stale', () => {
  const dir = history([['src/home.ts', T0 + 5 * DAY]]);
  const bin = tmpFolder('pemap-nogit-'); // an empty folder: the PATH of this case holds no git
  // The scope first: with this PATH git cannot start, or the run below does not test a missing git.
  const probe = spawnSync('git', ['--version'], { env: { ...cleanEnv(), PATH: bin }, encoding: 'utf8' });
  assert.equal(probe.error?.code, 'ENOENT', 'with this PATH, git must not start');
  const r = run([STALE], dir, undefined, { PATH: bin });
  assert.match(r.stdout, /unknown/i, `with no git the command must print that the result is unknown\n${head(r)}`);
  assert.match(r.stdout, /git/i, `the unknown line must say why: git is not on PATH\n${head(r)}`);
  assert.doesNotMatch(r.stdout, /nothing stale/i, `with no git the command must never print nothing stale\n${head(r)}`);
  assert.equal(r.status, 0, `the command is advisory and must exit 0\n${head(r)}`);
});

test('ST9. cost: git runs once per map page for blame, once for all file dates and once for the shallow check', POSIX_ONLY, () => {
  const dir = history([['src/home.ts', T0 + 5 * DAY]]);
  const shim = gitShim();
  const r = run([STALE], dir, undefined, shim.env);
  // The scope first: the run must list its stale line, or the count of its git calls is about nothing.
  assert.ok(rowFor(r.stdout, 'src/home.ts'), `the run must list src/home.ts, or the call count below is about nothing\n${head(r)}`);
  const pages = readdirSync(join(dir, 'docs', 'map')).filter((f) => f.endsWith('.md')).length;
  const calls = readFileSync(shim.log, 'utf8').split('\n').filter(Boolean);
  assert.equal(calls.length, pages + 2, `git must run ${pages + 2} times: one blame per map page (${pages}), one git log for all file dates, and one shallow check. It ran ${calls.length} times:\n${calls.join('\n')}`);
});

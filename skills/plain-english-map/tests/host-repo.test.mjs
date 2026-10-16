// The host repository is the root of every run, and never the skill's own folder. A run leaves the repository as it was.
//
// The skill sits in claude-settings, and `~/.claude/skills/plain-english-map` links to it. A run starts in a host
// repository, so the root is the cwd. A root found from the script's own place would be a folder of claude-settings.
//
//   4.  `repoMapConfig()` with no argument reads `map.config.json` from `process.cwd()`.
//   5.  `node <skill>/scripts/map-picture.mjs`, run with no argument from a host repository, exits 0 and prints the path of a page.
//       The page is outside the repository, under os.tmpdir(), and it exists. It names a file of the repository. The
//       repository has no new or changed file after the run: a page in the host repository would be an untracked file in
//       every repository that runs the skill.
//   5b. An explicit output path inside the repository is refused with a non-zero exit, and no file is written. An explicit
//       output path outside the repository still works, so the refusal is not a command that always fails.
//   5c. An explicit output path that goes through a junction into the repository is refused too, with no file written in the
//       repository. A junction to a folder outside the repository still works. The test compares real paths, never typed ones.
//   5d. With TEMP, TMP and TMPDIR inside the repository, a run with no argument is refused with a non-zero exit. The default
//       page folder is under os.tmpdir(), and here that is inside the repository. The status of the repository stays empty.
//
// Each case runs in a fresh copy of `tests/fixture/` in os.tmpdir(), with a child env that has no `NODE_PATH`.
// The repository of case 5 has one commit, as a host repository that builds a page has.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, readFileSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { isAbsolute, join, relative } from 'node:path';
import { pathToFileURL } from 'node:url';
import { SKILL, gitIn, junction, needFile, real, run, scratchRepo, tmpFolder } from './helpers.mjs';

const CONFIG = join(SKILL, 'scripts', 'lib', 'map-config.mjs');
const PICTURE = join(SKILL, 'scripts', 'map-picture.mjs');

test('4. repoMapConfig() with no argument reads map.config.json from process.cwd()', () => {
  needFile('scripts/lib/map-config.mjs');
  const dir = scratchRepo();
  const script = `const m = await import(${JSON.stringify(pathToFileURL(CONFIG).href)});
const c = m.repoMapConfig();
console.log(JSON.stringify({ title: c.title, codeExtensions: c.codeExtensions, screenKeys: c.screenKeys }));`;
  const r = run(['--input-type=module', '-'], dir, script);
  assert.equal(r.status, 0, `repoMapConfig() must read the config of the cwd\n${r.out.slice(0, 1500)}`);
  assert.deepEqual(
    JSON.parse(r.stdout.trim().split('\n').pop()),
    { title: 'Fixture', codeExtensions: ['ts'], screenKeys: { file: 'src/screens.ts', name: 'SCREEN_KEYS' } },
    'the config must be the one of the fixture repository, which is the cwd'
  );
});

/** True when the path `p` is inside the folder `dir`. Both are real paths in one case. */
const inside = (dir, p) => {
  const rel = relative(dir, p);
  return rel !== '' && !rel.startsWith('..') && !isAbsolute(rel);
};

// The printed path: an absolute path that ends in `.html`, from any line of the output. The first match wins.
const printedPage = (stdout) => /(?:[A-Za-z]:[\\/]|\/)[^\r\n]*?\.html\b/.exec(stdout)?.[0] ?? null;

test('5. map-picture.mjs with no argument exits 0, prints the path of a page outside the repository, and leaves the repository unchanged', () => {
  needFile('scripts/map-picture.mjs');
  const dir = scratchRepo({ commit: true });
  // The scope first: the fixture is clean before the run, so a line in the status after it was written by the command.
  assert.equal(gitIn(dir, 'status', '--porcelain').trim(), '', 'the fixture repository must be clean before the run');
  const r = run([PICTURE], dir);
  assert.equal(r.signal, null, `the command died with a signal: ${r.signal}`);
  assert.equal(r.status, 0, `1. the command must exit 0 with no readers bound\n${r.out.slice(0, 1500)}`);
  const page = printedPage(r.stdout);
  assert.ok(page, `2. the command must print the path of the page\n${r.out.slice(0, 1500)}`);
  assert.ok(existsSync(page), `2. the printed path ${page} does not exist`);
  assert.equal(inside(real(dir), real(page)), false, `2. the page ${page} is inside the repository ${dir}`);
  assert.ok(inside(real(tmpdir()), real(page)), `2. the page ${page} is not under os.tmpdir()`);
  assert.ok(readFileSync(page, 'utf8').includes('src/home.ts'), `3. the page ${page} does not name src/home.ts, a file of the repository`);
  assert.equal(gitIn(dir, 'status', '--porcelain').trim(), '', '4. the run left a new or changed file in the repository');
});

test('5b. an explicit output path inside the repository exits non-zero and writes nothing, and one outside it works', () => {
  needFile('scripts/map-picture.mjs');
  const dir = scratchRepo({ commit: true });
  // The scope first: an explicit path outside the repository must work, or a non-zero exit below proves nothing about the path.
  const outside = join(tmpFolder('pemap-out-'), 'page.html');
  const ok = run([PICTURE, outside], dir);
  assert.equal(ok.status, 0, `an explicit output path outside the repository must work\n${ok.out.slice(0, 1500)}`);
  assert.ok(existsSync(outside), `the command wrote no page at the explicit path ${outside}`);
  // The same command refuses a path inside the repository, in an absolute form and in a relative one.
  for (const out of [join(dir, 'page.html'), 'page.html']) {
    const r = run([PICTURE, out], dir);
    assert.equal(r.signal, null, `the command died with a signal: ${r.signal}`);
    assert.notEqual(r.status, 0, `an explicit output path inside the repository (${out}) must exit non-zero\n${r.out.slice(0, 1500)}`);
    assert.equal(existsSync(join(dir, 'page.html')), false, `the command wrote ${out} inside the repository`);
  }
  assert.equal(gitIn(dir, 'status', '--porcelain').trim(), '', 'a refused run must leave the repository unchanged');
});

/** Every `.html` file under `dir`, as relative paths. The `.git` folder is skipped. */
const htmlIn = (dir) => readdirSync(dir, { recursive: true }).map(String).filter((f) => f.endsWith('.html') && !f.startsWith('.git'));

test('5c. an explicit output path through a junction into the repository exits non-zero and writes nothing, and one through a junction outside it works', () => {
  needFile('scripts/map-picture.mjs');
  const dir = scratchRepo({ commit: true });
  assert.equal(gitIn(dir, 'status', '--porcelain').trim(), '', 'the fixture repository must be clean before the run');
  assert.deepEqual(htmlIn(dir), [], 'the fixture repository must hold no page before the run');
  // The scope first: a junction to a folder outside the repository must work, or a non-zero exit below proves nothing about the junction.
  const outFolder = tmpFolder('pemap-out-');
  const outLink = junction(outFolder);
  const ok = run([PICTURE, join(outLink, 'page.html')], dir);
  assert.equal(ok.status, 0, `an explicit output path through a junction outside the repository must work
${ok.out.slice(0, 1500)}`);
  assert.ok(existsSync(join(outFolder, 'page.html')), `the command wrote no page through the junction at ${outLink}`);
  // The junction to the repository: its typed path is outside the repository, and its real path is the repository.
  const link = junction(dir);
  assert.equal(inside(real(dir), real(link)), false, 'the link itself is the repository, so its typed path must be outside the repository');
  const r = run([PICTURE, join(link, 'page.html')], dir);
  assert.equal(r.signal, null, `the command died with a signal: ${r.signal}`);
  assert.notEqual(r.status, 0, `an explicit output path through a junction into the repository must exit non-zero
${r.out.slice(0, 1500)}`);
  assert.deepEqual(htmlIn(dir), [], 'the command wrote a page inside the repository through the junction');
  assert.equal(gitIn(dir, 'status', '--porcelain').trim(), '', 'a refused run must leave the repository unchanged');
});

test('5d. with TEMP, TMP and TMPDIR inside the repository, a run with no argument exits non-zero and leaves the repository unchanged', () => {
  needFile('scripts/map-picture.mjs');
  const dir = scratchRepo({ commit: true });
  const tmp = join(dir, 'tmp');
  mkdirSync(tmp);
  const env = { TEMP: tmp, TMP: tmp, TMPDIR: tmp };
  assert.equal(gitIn(dir, 'status', '--porcelain').trim(), '', 'the fixture repository must be clean before the run');
  // The scope first: in this env, os.tmpdir() of the child must be inside the repository, on this platform. Else the case tests nothing.
  const probe = run(['-p', "require('node:os').tmpdir()"], dir, undefined, env);
  assert.equal(probe.status, 0, `the probe of os.tmpdir() failed
${probe.out.slice(0, 500)}`);
  assert.ok(inside(real(dir), real(probe.stdout.trim())), `os.tmpdir() is ${probe.stdout.trim()}, which is not inside the repository ${dir}`);
  const r = run([PICTURE], dir, undefined, env);
  assert.equal(r.signal, null, `the command died with a signal: ${r.signal}`);
  assert.notEqual(r.status, 0, `a default page folder inside the repository must exit non-zero
${r.out.slice(0, 1500)}`);
  assert.deepEqual(htmlIn(dir), [], 'the command wrote a page inside the repository');
  assert.equal(gitIn(dir, 'status', '--porcelain').trim(), '', 'a refused run must leave the repository unchanged');
});

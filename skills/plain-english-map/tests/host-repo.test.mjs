// The host repository is the root of every run, and never the skill's own folder.
//
// The skill sits in claude-settings, and `~/.claude/skills/plain-english-map` links to it. A run starts in a host
// repository, so the root is the cwd. A root found from the script's own place would be a folder of claude-settings.
//
//   4. `repoMapConfig()` with no argument reads `map.config.json` from `process.cwd()`.
//   5. `node <skill>/scripts/map-picture.mjs`, run from a host repository with no readers bound, writes the page inside that
//      repository, the page names a file of the repository, and the command exits 0.
//
// Each case runs in a fresh copy of `tests/fixture/` in os.tmpdir(), with a child env that has no `NODE_PATH`.
// Case 5 does not name the page's path or its argument, because the skill owns them. The case takes any new `.html` file
// in the repository. The repository has one commit, as a host repository that builds a page has.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { SKILL, needFile, run, scratchRepo } from './helpers.mjs';

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

// Every file under `dir`, as a posix path relative to it. The .git folder is left out.
const filesOf = (dir) =>
  readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((e) => e.isFile())
    .map((e) => join(e.parentPath ?? e.path, e.name).slice(dir.length + 1).split('\\').join('/'))
    .filter((f) => !f.startsWith('.git/'));

test('5. map-picture.mjs, run from a host repository, writes a page inside it that names a file of it, and exits 0 with no readers bound', () => {
  needFile('scripts/map-picture.mjs');
  const dir = scratchRepo({ commit: true });
  const before = new Set(filesOf(dir));
  // The scope first: the fixture holds no page, so any page below was written by the command.
  assert.deepEqual([...before].filter((f) => f.endsWith('.html')), [], 'the fixture must hold no .html file');
  const r = run([PICTURE], dir);
  assert.equal(r.signal, null, `the command died with a signal: ${r.signal}`);
  assert.equal(r.status, 0, `the command must exit 0 with no readers bound\n${r.out.slice(0, 1500)}`);
  const pages = filesOf(dir).filter((f) => !before.has(f) && f.endsWith('.html'));
  assert.ok(pages.length > 0, `the command wrote no .html page inside the repository\n${r.out.slice(0, 1500)}`);
  assert.ok(
    pages.some((f) => readFileSync(join(dir, f), 'utf8').includes('src/home.ts')),
    `no new page names src/home.ts, a file of the repository. Pages: ${pages.join(', ')}`
  );
});

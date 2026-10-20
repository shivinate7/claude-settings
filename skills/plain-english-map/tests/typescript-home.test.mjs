// `typescript` installs once, in claude-settings, for every repository that runs the skill.
//
// `scripts/lib/lazy-typescript.mjs` resolves `typescript` from its own real path. `~/.claude/skills/plain-english-map` is a link
// to this folder, so the real path is inside claude-settings, and the package comes from the `node_modules` of claude-settings.
// It never comes from the host repository, from the cwd, or from `NODE_PATH`.
//
// Each case runs a child node process. The child has no `NODE_PATH` and no `GIT_*` variable, and its cwd is os.tmpdir(), a folder
// with no node_modules above it. The child loads the helper, reads `typescript`'s version, and prints each `typescript.js` file in
// the module cache. The case compares that file with `<claude-settings>/node_modules/typescript`, by native real path.
//
//   1. Run by its direct path.
//   2. Run through a junction in tmp that names the skill folder. That is the install link.
//   3. claude-settings pins `typescript` to `~5.8.2` in `package.json`, holds a lock file, and ignores `node_modules/`.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { ROOT, SKILL, junction, needFile, real, run } from './helpers.mjs';

const REL = 'scripts/lib/lazy-typescript.mjs';
const HOME = join(ROOT, 'node_modules', 'typescript');

// The child script, as module text on stdin. `String.raw` keeps the backslash of the path test.
const probe = (lazy) => String.raw`
import { createRequire } from 'node:module';
const m = await import(${JSON.stringify(pathToFileURL(lazy).href)});
const version = m.default.version;
const cache = createRequire(process.cwd() + '/x.cjs').cache;
const files = Object.keys(cache).filter((k) => k.replaceAll('\\', '/').endsWith('/typescript/lib/typescript.js'));
console.log(JSON.stringify({ version, files }));
`;

const assertOwnTypescript = (lazy) => {
  const r = run(['--input-type=module', '-'], tmpdir(), probe(lazy));
  assert.equal(r.status, 0, `the helper must load typescript with no NODE_PATH and a cwd outside any repository\n${r.out.slice(0, 1500)}`);
  const { version, files } = JSON.parse(r.stdout.trim().split('\n').pop());
  assert.match(version, /^5\.8\./, `typescript must be 5.8.x, the pin of the map skill. Loaded ${version}`);
  assert.ok(files.length > 0, 'the module cache holds no typescript.js, so the proof reads the wrong thing');
  // The scope first: claude-settings must hold the package, or the paths below compare nothing.
  assert.ok(existsSync(HOME), 'claude-settings has no node_modules/typescript. Run `npm ci` in the repository root');
  for (const f of files) assert.ok(real(f).startsWith(real(HOME) + sep), `typescript loaded from ${f}, and not from ${HOME}`);
};

test('1. run by its direct path, the helper loads typescript from the node_modules of claude-settings', () => {
  needFile(REL);
  assertOwnTypescript(join(SKILL, REL));
});

test('2. run through a link to the skill folder, the helper loads typescript from the node_modules of claude-settings', () => {
  needFile(REL);
  assertOwnTypescript(join(junction(SKILL), 'scripts', 'lib', 'lazy-typescript.mjs'));
});

test('3. claude-settings pins typescript to ~5.8.2 in package.json, holds a lock file for it, and ignores node_modules/', () => {
  const file = (rel) => join(ROOT, rel);
  assert.ok(existsSync(file('package.json')), 'package.json is missing from the claude-settings root');
  const pkg = JSON.parse(readFileSync(file('package.json'), 'utf8'));
  const pin = pkg.dependencies?.typescript ?? pkg.devDependencies?.typescript;
  assert.equal(pin, '~5.8.2', 'package.json must pin typescript to ~5.8.2');
  assert.ok(existsSync(file('package-lock.json')), 'package-lock.json is missing, so `npm ci` cannot run');
  const lock = JSON.parse(readFileSync(file('package-lock.json'), 'utf8'));
  assert.match(lock.packages?.['node_modules/typescript']?.version ?? '', /^5\.8\./, 'the lock file must hold typescript 5.8.x');
  const ignored = readFileSync(file('.gitignore'), 'utf8').split(/\r?\n/).some((l) => /^\/?node_modules\/?$/.test(l.trim()));
  assert.ok(ignored, '.gitignore must list node_modules/');
});

// The alias read of the plain-english map on a repository path with backslash separators (`readPathAliases` in
// `scripts/lib/tsconfig-paths.mjs`). These cases run on every platform.
//
// On Windows the root path holds backslashes. TypeScript normalises them to forward slashes for the tsconfig's own file name.
// A parse error of that file then fails TypeScript's `Debug.assertEqual` on the two spellings. The reader catches the throw and
// says `cannot be read`, where a truncated tsconfig must say `cannot be parsed`. Also, `rel()` names the baseUrl by a path that
// climbs out of the repository, since the root and TypeScript's folder spell the same folder two ways.
//
// The contract these cases pin: a backslash in the root path is a separator on every platform, because TypeScript converts it on
// every platform. A fix must not key on `process.platform === 'win32'`. On POSIX a backslash is a name character, so `backslashRoot`
// makes the root a symlink named `plain\repo` to `plain/repo`. The raw path keeps the backslash, and the forward path reaches the
// same folder.
//
// W1a and W1b are red on Linux at head. W1a is red on Windows at head too, which is the CI failure. W1b is green on Windows at head,
// since win32 `path.relative` accepts mixed separators. W1c is the control: the same two tsconfigs under a forward-slash root.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, symlinkSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { readPathAliases } from '../scripts/lib/tsconfig-paths.mjs';
import { tmpFolder } from './helpers.mjs';

const TRUNCATED = '{\n  "compilerOptions": {\n    "baseUrl": ".",\n    "paths": {"@/*": ["./*"]}\n';
const VALID = '{\n  "compilerOptions": {\n    "baseUrl": "src",\n    "paths": {"@/*": ["./*"]}\n  }\n}\n';

/** A folder `plain/repo` in a new tmp folder, with `text` as its tsconfig.json. Its path holds no backslash. */
const repoWith = (text) => {
  const base = tmpFolder('pemap-tsc-');
  const folder = join(base, 'plain', 'repo');
  mkdirSync(folder, { recursive: true });
  writeFileSync(join(folder, 'tsconfig.json'), text);
  return { base, folder };
};

/** The same folder, named by a root path with a backslash separator. On POSIX a symlink named `plain\repo` stands in for the separator. */
const backslashRoot = ({ base, folder }) => {
  const root = join(base, 'plain\\repo');
  if (process.platform !== 'win32') symlinkSync(folder, root, 'dir');
  return root;
};

/** The scope of a backslash case: the root holds a backslash, and its tsconfig.json is there under that root and in the folder it names. */
const scopeOf = (root, folder) => {
  assert.ok(root.includes('\\'), 'the root path must hold a backslash separator, or the case reaches nothing');
  assert.ok(existsSync(join(root, 'tsconfig.json')), 'tsconfig.json must exist under the root path that holds a backslash');
  assert.ok(existsSync(join(folder, 'tsconfig.json')), 'tsconfig.json must exist in the folder the root names');
};

test('W1a. a truncated tsconfig under a root path with backslash separators reads as a parse failure, not as a read failure', () => {
  const repo = repoWith(TRUNCATED);
  const root = backslashRoot(repo);
  scopeOf(root, repo.folder);
  const r = readPathAliases(root);
  assert.equal(r.ok, false, 'the truncated tsconfig must read as unknown');
  assert.match(r.reason, /^tsconfig\.json cannot be parsed: /, `a backslash in the root path made TypeScript throw on the parse error, so the reader said "cannot be read"; it must say "cannot be parsed". Got: ${r.reason}`);
});

test('W1b. a valid tsconfig under a root path with backslash separators reads repo-relative names with forward slashes', () => {
  const repo = repoWith(VALID);
  const root = backslashRoot(repo);
  scopeOf(root, repo.folder);
  const r = readPathAliases(root);
  assert.equal(r.ok, true, `the valid tsconfig must read. Got: ${r.reason}`);
  assert.equal(r.aliases.baseUrl, 'src', `baseUrl must be the repository-relative name 'src'; a backslash in the root path made it a path that climbs out of the repository. Got: ${r.aliases.baseUrl}`);
  assert.equal(r.aliases.pathsBase, 'src', `pathsBase must be the repository-relative name 'src', as baseUrl is. Got: ${r.aliases.pathsBase}`);
});

test('W1c. control: the same two tsconfigs under a root path with forward slashes read as they do today', () => {
  const repo = repoWith(TRUNCATED);
  const root = repo.folder.split('\\').join('/');
  assert.ok(!root.includes('\\'), 'the control root must hold no backslash');
  assert.ok(existsSync(join(root, 'tsconfig.json')), 'tsconfig.json must exist under the control root');
  const broken = readPathAliases(root);
  assert.equal(broken.ok, false, 'the truncated tsconfig must read as unknown');
  assert.match(broken.reason, /^tsconfig\.json cannot be parsed: /, `the forward-slash root must read the parse error as a parse failure. Got: ${broken.reason}`);
  writeFileSync(join(repo.folder, 'tsconfig.json'), VALID);
  const valid = readPathAliases(root);
  assert.equal(valid.ok, true, `the valid tsconfig must read under the control root. Got: ${valid.reason}`);
  assert.equal(valid.aliases.baseUrl, 'src', `the control baseUrl must be 'src'. Got: ${valid.aliases.baseUrl}`);
  assert.equal(valid.aliases.pathsBase, 'src', `the control pathsBase must be 'src'. Got: ${valid.aliases.pathsBase}`);
});

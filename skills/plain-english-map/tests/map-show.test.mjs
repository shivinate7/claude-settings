// The map-show command of the skill: `node <skill>/scripts/map-show.mjs <path|area|folder/>`, run from the root of a
// repository that has `map.config.json`. It reads the map through the parsers of `scripts/map-check.mjs`.
//
//   a file path  prints its area id, its map line sentence, its fact lines, its `## Homes` lines and its trace steps.
//   an area id   prints each map line of that area as `path — sentence`, with no fact line.
//   a folder     (ends with `/`) prints each map line whose path starts with it.
//   nothing      prints `no map line for <arg>` on stderr and exits 1. No arg prints a usage line and exits 2.
//   unreadable   a map page the command cannot read: one plain stderr line, exit 3, no stack trace.
//
// A map line is a list line whose path the config's `codeExtensions` accepts, as MAP1 reads it. The fixture names
// only `ts`, so a `.py` or `.json` line is no map line there. A case that needs one sets `codeExtensions` in its own
// scratch copy. A Tables row is never a map line.
//
// Every case calls `needFile` first, so on a checkout with no command each case fails for the missing file.
// The fixture holds one area (`core`), one Homes page and one trace page, so `src/home.ts` reaches every kind of line.
// `run` joins stdout and stderr in `out`, stdout first, so the stderr of a run is what follows its stdout.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { SKILL, gitIn, junction, needFile, run, scratchRepo } from './helpers.mjs';

const CLI = join(SKILL, 'scripts', 'map-show.mjs');
const CHECK = join(SKILL, 'scripts', 'map-check.mjs');
const REL = 'scripts/map-show.mjs';

// The map lines of area `core` for files that the fixture config names as code (`codeExtensions: ["ts"]`), as [path, sentence].
const TS_LINES = [
  ['src/screens.ts', 'Lists the screen keys of the fixture app.'],
  ['src/home.ts', 'Builds the title of the home screen from the saved notes.'],
  ['src/notes.ts', 'Holds the saved notes'],
];
// The map lines of area `core` for files the fixture config does not name as code. Each one prints only once its extension is named.
const OTHER_LINES = [
  ['src/retry.py', 'Holds the retry wait.'],
  ['src/caller.py', 'Calls the retry module, and reads its retry wait.'],
  ['config.json', 'Holds the retry settings as JSON.'],
];
const ALL_LINES = [...TS_LINES, ...OTHER_LINES];
// The fact lines of area `core` in the fixture.
const AREA_FACTS = [
  'The title counts the saved notes.',
  'A failed call waits 30 s before its next try.',
  'The caller reads the retry wait of the retry module.',
  'The file waits 30 s before a retry.',
];
const HOME_LINE = 'Builds the title of the home screen from the saved notes.';
const HOME_FACT = 'The title counts the saved notes.';
const HOME_STEP = 'Builds the title of the home screen.';
const NOTES_STEP = 'Gives the saved notes that the title counts';
const RETRY_FACT = 'A failed call waits 30 s before its next try.';
const SCREENS_LINE = 'Lists the screen keys of the fixture app.';
const PY_EXTS = ['ts', 'py', 'json'];

/** The command with `args`, run in a fresh copy of the fixture, after the check that names the missing file. */
const show = (args, dir = scratchRepo()) => {
  needFile(REL);
  return run([CLI, ...args], dir);
};

/** The stderr of a run: what `out` holds after its stdout. */
const stderrOf = (r) => r.out.slice(r.stdout.length);

/** The first line of `out` that holds every part, or null. */
const lineWith = (out, ...parts) => out.split('\n').find((l) => parts.every((p) => l.includes(p))) ?? null;

const dump = (r) => r.out.slice(0, 1500);

/** A failure that exits `status`, prints nothing on stdout, and prints one plain line on stderr with no stack frame. */
const plainFailure = (r, status, what) => {
  assert.equal(r.status, status, `${what} must exit ${status}\n${dump(r)}`);
  assert.equal(r.stdout.trim(), '', `${what} must print nothing on stdout\n${dump(r)}`);
  const err = stderrOf(r).trim();
  assert.notEqual(err, '', `${what} must print a message on stderr\n${dump(r)}`);
  assert.equal(err.split('\n').length, 1, `${what} must print one plain stderr line, not a trace\n${dump(r)}`);
  assert.doesNotMatch(err, /^\s*at\s/m, `${what} must print no stack frame\n${dump(r)}`);
};

/** Sets `codeExtensions` in the scratch copy's map.config.json. The fixture keeps `["ts"]`. */
const withExtensions = (dir, exts) => {
  const p = join(dir, 'map.config.json');
  const cfg = JSON.parse(readFileSync(p, 'utf8'));
  writeFileSync(p, `${JSON.stringify({ ...cfg, codeExtensions: exts }, null, 2)}\n`);
  return dir;
};

/** A scratch copy with one more area, `store`: a code file `src/store.ts`, and a Tables row that names `public.notes`. */
const tablesRepo = () => {
  const dir = scratchRepo();
  writeFileSync(join(dir, 'src', 'store.ts'), 'export const store: string[] = [];\n');
  writeFileSync(join(dir, 'docs', 'map', 'store.md'), [
    '# Store', '', '## Code files', '',
    '- `src/store.ts` — Holds the store of the fixture.', '',
    '## Tables', '',
    '- `public.notes` — One row for each saved note.', '',
  ].join('\n'));
  gitIn(dir, 'add', '-N', '.');
  return dir;
};

test('1. a file path prints its area id', () => {
  const r = show(['src/home.ts']);
  // The scope first: the file must be found, or the area id holds for the wrong reason.
  assert.equal(r.status, 0, `a file with a map line must exit 0\n${dump(r)}`);
  assert.match(r.stdout, /\bcore\b/, `the output must print the area id core\n${dump(r)}`);
});

test('2. a file path prints its map line sentence', () => {
  const r = show(['src/home.ts']);
  assert.equal(r.status, 0, `a file with a map line must exit 0\n${dump(r)}`);
  assert.ok(r.stdout.includes(HOME_LINE), `the output must print the map line sentence of src/home.ts\n${dump(r)}`);
});

test('3. a file path prints its fact line', () => {
  const r = show(['src/home.ts']);
  assert.equal(r.status, 0, `a file with a map line must exit 0\n${dump(r)}`);
  assert.ok(r.stdout.includes(HOME_FACT), `the output must print the fact line of src/home.ts\n${dump(r)}`);
});

test('3b. a .py file is no map line while codeExtensions is ts, so its value fact does not print', () => {
  const dir = scratchRepo();
  // The scope first: a ts file must print, so the command reads the map.
  const ts = show(['src/home.ts'], dir);
  assert.equal(ts.status, 0, `a ts file with a map line must exit 0\n${dump(ts)}`);
  assert.ok(ts.stdout.includes(HOME_LINE), `the ts file must print its map line\n${dump(ts)}`);
  const py = show(['src/retry.py'], dir);
  assert.equal(py.status, 1, `src/retry.py is not a code file under ["ts"], so it is no map line and must exit 1\n${dump(py)}`);
  assert.equal(stderrOf(py).trim(), 'no map line for src/retry.py', 'stderr must hold one line: no map line for src/retry.py');
  assert.equal(py.stdout.trim(), '', 'nothing prints on stdout');
});

test('3c. with codeExtensions that name py, a .py file prints its map line and its value fact', () => {
  const dir = withExtensions(scratchRepo(), PY_EXTS);
  const r = show(['src/retry.py'], dir);
  assert.equal(r.status, 0, `a .py file that the config names must exit 0\n${dump(r)}`);
  assert.ok(r.stdout.includes('Holds the retry wait.'), `the output must print the map line of src/retry.py\n${dump(r)}`);
  assert.ok(r.stdout.includes(RETRY_FACT), `the output must print the value fact line of src/retry.py\n${dump(r)}`);
});

test('4. a file path prints the Homes line that cites it', () => {
  const r = show(['src/home.ts']);
  assert.equal(r.status, 0, `a file with a map line must exit 0\n${dump(r)}`);
  assert.ok(r.stdout.includes('homeTitle'), `the output must print the Homes line that cites src/home.ts (symbol homeTitle)\n${dump(r)}`);
});

test('4b. a file that no Homes line cites prints no Homes line', () => {
  const r = show(['src/screens.ts']);
  // The scope first: the file's own map line must print, or "no Homes line" holds for a command that printed nothing.
  assert.equal(r.status, 0, `a file with a map line must exit 0\n${dump(r)}`);
  assert.ok(r.stdout.includes(SCREENS_LINE), `the output must print the map line of src/screens.ts\n${dump(r)}`);
  for (const cite of ['homeTitle', 'src/notes.ts:notes', 'RETRY_WAIT_S']) {
    assert.ok(!r.stdout.includes(cite), `src/screens.ts has no Homes line, so the output must not print ${cite}\n${dump(r)}`);
  }
});

test('4c. a file cited by a Homes line prints that line', () => {
  const r = show(['src/notes.ts']);
  assert.equal(r.status, 0, `a file with a map line must exit 0\n${dump(r)}`);
  assert.match(r.stdout, /src\/notes\.ts:notes\b/, `the output must print the Homes line that cites src/notes.ts:notes\n${dump(r)}`);
});

test('5. a file path prints the trace step that names it', () => {
  const r = show(['src/home.ts']);
  assert.equal(r.status, 0, `a file with a map line must exit 0\n${dump(r)}`);
  assert.ok(r.stdout.includes(HOME_STEP), `the output must print the trace step of src/home.ts in docs/map/traces/home.md\n${dump(r)}`);
});

test('5b. a file that is a later step of a trace prints that step', () => {
  const r = show(['src/notes.ts']);
  assert.equal(r.status, 0, `a file with a map line must exit 0\n${dump(r)}`);
  assert.ok(r.stdout.includes(NOTES_STEP), `the output must print step 2 of the trace, which names src/notes.ts\n${dump(r)}`);
});

test('6. a map line sentence keeps its // and # marks whole', () => {
  const r = show(['src/notes.ts']);
  assert.equal(r.status, 0, `a file with a map line must exit 0\n${dump(r)}`);
  assert.ok(r.stdout.includes("Each note's text keeps any"), `the output must print the whole sentence of src/notes.ts\n${dump(r)}`);
  assert.match(r.stdout, /\/\/`?\s+or\s+`?#/, `the // and # marks of the sentence must survive\n${dump(r)}`);
});

test('7. a file with no fact line, Homes line or trace step prints its map line and exits 0', () => {
  const r = show(['src/screens.ts']);
  assert.equal(r.status, 0, `a file with no fact line, Homes line or trace step must still exit 0\n${dump(r)}`);
  assert.ok(r.stdout.includes(SCREENS_LINE), `the output must print the map line of src/screens.ts\n${dump(r)}`);
  assert.equal(stderrOf(r).trim(), '', 'a file with a map line prints nothing on stderr');
});

test('8. a path with a ./ prefix resolves to the same file', () => {
  const dir = scratchRepo();
  const plain = show(['src/home.ts'], dir);
  // The scope first: the plain path must resolve, or the ./ form proves nothing.
  assert.equal(plain.status, 0, `the plain path must exit 0\n${dump(plain)}`);
  assert.ok(plain.stdout.includes(HOME_LINE), `the plain path must print the map line\n${dump(plain)}`);
  const dotted = show(['./src/home.ts'], dir);
  assert.equal(dotted.status, 0, `a path with a ./ prefix must exit 0\n${dump(dotted)}`);
  assert.ok(dotted.stdout.includes(HOME_LINE), `a path with a ./ prefix must print the map line of src/home.ts\n${dump(dotted)}`);
});

test('9. a path with a Windows separator resolves to the same file', () => {
  const dir = scratchRepo();
  const plain = show(['src/home.ts'], dir);
  // The scope first: the forward-slash path must resolve, or the backslash form proves nothing.
  assert.equal(plain.status, 0, `the plain path must exit 0\n${dump(plain)}`);
  assert.ok(plain.stdout.includes(HOME_LINE), `the plain path must print the map line\n${dump(plain)}`);
  const back = show(['src\\home.ts'], dir);
  assert.equal(back.status, 0, `a path with a \\ separator must exit 0\n${dump(back)}`);
  assert.ok(back.stdout.includes(HOME_LINE), `a path with a \\ separator must print the map line of src/home.ts\n${dump(back)}`);
});

test('10. run through the install link to the skill folder, a file path still resolves', () => {
  needFile(REL);
  const script = join(junction(SKILL), 'scripts', 'map-show.mjs');
  const r = run([script, 'src/home.ts'], scratchRepo());
  assert.equal(r.status, 0, `the command run through the install link must exit 0\n${dump(r)}`);
  assert.ok(r.stdout.includes(HOME_LINE), `the command run through the install link must print the map line\n${dump(r)}`);
});

test('11. an area id prints the map lines of its code files, and none for a file the config does not name', () => {
  const r = show(['core']);
  // The scope first: each code file's map line must print, or the absence below holds for a command that printed nothing.
  assert.equal(r.status, 0, `an area id must exit 0\n${dump(r)}`);
  for (const [path, sentence] of TS_LINES) {
    assert.ok(lineWith(r.stdout, path, sentence), `the area core must print the map line of ${path}\n${dump(r)}`);
  }
  for (const [path] of OTHER_LINES) {
    assert.ok(!r.stdout.includes(path), `${path} is not a code file under ["ts"], so the area must not print it\n${dump(r)}`);
  }
});

test('11b. an area id prints one output line for each code map line', () => {
  const r = show(['core']);
  // The scope first: every code map line must print, or the count holds for a command that printed too little.
  assert.equal(r.status, 0, `an area id must exit 0\n${dump(r)}`);
  for (const [path, sentence] of TS_LINES) {
    assert.ok(lineWith(r.stdout, path, sentence), `the area core must print the map line of ${path}\n${dump(r)}`);
  }
  const lines = r.stdout.split('\n').filter((l) => ALL_LINES.some(([path]) => l.includes(path)));
  assert.equal(lines.length, TS_LINES.length, `the area must print one line for each of its ${TS_LINES.length} code map lines\n${dump(r)}`);
});

test('11c. with codeExtensions that name py and json, the area id prints all six map lines', () => {
  const dir = withExtensions(scratchRepo(), PY_EXTS);
  const r = show(['core'], dir);
  assert.equal(r.status, 0, `an area id must exit 0\n${dump(r)}`);
  for (const [path, sentence] of ALL_LINES) {
    assert.ok(lineWith(r.stdout, path, sentence), `the area core must print the map line of ${path} once its extension is named\n${dump(r)}`);
  }
});

test('12. an area id prints no fact line', () => {
  const r = show(['core']);
  // The scope first: a map line must print, or "no fact line" holds for a command that printed nothing.
  assert.equal(r.status, 0, `an area id must exit 0\n${dump(r)}`);
  assert.ok(lineWith(r.stdout, 'src/home.ts', HOME_LINE), `the area core must print the map line of src/home.ts\n${dump(r)}`);
  for (const fact of AREA_FACTS) {
    assert.ok(!r.stdout.includes(fact), `an area id prints map lines only, but the output holds the fact line: ${fact}\n${dump(r)}`);
  }
});

test('13. a folder prefix prints the code map lines under it, and none for a file the config does not name', () => {
  const r = show(['src/']);
  // The scope first: the folder's code lines must print, or the absence below holds for a command that printed nothing.
  assert.equal(r.status, 0, `a folder prefix with map lines must exit 0\n${dump(r)}`);
  for (const [path, sentence] of TS_LINES.filter(([path]) => path.startsWith('src/'))) {
    assert.ok(lineWith(r.stdout, path, sentence), `the folder src/ must print the map line of ${path}\n${dump(r)}`);
  }
  for (const path of ['src/retry.py', 'src/caller.py']) {
    assert.ok(!r.stdout.includes(path), `${path} is not a code file under ["ts"], so the folder must not print it\n${dump(r)}`);
  }
});

test('14. a folder prefix prints no map line outside it', () => {
  const dir = withExtensions(scratchRepo(), PY_EXTS);
  // The scope first: config.json must be a map line under this config, or its absence holds for a line never read.
  const outside = show(['config.json'], dir);
  assert.equal(outside.status, 0, `config.json must be a map line once json is named\n${dump(outside)}`);
  const r = show(['src/'], dir);
  assert.equal(r.status, 0, `a folder prefix with map lines must exit 0\n${dump(r)}`);
  assert.ok(lineWith(r.stdout, 'src/home.ts', HOME_LINE), `the folder src/ must print the map line of src/home.ts\n${dump(r)}`);
  assert.ok(!r.stdout.includes('Holds the retry settings as JSON.'), `config.json is outside src/, so the output must not print its map line\n${dump(r)}`);
});

test('15. a folder prefix over a 250-line area prints all 250 map lines', () => {
  const dir = scratchRepo();
  const N = 250;
  mkdirSync(join(dir, 'src', 'big'));
  const rows = [];
  for (let i = 0; i < N; i++) {
    const n = String(i).padStart(3, '0');
    writeFileSync(join(dir, 'src', 'big', `f${n}.ts`), 'export {};\n');
    rows.push('- `src/big/f' + n + '.ts` — Generated line ' + n + '.');
  }
  writeFileSync(join(dir, 'docs', 'map', 'big.md'), `# Big\n\n## Code files\n\n${rows.join('\n')}\n`);
  gitIn(dir, 'add', '-N', '.');
  const r = show(['src/big/'], dir);
  assert.equal(r.status, 0, `a folder prefix with ${N} map lines must exit 0\n${dump(r)}`);
  const printed = r.stdout.split('\n').filter((l) => l.includes('src/big/f'));
  assert.equal(printed.length, N, `the folder must print one line for each of its ${N} map lines, with no cap\n${dump(r)}`);
});

test('16. a folder prefix that no map line starts with exits 1, with one plain stderr line', () => {
  const r = show(['src/none/']);
  assert.equal(r.status, 1, `nothing found must exit 1\n${dump(r)}`);
  assert.equal(r.stdout.trim(), '', 'nothing found prints nothing on stdout');
  assert.equal(stderrOf(r).trim(), 'no map line for src/none/', 'stderr must hold one line: no map line for src/none/');
});

test('17. a tracked file that no map line names exits 1, with one plain stderr line', () => {
  const r = show(['db/migrations/001_notes.sql']);
  assert.equal(r.status, 1, `nothing found must exit 1\n${dump(r)}`);
  assert.equal(r.stdout.trim(), '', 'nothing found prints nothing on stdout');
  assert.equal(stderrOf(r).trim(), 'no map line for db/migrations/001_notes.sql', 'stderr must hold one line, with no stack trace');
});

test('18. with no arg the command prints a usage line and exits 2', () => {
  const r = show([]);
  assert.equal(r.status, 2, `no arg must exit 2\n${dump(r)}`);
  assert.match(r.out, /usage/i, `the output must hold a usage line\n${dump(r)}`);
});

test('19. the command reads each map line that map-check reads, whatever its bullet', async () => {
  needFile(REL);
  const dir = scratchRepo();
  writeFileSync(join(dir, 'src', 'star.ts'), 'export const STAR = 1;\n');
  writeFileSync(join(dir, 'src', 'plus.ts'), 'export const PLUS = 2;\n');
  const area = [
    '# Mixed', '', '## Code files', '',
    '* `src/star.ts` — Star bullet sentence.',
    '  * The star holds one. — `STAR = 1`',
    '+ `src/plus.ts` — Plus bullet sentence.',
    '',
  ].join('\n');
  writeFileSync(join(dir, 'docs', 'map', 'mixed.md'), area);
  gitIn(dir, 'add', '-N', '.');
  // The scope first: map-check must read both paths from this text, or the case tests nothing about its parser.
  const { mapCodePaths } = await import(pathToFileURL(CHECK).href);
  assert.deepEqual(mapCodePaths(area, /\.ts$/), ['src/star.ts', 'src/plus.ts'], 'map-check must read both bullets of mixed.md');
  const star = show(['src/star.ts'], dir);
  assert.equal(star.status, 0, `a * bullet line must resolve\n${dump(star)}`);
  assert.ok(star.stdout.includes('Star bullet sentence.'), `the output must print the * bullet map line\n${dump(star)}`);
  assert.ok(star.stdout.includes('The star holds one.'), `the output must print the fact line under the * bullet\n${dump(star)}`);
  const plus = show(['src/plus.ts'], dir);
  assert.equal(plus.status, 0, `a + bullet line must resolve\n${dump(plus)}`);
  assert.ok(plus.stdout.includes('Plus bullet sentence.'), `the output must print the + bullet map line\n${dump(plus)}`);
});

test('20. a Tables row is no map line, so an area id never prints it', () => {
  const dir = tablesRepo();
  const r = show(['store'], dir);
  // The scope first: the area's code file must print, or the absence of the Tables row holds for an empty area.
  assert.equal(r.status, 0, `an area id must exit 0\n${dump(r)}`);
  assert.ok(lineWith(r.stdout, 'src/store.ts', 'Holds the store of the fixture.'), `the area store must print the map line of src/store.ts\n${dump(r)}`);
  assert.ok(!r.stdout.includes('public.notes'), `public.notes is a Tables row, not a map line, so the area must not print it\n${dump(r)}`);
});

test('20b. a Tables row name is no map line for a path arg', () => {
  const dir = tablesRepo();
  const scope = show(['src/store.ts'], dir);
  // The scope first: the code file's map line must resolve, or "no map line" holds for a command that resolves nothing.
  assert.equal(scope.status, 0, `a file with a map line must exit 0\n${dump(scope)}`);
  assert.ok(scope.stdout.includes('Holds the store of the fixture.'), `the output must print the map line of src/store.ts\n${dump(scope)}`);
  const r = show(['public.notes'], dir);
  assert.equal(r.status, 1, `public.notes names a Tables row, so it is no map line and must exit 1\n${dump(r)}`);
  assert.equal(stderrOf(r).trim(), 'no map line for public.notes', 'stderr must hold one line: no map line for public.notes');
});

test('21. a map page the command cannot read exits 3, with one plain stderr line and no stack trace', () => {
  const dir = scratchRepo();
  // The scope first: with every page on disk, the file is found.
  const ok = show(['src/home.ts'], dir);
  assert.equal(ok.status, 0, `a file with a map line must exit 0 while every page is on disk\n${dump(ok)}`);
  rmSync(join(dir, 'docs', 'map', 'core.md'));
  plainFailure(show(['src/home.ts'], dir), 3, 'an area page that is tracked but missing from disk');
});

test('21b. a trace page the command cannot read exits 3, the same as an area page', () => {
  const dir = scratchRepo();
  // The scope first: with every page on disk, the trace step prints, so the trace page is read.
  const ok = show(['src/home.ts'], dir);
  assert.equal(ok.status, 0, `a file with a map line must exit 0 while every page is on disk\n${dump(ok)}`);
  assert.ok(ok.stdout.includes(HOME_STEP), `the trace step must print while the trace page is on disk\n${dump(ok)}`);
  rmSync(join(dir, 'docs', 'map', 'traces', 'home.md'));
  plainFailure(show(['src/home.ts'], dir), 3, 'a trace page that is tracked but missing from disk');
});

test('22. an absolute path under the root prints the same output as the relative path', () => {
  const dir = scratchRepo();
  const plain = show(['src/home.ts'], dir);
  // The scope first: the relative path must resolve, or equal output proves nothing.
  assert.equal(plain.status, 0, `the relative path must exit 0\n${dump(plain)}`);
  assert.ok(plain.stdout.includes(HOME_LINE), `the relative path must print the map line\n${dump(plain)}`);
  // The root as the command sees it: its real path, which `process.cwd()` returns.
  const abs = show([join(realpathSync.native(dir), 'src', 'home.ts')], dir);
  assert.equal(abs.status, 0, `an absolute path under the root must exit 0\n${dump(abs)}`);
  assert.equal(abs.stdout, plain.stdout, `an absolute path under the root must print the same output as src/home.ts\n${dump(abs)}`);
});

test('22b. an absolute path outside the root prints no map line and exits 1', () => {
  const dir = scratchRepo();
  // The scope first: the relative path must resolve, or "no map line" holds for a command that resolves nothing.
  const inside = show(['src/home.ts'], dir);
  assert.equal(inside.status, 0, `the relative path must exit 0\n${dump(inside)}`);
  assert.ok(inside.stdout.includes(HOME_LINE), `the relative path must print the map line\n${dump(inside)}`);
  const outside = join(dirname(realpathSync.native(dir)), 'outside', 'src', 'home.ts');
  const r = show([outside], dir);
  assert.equal(r.status, 1, `a path outside the root must exit 1\n${dump(r)}`);
  assert.equal(r.stdout.trim(), '', 'a path outside the root prints nothing on stdout');
  assert.equal(stderrOf(r).trim(), `no map line for ${outside}`, `stderr must hold one line: no map line for ${outside}`);
});

test('22c. an absolute path through a symlink to the root prints the same output as the relative path', () => {
  const dir = scratchRepo();
  const plain = show(['src/home.ts'], dir);
  // The scope first: the relative path must resolve, or equal output proves nothing.
  assert.equal(plain.status, 0, `the relative path must exit 0\n${dump(plain)}`);
  assert.ok(plain.stdout.includes(HOME_LINE), `the relative path must print the map line\n${dump(plain)}`);
  // The link must reach the root, and its typed path must differ from its real path (checked by `junction`).
  const link = junction(dir);
  const viaLink = `${link}/src/home.ts`;
  // The cwd is the link. The command sees its real root, and the arg names the link.
  const fromLink = show([viaLink], link);
  assert.equal(fromLink.status, 0, `with the cwd at a symlink to the root, an absolute path through that link must exit 0\n${dump(fromLink)}`);
  assert.equal(fromLink.stdout, plain.stdout, `with the cwd at a symlink to the root, an absolute path through that link must print the same output as src/home.ts\n${dump(fromLink)}`);
  // The cwd is the real root. The arg names the link.
  const toLink = show([viaLink], dir);
  assert.equal(toLink.status, 0, `with the cwd at the real root, an absolute path through a symlink to the root must exit 0\n${dump(toLink)}`);
  assert.equal(toLink.stdout, plain.stdout, `with the cwd at the real root, an absolute path through a symlink to the root must print the same output as src/home.ts\n${dump(toLink)}`);
});

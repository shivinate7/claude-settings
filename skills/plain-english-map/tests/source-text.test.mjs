// The source-text readers of the skill, and the readers that pass them a file name.
//
// `scripts/lib/source-text.mjs` holds one scanner behind four readers: `blankComments`, `blankCommentsAndStrings`,
// `stripComments` and `stripCommentsAndStrings`. Each takes the file name as its second argument. Only a name that ends
// in `.tsx` or `.jsx` reads JSX: the text between a tag's `>` and the next `<` or `{` is text, so a quote, a `//` or a
// `/*` in it opens nothing. A `.ts` or `.mjs` name, and a call with no name, reads no JSX.
// The cases are the three shapes of the rule building-scanner-respects-strings (a comment opener inside a string, a
// multi-line template literal, a lone quote in text) and a generic arrow, which is no JSX tag.
// The JSX cases sit here, beside the one shared scanner, so a project that uses this skill needs no copy of them.
//
// Run from this folder: `node --test source-text.test.mjs`. No case needs the `typescript` package.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { blankComments, blankCommentsAndStrings, stripComments, stripCommentsAndStrings } from '../scripts/lib/source-text.mjs';
import { importEntries, importTargets } from '../scripts/lib/import-reader.mjs';
import { plainWordsNotes, seamHasCallSite, stageSitesOf } from '../scripts/map-check.mjs';
import { lookAlikes } from '../scripts/map-picture.mjs';

const READERS = { blankComments, blankCommentsAndStrings, stripComments, stripCommentsAndStrings };
// These two blank the text of a string. The other two keep it as written.
const BLANKS_STRINGS = new Set(['blankCommentsAndStrings', 'stripCommentsAndStrings']);
const JSX_FILES = ['x.tsx', 'x.jsx'];
const PLAIN_FILES = [undefined, 'x.ts', 'x.mjs'];

// ---- A lone quote in JSX text opens no string. A file that is read as JSX keeps the code after it, on the line and below.
// Without JSX reading, the apostrophe opens a string that runs to the end of the line. `blankCommentsAndStrings`
// and `stripCommentsAndStrings` then blank `keep()`. `blankComments` and `stripComments` keep the string text, so the comment
// in it stays a comment that is not blanked.
for (const [name, read] of Object.entries(READERS)) {
  for (const file of JSX_FILES) {
    test(`JSX: ${name}, ${file}: an apostrophe in JSX text hides no code and no comment after it on its line`, () => {
      const out = read("const el = <p>Don't</p>; keep(); // GATED\nconst after = 1;\n", file);
      assert.doesNotMatch(out, /GATED/, 'the comment after the element was kept as code');
      assert.match(out, /keep\(\);/, 'the code after the apostrophe was blanked');
      assert.match(out, /const after = 1;\n$/, 'the code on the next line was lost');
    });

    test(`JSX: ${name}, ${file}: an inch mark in JSX text hides nothing, and the text stays as written`, () => {
      const out = read('const el = <p>5" pipe</p>; keep(); // GATED\n', file);
      assert.doesNotMatch(out, /GATED/);
      assert.match(out, /keep\(\);/);
      assert.ok(out.includes('5" pipe'), 'JSX text was blanked');
    });

    test(`JSX: ${name}, ${file}: a quote pair around an expression in JSX text keeps the expression, and the code after it`, () => {
      const out = read('export const B = () => <p>"{side.words}"</p>; export const g = () => run();\n', file);
      assert.match(out, /\{side\.words\}/, 'the pair of quotes blanked the expression between them');
      assert.match(out, /run\(\);\n$/, 'the pair of quotes blanked the code after it');
    });
  }
}

// A `//` or a `/*` in JSX text is text. Without JSX reading, the `//` blanks the rest of the line, and the `/*` opens a block that runs on.
for (const [name, read] of Object.entries(READERS)) {
  for (const file of JSX_FILES) {
    test(`JSX: ${name}, ${file}: a comment opener in JSX text is text`, () => {
      const line = 'const el = <p>// not a comment</p>; keep();';
      assert.equal(read(`${line}\n`, file).includes('// not a comment</p>; keep();'), true, 'a `//` in JSX text was read as a comment');
      const block = read('const el = <p>/* not a comment</p>; keep();\nconst s = "*/";\n', file);
      assert.match(block, /keep\(\);\nconst s = /, 'a `/*` in JSX text opened a block comment');
    });
  }
}

test('JSX: a real comment between JSX parts is still blanked, in a `{ }` and in a tag', () => {
  for (const file of JSX_FILES) {
    const src = 'const el = <p {/* hidden(1) */...p} /* hidden(2) */ a="b">{/* hidden(3) */}x</p>;\nkeep(el);\n';
    const out = blankComments(src, file);
    assert.doesNotMatch(out, /hidden/, `${file}: a comment was kept`);
    assert.equal(out.length, src.length, `${file}: the length moved`);
    assert.match(out, /keep\(el\);\n$/);
  }
});

test('JSX: a lone quote in a JSX attribute string, and a `//` in one, hide nothing', () => {
  for (const file of JSX_FILES) {
    for (const src of ['const el = <a title="Don\'t" href="/x">y</a>; keep(el);', 'const el = <a href="http://x">y</a>; keep(el);']) {
      for (const [name, read] of Object.entries(READERS)) assert.match(read(src, file), /keep\(el\);$/, `${name}, ${file}: ${src}`);
    }
  }
});

// A `<` after `<T extends X>(a) =>` is a generic, so the JSX element after it still holds its lone quote as text.
test('JSX: a generic arrow in a `.tsx` file is no tag, and a JSX element after it still holds its lone quote as text', () => {
  const src = ['export const f = <T extends X>(a: T) => a;', '// GATED', "export const el = <p>Don't</p>; keep();", 'export const s = "</b>";', ''].join('\n');
  for (const [name, read] of Object.entries(READERS)) {
    const out = read(src, 'x.tsx');
    assert.doesNotMatch(out, /GATED/, `${name}: the comment after the generic was kept as code`);
    assert.match(out, /keep\(\);\nexport const s = /, `${name}: the lone quote in the JSX text blanked the code after it`);
  }
});

// Scope guard: the generic rule must not read a tag with a spaced attribute (`<a b = "1">`) as a generic.
test('JSX: a tag with a spaced attribute is still a tag, so its lone quote is text', () => {
  const src = ['export const el = <a b = "1">Don\'t</a>;', '// GATED', 'const keep = 1;', ''].join('\n');
  for (const [name, read] of Object.entries(READERS)) {
    const out = read(src, 'x.tsx');
    assert.ok(out.includes("Don't</a>;"), `${name}: the lone quote in the JSX text was read as a string`);
    assert.doesNotMatch(out, /GATED/, `${name}: the comment after the element was kept as code`);
    assert.match(out, /const keep = 1;\n$/);
  }
});

// A file that leaves a tag open at its end held no JSX: its `<` was a type assertion, as in `<T>x`. It is read again with no JSX.
test('JSX: a `.tsx` file that ends with a tag open is read again with no JSX, so a type assertion hides no comment', () => {
  const src = 'const a = <T>x;\n// GATED\nconst keep = 1;\n';
  for (const [name, read] of Object.entries(READERS)) {
    const out = read(src, 'x.tsx');
    assert.doesNotMatch(out, /GATED/, `${name}: the comment after the assertion was kept as code`);
    assert.match(out, /const keep = 1;\n$/);
  }
});

// ---- Today's behaviour stays for a name with no JSX, and for a call with no name: `<p>Don't</p>` opens a string.
// These pin the other half of the file-name switch: no JSX reading without a `.tsx` or `.jsx` name.
test('no JSX: a `.ts` name, a `.mjs` name and no name read the apostrophe as a string to the end of the line', () => {
  const src = "const el = <p>Don't</p>; keep(); // GATED\nconst after = 1;\n";
  for (const file of PLAIN_FILES) {
    // The string text is blanked, so `keep()` goes with it. The next line is whole.
    const swallowed = 't</p>; keep(); // GATED';
    assert.equal(blankCommentsAndStrings(src, file), `const el = <p>Don'${' '.repeat(swallowed.length)}\nconst after = 1;\n`, `blankCommentsAndStrings, ${file}`);
    // The string text is kept, and the comment inside it is part of the string, so it is not blanked.
    assert.equal(blankComments(src, file), src, `blankComments, ${file}`);
  }
});

test('no JSX: a pair of quotes in JSX text is a string in a `.ts` file, a `.mjs` file and with no name', () => {
  const src = 'export const B = () => <p>"{side.words}"</p>; export const g = () => run();\n';
  for (const file of PLAIN_FILES) {
    for (const name of ['blankCommentsAndStrings', 'stripCommentsAndStrings']) {
      const out = READERS[name](src, file);
      assert.doesNotMatch(out, /side\.words/, `${name}, ${file}: JSX was read, so the expression between the quotes was kept`);
      assert.match(out, /run\(\);\n$/, `${name}, ${file}: the code after the quotes was lost`);
    }
  }
});

// ---- A generic arrow is no JSX tag, in every name. A `.ts` name reads no JSX, and the reader of a `.tsx`
// name must not read a generic as a tag. A tag read there leaves the file open at its end, and one stray `</b>` after it closes the
// file again, so the comment between stayed unblanked.
// `= <T>(x) => x` is no valid `.tsx`, so only the `.ts` file holds it.
const GENERICS = [
  ['`= <T extends X>(`', 'export const f = <T extends X>(a: T) => a;', ['x.ts', 'x.tsx']],
  ['`= <T,>(`', 'export const f = <T,>(a: T) => a;', ['x.ts', 'x.tsx']],
  ['`: <T>(x) => T`', 'export const g: <T>(a: T) => T = (a) => a;', ['x.ts', 'x.tsx']],
  ['`= <T>(x) => x`', 'export const f = <T>(a: T) => a;', ['x.ts']],
  ['`= <T = unknown>(`', 'export const f = <T = unknown>(a: T) => a;', ['x.ts', 'x.tsx']],
  ['`= <T = unknown,>(`', 'export const f = <T = unknown,>(a: T) => a;', ['x.ts', 'x.tsx']],
  ['`= <const T,>(`', 'export const f = <const T,>(a: T) => a;', ['x.ts', 'x.tsx']],
  ['`= <const T extends X>(`', 'export const f = <const T extends X>(a: T) => a;', ['x.ts', 'x.tsx']],
];
const AFTER = [
  ['no stray tag after it', ['// GATED']],
  ['a stray `</b>` in a string after it', ['// GATED', 'const s = "</b>";']],
  ['a comment that names `</p>` after it', ['// GATED names </p>']],
];
for (const [what, decl, files] of GENERICS) {
  for (const file of files) {
    for (const [after, lines] of AFTER) {
      test(`generic: ${what} is no tag in ${file}, so the comment after it is blanked, ${after}`, () => {
        const src = [decl, ...lines, 'const keep = 1;', ''].join('\n');
        for (const [name, read] of Object.entries(READERS)) {
          const out = read(src, file);
          assert.ok(out.includes(decl), `${name}: the generic was changed`);
          assert.doesNotMatch(out, /GATED/, `${name}: the comment after the generic was kept as code`);
          assert.match(out, /const keep = 1;\n$/, `${name}: the code after the generic was lost`);
          if (lines.length > 1) assert.ok(out.includes(BLANKS_STRINGS.has(name) ? 'const s = "    ";' : 'const s = "</b>";'), `${name}: the string after the generic was changed`);
        }
      });
    }
  }
}

// ---- A comment opener inside a string, and a multi-line template literal, in every name. JSX reading must not change either.
for (const [what, src] of [
  ['`//` inside a string', 'const url = "https://x//y"; keep(url);'],
  ['`/*` in one string and `*/` in a later one', "const a = '/*'; keep(); const b = \"*/\";"],
  ['`#` inside a string', 'const s = "# not a comment"; keep(s);'],
  ['a private name `#x`', 'class A { #x = 1; get() { return this.#x; } }\nkeep(new A());'],
  ['`//` inside a template literal', 'const t = `http://x`; keep(t);'],
  ['`//` and `/*` in a template literal with a line break', 'const t = `a //\nb /*\nc`; keep(t); const s = "*/";'],
]) {
  for (const file of [...PLAIN_FILES, ...JSX_FILES]) {
    test(`opener in a string: ${what}, ${file}: no reader takes it for a comment, and the code after it stays`, () => {
      assert.equal(blankComments(src, file), src, 'something was read as a comment');
      assert.equal(stripComments(src, file), src, 'something was read as a comment');
      for (const [name, read] of Object.entries(READERS)) assert.match(read(src, file), /keep\(/, `${name}: the code after the opener was lost`);
    });
  }
}

test('opener in a string: a multi-line template literal holds its words as text, and the code after it stays', () => {
  // The lines of the template hold a comment opener and a lone quote. None of them ends the template or opens a comment.
  const src = "const t = `line one\nclassifyIntent(x) // not a comment\nDon't /* not a block\n\"q\"`;\nplanUnsureTurn();\nconst s = \"*/\";";
  for (const file of [...PLAIN_FILES, ...JSX_FILES]) {
    for (const [name, read] of Object.entries(READERS)) {
      const out = read(src, file);
      assert.equal(/classifyIntent/.test(out), !BLANKS_STRINGS.has(name), `${name}, ${file}: the template text was ${BLANKS_STRINGS.has(name) ? 'kept' : 'blanked'}`);
      assert.match(out, BLANKS_STRINGS.has(name) ? /planUnsureTurn\(\);\nconst s = " {2}";$/ : /planUnsureTurn\(\);\nconst s = "\*\/";$/, `${name}, ${file}: the code after the template was lost`);
    }
  }
});

test('opener in a string: a lone quote in a line comment and in a block comment hides no code after it', () => {
  for (const file of [...PLAIN_FILES, ...JSX_FILES]) {
    for (const [name, read] of Object.entries(READERS)) {
      assert.match(read("// don't\nkeep();", file), /\nkeep\(\);$/, `${name}, ${file}`);
      assert.match(read("/* it's */ keep();", file), /keep\(\);$/, `${name}, ${file}`);
    }
  }
});

// ---- The import reader passes the file name to the scanner. `importTargets` names the file it reads, and `importEntries`
// takes it in its options.
const TRACKED = new Set(['src/a.tsx', 'src/a.ts', 'src/x.ts', 'src/y.ts']);

test('import reader: importTargets finds an import after an apostrophe in JSX text, on the same line', () => {
  const src = "export const Q = () => <p>Don't</p>; const lazy = () => import('./x.ts');\n";
  assert.deepEqual(importTargets('src/a.tsx', src, TRACKED), ['src/x.ts']);
  assert.deepEqual(importTargets('src/a.tsx', src, TRACKED, { types: false }), ['src/x.ts']);
});

test('import reader: importTargets finds an import below a `/*` or a lone backtick in JSX text', () => {
  // Without JSX, the `/*` opens a block comment and the backtick opens a template. Each runs on and hides the import.
  for (const text of ['/* not a comment', 'a ` b']) {
    const src = `export const A = () => <p>${text}</p>;\nimport { v } from './x.ts';\nconst s = "*/ \`";\n`;
    assert.deepEqual(importTargets('src/a.tsx', src, TRACKED), ['src/x.ts'], text);
  }
});

test('import reader: importTargets keeps the type filter in a `.tsx` file whose JSX text holds an apostrophe', () => {
  const src = "export const Q = () => <p>Don't</p>; import type { T } from './x.ts'; export const R = () => import('./y.ts');\n";
  assert.deepEqual(importTargets('src/a.tsx', src, TRACKED, { types: true }), ['src/x.ts', 'src/y.ts']);
  assert.deepEqual(importTargets('src/a.tsx', src, TRACKED, { types: false }), ['src/y.ts']);
});

// With the apostrophe on its own line, the string ends at the line break and the import below is read. JSX reading must keep this read.
test("import reader: importTargets finds an import below the line of an apostrophe in JSX text", () => {
  const src = "const el = <p>Don't</p>;\nimport { v } from './x.ts';\nconst f = <p>It's</p>;\n";
  assert.deepEqual(importTargets('src/a.tsx', src, TRACKED), ['src/x.ts']);
});

test('import reader: importEntries takes the file name in its options, and a `.ts` name or no name reads no JSX', () => {
  const src = "const el = <p>Don't</p>; const m = () => import('./x.ts');\n";
  for (const file of JSX_FILES) assert.deepEqual(importEntries(src, { file }).map((e) => e.spec), ['./x.ts'], file);
  for (const file of PLAIN_FILES) assert.deepEqual(importEntries(src, { file }), [], `${file}: today's read, the apostrophe opens a string`);
  assert.deepEqual(importEntries(src), [], 'no options');
});

test('import reader: a string and a comment are no import in a `.tsx` file, and a comment opener in a string hides the import after it', () => {
  const src = "// import { a } from './y.ts';\nconst s = \"import { b } from './y.ts'\"; const t = '/*'; const u = \"//\";\nimport { v } from './x.ts';\nconst w = '*/';\n";
  assert.deepEqual(importTargets('src/a.tsx', src, TRACKED), ['src/x.ts']);
  assert.deepEqual(importTargets('src/a.ts', src, TRACKED), ['src/x.ts']);
});

// ---- The readers in `scripts/` that pass the file name on. Each must read a `.tsx` name as JSX.
test('map-check: stageSitesOf finds a stage literal after an apostrophe in JSX text, only when it gets a `.tsx` name', () => {
  const stage = { variable: 'stage', callback: 'setStage' };
  const src = "export const V = () => <p>Don't</p>; stage = 'queued';\nsetStage('done');\n";
  assert.deepEqual(stageSitesOf(src, stage, 'w.tsx'), [{ step: 'queued', line: 1 }, { step: 'done', line: 2 }]);
  assert.deepEqual(stageSitesOf(src, stage, 'w.ts'), [{ step: 'done', line: 2 }], "a `.ts` name keeps today's read");
  assert.deepEqual(stageSitesOf(src, stage), [{ step: 'done', line: 2 }], "no name keeps today's read");
});

test('map-check: plainWordsNotes finds a note after an apostrophe in JSX text in a `.tsx` file, and not in a `.ts` file', () => {
  const src = "const el = <p>Don't</p>; // In plain words: it shows a note.\nconst keep = 1;\n";
  assert.deepEqual(plainWordsNotes({ 'a.tsx': src }), ['a.tsx:1']);
  assert.deepEqual(plainWordsNotes({ 'a.ts': src }), [], "a `.ts` name keeps today's read");
});

// The `/*` in JSX text opens no block comment, so the import and the `export` below it are read. Without JSX it hides them.
test('map-check: seamHasCallSite finds the import of the seam below a `/*` in JSX text in a `.tsx` caller', () => {
  const seam = 'src/services/seam.ts';
  const src = "export const Panel = () => <p>/* not a comment</p>;\nimport { metered } from '../services/seam.ts';\n";
  const sites = () => [{ line: 2 }];
  assert.equal(seamHasCallSite(seam, ['src/ui/Panel.tsx'], () => src, sites), true);
  assert.equal(seamHasCallSite(seam, ['src/ui/Panel.ts'], () => src, sites), false, "a `.ts` name keeps today's read");
});

test('map-picture: lookAlikes reads the exports below a `/*` in JSX text in a `.tsx` file', () => {
  const src = 'export const View = () => <p>/* not a comment</p>;\nexport const Shared = 1;\n';
  const node = (p) => ({ k: 'code', p, a: 'area', j: 0 });
  const read = (one, two) => lookAlikes({ nodes: [node(one), node(two)] }, { [one]: src, [two]: src }).names.map((n) => n.name);
  assert.deepEqual(read('src/a/One.tsx', 'src/b/Two.tsx'), ['Shared', 'View']);
  assert.deepEqual(read('src/a/One.ts', 'src/b/Two.ts'), ['View'], "a `.ts` name keeps today's read: the `/*` hides `Shared`");
});

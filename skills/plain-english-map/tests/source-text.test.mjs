// The source-text readers of the skill, and the four callers that name a file for them.
//
// `scripts/lib/source-text.mjs` holds four readers: `stripComments`, `blankComments`, `blankCommentsAndStrings` and
// `stripCommentsAndStrings`. Each takes the source and the file name. A name that ends in `.tsx` or `.jsx` reads JSX. Any other name,
// and a call with no name, reads no JSX. In JSX text a quote, a `//` and a `/` open nothing. JSX text is kept as written.
// The cases below were first written in q_max, for its own copy of the scanner. They need no q_max file.
//
// Each case runs on the readers it can tell apart, so a red case names its reader. A case that reads no JSX is a GUARD. It is green
// before the scanner reads JSX, and it stops a scanner that reads too much. Each guard says so in its title.
//
//   1. A lone quote in JSX text of a `.tsx` file opens no string, in all four readers: the comment after it on the line is a comment,
//      and the two readers that blank strings keep the brace of a condition and the code after it.
//   2. A read with no name, or a `.ts`, `.mjs` or `.js` name, reads no JSX (guard). A `.tsx` or `.jsx` name reads it.
//   3. `<Foo>` and a tag with a spaced attribute are tags in a `.tsx` file. A `//` or a `/` in JSX text is text.
//   4. A generic is no tag: `<T,>`, `<T extends X>`, `<T = unknown>`, `<const T,>` and the others (guard in `.ts`, and in `.tsx` with no
//      JSX after it). A JSX element after a generic in a `.tsx` file still holds its lone quote as text.
//   5. The three shapes of the scanner rule: a comment opener inside a string, a multi-line template literal, and a lone quote in text.
//   6. The callers pass the name: `plainWordsNotes`, `importTargets`, `stageSitesOf` and `lookAlikes` read a `.tsx` file as JSX and a
//      `.ts` file as none. The `.ts` case of each is a guard.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { blankComments, blankCommentsAndStrings, stripComments, stripCommentsAndStrings } from '../scripts/lib/source-text.mjs';
import { importTargets } from '../scripts/lib/import-reader.mjs';
import { plainWordsNotes, stageSitesOf } from '../scripts/map-check.mjs';
import { lookAlikes } from '../scripts/map-picture.mjs';

const READERS = { stripComments, blankComments, blankCommentsAndStrings, stripCommentsAndStrings };
// The two readers that blank the text of a string. A reader that counts brackets uses one of them.
const BLANKING = { blankCommentsAndStrings, stripCommentsAndStrings };
const blanks = (name) => name in BLANKING;
const TSX = 'x.tsx';

// ---- 1. A lone quote in JSX text of a .tsx file opens no string. ----
const QUOTES = [['an apostrophe', "Don't"], ['an inch mark', '5" pipe']];

for (const [name, read] of Object.entries(READERS)) {
  test(`${name}: in a .tsx file a lone quote in JSX text opens no string, so a comment after it on the line is a comment`, () => {
    // The scope first: the same line with no quote reads as a comment, so a kept comment below is the quote's fault.
    const control = read('export const el = <p>Do not</p>; run(); // GATED\nexport const keep = 1;\n', TSX);
    assert.doesNotMatch(control, /GATED/, 'the control line kept its comment');
    for (const [what, text] of QUOTES) {
      const out = read(`export const el = <p>${text}</p>; run(); // GATED\nexport const keep = 1;\n`, TSX);
      assert.ok(out.includes('run();'), `${what} in JSX text opened a string, so the code after it on the line was blanked`);
      assert.doesNotMatch(out, /GATED/, `${what} in JSX text opened a string, so the comment after it was kept as code`);
      assert.match(out, /export const keep = 1;\n$/, `${what} in JSX text hid the code on the next line`);
    }
  });
}

// A test that searches backward from a part for the `{` of its condition reads an ungated part as gated, when a lone quote in JSX
// text hides the `}` of the condition.
const openBefore = (code, needle) => {
  assert.ok(code.includes(needle), `the part ${needle} was lost from the text, so no brace count is true`);
  const head = code.slice(0, code.indexOf(needle));
  return head.split('{').length - head.split('}').length;
};
const gated = (text) => `export const A = () => (\n  <div>\n    {gate && <p>${text}</p>}\n    <Ungated />\n  </div>\n);\n`;

for (const [name, read] of Object.entries(BLANKING)) {
  for (const [what, text] of QUOTES) {
    test(`${name}: a lone quote in JSX text opens no string, so the condition around it still closes: ${what}`, () => {
      assert.equal(openBefore(read(gated('Do not'), TSX), '<Ungated'), 0, 'the control text left a brace open');
      assert.equal(openBefore(read(gated(text), TSX), '<Ungated'), 0, `${what} in JSX text hid the closing brace of the condition, so an ungated part reads as gated`);
    });
  }
  test(`${name}: an apostrophe in JSX text does not blank the code after it, on its line or on the next, and JSX text stays as written`, () => {
    const out = read("const el = <p>Don't</p>; runQueryTurn();\nkeep();", TSX);
    assert.match(out, /runQueryTurn\(\);\nkeep\(\);/, 'the code after the apostrophe was blanked');
    assert.ok(out.includes("<p>Don't</p>"), 'the JSX text was not kept as written');
  });
  test(`${name}: the expression between a pair of quotes in JSX text is code, and the code after the pair stays`, () => {
    const out = read('export const B = () => <p>"{side.words}"</p>; export const g = () => run();\n', TSX);
    assert.match(out, /\{side\.words\}/, 'the pair of quotes blanked the expression between them');
    assert.match(out, /run\(\);\n$/, 'the pair of quotes blanked the code after it');
  });
}

// ---- 2. Which names read JSX. ----
test('GUARD: a read with no file name, or a .ts, .mjs or .js name, reads no JSX, so a quote in text opens a string', () => {
  const pair = 'export const B = () => <p>"{side.words}"</p>; export const g = () => run();\n';
  const lone = "const el = <p>Don't</p>; keep();\n";
  for (const [name, read] of Object.entries(BLANKING)) {
    for (const file of [undefined, 'x.ts', 'x.mjs', 'x.js']) {
      const out = read(pair, file);
      assert.doesNotMatch(out, /side\.words/, `${name}, name ${file}: JSX was read, so the expression between the quotes was kept`);
      assert.match(out, /run\(\);\n$/, `${name}, name ${file}: the code after the quotes was lost`);
      const alone = read(lone, file);
      assert.ok(alone.startsWith("const el = <p>Don'"), `${name}, name ${file}: the text before the quote changed`);
      assert.doesNotMatch(alone, /keep/, `${name}, name ${file}: the quote did not open a string, so JSX was read`);
    }
  }
});

test('a .tsx or .jsx name reads JSX, so the expression between a pair of quotes in JSX text is kept', () => {
  const pair = 'export const B = () => <p>"{side.words}"</p>; export const g = () => run();\n';
  for (const [name, read] of Object.entries(BLANKING)) {
    for (const file of ['x.tsx', 'x.jsx', 'src/ui/Page.tsx']) assert.match(read(pair, file), /\{side\.words\}/, `${name}, name ${file}: JSX was not read`);
  }
});

// ---- 3. `<Foo>` and a spaced attribute are tags. A `//` or a `/` in JSX text is text. ----
for (const [name, read] of Object.entries(READERS)) {
  test(`${name}: in a .tsx file <Foo> and a tag with a spaced attribute are tags, so a lone quote in their text opens no string`, () => {
    for (const [what, el] of [['<Foo>', "<Foo>Don't</Foo>"], ['<a b = "1">', `<a b = "1">Don't</a>`], ['<Foo.Bar x={1}>', "<Foo.Bar x={1}>Don't</Foo.Bar>"]]) {
      // A tag read as a generic leaves the quote open, and the quote then holds the rest of its line: the code and the comment after it.
      const out = read(`export const el = ${el}; run(); // GATED\nconst keep = 1;\n`, TSX);
      assert.ok(out.includes(`${el.slice(el.indexOf('>') + 1)}; run();`), `${what}: the lone quote in the JSX text was read as a string`);
      assert.doesNotMatch(out, /GATED/, `${what}: the comment after the element was kept as code`);
      assert.match(out, /const keep = 1;\n$/, `${what}: the code after the element was lost`);
    }
  });
  test(`${name}: in a .tsx file a // or a / in JSX text is text, and the code after it stays`, () => {
    const url = read('export const A = () => <p>see http://x</p>; keep();\n', TSX);
    assert.ok(url.includes('see http://x</p>'), 'the // in JSX text was read as a comment');
    assert.match(url, /keep\(\);\n$/, 'the // in JSX text hid the code after it');
    const slash = read('export const C = () => <p>{a}/ b</p>; keep();\n', TSX);
    assert.ok(slash.includes('/ b</p>'), 'the / after a brace in JSX text was read as a regex');
    assert.match(slash, /keep\(\);\n$/, 'the / after a brace in JSX text hid the code after it');
  });
}

// ---- 4. A generic is no tag. ----
// A `.ts` file holds no JSX, and a `.tsx` file holds JSX and generics both. `= <T>(x) =>` is no valid `.tsx`, so only `.ts` holds it.
// A file that ends with a tag still open is read again with no JSX. So one stray closing tag later (a string `"</b>"`, a comment that
// names `</p>`) makes a file look closed when a generic was read as a tag, and the comment between stays unblanked.
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
const stray = (name) => (blanks(name) ? 'const s = "    ";' : 'const s = "</b>";');

for (const [what, decl, files] of GENERICS) {
  for (const file of files) {
    test(`GUARD: a generic is no JSX tag, so the comment after it is blanked: ${what} in ${file}`, () => {
      for (const [after, lines] of AFTER) {
        const src = [decl, ...lines, 'const keep = 1;', ''].join('\n');
        for (const [name, read] of Object.entries(READERS)) {
          const out = read(src, file);
          assert.ok(out.includes(decl), `${name}, ${after}: the generic was changed`);
          assert.doesNotMatch(out, /GATED/, `${name}, ${after}: the comment after the generic was kept as code`);
          assert.match(out, /const keep = 1;\n$/, `${name}, ${after}: the code after the generic was lost`);
          if (lines.length > 1) assert.ok(out.includes(stray(name)), `${name}, ${after}: the string after the generic was changed`);
        }
      }
    });
  }
}

for (const [name, read] of Object.entries(READERS)) {
  test(`${name}: in a .tsx file a generic is no tag, and a JSX element after it still holds its lone quote as text`, () => {
    const src = ['export const f = <T extends X>(a: T) => a;', '// GATED', "export const el = <p>Don't</p>; keep(); // GATED", 'export const s = "</b>";', ''].join('\n');
    const out = read(src, TSX);
    assert.doesNotMatch(out, /GATED/, 'a comment was kept as code: after the generic, or after the lone quote in the JSX text');
    assert.match(out, /keep\(\);\s*\nexport const s = /, 'the lone quote in the JSX text blanked the code after it');
  });
}

// ---- 5. A comment opener inside a string, and a multi-line template literal. ----
test('GUARD: a comment opener or a lone quote inside a string or a comment hides no code after it', () => {
  for (const [what, src] of [
    ['`//` inside a string', 'const url = "https://x//y"; keep(url);'],
    ['`/*` in one string and `*/` in a later one', "const a = '/*'; keep(); const b = \"*/\";"],
    ['`#` inside a string', 'const s = "# not a comment"; keep(s);'],
    ['`//` inside a template literal', 'const t = `http://x`; keep(t);'],
    ['`//` inside a JSX attribute string', 'const el = <a href="http://x">y</a>; keep(el);'],
    ['a lone quote inside a JSX attribute string', 'const el = <a title="Don\'t" href="/x">y</a>; keep(el);'],
    ['a lone quote in a line comment', "// don't\nkeep();"],
    ['a lone quote in a block comment', "/* it's */ keep();"],
  ]) {
    for (const file of ['x.ts', TSX]) {
      for (const [name, read] of Object.entries(READERS)) assert.match(read(src, file), /keep\(/, `${name}, ${file}, ${what}: the code after it was lost`);
    }
  }
});

test('GUARD: a multi-line template literal holds its words as text, and the code after it stays', () => {
  // The lines of the template hold a comment opener and a lone quote. None of them ends the template or opens a comment.
  const src = "const t = `line one\nclassifyIntent(x) // not a comment\nDon't /* not a block\n\"q\"`;\nplanUnsureTurn();\nconst s = \"*/\";";
  for (const file of ['x.ts', TSX]) {
    for (const [name, read] of Object.entries(READERS)) {
      const out = read(src, file);
      if (blanks(name)) {
        assert.doesNotMatch(out, /classifyIntent/, `${name}, ${file}: a name in the template text was kept as code`);
        assert.match(out, /planUnsureTurn\(\);\nconst s = " {2}";/, `${name}, ${file}: the code after the template was lost`);
      } else {
        assert.ok(out.includes("classifyIntent(x) // not a comment\nDon't /* not a block"), `${name}, ${file}: a comment opener in the template was read as a comment`);
        assert.match(out, /planUnsureTurn\(\);\nconst s = "\*\/";$/, `${name}, ${file}: the code after the template was lost`);
      }
    }
  }
});

for (const [name, read] of Object.entries(READERS)) {
  test(`${name}: in a .tsx file a multi-line template literal inside JSX is text, and a lone quote after it opens no string`, () => {
    const src = "export const el = <p>{`line\n// not a comment\nDon't`} it's</p>; run(); // GATED\nconst keep = 1;\n";
    const out = read(src, TSX);
    assert.ok(out.includes('run();'), 'the lone quote after the template blanked the code after it');
    assert.doesNotMatch(out, /GATED/, 'the comment after the element was kept as code');
    assert.match(out, /const keep = 1;\n$/, 'the code after the element was lost');
    assert.equal(/not a comment/.test(out), !blanks(name), 'the text of the template was read wrong');
  });
}

// ---- 6. The callers pass the file name. Each source holds a lone quote in JSX text, then the thing the caller looks for on the same
// line, so a caller that passes no name reads the quote as a string and loses it. ----
const NOTE = "export const A = () => <p>Don't</p>; /**\n * In plain words: shows the note.\n */\n";

test('plainWordsNotes: in a .tsx file a note after a lone quote in JSX text is found', () => {
  assert.deepEqual(plainWordsNotes({ 'src/a.tsx': NOTE }), ['src/a.tsx:2']);
});
test('GUARD: plainWordsNotes: in a .ts file the quote opens a string, so the note after it is no note', () => {
  assert.deepEqual(plainWordsNotes({ 'src/a.ts': NOTE }), []);
});
test('plainWordsNotes: in a .tsx file a `// In plain words:` line in JSX text is text, so it is no note', () => {
  const text = 'export const A = () => (\n  <p>\n    // In plain words: this is on the screen\n  </p>\n);\n';
  assert.deepEqual(plainWordsNotes({ 'src/a.tsx': text }), []);
});

const IMPORT = "export const A = () => <p>Don't</p>; const m = import('./b');\n";
const TRACKED = new Set(['src/a.tsx', 'src/a.ts', 'src/b.ts']);
test('importTargets: in a .tsx file an import after a lone quote in JSX text is found', () => {
  assert.deepEqual(importTargets('src/a.tsx', IMPORT, TRACKED), ['src/b.ts']);
});
test('GUARD: importTargets: in a .ts file the quote opens a string, so the import after it is no import', () => {
  assert.deepEqual(importTargets('src/a.ts', IMPORT, TRACKED), []);
});

const STAGE = { variable: 'stage', callback: 'setStage' };
const STAGED = "const a = 1;\nconst el = <p>Don't</p>; setStage('read');\n";
test('stageSitesOf: in a .tsx file a stage site after a lone quote in JSX text is found', () => {
  assert.deepEqual(stageSitesOf(STAGED, STAGE, 'src/w.tsx'), [{ step: 'read', line: 2 }]);
});
test('GUARD: stageSitesOf: in a .ts file the quote opens a string, so the stage site after it is no site', () => {
  assert.deepEqual(stageSitesOf(STAGED, STAGE, 'src/w.ts'), []);
});

// A name is listed when two code files define it, so the second file is the control: `Shared` is listed only when the first file's
// `export` after the lone quote is read.
const nodes = (...ps) => ({ nodes: ps.map((p) => ({ k: 'code', p, a: 'app', j: 0 })) });
const shared = (ext) => lookAlikes(nodes(`src/a.${ext}`, `src/b.${ext}`), {
  [`src/a.${ext}`]: "export const A = () => <p>Don't</p>; export const Shared = 1;\n",
  [`src/b.${ext}`]: 'export const Shared = 2;\n',
}).names.map((n) => n.name);
test('lookAlikes: in a .tsx file a name exported after a lone quote in JSX text is found', () => {
  assert.deepEqual(shared('tsx'), ['Shared']);
});
test('GUARD: lookAlikes: in a .ts file the quote opens a string, so the name exported after it is not found', () => {
  assert.deepEqual(shared('ts'), []);
});

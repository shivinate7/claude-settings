// The layout of the skill folder, and what SKILL.md may say.
//
// `skills/plain-english-map/` holds the skill. Its scripts import only node builtins and files inside the folder, so the
// skill runs in any repository, with no help from the host. The one exception is the bare `typescript` import in
// `scripts/lib/lazy-typescript.mjs`, which loads at first use from the node_modules of claude-settings.
// SKILL.md must make the skill fire only in a repository that has `map.config.json` at its root, and it must name
// no path and no decision of one host repository.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { builtinModules, createRequire } from 'node:module';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { SKILL, needFile } from './helpers.mjs';

const LIB = ['lazy-typescript.mjs', 'source-text.mjs', 'import-reader.mjs', 'map-config.mjs'].map((n) => `scripts/lib/${n}`);
const FILES = ['SKILL.md', 'scripts/map-check.mjs', 'scripts/map-picture.mjs', 'assets/page.html', ...LIB];

// The front matter of SKILL.md as { name, description }. A value may continue on indented lines.
const frontMatter = () => {
  needFile('SKILL.md');
  const lines = readFileSync(join(SKILL, 'SKILL.md'), 'utf8').split(/\r?\n/);
  assert.equal(lines[0], '---', 'SKILL.md must open with a --- line');
  const end = lines.indexOf('---', 1);
  assert.ok(end > 1, 'SKILL.md front matter must close with a --- line');
  const front = lines.slice(1, end);
  const field = (key) => {
    const at = front.findIndex((l) => l.startsWith(`${key}:`));
    if (at < 0) return '';
    let value = front[at].slice(key.length + 1);
    for (let i = at + 1; i < front.length && /^\s/.test(front[i]); i++) value += ` ${front[i].trim()}`;
    return value.trim();
  };
  return { name: field('name'), description: field('description') };
};

test('SKILL.md opens with front matter that names the skill and says what it does', () => {
  const { name, description } = frontMatter();
  assert.equal(name, 'plain-english-map', 'front matter name must be plain-english-map');
  assert.notEqual(description, '', 'front matter must have a description');
});

test('the description names map.config.json, so the skill fires only in a repository that has one', () => {
  const { description } = frontMatter();
  assert.ok(description.includes('map.config.json'), `the description must name map.config.json. It says: ${description}`);
});

test('SKILL.md names no path of one host repository and cites no decision of one', () => {
  needFile('SKILL.md');
  const text = readFileSync(join(SKILL, 'SKILL.md'), 'utf8');
  assert.doesNotMatch(text, /\bharness\//, 'SKILL.md names a harness/ path, which only one host repository has');
  assert.doesNotMatch(text, /\bD-\d+\b/, 'SKILL.md cites a decision id of one host repository');
  assert.doesNotMatch(text, /\[\[[a-z0-9-]+\]\]/, 'SKILL.md cites a decision slug of one host repository');
});

test('the skill holds its scripts, its helpers and its page template', () => {
  for (const rel of FILES) needFile(rel);
});

// ---- the scan of the scripts ---------------------------------------------------------------------------------

// The specifiers a source names in an import, an export-from, a dynamic `import()`, a `require()`, a `createRequire(...)()` call and
// an `import('x')` type. The parser reads the source, so a comment, a string and a template literal make no import.
// `typescript` loads here, at first use, from the node_modules of claude-settings.
const specsOf = (file, src) => {
  const ts = createRequire(import.meta.url)('typescript');
  const ext = file.slice(file.lastIndexOf('.'));
  const kind = ext === '.tsx' ? ts.ScriptKind.TSX : ext === '.ts' ? ts.ScriptKind.TS : ts.ScriptKind.JS;
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, kind);
  const found = [];
  const text = (n) => (n && (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) ? n.text : null);
  const visit = (n) => {
    if ((ts.isImportDeclaration(n) || ts.isExportDeclaration(n)) && n.moduleSpecifier) found.push(text(n.moduleSpecifier));
    else if (ts.isImportEqualsDeclaration(n) && ts.isExternalModuleReference(n.moduleReference)) found.push(text(n.moduleReference.expression));
    else if (ts.isImportTypeNode(n) && ts.isLiteralTypeNode(n.argument)) found.push(text(n.argument.literal));
    else if (ts.isCallExpression(n) && n.arguments.length > 0) {
      const c = n.expression;
      if (c.kind === ts.SyntaxKind.ImportKeyword || (ts.isIdentifier(c) && c.text === 'require') || ts.isCallExpression(c)) found.push(text(n.arguments[0]));
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return found.filter((s) => s !== null);
};

test('the scanner: a comment opener in a string never hides an import, and a string or a comment is no import', () => {
  const T = './lib/a.mjs';
  // A comment opener inside strings must not blank the import after it.
  assert.deepEqual(specsOf('a.mjs', `const s = '/*'; const t = "//"; const u = \`#\`;\nimport { v } from '${T}';\nconst w = '*/';\n`), [T]);
  // A multi-line template literal holds the import text, and it holds a `//` and a `/*`. Only the real import after it counts.
  assert.deepEqual(specsOf('b.mjs', `const text = \`line one // not a comment\n/* nor this\nimport { v } from '${T}';\n\`;\nconst w = 1;\n`), []);
  assert.deepEqual(specsOf('c.mjs', `const text = \`a // b\n/* c\n\`;\nimport { v } from '${T}';\n`), [T]);
  // A lone quote in text, such as JSX `<p>Don't</p>`, must not open a string that swallows the import after it.
  assert.deepEqual(specsOf('d.tsx', `const el = <p>Don't</p>;\nimport { v } from '${T}';\nconst f = <p>It's</p>;\n`), [T]);
  // A comment and a string are no import.
  assert.deepEqual(specsOf('e.mjs', `// import { v } from '${T}';\n/* import('${T}') */\nconst s = "import { v } from '${T}'";\n`), []);
  // Every real form counts, and the bare specifier of a `createRequire` call counts too.
  assert.deepEqual(
    specsOf('f.mjs', `export { v } from './b.mjs';\nconst m = await import('./c.mjs');\nconst r = createRequire(import.meta.url)('typescript');\n`),
    ['./b.mjs', './c.mjs', 'typescript']
  );
});

// Every .mjs file under scripts/, lib/ included.
const scriptFiles = (dir = join(SKILL, 'scripts')) =>
  readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? scriptFiles(join(dir, e.name)) : e.name.endsWith('.mjs') ? [join(dir, e.name)] : []));

test('the skill scripts import only node builtins, files inside the skill folder, and typescript in lazy-typescript.mjs', () => {
  assert.ok(existsSync(join(SKILL, 'scripts')), 'skills/plain-english-map/scripts/ is missing');
  const files = scriptFiles();
  assert.ok(files.length >= 2, 'the scan found no skill scripts, so it proves nothing');
  for (const file of files) {
    const rel = relative(SKILL, file).split(sep).join('/');
    for (const spec of specsOf(file, readFileSync(file, 'utf8'))) {
      if (spec.startsWith('node:') || builtinModules.includes(spec)) continue;
      if (spec === 'typescript') {
        assert.equal(rel, 'scripts/lib/lazy-typescript.mjs', `${rel} loads typescript. Only scripts/lib/lazy-typescript.mjs may, and it loads at first use`);
        continue;
      }
      assert.ok(spec.startsWith('.'), `${rel} imports "${spec}", which is neither a node builtin nor a file in the skill`);
      const into = relative(SKILL, resolve(dirname(file), spec));
      assert.ok(into !== '' && !into.startsWith('..') && !isAbsolute(into), `${rel} imports "${spec}", which is outside the skill folder`);
    }
  }
});

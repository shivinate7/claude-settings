// The one home of the value readers behind the map's fact lines (MAP9). Each language is read by its own parser:
//   .py                    scripts/lib/py-facts.py, one `python3 -I` start for every Python request of a call
//   .json                  JSON.parse and a dotted path, with `[*]` to fan out over a list
//   .ts .tsx .mjs .js ...  the typescript parser, through lazy-typescript.mjs, module-level declarations only
//   any other extension    a line regex over the text with comments AND strings blanked. It is no parser: a stated limit.
// A request is { file, symbol } for a value. Internal callers add `op`: 'defines' (is the symbol bound at module level)
// 'uses' (does `file` import the tracked file `target`, and refer to `symbol`) or 'loads' (the tracked files that `file` loads at runtime, as
// { imports, named }: the files it imports without a type-only import, and the files a string in its code equals, from its folder or the root).
// A result is { file, symbol, ok: true, value } or { file, symbol, ok: false, reason, gone? }. `gone: true` means the file was
// read and the symbol is not in it. A failure without `gone` is unknown: the caller must never read it as a pass.
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from './lazy-typescript.mjs';
import { importTargets, resolveSpecifier } from './import-reader.mjs';
import { blankCommentsAndStrings, blankShell, SHELL_EXT } from './source-text.mjs';

const PY_FACTS = fileURLToPath(new URL('./py-facts.py', import.meta.url));
const TS_EXT = /\.(?:ts|tsx|mts|cts|mjs|cjs|js|jsx)$/;
// A non-shell file whose `#` starts a comment. Only a full-line `#` comment is read as one: a trailing `# note` after code stays a
// stated limit. A shell file goes to blankShell instead.
const HASH_COMMENT_EXT = /\.(?:ps1|rb|toml|ya?ml|conf|mk)$/;

const fail = (req, reason, gone = false) => ({ file: req.file, symbol: req.symbol, ok: false, reason, ...(gone && { gone: true }) });
const good = (req, value) => ({ file: req.file, symbol: req.symbol, ok: true, value });
const gone = (req) => fail(req, `${req.file} has no ${req.symbol}`, true);

// ---- .json ----

// The values at `parts` under `value`. A `name[*]` part fans out over a list. The grammar of `lint/rule_audit.py` → `_walk`.
const walk = (value, parts) => {
  if (!parts.length) return [value];
  const [head, ...rest] = parts;
  const fan = head.endsWith('[*]');
  const key = fan ? head.slice(0, -3) : head;
  if (value === null || typeof value !== 'object' || Array.isArray(value) || !Object.hasOwn(value, key)) return [];
  const child = value[key];
  if (!fan) return walk(child, rest);
  return Array.isArray(child) ? child.flatMap((item) => walk(item, rest)) : [];
};

const readJson = (req, text) => {
  let data;
  try { data = JSON.parse(text); } catch (e) { return fail(req, `${req.file} does not parse as JSON: ${e.message}`); }
  if (req.op === 'uses' || req.op === 'loads') return fail(req, `a ${req.op} fact is read for Python and JavaScript files, and ${req.file} is JSON`);
  const found = walk(data, req.symbol.split('.'));
  if (!found.length) return gone(req);
  if (req.op === 'defines') return good(req, true);
  return good(req, req.symbol.includes('[*]') ? found : found[0]);
};

// ---- .ts .tsx .mjs .js ----

class NotLiteral extends Error {}

// The JSON value of a literal expression. Anything else is not a literal, and that is never read as a value.
const literalOf = (x) => {
  if (ts.isParenthesizedExpression(x) || ts.isAsExpression(x) || ts.isSatisfiesExpression(x) || ts.isTypeAssertionExpression(x)) return literalOf(x.expression);
  if (ts.isNumericLiteral(x)) return Number(x.text.replace(/_/g, ''));
  if (ts.isPrefixUnaryExpression(x) && x.operator === ts.SyntaxKind.MinusToken && ts.isNumericLiteral(x.operand)) return -literalOf(x.operand);
  if (ts.isStringLiteral(x) || ts.isNoSubstitutionTemplateLiteral(x)) return x.text;
  if (x.kind === ts.SyntaxKind.TrueKeyword) return true;
  if (x.kind === ts.SyntaxKind.FalseKeyword) return false;
  if (x.kind === ts.SyntaxKind.NullKeyword) return null;
  if (ts.isArrayLiteralExpression(x)) return x.elements.map(literalOf);
  if (ts.isObjectLiteralExpression(x))
    return Object.fromEntries(x.properties.map((p) => {
      if (!ts.isPropertyAssignment(p) || !(ts.isIdentifier(p.name) || ts.isStringLiteral(p.name))) throw new NotLiteral();
      return [p.name.text, literalOf(p.initializer)];
    }));
  // `new Set([...])` and `Object.freeze(x)` hold a literal.
  if (ts.isNewExpression(x) && ts.isIdentifier(x.expression) && x.expression.text === 'Set' && x.arguments?.length === 1) return literalOf(x.arguments[0]);
  if (ts.isCallExpression(x) && x.expression.getText() === 'Object.freeze' && x.arguments.length === 1) return literalOf(x.arguments[0]);
  throw new NotLiteral();
};

// Each module-level binding of a parsed file: name -> initializer (a node, or null when it has none).
const moduleBindings = (sf) => {
  const out = new Map();
  for (const st of sf.statements) {
    if (ts.isVariableStatement(st)) for (const d of st.declarationList.declarations) { if (ts.isIdentifier(d.name)) out.set(d.name.text, d.initializer ?? null); }
    else if ((ts.isFunctionDeclaration(st) || ts.isClassDeclaration(st) || ts.isEnumDeclaration(st) || ts.isInterfaceDeclaration(st) || ts.isTypeAliasDeclaration(st)) && st.name) out.set(st.name.text, null);
    else if (ts.isExportDeclaration(st) && st.exportClause && ts.isNamedExports(st.exportClause)) for (const e of st.exportClause.elements) out.set(e.name.text, null);
  }
  return out;
};

// The local names that hold the whole module of `target`: `import * as ns`, a default `import lib`, `import m = require(...)`,
// `const m = require(...)` and `const m = await import(...)`. Each specifier goes through the import reader's resolver, so an
// alias of any other module is no alias of `target`.
const targetAliases = (sf, file, target, tracked) => {
  const aliases = new Set();
  const namesTarget = (spec) => ts.isStringLiteralLike(spec) && resolveSpecifier(file, spec.text, tracked) === target;
  const visit = (n) => {
    if (ts.isImportDeclaration(n) && n.importClause && namesTarget(n.moduleSpecifier)) {
      const { name, namedBindings } = n.importClause;
      if (name) aliases.add(name.text);
      if (namedBindings && ts.isNamespaceImport(namedBindings)) aliases.add(namedBindings.name.text);
    } else if (ts.isImportEqualsDeclaration(n) && ts.isExternalModuleReference(n.moduleReference) && namesTarget(n.moduleReference.expression)) {
      aliases.add(n.name.text);
    } else if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.initializer) {
      let x = n.initializer;
      while (ts.isParenthesizedExpression(x) || ts.isAwaitExpression(x)) x = x.expression;
      const callee = ts.isCallExpression(x) && x.arguments.length === 1 ? x.expression : null;
      const loads = callee && (callee.kind === ts.SyntaxKind.ImportKeyword || (ts.isIdentifier(callee) && callee.text === 'require'));
      if (loads && namesTarget(x.arguments[0])) aliases.add(n.name.text);
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return aliases;
};

// A key slot names a member, never the module's symbol: `{ notes() {} }`, a class method or field, `{ notes: x }`, the key of
// `const { notes: x } = obj`, a type member and a JSX attribute.
const isKeySlot = (n) => {
  const p = n.parent;
  if (!p) return false;
  if (ts.isBindingElement(p)) return p.propertyName === n;
  return p.name === n && (ts.isMethodDeclaration(p) || ts.isPropertyDeclaration(p) || ts.isGetAccessorDeclaration(p) || ts.isSetAccessorDeclaration(p)
    || ts.isPropertySignature(p) || ts.isMethodSignature(p) || ts.isPropertyAssignment(p) || ts.isJsxAttribute(p) || ts.isEnumMember(p));
};

// The names a file refers to, outside its imports. A key slot is no reference, and neither is a member: `e.code` refers to no `code`.
// A member of an alias of the cited file is one: `ns.code`, and the `code` key of `const { code: c } = ns`.
const identifiers = (sf, aliases) => {
  const names = new Set();
  const visit = (n) => {
    if (ts.isImportDeclaration(n)) return;
    if (ts.isPropertyAccessExpression(n)) {
      visit(n.expression);
      if (ts.isIdentifier(n.expression) && aliases.has(n.expression.text)) names.add(n.name.text);
      return;
    }
    if (ts.isVariableDeclaration(n) && ts.isObjectBindingPattern(n.name) && n.initializer && ts.isIdentifier(n.initializer) && aliases.has(n.initializer.text))
      for (const e of n.name.elements) if (e.propertyName && ts.isIdentifier(e.propertyName)) names.add(e.propertyName.text);
    if (ts.isIdentifier(n) && !isKeySlot(n)) names.add(n.text);
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return names;
};

// The tracked files that a string in the code equals, from the file's folder or the repository root. A module specifier of an import or
// an export is no code string, and neither is a type: `import type x from './a.ts'` names a file and loads none.
const namedFiles = (sf, file, files) => {
  const folder = path.posix.dirname(file);
  const out = new Set();
  const visit = (n) => {
    if (ts.isLiteralTypeNode(n) || ts.isImportTypeNode(n)) return;
    if ((ts.isImportDeclaration(n) || ts.isExportDeclaration(n)) && n.moduleSpecifier) return;
    if (ts.isExternalModuleReference(n)) return;
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) {
      const s = n.text;
      if (s && !s.includes('\n') && !s.startsWith('/'))
        for (const c of [path.posix.normalize(path.posix.join(folder, s)), path.posix.normalize(s)]) if (c !== file && files.has(c)) out.add(c);
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return [...out].sort();
};

const readTs = (req, text, files) => {
  let sf;
  try { sf = ts.createSourceFile(req.file, text, ts.ScriptTarget.Latest, true); } catch (e) { return fail(req, `${req.file} cannot be parsed: ${e.message}`); }
  if (req.op === 'loads') return good(req, { imports: importTargets(req.file, text, files, { types: false }).filter((f) => f !== req.file), named: namedFiles(sf, req.file, files) });
  if (req.op === 'uses') {
    const imports = importTargets(req.file, text, files).includes(req.target);
    const uses = req.symbol == null ? null : identifiers(sf, targetAliases(sf, req.file, req.target, files)).has(req.symbol);
    return good(req, { imports, uses });
  }
  const bindings = moduleBindings(sf);
  if (!bindings.has(req.symbol)) return gone(req);
  if (req.op === 'defines') return good(req, true);
  const init = bindings.get(req.symbol);
  if (!init) return fail(req, `${req.file} ${req.symbol} has no literal value`);
  try { return good(req, literalOf(init)); } catch (e) {
    if (e instanceof NotLiteral) return fail(req, `${req.file} ${req.symbol} is not a literal`);
    throw e;
  }
};

// ---- a shell file: the words of its code that name a tracked file ----

const SHELL_WORD_END = /[\s;&|()<>]/;

// The words of a shell file's code, each with its offset, and the code itself with its strings kept. Comments and heredoc bodies yield no
// word. A word is a run between blanks and `;&|()<>` outside quotes, so a quoted string with a blank is one word, and its quote marks
// are removed.
const shellWords = (text) => {
  const bare = blankShell(text);
  const code = blankShell(text, { keepStrings: true });
  const words = [];
  let word = null;
  let from = 0;
  let quote = null;
  const flush = () => { if (word !== null) words.push({ w: word, at: from }); word = null; };
  const open = (i) => { if (word === null) { word = ''; from = i; } };
  for (let i = 0; i < bare.length; i++) {
    const c = bare[i];
    if (quote) {
      // A `$` in single quotes is text: `\$` marks it, so the `\` filter in shellLoads skips the word.
      if (c === quote) quote = null; else word += quote === "'" && code[i] === '$' ? '\\$' : code[i];
      continue;
    }
    if (c === '\\' && i + 1 < bare.length) { open(i); word += code[i] + code[i + 1]; i++; continue; }
    if (c === "'" || c === '"') { open(i); quote = c; continue; }
    if (SHELL_WORD_END.test(c)) { flush(); continue; }
    open(i);
    word += code[i];
  }
  flush();
  return { code, words };
};

// A place expression in a shell binding: a base, then literal `/..` or `/sub` pieces. A base is the test's own folder as the file names
// it, `$(dirname "$0")` (or `dirname --`), or `${0%/*}`, each with `BASH_SOURCE[0]` or `BASH_SOURCE` for `$0`; or `$NAME` or `${NAME}`. A
// `$(cd "<base><pieces>" && pwd)` (also `cd --`, and `pwd -P`) is the same place, and so is `$(readlink -f "<base><pieces>")` or
// `$(realpath "<base><pieces>")`. A `$(dirname "<base><pieces>")` is the shell's text dirname of that place and its pieces, so
// `dirname "$HERE/.."` is HERE itself. A piece holds no `/`, so each `/` starts one piece and a failed match does not backtrack.
const SELF = '(?:\\$0|\\$\\{BASH_SOURCE(?:\\[0\\])?\\}|\\$BASH_SOURCE)';
const HERE = `(?:\\$\\(dirname (?:-- )?"?${SELF}"?\\)|\\$\\{(?:0|BASH_SOURCE(?:\\[0\\])?)%/\\*\\})`;
const SELF_FOLDER = new RegExp(`^${HERE}$`);
const BASE = `(?:${HERE}|\\$[A-Za-z_]\\w*|\\$\\{[A-Za-z_]\\w*\\})`;
const PIECES = '((?:/[^/\\s"\'$\\\\`;&|()<>*?]*)*)';
const PLACE = new RegExp(`^"?(?:\\$\\(cd (?:-- )?"?(${BASE})"?${PIECES}"? && pwd(?: -P)?\\)|(${BASE}))"?${PIECES}"?$`);
const SAME_PLACE = new RegExp(`^"?\\$\\((?:readlink -f|realpath) (?:-- )?"?(${BASE})${PIECES}"?\\)"?$`);
const PARENT_PLACE = new RegExp(`^"?\\$\\(dirname (?:-- )?"?(${BASE})${PIECES}"?\\)"?$`);
// `${NAME:-$OTHER/tail}` with OTHER bound: the default resolves from OTHER's place, as Python's `os.environ.get(...) or join(HERE, ...)`
// does. `${NAME:-src/x.py}` with no `$` in the default is that literal path, as Python's `os.environ.get(NAME, "src/x.py")` is.
const DEFAULT = /^"?\$\{[A-Za-z_]\w*:-(\$(?:[A-Za-z_]\w*|\{[A-Za-z_]\w*\})\/[^}]*|[^$`\\"'}\s]+)\}"?$/;

const fromPlace = (place, pieces) => path.posix.normalize(path.posix.join(place, ...pieces.split('/').filter(Boolean)));

// The repository path that a binding's value names, or null when it names no known place. `placeOf(NAME)` gives a bound name's place.
const boundPlace = (value, folder, placeOf) => {
  const v = value.replace(DEFAULT, '$1');
  const at = (base) => (SELF_FOLDER.test(base) ? folder : placeOf(base.replace(/^\$\{?|\}$/g, '')));
  let m = PLACE.exec(v);
  if (m) {
    const place = at(m[1] ?? m[3]);
    return place == null ? null : fromPlace(place, (m[2] ?? '') + m[4]);
  }
  m = SAME_PLACE.exec(v);
  if (m) {
    const place = at(m[1]);
    return place == null ? null : fromPlace(place, m[2]);
  }
  m = PARENT_PLACE.exec(v);
  if (!m) return null;
  const place = at(m[1]);
  return place == null ? null : path.posix.normalize(path.posix.dirname(place + m[2]));
};

// The names that something other than a line's `NAME=` sets: `read` into a name, `for NAME in`, `unset NAME`, a `NAME+=`, a later name of
// a `local`, `declare` or `typeset` with a value, and a `NAME=` after `&&` or `||`. Each takes its value at run time or on one branch
// only, or has none, so the name has no one static place. A `declare`, `typeset` or `local` of a first name with a value is a bind
// like any other (`bindPattern`), and without a value it changes nothing. A command's words run to the next `;`, `&`, `|` or newline.
const REBINDERS = new Set(['read', 'for', 'unset']);
const DECLARERS = new Set(['local', 'declare', 'typeset']);
const reboundNames = (code, words, starts, plus) => {
  const out = new Set(plus);
  for (const { w, at } of words) {
    const declares = DECLARERS.has(w);
    if (!declares && !REBINDERS.has(w)) continue;
    const args = code.slice(at).split(/[;&|\n]/, 1)[0].split(/[ \t]+/).slice(1).filter((a) => !a.startsWith('-'));
    for (const a of w === 'for' ? args.slice(0, 1) : declares ? args.slice(1) : args) {
      const m = /^([A-Za-z_]\w*)(=|$)/.exec(a);
      if (m && (!declares || m[2] === '=')) out.add(m[1]);
    }
  }
  for (const m of code.matchAll(/(?:&&|\|\|)[ \t]*(?:(?:export|readonly|local|declare|typeset)[ \t]+)?([A-Za-z_]\w*)=/g)) {
    if (starts.has(m.index + m[0].length - m[1].length - 1)) out.add(m[1]);
  }
  return out;
};

// A bind: a name and `=` at the start of a command, after `;`, `&`, `|`, `(`, `)`, `{`, `}` or a `then`, `else` or `do` word, with an
// optional `export`, `readonly`, `declare`, `typeset` or `local` and its options. The `)` covers `case x)`. A `+=` is no bind but a rebind.
const bindPattern = /(^|[;&|(){}]|\b(?:then|else|do)\b)[ \t]*(?:(?:export|readonly|declare|typeset|local)(?:[ \t]+-\S*)*[ \t]+)?([A-Za-z_]\w*)(\+?)=([^\n;]*)/gmd;

// The tracked files that a shell file's words name, from the file's folder or the repository root. A leading `NAME=` is dropped, and a
// word `${NAME:-$OTHER/tail}` or `${NAME:-literal/path}` is read as its default. A word with a `\`, a newline or a leading `/` is skipped.
// A word with no `$` must equal the path after normalization. A word `$NAME/tail` or `${NAME}/tail`, its tail with no `$`, counts only
// when the file binds NAME before the word, and every binding of NAME names one place (`boundPlace`); the tail then resolves from that
// place alone. A binding is a `NAME=` at the start of a command (`bindPattern`), with or without `export`, `readonly`, `declare` or `local`. A name with two places, with a binding to no known
// place, or with a rebind (`reboundNames`) counts for nothing. A binding or rebind anywhere in the file counts, above or below the word.
const shellLoads = (req, text, files) => {
  const folder = path.posix.dirname(req.file);
  const { code, words } = shellWords(text);
  const starts = new Set(words.map(({ at }) => at));
  const bindings = [];
  const plus = [];
  for (const m of code.matchAll(bindPattern)) {
    const at = m.indices[2][0];
    if (/^\w/.test(m[1]) && !starts.has(m.index)) continue;
    if (!starts.has(at)) continue;
    if (m[3]) plus.push(m[2]);
    else bindings.push({ name: m[2], at, value: m[4].trim() });
  }
  const rebound = reboundNames(code, words, starts, plus);
  const bound = (name, before) => bindings.some((b) => b.name === name && b.at < before);
  const places = new Map();
  const placeOf = (name) => {
    if (places.has(name)) return places.get(name);
    places.set(name, null);
    if (rebound.has(name)) return null;
    const found = new Set(bindings.filter((b) => b.name === name)
      .map((b) => boundPlace(b.value, folder, (other) => (bound(other, b.at) ? placeOf(other) : null))));
    const place = found.size === 1 ? [...found][0] : null;
    places.set(name, place);
    return place;
  };
  const out = new Set();
  for (const { w: raw, at } of words) {
    const w = raw.replace(/^[A-Za-z_]\w*=/, '').replace(DEFAULT, '$1');
    if (!w || /[\\\n]/.test(w) || w.startsWith('/')) continue;
    const anchored = /^\$(?:([A-Za-z_]\w*)|\{([A-Za-z_]\w*)\})\/(.+)$/.exec(w);
    const s = anchored ? anchored[3] : w;
    if (s.includes('$')) continue;
    const name = anchored && (anchored[1] ?? anchored[2]);
    const roots = anchored ? [bound(name, at) ? placeOf(name) : null] : [folder, '.'];
    for (const place of roots) {
      if (place == null) continue;
      const c = path.posix.normalize(path.posix.join(place, s));
      if (c !== req.file && files.has(c)) out.add(c);
    }
  }
  return good(req, { imports: [], named: [...out].sort() });
};

// ---- any other extension: a line regex over the text with comments and strings blanked ----

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const readRegex = (req, text, files) => {
  if (req.op === 'loads' && SHELL_EXT.test(req.file)) return shellLoads(req, text, files);
  if (req.op === 'uses' || req.op === 'loads') return fail(req, `a ${req.op} fact is read for Python and JavaScript files, and ${req.file} is neither`);
  // The blanked text keeps every offset, so a match there names the same span of the original, where a string value is still text.
  // A shell file has its own scanner (blankShell): a string may span lines, `#` opens a comment only at the start of a word, and a heredoc body is text.
  // Another `#` file blanks each full-line `#` comment first: the C-style scanner would read a lone quote in it as a string that hides real code.
  const hashBlanked = () => (HASH_COMMENT_EXT.test(req.file) ? text.replace(/^[ \t]*#.*$/gm, (m) => ' '.repeat(m.length)) : text);
  const blank = SHELL_EXT.test(req.file) ? blankShell(text) : blankCommentsAndStrings(hashBlanked(), req.file);
  const re = new RegExp(`^[ \\t]*(?:(?:export\\s+)?(?:let|const|var|readonly|static|final)\\s+)?${escapeRe(req.symbol)}\\s*(?::[^=\\n]*)?=(?!=)[ \\t]*([^\\n]*)$`, 'gm');
  let last = null;
  for (const m of blank.matchAll(re)) last = m;
  if (!last) return gone(req);
  if (req.op === 'defines') return good(req, true);
  const start = last.index + last[0].length - last[1].length;
  const end = start + last[1].trimEnd().length;
  const raw = text.slice(start, end).replace(/[;,]$/, '').trim();
  try { return good(req, JSON.parse(raw)); } catch { return fail(req, `${req.file} ${req.symbol} is not a literal: ${raw.slice(0, 40)}`); }
};

// ---- .py ----

const readPython = (reqs, root, tracked) => {
  const unknown = (reason) => reqs.map((r) => fail(r, reason));
  const input = JSON.stringify({ root, tracked, requests: reqs.map((r) => ({ file: r.file, op: r.op ?? 'value', symbol: r.symbol ?? null, target: r.target })) });
  const r = spawnSync('python3', ['-I', PY_FACTS], { input, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, windowsHide: true });
  if (r.error) return unknown(r.error.code === 'ENOENT' ? 'python3 not found' : `python3 did not run: ${r.error.message}`);
  if (r.status !== 0) return unknown(`python3 failed: ${(r.stderr ?? '').trim().split('\n').pop() || `exit ${r.status}`}`);
  let out;
  try { out = JSON.parse(r.stdout); } catch { return unknown('python3 answered no JSON'); }
  return reqs.map((req, i) => (out[i].ok ? good(req, out[i].value) : fail(req, out[i].reason, out[i].gone === true)));
};

// ---- the one entry ----

/**
 * One result for each request, in order. Every Python request of the call goes to one `python3` start, and a call with
 * none starts no process. `tracked` (the tracked files of `root`) is needed by a `uses` or `loads` request.
 */
export const readFacts = (requests, root, { tracked = [] } = {}) => {
  const results = new Array(requests.length);
  const files = new Set(tracked);
  const py = [];
  requests.forEach((req, i) => {
    if (req.file.endsWith('.py')) { py.push(i); return; }
    let text;
    try { text = readFileSync(path.join(root, req.file), 'utf8'); } catch (e) { results[i] = fail(req, `${req.file} cannot be read: ${e.code ?? e.message}`); return; }
    try {
      results[i] = req.file.endsWith('.json') ? readJson(req, text) : TS_EXT.test(req.file) ? readTs(req, text, files) : readRegex(req, text, files);
    } catch (e) {
      results[i] = fail(req, `${req.file} could not be read: ${e.message}`);
    }
  });
  if (py.length) readPython(py.map((i) => requests[i]), root, tracked).forEach((res, k) => { results[py[k]] = res; });
  return results;
};

/** The value of each { file, symbol } request, in order. See the header for the result shape. */
export const readValues = (requests, root) => readFacts(requests.map(({ file, symbol }) => ({ file, symbol })), root);

// The one home of the value readers behind the map's fact lines (MAP9). Each language is read by its own parser:
//   .py                    scripts/lib/py-facts.py, one `python3 -I` start for every Python request of a call
//   .json                  JSON.parse and a dotted path, with `[*]` to fan out over a list
//   .ts .tsx .mjs .js ...  the typescript parser, through lazy-typescript.mjs, module-level declarations only
//   any other extension    a line regex over the text with comments AND strings blanked. It is no parser: a stated limit.
// A request is { file, symbol } for a value. Internal callers add `op`: 'defines' (is the symbol bound at module level)
// or 'uses' (does `file` import the tracked file `target`, and refer to `symbol`).
// A result is { file, symbol, ok: true, value } or { file, symbol, ok: false, reason, gone? }. `gone: true` means the file was
// read and the symbol is not in it. A failure without `gone` is unknown: the caller must never read it as a pass.
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from './lazy-typescript.mjs';
import { importTargets } from './import-reader.mjs';
import { blankCommentsAndStrings } from './source-text.mjs';

const PY_FACTS = fileURLToPath(new URL('./py-facts.py', import.meta.url));
const TS_EXT = /\.(?:ts|tsx|mts|cts|mjs|cjs|js|jsx)$/;
// A file whose `#` starts a comment. The scanner below reads C-style comments, so a full-line `#` is blanked here.
const HASH_COMMENT_EXT = /\.(?:sh|bash|zsh|ps1|rb|toml|ya?ml|conf|mk)$/;

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
  if (req.op === 'uses') return fail(req, `a uses fact is read for Python and JavaScript files, and ${req.file} is JSON`);
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

const identifiers = (sf) => {
  const names = new Set();
  const visit = (n) => {
    if (ts.isImportDeclaration(n)) return;
    if (ts.isIdentifier(n)) names.add(n.text);
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return names;
};

const readTs = (req, text, tracked) => {
  let sf;
  try { sf = ts.createSourceFile(req.file, text, ts.ScriptTarget.Latest, true); } catch (e) { return fail(req, `${req.file} cannot be parsed: ${e.message}`); }
  if (req.op === 'uses') {
    const imports = importTargets(req.file, text, new Set(tracked)).includes(req.target);
    return good(req, { imports, uses: req.symbol == null ? null : identifiers(sf).has(req.symbol) });
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

// ---- any other extension: a line regex over the text with comments and strings blanked ----

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const readRegex = (req, text) => {
  if (req.op === 'uses') return fail(req, `a uses fact is read for Python and JavaScript files, and ${req.file} is neither`);
  // The blanked text keeps every offset, so a match there names the same span of the original, where a string value is still text.
  let blank = blankCommentsAndStrings(text, req.file);
  if (HASH_COMMENT_EXT.test(req.file)) blank = blank.replace(/^[ \t]*#.*$/gm, (m) => ' '.repeat(m.length));
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
 * none starts no process. `tracked` (the tracked files of `root`) is needed by a `uses` request on a Python file only.
 */
export const readFacts = (requests, root, { tracked = [] } = {}) => {
  const results = new Array(requests.length);
  const py = [];
  requests.forEach((req, i) => {
    if (req.file.endsWith('.py')) { py.push(i); return; }
    let text;
    try { text = readFileSync(path.join(root, req.file), 'utf8'); } catch (e) { results[i] = fail(req, `${req.file} cannot be read: ${e.code ?? e.message}`); return; }
    try {
      results[i] = req.file.endsWith('.json') ? readJson(req, text) : TS_EXT.test(req.file) ? readTs(req, text, tracked) : readRegex(req, text);
    } catch (e) {
      results[i] = fail(req, `${req.file} could not be read: ${e.message}`);
    }
  });
  if (py.length) readPython(py.map((i) => requests[i]), root, tracked).forEach((res, k) => { results[py[k]] = res; });
  return results;
};

/** The value of each { file, symbol } request, in order. See the header for the result shape. */
export const readValues = (requests, root) => readFacts(requests.map(({ file, symbol }) => ({ file, symbol })), root);

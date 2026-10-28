// Plain English is the master copy of what the code does, and a check keeps `docs/map/` in sync with it.
//
// Run `node <skill>/scripts/map-check.mjs` from a repository root to run the 8 MAP checks there.
// The check bodies live here, in `mapChecks`. A host may register each one with its own check.
//
// `migrationTables` strips SQL `--` comments first (`stripSqlComments` below — `ctx.stripComments`
// is a JS/TS scanner and does not know SQL's `--` syntax, so it is not reused here), so a migration
// comment that happens to say "ten CREATE TABLE statements" is never read as a table named
// `statements`. `docs/map/` carries no such fake line.
import { execFileSync } from 'node:child_process';
import { readFileSync, realpathSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from './lib/lazy-typescript.mjs';
import { blankComments, blankCommentsAndStrings } from './lib/source-text.mjs';
import { importTargets } from './lib/import-reader.mjs';
import { boundSeamReader, loadMapConfig, repoMapConfig, validateMapConfig } from './lib/map-config.mjs';

// The pin reader and the call-site reader of the model calls are injected by the host, so this file imports
// only node builtins and its own helpers in `./lib/`. Call `bindConfig({ pinTable, seamSites })` once before a reader that needs them.
// The validator has its own binding, `bindSeamReader` in `./lib/map-config.mjs`. The command binds none of them, and then the validator skips its `modelSeam` call-site check.
let config = null;
export const bindConfig = (readers) => { config = readers; };
// The pins of { path: text }, by name. the host's own reader of pin constants.
const pinTable = (...a) => config.pinTable(...a);
// The model-call sites of { path: text }. the host's own reader of them.
const seamSites = (...a) => config.seamSites(...a);

// The one list of code extensions, from `codeExtensions` (required in every config, and checked to be plain words). MAP1 and MAP2 both read it.
// No module state holds it: the regex is built from the validated config on each call.
export const extRe = (cfg) => new RegExp(`\\.(${cfg.codeExtensions.join('|')})$`);

// Every code file this project tracks: any tracked path with a code extension, wherever it sits.
export const trackedCodeFiles = (allFiles, cfg = repoMapConfig()) => {
  const re = extRe(validateMapConfig(cfg));
  return allFiles.filter((f) => re.test(f));
};

const extractSection = (text, headingTest) => {
  const lines = text.split('\n');
  const out = [];
  let inSection = false;
  for (const line of lines) {
    if (/^#{1,6}\s+/.test(line)) {
      inSection = headingTest(line);
      continue;
    }
    if (inSection) out.push(line);
  }
  return out;
};

const LIST_ITEM_TOKEN_RE = /^[ \t]*[-*+]\s+`([^`]+)`/;

const listTokens = (lines) => {
  const found = [];
  for (const line of lines) {
    const m = line.match(LIST_ITEM_TOKEN_RE);
    if (m) found.push(m[1]);
  }
  return found;
};

// Reads every code file path a docs/map/ file lists.
// With no second argument it reads the validated repo config. A second argument that is present and not a RegExp throws.
export const mapCodePaths = (text, re) => {
  if (re !== undefined && !(re instanceof RegExp)) throw new TypeError('mapCodePaths: the second argument must be a RegExp');
  const use = re ?? extRe(repoMapConfig());
  return listTokens(text.split('\n')).filter((t) => use.test(t));
};

// Reads every table name listed under a docs/map/ file's "Tables" heading.
export const mapTableNames = (text) => listTokens(extractSection(text, (h) => /\btables\b/i.test(h)));

// Reads every screen key listed under a docs/map/ file's "Screens" heading.
export const mapScreenKeys = (text) => listTokens(extractSection(text, (h) => /\bscreens\b/i.test(h)));

/** A SQL `--` line comment, blanked to end of line. No block-comment form is used in this schema. */
const stripSqlComments = (sql) => sql.replace(/--.*$/gm, '');

// Every table name a set of migration files creates.
export const migrationTables = (migrationSources) => {
  const names = new Set();
  for (const sql of migrationSources) {
    const stripped = stripSqlComments(sql);
    for (const m of stripped.matchAll(/CREATE TABLE\s+(?:IF NOT EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)/gi)) {
      names.add(m[1]);
    }
  }
  return [...names].sort();
};

// Every screen key that `SCREEN_KEYS` holds in a source file, such as src/utils/screens.ts.
// It parses the `SCREEN_KEYS` statement and follows each spread to the array it names, through
// `X.map((i) => i.key)` and `X.flatMap((g) => g.rows)`. A spread it cannot follow throws: never a partial list.
export const screenKeysFromSource = (source, constName) => {
  const file = ts.createSourceFile('screens.ts', source, ts.ScriptTarget.Latest, true);
  const decls = new Map();
  for (const st of file.statements)
    if (ts.isVariableStatement(st))
      for (const d of st.declarationList.declarations) if (ts.isIdentifier(d.name) && d.initializer) decls.set(d.name.text, d.initializer);
  const fail = (what) => {
    throw new Error(`screenKeysFromSource: cannot resolve ${what} in the ${constName} statement`);
  };
  const bare = (x) => (ts.isParenthesizedExpression(x) || ts.isAsExpression(x) || ts.isTypeAssertionExpression(x) || ts.isSatisfiesExpression(x) ? bare(x.expression) : x);
  const text = (x) => {
    const v = x && bare(x);
    return v && (ts.isStringLiteral(v) || ts.isNoSubstitutionTemplateLiteral(v)) ? v.text : null;
  };
  const prop = (obj, name) => obj.properties.find((p) => ts.isPropertyAssignment(p) && (ts.isIdentifier(p.name) || ts.isStringLiteral(p.name)) && p.name.text === name)?.initializer;
  // The property a callback reads: `(i) => i.key`.
  const member = (fn) => {
    const b = ts.isArrowFunction(fn) ? bare(fn.body) : null;
    return b && ts.isPropertyAccessExpression(b) ? b.name.text : fail('a callback that is not `(x) => x.name`');
  };
  // The element expressions of an array expression.
  const elements = (x) => {
    const v = bare(x);
    if (ts.isArrayLiteralExpression(v)) return v.elements;
    if (ts.isIdentifier(v)) return decls.has(v.text) ? elements(decls.get(v.text)) : fail(v.text);
    if (ts.isCallExpression(v) && ts.isPropertyAccessExpression(v.expression) && v.expression.name.text === 'flatMap' && v.arguments[0]) {
      const name = member(v.arguments[0]);
      return elements(v.expression.expression).flatMap((o) => (ts.isObjectLiteralExpression(bare(o)) && prop(bare(o), name) ? elements(prop(bare(o), name)) : fail(`'${name}' of a row`)));
    }
    return fail(v.getText(file));
  };
  const keys = (x) => {
    const v = bare(x);
    if (!ts.isArrayLiteralExpression(v)) return fail(v.getText(file));
    return v.elements.flatMap((e) => {
      if (!ts.isSpreadElement(e)) return text(e) ?? fail(e.getText(file));
      const c = bare(e.expression);
      if (!(ts.isCallExpression(c) && ts.isPropertyAccessExpression(c.expression) && c.expression.name.text === 'map' && c.arguments[0])) return fail(c.getText(file));
      const name = member(c.arguments[0]);
      return elements(c.expression.expression).map((o) => (ts.isObjectLiteralExpression(bare(o)) ? text(prop(bare(o), name)) : null) ?? fail(`a '${name}' string`));
    });
  };
  return decls.has(constName) ? keys(decls.get(constName)) : fail(`${constName} (not found)`);
};

const TRACE_STEP_RE = /^[ \t]*\d+\.\s+`([^`]+)`/;

// The lines of a page outside a ``` fence, each with its 1-based line number.
const unfenced = (text) => {
  let inFence = false;
  return text.split('\n').flatMap((l, i) => {
    if (/^\s*```/.test(l)) {
      inFence = !inFence;
      return [];
    }
    return inFence ? [] : [[i + 1, l]];
  });
};

// An unclosed fence hides the rest of the page, so it is an error. It names the opening line.
const unclosedFence = (text) => {
  let open = 0;
  text.split('\n').forEach((l, i) => {
    if (/^\s*```/.test(l)) open = open ? 0 : i + 1;
  });
  return open ? [`line ${open}: unclosed ${'`'.repeat(3)} fence`] : [];
};

// Reads the backticked path of each numbered item in a trace page, in order. A fenced line is no step.
export const traceSteps = (text) =>
  unfenced(text).flatMap(([, l]) => {
    const m = l.match(TRACE_STEP_RE);
    return m ? [m[1]] : [];
  });

// A numbered-looking line that is not in the one step form, so MAP5 would not read it.
export const stepFormErrors = (text) =>
  unfenced(text)
    .flatMap(([n, l]) => (/^\s*\d+[.)](?=\s|`)/.test(l) && !TRACE_STEP_RE.test(l) ? [`line ${n}: ${l.trim()}`] : []))
    .concat(unclosedFence(text));

// The `##` heading texts that have no step before the next `##`.
export const actionsWithoutStep = (text) => {
  const out = [];
  let open = null;
  for (const [, l] of unfenced(text)) {
    const h = l.match(/^##\s+(.*\S)/);
    if (h) {
      if (open !== null) out.push(open);
      open = h[1];
    } else if (open !== null && TRACE_STEP_RE.test(l)) open = null;
  }
  if (open !== null) out.push(open);
  return out;
};

// ---- MAP8: an earlier step of the same action must reach each step ----

// One parse for each file, shared by every reader below.
const parses = new Map();
const parse = (file, source) => {
  const key = `${file}\0${source}`;
  if (!parses.has(key)) parses.set(key, ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true));
  return parses.get(key);
};

const TEMPLATE_REF_RE = /\$\{\s*([A-Za-z_$][\w$]*)\s*\}/g;
const isText = (e) => ts.isStringLiteral(e) || ts.isNoSubstitutionTemplateLiteral(e) || ts.isTemplateExpression(e);

// The strings a node can be: a literal, or a conditional of those, nested. Null for anything else.
const literals = (x) => {
  if (ts.isParenthesizedExpression(x)) return literals(x.expression);
  if (ts.isStringLiteral(x) || ts.isNoSubstitutionTemplateLiteral(x)) return [x.text];
  const [a, b] = ts.isConditionalExpression(x) ? [literals(x.whenTrue), literals(x.whenFalse)] : [];
  return a && b ? [...a, ...b] : null;
};

// True when a node can only be an empty string or a text that starts with `?`: a query. A name is looked up as the
// nearest `const` of that name in an enclosing block, and the check reads its initializer.
const isQuery = (x) => {
  if (!x) return false;
  if (ts.isParenthesizedExpression(x)) return isQuery(x.expression);
  if (ts.isStringLiteral(x) || ts.isNoSubstitutionTemplateLiteral(x)) return x.text === '' || x.text.startsWith('?');
  if (ts.isTemplateExpression(x)) return x.head.text.startsWith('?');
  if (ts.isConditionalExpression(x)) return isQuery(x.whenTrue) && isQuery(x.whenFalse);
  if (!ts.isIdentifier(x)) return false;
  // The first declaration of the name, of any kind, decides: only a plain `const` can be a query.
  for (let up = x.parent; up; up = up.parent) {
    if (!scopeNames(up).includes(x.text)) continue;
    const d = (up.statements ?? []).filter(ts.isVariableStatement).flatMap((st) => (st.declarationList.flags & ts.NodeFlags.Const ? [...st.declarationList.declarations] : [])).find((v) => ts.isIdentifier(v.name) && v.name.text === x.text);
    return !!d && d.initializer !== x && isQuery(d.initializer);
  }
  return false;
};

// The names of the substitutions of a template that sit in the path: those before the first `?` in a literal.
const pathNames = (e) => {
  if (e.head.text.includes('?')) return [];
  const out = [];
  for (const s of e.templateSpans) {
    if (ts.isIdentifier(s.expression)) out.push(s.expression.text);
    if (s.literal.text.includes('?')) break;
  }
  return out;
};

// A template as paths, built from its nodes: the literal parts, with each substitution given by `sub` as its
// options and whether it is unresolved. The query starts at the first `?` in a literal part. A last unresolved
// substitution glued to a path is a query string: it is dropped. With no literal in its segment, as in
// `${API}${p}`, the path is not known, so it is left out.
const MAX_PATHS = 64;
const templatePaths = (e, sub, wide = true) => {
  const cut = (t) => { const q = t.indexOf('?'); return q < 0 ? [t, false] : [t.slice(0, q), true]; };
  const [head, headDone] = cut(e.head.text);
  let states = [{ v: head, lit: head.length, glued: null, done: headDone }];
  for (const s of e.templateSpans) {
    const got = sub(s.expression);
    const { opts, open, query } = wide || got.opts.length < 2 ? got : { opts: ['${}'], open: true };
    const [lit, litDone] = cut(s.literal.text);
    states = states.flatMap((st) => (st.done ? [st] : query ? [{ ...st, done: true, glued: null }] : opts.map((o) => {
      const gluedAt = open && st.v && !st.v.endsWith('/') ? (st.lit > st.v.lastIndexOf('/') + 1 ? st.v.length : -1) : null;
      return { v: st.v + o + lit, lit: lit ? st.v.length + o.length + lit.length : st.lit, glued: lit ? null : gluedAt, done: litDone };
    })));
    if (wide && states.length > MAX_PATHS) return templatePaths(e, sub, false);
  }
  return states.flatMap((st) => (st.glued === -1 ? [] : [st.glued === null ? st.v : st.v.slice(0, st.glued)]));
};

// One argument node as paths: a string, a template or a constant. A `${const}` resolves, and a conditional of
// literals gives one path for each. An unresolved name stays as `${name}`, and any other substitution is `${}`.
// The query string is cut. Anything that does not start with `/` after that did not resolve, so it is left out.
const pathsOf = (e, consts, fns = {}) => {
  let v = [];
  const named = (x, found) => {
    const alts = !ts.isIdentifier(x) && literals(x);
    return found !== undefined ? { opts: [found], open: false } : isQuery(x) ? { opts: [], open: false, query: true } : alts ? { opts: alts, open: false } : { opts: [ts.isIdentifier(x) ? `\${${x.text}}` : '${}'], open: true };
  };
  if (ts.isCallExpression(e) && ts.isIdentifier(e.expression) && fns[e.expression.text]) {
    // A call of a function constant: its body, with each parameter that names a path argument filled in.
    const { params, body } = fns[e.expression.text];
    const arg = (x) => {
      const i = ts.isIdentifier(x) ? params.indexOf(x.text) : -1;
      return i >= 0 && e.arguments[i] ? asPath(e.arguments[i], consts, fns) ?? undefined : undefined;
    };
    v = ts.isTemplateExpression(body) ? templatePaths(body, (x) => named(x, arg(x))) : [body.text.split('?')[0]];
  } else if (ts.isTemplateExpression(e)) v = templatePaths(e, (x) => named(x, ts.isIdentifier(x) ? consts[x.text] : undefined));
  else if (ts.isStringLiteral(e) || ts.isNoSubstitutionTemplateLiteral(e)) v = [e.text.split('?')[0]];
  else if (ts.isIdentifier(e)) v = consts[e.text] === undefined ? [] : [consts[e.text].split('?')[0]];
  return v.filter((x) => x.startsWith('/'));
};
const asPath = (e, consts, fns = {}) => pathsOf(e, consts, fns)[0] ?? null;

// Each `const NAME = <initializer>` of a parsed file.
const constDecls = (sf) => {
  const out = [];
  kids(sf, (n) => {
    if (ts.isVariableDeclaration(n) && n.parent.flags & ts.NodeFlags.Const && ts.isIdentifier(n.name) && n.initializer) out.push(n);
  });
  return out;
};

// The string constants a source declares: `const NAME = '...'`, or a template that uses an earlier one.
const stringConsts = (sf, seed = {}) => {
  const out = { ...seed };
  const decls = constDecls(sf).filter((d) => isText(d.initializer));
  for (let pass = 0; pass < 3; pass++)
    for (const d of decls) {
      const e = d.initializer.getText().slice(1, -1);
      out[d.name.text] = ts.isTemplateExpression(d.initializer) ? e.replace(TEMPLATE_REF_RE, (x, n) => out[n] ?? x) : e;
    }
  return out;
};

// The function constants that build a path: `const NAME = (a, b): string => `...``. Each has its parameter names and its text.
const fnConsts = (sf) => {
  const out = {};
  for (const d of constDecls(sf))
    if (ts.isArrowFunction(d.initializer) && isText(d.initializer.body))
      out[d.name.text] = { params: d.initializer.parameters.map((p) => p.name.getText()), body: d.initializer.body };
  return out;
};

// The `var` names in a function or a file: a `var` belongs to the nearest function, not to its block.
const varNames = (n, out = []) => {
  ts.forEachChild(n, (c) => {
    if (ts.isFunctionLike(c)) return;
    if (ts.isVariableDeclarationList(c) && !(c.flags & ts.NodeFlags.BlockScoped)) c.declarations.forEach((d) => out.push(...bindNames(d.name)));
    varNames(c, out);
  });
  return out;
};
const kids = (n, f) => { f(n); ts.forEachChild(n, (c) => kids(c, f)); };
const bindNames = (n) => (ts.isIdentifier(n) ? [n.text] : n.elements.flatMap((e) => (ts.isOmittedExpression(e) ? [] : bindNames(e.name))));
const hasKeyword = (n, kind) => (ts.getModifiers(n) ?? []).some((m) => m.kind === kind);

// The names a node declares for the code inside it: parameters, block-level declarations, loop and catch variables.
const scopeNames = (n) => {
  const out = [];
  if (ts.isFunctionLike(n)) { n.parameters.forEach((p) => out.push(...bindNames(p.name))); if (ts.isFunctionExpression(n) && n.name) out.push(n.name.text); }
  for (const st of ts.isCaseBlock(n) ? n.clauses.flatMap((c) => c.statements) : n.statements ?? [])
    if (ts.isVariableStatement(st) && st.declarationList.flags & ts.NodeFlags.BlockScoped) st.declarationList.declarations.forEach((d) => out.push(...bindNames(d.name)));
    else if ((ts.isFunctionDeclaration(st) || ts.isClassDeclaration(st)) && st.name) out.push(st.name.text);
  if ((ts.isForStatement(n) || ts.isForInStatement(n) || ts.isForOfStatement(n)) && n.initializer && ts.isVariableDeclarationList(n.initializer) && n.initializer.flags & ts.NodeFlags.BlockScoped)
    n.initializer.declarations.forEach((d) => out.push(...bindNames(d.name)));
  if (ts.isFunctionLike(n) || ts.isSourceFile(n)) out.push(...varNames(n));
  if (ts.isCatchClause(n) && n.variableDeclaration) out.push(...bindNames(n.variableDeclaration.name));
  return out;
};

// The top-level declarations of a parsed file, each with the names it is exported by (`out`): `export`,
// `export default`, and a later `export { a, b as c }`. A declaration is a const, a function or a class.
const topDecls = (sf) => {
  const decls = [];
  for (const st of sf.statements) {
    const out = hasKeyword(st, ts.SyntaxKind.ExportKeyword);
    if (ts.isVariableStatement(st))
      st.declarationList.declarations.forEach((d) => { if (ts.isIdentifier(d.name)) decls.push({ local: d.name.text, node: d, out: out ? [d.name.text] : [] }); });
    else if (ts.isFunctionDeclaration(st) || ts.isClassDeclaration(st)) {
      const dflt = hasKeyword(st, ts.SyntaxKind.DefaultKeyword);
      decls.push({ local: st.name?.text ?? 'default', node: st, out: out ? [dflt ? 'default' : st.name.text] : [] });
    }
  }
  const named = (local, as) => decls.find((d) => d.local === local)?.out.push(as);
  for (const st of sf.statements) {
    if (ts.isExportAssignment(st) && ts.isIdentifier(st.expression)) named(st.expression.text, 'default');
    else if (ts.isExportDeclaration(st) && !st.moduleSpecifier && st.exportClause && ts.isNamedExports(st.exportClause))
      st.exportClause.elements.forEach((e) => named((e.propertyName ?? e.name).text, e.name.text));
  }
  return decls;
};

// True when an identifier inside `root` is a value use of a name: not a declaration, a property key or
// member name, a type, or a local that shadows the name.
const isUse = (id, root) => {
  const p = id.parent;
  if ((p.name === id && !ts.isShorthandPropertyAssignment(p)) || p.propertyName === id || (ts.isQualifiedName(p) && p.right === id)) return false;
  for (let n = id.parent; n && id !== root; n = n.parent) {
    if ((ts.isTypeNode(n) && !(ts.isExpressionWithTypeArguments(n) && ts.isHeritageClause(n.parent))) || scopeNames(n).includes(id.text)) return false;
    if (n === root) break;
  }
  return true;
};

// Each call is { from, path, fn?, via? }. `fn` is the first exported name of the top-level declaration that holds
// the fetch. `via` holds the other exported names that reach it: a second name of the same declaration, and
// each exported declaration that uses it, followed until no new name appears. An importer of `via` reaches
// the call. A call that nothing exports has neither. The file is parsed once: a `fetch(` in a string is no node.
export const clientCalls = (file, source, consts = {}) => {
  const sf = parse(file, source);
  const k = stringConsts(sf, consts);
  const fns = fnConsts(sf);
  const decls = topDecls(sf);
  const holder = (n) => decls.find((d) => d.node.pos <= n.pos && n.end <= d.node.end);
  const callers = new Map(decls.map((d) => [d, []]));
  for (const d of decls)
    kids(d.node, (n) => {
      if (!ts.isIdentifier(n) || n === d.node.name) return;
      const t = decls.find((x) => x !== d && x.local === n.text);
      if (t && isUse(n, d.node) && !callers.get(t).includes(d)) callers.get(t).push(d);
    });
  const info = (n) => {
    const d = holder(n);
    if (!d) return {};
    const seen = new Set([d]);
    for (const q = [d]; q.length; ) for (const o of callers.get(q.shift())) if (!seen.has(o)) { seen.add(o); q.push(o); }
    const fn = d.out[0];
    const via = [...new Set([...seen].flatMap((x) => x.out))].filter((x) => x !== fn);
    return { ...(fn ? { fn } : {}), ...(via.length ? { via } : {}) };
  };
  const found = [];
  const calls = [];
  kids(sf, (n) => { if (ts.isCallExpression(n)) calls.push(n); });
  for (const n of calls) {
    const f = n.expression;
    const isFetch = (ts.isIdentifier(f) && f.text === 'fetch') || (ts.isPropertyAccessExpression(f) && f.name.text === 'fetch' && ts.isIdentifier(f.expression) && /^(window|globalThis)$/.test(f.expression.text));
    if (!isFetch || !n.arguments[0]) continue;
    // A helper that fetches its own parameters, bare or inside the template: fill each from the literal argument of each call.
    const first = n.arguments[0];
    const names = ts.isIdentifier(first) ? [first.text] : ts.isTemplateExpression(first) ? pathNames(first) : [];
    let fnNode = null;
    for (let up = n.parent; up && !fnNode; up = up.parent)
      if (ts.isFunctionLike(up) && up.parameters.some((q) => ts.isIdentifier(q.name) && names.includes(q.name.text)) && (up.name ?? (ts.isVariableDeclaration(up.parent) ? up.parent.name : null))) fnNode = up;
    const name = fnNode && (fnNode.name ?? fnNode.parent.name);
    // A call is a caller of the helper only when the nearest scope that declares the name is the helper's own.
    const home = (x) => { for (let up = x.parent; up; up = up.parent) if (scopeNames(up).includes(name.text)) return up; };
    const mine = calls.filter((c) => name && ts.isIdentifier(name) && ts.isIdentifier(c.expression) && c.expression.text === name.text && home(c) === home(fnNode));
    const here = [];
    let other = !fnNode;
    for (const c of mine) {
      let fills = [{}];
      for (const [at, q] of (fnNode?.parameters ?? []).entries()) {
        if (!ts.isIdentifier(q.name) || !names.includes(q.name.text)) continue;
        const a1 = c.arguments[at];
        const lit = a1 && (literals(a1) ?? pathsOf(a1, k, fns));
        if (lit?.length) fills = fills.flatMap((f) => lit.map((l) => ({ ...f, [q.name.text]: l })));
      }
      if (!Object.keys(fills[0]).length) other = true;
      else for (const f of fills) for (const hp of pathsOf(first, { ...k, ...f }, fns)) here.push({ from: file, path: hp, ...info(c) });
    }
    // Over the cap, the calls give way to the path as written. It is also the path of a call that gives no literal. A bare parameter has none.
    if (new Set(here.map((h) => h.path)).size > MAX_PATHS) other = true;
    else found.push(...here);
    if (other || (!mine.length && !ts.isIdentifier(first))) for (const p of pathsOf(first, k, fns)) found.push({ from: file, path: p, ...info(n) });
  }
  return found;
};

// Import links that run at run time. The one reader drops the type links.
export const runtimeLinks = (file, source, tracked) => {
  return importTargets(file, source, tracked, { types: false });
};

// Each import, `export ... from` and `import(...)` of a parsed file that brings a run-time name, with the
// tracked file it names. The one import reader (`runtimeLinks`) resolves the file and drops the type links.
// `whole` is true when the file is brought whole: a default or `* as` import, a side-effect, dynamic or
// `export` form. `named` holds the exported names of a `{ a, b as c }` import. `locals` holds the local names.
const importStatements = (sf, file, tracked) => {
  const out = [];
  kids(sf, (n) => {
    const dynamic = ts.isCallExpression(n) && n.expression.kind === ts.SyntaxKind.ImportKeyword;
    if (!dynamic && !((ts.isImportDeclaration(n) || ts.isExportDeclaration(n)) && n.moduleSpecifier)) return;
    const [target] = runtimeLinks(file, n.getText(sf), tracked);
    if (!target) return;
    const c = ts.isImportDeclaration(n) ? n.importClause : undefined;
    const named = c?.namedBindings && ts.isNamedImports(c.namedBindings) ? c.namedBindings.elements.filter((e) => !e.isTypeOnly) : [];
    out.push({
      target,
      whole: !(c && !c.name && c.namedBindings && ts.isNamedImports(c.namedBindings)),
      named: named.map((e) => (e.propertyName ?? e.name).text),
      locals: [c?.name?.text, c?.namedBindings && ts.isNamespaceImport(c.namedBindings) ? c.namedBindings.name.text : null, ...named.map((e) => e.name.text)].filter(Boolean),
    });
  });
  return out;
};

// The names each target is imported by: a Set of exported names, or null when any import of the file
// brings all of it: `import * as`, a default import, a dynamic import, a side-effect import, `export ... from`.
export const importedExports = (src, file, tracked) => {
  const out = new Map();
  for (const { target, whole, named } of importStatements(parse(file, src), file, tracked)) {
    if (whole) { out.set(target, null); continue; }
    if (out.get(target) === null) continue;
    out.set(target, new Set([...(out.get(target) ?? []), ...named]));
  }
  return out;
};

// `uses` holds the tracked files whose imported names the handler meets: in its own code, or in a name
// declared in the same file, in a block that holds the route, followed until no new name appears.
export const serverRoutes = (file, source, consts = {}, tracked = new Set()) => {
  const sf = parse(file, source);
  const k = stringConsts(sf, consts);
  const names = new Map(importStatements(sf, file, tracked).flatMap((i) => i.locals.map((l) => [l, i.target])));
  // Each `function f`, `const f` and `let f`, with the block that holds it.
  const scopeOf = (n) => (ts.isBlock(n) || ts.isSourceFile(n) || ts.isModuleBlock(n) || ts.isCaseBlock(n) ? n : scopeOf(n.parent));
  const decls = [];
  kids(sf, (n) => {
    const id = (ts.isFunctionDeclaration(n) && n.name) || (ts.isVariableDeclaration(n) && n.parent.flags & ts.NodeFlags.BlockScoped && n.name);
    if (id && ts.isIdentifier(id)) decls.push({ name: id.text, node: n, scope: scopeOf(n.parent) });
  });
  const found = [];
  kids(sf, (call) => {
    const f = ts.isCallExpression(call) && call.expression;
    if (!f || !ts.isPropertyAccessExpression(f) || !ts.isIdentifier(f.expression) || f.expression.text !== 'app' || !/^(get|post|put|patch|delete)$/.test(f.name.text)) return;
    const p = call.arguments[0] && asPath(call.arguments[0], k);
    if (!p) return;
    const files = new Set();
    const seen = new Set();
    for (const queue = call.arguments.slice(1); queue.length; ) {
      const root = queue.shift();
      kids(root, (id) => {
        if (!ts.isIdentifier(id) || !isUse(id, root)) return;
        if (names.has(id.text)) files.add(names.get(id.text));
        const here = decls.filter((d) => d.name === id.text && d.scope.pos <= call.pos && call.end <= d.scope.end);
        if (here.length && !seen.has(id.text)) {
          seen.add(id.text);
          queue.push(...here.map((d) => d.node));
          // A `let` is fed by the right-hand sides that fill it: what those use, the route uses.
          for (const d of here) if (ts.isVariableDeclaration(d.node) && d.node.parent.flags & ts.NodeFlags.Let) queue.push(...decls.filter((w) => w.scope === d.scope).flatMap((w) => feeds(w.node, id.text)));
        }
      });
    }
    found.push({ file, path: p, uses: [...files].sort() });
  });
  return found;
};

// The nodes that feed `name`: the right-hand side of each assignment to it (`=`, `+=`, `[name] =`, `({ name } =`),
// and the arguments of a mutating call on it (`name.push(x)`). A writer that declares `name` itself feeds nothing.
const MUTATORS = new Set(['push', 'unshift', 'splice', 'set', 'add', 'fill']);
const feeds = (node, name) => {
  const out = [];
  const rootIs = (x) => (ts.isIdentifier(x) ? x.text === name : (ts.isElementAccessExpression(x) || ts.isPropertyAccessExpression(x)) && rootIs(x.expression));
  const has = (x) => (ts.isIdentifier(x) ? x.text === name : ts.isArrayLiteralExpression(x) ? x.elements.some(has) : ts.isObjectLiteralExpression(x) ? x.properties.some((p) => (ts.isShorthandPropertyAssignment(p) ? p.name.text === name : ts.isPropertyAssignment(p) && has(p.initializer))) : ts.isSpreadElement(x) ? has(x.expression) : false);
  const visit = (n) => {
    if (scopeNames(n).includes(name) || ts.isParameter(n) && ts.isIdentifier(n.name) && n.name.text === name) return; // a local `name` shadows it in this scope only
    if (ts.isBinaryExpression(n) && n.operatorToken.kind >= ts.SyntaxKind.FirstAssignment && n.operatorToken.kind <= ts.SyntaxKind.LastAssignment && (has(n.left) || rootIs(n.left))) out.push(n.right);
    const f = ts.isCallExpression(n) && n.expression;
    if (f && ts.isPropertyAccessExpression(f) && rootIs(f.expression) && MUTATORS.has(f.name.text)) out.push(...n.arguments);
    ts.forEachChild(n, visit);
  };
  visit(node);
  return out;
};

const routeRe = (route) => new RegExp(`^${route.replace(/[.*+?^$()|[\]\\{}]/g, '\\$&').replace(/:[\w$]+/g, '[^/]+')}$`);

// The routes that answer one client call.
export const routesAnswering = (routes, call) => {
  const probe = call.path.replace(/\$\{[^}]*\}/g, 'x');
  return routes.filter((r) => routeRe(r.path).test(probe));
};

// The web calls of the client files and the routes of the server files, from the run-time import links.
// A file takes the string constants of the files it imports. `code` lists the files, `src` holds their sources,
// and `targets` maps each file to its run-time import targets.
export const webCalls = ({ code, src, tracked, targets }) => {
  const exported = Object.fromEntries(code.map((f) => [f, stringConsts(parse(f, src[f]))]));
  const consts = (f) => Object.assign({}, ...targets[f].map((t) => exported[t] ?? {}));
  return {
    routes: code.flatMap((f) => serverRoutes(f, src[f], consts(f), tracked)),
    calls: code.flatMap((f) => clientCalls(f, src[f], consts(f))),
  };
};

// The tracked code file that each package.json script runs after `tsx` or `node`: a separate process. A flag
// and its value are skipped, and a file that registers routes is the server, not a separate process.
export const scriptEntries = (scripts, tracked, routeFiles = [], re = extRe(repoMapConfig())) => {
  const out = new Set();
  for (const cmd of Object.values(scripts))
    for (const part of cmd.split(/&&|\|\||;|\|/)) {
      const w = part.trim().split(/\s+/);
      const at = w.findIndex((x) => /^(tsx|node)$/.test(x));
      if (at < 0) continue;
      const hit = w.slice(at + 1).find((x, i, rest) => !(i > 0 && /^-[^=]*$/.test(rest[i - 1])) && re.test(x) && tracked.has(x));
      if (hit && !routeFiles.includes(hit)) out.add(hit);
    }
  return [...out].sort();
};

/** Reads { traces, links, calls, routes }. Returns each step that no earlier step of its action reaches, with the step before it. */
export const traceGaps = ({ traces, links, calls, routes, entries = [], tables = null }) => {
  // A file that registers a route imports most of the server. Its plain import links do not count: it
  // reaches only the files that the routes called by an earlier step use.
  const routeFiles = new Set(routes.map((r) => r.file));
  const next = new Map();
  for (const l of links) if (!routeFiles.has(l.from)) (next.get(l.from) ?? next.set(l.from, []).get(l.from)).push(l.to);
  const chain = (seeds) => {
    const seen = new Set(seeds);
    for (const q = [...seeds]; q.length; ) for (const t of next.get(q.shift()) ?? []) if (!seen.has(t)) { seen.add(t); q.push(t); }
    return seen;
  };
  const answers = (c) => routesAnswering(routes, c);
  // The calls of client file `a` that the steps in `earlier` reach: a client file is reached by name, so
  // only the functions an earlier step imports by name make calls. A whole-file import reaches them all.
  const callsOf = (a, earlier) => {
    const into = links.filter((l) => l.to === a && l.from !== a && earlier.includes(l.from));
    const only = into.length && into.every((l) => l.names) ? new Set(into.flatMap((l) => l.names)) : null;
    return calls.filter((c) => c.from === a && (!only || (!c.fn && !c.via) || only.has(c.fn) || c.via?.some((n) => only.has(n))));
  };
  // `earlier` holds the steps before the one being reached.
  const reaches = (a, b, earlier) => {
    const seeds = [a];
    for (const c of callsOf(a, earlier)) for (const r of answers(c)) seeds.push(r.file, ...(r.uses ?? []));
    if (routeFiles.has(a))
      for (const e of earlier) for (const c of callsOf(e, earlier)) for (const r of answers(c)) if (r.file === a) seeds.push(...(r.uses ?? []));
    return chain(seeds).has(b);
  };
  // A separate process (a file no code file imports) joins an earlier step it imports when both step
  // sentences name the same table in backticks.
  const entry = new Set(entries);
  const tablesOf = (sentence) =>
    new Set([...sentence.matchAll(/`([^`]+)`/g)].map((x) => x[1]).filter((t) => (tables ? tables.includes(t) : true)));
  const sharesTable = (a, b) => [...a].some((t) => b.has(t));
  const gaps = [];
  for (const key of Object.keys(traces).sort()) {
    let action = '';
    let before = [];
    for (const [, line] of unfenced(traces[key])) {
      const h = line.match(/^##\s+(.*)$/);
      if (h) { action = h[1].trim(); before = []; continue; }
      const m = line.match(TRACE_STEP_RE);
      if (!m) continue;
      const step = { path: m[1], tables: tablesOf(line.slice(line.indexOf(' — ') + 3)) };
      const joined = (e) =>
        entry.has(step.path) && links.some((l) => l.from === step.path && l.to === e.path) && sharesTable(e.tables, step.tables);
      // A step is fine when any earlier step of the same action reaches it.
      if (before.length && !before.some((e) => reaches(e.path, step.path, before.map((x) => x.path)) || joined(e)))
        gaps.push({ key, action, from: before[before.length - 1].path, to: step.path });
      before.push(step);
    }
  }
  return gaps;
};

// Finds what is wrong with a set of trace pages. `traces` maps a screen key to its page text.
export const traceFindings = ({ traces, screenKeys, tracked }) => {
  const keys = Object.keys(traces);
  const out = { badSteps: [], missingKeys: [], strayPages: [], emptyPages: [], badForms: [], emptyActions: [] };
  for (const k of keys) {
    const steps = traceSteps(traces[k]);
    if (!steps.length) out.emptyPages.push(k);
    for (const e of stepFormErrors(traces[k])) out.badForms.push(`${k}: ${e}`);
    for (const a of actionsWithoutStep(traces[k])) out.emptyActions.push(`${k}: ${a}`);
    for (const p of steps) if (!tracked.has(p)) out.badSteps.push(`${k}: ${p}`);
    if (!screenKeys.includes(k)) out.strayPages.push(k);
  }
  out.missingKeys = screenKeys.filter((k) => !keys.includes(k));
  for (const v of Object.values(out)) v.sort();
  return out;
};

// A note is a comment line whose comment text opens with the label. Comment text is what
// `blankComments` (the one scanner) blanks, so a label in a string or a template literal is not one.
// The scanner does not know SQL `--`, so a line that opens with `--` and the label counts as well.
const NOTE_RE = /^\s*(?:\/\*\*?|\/\/|\*)?\s*In plain words:/;
// A `.py` or `.sh` file has `#` comments. The JS scanner does not know them, so a line that opens with `#` counts.
const HASH_NOTE_RE = /^\s*#\s*In plain words:/;
const SQL_NOTE_RE =/^\s*--\s*In plain words:/;

const commentText = (text) => {
  const blanked = blankComments(text);
  let out = '';
  for (let i = 0; i < text.length; i++) out += blanked[i] !== text[i] || text[i] === '\n' ? text[i] : ' ';
  return out.split('\n');
};

/** Reads { path: text }. Returns the sorted path:line of each note that opens with the label. */
export const plainWordsNotes = (files) =>
  Object.keys(files)
    .sort()
    .flatMap((path) => {
      const raw = files[path].split('\n');
      if (/\.(py|sh)$/.test(path)) return raw.flatMap((line, i) => (HASH_NOTE_RE.test(line) ? [path + ':' + (i + 1)] : []));
      return commentText(files[path]).flatMap((line, i) =>
        NOTE_RE.test(line) || SQL_NOTE_RE.test(raw[i]) ? [path + ':' + (i + 1)] : []
      );
    });

// ---- The AI calls tab reader. It reads the model-call sites from the generator and the worker stages. No check holds its coverage. ----
// The call sites come from `seamSites` of the generator, read with the parser, so a comment or a string makes no row. The tab adds the
// tier and the effort that a call's own line gives as literals. The seam is the file in `modelSeam.file` of the config, and it is no
// caller. A config with no seam has no rows.
const seamOf = (cfg) => cfg.modelSeam?.file ?? null;
const escapeRe = (t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const isTestPath = (p) => /(^|\/)tests?\/|\.test\./.test(p);
const importsSeam = (code, clean, seam) => {
  const [, base, ext] = /([^/]*?)(\.[^./]+)?$/.exec(seam);
  const isSeam = new RegExp(`(^|/)${escapeRe(base)}(${escapeRe(ext ?? '')})?$`);
  for (const m of code.matchAll(/\b(?:from|import\s*\()\s*(['"])( *)\1/g)) {
    const start = m.index + m[0].length - m[2].length - 1;
    if (isSeam.test(clean.slice(start, start + m[2].length))) return true;
  }
  return false;
};

/** True when a tracked code file, other than the seam and the tests, imports the seam and holds a model-call site of the generator. The validator asks it. */
export const seamHasCallSite = (seam, files, read, readSites) =>
  files.some((p) => {
    if (!/\.(ts|tsx|mjs|js|cjs)$/.test(p) || p === seam || isTestPath(p)) return false;
    const source = read(p);
    return importsSeam(blankCommentsAndStrings(source), blankComments(source), seam) && readSites({ [p]: source }).length > 0;
  });

/** Reads the stage literals a worker records: `<variable> = '<lit>'` and `<callback>('<lit>'`, the names from `workerStage` in the config. The literal may sit on the line after `<callback>(`. A config with no `workerStage` has no stages. */
export const stageSites = (source, cfg = repoMapConfig()) => {
  const stage = validateMapConfig(cfg).workerStage;
  return stage ? stageSitesOf(source, stage) : [];
};

/** The stage sites of one source for one `workerStage` pair. The validator asks it, before a config is valid. */
export const stageSitesOf = (source, stage) => {
  const code = blankCommentsAndStrings(source), clean = blankComments(source);
  const out = [];
  // A name left out of `stage` has no alternative, so no source can satisfy it.
  const alts = [stage.variable && `${escapeRe(stage.variable)}\\s*=(?!=)`, stage.callback && `${escapeRe(stage.callback)}\\s*\\(`].filter(Boolean);
  if (!alts.length) return out;
  for (const m of code.matchAll(new RegExp(`\\b(?:${alts.join('|')})\\s*(['"\`])( *)\\1`, 'g'))) {
    const start = m.index + m[0].length - m[2].length - 1;
    // A template with a `${` is a variable, so it is no literal.
    if (m[1] === '`' && clean.slice(start, start + m[2].length).includes('${')) continue;
    out.push({ step: clean.slice(start, start + m[2].length), line: code.slice(0, start).split('\n').length });
  }
  return out;
};

const callerPaths = (sources, cfg) =>
  Object.keys(sources).filter((p) => /\.(ts|tsx|mjs|js|cjs)$/.test(p) && p !== seamOf(cfg) && !isTestPath(p)).sort();

// ---- The places that start a model call, read from one file ----
const TRANSPORT_RE = /\b\w*[Tt]ransport\b/;
const TRANSPORT_DECL_RE = /\b(?:const|let|var|function)\s+\w*[Tt]ransport\b/;
const lineOf = (sf, pos) => sf.getLineAndCharacterOfPosition(pos).line + 1;
// The nodes that hold a line, outer first.
const around = (sf, line) => {
  const out = [];
  kids(sf, (n) => { if (n !== sf && lineOf(sf, n.getStart(sf)) <= line && line <= lineOf(sf, n.end)) out.push(n); });
  return out;
};

/** A stage makes a model call where its span, from its literal to the next stage's literal, hands a transport on. Returns { step, line }. */
const stageCalls = (source, stages) => {
  const lines = blankCommentsAndStrings(source).split('\n'), out = [];
  // `const gatedTransport = gate(countedTransport(...))` builds a transport. A name inside that initializer is a wrapper, not a call.
  const building = [], sf = parse('stage-calls.ts', source);
  kids(sf, (n) => {
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && TRANSPORT_RE.test(n.name.text) && n.initializer)
      building.push([lineOf(sf, n.initializer.getStart(sf)), lineOf(sf, n.initializer.end)]);
  });
  const inBuild = (l) => building.some(([from, to]) => from <= l && l <= to);
  stages.forEach((s, k) => {
    const end = stages[k + 1]?.line ?? lines.length + 1;
    for (let l = s.line; l < end; l++) {
      if (!TRANSPORT_RE.test(lines[l - 1]) || TRANSPORT_DECL_RE.test(lines[l - 1]) || inBuild(l)) continue;
      if (!out.some((o) => o.step === s.step && o.line === l)) out.push({ step: s.step, line: l });
      break;
    }
  });
  return out;
};

const METERED_RE = /\bmetered\s*\(\s*(['"])([^'"]+)\1/g;

/** The routes of a server file, with the lines that the registration spans: { route, path, from, to }. */
export const routeSpans = (file, source) => {
  if (!/\bapp\s*\.\s*(?:get|post|put|patch|delete)\s*\(/.test(source)) return [];
  const sf = parse(file, source), k = stringConsts(sf), out = [];
  kids(sf, (call) => {
    const f = ts.isCallExpression(call) && call.expression;
    if (!f || !ts.isPropertyAccessExpression(f) || !ts.isIdentifier(f.expression) || f.expression.text !== 'app' || !/^(get|post|put|patch|delete)$/.test(f.name.text)) return;
    const p = call.arguments[0] && asPath(call.arguments[0], k);
    if (p) out.push({ route: `${f.name.text.toUpperCase()} ${p}`, path: p, from: lineOf(sf, call.getStart(sf)), to: lineOf(sf, call.end), uses: call.arguments.slice(1).map((a) => a.getText(sf)).join(',') });
  });
  return out;
};

// One file's rows. A site that sets no step of its own is read three ways, in this order:
// 1. The hook reads `step: currentStep`, so the stage that is running names the step. The stage rows below then give the steps.
// 2. A provider getter, `provider: () => activeProvider()`, joins the step of the call that follows it within four lines.
// 3. A helper that a caller feeds a `metered('<step>')` takes that step.
// A site that none of these names stays a row with no step. The page shows it in the "No step recorded" group.
// A pin is a constant, named in capitals, that holds a tier and an effort as literals, or a table of them such as `CHAT_MODELS`.
// `pinTable` of the host's model-calls reader reads them. It is the one home of that reader.
const sameList = (pins) => {
  const seen = new Set();
  return pins.filter((x) => !seen.has(`${x.tier}/${x.effort}`) && seen.add(`${x.tier}/${x.effort}`)).sort((x, y) => `${x.tier}/${x.effort}`.localeCompare(`${y.tier}/${y.effort}`));
};
// The pins that a function body passes on: `...PIN`, `...TABLE[key]`, or `tier: PIN.tier` and `effort: PIN.effort`.
const pinsIn = (node, pins) => {
  const out = [], part = { tier: null, effort: null };
  kids(node, (n) => {
    if (ts.isSpreadAssignment(n)) {
      const e = ts.isElementAccessExpression(n.expression) ? n.expression.expression : n.expression;
      if (ts.isIdentifier(e) && pins[e.text]) out.push(...pins[e.text]);
    } else if (ts.isPropertyAssignment(n) && /^(tier|effort)$/.test(n.name.getText()) && ts.isPropertyAccessExpression(n.initializer) && ts.isIdentifier(n.initializer.expression) && pins[n.initializer.expression.text]?.length === 1 && n.initializer.name.text === n.name.getText())
      part[n.name.getText()] = pins[n.initializer.expression.text][0][n.name.getText()];
  });
  if (part.tier || part.effort) out.push(part);
  return sameList(out);
};
// Every named function of the caller files, by name: { name: [{ fn, sf }] }. It lets a call reach a pin that another file spreads.
const fnIndexOf = (sources, cfg) => {
  const idx = Object.create(null);
  for (const p of callerPaths(sources, cfg)) {
    const sf = parse(p, sources[p]);
    kids(sf, (n) => {
      let name = null, fn = null;
      if (ts.isFunctionDeclaration(n) && n.name) { name = n.name.text; fn = n; }
      else if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.initializer && ts.isFunctionLike(n.initializer)) { name = n.name.text; fn = n.initializer; }
      if (name) (idx[name] ??= []).push(fn);
    });
  }
  return idx;
};
// Every pin that a function can reach: the pins its own body passes on, and the pins of each function that it hands the transport to.
// A function that gets no transport is not on the path of the call, so its pin is not read. A name that two files define is ambiguous, so it gives no pin.
const calleeName = (n) => (ts.isIdentifier(n.expression) ? n.expression.text : ts.isPropertyAccessExpression(n.expression) ? n.expression.name.text : null);
// `transport`, `deps.transport` and `deps.transport(req)` all hand the transport on.
const isTransportArg = (a) => (ts.isIdentifier(a) && TRANSPORT_RE.test(a.text)) || (ts.isPropertyAccessExpression(a) && TRANSPORT_RE.test(a.name.text)) || (ts.isCallExpression(a) && TRANSPORT_RE.test(calleeName(a) ?? ''));
const reach = (fn, idx, pins, seen = new Set()) => {
  const out = [...pinsIn(fn, pins)];
  const follow = (name) => {
    if (!name || seen.has(name) || idx[name]?.length !== 1) return;
    seen.add(name);
    out.push(...reach(idx[name][0], idx, pins, seen));
  };
  kids(fn, (n) => {
    if (!ts.isCallExpression(n)) return;
    // `fn(…, transport)` hands the transport on. `transport(build(…))` sends what `build` makes.
    if (n.arguments.some(isTransportArg)) follow(calleeName(n));
    if (TRANSPORT_RE.test(calleeName(n) ?? '')) for (const a of n.arguments) if (ts.isCallExpression(a)) follow(calleeName(a));
  });
  return sameList(out);
};
// The function that a stage call hands the transport to, found by name in the same file, and the pins that it reaches.
// A function of another file is found through the index.
const calleePin = (sf, line, pins, idx) => {
  const calls = [];
  kids(sf, (n) => {
    if (ts.isCallExpression(n) && lineOf(sf, n.getStart(sf)) <= line && line <= lineOf(sf, n.end)
      && n.arguments.some((a) => ts.isIdentifier(a) && TRANSPORT_RE.test(a.text))) {
      const callee = ts.isNonNullExpression(n.expression) ? n.expression.expression : n.expression;
      if (ts.isIdentifier(callee)) calls.push(callee.text);
      // `deps.readFile(...)`: the property is typed `readFile?: typeof readFileKind`, so the function is `readFileKind`.
      else if (ts.isPropertyAccessExpression(callee)) kids(sf, (q) => {
        if (ts.isPropertySignature(q) && q.name.getText() === callee.name.text && q.type && ts.isTypeQueryNode(q.type) && ts.isIdentifier(q.type.exprName)) calls.push(q.type.exprName.text);
      });
    }
  });
  const name = calls.at(-1);
  let fn = null;
  if (name) kids(sf, (n) => {
    if (fn) return;
    if (ts.isFunctionDeclaration(n) && n.name?.text === name) fn = n;
    else if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === name && n.initializer && ts.isFunctionLike(n.initializer)) fn = n.initializer;
  });
  if (!fn && name && idx()[name]?.length === 1) fn = idx()[name][0];
  return fn ? reach(fn, idx(), pins) : [];
};
// A call whose registration holds no line of it, such as a `propose` property of an object that a handler takes. It takes the route
// whose handler name holds the property name, when one route does: `propose` and `escalationProposeHandler`.
const routeByHandler = (sf, spans, line) => {
  // The innermost variable that holds an object literal, and the property of that object which holds the line.
  const holder = around(sf, line).reverse().find((n) => ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.initializer && ts.isObjectLiteralExpression(n.initializer));
  const prop = holder?.initializer.properties.find((q) => ts.isPropertyAssignment(q) && ts.isIdentifier(q.name) && lineOf(sf, q.getStart(sf)) <= line && line <= lineOf(sf, q.end));
  if (!prop || !holder) return null;
  const hit = spans.filter((r) => new RegExp(`\\b${holder.name.text}\\b`).test(r.uses) && new RegExp(prop.name.text, 'i').test(r.uses));
  // One matching handler gives its route. Two or more give null, because a wrong route is worse than "route not found".
  return hit.length === 1 ? hit[0].route : null;
};

// A row holds every pin its path can reach. `tier` and `effort` read the pin only when it is the one.
export const pinFields = (pins) => ({ pins, tier: pins.length === 1 ? pins[0].tier : null, effort: pins.length === 1 ? pins[0].effort : null });

const fileRows = (p, source, outside, pins, idx, cfg, found) => {
  const code = blankCommentsAndStrings(source).split('\n');
  const stages = stageSites(source, cfg), lines = blankComments(source).split('\n');
  const literal = (line, key) => lines[line - 1].match(new RegExp(`\\b${key}\\s*:\\s*(['"])(\\w+)\\1`))?.[2] ?? null;
  const sites = found.map(({ line, step }) => ({ line, step, tier: literal(line, 'tier'), effort: literal(line, 'effort') }));
  // The hook of a call reads the running stage: `step: <variable>`.
  const stageHook = cfg.workerStage?.variable ? new RegExp(`\\bstep\\s*:\\s*${escapeRe(cfg.workerStage.variable)}\\b`) : null;
  const needs = sites.some((s) => s.step === null);
  const sf = needs ? parse(p, source) : null;
  const rows = [];
  sites.forEach((s) => {
    if (s.step !== null) return rows.push({ ...s });
    const here = around(sf, s.line);
    const gen = [...here].reverse().find((n) => ts.isCallExpression(n) && ts.isPropertyAccessExpression(n.expression) && n.expression.name.text === 'generateContent');
    if (gen && stageHook?.test(gen.expression.expression.getText(sf))) return;
    const getter = /\bactiveProvider\s*\(\s*\)(?!\s*\.\s*generateContent)/.test(code[s.line - 1] ?? '');
    const next = getter ? sites.find((o) => o.step !== null && o.line > s.line && o.line - s.line <= 4) : null;
    // The getter adds no row. The call that it serves keeps its own row, and takes a tier or effort that only the getter line holds.
    if (next) { next.tier ??= s.tier; next.effort ??= s.effort; return; }
    const helper = [...here].reverse().find((n) => ((ts.isVariableDeclaration(n) && n.initializer && ts.isFunctionLike(n.initializer)) || ts.isFunctionDeclaration(n)) && n.name && ts.isIdentifier(n.name));
    const fed = new Set();
    if (helper) kids(sf, (c) => {
      if (ts.isCallExpression(c) && ts.isIdentifier(c.expression) && c.expression.text === helper.name.text)
        for (const m of c.arguments.map((a) => a.getText(sf)).join(',').matchAll(METERED_RE)) fed.add(m[2]);
    });
    if (!fed.size) return rows.push({ ...s });
    for (const step of [...fed].sort()) rows.push({ ...s, step });
  });
  let parsed = null;
  const sfAll = () => (parsed ??= parse(p, source));
  const calls = stageCalls(source, stages).map(({ step, line }) => ({ line, step, ...pinFields(calleePin(sfAll(), line, pins, idx)) }));
  const spans = routeSpans(p, source);
  const routeOf = (line) => spans.filter((r) => r.from <= line && line <= r.to).sort((a, b) => (a.to - a.from) - (b.to - b.from))[0]?.route
    ?? (spans.length ? routeByHandler(sfAll(), spans, line) : null);
  // A call that sets no tier or effort on its own line takes the pins that the function it serves reaches, in this file or in another.
  const pinned = rows.map((s) => {
    if (s.step === null) return { ...s, ...pinFields(s.tier || s.effort ? [{ tier: s.tier, effort: s.effort }] : []) };
    if (s.tier && s.effort) return { ...s, ...pinFields([{ tier: s.tier, effort: s.effort }]) };
    // A closure gives no pin: the callee that holds the closure may never call it. A site takes only its own pin.
    return { ...s, ...pinFields(s.tier || s.effort ? [{ tier: s.tier, effort: s.effort }] : []) };
  });
  return [
    ...pinned.map((s) => ({ p, ...s, kind: 'call', outside })),
    ...calls.map((s) => ({ p, ...s, kind: 'call', outside })),
    ...stages.map((s) => ({ p, line: s.line, step: s.step, ...pinFields([]), kind: 'stage', outside })),
  ].map((r) => ({ ...r, route: routeOf(r.line) })).sort((a, b) => a.line - b.line);
};

/**
 * The pins of a call that crosses the wire. A route's call has no pin in its own file, because the browser makes the request. So the
 * client files that call the route are read: the functions of them that `fetch`, then the places that call those functions with a request
 * that spreads a pin. `callModel` as a default value is not a call, so a service that only defaults to it adds none.
 */
export const clientPins = (sources, clientFiles, cfg = repoMapConfig()) => {
  cfg = validateMapConfig(cfg);
  const pins = pinTable(sources), names = new Set(), out = [];
  for (const p of clientFiles) if (sources[p]) kids(parse(p, sources[p]), (n) => {
    const fn = ts.isFunctionDeclaration(n) && n.name ? n : ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.initializer && ts.isFunctionLike(n.initializer) ? n.initializer : null;
    let fetches = false;
    if (fn) kids(fn, (c) => { if (ts.isCallExpression(c) && ts.isIdentifier(c.expression) && c.expression.text === 'fetch') fetches = true; });
    if (fetches) names.add(ts.isFunctionDeclaration(n) ? n.name.text : n.name.text);
  });
  if (!names.size) return [];
  for (const p of callerPaths(sources, cfg)) {
    if (clientFiles.includes(p)) continue;
    const sf = parse(p, sources[p]);
    kids(sf, (c) => {
      if (!ts.isCallExpression(c) || !ts.isIdentifier(c.expression) || !names.has(c.expression.text) || !c.arguments[0]) return;
      const a = c.arguments[0];
      if (ts.isObjectLiteralExpression(a)) return void out.push(...pinsIn(a, pins));
      if (!ts.isIdentifier(a)) return;
      // The request is a variable of the function that makes the call.
      const home = around(sf, lineOf(sf, c.getStart(sf))).reverse().find((q) => ts.isFunctionLike(q));
      if (home) kids(home, (d) => { if (ts.isVariableDeclaration(d) && ts.isIdentifier(d.name) && d.name.text === a.text && d.initializer) out.push(...pinsIn(d.initializer, pins)); });
    });
  }
  return sameList(out);
};

/** Reads { path: text }. Returns the rows of the AI calls tab, sorted by file then line: { p, line, step, tier, effort, pins, kind, outside, route }. A stage row has kind "stage"; a place that starts a call has kind "call". */
export const aiCallRows = (sources, cfg = repoMapConfig()) => {
  cfg = validateMapConfig(cfg);
  if (!seamOf(cfg)) return [];
  const pins = pinTable(sources);
  let idx = null;
  const lazyIdx = () => (idx ??= fnIndexOf(sources, cfg));
  const sites = seamSites(sources);
  return callerPaths(sources, cfg).flatMap((p) => {
    const outside = /(^|\/)[^/]*Cli\.[a-z]+$/.test(p) ? 'cli' : null;
    // A file is a caller only when it imports the seam, as `seamHasCallSite` holds. A stage row needs no import.
    const imports = importsSeam(blankCommentsAndStrings(sources[p]), blankComments(sources[p]), seamOf(cfg));
    return fileRows(p, sources[p], outside, pins, lazyIdx, cfg, imports ? sites.filter((s) => s.file === p) : []);
  });
};

// ---- The 8 MAP checks. One home for each body: a host may register them with its own check, and the command below runs them. ----
const TRACE_PAGE_RE = /^docs\/map\/traces\/([^/]+)\.md$/;

/** The files this repository tracks in `root`, from `git ls-files`. */
export const gitLsFiles = (root) =>
  execFileSync('git', ['ls-files'], { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], windowsHide: true })
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);

// Top-level docs/map/*.md only. A trace page under docs/map/traces/ has its own checks, MAP5 and MAP6.
// A bullet under a trace heading that says "tables" or "screens" would else add a fake MAP3 or MAP4 line.
const mapFilePaths = (files) => files.filter((f) => /^docs\/map\/[^/]+\.md$/.test(f));

const skip = (key, what) => ({ skipped: `map.config.json has no "${key}" setting, so there is no ${what} to check` });

/**
 * The bodies of MAP1..MAP8, for one validated config `cfg`, one repository `root` and a `read(file)` of its text. Each body returns true,
 * returns `{ skipped: '<reason>' }`, or throws an error that says what is wrong. `files` is the list of tracked files, read at each call.
 */
export const mapChecks = ({ cfg, root, read, files = () => gitLsFiles(root) }) => {
  const screenKeys = () => {
    const { file, name } = cfg.screenKeys;
    return [...new Set(screenKeysFromSource(read(file), name))];
  };
  const mapTexts = () => mapFilePaths(files()).map((f) => read(f));
  const traceTexts = (all) => {
    const traces = {};
    for (const f of all) {
      const m = f.match(TRACE_PAGE_RE);
      if (m) traces[m[1]] = read(f);
    }
    return traces;
  };
  const traceFindingsNow = () => {
    const all = files();
    return traceFindings({
      traces: traceTexts(all),
      screenKeys: cfg.screenKeys ? screenKeys() : [],
      tracked: new Set(trackedCodeFiles(all, cfg)),
    });
  };

  return {
    MAP1: () => {
      const all = trackedCodeFiles(files(), cfg);
      const mapped = new Set(mapTexts().flatMap((t) => mapCodePaths(t, extRe(cfg))));
      const missing = all.filter((f) => !mapped.has(f));
      if (missing.length)
        throw new Error(`${missing.length}/${all.length} tracked code files have no docs/map/ line — e.g. ${missing.slice(0, 5).join(', ')}`);
      return true;
    },

    MAP2: () => {
      const tracked = new Set(trackedCodeFiles(files(), cfg));
      const bad = mapTexts()
        .flatMap((t) => mapCodePaths(t, extRe(cfg)))
        .filter((p) => !tracked.has(p));
      if (bad.length) throw new Error(`docs/map/ names ${bad.length} file(s) git does not track: ${bad.join(', ')}`);
      return true;
    },

    MAP3: () => {
      if (!cfg.migrationsDir) return skip('migrationsDir', 'migrations folder');
      const migrationFiles = files().filter((f) => f.startsWith(cfg.migrationsDir) && f.endsWith('.sql'));
      const tables = migrationTables(migrationFiles.map((f) => read(f)));
      const mapped = new Set(mapTexts().flatMap(mapTableNames));
      const missing = tables.filter((t) => !mapped.has(t));
      if (missing.length)
        throw new Error(`${missing.length}/${tables.length} migration-created tables have no docs/map/ Tables line — e.g. ${missing.slice(0, 5).join(', ')}`);
      return true;
    },

    MAP4: () => {
      if (!cfg.screenKeys) return skip('screenKeys', 'screen keys file');
      const keys = screenKeys();
      const mapped = new Set(mapTexts().flatMap(mapScreenKeys));
      const missing = keys.filter((k) => !mapped.has(k));
      if (missing.length) throw new Error(`${missing.length}/${keys.length} screen keys have no docs/map/ Screens line: ${missing.join(', ')}`);
      return true;
    },

    MAP5: () => {
      const { badSteps, badForms } = traceFindingsNow();
      if (badSteps.length) throw new Error(`trace steps name ${badSteps.length} file(s) git does not track: ${badSteps.join(', ')}`);
      if (badForms.length) throw new Error(`numbered lines not in the form 1. \`path\`: ${badForms.join('; ')}`);
      return true;
    },

    MAP6: () => {
      if (!cfg.screenKeys) return skip('screenKeys', 'screen keys file');
      const { missingKeys, strayPages, emptyPages, emptyActions } = traceFindingsNow();
      const bad = [
        missingKeys.length && `no page for: ${missingKeys.join(', ')}`,
        strayPages.length && `page for no screen: ${strayPages.join(', ')}`,
        emptyPages.length && `page with no step: ${emptyPages.join(', ')}`,
        emptyActions.length && `action with no step: ${emptyActions.join('; ')}`,
      ].filter(Boolean);
      if (bad.length) throw new Error(bad.join('; '));
      return true;
    },

    MAP7: () => {
      const code = Object.fromEntries(trackedCodeFiles(files(), cfg).map((f) => [f, read(f)]));
      const notes = plainWordsNotes(code);
      if (notes.length)
        throw new Error(
          `${notes.length} tracked code file note(s) say "In plain words". The docs/map/ line is the one home. For example: ${notes.slice(0, 5).join(', ')}`
        );
      return true;
    },

    MAP8: () => {
      const all = files();
      const tracked = new Set(all);
      const code = all.filter((f) => /\.(ts|tsx)$/.test(f) && !/(^|\/)tests?\/|\.test\./.test(f));
      const src = Object.fromEntries(code.map((f) => [f, read(f)]));
      const targets = Object.fromEntries(code.map((f) => [f, runtimeLinks(f, src[f], tracked)]));
      const named = (f) => importedExports(src[f], f, tracked);
      const tableNames = [...new Set(mapTexts().flatMap(mapTableNames))];
      const { routes, calls } = webCalls({ code, src, tracked, targets });
      const gaps = traceGaps({
        traces: traceTexts(all),
        links: code.flatMap((f) => { const n = named(f); return targets[f].map((to) => ({ from: f, to, ...(n.get(to) ? { names: [...n.get(to)] } : {}) })); }),
        calls,
        routes,
        entries: scriptEntries(tracked.has('package.json') ? JSON.parse(read('package.json')).scripts ?? {} : {}, tracked, [...new Set(routes.map((r) => r.file))], extRe(cfg)),
        tables: tableNames,
      });
      if (gaps.length)
        throw new Error(`${gaps.length} trace step(s) no earlier step reaches: ${gaps.map((g) => `${g.key} / ${g.action}: ${g.to} (after ${g.from})`).join('; ')}`);
      return true;
    },
  };
};

// ---- The command: `node <skill>/scripts/map-check.mjs`, run from a repository root. ----
// One line per check: `[PASS] MAPn`, `[FAIL] MAPn <message>` or `[SKIP] MAPn <reason>`. The exit code is 1 when a line says FAIL.
// A bad config makes every check FAIL with the validator's message. A SKIP is a FAIL when the config sets `requireAllKeys`.
// The check list is the keys of `mapChecks`: one list, so a check added there runs here. Building the bodies runs none.

/** Runs every check of `mapChecks` in `root`. Returns the lines to print and whether any check failed. */
export const runMapChecks = (root) => {
  let cfg, bad = null;
  try { cfg = loadMapConfig(path.join(root, 'map.config.json'), root); } catch (e) { bad = e; }
  const read = (f) => readFileSync(path.join(root, f), 'utf8');
  const bodies = mapChecks({ cfg: cfg ?? {}, root, read });
  const lines = [];
  let failed = false;
  // A note is no verdict: it carries no check id.
  if (cfg?.modelSeam && !boundSeamReader()) lines.push('[NOTE] no model-call reader is bound here, so the check that a file calls a model through "modelSeam.file" did not run');
  for (const id of Object.keys(bodies)) {
    let verdict = 'PASS', text = '';
    try {
      if (bad) throw bad;
      const r = bodies[id]();
      if (typeof r?.skipped === 'string') {
        verdict = cfg.requireAllKeys ? 'FAIL' : 'SKIP';
        text = cfg.requireAllKeys ? `${r.skipped}, and "requireAllKeys" is true` : r.skipped;
      }
    } catch (e) {
      verdict = 'FAIL';
      text = e.message;
    }
    if (verdict === 'FAIL') failed = true;
    lines.push(`[${verdict}] ${id}${text ? ` ${text.replace(/\s*\n\s*/g, ' ')}` : ''}`);
  }
  return { lines, failed };
};

// `realpathSync` on both sides: a run through a junction or symlink to the skill folder must still match.
// `argv[1]` names no file when a script imports this module from stdin (`node -`): then `realpathSync` throws ENOENT, and the guard is false. Any other error is rethrown, so a real run never ends in a silent green.
const isMain = () => {
  try { return !!process.argv[1] && realpathSync(fileURLToPath(import.meta.url)) === realpathSync(path.resolve(process.argv[1])); } catch (e) { if (e.code === 'ENOENT') return false; throw e; }
};
if (isMain()) {
  const { lines, failed } = runMapChecks(process.cwd());
  console.log(lines.join('\n'));
  process.exitCode = failed ? 1 : 0;
}

// Duplicate top-level names in the waiting page (page.html), step page-dup-helpers.
// The Answer script (the page's first classic <script>) binds names at the top level, so they are globals. The
// Status script (the second) runs its code in one arrow IIFE. A Status name that matches an Answer global clashes
// with it: a top-level Status declaration or write replaces the global for every caller, and a declaration in the
// IIFE shadows it for the whole Status tab. Both scripts are read with TypeScript's parser, the compiler the repo
// pins for lint/comment_scan.mjs. The HTML is cut only at its <script> tags, and a block the parser cannot read
// fails the test.
//   PATH=<code-check tools>/node_modules/.bin:$PATH node --test skills/waiting-page/tests/test_page_dup_helpers.mjs
// Needs tsc on PATH: a laptop without it skips, CI fails (testing/skip-locally-fail-in-ci.mjs).
// Seam: PAGE_UNDER_TEST is the page to load, for a run against another copy, as in page.test.mjs.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { needEnv } from "../../../testing/skip-locally-fail-in-ci.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE = process.env.PAGE_UNDER_TEST || path.join(HERE, "..", "page.html");
const require = createRequire(import.meta.url);

// The `tsc` on PATH, found the way lint/comment_scan.mjs finds it. That file scans on import, so its lookup
// is repeated here rather than imported.
function loadTypescript() {
  for (const dir of (process.env.PATH || "").split(path.delimiter)) {
    if (!dir || !fs.existsSync(path.join(dir, "tsc"))) continue;
    const root = path.resolve(path.dirname(fs.realpathSync(path.join(dir, "tsc"))), "..");
    return require(path.join(root, "lib", "typescript.js"));
  }
  throw new Error("tsc is not on PATH");
}

// The page's <script> blocks in order, as {attrs, body, at}; `at` is where the body starts in the page. The
// page writes a closing tag inside its code as <\/script>, so the first </script> after an opening tag ends it.
function scriptBlocks(html) {
  const blocks = [];
  let from = 0;
  for (;;) {
    const open = html.indexOf("<script", from);
    const gt = open < 0 ? -1 : html.indexOf(">", open);
    const close = gt < 0 ? -1 : html.indexOf("</script>", gt);
    if (close < 0) return blocks;
    blocks.push({ attrs: html.slice(open + "<script".length, gt), body: html.slice(gt + 1, close), at: gt + 1 });
    from = close + "</script>".length;
  }
}

const parse = (ts, text) => ts.createSourceFile("page-script.js", text, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);

// The syntax errors of a script. Parsing recovers past an error, so a block with one would yield partial names.
function syntaxErrors(ts, text) {
  const options = { allowJs: true, target: ts.ScriptTarget.Latest };
  return ts.transpileModule(text, { reportDiagnostics: true, compilerOptions: options }).diagnostics
    .map((d) => ts.flattenDiagnosticMessageText(d.messageText, " "));
}

const isFnNode = (ts, n) => ts.isFunctionDeclaration(n) || ts.isFunctionExpression(n) || ts.isArrowFunction(n) ||
  ts.isMethodDeclaration(n) || ts.isGetAccessorDeclaration(n) || ts.isSetAccessorDeclaration(n) || ts.isConstructorDeclaration(n);
const isLexical = (ts, list) => (list.flags & (ts.NodeFlags.Let | ts.NodeFlags.Const)) !== 0;
const isAssign = (ts, kind) => kind >= ts.SyntaxKind.FirstAssignment && kind <= ts.SyntaxKind.LastAssignment;

// The names a binding pattern binds: an identifier, or the names inside an object or array pattern.
function boundNames(ts, name) {
  if (ts.isIdentifier(name)) return [name.text];
  return name.elements.filter((el) => !ts.isOmittedExpression(el)).flatMap((el) => boundNames(ts, el.name));
}

// The names a function body or a script binds at its own level, as [name, node, kind]. A top-level let, const,
// class or function binds there. So does a var at any depth, and a function declared in a block (sloppy mode
// hoists it to the function, Annex B). A nested function is not entered: the names inside it are its own.
function levelNames(ts, scope) {
  const out = [];
  const visit = (node, top) => {
    if (isFnNode(ts, node)) {
      if (ts.isFunctionDeclaration(node) && node.name) out.push([node.name.text, node, top ? "function" : "block function"]);
      return;
    }
    if (ts.isVariableStatement(node)) return visit(node.declarationList, top);
    if (ts.isVariableDeclarationList(node)) {
      if (top || !isLexical(ts, node)) {
        const kind = node.flags & ts.NodeFlags.Const ? "const" : node.flags & ts.NodeFlags.Let ? "let" : "var";
        for (const d of node.declarations) for (const name of boundNames(ts, d.name)) out.push([name, d, kind]);
      }
      return;
    }
    if (ts.isClassDeclaration(node)) {
      if (top && node.name) out.push([node.name.text, node, "class"]);
      return;
    }
    ts.forEachChild(node, (child) => visit(child, false));
  };
  for (const st of scope.statements ?? []) visit(st, true);
  return out;
}

// The names a block's own statements bind: let, const, class and function declarations. A var belongs to the function.
function directNames(ts, statements) {
  return statements.flatMap((st) => {
    if ((ts.isFunctionDeclaration(st) || ts.isClassDeclaration(st)) && st.name) return [st.name.text];
    if (ts.isVariableStatement(st) && isLexical(ts, st.declarationList)) {
      return st.declarationList.declarations.flatMap((d) => boundNames(ts, d.name));
    }
    return [];
  });
}

// The names a node binds for the code inside it, or null when the node opens no scope.
function scopeNamesOf(ts, node) {
  if (ts.isSourceFile(node)) return levelNames(ts, node).map(([name]) => name);
  if (isFnNode(ts, node)) {
    const own = ts.isFunctionExpression(node) && node.name ? [node.name.text] : [];
    const params = node.parameters.flatMap((p) => boundNames(ts, p.name));
    const body = node.body && ts.isBlock(node.body) ? levelNames(ts, node.body).map(([name]) => name) : [];
    return [...own, ...params, ...body];
  }
  if (ts.isClassDeclaration(node) || ts.isClassExpression(node)) return node.name ? [node.name.text] : null;
  if (ts.isBlock(node)) return directNames(ts, node.statements);
  if (ts.isCaseBlock(node)) return directNames(ts, node.clauses.flatMap((c) => [...c.statements]));
  if (ts.isCatchClause(node)) return node.variableDeclaration ? boundNames(ts, node.variableDeclaration.name) : null;
  const init = ts.isForStatement(node) || ts.isForInStatement(node) || ts.isForOfStatement(node) ? node.initializer : null;
  if (init && ts.isVariableDeclarationList(init) && isLexical(ts, init)) return init.declarations.flatMap((d) => boundNames(ts, d.name));
  return null;
}

// The identifiers a write target names: a name, or the names inside a destructuring pattern.
function writtenNames(ts, t) {
  if (ts.isIdentifier(t)) return [t];
  if (ts.isParenthesizedExpression(t)) return writtenNames(ts, t.expression);
  if (ts.isBinaryExpression(t) && t.operatorToken.kind === ts.SyntaxKind.EqualsToken) return writtenNames(ts, t.left); // a default
  if (ts.isSpreadElement(t)) return writtenNames(ts, t.expression);
  if (ts.isArrayLiteralExpression(t)) return t.elements.flatMap((el) => writtenNames(ts, el));
  if (ts.isObjectLiteralExpression(t)) {
    return t.properties.flatMap((p) => {
      if (ts.isShorthandPropertyAssignment(p)) return [p.name];
      if (ts.isPropertyAssignment(p)) return writtenNames(ts, p.initializer);
      if (ts.isSpreadAssignment(p)) return writtenNames(ts, p.expression);
      return [];
    });
  }
  return [];
}

// The identifiers a node writes: an assignment's target, a ++ or -- operand, or a for-in or for-of target.
function writesOf(ts, node) {
  if (ts.isBinaryExpression(node) && isAssign(ts, node.operatorToken.kind)) return writtenNames(ts, node.left);
  if ((ts.isPrefixUnaryExpression(node) || ts.isPostfixUnaryExpression(node)) &&
    (node.operator === ts.SyntaxKind.PlusPlusToken || node.operator === ts.SyntaxKind.MinusMinusToken)) {
    return writtenNames(ts, node.operand);
  }
  if ((ts.isForInStatement(node) || ts.isForOfStatement(node)) && !ts.isVariableDeclarationList(node.initializer)) {
    return writtenNames(ts, node.initializer);
  }
  return [];
}

// The writes to an Answer name that no scope inside the file binds, so they reach the Answer global. A write to a
// name a Status scope binds stays in that scope.
function globalWrites(ts, file, answerNames) {
  const found = [];
  const scopes = [];
  const bound = (name) => scopes.some((s) => s.has(name));
  const visit = (node) => {
    const names = scopeNamesOf(ts, node);
    if (names) scopes.push(new Set(names));
    for (const id of writesOf(ts, node)) if (answerNames.has(id.text) && !bound(id.text)) found.push(id);
    ts.forEachChild(node, visit);
    if (names) scopes.pop();
  };
  visit(file);
  return found;
}

// The arrow of a statement that is `(() => { ... })();`, or null.
function iifeArrow(ts, st) {
  const call = ts.isExpressionStatement(st) && ts.isCallExpression(st.expression) ? st.expression : null;
  const paren = call && ts.isParenthesizedExpression(call.expression) ? call.expression : null;
  const arrow = paren && ts.isArrowFunction(paren.expression) ? paren.expression : null;
  return arrow && ts.isBlock(arrow.body) ? arrow : null;
}

// The clashes of the Status script with the Answer script, as { name, kind, where, line }. A clash is a Status
// name that the Answer script binds at the top level and the Status script binds at its top level or in its IIFE,
// or a write to such a name that reaches the global. `line` counts from the top of the Status script.
function statusClashes(ts, answerText, statusText) {
  for (const [who, text] of [["Answer", answerText], ["Status", statusText]]) {
    const errors = syntaxErrors(ts, text);
    assert.deepEqual(errors, [], `the ${who} script does not parse, so its names cannot be read: ${errors.join("; ")}`);
  }
  const answerFile = parse(ts, answerText);
  const answerNames = new Set(levelNames(ts, answerFile).map(([name]) => name));
  assert.ok(answerNames.size > 0, "the Answer script binds no top-level name, so there is nothing for the Status script to clash with");
  const statusFile = parse(ts, statusText);
  const iifes = statusFile.statements.map((st) => iifeArrow(ts, st)).filter(Boolean);
  assert.equal(iifes.length, 1, `the Status script holds ${iifes.length} (() => { ... })() statements; the check needs one`);
  const [iife] = iifes;
  const iifeNames = [
    ...iife.parameters.flatMap((p) => boundNames(ts, p.name).map((name) => [name, p, "parameter"])),
    ...levelNames(ts, iife.body),
  ];
  assert.ok(iifeNames.length > 0, "the Status IIFE declares no name, so the check would pass with nothing to compare");
  const found = [
    ...levelNames(ts, statusFile).map(([name, node, kind]) => [name, node, kind, "top level of the Status script"]),
    ...iifeNames.map(([name, node, kind]) => [name, node, kind, "Status IIFE"]),
    ...globalWrites(ts, statusFile, answerNames).map((id) => [id.text, id, "assignment", "Status script"]),
  ];
  return found
    .filter(([name]) => answerNames.has(name))
    .map(([name, node, kind, where]) => ({
      name, kind, where, line: statusFile.getLineAndCharacterOfPosition(node.getStart(statusFile)).line + 1,
    }))
    .sort((a, b) => a.line - b.line);
}

const describeClash = (c) => `${c.name} (${c.kind}, ${c.where}, line ${c.line})`;

// A test that reads the scripts with the pinned tsc. A missing tsc skips it on a laptop and fails it in CI.
function scanTest(name, body) {
  test(name, async (t) => {
    const ts = await needEnv(t, "tsc", loadTypescript);
    if (ts) body(ts);
  });
}

scanTest("page.html's Status script clashes with no Answer-script name", (ts) => {
  const html = fs.readFileSync(PAGE, "utf8");
  const blocks = scriptBlocks(html).filter((b) => b.attrs.trim() === "");
  assert.equal(blocks.length, 2,
    `${PAGE} has ${blocks.length} classic <script> blocks; this test reads two, the Answer script then the Status script`);
  const [answer, status] = blocks;
  const lineOf = (offset) => html.slice(0, offset).split("\n").length;
  const named = statusClashes(ts, answer.body, status.body)
    .map((c) => describeClash({ ...c, line: lineOf(status.at) + c.line - 1 }));
  assert.deepEqual(named, [],
    `page.html's Status script clashes with the Answer script's names: ${named.join(", ")}. ` +
    "Rename the Status name, or call the Answer script's name.");
});

// The fixtures are small in-memory scripts in the page's shape: an Answer script with one top-level function, and
// a Status script with one IIFE. Each red case is one shape the scan must name; each green case is one it must pass.
const ANSWER = "function copyText(t) { return t; }\n";
const withIife = (body) => `(() => {\n${body}\n})();\n`;
const clash = (name, kind, where, line) => ({ name, kind, where, line });

scanTest("a Status function at the top level, outside its IIFE, is named", (ts) => {
  const status = withIife("  const n = 1;") + "function copyText(t) { return t; }\n";
  assert.deepEqual(statusClashes(ts, ANSWER, status), [clash("copyText", "function", "top level of the Status script", 4)]);
});

scanTest("a block function inside the Status IIFE is named", (ts) => {
  const status = withIife("  const n = 1;\n  if (window.x) { function copyText(t) { return t; } }");
  assert.deepEqual(statusClashes(ts, ANSWER, status), [clash("copyText", "block function", "Status IIFE", 3)]);
});

scanTest("a bare assignment to an Answer name at the top level is named", (ts) => {
  const status = withIife("  const n = 1;") + "copyText = (t) => t;\n";
  assert.deepEqual(statusClashes(ts, ANSWER, status), [clash("copyText", "assignment", "Status script", 4)]);
});

scanTest("a bare assignment to an Answer name inside a nested function is named", (ts) => {
  const status = withIife("  function render() { copyText = null; }\n  render();");
  assert.deepEqual(statusClashes(ts, ANSWER, status), [clash("copyText", "assignment", "Status script", 2)]);
});

scanTest("an Answer name bound to a call's result is counted", (ts) => {
  const answer = ANSWER + "const priceOf = (() => (x) => x)();\n";
  const status = withIife("  function priceOf(x) { return x; }");
  assert.deepEqual(statusClashes(ts, answer, status), [clash("priceOf", "function", "Status IIFE", 2)]);
});

scanTest("an Answer const bound to a string is counted", (ts) => {
  const answer = ANSWER + 'const copyLabel = "Copy";\n';
  const status = withIife("  const copyLabel = 'Copy!';");
  assert.deepEqual(statusClashes(ts, answer, status), [clash("copyLabel", "const", "Status IIFE", 2)]);
});

scanTest("names only in strings, comments, template literals and property keys are not clashes", (ts) => {
  const body = [
    '  const label = "copyText"; // copyText',
    "  const note = \"Don't reuse copyText\";",
    "  const tpl = `copyText`;",
    "  const block = `",
    "copyText",
    "`;",
    "  const o = { copyText: 1 };",
    "  o.copyText = 2;",
  ].join("\n");
  assert.deepEqual(statusClashes(ts, ANSWER, withIife(body)), []);
});

scanTest("a nested function's own local helper and its own local write are not clashes", (ts) => {
  const body = [
    "  function render() { function copyText(t) { return t; } return copyText(1); }",
    "  function fmt(t) { let copyText = 0; copyText = t; return copyText; }",
    "  function pick(t) { if (window.x) { function copyText(u) { return u; } } return t; }",
    "  render(); fmt(1); pick(2);",
  ].join("\n");
  assert.deepEqual(statusClashes(ts, ANSWER, withIife(body)), []);
});

scanTest("a Status name the Answer script does not bind, and a call to an Answer function, are not clashes", (ts) => {
  const body = [
    '  const n = copyText("x");',
    "  function drawRail() { return n; }",
    "  let count = 0; count = count + 1;",
  ].join("\n");
  assert.deepEqual(statusClashes(ts, ANSWER, withIife(body) + "function drawTop() {}\n"), []);
});

scanTest("a Status IIFE that declares no name fails with its reason, not a pass", (ts) => {
  assert.throws(() => statusClashes(ts, ANSWER, withIife('  copyText("x");')), /declares no name/);
});

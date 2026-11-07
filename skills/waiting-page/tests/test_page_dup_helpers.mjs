// Duplicate top-level functions in the waiting page (page.html), step page-dup-helpers.
// The Status script (the page's second classic <script>) runs its code in one arrow IIFE. A function that the
// Answer script (the first classic <script>) declares at top level, and the IIFE declares again, shadows the
// global one for the whole Status tab. The scripts are read with TypeScript's parser, the compiler the repo
// pins for lint/comment_scan.mjs. The HTML is cut only at its <script> tags, and a block the parser cannot
// read fails the test.
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

// The names a statement declares directly: a function, a class, or what a var, let or const binds.
function declaredBy(ts, st) {
  if ((ts.isFunctionDeclaration(st) || ts.isClassDeclaration(st)) && st.name) return [[st.name.text, st]];
  if (!ts.isVariableStatement(st)) return [];
  return st.declarationList.declarations.flatMap((d) => boundNames(ts, d.name).map((name) => [name, d]));
}

function boundNames(ts, name) {
  if (ts.isIdentifier(name)) return [name.text];
  return name.elements.filter((el) => !ts.isOmittedExpression(el)).flatMap((el) => boundNames(ts, el.name));
}

// The top-level functions of a script: function declarations, and names bound to an arrow or a function
// expression, since a const arrow shadows the same way.
function topLevelFunctions(ts, file) {
  const names = new Set();
  for (const st of file.statements) {
    if (ts.isFunctionDeclaration(st) && st.name) names.add(st.name.text);
    if (!ts.isVariableStatement(st)) continue;
    for (const d of st.declarationList.declarations) {
      const init = d.initializer;
      if (ts.isIdentifier(d.name) && init && (ts.isArrowFunction(init) || ts.isFunctionExpression(init))) names.add(d.name.text);
    }
  }
  return names;
}

// The arrow of a statement that is `(() => { ... })();`, or null.
function iifeArrow(ts, st) {
  const call = ts.isExpressionStatement(st) && ts.isCallExpression(st.expression) ? st.expression : null;
  const paren = call && ts.isParenthesizedExpression(call.expression) ? call.expression : null;
  const arrow = paren && ts.isArrowFunction(paren.expression) ? paren.expression : null;
  return arrow && ts.isBlock(arrow.body) ? arrow : null;
}

test("page.html's Status script declares no top-level Answer-script function again inside its IIFE", async (t) => {
  const ts = await needEnv(t, "tsc", loadTypescript);
  if (!ts) return;
  const html = fs.readFileSync(PAGE, "utf8");
  const blocks = scriptBlocks(html).filter((b) => b.attrs.trim() === "");
  assert.equal(blocks.length, 2,
    `${PAGE} has ${blocks.length} classic <script> blocks; this test reads two, the Answer script then the Status script`);
  const [answer, status] = blocks;
  for (const [who, block] of [["Answer", answer], ["Status", status]]) {
    const errors = syntaxErrors(ts, block.body);
    assert.deepEqual(errors, [], `the ${who} script does not parse, so its names cannot be read: ${errors.join("; ")}`);
  }
  const answerFns = topLevelFunctions(ts, parse(ts, answer.body));
  assert.ok(answerFns.size > 0, "the Answer script has no top-level function, so there is nothing for the Status script to clash with");
  const statusFile = parse(ts, status.body);
  const iifes = statusFile.statements.map((st) => iifeArrow(ts, st)).filter(Boolean);
  assert.equal(iifes.length, 1, `the Status script holds ${iifes.length} (() => { ... })() statements; the check needs one`);
  const declared = iifes[0].body.statements.flatMap((st) => declaredBy(ts, st));
  assert.ok(declared.length > 0, "the Status IIFE declares no name, so the check would pass with nothing to compare");
  const lineOf = (offset) => html.slice(0, offset).split("\n").length;
  const clashes = declared
    .filter(([name]) => answerFns.has(name))
    .map(([name, node]) => `${name} (line ${lineOf(status.at + node.getStart(statusFile))})`);
  assert.deepEqual(clashes, [],
    `page.html's Status script declares again, inside its IIFE, a top-level function of the Answer script: ${clashes.join(", ")}. ` +
    "Rename the Status declaration, or call the Answer script's function.");
});

// Judges whether two texts of one JS or TS file differ in comments only. Reads one JSON object
// {name, old, new} on stdin and prints `same` (exit 0) when the code tokens match, `differ` (exit 1) when they
// do not or when either text has a syntax error, and exits 2 when the TypeScript compiler cannot be loaded.
// Used by hooks/guard.py (`comment_only_change`, rule builder-test-edit).
//
// The compared units are the leaf tokens of the syntax tree: kind and text. Comments are trivia, so they are no
// token, and a comment opener inside a string, a template piece, a regex or JSX text is part of that token's text.
// A line break before a token is compared too: a block comment that holds one is a line terminator, and removing
// it changes a `return` or a statement that follows (automatic semicolon insertion).
import fs from "node:fs";
import { loadTypescript } from "../lint/typescript_on_path.mjs";

let ts;
try {
  ts = loadTypescript();
} catch (e) {
  console.error(`cannot load typescript: ${e.message}`);
  process.exit(2);
}

const KINDS = {
  ".js": ts.ScriptKind.JS, ".mjs": ts.ScriptKind.JS, ".cjs": ts.ScriptKind.JS, ".jsx": ts.ScriptKind.JSX,
  ".ts": ts.ScriptKind.TS, ".tsx": ts.ScriptKind.TSX,
};
const LINE_BREAK = new RegExp("[\\r\\n\\u2028\\u2029]");

// The [kind, text, line break before] triples of a source text, or null when it has a syntax error.
function tokens(name, text) {
  const dot = name.lastIndexOf(".");
  const kind = dot < 0 ? undefined : KINDS[name.slice(dot).toLowerCase()];
  if (kind === undefined) return null;
  const file = ts.createSourceFile(name, text, ts.ScriptTarget.Latest, true, kind);
  if (file.parseDiagnostics.length > 0) return null;
  const out = [];
  const walk = (node) => {
    // A JSDoc node is inside a comment.
    if (node.kind >= ts.SyntaxKind.FirstJSDocNode && node.kind <= ts.SyntaxKind.LastJSDocNode) return;
    const children = node.getChildren(file);
    if (children.length === 0) {
      // JSX text is all text, spaces included: its start is its full start, not the start after whitespace.
      const start = node.kind === ts.SyntaxKind.JsxText ? node.pos : node.getStart(file);
      // The first token has no statement before it, so a line break ahead of it cannot change how it parses.
      const lineBreak = out.length > 0 && LINE_BREAK.test(text.slice(node.pos, start));
      out.push([node.kind, text.slice(start, node.end), lineBreak]);
      return;
    }
    children.forEach(walk);
  };
  walk(file);
  return out;
}

try {
  const job = JSON.parse(fs.readFileSync(0, "utf8"));
  const before = tokens(job.name, job.old);
  const after = tokens(job.name, job.new);
  const same = before !== null && after !== null && JSON.stringify(before) === JSON.stringify(after);
  console.log(same ? "same" : "differ");
  process.exit(same ? 0 : 1);
} catch (e) {
  console.error(String(e.message || e));
  process.exit(1);
}

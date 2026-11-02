// Prints each comment line of the JS, TS and Astro files named on the command line, as JSON rows
// {path, line, text}. A file it cannot read prints {path, error} and the run goes on.
// Exit 2 with a reason on stderr when the TypeScript compiler cannot be loaded.
// Used by lint/check_comment_narration.py (rule building-comments-say-why).
//
// TypeScript is the one on PATH as `tsc` (a symlink or shim is followed to its package). The caller puts
// the version pinned in actions/code-check/standard.json there, so this file names no version.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

function loadTypescript() {
  for (const dir of (process.env.PATH || "").split(path.delimiter)) {
    const tsc = path.join(dir, "tsc");
    if (!dir || !fs.existsSync(tsc)) continue;
    // The first tsc on PATH is the one the caller chose: a broken one is an error, never a reason to look further.
    const root = path.resolve(path.dirname(fs.realpathSync(tsc)), "..");
    for (const candidate of [path.join(root, "lib", "typescript.js"), root]) {
      try {
        return require(candidate);
      } catch { /* try the package root next */ }
    }
    throw new Error(`the typescript package is not beside ${tsc}`);
  }
  throw new Error("tsc is not on PATH");
}

let ts;
try {
  ts = loadTypescript();
} catch (e) {
  console.error(`cannot load typescript: ${e.message}`);
  process.exit(2);
}

const NEWLINE = /\r\n|\r|\n/;

// Text a comment opener cannot start in: JSX text and the text pieces of a template literal.
function isTextToken(kind) {
  return kind === ts.SyntaxKind.JsxText || kind === ts.SyntaxKind.TemplateMiddle || kind === ts.SyntaxKind.TemplateTail;
}

// Every comment in a source text as {pos, end}, deduplicated by position. Parsing is error tolerant, so a
// file with a syntax error still yields the comments the parser reached.
function commentRanges(text, name, kind) {
  const file = ts.createSourceFile(name, text, ts.ScriptTarget.Latest, true, kind);
  const found = new Map();
  const textSpans = [];
  // Leading ranges hold the comments after a line break, trailing ranges those on the token's own line.
  const walk = (node) => {
    // A JSDoc node is inside a block comment that the next token already reports.
    if (node.kind >= ts.SyntaxKind.FirstJSDocNode && node.kind <= ts.SyntaxKind.LastJSDocNode) return;
    const children = node.getChildren(file);
    if (isTextToken(node.kind)) textSpans.push([node.getStart(file), node.end]);
    if (children.length === 0) {
      for (const r of ts.getLeadingCommentRanges(text, node.pos) || []) found.set(r.pos, r);
      for (const r of ts.getTrailingCommentRanges(text, node.end) || []) found.set(r.pos, r);
    }
    children.forEach(walk);
  };
  walk(file);
  return [...found.values()].filter((r) => !textSpans.some(([s, e]) => r.pos >= s && r.pos < e));
}

// Pushes one {path, line, text} row per line of each comment range.
function emitComments(file, source, ranges, out) {
  const starts = [0];
  for (const m of source.matchAll(/\r\n|\r|\n/g)) starts.push(m.index + m[0].length);
  for (const r of ranges) {
    let lo = 0;
    let hi = starts.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (starts[mid] <= r.pos) lo = mid; else hi = mid - 1;
    }
    source.slice(r.pos, r.end).split(NEWLINE).forEach((text, k) => {
      out.push({ path: file, line: lo + 1 + k, text });
    });
  }
}

// Blank everything except the given [start, end) ranges, keeping every line break, so offsets and line numbers hold.
function keepOnly(text, ranges) {
  const blank = text.replace(/[^\r\n]/g, " ");
  let out = "";
  let at = 0;
  for (const [s, e] of ranges) {
    out += blank.slice(at, s) + text.slice(s, e);
    at = e;
  }
  return out + blank.slice(at);
}

function astroRegions(text) {
  const code = [];
  const front = /^﻿?\s*---[ \t]*\r?\n/.exec(text);
  let templateFrom = 0;
  if (front) {
    const start = front[0].length;
    const close = text.slice(start).search(/^---[ \t]*\r?$/m);
    if (close >= 0) {
      code.push([start, start + close]);
      templateFrom = start + close;
    }
  }
  for (const m of text.matchAll(/(<script\b[^>]*>)([\s\S]*?)(<\/script>)/g)) {
    if (m.index < templateFrom) continue;
    const start = m.index + m[1].length;
    code.push([start, start + m[2].length]);
  }
  return code;
}

// The opposite of keepOnly: blank the given ranges.
function blankRanges(text, ranges) {
  let out = "";
  let at = 0;
  for (const [s, e] of ranges) {
    out += text.slice(at, s) + text.slice(s, e).replace(/[^\r\n]/g, " ");
    at = e;
  }
  return out + text.slice(at);
}

function scanAstro(file, text, out) {
  const code = astroRegions(text);
  const script = keepOnly(text, code);
  emitComments(file, script, commentRanges(script, file, ts.ScriptKind.TS), out);
  // The template is everything outside the code regions: its comments are `<!-- -->` and `{/* */}`.
  const body = blankRanges(text, code);
  const found = [];
  for (const m of body.matchAll(/<!--[\s\S]*?-->|\{\s*\/\*[\s\S]*?\*\/\s*\}/g)) {
    found.push({ pos: m.index, end: m.index + m[0].length });
  }
  emitComments(file, body, found, out);
}

const KIND = {
  ".ts": ts.ScriptKind.TS, ".mts": ts.ScriptKind.TS, ".cts": ts.ScriptKind.TS, ".tsx": ts.ScriptKind.TSX,
  ".js": ts.ScriptKind.JS, ".mjs": ts.ScriptKind.JS, ".cjs": ts.ScriptKind.JS,
};

for (const file of process.argv.slice(2)) {
  try {
    const text = fs.readFileSync(file, "utf8");
    const out = [];
    const ext = path.extname(file).toLowerCase();
    if (ext === ".astro") {
      scanAstro(file, text, out);
    } else {
      emitComments(file, text, commentRanges(text, file, KIND[ext] ?? ts.ScriptKind.JS), out);
    }
    for (const row of out) console.log(JSON.stringify(row));
  } catch (e) {
    console.log(JSON.stringify({ path: file, error: String(e.message || e) }));
  }
}

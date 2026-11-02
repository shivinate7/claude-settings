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

// The text with every character but its line breaks turned to a space, so offsets and line numbers hold.
const blank = (text) => text.replace(/[^\r\n]/g, " ");

// Text a comment opener cannot start in: JSX text and the text pieces of a template literal.
function isTextToken(kind) {
  return kind === ts.SyntaxKind.JsxText || kind === ts.SyntaxKind.TemplateMiddle || kind === ts.SyntaxKind.TemplateTail;
}

// Every comment in a source text as {pos, end}, deduplicated by position. Parsing is error tolerant, so a
// file with a syntax error still yields the comments the parser reached.
function commentRanges(text, name, kind) {
  return commentRangesOf(ts.createSourceFile(name, text, ts.ScriptTarget.Latest, true, kind));
}

function commentRangesOf(file) {
  const text = file.text;
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
  const blanked = blank(text);
  let out = "";
  let at = 0;
  for (const [s, e] of ranges) {
    out += blanked.slice(at, s) + text.slice(s, e);
    at = e;
  }
  return out + blanked.slice(at);
}

function astroRegions(text) {
  const code = [];
  const front = /^\uFEFF?\s*---[ \t]*\r?\n/.exec(text);
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
    out += text.slice(at, s) + blank(text.slice(s, e));
    at = e;
  }
  return out + text.slice(at);
}

function scanAstro(file, text, out) {
  const code = astroRegions(text);
  const script = keepOnly(text, code);
  emitComments(file, script, commentRanges(script, file, ts.ScriptKind.TS), out);
  // The template is everything outside the code regions. Its HTML comments come from a pattern. Its expression
  // comments come from parsing it as TSX inside a fragment: JSX text is then text, and a `{...}` is code.
  // HTML comments, declarations and style content are blanked first, as the parser cannot read them.
  const body = blankRanges(text, code);
  const html = [];
  for (const m of body.matchAll(/<!--[\s\S]*?-->/g)) html.push({ pos: m.index, end: m.index + m[0].length });
  emitComments(file, body, html, out);
  const plain = body
    .replace(/<!--[\s\S]*?-->|<![^>]*>/g, blank)
    .replace(/(<style\b[^>]*>)([\s\S]*?)(<\/style>)/g, (_, open, css, close) => open + blank(css) + close);
  const wrapped = ts.createSourceFile(file, `<>${plain}</>`, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const ranges = commentRangesOf(wrapped).map((r) => ({ pos: r.pos - 2, end: r.end - 2 }));
  emitComments(file, body, ranges, out);
}

// The language row picks the script kind. TypeScript reads `.ts` and `.tsx` itself from the file name, so no
// extension list lives here.
const KIND = { javascript: ts.ScriptKind.JS, typescript: undefined };

for (const arg of process.argv.slice(2)) {
  const colon = arg.indexOf(":");
  const language = arg.slice(0, colon);
  const file = arg.slice(colon + 1);
  try {
    const text = fs.readFileSync(file, "utf8");
    const out = [];
    if (language === "astro") {
      scanAstro(file, text, out);
    } else if (language in KIND) {
      emitComments(file, text, commentRanges(text, file, KIND[language]), out);
    } else {
      throw new Error(`no scanner for language ${language}`);
    }
    for (const row of out) console.log(JSON.stringify(row));
  } catch (e) {
    console.log(JSON.stringify({ path: file, error: String(e.message || e) }));
  }
}

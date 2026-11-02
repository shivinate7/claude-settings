// Shared scanner self-tests (rule building-scanner-respects-strings). Every scanner in SCANNERS runs the
// same trap table. A trap is a comment opener (`//`, `/*`, `#`) inside a string, a multi-line template
// literal, or a lone quote inside a string. A trap alone must find nothing. A trap followed by the
// scanner's defect must still flag the defect. Cases that test something else stay here in their own
// blocks, labelled with the scanner. A new scanner joins with one entry in SCANNERS.
// Run: node lint/test_scanner_traps.mjs  (exit 1 on any FAIL). LIST_TESTS=1 prints each name as LISTED <JSON>.
// The decision-watch mod test imports machinePaths and codeNouns from this file.
import "./_test_git.mjs";  // test-run signing opt-out (lint/_test_git.mjs)
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { check, loadConfig } from "../actions/stamp/stamp.mjs";
import { looksSecret } from "../mods/plain-diff/hooks/lib.mjs";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const real = (p) => { try { return realpathSync(p); } catch { return resolve(p); } };
const isMain = Boolean(process.argv[1]) && real(process.argv[1]) === real(fileURLToPath(import.meta.url));

const tests = [];
const test = (name, fn) => tests.push({ name, fn });
const same = (got, want, why) => assert.deepEqual(got, want, `${why}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);

// ---- the traps. Each is written in front of a scanner's defect, on the same text.
const TRAPS = [
  { name: "comment opener // in a string", text: 'const u = "http://a.test/"; ' },
  { name: "comment opener /* in a string", text: 'const s = "/* not a comment"; ' },
  { name: "comment opener # in a string", text: 'const h = "# not a comment"; ' },
  { name: "multi-line template literal", text: "const t = `first line\nmiddle line\nlast line`; " },
  { name: "lone quote in a string", text: 'const q = "<p>Don\'t</p>"; ' },
];

// ---- scanner 1, decision-watch: machine paths, comments included on purpose (the scan does not parse).
const MACHINE = [
  /(?<![A-Za-z])[A-Za-z]:(?!\/\/)[\\/]/,
  /ShivamSemwal|SHIVAM~1|AppData|Clones|claude-settings|scratchpad|C--Users/,
  /\/Users\/|\/home\//,
  /\\Users\\/,
];
export const machinePaths = (text) => MACHINE.map((re) => text.match(re)).filter(Boolean).map((m) => m[0]);

// ---- scanner 2, decision-watch: bare $ noun reads in code only. Comments are dropped, string and template
// text are blanked, and a ${...} inside a template is code.
function codeOf(src) {
  const out = [];
  const frames = [{ tpl: false, braces: 0, interp: false }];
  let i = 0;
  while (i < src.length) {
    const top = frames[frames.length - 1];
    const c = src[i];
    const d = src[i + 1];
    if (top.tpl) {
      if (c === "\\") { out.push("  "); i += 2; continue; }
      if (c === "`") { frames.pop(); i++; continue; }
      if (c === "$" && d === "{") { frames.push({ tpl: false, braces: 0, interp: true }); out.push("  "); i += 2; continue; }
      out.push(c === "\n" ? "\n" : " ");
      i++;
      continue;
    }
    if (c === "/" && d === "/") { while (i < src.length && src[i] !== "\n") i++; continue; }
    if (c === "/" && d === "*") { const end = src.indexOf("*/", i + 2); i = end < 0 ? src.length : end + 2; out.push(" "); continue; }
    if (c === '"' || c === "'") {
      let j = i + 1;
      while (j < src.length && src[j] !== c && src[j] !== "\n") j += src[j] === "\\" ? 2 : 1;
      out.push(" ");
      i = j + 1;
      continue;
    }
    if (c === "`") { frames.push({ tpl: true, braces: 0, interp: false }); i++; continue; }
    if (c === "{") { top.braces++; out.push(c); i++; continue; }
    if (c === "}") {
      if (top.interp && top.braces === 0) { frames.pop(); i++; continue; }
      top.braces--;
      out.push(c);
      i++;
      continue;
    }
    out.push(c);
    i++;
  }
  return out.join("");
}
// Bare noun reads: $.noun.method that is not called. The \b stops a longer name matching a prefix.
const BARE_NOUN = /\$\.[A-Za-z_]\w*\.[A-Za-z_]\w*\b(?!\s*\()/g;
const bareNouns = (text) => [...text.matchAll(BARE_NOUN)].map((m) => m[0]);
export const codeNouns = (text) => bareNouns(codeOf(text));

// ---- scanner 3, stamp: a near-miss cite in a doc. The fixture is the one the stamp suite uses for D`one`.
const STAMP_CONFIG = join(ROOT, "actions", "stamp", "examples", "frontmatter-prefixed-cite.stamp.json");
const STAMP_RECORD = {
  path: "docs/decisions/one.md",
  text: "---\nid: D1\nslug: one\nkind: decision\nstatus: open\ndate: 2026-01-01\n---\n\nBody.\n",
};
const git = (root, ...args) => execFileSync("git", args, { cwd: root, encoding: "utf8" });
// The run folder comes from the one Python temp home (lint/_test_temp.py), so this suite follows the test-temp
// standard. It is made on first use, so importing this file makes no folder, and it is removed at the end of a run.
let runFolderPath = null;
function runFolder() {
  if (!runFolderPath) {
    const make = "import sys; sys.path.insert(0, sys.argv[1]); import _test_temp; print(_test_temp.run_folder())";
    runFolderPath = execFileSync("python3", ["-I", "-c", make, join(ROOT, "lint")], { encoding: "utf8" }).trim();
  }
  return runFolderPath;
}
function withTempDir(fn) {
  const dir = mkdtempSync(join(runFolder(), "scanner-traps-"));
  try { return fn(dir); } finally { rmSync(dir, { recursive: true, force: true }); }
}
function writeRel(root, rel, content) {
  const abs = join(root, rel);
  mkdirSync(join(abs, ".."), { recursive: true });
  writeFileSync(abs, content);
}
function stampProblems(docText) {
  return withTempDir((root) => {
    git(root, "init", "-q", "-b", "main");
    git(root, "config", "user.email", "test@example.com");
    git(root, "config", "user.name", "test");
    git(root, "config", "core.autocrlf", "false");
    writeRel(root, STAMP_RECORD.path, STAMP_RECORD.text);
    writeRel(root, "notes/doc.md", docText);
    git(root, "add", "-A");
    git(root, "commit", "-q", "-m", "a numbered record, and a doc that cites it");
    return check(root, loadConfig(STAMP_CONFIG)).filter((p) => p.includes("notes/doc.md"));
  });
}
// A near-miss is the wrong form D`one` named together with the right form D‹one›.
const stampNearMiss = (docText) => stampProblems(docText).filter((p) => p.includes("D`one`") && p.includes("D‹one›"));

// ---- scanner 4, plain-diff: a secret key in added lines. looksSecret reads diff text, so each line gets a "+".
const asAddedLines = (text) => text.split("\n").map((l) => "+" + l).join("\n");
const GHP = "gh" + "p_" + "A".repeat(36); // a fake token, built so no scanner reads it as live
const secretFlagged = (text) => looksSecret(asAddedLines(text));

// ---- scanner 5, ios-mockup: the page's font, safe-area and duo frames (lint/check_ios_mockup.py). The check is
// Python, so node runs it on the page text from stdin. The page is whole (font, inset, both frames), so a trap
// alone finds nothing. The defect is an unfolded frame ahead of the folded one, which the check flags.
const IOS_CHECK = join(ROOT, "lint", "check_ios_mockup.py");
const IOS_LOAD = "import importlib.util, json, sys\nspec = importlib.util.spec_from_file_location('m', sys.argv[1])\n"
  + "m = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(m)\n"
  + "print(json.dumps([code for code, _ in m.faults(sys.stdin.read())]))";
const iosPage = (body) => `<!doctype html><html><head><style>body { font-family: -apple-system, sans-serif; `
  + `padding: env(safe-area-inset-top); }</style></head><body>${body}`
  + `<div data-device="iphone-duo-folded"></div><div data-device="iphone-duo-unfolded"></div></body></html>`;
const iosCodes = (html) => {
  try { return JSON.parse(execFileSync("python3", ["-c", IOS_LOAD, IOS_CHECK], { input: html, encoding: "utf8" })); }
  catch (e) { throw new Error(String(e.stderr || e.message).trim().split("\n").pop()); }
};

// ---- scanner 6, time-pinned finder (lint/find_time_pinned.py). The text goes into one x.test.js in a git-less
// folder, and the --json findings decide. Exit 1 means findings, so spawnSync, not execFileSync. Any other exit,
// or output that is not JSON, throws, so an unknown result never reads as clean.
const TIME_PINNED = join(ROOT, "lint", "find_time_pinned.py");
function timePinnedFindings(text) {
  return withTempDir((dir) => {
    writeRel(dir, "x.test.js", text);
    const run = spawnSync("python3", [TIME_PINNED, dir, "--json"], { encoding: "utf8" });
    if (run.status !== 0 && run.status !== 1) {
      throw new Error(`finder gave no result (exit ${run.status}): ${String(run.stderr).trim().split("\n").pop()}`);
    }
    return JSON.parse(run.stdout).findings;
  });
}

// ---- the registry. A new scanner joins here with one entry: its name, its defect, and a flags(text) check.
const SCANNERS = [
  { name: "decision-watch machinePaths", defect: 'const p = "D:/work/x"', flags: (t) => machinePaths(t).length > 0 },
  { name: "decision-watch codeNouns", defect: "typeof $.fs.mkdir", flags: (t) => codeNouns(t).length > 0 },
  { name: "stamp near-miss", defect: "D`one`, a gloss.", flags: (t) => stampNearMiss(t).length > 0 },
  { name: "plain-diff looksSecret", defect: 'const k = "' + GHP + '"', flags: secretFlagged },
  { name: "ios-mockup duo frames", defect: '<div data-device="iphone-duo-unfolded"></div>', flags: (t) => iosCodes(iosPage(t)).length > 0 },
  { name: "time-pinned finder", defect: "await new Promise((r) => setTimeout(r, 500));", flags: (t) => timePinnedFindings(t).length > 0 },
];

// ---- the shared table: every scanner, every trap. A trap alone is clean; a trap then the defect is flagged.
for (const s of SCANNERS) {
  for (const t of TRAPS) {
    test(`${s.name}: ${t.name} alone finds nothing`, () => {
      assert.equal(s.flags(t.text), false, `false alarm on the trap alone: ${JSON.stringify(t.text)}`);
    });
    test(`${s.name}: ${t.name} does not hide the defect after it`, () => {
      assert.equal(s.flags(t.text + s.defect), true, `the defect after the trap was missed: ${JSON.stringify(t.text)}`);
    });
  }
}

// ---- distinct cases, kept per scanner. A case is removed from a scanner's own suite only when the table
// above runs the same trap with the same defect.
test("decision-watch machinePaths: a path in a multi-line template literal is flagged", () => {
  assert.ok(machinePaths("const t = `first\nD:/work/x\nlast`").length > 0, "path in a multi-line template literal");
});
test("decision-watch machinePaths: a backslash path beside a lone quote is flagged", () => {
  assert.ok(machinePaths("const q = \"<p>Don't</p>\"; const p = 'C:\\\\Work\\\\y'").length > 0, "backslash path beside a lone quote");
});
test("decision-watch machinePaths: clean text, a lone quote in a string, and the WindowsApps store name find nothing", () => {
  same(machinePaths("const s = \"<p>Don't</p>\"; const w = 'WindowsApps'"), [], "clean text");
});
test("decision-watch codeNouns: a line comment, a block comment, and template text hide a bare noun; code and ${} do not", () => {
  same(codeNouns("// do not call $.fs.mkdir here\nconst x = 1"), [], "line comment");
  same(codeNouns("/* $.fs.mkdir */ const x = 1"), [], "block comment");
  same(codeNouns("const t = `text $.fs.mkdir text`"), [], "template text");
  same(codeNouns("const t = `${$.fs.mkdir}`"), ["$.fs.mkdir"], "interpolation is code");
});
test("decision-watch codeNouns: a multi-line template literal keeps its text out of code, and its interpolation in", () => {
  same(codeNouns("const t = `first\n$.fs.mkdir text\nlast ${$.fs.mkdir}`"), ["$.fs.mkdir"], "only the interpolation");
});
test("decision-watch codeNouns: a lone quote in a comment does not hide the code after it", () => {
  same(codeNouns("// Don't call it\ntypeof $.fs.mkdir"), ["$.fs.mkdir"], "lone quote in a comment");
  same(codeNouns("await $.fs.write(file, text); // Don't\n"), [], "called method and a comment with a quote");
});
test("decision-watch codeNouns: a called $.fs.write and a called $.model.complete are not bare reads", () => {
  same(codeNouns("await $.fs.write(file, text); await $.model.complete({ model });"), [], "called methods");
});
// ---- run. Only when this file is the entry point: the decision-watch mod test imports two scanners from it.
if (isMain) {
  // The stamp fixture repo reads CI branch variables. This lint clears them, as the stamp suite does.
  delete process.env.GITHUB_REF;
  delete process.env.GITHUB_BASE_REF;
  delete process.env.GITHUB_ACTIONS;
  if (process.env.LIST_TESTS === "1") {
    for (const { name } of tests) console.log("LISTED " + JSON.stringify(name));
    process.exit(0);
  }
  let fail = 0;
  for (const { name, fn } of tests) {
    try {
      await fn();
      console.log(`PASS ${name}`);
    } catch (e) {
      fail++;
      console.log(`FAIL ${name}: ${String(e && e.message ? e.message : e).split("\n")[0]}`);
    }
  }
  if (runFolderPath) rmSync(runFolderPath, { recursive: true, force: true });
  console.log(`${tests.length - fail} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
}

#!/usr/bin/env node
// One shared parser for "claim the number at merge" (CLAUDE.md rule git-slug-then-claim-number:
// "Never allocate a numbered record on a branch. Write a slug. Claim the number at merge.").
//
// A branch writes a record with a PENDING marker instead of a number. This tool numbers every
// pending record, in order, from the next free number for its kind, then rewrites every cite of
// its slug to the numbered form. It never renumbers an existing record and never rewrites a
// repo's record shape: the shape is a config file the calling repo owns (see README.md). This
// file names no repo. Each repo reads its own fields off its own tree.
//
// Shapes covered:
//   1. number in frontmatter only
//   2. number in frontmatter AND filename
//   3. number in a heading, and for a split corpus in the filename too. Its own module,
//      formats/heading.mjs, picked by `"format": "heading"` in the config. This file dispatches
//      to it, and asks the off-branch question for it.
//
// Modes:
//   --claim   number every pending record and rewrite cites, before the merge, on a branch: the next number is above every number in the
//             tree, in the tip of --base (required), in every commit of the base ref's history
//             (a deleted record keeps its number), and in each RETIRED list. A shallow clone or an
//             unreadable history refuses. Then runs the config's `regenerate` command. Prints a last line `Record-claim: <ids>`,
//             the trailer for the claim commit. Writes the tree.
//   --check   refuse a malformed record, a duplicate id, or a cite that points at no record. On
//             the default branch, also refuse any pending record. Off it, refuse a
//             record numbered on the branch and a renamed numbered record, against the base
//             branch's tree. A removed record is allowed. A number that a `Record-claim:` commit
//             added is accepted, when the base ref never held it. Touches nothing. A base it cannot read fails the
//             check when GITHUB_ACTIONS is "true", and prints UNKNOWN and exits 0 elsewhere.
//
// All take --config <path> (required) and --root <path> (default: cwd). --check also takes
// --base <ref> (default: origin/$GITHUB_BASE_REF, else origin/<defaultBranch>).

import { realpathSync, readFileSync, writeFileSync, unlinkSync, readdirSync, statSync, existsSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { execFileSync } from "node:child_process";
import { join, resolve, posix, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import * as headingFormat from "./formats/heading.mjs";

// ---------------------------------------------------------------- config

export function loadConfig(path) {
  const config = JSON.parse(readFileSync(path, "utf8"));
  if (!Array.isArray(config.kinds) || !config.kinds.length) {
    throw new Error("config.kinds must be a non-empty array");
  }
  if (config.regenerate !== undefined && typeof config.regenerate !== "string") {
    throw new Error("config.regenerate must be a string: a shell command");
  }
  if (config.format === "heading") return headingFormat.normalizeConfig(config);
  if (config.format !== undefined) throw new Error(`config.format "${config.format}" is not a format this tool builds`);
  for (const kind of config.kinds) {
    for (const field of ["id", "folder", "prefix", "pendingRegex", "idTemplate"]) {
      if (!kind[field]) throw new Error(`kind ${kind.id ?? "(unnamed)"} is missing "${field}"`);
    }
    kind.filePattern ??= "*.md";
    kind.pad ??= 0;
    kind.location ??= "frontmatter";
    kind.order ??= "date";
    kind.numbering ??= "max_plus_one";
    kind.slugField ??= "slug";
    kind.dateField ??= "date";
    kind.glossField ??= "title";
    kind.requireFieldsOnPending ??= [];
    kind.excludeFiles ??= [];
    if (kind.location === "frontmatter+filename" && !kind.filenameTemplate) {
      throw new Error(`kind ${kind.id} has location "frontmatter+filename" but no "filenameTemplate"`);
    }
  }
  return config;
}

// ---------------------------------------------------------------- small utilities
// EOL is a property of the file on disk, never of the tool. Read the file's own ending, match it
// back on write, so a stamp never rewrites every line of a CRLF file.
function readFileEol(abs) {
  const raw = readFileSync(abs, "utf8");
  const crlf = (raw.match(/\r\n/g) ?? []).length;
  const lines = (raw.match(/\n/g) ?? []).length;
  return { text: raw.replace(/\r\n/g, "\n"), eol: crlf * 2 > lines ? "\r\n" : "\n" };
}
const withEol = (text, eol) => (eol === "\n" ? text : text.replace(/\n/g, eol));

function pad(n, width) {
  const s = String(n);
  return width > 0 ? s.padStart(width, "0") : s;
}

function renderId(kind, n) {
  return kind.idTemplate
    .replace(/\{prefix\}/g, kind.prefix)
    .replace(/\{n\}/g, pad(n, kind.pad));
}

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\-]/g, "\\$&");

// Read the number back out of an already-rendered id, or an already-renamed filename, by
// turning the template itself into a pattern — never a second, hand-written guess at the
// template's shape that could drift from `renderId`/`finishStamp`.
function templateToPattern(template, extra) {
  let re = "";
  for (const part of template.split(/(\{prefix\}|\{n\}|\{rest\})/)) {
    if (part === "{prefix}") re += escapeRe(String(extra.prefix));
    else if (part === "{n}") re += "(\\d+)";
    else if (part === "{rest}") re += "(.*)";
    else re += escapeRe(part);
  }
  return new RegExp("^" + re + "$");
}

// A minimal glob: `*` inside one segment, `**` across segments, in .gitignore syntax. Good enough for the exclude/scan lists this schema asks
// for, without pulling in a dependency for it (this tool is Node stdlib only, no npm).
function globToRegExp(pattern) {
  let re = "";
  for (let i = 0; i < pattern.length; i++) {
    const c = pattern[i];
    if (c === "*" && pattern[i + 1] === "*") {
      if (pattern[i + 2] === "/") { re += "(?:.*/)?"; i += 2; } else { re += ".*"; i += 1; }
    } else if (c === "*") re += "[^/]*";
    else if (c === "?") re += "[^/]";
    else re += c.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  }
  return new RegExp("^" + re + "$");
}
function makeMatcher(globs) {
  const res = (globs ?? []).map(globToRegExp);
  return (rel) => res.some((re) => re.test(rel));
}

// Every file under root, posix-relative, skipping `.git` and a nested checkout (a directory
// holding its own `.git`, e.g. a worktree). A nested checkout's files belong to another commit,
// not this one.
function walk(root) {
  const out = [];
  (function go(dir, prefix) {
    for (const name of readdirSync(dir)) {
      if (name === ".git") continue;
      const rel = prefix ? `${prefix}/${name}` : name;
      let s;
      try { s = statSync(join(dir, name)); } catch { continue; }
      if (s.isDirectory()) {
        if (existsSync(join(dir, name, ".git"))) continue;
        go(join(dir, name), rel);
      } else out.push(rel);
    }
  })(root, "");
  return out;
}

// ---------------------------------------------------------------- record files

function listRecordFiles(root, kind) {
  const dir = join(root, kind.folder);
  if (!existsSync(dir)) return [];
  const re = globToRegExp(kind.filePattern);
  const exclude = kind.excludeFiles?.length ? makeMatcher(kind.excludeFiles) : () => false;
  return readdirSync(dir).filter((n) => re.test(n) && !exclude(n)).sort().map((n) => `${kind.folder}/${n}`);
}

// The retired-numbers list: one file, RETIRED, in the kind's folder. One line per number: the id
// as the kind renders it, then optionally its last title. A blank line is skipped. Any other line
// that does not start with a rendered id is malformed. A retired number is taken forever.
export const RETIRED_FILE = "RETIRED";
function retiredNumbers(root, kind) {
  const nums = new Set();
  const bad = [];
  const abs = join(root, kind.folder, RETIRED_FILE);
  if (!existsSync(abs)) return { nums, bad };
  const pattern = templateToPattern(kind.idTemplate, kind);
  for (const [i, raw] of readFileEol(abs).text.split("\n").entries()) {
    const line = raw.trim();
    if (!line) continue;
    const m = pattern.exec(line.split(/\s+/)[0]);
    if (m) nums.add(Number(m[1]));
    else bad.push(`${kind.folder}/${RETIRED_FILE} line ${i + 1} does not start with an id like ${renderId(kind, 1)}`);
  }
  return { nums, bad };
}

function fieldRegex(field) {
  return new RegExp(`^${field}:[ \\t]*(.*)$`, "m");
}
function readField(raw, field) {
  const m = fieldRegex(field).exec(raw);
  if (!m) return undefined;
  let v = m[1].trim();
  if (v.startsWith('"') && v.endsWith('"')) v = JSON.parse(v);
  return v;
}
function splitFrontMatter(text) {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n/.exec(text);
  return m ? m[1] : null;
}

// A record's id value may name MORE than one number: "D-044 to D-046" for a range and "D-048 and
// D-053" for a list. This tool never PRODUCES either shape. It only ever assigns a single number
// to a pending record. But it must still count every number such a value already defines, or the
// running "highest so far" undercounts and the next assignment collides. Only a kind that opts in
// with `allowRanges: true` pays for this.
function idsFromValue(kind, idVal) {
  if (!idVal) return [];
  if (!kind.allowRanges) {
    const m = templateToPattern(kind.idTemplate, kind).exec(idVal);
    return m ? [Number(m[1])] : [];
  }
  const numRe = new RegExp(escapeRe(kind.prefix) + "-?(\\d+)", "g");
  const nums = [...idVal.matchAll(numRe)].map((m) => Number(m[1]));
  if (!nums.length) return [];
  if (/\bto\b/.test(idVal)) {
    const out = [];
    for (let n = Math.min(...nums); n <= Math.max(...nums); n++) out.push(n);
    return out;
  }
  return nums;
}

function loadRecord(root, kind, rel) {
  const { text, eol } = readFileEol(join(root, rel));
  const front = splitFrontMatter(text) ?? "";
  const name = rel.split("/").pop();
  // The numbers, when this record already carries at least one: read from the id field for a
  // frontmatter-only kind, or from the filename for a kind that also renames (a filename never
  // carries a range).
  //
  // PENDING is a different question for each location. A frontmatter-only kind reads it off the
  // id field, via `pendingRegex`. A kind that also renames reads it off the FILENAME instead, by
  // `filenamePendingPrefix` alone. The filename is the one place such a kind's number lives, so
  // the filename is the one place its pending state can live too.
  let numbers = [];
  let pending;
  if (kind.location === "frontmatter+filename") {
    const m = templateToPattern(kind.filenameTemplate, kind).exec(name);
    if (m) numbers = [Number(m[1])];
    pending = name.startsWith(kind.filenamePendingPrefix ?? "_");
  } else {
    numbers = idsFromValue(kind, readField(front, "id"));
    pending = new RegExp(kind.pendingRegex, "m").test(front);
  }
  return {
    rel, text, eol, front,
    slug: readField(front, kind.slugField) ?? rel.split("/").pop().replace(/^_+/, "").replace(/\.md$/, ""),
    date: readField(front, kind.dateField),
    gloss: kind.glossField === "title" ? readField(front, "title") : readField(front, kind.glossField),
    title: readField(front, "title"),
    pending,
    numbers,
    number: numbers[0] ?? null,
  };
}

// ---------------------------------------------------------------- git order. Asked only for a
// kind whose order is "merge", or by --check's branch questions. stamp() on any other order runs
// on a tree with no git at all.
function mergeOrder(root, folder) {
  const out = execFileSync("git", [
    "log", "--first-parent", "--diff-filter=A", "--name-only", "--reverse", "--format=%x00", "--", folder,
  ], { cwd: root, encoding: "utf8", maxBuffer: 256 * 1024 * 1024 });
  const order = [];
  let batch = [];
  for (const raw of out.split("\n")) {
    const line = raw.trim();
    if (line.startsWith("\0")) { order.push(...batch.sort()); batch = []; continue; }
    if (line.startsWith(folder + "/")) batch.push(line);
  }
  order.push(...batch.sort());
  return order;
}

export function currentBranch(root) {
  if (process.env.GITHUB_REF && process.env.GITHUB_REF.startsWith("refs/heads/")) {
    return process.env.GITHUB_REF.slice("refs/heads/".length);
  }
  try {
    let git = join(root, ".git");
    if (statSync(git).isFile()) {
      const m = /^gitdir:\s*(.+)$/m.exec(readFileSync(git, "utf8"));
      if (!m) return "";
      git = m[1].trim();
      if (!posix.isAbsolute(git) && !/^[A-Za-z]:[\\/]/.test(git)) git = join(root, git);
    }
    const head = readFileSync(join(git, "HEAD"), "utf8").trim();
    return /^ref: refs\/heads\/(.+)$/.exec(head)?.[1] ?? head;
  } catch {
    return "";
  }
}

// ---------------------------------------------------------------- ordering pending records
function orderPending(root, kind, pending) {
  if (kind.order === "merge") {
    const rank = new Map(mergeOrder(root, kind.folder).map((p, i) => [p, i]));
    return [...pending].sort((a, b) =>
      (rank.get(a.rel) ?? Number.MAX_SAFE_INTEGER) - (rank.get(b.rel) ?? Number.MAX_SAFE_INTEGER) ||
      a.slug.localeCompare(b.slug));
  }
  if (kind.order === "filename") {
    return [...pending].sort((a, b) => a.rel.localeCompare(b.rel));
  }
  // "date": a record with no date sorts as "", which
  // `--check`'s malformed-record refusal below catches when the kind requires the field.
  return [...pending].sort((a, b) =>
    (a.date ?? "").localeCompare(b.date ?? "") || a.slug.localeCompare(b.slug));
}

// ---------------------------------------------------------------- one kind, numbered
function stampKind(root, kind, records, extra) {
  const takenNumbers = [...records.flatMap((r) => r.numbers), ...retiredNumbers(root, kind).nums, ...(extra?.get(kind.id) ?? [])];
  const pending = orderPending(root, kind, records.filter((r) => r.pending));
  const taken = new Set(takenNumbers);

  const assigned = [];
  if (kind.numbering === "lowest_free") {
    let cursor = 1;
    for (const rec of pending) {
      while (taken.has(cursor)) cursor += 1;
      taken.add(cursor);
      assigned.push(finishStamp(root, kind, rec, cursor));
    }
  } else {
    let n = Math.max(0, ...takenNumbers);
    for (const rec of pending) {
      n += 1;
      assigned.push(finishStamp(root, kind, rec, n));
    }
  }
  return assigned;
}

function finishStamp(root, kind, rec, n) {
  const id = renderId(kind, n);
  // Turn the pending marker into `id: <id>`, against the front matter's own id line — never a
  // guess at the marker's exact shape, since `kind.pendingRegex` already found the line.
  const idLineRe = new RegExp(kind.pendingRegex, "m");
  const finalText = rec.text.replace(idLineRe, (whole) => {
    const key = /^([A-Za-z_]+):/.exec(whole)[1];
    return `${key}: ${id}`;
  });

  let newRel = rec.rel;
  if (kind.location === "frontmatter+filename") {
    const base = rec.rel.split("/").pop().replace(/^_+/, "").replace(/\.md$/, "");
    const name = kind.filenameTemplate
      .replace(/\{prefix\}/g, kind.prefix)
      .replace(/\{n\}/g, pad(n, kind.pad))
      .replace(/\{rest\}/g, base);
    newRel = `${kind.folder}/${name}`;
  }

  writeFileSync(join(root, newRel), withEol(finalText, rec.eol));
  if (newRel !== rec.rel) unlinkSync(join(root, rec.rel));
  return { id, n, prefix: kind.prefix, slug: rec.slug, gloss: rec.gloss, title: rec.title, rel: newRel, oldRel: rec.rel };
}

// ---------------------------------------------------------------- protected ranges
// A citation SYNTAX is usually explained somewhere, in prose, with the literal placeholder
// spelled out as an example, such as "[[slug]]" inside a code span. That example is not a
// citation of a record named "slug", so the dangling-cite refusal must not treat it as one. The
// protected spans are frontmatter, a fenced block, an inline code span, and a markdown link
// target.
const FM_RE = /^---\r?\n[\s\S]*?\r?\n---\r?\n/;
function protectedRanges(text) {
  const spans = [];
  const fm = FM_RE.exec(text);
  if (fm) spans.push([0, fm[0].length]);
  let fenceAt = null;
  let at = 0;
  for (const line of text.split("\n")) {
    if (/^\s*```/.test(line)) {
      if (fenceAt === null) fenceAt = at;
      else { spans.push([fenceAt, at + line.length]); fenceAt = null; }
    }
    at += line.length + 1;
  }
  if (fenceAt !== null) spans.push([fenceAt, text.length]);
  for (const m of text.matchAll(/`[^`\n]*`/g)) spans.push([m.index, m.index + m[0].length]);
  for (const m of text.matchAll(/\]\([^)\n]*\)/g)) spans.push([m.index, m.index + m[0].length]);
  return spans;
}
const inSpans = (spans, i) => spans.some(([a, b]) => i >= a && i < b);

// ---------------------------------------------------------------- cite rewrite
function renderCite(template, a) {
  return template
    .replace(/\{id\}/g, a.id)
    .replace(/\{gloss\}/g, a.gloss ?? "")
    .replace(/\{title\}/g, a.title ?? "");
}

// A citation may name its own prefix beside the slug (`D‹slug›`): resolve it only when that
// prefix matches the record the slug actually belongs to. A mismatched pair is left as text,
// never a guess at which kind was meant.
function resolveCite(config, byId, groups) {
  const slug = groups[(config.cite.slugGroup ?? 1) - 1];
  const a = byId.get(slug);
  if (!a) return null;
  if (config.cite.prefixGroup && groups[config.cite.prefixGroup - 1] !== a.prefix) return null;
  return a;
}

function rewriteCites(root, config, byId, files) {
  if (!config.cite) return 0;
  const pattern = new RegExp(config.cite.pattern, "g");
  const scan = makeMatcher(config.cite.scanGlobs ?? ["**/*.md"]);
  const exclude = makeMatcher(config.cite.excludeGlobs ?? []);
  let touched = 0;
  for (const rel of files.filter((f) => scan(f) && !exclude(f))) {
    const abs = join(root, rel);
    const { text, eol } = readFileEol(abs);
    // UNGUARDED, on purpose: a real citation of a slug THIS run assigns is rewritten whether or
    // not it sits inside a backtick span (a stylistic choice some entries make). Only the DANGLING-cite check below needs to tell an
    // example apart from a citation, because only it can otherwise refuse to write over nothing
    // wrong. The rewrite itself never invents a match: `resolveCite` already requires the slug
    // to be one this run actually assigned.
    const next = text.replace(pattern, (whole, ...args) => {
      const a = resolveCite(config, byId, args);
      return a ? renderCite(config.cite.template, a) : whole;
    });
    if (next !== text) { writeFileSync(abs, withEol(next, eol)); touched += 1; }
  }
  return touched;
}

// ---------------------------------------------------------------- structural validation, shared
// by stamp() (which refuses to write on top of it) and --check (which adds the branch question,
// below, to it). One implementation of "is this record file sound" for both, so they cannot
// silently disagree about what counts as malformed.
function validate(root, config) {
  const problems = [];
  const bySlug = new Map();
  const prefixBySlug = new Map();
  const byKind = new Map();

  for (const kind of config.kinds) {
    const files = listRecordFiles(root, kind);
    const records = files.map((rel) => loadRecord(root, kind, rel));
    byKind.set(kind, records);
    const seen = new Map();
    for (const rec of records) {
      const rel = rec.rel;
      if (bySlug.has(rec.slug)) problems.push(`duplicate slug "${rec.slug}": ${bySlug.get(rec.slug)} and ${rel}`);
      bySlug.set(rec.slug, rel);
      prefixBySlug.set(rec.slug, kind.prefix);

      if (rec.numbers.length) {
        for (const num of rec.numbers) {
          if (seen.has(num)) problems.push(`duplicate id ${renderId(kind, num)}: ${seen.get(num)} and ${rel}`);
          seen.set(num, rel);
        }
      } else if (!rec.pending) {
        problems.push(`${rel} has an id this tool does not recognise as pending or numbered — malformed record`);
      }
      if (rec.pending) {
        for (const field of kind.requireFieldsOnPending) {
          if (!rec[field]) problems.push(`${rel} has no \`${field}\`; it cannot be claimed in order`);
        }
      }
    }
  }

  for (const kind of config.kinds) {
    const { nums, bad } = retiredNumbers(root, kind);
    problems.push(...bad);
    for (const rec of byKind.get(kind)) {
      for (const n of rec.numbers) {
        if (nums.has(n)) problems.push(`${renderId(kind, n)} is in ${kind.folder}/${RETIRED_FILE} and ${rec.rel} still holds it. Remove one of them.`);
      }
    }
  }

  if (config.cite) {
    const pattern = new RegExp(config.cite.pattern, "g");
    const scan = makeMatcher(config.cite.scanGlobs ?? ["**/*.md"]);
    const exclude = makeMatcher(config.cite.excludeGlobs ?? []);
    for (const rel of walk(root).filter((f) => scan(f) && !exclude(f))) {
      const { text } = readFileEol(join(root, rel));
      const guarded = protectedRanges(text);
      for (const m of text.matchAll(pattern)) {
        if (inSpans(guarded, m.index)) continue; // a code-span example of the syntax, not a cite
        const slug = m[config.cite.slugGroup ?? 1];
        const prefixOk = !config.cite.prefixGroup || m[config.cite.prefixGroup] === prefixBySlug.get(slug);
        if (!bySlug.has(slug) || !prefixOk) problems.push(`${rel} cites [[${slug}]], which no record file defines`);
      }
    }
  }

  return { problems, bySlug, byKind };
}

// ---------------------------------------------------------------- stamp()
// The helpers format 3 shares with the other two, so all three read EOL and git the same way.
const HELPERS = { readFileEol, withEol, currentBranch, makeMatcher };

// `extra`: Map kind.id -> numbers to treat as taken, besides the tree's own. --claim passes the
// base tip's. Without it, the tree alone decides.
export function stamp(root, config, extra) {
  if (config.format === "heading") return headingFormat.stamp(root, config, HELPERS, extra);
  const { problems, byKind } = validate(root, config);
  if (problems.length) {
    return { problems, assigned: [], glossed: 0 };
  }

  const allAssigned = [];
  for (const kind of config.kinds) {
    const assigned = stampKind(root, kind, byKind.get(kind), extra);
    for (const a of assigned) console.log(`stamped ${a.id}  ${a.slug}  ${a.title ?? ""}`.trimEnd());
    allAssigned.push(...assigned);
  }
  if (!allAssigned.length) {
    console.log("nothing pending.");
    return { problems: [], assigned: allAssigned, glossed: 0 };
  }
  const byId = new Map(allAssigned.map((a) => [a.slug, a]));
  const files = walk(root);
  const glossed = rewriteCites(root, config, byId, files);
  console.log(`${allAssigned.length} entry(ies) stamped; ${glossed} document(s) had a cite rewritten.`);
  return { problems: [], assigned: allAssigned, glossed };
}

// ---------------------------------------------------------------- --check

// A pull_request checkout is a detached merge commit, so it is never the default branch, whatever
// its first parent is. GitHub sets GITHUB_BASE_REF only on a pull_request event, and names the
// ref refs/pull/<n>/merge.
export function onDefaultBranch(root, config) {
  if (process.env.GITHUB_BASE_REF) return false;
  if ((process.env.GITHUB_REF ?? "").startsWith("refs/pull/")) return false;
  return Boolean(config.defaultBranch) && currentBranch(root) === config.defaultBranch;
}

export function baseRef(config, opts = {}) {
  if (opts.base) return opts.base;
  if (process.env.GITHUB_BASE_REF) return `origin/${process.env.GITHUB_BASE_REF}`;
  if (config.defaultBranch) return `origin/${config.defaultBranch}`;
  return null;
}

function gitOut(root, args, input) {
  return execFileSync("git", args, {
    cwd: root, input, maxBuffer: 256 * 1024 * 1024, stdio: [input === undefined ? "ignore" : "pipe", "pipe", "pipe"],
  });
}

// Write the record paths of one commit into a new temp dir, from git's own objects, so the
// engine's own loader can read the base tree the same way it reads this one. No second parser.
// Only regular files are written. A symlink is not a record file here either.
function materializeTree(root, commit, paths) {
  const dir = mkdtempSync(join(tmpdir(), "stamp-base-"));
  const listing = gitOut(root, ["--literal-pathspecs", "ls-tree", "-r", "-z", commit, "--", ...paths]).toString("utf8");
  const files = [];
  for (const entry of listing.split("\0")) {
    const m = /^(\d+) blob ([0-9a-f]+)\t(.+)$/s.exec(entry);
    if (m && (m[1] === "100644" || m[1] === "100755")) files.push({ oid: m[2], rel: m[3] });
  }
  if (!files.length) return dir;
  const out = gitOut(root, ["cat-file", "--batch"], files.map((f) => f.oid).join("\n") + "\n");
  let at = 0;
  for (const f of files) {
    const nl = out.indexOf(0x0a, at);
    const size = Number(out.subarray(at, nl).toString("utf8").split(" ")[2]);
    const body = out.subarray(nl + 1, nl + 1 + size);
    at = nl + 1 + size + 1;
    mkdirSync(dirname(join(dir, f.rel)), { recursive: true });
    writeFileSync(join(dir, f.rel), body);
  }
  return dir;
}

// Every numbered record in one tree, keyed so the same record in two trees has the same key. A
// frontmatter kind keys a record by its slug, since the slug is the record's own name before and
// after its number. heading.mjs keys its own.
function numberedRecords(root, config) {
  if (config.format === "heading") return headingFormat.numberedRecords(root, config, HELPERS);
  const out = [];
  for (const kind of config.kinds) {
    for (const rel of listRecordFiles(root, kind)) {
      const rec = loadRecord(root, kind, rel);
      for (const n of rec.numbers) {
        out.push({ key: `${kind.id}\0${rec.slug}\0${n}`, name: rec.slug, kind: kind.id, n, rel, id: renderId(kind, n), prefix: kind.prefix });
      }
    }
  }
  return out;
}

const recordPaths = (config) =>
  config.format === "heading" ? headingFormat.recordPaths(config) : config.kinds.map((k) => k.folder);

// Every number one tree holds, per kind id: its numbered records and each RETIRED list. The
// heading shape reads no retired list.
function takenNumbers(root, config) {
  const out = new Map(config.kinds.map((k) => [k.id, new Set()]));
  for (const r of numberedRecords(root, config)) out.get(r.kind).add(r.n);
  if (config.format !== "heading") {
    for (const k of config.kinds) for (const n of retiredNumbers(root, k).nums) out.get(k.id).add(n);
  }
  return out;
}

// The numbers the tip of `ref` takes. Throws when git cannot read it.
function tipTaken(root, config, ref) {
  const dir = materializeTree(root, ref, recordPaths(config));
  try {
    return takenNumbers(dir, config);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

// The numbers one historical file holds, for kind `kind`: [] when it is not that kind's record file.
function numbersOfFile(config, kind, rel, text) {
  if (config.format === "heading") return headingFormat.numbersOfFile(kind, rel, text);
  if (!rel.startsWith(kind.folder + "/") || rel.slice(kind.folder.length + 1).includes("/")) return [];
  const name = rel.split("/").pop();
  if (!globToRegExp(kind.filePattern).test(name) || makeMatcher(kind.excludeFiles)(name)) return [];
  if (kind.location === "frontmatter+filename") {
    const m = templateToPattern(kind.filenameTemplate, kind).exec(name);
    return m ? [Number(m[1])] : [];
  }
  return idsFromValue(kind, readField(splitFrontMatter(text.replace(/\r\n/g, "\n")) ?? "", "id"));
}

const FETCH_REMEDY = "Fetch full history (actions/checkout with fetch-depth: 0, or git fetch --unshallow).";

// Every number the tip of `ref` takes, plus every number any commit in its history ever held, per
// kind id. A deleted record leaves its number here, so no claim reuses it: the next number is
// above the highest ever used, not the highest still present. Throws when git cannot read the tip
// or the history, or when the clone is shallow: a history that is cut short would hand out a low
// number, so the read refuses instead.
function everTaken(root, config, ref) {
  const out = tipTaken(root, config, ref);
  let log;
  try {
    if (gitOut(root, ["rev-parse", "--is-shallow-repository"]).toString().trim() === "true") {
      throw new Error("the clone is shallow");
    }
    // --full-history: the default simplification can prune the side of a merge where a number was
    // added and then deleted, and that number would be reused.
    // ponytail: reads today's record paths only. A number used under a path a kind has since left
    // is not seen. Upgrade: a per-kind list of old paths in the config.
    log = gitOut(root, ["log", "--full-history", "-m", "--no-renames", "--raw", "-z", "--format=", ref, "--", ...recordPaths(config)]).toString("utf8");
  } catch (e) {
    throw new Error(`git cannot read the full history of ${ref} (${String(e.message).split("\n")[0]}), so a number deleted from it cannot be told from a free one. ${FETCH_REMEDY}`);
  }
  const files = new Map(); // oid -> Set of paths
  const toks = log.split("\0").map((t) => t.replace(/^\n+/, ""));
  for (let i = 0; i + 1 < toks.length; i++) {
    const m = /^:\d+ \d+ ([0-9a-f]+) ([0-9a-f]+) \S+$/.exec(toks[i]);
    if (!m) continue;
    for (const oid of [m[1], m[2]]) if (!/^0+$/.test(oid)) files.set(oid, (files.get(oid) ?? new Set()).add(toks[i + 1]));
    i += 1;
  }
  if (!files.size) return out;
  const oids = [...files.keys()];
  const blobs = gitOut(root, ["cat-file", "--batch"], oids.join("\n") + "\n");
  let at = 0;
  for (const oid of oids) {
    const nl = blobs.indexOf(0x0a, at);
    const size = Number(blobs.subarray(at, nl).toString("utf8").split(" ")[2]);
    if (!Number.isFinite(size)) throw new Error(`git cannot read blob ${oid} of ${ref}. ${FETCH_REMEDY}`);
    const text = blobs.subarray(nl + 1, nl + 1 + size).toString("utf8");
    at = nl + 1 + size + 1;
    for (const rel of files.get(oid)) for (const kind of config.kinds) for (const n of numbersOfFile(config, kind, rel, text)) out.get(kind.id).add(n);
  }
  return out;
}

// The (kind, number) pairs one commit's tree holds. A commit git cannot read, such as the parent
// of a root commit, holds none.
function numbersAt(root, config, commit) {
  let dir;
  try {
    dir = materializeTree(root, commit, recordPaths(config));
  } catch {
    return new Set();
  }
  try {
    return new Set(numberedRecords(dir, config).map((r) => `${r.kind}\0${r.n}`));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

// The ids that `Record-claim:` commits of base..HEAD added. A trailer names ids. It vouches for
// an id only when the same commit ADDED the number: the commit's parent lacks it, and the commit
// holds it. A number a commit only edits is not vouched for.
function claimedByTrailer(root, config, base) {
  const out = new Set();
  const log = gitOut(root, ["log", "--no-merges", "--format=%x01%H%n%(trailers:key=Record-claim,valueonly)", `${base}..HEAD`]).toString("utf8");
  for (const chunk of log.split("\x01").slice(1)) {
    const [hash, ...vals] = chunk.split("\n");
    const ids = new Set(vals.join(" ").split(/[\s,]+/).filter(Boolean));
    if (!ids.size) continue;
    const before = numbersAt(root, config, `${hash}^`);
    const after = materializeTree(root, hash, recordPaths(config));
    try {
      for (const r of numberedRecords(after, config)) {
        if (ids.has(r.id) && !before.has(`${r.kind}\0${r.n}`)) out.add(r.id);
      }
    } finally {
      rmSync(after, { recursive: true, force: true });
    }
  }
  return out;
}

// Off the default branch, against the base tree:
//   - every record that carries a number in this tree must carry that same number, under the
//     same key, in the base tree. A new record with a number fails, and so does a record that was
//     pending on the base and has a number now. A record whose number the base holds under
//     another key was renamed, and gets its own message.
//   - a record may be deleted. Its number stays taken: the claim reads the history of the base ref
//     (everTaken) and never hands the number out again. A RETIRED list, where a format has one,
//     is append-only: a number the base list names stays named.
// The base tree is the merge base of HEAD and the base ref, never the ref's tip: the tip may have
// taken the same number since, for another record, and that reads as "already there" and hides
// the defect. In a pull_request merge commit the merge base IS the base ref's tip, so both read
// the same tree there.
//   - one exception. A number that a `Record-claim:` commit of the branch added is accepted when
//     the base ref, tip and history, never held it. The commit must have added the number itself (the tool claims before the merge, against the
//     tip). A number with no such trailer stays refused, and so does one the base ref took since.
//
// A base that cannot be read comes back as `unknown`, never as a pass. check() decides whether
// that fails the run. A check that did not run is not green.
function branchNumbered(root, config, opts) {
  const ref = baseRef(config, opts);
  const remedy = "Fetch the base branch with its history (actions/checkout with fetch-depth: 0), or pass --base <ref>.";
  if (!ref) {
    return { problems: [], unknown: `branch question could not run: no base ref. Set "defaultBranch" in the config, or pass --base <ref>.` };
  }
  let base;
  try {
    base = gitOut(root, ["merge-base", "HEAD", ref]).toString("utf8").trim();
  } catch {
    base = "";
  }
  if (!base) return { problems: [], unknown: `branch question could not run: git cannot read a merge base of HEAD and ${ref}. ${remedy}` };
  let dir;
  try {
    dir = materializeTree(root, base, recordPaths(config));
    const before = numberedRecords(dir, config);
    const now = numberedRecords(root, config);
    const numberOf = (r) => `${r.kind}\0${r.n}`;
    const baseKeys = new Set(before.map((r) => r.key));
    const nowKeys = new Set(now.map((r) => r.key));
    const baseByNumber = new Map();
    for (const r of before) if (!baseByNumber.has(numberOf(r))) baseByNumber.set(numberOf(r), r);
    const problems = [];
    const claims = claimedByTrailer(root, config, base);
    let tip; // read only when a claim needs it
    // A record the default branch already holds, under the same number and key, is synced in, not
    // numbered here. The old post-merge stamp numbered them on main with no trailer. Read once.
    let onDefault; // opts.defaultRef is for tests, whose fixture has no origin
    let defaultUnreadable = null;
    const defaultRef = opts.defaultRef ?? `origin/${config.defaultBranch}`;
    const defaultHas = (r) => {
      if (!onDefault) {
        try {
          const d = materializeTree(root, defaultRef, recordPaths(config));
          try { onDefault = new Set(numberedRecords(d, config).map((x) => x.key)); } finally { rmSync(d, { recursive: true, force: true }); }
        } catch { onDefault = new Set(); defaultUnreadable = defaultRef; }
      }
      return onDefault.has(r.key);
    };
    for (const r of now) {
      if (baseKeys.has(r.key) || defaultHas(r)) continue;
      if (claims.has(r.id)) {
        tip ??= everTaken(root, config, ref);
        if (tip.get(r.kind).has(r.n)) {
          problems.push(`${r.rel}: ${r.id} was claimed on this branch, and ${ref} holds or once held ${r.id}. ` +
            `Merge ${ref} into the branch, write the pending marker again, and claim again.`);
        }
        continue;
      }
      const old = baseByNumber.get(numberOf(r));
      if (old && !nowKeys.has(old.key)) {
        problems.push(`${r.rel}: ${r.id} was renamed on a branch. ${ref} holds it under the key "${old.name}", and this tree ` +
          `holds it under "${r.name}". A numbered record keeps its key. Restore "${old.name}", or delete the record and claim a new number.`);
      } else {
        problems.push(`${r.rel} is numbered ${r.id} on a branch, and ${ref} does not number it so. ` +
          `Write the pending marker and let the stamp claim the number at merge.` +
          (defaultUnreadable
            ? ` The default-branch ref ${defaultUnreadable} was unreadable, so a record synced in from it cannot be told from one numbered here. ` +
              `Use actions/checkout with fetch-depth: 0, or run git fetch origin ${config.defaultBranch}.`
            : ""));
      }
    }
    // A retired-numbers list exists for the frontmatter shapes only. The heading shape reads none.
    const listed = (dir_, kind) => (config.format === "heading" ? new Set() : retiredNumbers(dir_, kind).nums);
    const retiredNow = new Set();
    for (const kind of config.kinds) for (const n of listed(root, kind)) retiredNow.add(`${kind.id}\0${n}`);
    for (const kind of config.kinds) {
      for (const n of listed(dir, kind)) {
        if (!retiredNow.has(`${kind.id}\0${n}`)) {
          problems.push(`${renderId(kind, n)} is removed from ${kind.folder}/${RETIRED_FILE} on a branch. The list is append-only. Restore the line.`);
        }
      }
    }
    return { problems: [...new Set(problems)], unknown: null };
  } catch (e) {
    if (String(e.message).startsWith("git cannot read the full history")) return { problems: [], unknown: `branch question could not run: ${e.message}` };
    return { problems: [], unknown: `branch question could not run: git cannot read the tree of ${base} (${String(e.message).split("\n")[0]}). ${remedy}` };
  } finally {
    if (dir) rmSync(dir, { recursive: true, force: true });
  }
}

// On the default branch: any pending record means a record reached the branch unclaimed. The
// claim runs before the merge, so none is expected here, HEAD's own included.
function defaultPending(config, byKind, branch) {
  const problems = [];
  for (const kind of config.kinds) {
    for (const rec of byKind.get(kind).filter((r) => r.pending)) {
      problems.push(`${rec.rel} is still pending on ${branch}. Claim the number before the merge. Run the merge tool on a pull request that carries it.`);
    }
  }
  return problems;
}

// Returns the problems. When the off-branch question could not read the base, the verdict
// depends on where it runs. In GitHub Actions (GITHUB_ACTIONS is "true") that is a problem, so
// CI fails. Elsewhere it is set on the array as `unknown`, a line that starts with "UNKNOWN:",
// and it is not a problem: a local run warns and exits 0, and never claims the tree is in order.
export function check(root, config, opts = {}) {
  const onDefault = onDefaultBranch(root, config);
  let problems;
  if (config.format === "heading") {
    problems = headingFormat.check(root, config, HELPERS, onDefault);
  } else {
    const v = validate(root, config);
    problems = v.problems;
    if (onDefault) problems.push(...defaultPending(config, v.byKind, config.defaultBranch));
  }
  if (!onDefault) {
    const branch = branchNumbered(root, config, opts);
    problems.push(...branch.problems);
    if (branch.unknown && process.env.GITHUB_ACTIONS === "true") problems.push(branch.unknown);
    else if (branch.unknown) problems.unknown = `UNKNOWN: ${branch.unknown}`;
  }
  return problems;
}

// ---------------------------------------------------------------- --claim
// stamp() with the base tip's numbers taken too. Throws when git cannot read the tip: a claim made
// without it could hand out a number the base holds. Runs the config's `regenerate` after, when
// something was claimed. The tree is written either way.
export function claim(root, config, baseTip) {
  let taken;
  try {
    taken = everTaken(root, config, baseTip);
  } catch (e) {
    throw new Error(`git cannot read ${baseTip} (${String(e.message).split("\n")[0]}). Nothing was written`);
  }
  const result = stamp(root, config, taken);
  if (!result.problems.length && result.assigned.length && config.regenerate) {
    try {
      execFileSync("bash", ["-c", config.regenerate], { cwd: root, stdio: "inherit" });
    } catch {
      throw new Error("the regenerate command failed. The tree holds the claim. Discard the tree, and do not commit it");
    }
  }
  return result;
}

// ---------------------------------------------------------------- CLI
function parseArgv(argv) {
  const out = { mode: null, config: null, root: process.cwd(), base: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--check" || argv[i] === "--claim") out.mode = argv[i].slice(2);
    else if (argv[i] === "--config") out.config = argv[++i];
    else if (argv[i] === "--root") out.root = argv[++i];
    else if (argv[i] === "--base") out.base = argv[++i];
  }
  return out;
}

// Compare real paths: a symlinked directory (macOS /var -> /private/var) made the two differ and the
// CLI exit 0 with no output.
const real = (p) => { try { return realpathSync(p); } catch { return resolve(p); } };
const isMain = Boolean(process.argv[1]) && real(process.argv[1]) === real(fileURLToPath(import.meta.url));

if (isMain) {
  const args = parseArgv(process.argv.slice(2));
  if (!args.mode || !args.config) {
    console.error("usage: node stamp.mjs --check|--claim --config <path> [--root <path>] [--base <ref>]   (--claim needs --base)");
    process.exit(2);
  }
  if (args.mode === "claim" && !args.base) {
    console.error("claim REFUSES: --claim needs --base <ref>, the ref whose tip holds the numbers already taken.");
    process.exit(2);
  }
  const config = loadConfig(args.config);
  if (args.mode === "claim") {
    let result;
    try {
      result = claim(args.root, config, args.base);
    } catch (e) {
      console.error(`claim REFUSES: ${String(e.message).split("\n")[0]}.`);
      process.exit(1);
    }
    if (result.problems.length) {
      console.error("claim REFUSES: the tree has a problem --check would also refuse. Nothing was written.");
      for (const p of result.problems) console.error(p);
      process.exit(1);
    }
    if (result.assigned.length) console.log(`Record-claim: ${result.assigned.map((a) => a.id).join(" ")}`);
  } else {
    const problems = check(args.root, config, { base: args.base });
    if (problems.unknown) console.error(problems.unknown);
    if (problems.length) {
      for (const p of problems) console.error(p);
      process.exit(1);
    }
    if (problems.unknown) process.exit(0);
    console.log(config.format === "heading"
      ? "every pending heading is well formed, every id is unique, nothing is numbered out of turn."
      : "every pending record is in order, every id is unique, every cite resolves.");
  }
}

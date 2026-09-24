#!/usr/bin/env node
// One shared parser for "claim the number at merge" (CLAUDE.md rule git-slug-then-claim-number:
// "Never allocate a numbered record on a branch. Write a slug. Claim the number at merge.").
//
// A branch writes a record with a PENDING marker instead of a number. This tool numbers every
// pending record, in order, from the next free number for its kind, then rewrites every cite of
// its slug to the numbered form. It never renumbers an existing record and never rewrites a
// repo's record shape: the shape is a config file the calling repo owns (see README.md).
//
// Formats covered (see decisions/one-shared-record-stamp.md for the design and what is out of
// scope):
//   1. number in frontmatter only            (q_max docs/decisions, sharables decisions/findings/gaps)
//   2. number in frontmatter AND filename     (job-cost-reporting docs/decisions, docs/build, ...)
//   3. number in a heading, and for a split corpus in the filename too (banchi docs/decisions and
//      docs/CODES-DECISIONS.md). Its own module, formats/heading.mjs, picked by
//      `"format": "heading"` in the config. This file only dispatches to it.
//
// Modes:
//   --stamp   number every pending record and rewrite cites. Writes the tree.
//   --check   refuse a record numbered on a branch, a malformed record, a duplicate id, or a
//             cite that points at no record. Touches nothing.
//
// Both take --config <path> (required) and --root <path> (default: cwd).

import { readFileSync, writeFileSync, unlinkSync, readdirSync, statSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join, resolve, posix } from "node:path";
import { fileURLToPath } from "node:url";
import * as headingFormat from "./formats/heading.mjs";

// ---------------------------------------------------------------- config

export function loadConfig(path) {
  const config = JSON.parse(readFileSync(path, "utf8"));
  if (!Array.isArray(config.kinds) || !config.kinds.length) {
    throw new Error("config.kinds must be a non-empty array");
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

// ---------------------------------------------------------------- small utilities shared with
// q_max's harness/decision-refs.mjs: EOL is a property of the file on disk, never of the tool
// (D-338 in that log). Read the file's own ending, match it back on write.
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

// A minimal glob: `*` inside one segment, `**` across segments, matched the way q_max's
// globToSource reads .gitignore syntax. Good enough for the exclude/scan lists this schema asks
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
// holding its own `.git`, e.g. a worktree) the same way q_max's walk does — a nested checkout's
// files belong to another commit, not this one.
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

// A record's id value may name MORE than one number: q_max writes "D-044 to D-046" for a range
// and "D-048 and D-053" for a list (brief point 7). This tool never PRODUCES either shape — it
// only ever assigns a single number to a pending record — but it must still count every number
// such a value already defines, or the running "highest so far" undercounts and the next
// assignment collides. Only a kind that opts in with `allowRanges: true` pays for this; jcr and
// sharables never write a multi-id value, so their kinds skip it.
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
  // frontmatter-only kind, or from the filename for a kind that also renames (which never
  // carries a range — jcr's own tool has no such shape).
  //
  // PENDING is a different question for each location. A frontmatter-only kind reads it off the
  // id field, via `pendingRegex` (q_max and sharables both write `id: pending`). A kind that also
  // renames reads it off the FILENAME instead: jcr's own tool decides pending by the leading `_`
  // alone, never by the id field's content (`toolchain/claim_ids.py`'s `survey()`), so a stray
  // value there is not this tool's business either.
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

// ---------------------------------------------------------------- git order (only path in this
// file that spawns git, and only asked for a kind whose order is "merge" or whose check runs on
// the default branch — matching q_max's own boundary for the same reason: every other mode must
// run on a tree with no git at all)
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

function addedByHead(root, folder) {
  try {
    const out = execFileSync("git", [
      "diff-tree", "-r", "-m", "--first-parent", "--root", "--no-commit-id", "--diff-filter=A", "--name-only",
      "HEAD", "--", folder,
    ], { cwd: root, encoding: "utf8", maxBuffer: 64 * 1024 * 1024, stdio: ["ignore", "pipe", "ignore"] });
    return new Set(out.split("\n").map((l) => l.trim()).filter((l) => l.startsWith(folder + "/")));
  } catch {
    return null;
  }
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
  // "date": the order jcr and sharables both claim in. A record with no date sorts as "", which
  // `--check`'s malformed-record refusal below catches when the kind requires the field.
  return [...pending].sort((a, b) =>
    (a.date ?? "").localeCompare(b.date ?? "") || a.slug.localeCompare(b.slug));
}

// ---------------------------------------------------------------- one kind, numbered
function stampKind(root, kind, records) {
  const takenNumbers = records.flatMap((r) => r.numbers);
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
// spelled out as an example — q_max's own README does this for "[[slug]]" itself, inside a code
// span. That example is not a citation of a record named "slug", and neither the rewrite nor
// the dangling-cite refusal may treat it as one. Lifted from q_max's own `protectedRanges`
// (harness/decision-refs.mjs), which exists for exactly this reason, over frontmatter, a fenced
// block, an inline code span, or a markdown link target.
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

// A citation may name its own prefix beside the slug (sharables' `D‹slug›`): resolve it only when
// that prefix matches the record the slug actually belongs to, the way sharables' own
// `assigned.get((letter, slug))` refuses a mismatched pair rather than guessing which kind was
// meant.
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
    // UNGUARDED, on purpose, matching q_max's own `stamp()` rewrite exactly: a real citation of
    // a slug THIS run assigns is rewritten whether or not it sits inside a backtick span (a
    // stylistic choice some entries make). Only the DANGLING-cite check below needs to tell an
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
// by --stamp (which refuses to write on top of it) and --check (which adds the branch question,
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

// ---------------------------------------------------------------- --stamp
// The helpers format 3 shares with the other two, so all three read EOL and git the same way.
const HELPERS = { readFileEol, withEol, addedByHead, currentBranch };

export function stamp(root, config) {
  if (config.format === "heading") return headingFormat.stamp(root, config, HELPERS);
  const { problems, byKind } = validate(root, config);
  if (problems.length) {
    return { problems, assigned: [], glossed: 0 };
  }

  const allAssigned = [];
  for (const kind of config.kinds) {
    const assigned = stampKind(root, kind, byKind.get(kind));
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
export function check(root, config) {
  if (config.format === "heading") return headingFormat.check(root, config, HELPERS);
  const { problems, byKind } = validate(root, config);
  const branch = currentBranch(root);
  const onDefault = config.defaultBranch ? branch === config.defaultBranch : false;
  if (onDefault) {
    for (const kind of config.kinds) {
      const pending = byKind.get(kind).filter((r) => r.pending);
      if (!pending.length) continue;
      const added = addedByHead(root, kind.folder);
      for (const rec of pending) {
        if (added && !added.has(rec.rel)) {
          problems.push(`${rec.rel} is still pending on ${branch}, added before HEAD — the stamp did not run, or its push was rejected`);
        }
      }
    }
  }
  return problems;
}

// ---------------------------------------------------------------- CLI
function parseArgv(argv) {
  const out = { mode: null, config: null, root: process.cwd() };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--stamp" || argv[i] === "--check") out.mode = argv[i].slice(2);
    else if (argv[i] === "--config") out.config = argv[++i];
    else if (argv[i] === "--root") out.root = argv[++i];
  }
  return out;
}

const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (isMain) {
  const args = parseArgv(process.argv.slice(2));
  if (!args.mode || !args.config) {
    console.error("usage: node stamp.mjs --stamp|--check --config <path> [--root <path>]");
    process.exit(2);
  }
  const config = loadConfig(args.config);
  if (args.mode === "stamp") {
    const result = stamp(args.root, config);
    if (result.problems.length) {
      console.error("stamp REFUSES: the tree has a problem --check would also refuse. Nothing was written.");
      for (const p of result.problems) console.error(p);
      process.exit(1);
    }
  } else {
    const problems = check(args.root, config);
    if (problems.length) {
      for (const p of problems) console.error(p);
      process.exit(1);
    }
    console.log(config.format === "heading"
      ? "every pending heading is well formed, every id is unique, nothing is numbered out of turn."
      : "every pending record is in order, every id is unique, every cite resolves.");
  }
}

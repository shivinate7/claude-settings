// Format 3 for stamp.mjs: the number lives in a markdown HEADING, and for a split corpus also in
// the FILENAME. Read off banchi's own `scripts/claim-ids.py` (main 053acf0), rule by rule. The
// rule list, and what this module covers or leaves out, is in decisions/one-shared-record-stamp.md.
//
// Two corpus shapes, one per kind:
//   folder  one file per record, the record's heading on the file's FIRST line, the number in the
//           heading AND the filename (banchi docs/decisions: `D-<slug>.md` holding
//           `## D-<slug> — Title` becomes `D258-<slug>.md` holding `## D258 — Title`).
//   file    one flat file, every heading line is a record (banchi docs/CODES-DECISIONS.md:
//           `## C-<slug> — Title` becomes `## C12 — Title`). No rename.
//
// A claim is claim-ids.py's own: max + 1 over every numbered heading the kind holds, never a gap,
// then every bounded occurrence of the slug token in every walked text file becomes the id.
// Banchi's generators (the ORDER.json append and the CLAUDE.md index, both owned by
// scripts/index-decisions.py) are NOT here. They run as the action's `regenerate` command.
//
// stamp.mjs dispatches here when config.format is "heading". Its own helpers come in as `h`, so
// this module shares one EOL rule and one git reader with the other two formats.

import { readFileSync, writeFileSync, renameSync, readdirSync, lstatSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join } from "node:path";

// Python's `\w` in a str pattern is Unicode: a letter, a number, or `_`, by category. JS `\w` is
// ASCII only. claim-ids.py's boundary `(?<![-\w])...(?![-\w])` must mean the same thing here.
export const PY_WORD = "[\\p{L}\\p{N}_]";

// Every pattern here carries the `u` flag (for `\p{L}`), and `u` refuses an escaped `-` outside a
// class, so `-` stays bare. Outside a class it is a literal anyway.
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// ---------------------------------------------------------------- config

export function normalizeConfig(config) {
  if (!config.slugRegex) throw new Error('format "heading" needs "slugRegex"');
  const walk = (config.walk ??= {});
  if (!Array.isArray(walk.textSuffixes)) throw new Error('format "heading" needs "walk.textSuffixes"');
  walk.skipDirs ??= [];
  walk.skipDotDirs ??= true;
  walk.extensionlessDirs ??= [];
  const cite = (config.cite ??= {});
  cite.before ??= `(?<![-\\p{L}\\p{N}_])`;
  cite.after ??= `(?![-\\p{L}\\p{N}_])`;
  for (const kind of config.kinds) {
    for (const field of ["id", "prefix", "pendingRegex", "numberedRegex", "idTemplate"]) {
      if (!kind[field]) throw new Error(`kind ${kind.id ?? "(unnamed)"} is missing "${field}"`);
    }
    if (!kind.folder === !kind.file) throw new Error(`kind ${kind.id} needs exactly one of "folder" or "file"`);
    if (kind.folder && !kind.filenameTemplate) throw new Error(`kind ${kind.id} has a folder but no "filenameTemplate"`);
    kind.numbering ??= "max_plus_one";
    if (kind.numbering !== "max_plus_one") {
      throw new Error(`kind ${kind.id}: format "heading" builds "max_plus_one" only (claim-ids.py's own rule)`);
    }
    kind.pad ??= 0;
    kind.filenamePad ??= 0;
    kind.manifestKey ??= "order";
  }
  return config;
}

function padN(n, width) {
  return width > 0 ? String(n).padStart(width, "0") : String(n);
}
function render(template, kind, n, width, rest = "") {
  return template
    .replace(/\{prefix\}/g, kind.prefix)
    .replace(/\{n\}/g, padN(n, width))
    .replace(/\{rest\}/g, rest);
}
const renderId = (kind, n) => render(kind.idTemplate, kind, n, kind.pad);

// ---------------------------------------------------------------- reading a kind

// claim-ids.py `corpus_order`: the manifest's list, then every `*.md` on disk it does not name,
// in plain sorted order. A name the manifest lists that is not on disk is skipped, the way
// `corpus_pieces` skips it.
function corpusOrder(root, kind) {
  const dir = join(root, kind.folder);
  if (!existsSync(dir)) return [];
  const onDisk = readdirSync(dir).filter((n) => n.endsWith(".md") && lstatSync(join(dir, n)).isFile());
  let listed = [];
  const manifest = kind.manifest && join(root, kind.manifest);
  if (manifest && existsSync(manifest)) listed = JSON.parse(readFileSync(manifest, "utf8"))[kind.manifestKey] ?? [];
  const known = new Set(listed);
  const extra = onDisk.filter((n) => !known.has(n)).sort();
  return [...listed, ...extra].filter((n) => existsSync(join(dir, n)));
}

// One heading's token, sorted three ways. claim-ids.py claims every token that is not a clean
// number (its "complement" rule), whatever shape it has. This engine claims only a token of the
// slug grammar and refuses the rest, so a malformed heading stops the run instead of turning
// into an id.
function classify(config, token) {
  if (/^[1-9][0-9]*$/.test(token)) return "numbered";
  if (new RegExp(`^-(?:${config.slugRegex})$`, "u").test(token)) return "pending";
  return "malformed";
}

const titleOf = (line) => line.replace(/^#+\s+\S+\s*[—-]?\s*/u, "").trim();

function readKind(root, config, kind, h) {
  const out = { kind, pending: [], malformed: [], numbers: [], order: [] };
  const numberedRe = new RegExp(kind.numberedRegex, "gmu");
  const take = (text, rel) => {
    for (const m of text.matchAll(numberedRe)) out.numbers.push({ n: Number(m[1]), rel });
  };
  const sort = (line, token, rel, name) => {
    const cls = classify(config, token);
    if (cls === "pending") out.pending.push({ rel, name, slug: kind.prefix + token, title: titleOf(line) });
    else if (cls === "malformed") out.malformed.push({ rel, line });
  };
  if (kind.folder) {
    out.order = corpusOrder(root, kind);
    const pendingRe = new RegExp(kind.pendingRegex, "u");
    for (const name of out.order) {
      const rel = `${kind.folder}/${name}`;
      const { text } = h.readFileEol(join(root, rel));
      take(text, rel);
      const first = text.split("\n", 1)[0];
      const m = pendingRe.exec(first);
      if (m) sort(first, m[1], rel, name);
    }
  } else if (existsSync(join(root, kind.file))) {
    const { text } = h.readFileEol(join(root, kind.file));
    take(text, kind.file);
    const pendingRe = new RegExp(kind.pendingRegex, "gmu");
    for (const m of text.matchAll(pendingRe)) {
      const line = text.slice(m.index).split("\n", 1)[0];
      sort(line, m[1], kind.file, null);
    }
  }
  return out;
}

// claim-ids.py `rename_claimed_entries`: the FIRST name in corpus order that starts with
// `<slug>-` or equals `<slug>.md`, and each rename replaces its name in that order before the
// next claim looks. Replayed here in claim order, so a lookup that lands on another record's file
// is refused before anything is written, where claim-ids.py would rename the wrong file. Keyed
// by the record's own file, never by slug: two records can share a slug, and that state has its
// own refusal.
function planRenames(kind, order, pending) {
  const live = [...order];
  const out = new Map();
  for (const rec of pending) {
    const found = live.find((n) => n.startsWith(rec.slug + "-") || n === rec.slug + ".md");
    out.set(rec.rel, found ?? null);
    if (found) live[live.indexOf(found)] = `\0claimed:${found}`;
  }
  return out;
}

// claim-ids.py's tail rule, kept exactly: the text after `<slug>-` when the file has a longer
// name, else the slug without its `<prefix>-`. A file `D-foo-extra.md` for slug `D-foo` becomes
// `D258-extra.md`, so the slug's own words leave the filename. That is banchi's rule, not a
// choice made here.
function tailOf(kind, slug, name) {
  if (name.startsWith(slug + "-")) return name.slice(slug.length + 1, -3);
  return slug.startsWith(kind.prefix + "-") ? slug.slice(kind.prefix.length + 1) : slug;
}

// ---------------------------------------------------------------- validation, shared by both modes

function validate(root, config, h) {
  const problems = [];
  const kinds = config.kinds.map((kind) => readKind(root, config, kind, h));
  const slugsSeen = new Map();
  for (const k of kinds) {
    const { kind } = k;
    for (const bad of k.malformed) {
      problems.push(`${bad.rel}: malformed pending heading "${bad.line}". A pending id is ${kind.prefix}-<slug>, ` +
        `two or more lowercase segments. Refusing, nothing written.`);
    }
    const byNumber = new Map();
    for (const { n, rel } of k.numbers) byNumber.set(n, [...(byNumber.get(n) ?? []), rel]);
    for (const [n, rels] of byNumber) {
      if (rels.length > 1) problems.push(`duplicate id ${renderId(kind, n)}: ${rels.length} headings carry it (${[...new Set(rels)].join(", ")})`);
    }
    const doubled = new Set();
    for (const rec of k.pending) {
      if (slugsSeen.has(rec.slug)) {
        problems.push(`duplicate pending slug ${rec.slug}: ${slugsSeen.get(rec.slug)} and ${rec.rel}`);
        doubled.add(rec.slug);
      }
      slugsSeen.set(rec.slug, rec.rel);
    }
    if (kind.folder) {
      const renames = planRenames(kind, k.order, k.pending);
      for (const rec of k.pending) {
        // A doubled slug is already refused above. Its filename lookup can only report noise.
        if (doubled.has(rec.slug)) continue;
        const found = renames.get(rec.rel);
        if (found !== rec.name) {
          problems.push(`${rec.rel}: slug ${rec.slug} resolves to ${found ? `${kind.folder}/${found}` : "no file"} by ` +
            `claim-ids.py's filename rule. Name the file ${rec.slug}.md or ${rec.slug}-<tail>.md.`);
        }
      }
      // claim-ids.py `duplicate_pending`: a pending slug whose file main already claimed under
      // a number. Read here off this tree, which at the merge IS main.
      const numberedName = new RegExp("^" + escapeRe(kind.filenameTemplate)
        .replace(escapeRe("{prefix}"), escapeRe(kind.prefix))
        .replace(escapeRe("{n}"), "(\\d+)")
        .replace(escapeRe("{rest}"), "(.+)") + "$", "u");
      const claimedTail = new Map();
      for (const name of k.order) {
        const m = numberedName.exec(name);
        if (m) claimedTail.set(m[2], m[1]);
      }
      for (const rec of k.pending) {
        const text = rec.slug.slice(kind.prefix.length + 1);
        if (claimedTail.has(text)) {
          problems.push(`${rec.rel}: ${rec.slug} is already claimed as ${kind.prefix}${Number(claimedTail.get(text))} in this tree. ` +
            `Drop this pending copy. Do not mint a second number for it.`);
        }
      }
    }
  }
  return { problems, kinds };
}

// ---------------------------------------------------------------- the walk and the substitution

// claim-ids.py `text_files`: every file whose suffix is in TEXT_SUFFIXES, plus an extensionless
// file directly under a named hook directory. Directories named in SKIP, and every directory
// whose name starts with ".", are not entered. A symlink is never walked: the real file is.
function textFiles(root, walk) {
  const out = [];
  const suffixes = new Set(walk.textSuffixes);
  const skip = new Set(walk.skipDirs);
  (function go(abs, rel) {
    for (const name of readdirSync(abs).sort()) {
      const childAbs = join(abs, name);
      const childRel = rel ? `${rel}/${name}` : name;
      let st;
      try { st = lstatSync(childAbs); } catch { continue; }
      if (st.isSymbolicLink()) continue;
      if (st.isDirectory()) {
        if (skip.has(name) || (walk.skipDotDirs && name.startsWith("."))) continue;
        go(childAbs, childRel);
        continue;
      }
      if (!st.isFile()) continue;
      const dot = name.lastIndexOf(".");
      const suffix = dot > 0 ? name.slice(dot) : "";
      if (suffixes.has(suffix)) { out.push(childRel); continue; }
      // `path.parent.as_posix().endswith(HOOK_DIR)`, the same plain suffix test.
      if (!suffix && walk.extensionlessDirs.some((d) => rel.endsWith(d))) out.push(childRel);
    }
  })(root, "");
  return out;
}

function substitute(text, config, claims) {
  // claim-ids.py `rewrite_decision_paths`: a path cite of a pending file becomes the bare id.
  // LONGEST TOKEN FIRST, a deliberate difference. claim-ids.py runs its claims in claim order, so
  // when one pending slug is a prefix of another, the shorter one's `[\w-]*` tail swallows the
  // longer one's path and writes the wrong id (probe 6 in the parity notes). The order changes
  // nothing when no token is a prefix of another.
  const pathClaims = claims.filter((c) => c.kind.pathCite).sort((a, b) => b.token.length - a.token.length);
  for (const c of pathClaims) {
    const re = new RegExp(c.kind.pathCite.replace("{token}", escapeRe(c.token)), "gu");
    text = text.replace(re, () => c.id);
  }
  // claim-ids.py `apply_to_text`: every bounded occurrence of the token, in claim order.
  for (const c of claims) {
    const re = new RegExp(config.cite.before + escapeRe(c.token) + config.cite.after, "gu");
    text = text.replace(re, () => c.id);
  }
  return text;
}

// Python's `json.dumps(obj, indent=2)`, which is how claim-ids.py writes ORDER.json. JSON.stringify
// gives the same bytes except for `ensure_ascii`: Python escapes every character outside
// U+0020 to U+007E, so U+007F (DEL) and everything above it become `\uXXXX`. A character above
// U+FFFF is a surrogate pair in both, so each half is escaped on its own, as Python does.
export function pythonJson(obj) {
  return JSON.stringify(obj, null, 2).replace(/[\u007f-\uffff]/g,
    (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
}

// ---------------------------------------------------------------- --stamp

export function stamp(root, config, h) {
  const { problems, kinds } = validate(root, config, h);
  if (problems.length) return { problems, assigned: [], glossed: 0 };

  const claims = [];
  for (const k of kinds) {
    let n = Math.max(0, ...k.numbers.map((x) => x.n));
    for (const rec of k.pending) {
      n += 1;
      const target = k.kind.folder
        ? `${k.kind.folder}/${render(k.kind.filenameTemplate, k.kind, n, k.kind.filenamePad, tailOf(k.kind, rec.slug, rec.name))}`
        : null;
      claims.push({ kind: k.kind, token: rec.slug, n, id: renderId(k.kind, n), rec, target });
    }
  }
  // A rename never lands on a file that exists. claim-ids.py's `Path.rename` replaces it on
  // POSIX, silently, and fails on Windows. Here the run is refused before anything is written.
  const blocked = claims.filter((c) => c.target && c.target !== c.rec.rel && existsSync(join(root, c.target)));
  if (blocked.length) {
    return {
      problems: blocked.map((c) => `${c.rec.rel}: ${c.token} would be renamed to ${c.target}, which already exists. ` +
        `Refusing, nothing written.`),
      assigned: [], glossed: 0,
    };
  }
  for (const c of claims) console.log(`stamped ${c.id}  ${c.token}  ${c.rec.title}`.trimEnd());
  if (!claims.length) {
    console.log("nothing pending.");
    return { problems: [], assigned: [], glossed: 0 };
  }

  const skip = new Set(config.kinds.filter((k) => k.manifest).map((k) => k.manifest));
  let glossed = 0;
  for (const rel of textFiles(root, config.walk)) {
    if (skip.has(rel)) continue;
    const abs = join(root, rel);
    const { text, eol } = h.readFileEol(abs);
    const next = substitute(text, config, claims);
    if (next !== text) { writeFileSync(abs, h.withEol(next, eol)); glossed += 1; }
  }

  const assigned = [];
  for (const k of kinds) {
    const mine = claims.filter((c) => c.kind === k.kind);
    const renamed = new Map();
    for (const c of mine) {
      let rel = c.rec.rel;
      if (c.target) {
        renameSync(join(root, c.rec.rel), join(root, c.target));
        renamed.set(c.rec.name, c.target.slice(k.kind.folder.length + 1));
        rel = c.target;
      }
      assigned.push({ id: c.id, n: c.n, prefix: k.kind.prefix, slug: c.token, title: c.rec.title, rel, oldRel: c.rec.rel });
    }
    // claim-ids.py renames a listed name IN PLACE and rewrites the manifest whenever it renamed
    // anything. It never appends: index-decisions.py's `normalize` does that, in `regenerate`.
    const manifest = k.kind.manifest && join(root, k.kind.manifest);
    if (renamed.size && manifest && existsSync(manifest)) {
      const { text, eol } = h.readFileEol(manifest);
      const data = JSON.parse(text);
      data[k.kind.manifestKey] = (data[k.kind.manifestKey] ?? []).map((n) => renamed.get(n) ?? n);
      writeFileSync(manifest, h.withEol(pythonJson(data) + "\n", eol));
    }
  }
  console.log(`${assigned.length} entry(ies) stamped; ${glossed} document(s) had a cite rewritten.`);
  return { problems: [], assigned, glossed };
}

// ---------------------------------------------------------------- --check

function git(root, args) {
  try {
    return execFileSync("git", args, { cwd: root, encoding: "utf8", maxBuffer: 256 * 1024 * 1024, stdio: ["ignore", "pipe", "ignore"] });
  } catch {
    return null;
  }
}

function numbersIn(kind, text) {
  return new Set([...text.matchAll(new RegExp(kind.numberedRegex, "gmu"))].map((m) => Number(m[1])));
}

// Off the default branch: a record NUMBERED on the branch is the thing the rule forbids. The
// baseline is the merge base with the default branch, never the default branch's tip (the tip
// may have taken the number since, which reads as "already there" and hides the defect).
function branchNumbered(root, config, kinds, notes) {
  const def = config.defaultBranch;
  const base = [`origin/${def}`, def].map((ref) => git(root, ["merge-base", "HEAD", ref])?.trim()).find(Boolean);
  if (!base) {
    notes.push(`branch question NOT ASKED: no merge base with origin/${def} or ${def}. A clone without that ref cannot say what this branch numbered.`);
    return [];
  }
  const problems = [];
  for (const k of kinds) {
    const kind = k.kind;
    if (kind.folder) {
      const out = git(root, ["-c", "core.quotePath=false", "diff", "--name-only", "--no-renames", "--diff-filter=A", base, "HEAD", "--", kind.folder]);
      if (out === null) { notes.push(`branch question NOT ASKED for ${kind.id}: git diff failed.`); continue; }
      const added = new Set(out.split("\n").map((l) => l.trim()).filter(Boolean));
      const numberedRe = new RegExp(kind.numberedRegex, "u");
      for (const name of k.order) {
        const rel = `${kind.folder}/${name}`;
        if (!added.has(rel)) continue;
        const first = h_first(root, rel);
        const m = numberedRe.exec(first);
        if (m) problems.push(`${rel} is numbered ${renderId(kind, Number(m[1]))} on a branch. Write ${kind.prefix}-<slug> and let the stamp claim it at merge.`);
      }
    } else {
      const was = git(root, ["show", `${base}:${kind.file}`]) ?? "";
      const before = numbersIn(kind, was);
      for (const { n } of k.numbers) {
        if (!before.has(n)) problems.push(`${kind.file}: ${renderId(kind, n)} is numbered on a branch. Write ${kind.prefix}-<slug> and let the stamp claim it at merge.`);
      }
    }
  }
  return [...new Set(problems)];
}
const h_first = (root, rel) => readFileSync(join(root, rel), "utf8").replace(/\r\n/g, "\n").split("\n", 1)[0];

// On the default branch: a pending record HEAD did not itself add means the stamp did not run,
// or its push was rejected (claim-ids.py `--landed` asks the same of a landed commit).
function defaultPendingOld(root, kinds, h, notes) {
  const problems = [];
  for (const k of kinds) {
    if (!k.pending.length) continue;
    const kind = k.kind;
    if (kind.folder) {
      const added = h.addedByHead(root, kind.folder);
      if (!added) { notes.push(`branch question NOT ASKED for ${kind.id}: git could not read HEAD.`); continue; }
      for (const rec of k.pending) {
        if (!added.has(rec.rel)) problems.push(`${rec.rel} is still pending on the default branch, added before HEAD. The stamp did not run, or its push was rejected.`);
      }
    } else {
      if (git(root, ["rev-parse", "--verify", "--quiet", "HEAD"]) === null) {
        notes.push(`branch question NOT ASKED for ${kind.id}: git could not read HEAD.`);
        continue;
      }
      const parent = git(root, ["show", `HEAD^1:${kind.file}`]) ?? "";
      const pendingRe = new RegExp(kind.pendingRegex, "gmu");
      const older = new Set([...parent.matchAll(pendingRe)].map((m) => kind.prefix + m[1]));
      for (const rec of k.pending) {
        if (older.has(rec.slug)) problems.push(`${kind.file}: ${rec.slug} is still pending on the default branch, added before HEAD. The stamp did not run, or its push was rejected.`);
      }
    }
  }
  return problems;
}

export function check(root, config, h) {
  const { problems, kinds } = validate(root, config, h);
  if (!config.defaultBranch) return problems;
  const notes = [];
  const onDefault = h.currentBranch(root) === config.defaultBranch;
  problems.push(...(onDefault ? defaultPendingOld(root, kinds, h, notes) : branchNumbered(root, config, kinds, notes)));
  for (const n of notes) console.error(`stamp --check: ${n}`);
  return problems;
}

// Format 3 for stamp.mjs: the number lives in a markdown HEADING, and for a split corpus also in
// the FILENAME. The config states every grammar. This module names no repo.
//
// Two corpus shapes, one per kind:
//   folder  one file per record, the record's heading on the file's FIRST line, the number in the
//           heading AND the filename (`D-<slug>.md` holding `## D-<slug> — Title` becomes
//           `D258-<slug>.md` holding `## D258 — Title`).
//   file    one flat file, every heading line is a record (`## C-<slug> — Title` becomes
//           `## C12 — Title`). No rename.
//
// A claim is max + 1 over every numbered heading the kind holds, never a gap. Then every bounded
// occurrence of the slug token in every walked text file becomes the id. A repo's own generators
// (a manifest append, an index) are NOT here. They run as the action's `regenerate` command.
//
// stamp.mjs dispatches here when config.format is "heading". Its own helpers come in as `h`, so
// this module shares one EOL rule and one git reader with the other two formats. The branch
// question off the default branch lives in stamp.mjs, for all three formats. This module gives
// it `numberedRecords`.

import { readFileSync, writeFileSync, renameSync, readdirSync, lstatSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join } from "node:path";

// Python's `\w` in a str pattern is Unicode: a letter, a number, or `_`, by category. JS `\w` is
// ASCII only. A boundary written for a Python tool, `(?<![-\w])...(?![-\w])`, must mean the same
// thing here.
export const PY_WORD = "[\\p{L}\\p{N}_]";

// Every pattern here carries the `u` flag (for `\p{L}`), and `u` refuses an escaped `-` outside a
// class, so `-` stays bare. Outside a class it is a literal anyway.
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// ---------------------------------------------------------------- config

// Names captured by every `(?<name>...)` GROUP in a regex source string, never a lookbehind
// (`(?<=` or `(?<!`): the character class right after `<` excludes both `=` and `!` already, by
// construction, so this needs no separate lookbehind exclusion.
function namedGroups(source) {
  return [...source.matchAll(/\(\?<([A-Za-z_$][\w$]*)>/g)].map((m) => m[1]);
}

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
  cite.glossFirstUse ??= [];
  if (!Array.isArray(cite.glossFirstUse) || cite.glossFirstUse.some((g) => typeof g !== "string")) {
    throw new Error("config.cite.glossFirstUse must be an array of glob strings");
  }
  // A bad `unclaimed` entry is a config error, caught here, before any tree is read — never a
  // TypeError mid-walk from a pattern with no "slug" group, and never a run that silently walks
  // right past an unparseable pattern.
  for (const spec of config.unclaimed ?? []) {
    for (const field of ["folder", "pattern", "message"]) {
      if (!spec[field]) throw new Error(`config.unclaimed entry is missing "${field}"`);
    }
    try {
      new RegExp(spec.pattern, "gmu");
    } catch (e) {
      throw new Error(`config.unclaimed entry's "pattern" is not a valid regex: ${e.message}`);
    }
    if (!namedGroups(spec.pattern).includes("slug")) {
      throw new Error(`config.unclaimed entry's "pattern" needs a named group "(?<slug>...)"`);
    }
  }
  for (const kind of config.kinds) {
    for (const field of ["id", "prefix", "pendingRegex", "numberedRegex", "idTemplate"]) {
      if (!kind[field]) throw new Error(`kind ${kind.id ?? "(unnamed)"} is missing "${field}"`);
    }
    if (!kind.folder === !kind.file) throw new Error(`kind ${kind.id} needs exactly one of "folder" or "file"`);
    if (kind.folder && !kind.filenameTemplate) throw new Error(`kind ${kind.id} has a folder but no "filenameTemplate"`);
    kind.numbering ??= "max_plus_one";
    if (kind.numbering !== "max_plus_one") {
      throw new Error(`kind ${kind.id}: format "heading" builds "max_plus_one" only`);
    }
    kind.pad ??= 0;
    kind.filenamePad ??= 0;
    kind.manifestKey ??= "order";
    kind.manifestAscii ??= true;
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

// Corpus order: the manifest's list, then every `*.md` on disk it does not name, in plain sorted
// order. A name the manifest lists that is not on disk is skipped.
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

// One heading's token, sorted three ways. This engine claims only a token of the slug grammar and
// refuses the rest, so a malformed heading stops the run instead of turning into an id.
function classify(config, token) {
  if (/^[1-9][0-9]*$/.test(token)) return "numbered";
  if (new RegExp(`^-(?:${config.slugRegex})$`, "u").test(token)) return "pending";
  return "malformed";
}

// The gloss a claim writes after a cite: the first six words of the record's heading title, with
// parentheses and backticks dropped. Empty when the heading has no dash and title.
function glossOf(line, token) {
  const m = new RegExp(`^#+\\s+${escapeRe(token)}\\s+[\u2014-]\\s*(.+)`, "u").exec(line);
  return m ? m[1].replace(/[()`]/g, "").split(/\s+/).filter(Boolean).slice(0, 6).join(" ") : "";
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
    if (cls === "pending") out.pending.push({ rel, name, slug: kind.prefix + token, title: titleOf(line), gloss: kind.folder ? glossOf(line, kind.prefix + token) : "" });
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

// The filename rule: the FIRST name in corpus order that starts with `<slug>-` or equals
// `<slug>.md`, and each rename replaces its name in that order before the next claim looks.
// Replayed here in claim order, so a lookup that lands on another record's file is refused before
// anything is written, instead of a rename of the wrong file. Keyed
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

// The tail rule: the text after `<slug>-` when the file has a longer name, else the slug without
// its `<prefix>-`. A file `D-foo-extra.md` for slug `D-foo` becomes `D258-extra.md`, so the
// slug's own words leave the filename. A repo that wants to keep them names its files
// `<slug>.md`.
function tailOf(kind, slug, name) {
  if (name.startsWith(slug + "-")) return name.slice(slug.length + 1, -3);
  return slug.startsWith(kind.prefix + "-") ? slug.slice(kind.prefix.length + 1) : slug;
}

// ---------------------------------------------------------------- unclaimed markers
//
// A marker this engine does not number at all, because the repo has no rule for it yet.
// config.unclaimed:
// [{ folder, pattern, message, label }]. `pattern` runs with the "gmu" flags over each ".md"
// file directly in `folder`, and must carry a named group `slug` (normalizeConfig refuses a
// pattern without one, before any tree is read). The problem names the matched line, trimmed,
// unless `label` is set, in which case it names `<label> <slug>` instead (with `label: "step"`
// the refusal reads "step add-widget", not the raw matched line).
// Nothing here is numbered, renamed, or rewritten — only refused, in both `--check` and
// `--stamp`, before either writes anything. Absent config.unclaimed, this is a no-op, same as
// before it existed.
function unclaimedProblems(root, config) {
  const problems = [];
  for (const spec of config.unclaimed ?? []) {
    const dir = join(root, spec.folder);
    if (!existsSync(dir)) continue;
    const re = new RegExp(spec.pattern, "gmu");
    for (const name of readdirSync(dir).sort()) {
      if (!name.endsWith(".md") || !lstatSync(join(dir, name)).isFile()) continue;
      const text = readFileSync(join(dir, name), "utf8");
      for (const m of text.matchAll(re)) {
        const detail = spec.label ? `${spec.label} ${m.groups.slug}` : m[0].trim();
        problems.push(`${spec.folder}/${name}: ${detail}. ${spec.message}`);
      }
    }
  }
  return problems;
}

// ---------------------------------------------------------------- validation, shared by both modes

function validate(root, config, h) {
  const problems = [...unclaimedProblems(root, config)];
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
            `the filename rule. Name the file ${rec.slug}.md or ${rec.slug}-<tail>.md.`);
        }
      }
      // A pending slug whose file this tree already holds under a number. Read off this tree,
      // which at the merge IS the default branch.
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

// The walk: every file whose suffix is in `walk.textSuffixes`, plus an extensionless file
// directly under a directory named in `walk.extensionlessDirs`. Directories named in `walk.skipDirs`, and every directory
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
      // A plain suffix test on the parent's posix path.
      if (!suffix && walk.extensionlessDirs.some((d) => rel.endsWith(d))) out.push(childRel);
    }
  })(root, "");
  return out;
}

function substitute(text, config, claims) {
  // A path cite of a pending file becomes the bare id. LONGEST TOKEN FIRST: when one pending slug
  // is a prefix of another, a claim-order pass lets the shorter one's `[\w-]*` tail swallow the
  // longer one's path and write the wrong id. The order changes nothing when no token is a
  // prefix of another.
  const pathClaims = claims.filter((c) => c.kind.pathCite).sort((a, b) => b.token.length - a.token.length);
  for (const c of pathClaims) {
    const re = new RegExp(c.kind.pathCite.replace("{token}", escapeRe(c.token)), "gu");
    text = text.replace(re, () => c.id);
  }
  // Every bounded occurrence of the token, in claim order.
  for (const c of claims) {
    const re = new RegExp(config.cite.before + escapeRe(c.token) + config.cite.after, "gu");
    text = text.replace(re, () => c.id);
  }
  return text;
}

// At a claimed cite's first use in a paragraph, add ` (gloss)`. A paragraph ends at a blank line
// and starts at a bullet. A cite already followed by ` (` or `, word` is left alone, so a gloss
// is never doubled. Only the first match of a cite on a line is looked at. Heading lines are
// skipped. Only a `folder` kind carries a gloss: a flat-file record has no entry file.
function glossFirstUses(text, claims) {
  let seen = new Set();
  const lines = text.split("\n").map((line) => {
    if (!line.trim() || /^\s*[-*] /.test(line)) seen = new Set();
    if (line.startsWith("#")) return line;
    for (const c of claims) {
      if (!c.rec.gloss) continue;
      const re = new RegExp(`(?<![-\\p{L}\\p{N}_])${escapeRe(c.id)}(\`?)(?![-\\p{L}\\p{N}_])`, "u");
      line = line.replace(re, (all, tick, offset, whole) => {
        if (seen.has(c.id)) return all;
        seen.add(c.id);
        if (/^`?( \(|,\s+[\p{L}\p{N}_])/u.test(whole.slice(offset + all.length))) return all;
        return `${c.id}${tick} (${c.rec.gloss})`;
      });
    }
    return line;
  });
  return lines.join("\n");
}

// Python's `json.dumps(obj, indent=2)`, the byte shape a Python generator writes a manifest in.
// `kind.manifestAscii` (default true) picks it. JSON.stringify gives the same bytes except for
// `ensure_ascii`: Python escapes every character outside
// U+0020 to U+007E, so U+007F (DEL) and everything above it become `\uXXXX`. A character above
// U+FFFF is a surrogate pair in both, so each half is escaped on its own, as Python does.
export function pythonJson(obj) {
  return JSON.stringify(obj, null, 2).replace(/[\u007f-\uffff]/g,
    (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
}

// ---------------------------------------------------------------- --stamp

export function stamp(root, config, h, extra) {
  const { problems, kinds } = validate(root, config, h);
  if (problems.length) return { problems, assigned: [], glossed: 0 };

  const claims = [];
  for (const k of kinds) {
    let n = Math.max(0, ...k.numbers.map((x) => x.n), ...(extra?.get(k.kind.id) ?? []));
    for (const rec of k.pending) {
      n += 1;
      const target = k.kind.folder
        ? `${k.kind.folder}/${render(k.kind.filenameTemplate, k.kind, n, k.kind.filenamePad, tailOf(k.kind, rec.slug, rec.name))}`
        : null;
      claims.push({ kind: k.kind, token: rec.slug, n, id: renderId(k.kind, n), rec, target });
    }
  }
  // A rename never lands on a file that exists. A plain rename replaces it on POSIX, silently, and
  // fails on Windows. Here the run is refused before anything is written.
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
  const glossMatch = h.makeMatcher(config.cite.glossFirstUse);
  for (const rel of textFiles(root, config.walk)) {
    if (skip.has(rel)) continue;
    const abs = join(root, rel);
    const { text, eol } = h.readFileEol(abs);
    let next = substitute(text, config, claims);
    if (glossMatch(rel)) next = glossFirstUses(next, claims);
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
    // A listed name is renamed IN PLACE, and the manifest is rewritten whenever a rename ran.
    // Nothing is appended here. A repo's own generator does that, in `regenerate`.
    const manifest = k.kind.manifest && join(root, k.kind.manifest);
    if (renamed.size && manifest && existsSync(manifest)) {
      const { text, eol } = h.readFileEol(manifest);
      const data = JSON.parse(text);
      data[k.kind.manifestKey] = (data[k.kind.manifestKey] ?? []).map((n) => renamed.get(n) ?? n);
      const json = k.kind.manifestAscii ? pythonJson(data) : JSON.stringify(data, null, 2);
      writeFileSync(manifest, h.withEol(json + "\n", eol));
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

// Every numbered record in this tree, keyed for stamp.mjs's branch question. A folder kind keys
// a number by its file, since a file keeps its name once numbered. A flat-file kind has no stable
// per-record key but the number itself, so it keys by the kind and the number. a deleted record
// keeps its number taken through the history read in stamp.mjs.
export function numberedRecords(root, config, h) {
  const out = [];
  for (const kind of config.kinds) {
    const k = readKind(root, config, kind, h);
    for (const { n, rel } of k.numbers) {
      const key = kind.folder ? `${kind.id}\0${rel}\0${n}` : `${kind.id}\0${n}`;
      out.push({ key, name: kind.folder ? rel : renderId(kind, n), kind: kind.id, n, rel, id: renderId(kind, n), prefix: kind.prefix });
    }
  }
  return out;
}

// The numbers one historical file holds, for stamp.mjs's highest-ever read: the kind's own
// numbered headings, and for a folder kind the number in the filename. [] when `rel` is not a
// record file of `kind`.
export function numbersOfFile(kind, rel, text) {
  const own = kind.folder ? rel.startsWith(kind.folder + "/") && !rel.slice(kind.folder.length + 1).includes("/") && rel.endsWith(".md") : rel === kind.file;
  if (!own) return [];
  const out = [...text.replace(/\r\n/g, "\n").matchAll(new RegExp(kind.numberedRegex, "gmu"))].map((m) => Number(m[1]));
  if (kind.folder) {
    const re = new RegExp("^" + escapeRe(kind.filenameTemplate).replace(escapeRe("{prefix}"), escapeRe(kind.prefix)).replace(escapeRe("{n}"), "(\\d+)").replace(escapeRe("{rest}"), "(?:.+)") + "$", "u");
    const m = re.exec(rel.slice(kind.folder.length + 1));
    if (m) out.push(Number(m[1]));
  }
  return out;
}

// The paths a base-tree read must hold for readKind to run on it.
export function recordPaths(config) {
  return config.kinds.flatMap((kind) => [kind.folder, kind.file, kind.manifest].filter(Boolean));
}

// On the default branch: any pending record means a record reached the branch unclaimed. The
// claim runs before the merge, so none is expected here, HEAD's own included.
function defaultPending(kinds) {
  const problems = [];
  for (const k of kinds) {
    for (const rec of k.pending) {
      const where = k.kind.folder ? rec.rel : k.kind.file;
      problems.push(`${where}: ${rec.slug} is still pending on the default branch. Claim the number before the merge. Run the merge tool on a pull request that carries it.`);
    }
  }
  return problems;
}

// Structural refusals always. The default-branch question only when stamp.mjs says HEAD is on
// the default branch. The off-branch question is stamp.mjs's own, shared by every format.
export function check(root, config, h, onDefault) {
  const { problems, kinds } = validate(root, config, h);
  if (!onDefault) return problems;
  problems.push(...defaultPending(kinds));
  return problems;
}

// The show command: prints one part of `docs/map/` as short plain text.
// Use: node <skill>/scripts/map-show.mjs <path|area|folder/|decision-id> [--full], run from the root of a repository that has `map.config.json`.
//   a file path  prints its area, its map line, its fact lines, its tested-by line, its Homes lines and its trace steps.
//                A non-code file prints its map line, then its `Decisions:` ids and its `Debts:` slugs, only when a record names the file.
//                A test path also prints `Named as a test of:` and the files whose tested-by line names it. A test with no map line prints that alone.
//   an area id   prints each map line of that area as `path — sentence`.
//   a folder     (ends with `/`) prints each map line whose path starts with it.
//   a decision id  (the config sets `decisionsDir` and `decisionIdPattern`, and the arg wholly matches the pattern) prints each map line
//                whose decisions line cites it, as `path — sentence`. A non-code file is listed only when a record names it. Ids compare by `idKey`, so D7 and D007 are one id.
//                `--full` after the id first prints one line for each record the id names, as `<heading> — <record path>`.
//                A record that no map line cites: `no map line cites <id>` on stderr, exit 1.
//                An id that names no record: one plain stderr line that names the id and the decisions folder, exit 1.
//                `--full` with any other arg is ignored.
// A code map line is a list line whose path the config's `codeExtensions` accepts, as MAP1 reads it. A Tables row is none.
// Every non-code map line is parsed, and only a file that a record names (`namedNonCode`) prints. A non-code file that no record names is out of scope.
// A path may be absolute: under the repository root it is read as its relative form.
// Nothing found: `no map line for <arg>` on stderr, exit 1. No arg: a usage line, exit 2.
// A map the skill cannot read (a bad config, or a page that is tracked and not on disk): one plain stderr line, exit 3.
import { readFileSync, realpathSync } from 'node:fs';
import path from 'node:path';
import { extRe, factLines, gitLsFiles, homeLines, mapFilePaths, mapLines, namedNonCode, subLineEntries, TRACE_PAGE_RE, traceStepItems } from './map-check.mjs';
import { repoMapConfig } from './lib/map-config.mjs';
import { idKey, recordFiles } from './lib/decisions.mjs';

const fail = (msg, code) => { console.error(msg); process.exit(code); };

const full = process.argv.slice(2).includes('--full');
const arg = process.argv.slice(2).find((a) => a !== '--full');
if (!arg) fail('usage: map-show.mjs <path|area|folder/|decision-id> [--full]', 2);

const root = process.cwd();
const read = (f) => {
  try { return readFileSync(path.join(root, f), 'utf8'); } catch (e) { throw new Error(`cannot read ${f}: ${e.code ?? e.message}`); }
};
let cfg, re, areas, traces;
try {
  cfg = repoMapConfig();
  re = extRe(cfg);
  const files = gitLsFiles(root);
  // One entry per area page, in the order git lists them.
  areas = mapFilePaths(files).map((f) => {
    const text = read(f);
    const cites = subLineEntries(text, re).entries;
    return { id: path.posix.basename(f, '.md'), text, lines: mapLines(text, re), cites, others: cites.filter((e) => !e.code) };
  });
  traces = files.flatMap((f) => {
    const m = f.match(TRACE_PAGE_RE);
    return m ? [{ key: m[1], steps: traceStepItems(read(f)) }] : [];
  });
} catch (e) {
  fail(e.message.replace(/\s*\n\s*/g, ' '), 3);
}

// The real form of a path that may not exist: the real form of its longest existing prefix, plus the rest.
// Two spellings of one folder differ on Windows (an 8.3 short name or the drive-letter case) and anywhere a symlink
// is on the path. `path.relative` compares text only, so it needs both sides in their real form.
const realPath = (p) => {
  const rest = [];
  for (let cur = p; ; cur = path.dirname(cur)) {
    try { return path.join(realpathSync.native(cur), ...rest.reverse()); } catch {
      if (path.dirname(cur) === cur) return p;
      rest.push(path.basename(cur));
    }
  }
};
// An absolute path under the root is its relative form. One outside the root stays absolute, and no map line names it.
// `path.relative` drops a trailing separator, and a folder arg needs it, so it is put back.
const relOf = (a) => {
  const r = path.relative(realPath(root), realPath(a));
  return r && /[\\/]$/.test(a) ? `${r}/` : r;
};
const rel = path.isAbsolute(arg) ? relOf(arg) : arg;
// Backslashes and a leading `./` name the same path: Windows and shell completion type them.
const want = path.posix.normalize(rel.replace(/\\/g, '/'));
const row = (l) => `${l.path} — ${l.sentence}`;

// Whether a record names this non-code file. The set of named files is read once, on first use.
let namedFiles;
const isNamed = (f) => {
  try { return (namedFiles ??= namedNonCode({ cfg, root, read, all: gitLsFiles(root) })).has(f); } catch (e) { return fail(e.message.replace(/\s*\n\s*/g, ' '), 3); }
};

const out = [];
if (cfg.decisionsDir && new RegExp(`^(?:${cfg.decisionIdPattern})$`).test(arg)) {
  let records;
  try { records = recordFiles(root, cfg.decisionsDir, arg); } catch (e) { fail(`cannot read ${cfg.decisionsDir}: ${e.code ?? e.message}`, 3); }
  if (!records.length) fail(`no record names ${arg} in ${cfg.decisionsDir}`, 1);
  if (full) {
    for (const f of records) {
      let heading;
      try { heading = read(f).match(/^#[ \t]+(.+?)\s*$/m)?.[1] ?? path.posix.basename(f, '.md'); } catch (e) { fail(e.message, 3); }
      out.push(`${heading} — ${f}`);
    }
  }
  const key = idKey(arg);
  const cites = [];
  for (const a of areas) {
    const files = new Set(a.cites.filter((e) => e.ids.some((id) => idKey(id) === key)).map((e) => e.file));
    for (const l of a.lines) if (files.has(l.path)) cites.push(row(l));
    // A non-code file that a record names, and whose decisions line holds the id.
    for (const e of a.others) if (e.ids.some((id) => idKey(id) === key) && isNamed(e.file)) cites.push(row({ path: e.file, sentence: e.sentence }));
  }
  if (!cites.length) fail(`no map line cites ${arg}`, 1);
  out.push(...cites);
} else if (want.endsWith('/')) {
  for (const a of areas) for (const l of a.lines) if (l.path.startsWith(want)) out.push(row(l));
} else {
  const entries = areas.flatMap((a) => a.cites);
  const tests = [...new Set(entries.filter((e) => e.file === want).flatMap((e) => e.tests))];
  // A test path: the files whose tested-by line names it.
  const named = [...new Set(entries.filter((e) => e.tests.includes(want)).map((e) => e.file))];
  const namedLines = named.length ? ['Named as a test of:', ...named.map((f) => `  ${f}`)] : [];
  for (const a of areas) {
    for (const l of a.lines) {
      if (l.path !== want) continue;
      out.push(`${want} — area ${a.id}`, l.sentence);
      const facts = factLines(a.text).filter((f) => f.parent === want);
      if (facts.length) out.push('Facts:', ...facts.map((f) => `  ${f.prose}`));
      if (tests.length) out.push('Tested by:', ...tests.map((t) => `  ${t}`));
      out.push(...namedLines);
      const homes = areas.flatMap((h) => homeLines(h.text)).filter((h) => h.file === want);
      if (homes.length) out.push('Homes:', ...homes.map((h) => `  ${h.capability} — ${h.file}${h.symbol ? `:${h.symbol}` : ''}`));
      const steps = traces.flatMap((t) => t.steps.filter((s) => s.path === want).map((s) => `  ${t.key} / ${s.heading}: ${s.text}`));
      if (steps.length) out.push('Trace:', ...steps);
    }
  }
  // A non-code file that a record names: its map line, then its decisions line and debts line.
  for (const a of areas) {
    for (const e of a.others) {
      if (e.file !== want || !isNamed(e.file)) continue;
      out.push(`${want} — area ${a.id}`, e.sentence);
      if (e.ids.length) out.push(`Decisions: ${e.ids.join(', ')}`);
      if (e.slugs.length) out.push(`Debts: ${e.slugs.join(', ')}`);
    }
  }
  // A test that has no map line of its own still prints the files that name it.
  if (!out.length) out.push(...namedLines);
  if (!out.length) for (const a of areas) if (a.id === want) out.push(...a.lines.map(row));
}

if (!out.length) fail(`no map line for ${arg}`, 1);
console.log(out.join('\n'));

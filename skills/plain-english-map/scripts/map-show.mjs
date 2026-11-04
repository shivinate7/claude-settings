// The show command: prints one part of `docs/map/` as short plain text.
// Use: node <skill>/scripts/map-show.mjs <path|area|folder/>, run from the root of a repository that has `map.config.json`.
//   a file path  prints its area, its map line, its fact lines, its Homes lines and its trace steps.
//   an area id   prints each map line of that area as `path — sentence`.
//   a folder     (ends with `/`) prints each map line whose path starts with it.
// A map line is a list line whose path the config's `codeExtensions` accepts, as MAP1 reads it. A Tables row is none.
// A path may be absolute: under the repository root it is read as its relative form.
// Nothing found: `no map line for <arg>` on stderr, exit 1. No arg: a usage line, exit 2.
// A map the skill cannot read (a bad config, or a page that is tracked and not on disk): one plain stderr line, exit 3.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { extRe, factLines, gitLsFiles, homeLines, mapFilePaths, mapLines, TRACE_PAGE_RE, traceStepItems } from './map-check.mjs';
import { repoMapConfig } from './lib/map-config.mjs';

const fail = (msg, code) => { console.error(msg); process.exit(code); };

const arg = process.argv[2];
if (!arg) fail('usage: map-show.mjs <path|area|folder/>', 2);

const root = process.cwd();
let areas, traces;
try {
  const re = extRe(repoMapConfig());
  const files = gitLsFiles(root);
  const read = (f) => {
    try { return readFileSync(path.join(root, f), 'utf8'); } catch (e) { throw new Error(`cannot read ${f}: ${e.code ?? e.message}`); }
  };
  // One entry per area page, in the order git lists them.
  areas = mapFilePaths(files).map((f) => {
    const text = read(f);
    return { id: path.posix.basename(f, '.md'), text, lines: mapLines(text, re) };
  });
  traces = files.flatMap((f) => {
    const m = f.match(TRACE_PAGE_RE);
    return m ? [{ key: m[1], steps: traceStepItems(read(f)) }] : [];
  });
} catch (e) {
  fail(e.message.replace(/\s*\n\s*/g, ' '), 3);
}

// An absolute path under the root is its relative form. One outside the root stays absolute, and no map line names it.
const rel = path.isAbsolute(arg) ? path.relative(root, arg) : arg;
// Backslashes and a leading `./` name the same path: Windows and shell completion type them.
const want = path.posix.normalize(rel.replace(/\\/g, '/'));
const row = (l) => `${l.path} — ${l.sentence}`;

const out = [];
if (want.endsWith('/')) {
  for (const a of areas) for (const l of a.lines) if (l.path.startsWith(want)) out.push(row(l));
} else {
  for (const a of areas) {
    for (const l of a.lines) {
      if (l.path !== want) continue;
      out.push(`${want} — area ${a.id}`, l.sentence);
      const facts = factLines(a.text).filter((f) => f.parent === want);
      if (facts.length) out.push('Facts:', ...facts.map((f) => `  ${f.prose}`));
      const homes = areas.flatMap((h) => homeLines(h.text)).filter((h) => h.file === want);
      if (homes.length) out.push('Homes:', ...homes.map((h) => `  ${h.capability} — ${h.file}${h.symbol ? `:${h.symbol}` : ''}`));
      const steps = traces.flatMap((t) => t.steps.filter((s) => s.path === want).map((s) => `  ${t.key} / ${s.heading}: ${s.text}`));
      if (steps.length) out.push('Trace:', ...steps);
    }
  }
  if (!out.length) for (const a of areas) if (a.id === want) out.push(...a.lines.map(row));
}

if (!out.length) fail(`no map line for ${arg}`, 1);
console.log(out.join('\n'));

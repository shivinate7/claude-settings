// Lists the map lines whose cited file changed after the line was written. It is advisory: it always exits 0.
//
// Run `node <skill>/scripts/map-stale.mjs` from a repository root.
// A map line's date is the newest `git blame` author time of the line and of its indented fact lines.
// A file's date is the author time of its last commit. A line is listed when its file is more than one day newer. Worst gap first.
// The dates are UTC. A shallow clone, no repository or no git prints an unknown line that says why, and never "nothing stale".
//
// Cost: one `git rev-parse --is-shallow-repository`, one `git blame --line-porcelain` per map page, and one `git log` pass for all files.
import { execFileSync } from 'node:child_process';
import { readdirSync, readFileSync, realpathSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { extRe, factLines, mapCodeLines } from './map-check.mjs';
import { loadMapConfig } from './lib/map-config.mjs';

const DAY = 86400;
const iso = (epoch) => new Date(epoch * 1000).toISOString().slice(0, 10);

const git = (root, args) =>
  execFileSync('git', ['-c', 'core.quotepath=false', ...args], { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 1024 * 1024 * 1024, windowsHide: true });

/** The author time of each line of `page`, by 1-based line number, from one `git blame --line-porcelain`. */
const lineTimes = (root, page) => {
  const when = new Map();
  let number = 0, stamp = null;
  for (const l of git(root, ['blame', '--line-porcelain', '--', page]).split('\n')) {
    if (/^[0-9a-f]{40} \d+ \d+/.test(l)) number = Number(l.split(' ')[2]);
    else if (l.startsWith('author-time ')) stamp = Number(l.split(' ')[1]);
    else if (l.startsWith('\t') && stamp !== null) when.set(number, stamp);
  }
  return when;
};

/** The newest author time of each file, from one `git log` pass over all history. Paths are relative to `root`. */
const fileTimes = (root) => {
  const when = new Map();
  let at = 0;
  for (const l of git(root, ['log', '--relative', '--format=%at', '--name-only']).split('\n')) {
    if (/^\d+$/.test(l)) at = Number(l);
    else if (l && at > (when.get(l) ?? 0)) when.set(l, at);
  }
  return when;
};

const reason = (e) => (e.code === 'ENOENT' ? 'git is not on PATH' : String(e.stderr ?? e.message).trim().split('\n')[0]);

/** The lines to print for the repository at `root`. */
export const staleReport = (root) => {
  let cfg;
  try { cfg = loadMapConfig(path.join(root, 'map.config.json'), root, { git: false }); } catch (e) { return [`unknown: ${e.message}`]; }
  let pages;
  try {
    pages = readdirSync(path.join(root, 'docs', 'map'), { withFileTypes: true }).filter((d) => d.isFile() && d.name.endsWith('.md')).map((d) => d.name).sort();
  } catch { pages = []; }
  if (!pages.length) return ['unknown: docs/map/ holds no map page'];

  try {
    if (git(root, ['rev-parse', '--is-shallow-repository']).trim() === 'true') return ['unknown: this clone is shallow, so git does not hold the history that the dates need'];
  } catch (e) {
    return [`unknown: git cannot read a repository here (${reason(e)})`];
  }

  const re = extRe(cfg);
  const unread = [];
  const found = [];
  for (const name of pages) {
    const page = `docs/map/${name}`;
    let when;
    try { when = lineTimes(root, page); } catch (e) { unread.push(`${page} (${reason(e)})`); continue; }
    const text = readFileSync(path.join(root, page), 'utf8');
    const maps = mapCodeLines(text, re);
    const facts = factLines(text);
    for (const m of maps) {
      // A fact line belongs to the last map line above it that names its parent.
      const own = facts.filter((f) => f.parent === m.path && maps.filter((o) => o.path === m.path && o.line < f.line).at(-1) === m);
      const at = Math.max(...[m.line, ...own.map((f) => f.line)].map((n) => when.get(n) ?? 0));
      found.push({ page, path: m.path, line: m.line, at });
    }
  }

  let files;
  try { files = fileTimes(root); } catch (e) { return [`unknown: git log failed (${reason(e)})`]; }
  const rows = found
    .filter((l) => l.at > 0 && files.has(l.path) && files.get(l.path) - l.at > DAY)
    .map((l) => ({ ...l, file: files.get(l.path), gap: Math.floor((files.get(l.path) - l.at) / DAY) }))
    .sort((a, b) => b.file - b.at - (a.file - a.at) || a.path.localeCompare(b.path));

  const out = [];
  if (rows.length) {
    out.push(`${rows.length} map line${rows.length === 1 ? '' : 's'} whose file changed after the line, worst gap first:`);
    for (const r of rows) out.push(`${r.path}  line ${iso(r.at)}  file ${iso(r.file)}  gap ${r.gap} days  (${r.page}:${r.line})`);
  } else if (!unread.length) out.push('nothing stale');
  else out.push('no stale line in the pages that git could read');
  if (unread.length) out.push(`unknown: git could not blame ${unread.join(', ')}`);
  return out;
};

// `realpathSync` on both sides: a run through a junction or symlink to the skill folder must still match.
const isMain = () => {
  try { return !!process.argv[1] && realpathSync(fileURLToPath(import.meta.url)) === realpathSync(path.resolve(process.argv[1])); } catch (e) { if (e.code === 'ENOENT') return false; throw e; }
};
if (isMain()) console.log(staleReport(process.cwd()).join('\n'));

// The one home of the decision-id rules: which record an id names, and which ids a file's comments cite.
// MAP10 (`map-check.mjs`) and `map-fix.mjs` both read them here, so the two never disagree.
// It also holds which files a record names (`recordNaming`): a decision record in `decisionsDir`, or a debt record in the debts folder of lint/layout.json.
// A LEAF: it imports only node builtins and `source-text.mjs`. The map lines are parsed in `map-check.mjs`.
import { existsSync, readdirSync, readFileSync, realpathSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { commentsOf } from './source-text.mjs';

/** An id in the form that compares: each run of digits by value, so `D7` and `D007` are one key. */
export const idKey = (id) => id.replace(/\d+/g, (d) => d.replace(/^0+(?=\d)/, ''));

// A folder of records holds files that are no record: its index and its notes. Every reader of a record file here skips them.
const NOT_RECORDS = new Set(['notes.md', 'README.md']);
const isRecordFile = (e) => e.isFile() && e.name.endsWith('.md') && !NOT_RECORDS.has(e.name);

/** The keys of the records in `decisionsDir`: each `.md` file directly in the folder, except notes.md and README.md, by its name without `.md`. A sub-folder holds none. */
export const recordKeys = (root, decisionsDir) =>
  readdirSync(path.join(root, decisionsDir), { withFileTypes: true })
    .filter(isRecordFile)
    .map((e) => idKey(e.name.slice(0, -3)));

// A record's key is the id's key, or starts with the id's key and a `-`.
const keyNames = (k, record) => record === k || record.startsWith(`${k}-`);

/** True when an id names a record: the record's name is the id, or starts with the id and a `-`. `keys` is from `recordKeys`. */
export const namesRecord = (id, keys) => {
  const k = idKey(id);
  return keys.some((r) => keyNames(k, r));
};

/** The record files that an id names, each as its path from the repository root, in folder order. `decisionsDir` ends with `/`. Same rule as `namesRecord`. */
export const recordFiles = (root, decisionsDir, id) => {
  const k = idKey(id);
  return readdirSync(path.join(root, decisionsDir), { withFileTypes: true })
    .filter((e) => isRecordFile(e) && keyNames(k, idKey(e.name.slice(0, -3))))
    .map((e) => `${decisionsDir.replace(/\/?$/, '/')}${e.name}`);
};

/** The ids that the comments of one file cite, each once, in order of first cite. A string, a Python triple-quoted string and a heredoc hold none. */
export const citedIds = (src, file, pattern) => {
  const re = new RegExp(`(?<![A-Za-z0-9_])(?:${pattern})(?![A-Za-z0-9_])`, 'g');
  return [...new Set([...commentsOf(src, file).matchAll(re)].map((m) => m[0]).filter(Boolean))];
};

// ---- The files a record names ----

const stemOf = (name) => name.slice(0, -3);

// lint/layout.json sits in the claude-settings root, four folders above this file. Through the install link its real path is inside the clone.
// A copy of the skill outside the clone has no layout beside it, and then it has no debts folder.
const layoutFile = () => path.join(path.dirname(realpathSync(fileURLToPath(import.meta.url))), '..', '..', '..', '..', 'lint', 'layout.json');
const debtsFolders = new Map();
const readJson = (file) => { try { return JSON.parse(readFileSync(file, 'utf8')); } catch (e) { if (e.code === 'ENOENT') return null; throw new Error(`cannot read ${file}: ${e.message}`); } };

/**
 * The debts folder of `root` as lint/layout.json gives it: the layout path of kind `debts` in a repo that has rolled out (its extras file marks `"rolled-out": true`),
 * else the layout's legacy path for it. From the repository root with `/` separators; null when the skill has no layout beside it.
 * It reads the JSON in this process: lint/layout.py `path()` is the same rule, and a `python3` start would add a process to every check run.
 * BANDAID, named: it does not read "legacy-repos" (a repo that keeps a kind elsewhere, by its origin name). No entry there names `debts` today, so a layout that adds one throws here.
 * Cause: the one reader of the layout is Python. Retire this when a shared JS reader exists.
 */
export const debtsDir = (root) => {
  if (debtsFolders.has(root)) return debtsFolders.get(root);
  const layout = readJson(layoutFile());
  let found = null;
  if (layout) {
    const held = layout.kinds?.debts?.path?.replace(/^\/+|\/+$/g, '');
    if (!held) throw new Error('lint/layout.json has no "debts" kind');
    if (Object.values(layout['legacy-repos'] ?? {}).some((entry) => entry && 'debts' in entry)) throw new Error('lint/layout.json keeps the debts kind elsewhere in a repo ("legacy-repos"), and the map skill does not read that');
    const extras = layout.extras ? readJson(path.join(root, ...layout.extras.split('/'))) : null;
    found = extras?.['rolled-out'] === true ? held : (layout.legacy?.[held] ?? held);
  }
  debtsFolders.set(root, found);
  return found;
};

const mdNames = (root, dir) => {
  try { return readdirSync(path.join(root, dir), { withFileTypes: true }).filter(isRecordFile).map((e) => e.name).sort(); } catch (e) { if (e.code === 'ENOENT') return []; throw e; }
};

/** The debt records of `root`: each `.md` file directly in the debts folder, except notes.md and README.md. As { dir, exists, slugs }; `slugs` are the file names without `.md`. */
export const debtRecords = (root) => {
  const dir = debtsDir(root);
  return { dir, exists: !!dir && existsSync(path.join(root, dir)), slugs: dir ? mdNames(root, dir).map(stemOf) : [] };
};

/** The id of a decision record: the leading match of `pattern` on its file name without `.md`, when that id names the record. Else null. */
export const recordId = (stem, pattern) => {
  const id = new RegExp(`^(?:${pattern})`).exec(stem)?.[0];
  return id && keyNames(idKey(id), idKey(stem)) ? id : null;
};

/**
 * The tracked files that the records name, as a Map { file -> { decisions, debts } }: `decisions` is the id of each naming decision record (a record with no id adds none),
 * `debts` the slug of each naming debt record. A record names a file only by a backticked token that equals the file's path. A record, a docs/map/ page and map.config.json
 * are named by no file. `decisionsDir` may be unset: then only debts name. `all` is the tracked files, and `read(file)` their text.
 */
export const recordNaming = ({ root, read, all, decisionsDir, idPattern }) => {
  const tracked = new Set(all);
  const debts = debtRecords(root);
  const dd = decisionsDir ? decisionsDir.replace(/\/?$/, '/') : null;
  const skip = (f) => f === 'map.config.json' || f.startsWith('docs/map/') || (dd && f.startsWith(dd)) || (debts.dir && f.startsWith(`${debts.dir}/`));
  const found = new Map();
  const scan = (file, kind, name) => {
    for (const [, token] of read(file).matchAll(/`([^`\n]+)`/g)) {
      if (!tracked.has(token) || skip(token)) continue;
      if (!found.has(token)) found.set(token, { decisions: [], debts: [] });
      const list = found.get(token)[kind];
      if (name && !list.some((x) => idKey(x) === idKey(name))) list.push(name);
    }
  };
  if (dd) for (const n of mdNames(root, dd)) scan(`${dd}${n}`, 'decisions', recordId(stemOf(n), idPattern));
  if (debts.dir) for (const slug of debts.slugs) scan(`${debts.dir}/${slug}.md`, 'debts', slug);
  return found;
};

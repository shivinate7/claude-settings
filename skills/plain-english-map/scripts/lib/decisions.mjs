// The one home of the decision-id rules: which record an id names, and which ids a file's comments cite.
// MAP10 (`map-check.mjs`) and `map-fix.mjs` both read them here, so the two never disagree.
// A LEAF: it imports only node builtins and `source-text.mjs`. The map lines are parsed in `map-check.mjs`.
import { readdirSync } from 'node:fs';
import path from 'node:path';
import { commentsOf } from './source-text.mjs';

/** An id in the form that compares: each run of digits by value, so `D7` and `D007` are one key. */
export const idKey = (id) => id.replace(/\d+/g, (d) => d.replace(/^0+(?=\d)/, ''));

/** The keys of the records in `decisionsDir`: each `.md` file directly in the folder, by its name without `.md`. A sub-folder holds none. */
export const recordKeys = (root, decisionsDir) =>
  readdirSync(path.join(root, decisionsDir), { withFileTypes: true })
    .filter((e) => e.isFile() && e.name.endsWith('.md'))
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
    .filter((e) => e.isFile() && e.name.endsWith('.md') && keyNames(k, idKey(e.name.slice(0, -3))))
    .map((e) => `${decisionsDir.replace(/\/?$/, '/')}${e.name}`);
};

/** The ids that the comments of one file cite, each once, in order of first cite. A string, a Python triple-quoted string and a heredoc hold none. */
export const citedIds = (src, file, pattern) => {
  const re = new RegExp(`(?<![A-Za-z0-9_])(?:${pattern})(?![A-Za-z0-9_])`, 'g');
  return [...new Set([...commentsOf(src, file).matchAll(re)].map((m) => m[0]).filter(Boolean))];
};

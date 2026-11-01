// The one import reader. It imports only `source-text.mjs`, so
// `check-invariants.mjs` stays runnable with no install. `map-picture.mjs` re-exports it.
import path from 'node:path';
import { blankCommentsAndStrings } from './source-text.mjs';

const EXTS = ['.ts', '.tsx', '.mjs', '.js'];
// Found in the blanked text, so an import inside a comment or a string is no import. The quote stays, the specifier does not.
const SPEC_RE = /(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)['"`]/g;
const TS_FOR = { '.js': '.ts', '.jsx': '.tsx', '.mjs': '.mts' }; // NodeNext: `./f.js` names `f.ts` when `f.js` is not tracked.

// True when the clause between `import` or `export` and `from` brings no runtime name.
const typeOnly = (clause) => {
  const c = clause.trim();
  if (/^type\b/.test(c)) return true;
  const m = /^\{([^}]*)\}$/.exec(c);
  return m !== null && m[1].split(',').map((n) => n.trim()).filter(Boolean).every((n) => /^type\s/.test(n));
};

// The specifier of each import in a source, in source order. `{ types: false }` drops each link the
// build erases: `import type`, `export type ... from`, an all-`type` import, `import('./x').T` and
// `typeof import('./x')`. A dynamic `import('./x')` and `import('./x').then(...)` stay.
export const importEntries = (src, { types = true, file } = {}) => {
  const out = [];
  const bare = blankCommentsAndStrings(src, file);
  for (const m of bare.matchAll(SPEC_RE)) {
    const after = src.slice(m.index + m[0].length);
    const spec = /^[^'"`]*/.exec(after)[0];
    let clause = null; // the text between `import` and `from`; null for a dynamic or a bare `import 'x'`
    let kind = m[0].includes('(') ? 'dynamic' : 'import';
    if (m[0].startsWith('from')) {
      const head = bare.slice(0, m.index);
      const at = Math.max(head.lastIndexOf('import'), head.lastIndexOf('export'));
      clause = head.slice(at + 6);
      if (head.startsWith('export', at)) kind = 'export';
    }
    if (!types) {
      if (kind === 'dynamic') {
        const member = /^[^'"`]*['"`]\s*\)\s*\.\s*(\w+)/.exec(after)?.[1];
        if (/\btypeof\s*$/.test(bare.slice(0, m.index)) || (member !== undefined && !/^(then|catch|finally)$/.test(member))) continue;
      } else if (clause !== null && typeOnly(clause)) continue;
    }
    out.push({ spec, clause, kind });
  }
  return out;
};

export const importSpecifiers = (src, opts) => importEntries(src, opts).map((e) => e.spec);

// The tracked file that the specifier `spec` in the file `from` names, or null. A package specifier names none.
export const resolveSpecifier = (from, spec, tracked) => {
  if (!spec.startsWith('.')) return null;
  const base = path.posix.join(path.posix.dirname(from), spec);
  const ext = path.posix.extname(base);
  return [base, ...(TS_FOR[ext] ? [base.slice(0, -ext.length) + TS_FOR[ext]] : []), ...EXTS.map((e) => base + e), ...EXTS.map((e) => `${base}/index${e}`)].find((c) => tracked.has(c)) ?? null;
};

// The tracked files that a source file imports. A package import and an untracked target are skipped.
export const importTargets = (from, src, tracked, opts) => {
  const found = new Set();
  if (!/\.(ts|tsx|mjs|js|cjs)$/.test(from)) return []; // A .py, .sh or .sql file has no JS imports.
  for (const spec of importSpecifiers(src, { file: from, ...opts })) {
    const hit = resolveSpecifier(from, spec, tracked);
    if (hit) found.add(hit);
  }
  return [...found].sort();
};

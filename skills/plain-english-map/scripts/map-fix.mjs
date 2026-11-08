// The decisions-line fixer: `node <skill>/scripts/map-fix.mjs [--write]`, run from the host repository root.
// It adds the ids and slugs that MAP10 says a map line lacks: each id that a mapped code file's comments cite and that names a record in `decisionsDir`,
// the id of each decision record that names a non-code file, and the slug of each debt record that names it.
// It is add-only: it never removes or reorders an id, and it never touches a line that is not a decisions line, a debts line or a map line.
// With no flag it prints one line per id or slug it would add, and writes nothing. With `--write` it adds them: it creates the decisions line
// (and the debts line, right after it) right under the map line when there is none. A second `--write` changes no byte.
import { readFileSync, realpathSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { decisionGaps, gitLsFiles, mapFilePaths } from './map-check.mjs';
import { loadMapConfig } from './lib/map-config.mjs';
import { debtRecords } from './lib/decisions.mjs';

/** The ids and slugs to add, as { page, file, id } (a slug is an `id` with `slug: true`), and each page's new text. Writes nothing. Throws when the config sets no decision keys and there is no debts folder. */
export const planDecisionFix = (root) => {
  const cfg = loadMapConfig(path.join(root, 'map.config.json'), root);
  if (!cfg.decisionsDir && !debtRecords(root).exists) throw new Error('map.config.json has no "decisionsDir" and "decisionIdPattern" setting, so there are no decision ids to add');
  const read = (f) => readFileSync(path.join(root, f), 'utf8');
  const all = gitLsFiles(root);
  const pages = mapFilePaths(all).map((f) => [f, read(f)]);
  const { missing } = decisionGaps({ cfg, root, read, all, pages });
  const adds = missing.flatMap((m) => [...m.ids.map((id) => ({ page: m.page, file: m.file, id })), ...m.slugs.map((id) => ({ page: m.page, file: m.file, id, slug: true }))]);
  const texts = {};
  for (const [page, text] of pages) {
    const mine = missing.filter((m) => m.page === page);
    if (!mine.length) continue;
    const lines = text.split('\n');
    // A CRLF page keeps its line ends: the `\r` stays at the end of the line it was on.
    const cr = (at) => (lines[at].endsWith('\r') ? '\r' : '');
    const join = (list) => list.map((x) => `\`${x}\``);
    // An existing line takes its additions first: that shifts no line number. A new line goes right under its map line, the decisions line before the debts line.
    // From the last map line up, so an insert never moves a line number that is still to be used.
    for (const m of mine) {
      for (const [list, at] of [[m.ids, m.at], [m.slugs, m.slugsAt]]) {
        if (!list.length || !at) continue;
        lines[at - 1] = `${lines[at - 1].slice(0, lines[at - 1].length - cr(at - 1).length)}${join(list).map((x) => `, ${x}`).join('')}${cr(at - 1)}`;
      }
    }
    for (const m of [...mine].sort((a, b) => b.line - a.line)) {
      const fresh = [];
      if (m.ids.length && !m.at) fresh.push(`  - Decisions: ${join(m.ids).join(', ')}${cr(m.line - 1)}`);
      if (m.slugs.length && !m.slugsAt) fresh.push(`  - Debts: ${join(m.slugs).join(', ')}${cr(m.line - 1)}`);
      lines.splice(m.line, 0, ...fresh);
    }
    texts[page] = lines.join('\n');
  }
  return { adds, texts };
};

// `realpathSync` on both sides: a run through a junction or symlink to the skill folder must still match.
const isMain = () => {
  try { return !!process.argv[1] && realpathSync(fileURLToPath(import.meta.url)) === realpathSync(path.resolve(process.argv[1])); } catch (e) { if (e.code === 'ENOENT') return false; throw e; }
};
if (isMain()) {
  try {
    const flags = process.argv.slice(2);
    const bad = flags.find((f) => f !== '--write');
    if (bad) throw new Error(`unknown flag ${bad}: the only flag is --write`);
    const { adds, texts } = planDecisionFix(process.cwd());
    for (const a of adds) console.log(`${a.page}: ${a.file}: add ${a.slug ? 'debt ' : ''}${a.id}`);
    if (!adds.length) console.log('No decision id or debt slug to add.');
    else if (flags.includes('--write')) {
      for (const [page, text] of Object.entries(texts)) writeFileSync(path.join(process.cwd(), page), text);
      console.log(`Added ${adds.length} id(s) in ${Object.keys(texts).length} map page(s).`);
    } else console.log('Nothing written. Run again with --write to add them.');
  } catch (e) {
    console.error(e.message);
    process.exitCode = 1;
  }
}

// The decisions-line fixer: `node <skill>/scripts/map-fix.mjs [--write]`, run from the host repository root.
// It adds the ids that MAP10 says a map line lacks: each id that a mapped file's comments cite and that names a record in `decisionsDir`.
// It is add-only: it never removes or reorders an id, and it never touches a line that is not a decisions line or a map line.
// With no flag it prints one line per id it would add, and writes nothing. With `--write` it adds them: it creates the decisions line
// right under the map line when there is none. A second `--write` changes no byte.
import { readFileSync, realpathSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { decisionGaps, gitLsFiles, mapFilePaths } from './map-check.mjs';
import { loadMapConfig } from './lib/map-config.mjs';

/** The ids to add, as { page, file, id }, and each page's new text. Writes nothing. Throws when the config sets no decision keys. */
export const planDecisionFix = (root) => {
  const cfg = loadMapConfig(path.join(root, 'map.config.json'), root);
  if (!cfg.decisionsDir) throw new Error('map.config.json has no "decisionsDir" and "decisionIdPattern" setting, so there are no decision ids to add');
  const read = (f) => readFileSync(path.join(root, f), 'utf8');
  const all = gitLsFiles(root);
  const pages = mapFilePaths(all).map((f) => [f, read(f)]);
  const { missing } = decisionGaps({ cfg, root, read, all, pages });
  const adds = missing.flatMap((m) => m.ids.map((id) => ({ page: m.page, file: m.file, id })));
  const texts = {};
  for (const [page, text] of pages) {
    // From the last line up, so an insert never moves a line number that is still to be used.
    const mine = missing.filter((m) => m.page === page).sort((a, b) => b.line - a.line);
    if (!mine.length) continue;
    const lines = text.split('\n');
    for (const m of mine) {
      const ids = m.ids.map((id) => `\`${id}\``);
      const at = (m.at ?? m.line) - 1;
      // A CRLF page keeps its line ends: the `\r` stays at the end of the line it was on.
      const cr = lines[at].endsWith('\r') ? '\r' : '';
      if (m.at) lines[at] = `${lines[at].slice(0, lines[at].length - cr.length)}${ids.map((x) => `, ${x}`).join('')}${cr}`;
      else lines.splice(at + 1, 0, `  - Decisions: ${ids.join(', ')}${cr}`);
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
    for (const a of adds) console.log(`${a.page}: ${a.file}: add ${a.id}`);
    if (!adds.length) console.log('No decision id to add.');
    else if (flags.includes('--write')) {
      for (const [page, text] of Object.entries(texts)) writeFileSync(path.join(process.cwd(), page), text);
      console.log(`Added ${adds.length} id(s) in ${Object.keys(texts).length} map page(s).`);
    } else console.log('Nothing written. Run again with --write to add them.');
  } catch (e) {
    console.error(e.message);
    process.exitCode = 1;
  }
}

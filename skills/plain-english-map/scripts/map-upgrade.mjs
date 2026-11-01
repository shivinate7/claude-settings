// The upgrade command: `node <skill>/scripts/map-upgrade.mjs`, run from the host repository root.
// It brings the map files of the host up to `MAP_FORMAT_VERSION`, in place, one step at a time, and sets `formatVersion` in `map.config.json`.
// A step keeps every plain-English sentence. A map that is already current changes no file, so a second run is a no-op.
// A map newer than the skill is refused, and nothing is written.
// To add a step: raise `MAP_FORMAT_VERSION` in `lib/map-config.mjs`, and append one `{ from, run }` here.
import { readdirSync, readFileSync, realpathSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { MAP_FORMAT_VERSION, readFormatVersion } from './lib/map-config.mjs';


/**
 * The steps, in order. Each `run` takes one map file's text and answers it in the next version.
 * Step 2 to 3: no file changes (see its comment).
 * Step 1 to 2: version 1 map lines carried line references, and a line number goes stale with the next edit.
 * It removes the three forms of them. A reference that was rewritten by hand into other words is not a form it can find.
 * `run` takes the config too: a ":N" goes only after a name whose extension is in `codeExtensions`, so `example.com:3000` stays.
 */
export const STEPS = [
  {
    from: 1,
    run: (text, cfg) => {
      const exts = cfg.codeExtensions;
      if (!Array.isArray(exts) || exts.some((e) => typeof e !== 'string' || !/^[a-z0-9]+$/i.test(e))) throw new Error('map.config.json "codeExtensions" must be a list of extensions, so the upgrade can tell a file name from a host name');
      return text
        // A parenthesis that holds only line references (`:26-36`, or `:1`, `:2`) goes, with the space before it: "x (`:26-36`). y" becomes "x. y".
        .replace(/ \(`:\d+(?:-\d+)?`(?:, `:\d+(?:-\d+)?`)*\)/g, '')
        // "`file.ext:N`" loses its ":N" part when "ext" is a code extension.
        .replace(new RegExp(String.raw`\`([^\`\s:]+\.(?:${exts.join('|')})):\d+(?:-\d+)?\``, 'g'), '`$1`')
        // ", `:N`" goes from inside a parenthesis that has a name: "(`notes`, `:492`)" becomes "(`notes`)". A run of them goes at once.
        .replace(/(?:, `:\d+(?:-\d+)?`)+(?=\))/g, '');
    },
  },
  // Version 3 adds the fact line, the Homes section and MAP9. A version 2 map holds none of them, so no file changes: the step only moves the version.
  // The check then refuses a copy of the skill that is older than 3, instead of passing a map whose facts it never reads.
  { from: 2, run: (text) => text },
];

const mapFilesOf = (root) => {
  const out = [];
  for (const dir of ['docs/map', 'docs/map/traces'])
    try { for (const e of readdirSync(path.join(root, dir), { withFileTypes: true })) if (e.isFile() && e.name.endsWith('.md')) out.push(`${dir}/${e.name}`); } catch (e) { if (e.code !== 'ENOENT') throw e; }
  return out;
};

/** Upgrades the map of `root`. It answers the list of files it wrote. It throws, and writes nothing, for a map the skill cannot read. */
export const upgradeMap = (root) => {
  const cfgFile = path.join(root, 'map.config.json');
  const raw = readFileSync(cfgFile, 'utf8');
  const cfg = JSON.parse(raw);
  if (cfg === null || typeof cfg !== 'object' || Array.isArray(cfg)) throw new Error('map.config.json is not an object: the top level must be a JSON object');
  const version = readFormatVersion(cfg);
  if (version === MAP_FORMAT_VERSION) return [];
  const wrote = [];
  for (const f of mapFilesOf(root)) {
    const before = readFileSync(path.join(root, f), 'utf8');
    const after = STEPS.filter((s) => s.from >= version).reduce((t, s) => s.run(t, cfg), before);
    if (after !== before) { writeFileSync(path.join(root, f), after); wrote.push(f); }
  }
  const eol = raw.includes('\r\n') ? '\r\n' : '\n';
  // The new version wins over a "formatVersion": 1 in the file. The key keeps its place.
  const next = { formatVersion: MAP_FORMAT_VERSION, ...cfg };
  next.formatVersion = MAP_FORMAT_VERSION;
  writeFileSync(cfgFile, `${JSON.stringify(next, null, 2).replace(/\n/g, eol)}${eol}`);
  return [...wrote, 'map.config.json'];
};

// `realpathSync` on both sides: a run through a junction or symlink to the skill folder must still match.
const isMain = () => {
  try { return !!process.argv[1] && realpathSync(fileURLToPath(import.meta.url)) === realpathSync(path.resolve(process.argv[1])); } catch (e) { if (e.code === 'ENOENT') return false; throw e; }
};
if (isMain()) {
  try {
    const wrote = upgradeMap(process.cwd());
    console.log(wrote.length ? `Upgraded the map to version ${MAP_FORMAT_VERSION}. Files written: ${wrote.join(', ')}` : `The map is at version ${MAP_FORMAT_VERSION}. No file changed.`);
  } catch (e) {
    console.error(e.message);
    process.exitCode = 1;
  }
}

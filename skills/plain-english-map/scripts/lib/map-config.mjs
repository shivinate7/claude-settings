// The one reader and the one validator of `map.config.json`. The file holds what the map
// code knows about this project: its title, its code extensions, its screen keys, its model seam and its worker stages.
// The file is required, and `title` and `codeExtensions` are required in it. Any other key left out turns the matching check or tab off, and says so, unless `requireAllKeys` is true: then a left-out key is an error.
// A bad config is an error that names `map.config.json` and the key. It is never read as a smaller config.
import { execFileSync } from 'node:child_process';
import { readFileSync, statSync } from 'node:fs';
import path from 'node:path';
// The deep checks run the readers of `map-check.mjs`. That file imports this one too, and each side uses the other only inside a function, never at load.
import { screenKeysFromSource, extRe, stageSitesOf, seamHasCallSite } from '../map-check.mjs';

// The reader of model-call sites that the `modelSeam` deep check runs. The host binds it once. The map tab binds its own reader apart, so
// swapping that one never changes what the validator accepts. The command binds none, and then the deep check is skipped.
let seamReader = null;
export const bindSeamReader = (readSites) => { seamReader = readSites; };
/** The bound call-site reader, or null when the host binds none. */
export const boundSeamReader = () => seamReader;

// The host repository is the root, never the skill's own folder: the skill is linked into `~/.claude/skills/`, and it runs from the host's working directory.
// A caller that knows another root passes it.

// The optional keys. `requireAllKeys` makes each one required, and the test reads this same list.
export const OPTIONAL_KEYS = Object.freeze(['screenKeys', 'modelSeam', 'workerStage', 'migrationsDir']);

/** The map format this skill reads and writes. `map.config.json` holds `formatVersion`, and a missing key means version 1. Raise it with one step in `map-upgrade.mjs`. */
export const MAP_FORMAT_VERSION = 3;

/** The format version of a parsed config. A value that is no whole number, or a version newer than the skill, is an error. It never answers a version the skill cannot read. */
export const readFormatVersion = (cfg) => {
  const v = cfg.formatVersion ?? 1;
  if (!Number.isInteger(v) || v < 1) throw new Error(`map.config.json "formatVersion" must be a whole number, 1 or more, and it is ${JSON.stringify(v)}`);
  if (v > MAP_FORMAT_VERSION) throw new Error(`map.config.json "formatVersion" is ${v}, and this skill reads up to ${MAP_FORMAT_VERSION}. Update the skill: it never changes a newer map.`);
  return v;
};

const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const kindOf = (abs) => {
  try { return statSync(abs).isDirectory() ? 'folder' : 'file'; } catch { return null; }
};
// A config this module returned. `validateMapConfig` on it is then a no-op. The set holds objects, never config values.
const VALID = new WeakSet();
// The last valid result of `loadMapConfig` per root and file, with the file text it came from.
const LOADED = new Map();
const posix = (p) => p.split(/[\\/]/).filter((s) => s && s !== '.').join('/');

/**
 * Checks the whole shape of one parsed config, and the repo it names. It returns a frozen, normalized copy, or throws an error that
 * names `map.config.json` and the dotted key. Every reader that takes a config takes this object, and no reader checks a key again.
 */
export const validateMapConfig = (cfg, root = process.cwd()) => {
  if (VALID.has(cfg)) return cfg;
  const bad = (msg) => { throw new Error(`map.config.json ${msg}`); };
  const text = (obj, key, label) => { if (typeof obj[key] !== 'string' || !obj[key]) bad(`"${label}" must be a non-empty string`); };
  const known = (obj, keys, label) => { for (const k of Object.keys(obj)) if (!keys.includes(k)) bad(`has an unknown key "${label ? `${label}.` : ''}${k}"`); };
  let tracked;
  const trackedFiles = () => (tracked ??= (() => {
    try { return execFileSync('git', ['ls-files'], { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], windowsHide: true }).split('\n').map((l) => l.trim()).filter(Boolean); }
    catch { return bad(`codeExtensions: cannot list tracked files, because ${root} is not a git repository`); }
  })());
  // Every form and path check runs first. A check that needs git waits in this list, and runs last.
  const withGit = [];
  // A path is relative, has no `..` segment, stays inside the repo root, and is the right kind.
  const place = (p, label, want) => {
    if (path.isAbsolute(p) || /^[a-z]:/i.test(p) || p.split(/[\\/]/).includes('..')) bad(`"${label}" names ${p}, and a path must be relative, inside the repo, with no ".." segment`);
    const abs = path.resolve(root, posix(p)), rel = path.relative(root, abs);
    if (rel.startsWith('..') || path.isAbsolute(rel)) bad(`"${label}" names ${p}, and it leaves the repo`);
    if (kindOf(abs) !== want) bad(`"${label}" names ${p}, and no such ${want} exists`);
    return abs;
  };
  const section = (key, keys) => {
    if (!isObject(cfg[key])) bad(`"${key}" must be an object`);
    known(cfg[key], keys, key);
    for (const k of keys) text(cfg[key], k, `${key}.${k}`);
  };
  if (!isObject(cfg)) bad('is not an object: the top level must be a JSON object');
  // The version first: a newer map may hold keys this skill does not know, and the refusal must say "update the skill", not "unknown key".
  if (readFormatVersion(cfg) < MAP_FORMAT_VERSION) bad(`"formatVersion" is ${readFormatVersion(cfg)}, and this skill reads version ${MAP_FORMAT_VERSION}. Run node <skill>/scripts/map-upgrade.mjs from the repository root, then run this command again.`);
  known(cfg, ['formatVersion', 'title', 'codeExtensions', 'mapPaths', ...OPTIONAL_KEYS, 'requireAllKeys']);
  text(cfg, 'title', 'title');
  if ('requireAllKeys' in cfg && typeof cfg.requireAllKeys !== 'boolean') bad('"requireAllKeys" must be true or false');
  // With the flag on, a left-out optional key is an error, so a deleted key goes red and never skips in silence.
  if (cfg.requireAllKeys) for (const k of OPTIONAL_KEYS) if (!(k in cfg)) bad(`"${k}" is required, because "requireAllKeys" is true`);
  if (!Array.isArray(cfg.codeExtensions) || !cfg.codeExtensions.length || cfg.codeExtensions.some((e) => typeof e !== 'string' || !/^[a-z0-9]+$/.test(e)))
    bad('"codeExtensions" is required, and must be a non-empty list of extensions in lowercase letters and digits, with no dot');
  withGit.push(() => { for (const e of cfg.codeExtensions) if (!trackedFiles().some((f) => f.endsWith(`.${e}`))) bad(`"codeExtensions" names "${e}", and no tracked file has that extension`); });
  // The scope of MAP1: path prefixes. A prefix keeps its trailing slash, so `src/` never matches `src2/`. It is not in `OPTIONAL_KEYS`: a repo that covers all of itself needs no key.
  let mapPaths;
  if ('mapPaths' in cfg) {
    if (!Array.isArray(cfg.mapPaths) || !cfg.mapPaths.length || cfg.mapPaths.some((p) => typeof p !== 'string' || !p))
      bad('"mapPaths" must be a non-empty list of path prefixes, each a non-empty string');
    mapPaths = cfg.mapPaths.map((p) => {
      if (path.isAbsolute(p) || /^[a-z]:/i.test(p) || p.split(/[\\/]/).includes('..')) bad(`"mapPaths" names ${p}, and a path must be relative, inside the repo, with no ".." segment`);
      return posix(p) + (/[\\/]$/.test(p) ? '/' : '');
    });
    withGit.push(() => { for (const p of mapPaths) if (!trackedFiles().some((f) => f.startsWith(p))) bad(`"mapPaths" names ${p}, and no tracked file starts with it`); });
  }
  const readTracked = (f) => readFileSync(path.join(root, f), 'utf8');
  if ('screenKeys' in cfg) {
    section('screenKeys', ['file', 'name']);
    const abs = place(cfg.screenKeys.file, 'screenKeys.file', 'file');
    let keys;
    try { keys = screenKeysFromSource(readFileSync(abs, 'utf8'), cfg.screenKeys.name); } catch (e) { bad(`"screenKeys.name" ${cfg.screenKeys.name} is not read from ${cfg.screenKeys.file}: ${e.message}`); }
    if (!keys.length) bad(`"screenKeys.name" ${cfg.screenKeys.name} holds no key in ${cfg.screenKeys.file}`);
  }
  if ('workerStage' in cfg) {
    section('workerStage', ['variable', 'callback']);
    for (const k of ['variable', 'callback']) if (!/^[A-Za-z_$][\w$]*$/.test(cfg.workerStage[k])) bad(`"workerStage.${k}" must be one identifier`);
    const ext = extRe(cfg);
    // Each name must find its own site, so a site of one name never rescues the other.
    withGit.push(() => {
      for (const k of ['variable', 'callback']) {
        const only = { [k]: cfg.workerStage[k] };
        // A file that does not hold the name as text has no site for it, so the scan skips that file.
        if (!trackedFiles().some((f) => { if (!ext.test(f)) return false; const src = readTracked(f); return src.includes(cfg.workerStage[k]) && stageSitesOf(src, only, f).length; }))
          bad(`"workerStage.${k}" ${cfg.workerStage[k]} finds no stage site in any tracked code file`);
      }
    });
  }
  if ('migrationsDir' in cfg) {
    text(cfg, 'migrationsDir', 'migrationsDir');
    place(cfg.migrationsDir, 'migrationsDir', 'folder');
    const dir = `${posix(cfg.migrationsDir)}/`;
    withGit.push(() => { if (!trackedFiles().some((f) => f.startsWith(dir) && f.endsWith('.sql'))) bad(`"migrationsDir" names ${cfg.migrationsDir}, and it holds no tracked .sql file`); });
  }
  if ('modelSeam' in cfg) {
    section('modelSeam', ['file']);
    place(cfg.modelSeam.file, 'modelSeam.file', 'file');
    // With no call-site reader bound (the command binds none), the deep check is skipped. The command prints a note that says so.
    withGit.push(() => { const sites = seamReader; if (sites && !seamHasCallSite(posix(cfg.modelSeam.file), trackedFiles(), readTracked, sites))
      bad(`"modelSeam.file" names ${cfg.modelSeam.file}, and no tracked code file calls a model through it`); });
  }
  for (const run of withGit) run();
  const out = Object.freeze({
    formatVersion: MAP_FORMAT_VERSION,
    title: cfg.title,
    codeExtensions: Object.freeze([...cfg.codeExtensions]),
    ...(mapPaths && { mapPaths: Object.freeze(mapPaths) }),
    ...(cfg.requireAllKeys && { requireAllKeys: true }),
    ...('screenKeys' in cfg && { screenKeys: Object.freeze({ ...cfg.screenKeys }) }),
    ...('modelSeam' in cfg && { modelSeam: Object.freeze({ file: posix(cfg.modelSeam.file) }) }),
    ...('workerStage' in cfg && { workerStage: Object.freeze({ ...cfg.workerStage }) }),
    ...('migrationsDir' in cfg && { migrationsDir: `${posix(cfg.migrationsDir)}/` }),
  });
  VALID.add(out);
  return out;
};

/** Reads and validates one config file. A missing, broken or malformed file is an error that names the file, never an empty config. */
export const loadMapConfig = (file, root = process.cwd()) => {
  file ??= path.join(root, 'map.config.json');
  let text, cfg;
  try {
    text = readFileSync(file, 'utf8');
    cfg = JSON.parse(text);
  } catch (e) {
    throw new Error(`map.config.json cannot be read (${file}): ${e.message}`);
  }
  // The file is read on every call. The deep checks run again only when its text, its path or the root changes.
  const key = `${root}\0${file}`, hit = LOADED.get(key);
  if (hit?.text === text) return hit.out;
  const out = validateMapConfig(cfg, root);
  LOADED.set(key, { text, out });
  return out;
};

/** The repo's own config, read and checked on every call: a changed file is read again. A repo with no valid `map.config.json` fails here. */
export const repoMapConfig = () => loadMapConfig();

// The path aliases of the host's root `tsconfig.json`, for the import reader (`import-reader.mjs` → `resolveSpecifier`).
// It reads that one file, with its `extends` chain. A `jsconfig.json`, a nested tsconfig and a bundler or test-runner alias are not read.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import ts from './lazy-typescript.mjs';

const NO_INPUTS = 18003; // `include` is never walked here, so "no inputs were found" is expected.

const rel = (root, abs) => path.relative(root, abs).split(path.sep).join('/');

/**
 * `{ ok: true, aliases }` for the root tsconfig.json of `root`: `aliases` is null when the file is missing or sets no `baseUrl` and
 * no `paths`, else `{ baseUrl, paths, pathsBase }` with each folder from `root`. `pathsBase` is where the `paths` targets resolve from:
 * `baseUrl`, else the folder of the file that holds `paths`. `{ ok: false, reason }` when the file is there and cannot be read.
 */
export const readPathAliases = (root) => {
  const file = path.join(root, 'tsconfig.json');
  let text;
  try { text = readFileSync(file, 'utf8'); } catch (e) {
    return e.code === 'ENOENT' ? { ok: true, aliases: null } : { ok: false, reason: `tsconfig.json cannot be read: ${e.code ?? e.message}` };
  }
  const say = (d) => ts.flattenDiagnosticMessageText(d.messageText, ' ');
  try {
    const { config, error } = ts.readConfigFile(file, () => text);
    if (error) return { ok: false, reason: `tsconfig.json cannot be parsed: ${say(error)}` };
    // `readDirectory` returns nothing, so the parse never walks the `include` globs of the host.
    const host = { useCaseSensitiveFileNames: true, readDirectory: () => [], fileExists: ts.sys.fileExists, readFile: ts.sys.readFile };
    const parsed = ts.parseJsonConfigFileContent(config, host, root, undefined, file);
    const errors = parsed.errors.filter((d) => d.code !== NO_INPUTS);
    if (errors.length) return { ok: false, reason: `tsconfig.json cannot be parsed: ${say(errors[0])}` };
    const { baseUrl, paths, pathsBasePath } = parsed.options;
    if (baseUrl === undefined && paths === undefined) return { ok: true, aliases: null };
    return {
      ok: true,
      aliases: {
        baseUrl: baseUrl === undefined ? null : rel(root, baseUrl),
        paths: paths ?? null,
        pathsBase: rel(root, baseUrl ?? pathsBasePath),
      },
    };
  } catch (e) {
    return { ok: false, reason: `tsconfig.json cannot be read: ${e.message}` };
  }
};

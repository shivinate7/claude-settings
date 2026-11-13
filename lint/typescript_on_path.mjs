// The TypeScript compiler on PATH, loaded for a script that parses JS or TS (lint/comment_scan.mjs,
// hooks/comment_only.mjs). The one home of the lookup: `tsc` is followed through a symlink or shim to its package.
// The caller puts the version it wants first on PATH, so no version is named here.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

// Throws when `tsc` is not on PATH or its package cannot be loaded.
export function loadTypescript() {
  for (const dir of (process.env.PATH || "").split(path.delimiter)) {
    const tsc = path.join(dir, "tsc");
    if (!dir || !fs.existsSync(tsc)) continue;
    // The first tsc on PATH is the one the caller chose: a broken one is an error, never a reason to look further.
    const root = path.resolve(path.dirname(fs.realpathSync(tsc)), "..");
    for (const candidate of [path.join(root, "lib", "typescript.js"), root]) {
      try {
        return require(candidate);
      } catch { /* try the package root next */ }
    }
    throw new Error(`the typescript package is not beside ${tsc}`);
  }
  throw new Error("tsc is not on PATH");
}

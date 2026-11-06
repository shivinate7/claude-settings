// Links each root file unrun, and checks every import against the target's exports, as Node does before it runs a line.
//   node --no-warnings --experimental-vm-modules --experimental-import-meta-resolve link_check.mjs <root file>...
// Run from the repo root; the roots are paths from there. tsc has no checkJs for type errors here, so a missing named export or
// a missing package in a script turns nothing red; this closes that gap without running the script (many read argv or start servers).
// The project's own files are parsed and linked, never evaluated. A package or `node:` module is really imported, so its export
// names are real. A `.ts` file goes through the TypeScript transpiler, found in the repo's own node_modules, never this folder's.
// A `.ts` root resolves as `tsx` does: `./f.js` names `f.ts`, `./f` probes `.ts .tsx .mjs .js` and `f/index.*`, and `@/x` names `x`
// from the repo root. A `.mjs` root resolves as node does: the exact path. A `.json` target is a leaf with a `default` export.
// A bare specifier resolves from the importing file, so a package under a subfolder's node_modules is found from that subfolder.
// Output: `FAIL load: <path>` and the error for each root that does not link, then a count. Exit 0 all link, 1 a root failed,
// 2 unknown (typescript cannot be loaded from the repo root; the reason is the only output line).
import { existsSync, readFileSync, statSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve, extname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import vm from 'node:vm';

const REPO = process.cwd();
let ts;
try {
  // ESM resolution, not require.resolve: require also reads NODE_PATH, which would find a global copy the repo does not hold.
  ts = createRequire(import.meta.url)(fileURLToPath(import.meta.resolve('typescript', pathToFileURL(resolve(REPO, 'package.json')).href)));
} catch (error) {
  console.log(`cannot load typescript from ${REPO}: ${String(error?.message ?? error).split('\n')[0]}`);
  process.exit(2);
}

const EXTS = ['.ts', '.tsx', '.mjs', '.js'];
const TS_FOR = { '.js': '.ts', '.jsx': '.tsx', '.mjs': '.mts' };

const isFile = (p) => existsSync(p) && statSync(p).isFile();
let tsx = false; // the current root runs under `tsx` (a .ts file), not under node
const local = (spec) => spec.startsWith('.') || (tsx && spec.startsWith('@/'));
const find = (from, spec) => {
  const base = spec.startsWith('@/') ? resolve(REPO, spec.slice(2)) : resolve(dirname(from), spec);
  if (!tsx) return isFile(base) ? base : null; // node: no extension probe and no .js -> .ts swap
  const ext = extname(base);
  const swap = TS_FOR[ext] ? [base.slice(0, -ext.length) + TS_FOR[ext]] : [];
  return [base, ...swap, ...EXTS.map((e) => base + e), ...EXTS.map((e) => `${base}/index${e}`)].find(isFile) ?? null;
};

const sources = new Map(); // a file in many graphs is transpiled once
const source = (file) => {
  if (!sources.has(file)) sources.set(file, read(file));
  return sources.get(file);
};
const read = (file) => {
  const text = readFileSync(file, 'utf8');
  if (!/\.m?tsx?$/.test(file)) return text;
  const out = ts.transpileModule(text, {
    fileName: file,
    reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, verbatimModuleSyntax: false, isolatedModules: true },
  });
  const bad = out.diagnostics?.[0];
  if (bad) throw new SyntaxError(`${file}: ${ts.flattenDiagnosticMessageText(bad.messageText, ' ')}`);
  return out.outputText;
};

const modules = new Map(); // file -> module, for the current root's graph
const packages = new Map(); // resolved url -> SyntheticModule
const deps = new Map(); // module -> Map(specifier -> module)

const synthetic = async (spec, parent) => {
  // The url, not the specifier, is the key: one name can mean two packages from two folders.
  const url = import.meta.resolve(spec, pathToFileURL(parent).href);
  if (packages.has(url)) return packages.get(url);
  const ns = await import(url);
  const names = Object.keys(ns);
  const m = new vm.SyntheticModule(names, function () { for (const n of names) this.setExport(n, ns[n]); }, { identifier: url });
  packages.set(url, m);
  deps.set(m, new Map());
  return m;
};

const build = async (file) => {
  if (modules.has(file)) return modules.get(file);
  if (file.endsWith('.json')) {
    let json;
    try { json = JSON.parse(readFileSync(file, 'utf8')); } catch (error) { throw new SyntaxError(`${file}: ${error.message}`); }
    const leaf = new vm.SyntheticModule(['default'], function () { this.setExport('default', json); }, { identifier: pathToFileURL(file).href });
    modules.set(file, leaf);
    deps.set(leaf, new Map());
    return leaf;
  }
  let m;
  try { m = new vm.SourceTextModule(source(file), { identifier: pathToFileURL(file).href }); } catch (error) {
    if (String(error?.message).includes(file)) throw error; // a dependency's syntax error names the dependency, not the root
    throw new SyntaxError(`${file}: ${error?.message ?? error}`);
  }
  modules.set(file, m);
  const edges = new Map();
  deps.set(m, edges);
  for (const spec of m.moduleRequests?.map((r) => r.specifier) ?? m.dependencySpecifiers) {
    if (!local(spec)) { edges.set(spec, await synthetic(spec, file)); continue; }
    const target = find(file, spec);
    if (target === null) throw new Error(`Cannot find module '${spec}' imported from ${file}`);
    edges.set(spec, await build(target));
  }
  return m;
};

// A dependency links before its dependents. Nothing is evaluated; a missing named export throws here.
const link = async (root) => {
  const seen = new Set();
  const order = [];
  const walk = (m) => { if (seen.has(m)) return; seen.add(m); for (const d of deps.get(m).values()) walk(d); order.push(m); };
  walk(root);
  for (const m of order) if (m.status === 'unlinked') await m.link((spec, parent) => deps.get(parent).get(spec));
};

const files = process.argv.slice(2);
let failed = 0;
for (const f of files) {
  modules.clear(); // a file in a shared graph links with the first root that reaches it, so each root gets a fresh graph
  tsx = /\.m?tsx?$/.test(f);
  try {
    await link(await build(resolve(REPO, f)));
  } catch (error) {
    failed += 1;
    console.log(`FAIL load: ${f}\n  ${String(error?.message ?? error).split('\n').slice(0, 3).join('\n  ')}`);
  }
}
console.log(`${files.length - failed} of ${files.length} files link${failed ? `, ${failed} FAIL` : ''}.`);
process.exit(failed ? 1 : 0);

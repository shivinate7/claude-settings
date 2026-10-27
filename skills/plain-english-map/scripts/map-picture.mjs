// The web of code areas is generated from `docs/map/`, never written by hand. It reads the map lines, the trace pages and the
// code's own imports.
// Use: node <skill>/scripts/map-picture.mjs [<out.html>] [--usage <file.json>] [--config <map.config.json>], run from the root
// of a repository that has `map.config.json`. It reads that repository and writes one page. With no <out.html>, the page is
// `map.html` in a new folder under the system temp folder, and the command prints its path. The command refuses a page whose folder is inside the repository, by real path: a junction, a symlink, or a temp folder inside the repository.
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, realpathSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { stripCommentsAndStrings } from './lib/source-text.mjs';
import { importTargets } from './lib/import-reader.mjs';
import * as check from './map-check.mjs';
import { loadMapConfig, repoMapConfig as ownRepoMapConfig, validateMapConfig as ownValidateMapConfig } from './lib/map-config.mjs';
export { importTargets };

// A host may bind its own readers with `bindReaders({ ... })` before any function here. The command binds the skill's own readers
// for each name the host left unbound, except the AI calls reader: with none bound, the AI calls tab is empty.
const R = {};
export const bindReaders = (readers) => Object.assign(R, readers);
const repoMapConfig = (...a) => R.repoMapConfig(...a);
const validateMapConfig = (...a) => R.validateMapConfig(...a);
const extRe = (...a) => R.extRe(...a);
const mapCodePaths = (...a) => R.mapCodePaths(...a);
const traceSteps = (...a) => R.traceSteps(...a);
const runtimeLinks = (...a) => R.runtimeLinks(...a);
const webCalls = (...a) => R.webCalls(...a);
const routesAnswering = (...a) => R.routesAnswering(...a);
const scriptEntries = (...a) => R.scriptEntries(...a);
const aiCallRows = (...a) => R.aiCallRows(...a);
const clientPins = (...a) => R.clientPins(...a);
const pinFields = (...a) => R.pinFields(...a);

const ITEM_RE = /^[ \t]*(?:[-*+]|\d+\.)\s+`([^`]+)`\s*(?:—\s*(.*))?$/;
const kindOf = (p) => (/(^|\/)tests\/|\.test\./.test(p) ? 'test' : 'code');

const byKey = (...ks) => (a, b) => {
  for (const k of ks) if (a[k] !== b[k]) return a[k] < b[k] ? -1 : 1;
  return 0;
};

// Reads the title, the first paragraph, and each list item with the heading it sits under.
const readMap = (text) => {
  const lines = text.split('\n');
  const title = lines.find((l) => l.startsWith('# '))?.slice(2).trim() ?? '';
  let heading = '';
  const items = [];
  for (const l of lines) {
    if (/^#{1,6}\s/.test(l)) { heading = l; continue; }
    const m = l.match(ITEM_RE);
    if (m) items.push({ token: m[1], sentence: (m[2] ?? '').trim(), heading, line: l });
  }
  // The summary is the first paragraph under the title, before the first `##` heading.
  const head = text.split(/^##\s/m)[0].split('\n').slice(1).join('\n').trim();
  return { title, summary: head.split(/\n\s*\n/)[0].replace(/\s*\n\s*/g, ' ').trim(), items };
};

// Reads one trace page into its actions. Each `##` heading is an action, each numbered item a step.
const readTrace = (key, text) => {
  const actions = [];
  for (const l of text.split('\n')) {
    if (l.startsWith('## ')) actions.push({ name: l.slice(3).trim(), steps: [] });
    const [p] = traceSteps(l);
    if (p && actions.length) actions.at(-1).steps.push({ p, j: (l.match(ITEM_RE)?.[2] ?? '').trim() });
  }
  return { key, name: text.split('\n').find((l) => l.startsWith('# '))?.slice(2).trim() ?? key, actions };
};

// The web side of the app. `web` joins each client file to the file of the route that
// answers its call. `page` holds the files that `index.html` loads. `server` holds the files that register a route.
// The reader is MAP8's (`webCalls`), never a second one. Only files in the map count.
const webOf = (sources, tracked) => {
  const code = Object.keys(sources).filter((f) => /\.(ts|tsx)$/.test(f) && kindOf(f) === 'code');
  const targets = Object.fromEntries(code.map((f) => [f, runtimeLinks(f, sources[f], tracked)]));
  return webCalls({ code, src: sources, tracked, targets });
};
const webJoins = (sources, tracked, area, { calls, routes }, re) => {
  const web = new Set();
  for (const c of calls) for (const r of routesAnswering(routes, c)) if (area.has(c.from) && area.has(r.file) && c.from !== r.file) web.add(JSON.stringify({ from: c.from, to: r.file }));
  const page = [...(sources['index.html'] ?? '').matchAll(/<script[^>]*\ssrc="([^"]+)"/g)].map((m) => m[1].replace(/^\//, '')).filter((p) => area.has(p));
  return {
    web: [...web].map((j) => JSON.parse(j)).sort(byKey('from', 'to')),
    page: [...new Set(page)].sort(),
    server: [...new Set(routes.map((r) => r.file))].filter((p) => area.has(p)).sort(),
    scripts: scriptEntries(JSON.parse(sources['package.json'] ?? '{}').scripts ?? {}, tracked, routes.map((r) => r.file), re).filter((p) => area.has(p)),
  };
};

// `config` is a config the validator returned. Left out, the reader reads the repo's own file. A raw config is validated here, and a bad one throws.
export const pictureData = ({ mapFiles, traceFiles, sources, tracked, commit, config: raw }) => {
  const config = validateMapConfig(raw ?? repoMapConfig()), codeRe = extRe(config);
  const areas = [], nodes = [], tables = [], screens = [], stepNotes = {};
  const seen = new Set();
  for (const id of Object.keys(mapFiles).sort()) {
    const { title, summary, items } = readMap(mapFiles[id]);
    areas.push({ id, name: title, summary });
    for (const it of items) {
      if (mapCodePaths(it.line, codeRe).length) {
        if (seen.has(it.token)) continue;
        seen.add(it.token);
        nodes.push({ p: it.token, a: id, j: it.sentence, k: kindOf(it.token) });
      } else if (/\btables\b/i.test(it.heading)) tables.push({ name: it.token, a: id, j: it.sentence });
      else if (/\bscreens\b/i.test(it.heading)) screens.push({ name: it.token, a: id, j: it.sentence });
      else if (/\bAI call steps\b/i.test(it.heading)) stepNotes[it.token] = it.sentence;
    }
  }
  nodes.sort(byKey('p'));
  tables.sort(byKey('name'));
  screens.sort(byKey('name'));
  const area = new Map(nodes.map((n) => [n.p, n.a]));
  const links = nodes
    .flatMap((n) => (sources[n.p] ? importTargets(n.p, sources[n.p], tracked) : []).filter((t) => area.has(t) && t !== n.p).map((to) => ({ from: n.p, to })))
    .sort(byKey('from', 'to'));
  // An area link counts imports from code files only, never from test files.
  const isTest = new Set(nodes.filter((n) => n.k === 'test').map((n) => n.p));
  const counts = new Map();
  for (const l of links) {
    const a = area.get(l.from), b = area.get(l.to);
    if (a !== b && !isTest.has(l.from)) counts.set(`${a}\t${b}`, (counts.get(`${a}\t${b}`) ?? 0) + 1);
  }
  const areaLinks = [...counts].map(([k, n]) => ({ from: k.split('\t')[0], to: k.split('\t')[1], n })).sort(byKey('from', 'to'));
  const traces = Object.keys(traceFiles).sort().map((k) => readTrace(k, traceFiles[k]));
  // The AI calls tab. `aiCalls` holds one row per place that starts a model call or records
  // a step, read from the code by the reader in `.claude/skills/plain-english-map/scripts/map-check.mjs`. `aiSteps` holds one card per spend step, because `model_calls` records the step.
  // A call path with no step goes in `aiNoStep`. No money and no rate is read or held here.
  const web = webOf(sources, tracked);
  const node = new Map(nodes.map((n) => [n.p, n]));
  const named = (pred) => traces.filter((t) => t.actions.some((x) => x.steps.some((s) => pred(s.p)))).map((t) => t.key);
  // The screens that reach a row: through the clients of its route. A row with no route has none, never the screens of its whole file.
  const screensOf = (r) => {
    if (!r.route) return [];
    const path = r.route.split(' ')[1];
    const clients = new Set(web.calls.filter((c) => routesAnswering(web.routes, c).some((x) => x.file === r.p && x.path === path)).map((c) => c.from));
    return named((p) => clients.has(p));
  };
  // A call that no pin reaches in its own file is read through the client that calls its route: the chat route takes the pins of `chatService.ts`.
  const viaClient = (r) => {
    if (r.kind !== 'call' || r.pins.length || !r.route) return r;
    const path = r.route.split(' ')[1];
    const clients = [...new Set(web.calls.filter((c) => routesAnswering(web.routes, c).some((x) => x.file === r.p && x.path === path)).map((c) => c.from))];
    return clients.length ? { ...r, ...pinFields(clientPins(sources, clients, config)) } : r;
  };
  const aiCalls = aiCallRows(sources, config).map(viaClient).map((r) => ({
    p: r.p, line: r.line, step: r.step, tier: r.tier, effort: r.effort, pins: r.pins,
    a: node.get(r.p)?.a ?? null, j: node.get(r.p)?.j ?? '',
    screens: screensOf(r), route: r.route,
    outside: r.outside, kind: r.kind,
  }));
  const calls = aiCalls.filter((r) => r.kind === 'call');
  const uniq = (xs) => [...new Set(xs)].sort();
  const aiSteps = uniq(calls.map((r) => r.step).filter(Boolean)).map((step) => {
    const rows = calls.filter((r) => r.step === step);
    return {
      step, note: stepNotes[step] ?? '',
      files: uniq(rows.map((r) => r.p)).map((p) => {
        const mine = rows.filter((r) => r.p === p);
        return { p, lines: [...new Set(mine.map((r) => r.line))].sort((x, y) => x - y), j: mine[0].j, outside: mine[0].outside };
      }),
      routes: uniq(rows.map((r) => r.route).filter(Boolean)), unrouted: rows.filter((r) => !r.route).length,
      screens: uniq(rows.flatMap((r) => r.screens)),
      pins: [...new Map(rows.flatMap((r) => r.pins).filter((x) => x.tier || x.effort).map((x) => [`${x.tier}, ${x.effort}`, x])).values()],
      tier: uniq(rows.flatMap((r) => r.pins.map((x) => x.tier)).filter(Boolean)), effort: uniq(rows.flatMap((r) => r.pins.map((x) => x.effort)).filter(Boolean)),
    };
  });
  const aiNoStep = calls.filter((r) => !r.step);
  // `noSeam` is set only when the config names no model seam. The AI calls tab then says so, and it has no rows.
  const noSeam = !config.modelSeam;
  return { commit, areas, nodes, tables, screens, links, areaLinks, traces, aiCalls, aiSteps, aiNoStep, ...(noSeam ? { noSeam } : {}), ...webJoins(sources, tracked, area, web, codeRe) };
};

// The token layer of the AI calls tab (a file made outside git). It joins by step and stays in its own `usage` key,
// so the code rows never change. A sum the file gives as null stays null. Rows of one step add up over the tiers.
const addTokens = (rows) => {
  const sum = (k) => (rows.every((r) => r[k] == null) ? null : rows.reduce((s, r) => s + (r[k] ?? 0), 0));
  return { calls: sum('calls'), input: sum('input'), output: sum('output'), cacheRead: sum('cacheRead'), cacheWrite: sum('cacheWrite') };
};
export const withUsage = (data, usage) => {
  const given = new Map();
  for (const r of usage.rows) given.set(r.step, [...(given.get(r.step) ?? []), r]);
  const steps = data.aiSteps.map((c) => c.step);
  const rows = steps.map((step) => given.has(step)
    ? { step, tokens: addTokens(given.get(step)), note: null }
    : { step, tokens: null, note: 'no calls recorded in this window' });
  const unmatched = [...given].filter(([step]) => !steps.includes(step))
    .map(([step, r]) => ({ step, tokens: addTokens(r), note: 'recorded, but not found in the code' }));
  return { ...data, usage: { commit: usage.commit, from: usage.from, to: usage.to, rows, unmatched } };
};

// The area tree. Only a link from a code file counts. `usedBy` holds every area
// that uses the file, its own area too.
export const areaGroups = ({ nodes, links }, areaId) => {
  const kind = new Map(nodes.map((n) => [n.p, n]));
  const users = new Map();
  for (const l of links) {
    const from = kind.get(l.from);
    if (from?.k !== 'code') continue;
    (users.get(l.to) ?? users.set(l.to, new Set()).get(l.to)).add(from.a);
  }
  const g = { entry: [], core: [], bridge: [], shared: [], tests: [] };
  for (const n of nodes) {
    if (n.a !== areaId) continue;
    const all = users.get(n.p);
    const used = [...(all ?? [])].sort();
    if (n.k === 'test') g.tests.push({ p: n.p, usedBy: [] });
    else if (!all) g.entry.push({ p: n.p, usedBy: [] });
    else if (used.length === 1 && used[0] === areaId) g.core.push({ p: n.p, usedBy: used });
    else g[used.length >= 3 ? 'shared' : 'bridge'].push({ p: n.p, usedBy: used });
  }
  for (const list of Object.values(g)) list.sort((a, b) => b.usedBy.length - a.usedBy.length || (a.p < b.p ? -1 : 1));
  return g;
};

// Each node counts `direct` (its children before any cut) and `files` (the distinct files opened below it, never a `seen` repeat, never its own file).
const count = (n) => { n.direct = n.children.length; n.files = n.children.reduce((s, c) => s + count(c).files + (c.p && !c.seen ? 1 : 0), 0); return n; };

// Claims files breadth-first: a file belongs to the first file that reaches it, at its shortest depth. `owner` maps each file to its parent.
const claimFrom = (next, owner, queue) => {
  while (queue.length) {
    const up = [];
    for (const p of queue) for (const c of [...(next.get(p) ?? [])].sort()) if (!owner.has(c)) { owner.set(c, p); up.push(c); }
    queue = up;
  }
};
// A loop that nothing outside it reaches gives one root: its first file by path. Returns the new roots.
const loopRoots = (next, owner, files) => {
  const roots = [];
  const reach = (p) => { const r = new Set([p]); for (const q of r) for (const c of next.get(q) ?? []) r.add(c); return r; };
  for (let left = [...files].sort().filter((p) => !owner.has(p)); left.length; left = left.filter((p) => !owner.has(p))) {
    const top = left.find((p) => { const r = reach(p); return left.every((u) => !(next.get(u) ?? new Set()).has(p) || r.has(u)); });
    owner.set(top, null); roots.push(top); claimFrom(next, owner, [top]);
  }
  return roots;
};

// The area tree. Roots are the area's code files that no other code file of
// the area uses. A screen's first step comes first, with the screen's name. A file opens once, at its
// SHORTEST depth from a root (breadth-first), and every other place shows it `seen`. A loop with no
// other user gives one root: its first file by path. Other areas fold into `other`, with a count each.
export const areaTree = (data, areaId) => {
  const { nodes, links, traces = [] } = data;
  const own = nodes.filter((n) => n.a === areaId);
  const code = new Set(own.filter((n) => n.k === 'code').map((n) => n.p));
  const tag = new Map();
  for (const [g, items] of Object.entries(areaGroups(data, areaId))) for (const i of items) tag.set(i.p, g);
  const next = new Map([...code].map((p) => [p, new Set()]));
  const other = new Map([...code].map((p) => [p, new Map()]));
  const used = new Set();
  const area = new Map(nodes.filter((n) => n.k === 'code').map((n) => [n.p, n.a]));
  for (const { from, to } of links) {
    if (!code.has(from) || from === to) continue;
    if (code.has(to)) { next.get(from).add(to); used.add(to); }
    else if (area.has(to)) other.get(from).set(area.get(to), (other.get(from).get(area.get(to)) ?? 0) + 1);
  }
  const kids = (p) => [...next.get(p)].sort();
  const screens = new Map();
  for (const t of traces) {
    const first = t.actions?.[0]?.steps?.[0]?.p;
    if (code.has(first) && !used.has(first) && !screens.has(first)) screens.set(first, t.name);
  }
  const loose = [...code].filter((p) => !used.has(p) && !screens.has(p)).sort();
  const roots = [...screens.keys(), ...loose];
  const owner = new Map(roots.map((p) => [p, null]));
  claimFrom(next, owner, roots);
  roots.push(...loopRoots(next, owner, code));
  const build = (p) => ({
    p, a: areaId, g: tag.get(p),
    ...(screens.has(p) ? { screen: screens.get(p) } : {}),
    children: kids(p).map((c) => (owner.get(c) === p ? build(c) : { p: c, a: areaId, g: tag.get(c), seen: true, children: [] })),
    other: [...other.get(p)].map(([a, n]) => ({ a, n })).sort(byKey('a')),
  });
  const rootsSorted = [...roots.filter((p) => screens.has(p)), ...roots.filter((p) => !screens.has(p)).sort()];
  const built = rootsSorted.map(build);
  built.forEach(count);
  return { root: count({ a: areaId, children: built }), roots: built, tests: own.filter((n) => n.k === 'test').map((n) => n.p).sort() };
};

// The graph of the whole app: every code file, the imports between them, and the web joins. Each file carries its area and its group.
const appGraph = (data) => {
  const { nodes, links, web = [] } = data;
  const area = new Map(nodes.filter((n) => n.k === 'code').map((n) => [n.p, n.a]));
  const tag = new Map();
  for (const a of data.areas) for (const [g, items] of Object.entries(areaGroups(data, a.id))) for (const i of items) tag.set(i.p, g);
  const next = new Map([...area.keys()].map((p) => [p, new Set()]));
  for (const { from, to } of [...links, ...web]) if (area.has(from) && area.has(to) && from !== to) next.get(from).add(to);
  const leaf = (p) => ({ p, a: area.get(p), g: tag.get(p), seen: true, children: [] });
  const build = (owner) => { const b = (p) => ({ p, a: area.get(p), g: tag.get(p), children: [...next.get(p)].sort().map((c) => (owner.get(c) === p ? b(c) : leaf(c))) }); return b; };
  return { area, next, build };
};

// The app tree: one root, three trunks. The browser trunk starts at the files that the page
// loads, the server trunk at the files that register a route, and a web call joins a client file to its route's file.
// The third trunk holds the code files that neither reaches, by area. A file opens once, at its shortest depth.
export const appTree = (data) => {
  const { area, next, build } = appGraph(data);
  const owner = new Map();
  const seeds = [data.page ?? [], data.server ?? [], data.scripts ?? []].map((l) => l.filter((p) => area.has(p)));
  seeds.flat().forEach((p) => owner.set(p, null));
  claimFrom(next, owner, seeds.flat());
  const free = [...area.keys()].filter((p) => !owner.has(p));
  const loose = free.filter((p) => !free.some((q) => q !== p && next.get(q).has(p)));
  loose.forEach((p) => owner.set(p, null));
  claimFrom(next, owner, loose);
  const rest = [...loose, ...loopRoots(next, owner, area.keys())].sort();
  const b = build(owner);
  const byArea = [...new Set(rest.map((p) => area.get(p)))].sort().map((a) => ({ a, children: rest.filter((p) => area.get(p) === a).map(b) }));
  return { roots: [count({ a: null, name: data.title ?? '', children: [
    { trunk: 'browser', children: [...new Set(seeds[0])].map(b) },
    { trunk: 'server', children: [...new Set(seeds[1])].filter((p) => !seeds[0].includes(p)).map(b) },
    ...(seeds[2].length ? [{ trunk: 'scripts', children: [...new Set(seeds[2])].filter((p) => !seeds[0].includes(p) && !seeds[1].includes(p)).map(b) }] : []),
    { trunk: 'unreached', children: byArea },
  ] })] };
};

// The tree of one screen: from the first file of its trace, through imports and web calls, in every area.
export const screenTree = (data, key) => {
  const { area, next, build } = appGraph(data);
  const first = data.traces?.find((t) => t.key === key)?.actions?.[0]?.steps?.[0]?.p;
  if (!first || !area.has(first)) return { roots: [] };
  const owner = new Map([[first, null]]);
  claimFrom(next, owner, [first]);
  return { roots: [count(build(owner)(first))] };
};

// A branch with more than `max` children gives one box for each area, the largest area first (a tie by area id).
// An area box is { area, n, children }: its files with the most files under each first (a tie by path). Past `max`
// files, the last child is { fold: true, n, rest } and stands for the rest. A branch of one area gets no area box.
// The page runs this same source (`renderPage` injects it), so it holds no outside reference.
export const fold = (children, max = 8) => {
  if (children.length <= max) return children;
  const size = (n) => 1 + n.children.reduce((s, c) => s + size(c), 0);
  const by = new Map();
  for (const c of children) (by.get(c.a) ?? by.set(c.a, []).get(c.a)).push(c);
  const boxes = [...by].map(([area, files]) => {
    const sorted = files.map((f) => [f, size(f)]).sort((x, y) => y[1] - x[1] || (x[0].p < y[0].p ? -1 : 1)).map((x) => x[0]);
    const shown = sorted.length > max ? [...sorted.slice(0, max), { fold: true, n: sorted.length - max, rest: sorted.slice(max) }] : sorted;
    return { area, n: sorted.length, files: sorted.reduce((s, f) => s + (f.seen ? 0 : 1) + (f.files ?? 0), 0), children: shown };
  }).sort((x, y) => y.n - x.n || (x.area < y.area ? -1 : 1));
  return boxes.length === 1 ? boxes[0].children : boxes;
};

// The children a branch shows: all of them, or the area boxes of `fold` past `max`. A branch of one area (`area` set) is never folded.
// `place()` on the page and `branchKeys` both call this one rule. The page runs this same source (`renderPage` injects it).
export const treeKids = (n, max = 8) => (n.area || (n.children || []).length <= max ? n.children || [] : fold(n.children, max));

// The key of each branch box in a tree, as `place()` on the page builds them: the root index, then `.` and the index of the shown child.
// The fold box has a key too, and each item under it is at `key.m`. "Open all" holds these keys in the open set.
// The page runs this same source (`renderPage` injects it), so it holds no outside reference but `treeKids`.
export const branchKeys = (roots, max = 8) => {
  const out = [];
  const walk = (n, key) => {
    if (!(n.children || []).length) return;
    out.push(key);
    treeKids(n, max).forEach((c, j) => {
      const k = key + '.' + j;
      if (c.fold) { out.push(k); c.rest.forEach((r, m) => walk(r, k + '.' + m)); } else walk(c, k);
    });
  };
  roots.forEach((r, i) => walk(r, String(i)));
  return out;
};

// The focus on one file. Only a link from a code file counts. Each side is
// a tree to `depth` steps (1 to 3). A file expands once, at its SHORTEST depth from the focus file,
// found breadth-first. Every other place it appears is a `seen` leaf with no children.
// The page runs this same source (`renderPage` injects it), so it holds no outside reference.
export const focusTree = ({ nodes, links }, path, depth) => {
  const max = Math.min(3, Math.max(1, depth));
  const code = new Set(nodes.filter((n) => n.k === 'code').map((n) => n.p));
  const side = (key, other) => {
    const next = new Map();
    for (const l of links) {
      if (code.has(l.from)) (next.get(l[key]) ?? next.set(l[key], []).get(l[key])).push(l[other]);
    }
    const kids = (p) => [...new Set(next.get(p) ?? [])].sort();
    const owner = new Map([[path, null]]);
    const level = new Map([[path, 0]]);
    for (let queue = [path]; queue.length; ) {
      const upper = [];
      for (const p of queue) {
        if (level.get(p) >= max) continue;
        for (const c of kids(p)) {
          if (owner.has(c)) continue;
          owner.set(c, p);
          level.set(c, level.get(p) + 1);
          upper.push(c);
        }
      }
      queue = upper;
    }
    const build = (p) => (level.get(p) >= max ? [] : kids(p).map((c) => (
      owner.get(c) === p ? { p: c, children: build(c) } : { p: c, seen: true, children: [] }
    )));
    return build(path);
  };
  return { uses: side('from', 'to'), usedBy: side('to', 'from') };
};

// The layers. Only a link between two code files counts. A loop is a
// strongly connected group (iterative Tarjan, so a deep graph cannot overflow the stack). A group
// sits 1 row above the highest group it uses, and row 0 uses no other file.
export const layers = ({ nodes, links }) => {
  const code = nodes.filter((n) => n.k === 'code').map((n) => n.p).sort();
  const isCode = new Set(code);
  const out = new Map(code.map((p) => [p, []]));
  for (const l of links) if (isCode.has(l.from) && isCode.has(l.to) && l.from !== l.to) out.get(l.from).push(l.to);
  const index = new Map(), low = new Map(), comp = new Map(), stack = [], groups = [];
  for (const root of code) {
    if (index.has(root)) continue;
    const work = [[root, 0]];
    index.set(root, index.size); low.set(root, index.get(root)); stack.push(root);
    while (work.length) {
      const top = work.at(-1);
      const [v, i] = top;
      if (i < out.get(v).length) {
        top[1]++;
        const w = out.get(v)[i];
        if (!index.has(w)) {
          index.set(w, index.size); low.set(w, index.get(w)); stack.push(w);
          work.push([w, 0]);
        } else if (!comp.has(w)) low.set(v, Math.min(low.get(v), index.get(w)));
        continue;
      }
      work.pop();
      if (work.length) { const u = work.at(-1)[0]; low.set(u, Math.min(low.get(u), low.get(v))); }
      if (low.get(v) === index.get(v)) {
        const group = [];
        let w;
        do { w = stack.pop(); comp.set(w, groups.length); group.push(w); } while (w !== v);
        groups.push(group.sort());
      }
    }
  }
  // Tarjan emits a group after every group it uses, so each row is known when it is read.
  const row = [];
  groups.forEach((group, g) => {
    let r = 0;
    for (const p of group) for (const q of out.get(p)) if (comp.get(q) !== g) r = Math.max(r, row[comp.get(q)] + 1);
    row[g] = r;
  });
  const rows = [];
  groups.forEach((group, g) => (rows[row[g]] ??= []).push(...group));
  return { rows: rows.map((r) => r.sort()), loops: groups.filter((g) => g.length > 1).sort((a, b) => (a[0] < b[0] ? -1 : 1)) };
};

// The look-alikes. Two views of repeated work, read with no
// model. A name is listed when two or more code files define it. A browser client in
// `src/services/*Client.ts` shares names with the server on purpose, so a name is hidden when all its
// files but one are such clients. A family is the files that share the last capitalised word of the base
// name (`UserStore.ts` is `Store`); one file is no family. A test file never counts.
const isTest = (p) => /\.test\.|(^|\/)tests\//.test(p);
const isClient = (p) => /^src\/services\/[^/]*Client\.ts$/.test(p);
// The anchor (a line start, or a `;` or `}` before it) skips an `export` inside a regex literal, which the comment stripper does not read.
const EXPORT_RE = /(?:^|[;}])[ \t]*export\s+(?:async\s+)?(?:function\*?|const|let|var|class)\s+([A-Za-z_$][\w$]*)/gm;
export const lookAlikes = ({ nodes }, sources) => {
  const code = nodes.filter((n) => n.k === 'code' && !isTest(n.p)).sort(byKey('p'));
  const entry = ({ p, a, j }) => ({ p, a, j });
  const defs = new Map(), ends = new Map();
  for (const n of code) {
    const text = sources[n.p] === undefined ? '' : stripCommentsAndStrings(sources[n.p]);
    for (const name of new Set([...text.matchAll(EXPORT_RE)].map((m) => m[1]))) (defs.get(name) ?? defs.set(name, []).get(name)).push(n);
    const base = path.posix.basename(n.p).replace(/\.[^.]+$/, '');
    const end = base.match(/[A-Z][a-z0-9]*$/)?.[0];
    if (end && end !== base) (ends.get(end) ?? ends.set(end, []).get(end)).push(n);
  }
  const bySize = (a, b) => b.files.length - a.files.length;
  const names = [...defs]
    .filter(([, f]) => f.length > 1 && f.filter((n) => !isClient(n.p)).length > 1)
    .map(([name, f]) => ({ name, files: f.map(entry) }))
    .sort((a, b) => bySize(a, b) || (a.name < b.name ? -1 : 1));
  const families = [...ends]
    .filter(([, f]) => f.length > 1)
    .map(([ending, f]) => ({ ending, files: f.map(entry) }))
    .sort((a, b) => bySize(a, b) || (a.ending < b.ending ? -1 : 1));
  return { names, families, hidden: [...defs].filter(([, f]) => f.length > 1).length - names.length };
};

// The rulings. Each decision record, with the checks it lists
// (its prose names them, or a check's call or comment block cites it), sorted, and the checks its `Held by:` line holds. A numbered entry comes first, by number. A pending entry (id `pending`) comes after, by slug.
export const rulingProof = (index) => {
  const num = (e) => Number(String(e.id).match(/\d+/)?.[0] ?? Infinity);
  const entries = [...index]
    .sort((a, b) => num(a) - num(b) || (a.slug < b.slug ? -1 : a.slug > b.slug ? 1 : 0))
    .map((e) => ({ id: e.id, title: e.title, checks: [...e.checks].sort(), holds: [...(e.holds ?? [])] }));
  const held = entries.filter((e) => e.holds.length).length;
  return { entries, held, none: entries.length - held };
};

// The CLI adds the layers, the look-alikes and the area trees to the page data, so the page never computes them.
export const withGroups = (data, sources = {}, rulings = { entries: [], held: 0, none: 0 }) => ({
  ...data,
  layers: layers(data),
  lookAlikes: lookAlikes(data, sources),
  rulings,
  trees: Object.fromEntries(data.areas.map((a) => { const { roots, ...t } = areaTree(data, a.id); return [a.id, t]; })), // the page reads `root` only
  appTree: appTree(data),
  screenTrees: Object.fromEntries(data.traces.map((t) => [t.key, screenTree(data, t.key)])),
});

// The ranked map (owner ruling, 2026-10-08). `strongLinks` keeps the k strongest links of each source area (most imports first).
// A tie keeps the lower target id, whatever the input order.
// The page runs this same source (`renderPage` injects it), so it holds no outside reference.
export const strongLinks = (areaLinks, k = 2) => {
  const by = new Map();
  for (const l of areaLinks) (by.get(l.from) ?? by.set(l.from, []).get(l.from)).push(l);
  return [...by.values()].flatMap((ls) => [...ls].sort((p, q) => q.n - p.n || (p.to < q.to ? -1 : p.to > q.to ? 1 : 0)).slice(0, k));
};

// `mostUsed` lists the code files that the most other areas use: { p, areas, files }. `areas` counts the other areas whose
// code files import it. `files` counts every code file that imports it, its own area too. A test file is never an importer.
// A file that no other area uses is left out. Order: areas, then files, then path. The page runs this same source too.
export const mostUsed = (data, n = 15) => {
  const node = new Map(data.nodes.map((x) => [x.p, x]));
  const by = new Map();
  for (const { from, to } of data.links) {
    const f = node.get(from), t = node.get(to);
    if (!f || !t || f.k === 'test' || t.k === 'test') continue;
    const e = by.get(to) ?? by.set(to, { areas: new Set(), files: 0 }).get(to);
    e.files++;
    if (f.a !== t.a) e.areas.add(f.a);
  }
  return [...by].filter(([, e]) => e.areas.size).map(([p, e]) => ({ p, areas: e.areas.size, files: e.files }))
    .sort((x, y) => y.areas - x.areas || y.files - x.files || (x.p < y.p ? -1 : x.p > y.p ? 1 : 0)).slice(0, n);
};

// The AI ranking of the rulings (owner ruling, 2026-10-08). One prompt and one output shape serve the "Rank by AI" button
// and the ranking baked in at a hand rebuild. `rankPrompt` builds the prompt from `data.rulings.entries` and `data.checks`.
// `parseRank` reads a model reply into { rows: [{ id, risk, why }], problems } and never throws.
// The page runs this same source (`renderPage` injects it), so it holds no outside reference.
export const rankPrompt = (entries, checks) => {
  const said = (c) => `${c} ("${(checks[c] && checks[c].title) || 'the check gives its sentence in code'}")`;
  const lines = entries.map((e) => {
    const holds = e.holds || [], only = (e.checks || []).filter((c) => !holds.includes(c));
    const hold = holds.length ? `held by ${holds.map(said).join('; ')}` : 'no check holds it';
    return `- ${e.id} | ${e.title} | ${hold}${only.length ? `; also names ${only.map(said).join('; ')}` : ''}`;
  });
  return [
    'You rank the standing rulings of a software project by risk.',
    'Risk means: if the ruling is broken, how bad is the harm to the people the software serves? A ruling that no check holds is more exposed than one that a check holds.',
    'Give every ruling below one risk: high, medium or low. Put the riskiest rulings first.',
    'Reply with only a JSON array, no other text. Each item has this shape: {"id": "<ruling id>", "risk": "high", "why": "<at most 20 words, plain words>"}.',
    'Use each ruling id once, exactly as written. Judge from the lines below only.',
    '',
    'Rulings, one per line as: id | title | what holds it',
    ...lines,
  ].join('\n');
};

export const parseRank = (text, ids) => {
  const problems = [], rows = [];
  try {
    const known = new Set(ids), seen = new Set();
    const raw = typeof text === 'string' ? text.trim() : '';
    let value, ok = false;
    const attempt = (t) => { if (ok) return; try { value = JSON.parse(t); ok = true; } catch { /* try the next form */ } };
    attempt(raw);
    const fence = raw.match(/```(?:json)?\s*([\s\S]*?)```/i);
    if (fence) attempt(fence[1].trim());
    if (raw.indexOf('[') >= 0 && raw.lastIndexOf(']') > raw.indexOf('[')) attempt(raw.slice(raw.indexOf('['), raw.lastIndexOf(']') + 1));
    if (!ok || !Array.isArray(value)) {
      problems.push(ok ? 'The reply is JSON, but not a list of rows.' : 'The reply is not JSON, so no row was read.');
      return { rows, problems };
    }
    for (const x of value) {
      if (!x || typeof x !== 'object' || Array.isArray(x)) { problems.push('A row is not an object, so it was dropped.'); continue; }
      const id = typeof x.id === 'string' ? x.id : '';
      if (!known.has(id)) { problems.push(`Unknown id ${id || String(x.id)}, so its row was dropped.`); continue; }
      if (!['high', 'medium', 'low'].includes(x.risk)) { problems.push(`${id} has the risk "${String(x.risk)}", so its row was dropped.`); continue; }
      if (seen.has(id)) { problems.push(`${id} appears more than once. The first row is kept.`); continue; }
      seen.add(id);
      rows.push({ id, risk: x.risk, why: typeof x.why === 'string' ? x.why.trim() : '' });
    }
    for (const id of known) if (!seen.has(id)) problems.push(`${id} is missing from the reply.`);
  } catch (e) {
    problems.push('The reply could not be read.');
  }
  return { rows, problems };
};

// Puts the data in the template in ONE pass, so no filled text is read again: a title or a sentence that holds a
// placeholder stays text, and can never pull in the page data. A `<` in the data is escaped, so no sentence can end
// the data block early. The title is HTML-escaped, because it lands in markup.
export const renderPage = (data, template) => {
  const fill = {
    TITLE: () => String(data.title ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]),
    FOCUS: () => focusTree.toString(),
    FOLD: () => fold.toString(),
    TREEKIDS: () => treeKids.toString(),
    KEYS: () => branchKeys.toString(),
    STRONG: () => strongLinks.toString(),
    MOSTUSED: () => mostUsed.toString(),
    RANKPROMPT: () => rankPrompt.toString(),
    PARSERANK: () => parseRank.toString(),
    DATA: () => JSON.stringify(data).replaceAll('<', '\\u003c'),
  };
  return template.replace(/\{\{(TITLE|FOCUS|FOLD|TREEKIDS|KEYS|STRONG|MOSTUSED|RANKPROMPT|PARSERANK|DATA)\}\}/g, (_, k) => fill[k]());
};

// ---- The command ----

// A path on another drive gives an absolute `relative`, so it is outside too.
export const insideRepo = (root, out, p = path) => {
  const rel = p.relative(root, out);
  return !rel.startsWith('..') && !p.isAbsolute(rel);
};

const git = (root, ...a) => execFileSync('git', a, { cwd: root, encoding: 'utf8', windowsHide: true }).trim();
const keyOf = (f) => path.posix.basename(f, '.md');

// Reads a file made by hand or by a script outside git: { commit, ... }. A BOM is stripped. The commit must be one of this repo's
// commits, because the page says the file read it. A hex id only, so no option can slip into git. Errors are plain, with no stack.
const readGiven = (root, what, file, subject) => {
  let given;
  try { given = JSON.parse(readFileSync(file, 'utf8').replace(/^﻿/, '')); } catch (e) { console.error(`The ${what} file ${file} cannot be read as JSON: ${e.message}`); process.exit(1); }
  if (!given || typeof given.commit !== 'string' || !given.commit) { console.error(`The ${what} file needs a "commit" string.`); process.exit(2); }
  let known = /^[0-9a-f]{7,40}$/i.test(given.commit);
  if (known) try { git(root, 'rev-parse', '--verify', '--quiet', `${given.commit}^{commit}`); } catch { known = false; }
  if (!known) { console.error(`The ${what} file names the commit "${given.commit}", and this repo has no such commit. Use the commit ${subject} read.`); process.exit(1); }
  return given;
};

// The step main() runs after it reads the repo. `checkSources` is an object keyed by check id.
export const buildPage = ({ mapFiles, traceFiles, sources, tracked, commit, config, title, rulings, checkSources, template, rank = null, usage = null }) => {
  const picture = pictureData({ mapFiles, traceFiles, sources, tracked, commit, config });
  const data = withGroups({ ...picture, title }, sources, rulings);
  // The page shows the source of each check a ruling names, and of no other.
  data.checks = Object.fromEntries([...new Set(rulings.entries.flatMap((e) => [...e.checks, ...e.holds]))].filter((id) => Object.hasOwn(checkSources, id)).sort().map((id) => [id, checkSources[id]]));
  if (rank) data.rank = rank;
  return { picture, data, page: renderPage(usage ? withUsage(data, usage) : data, template) };
};

const main = (root, out, usageFile, configFile) => {
  // The skill's own readers fill each name the host left unbound.
  const own = { ...check, repoMapConfig: ownRepoMapConfig, validateMapConfig: ownValidateMapConfig, aiCallRows: () => [] };
  for (const k of Object.keys(own)) R[k] ??= own[k];
  const config = configFile ? loadMapConfig(configFile, root) : repoMapConfig();
  // Compare real paths, so a junction or symlink into the repo, or a temp folder inside the repo, is refused. This runs before any folder is made.
  const outDir = out ? path.dirname(path.resolve(out)) : os.tmpdir();
  if (insideRepo(realpathSync.native(root), realpathSync.native(outDir))) throw new Error('Write the page outside the repo.');
  const outPath = out ? path.resolve(out) : path.join(mkdtempSync(path.join(outDir, 'plain-english-map-')), 'map.html');
  const all = git(root, 'ls-files').split('\n').filter(Boolean);
  const tracked = new Set(all);
  const read = (f) => readFileSync(path.join(root, f), 'utf8');
  const mapFiles = {}, traceFiles = {};
  for (const f of all) {
    if (/^docs\/map\/[^/]+\.md$/.test(f)) mapFiles[keyOf(f)] = read(f);
    else if (/^docs\/map\/traces\/[^/]+\.md$/.test(f)) traceFiles[keyOf(f)] = read(f);
  }
  const sources = {};
  for (const f of all) if (/\.(ts|tsx|mjs|js|cjs)$/.test(f)) sources[f] = read(f);
  for (const f of ['index.html', 'package.json']) if (tracked.has(f)) sources[f] = read(f);
  // `--usage <file.json>`: the token layer of the AI calls tab, { commit, from, to, rows }. It lives outside git.
  let usage = null;
  if (usageFile) {
    const given = readGiven(root, 'usage', usageFile, 'the token counts');
    const day = /^\d{4}-\d{2}-\d{2}$/;
    if (!day.test(given.from) || !day.test(given.to) || !Array.isArray(given.rows) || given.rows.some((r) => !r || typeof r.step !== 'string')) {
      console.error('The usage file needs "from" and "to" dates (YYYY-MM-DD) and a "rows" list, each row with a "step".'); process.exit(2);
    }
    usage = given;
  }
  const template = readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'assets', 'page.html'), 'utf8');
  // The skill reads no decision records, so the rulings tab is empty. A host that has records builds its own page through `buildPage`.
  const { data, page } = buildPage({ mapFiles, traceFiles, sources, tracked, commit: git(root, 'rev-parse', '--short', 'HEAD'), config, title: config.title, rulings: rulingProof([]), checkSources: {}, template, usage });
  writeFileSync(outPath, page);
  const n = (k) => data[k].length;
  console.log(`${outPath}: ${page.length} bytes, ${n('areas')} areas, ${n('nodes')} nodes, ${n('links')} links, ${n('areaLinks')} areaLinks, ${n('traces')} traces`);
};

// `realpathSync` on both sides: a run through a junction or symlink to the skill folder must still match. `argv[1]` names no file when
// a script imports this module from stdin (`node -`): then `realpathSync` throws ENOENT, and the guard is false.
const isMain = () => {
  try { return !!process.argv[1] && realpathSync(fileURLToPath(import.meta.url)) === realpathSync(path.resolve(process.argv[1])); } catch (e) { if (e.code === 'ENOENT') return false; throw e; }
};
if (isMain()) {
  const args = process.argv.slice(2), opt = (name) => { const at = args.indexOf(name); return at >= 0 ? [args.splice(at, 2)[1] ?? null] : []; };
  const [usageFile] = opt('--usage'), [configFile] = opt('--config');
  if (usageFile === null || configFile === null || args.length > 1) { console.error('Use: node <skill>/scripts/map-picture.mjs [<out.html>] [--usage <file.json>] [--config <map.config.json>]'); process.exit(2); }
  main(process.cwd(), args[0], usageFile, configFile);
}

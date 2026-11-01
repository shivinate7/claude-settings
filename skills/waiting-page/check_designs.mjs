// Checks the design pictures of one waiting-page item the way the page itself will draw them.
//   node check_designs.mjs --page <published page file> --item <item json file>
// Rule page-item-design (decision page-item-checked-at-write): hooks/guard.py runs this at the write of an item.
// It loads the page file in headless Chromium with a stub database that holds only the item, then asks the
// page's own code: pictureProblem(item) for the sentence the page shows, and the drawn height of each option
// card picture (`.opic .dfitwrap`, at 390 px wide) against the page's own MIN_PIC. Nothing of the page's
// rules is copied here, so the page and this check cannot disagree.
// Prints one JSON line {"problem": string|null}. Exit 0 pass, 1 miss, 3 unknown (no Playwright or
// Chromium, an unreadable file, a run past its time cap). A missing mockup slug passes: the page warns in its frame.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const CAP_MS = 20_000; // under the 60 s timeout of the guard hook that runs this
const ORIGIN = "http://waiting.test/";
const WIDTH = 390; // a phone: the width where a wide mockup scales to a strip
const unknown = (why) => { process.stderr.write("check_designs: unknown: " + why + "\n"); process.exit(3); };

const argOf = (name) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : undefined; };
const pageFile = argOf("--page"), itemFile = argOf("--item");
if (!pageFile || !itemFile) unknown("usage: check_designs.mjs --page <file> --item <json file>");

let html, item;
try { html = fs.readFileSync(pageFile, "utf8"); } catch (e) { unknown("cannot read the page: " + (e.code || e.message)); }
try {
  item = JSON.parse(fs.readFileSync(itemFile, "utf8"));
  if (!item || typeof item !== "object" || Array.isArray(item)) throw new Error("not an object");
} catch (e) { unknown("cannot read the item: " + (e.code || e.message)); }

// Playwright from this folder's reach, then from each NODE_PATH folder: a bare `import` ignores NODE_PATH, require does not.
function loadPlaywright() {
  const roots = [import.meta.url, ...(process.env.NODE_PATH || "").split(path.delimiter).filter(Boolean)
    .map((dir) => path.join(path.resolve(dir), "noop.js"))];
  for (const root of roots) {
    for (const name of ["playwright", "playwright-core"]) {
      try { return createRequire(root)(name); } catch { /* try the next */ }
    }
  }
  return null;
}
const playwright = loadPlaywright();
if (!playwright) unknown("playwright is not installed here");

// The page reads its database through window.claude.use("db"). This stub holds the one item and no other collection.
function stubDb(doc) {
  const docs = { items: { [doc.id]: doc } };
  const snap = (name) => ({ docs: Object.entries(docs[name] || {}).map(([id, v]) => ({ id, data: () => v })) });
  const coll = (name) => ({
    onSnapshot: (cb) => { setTimeout(() => cb(snap(name)), 0); return () => {}; },
    orderBy: () => coll(name),
    doc: (id) => ({
      get: async () => ({ exists: !!(docs[name] || {})[id], data: () => (docs[name] || {})[id] || null }),
      onSnapshot: (cb) => { setTimeout(() => cb({ exists: false, data: () => null }), 0); return () => {}; },
    }),
  });
  window.__dfit = 0; // each mockup frame reports its height once it has loaded; the page's own listener then fits it
  addEventListener("message", (e) => { if (e.data && e.data.dfit) window.__dfit++; });
  window.claude = { use: async (cap) => (cap === "db" ? { collection: coll, doc: (p) => coll(p.split("/")[0]).doc(p.split("/")[1]) } : null) };
}

// Runs inside the page: the page's pictureProblem, then the drawn height of each option picture whose mockup exists.
const judge = (it) => {
  const problem = pictureProblem(it);
  const pics = [];
  for (const o of it.options || []) {
    const d = optionDesigns(it, o)[0];
    if (!d || DESIGN_HTML[d.slug] == null) continue; // no picture, or a missing mockup the page warns about
    pics.push({ letter: letterOf(it, o.key), sel: 'label.opt[for="o-' + it.id + "-" + o.key + '"] .opic .dfitwrap' });
  }
  return { problem, pics, min: MIN_PIC };
};

let browser;
const finish = async (code, line) => {
  try { if (browser) await browser.close(); } catch { /* the run is over */ }
  if (line) process.stdout.write(JSON.stringify(line) + "\n");
  process.exit(code);
};
const timer = setTimeout(() => { process.stderr.write("check_designs: unknown: no answer in " + CAP_MS / 1000 + " s\n"); finish(3); }, CAP_MS);
timer.unref?.();

try {
  if (!item.id) item.id = "item";
  browser = await playwright.chromium.launch();
  const page = await browser.newPage({ viewport: { width: WIDTH, height: 900 } });
  await page.route("**/*", (r) => (r.request().url() === ORIGIN ? r.fulfill({ contentType: "text/html; charset=utf-8", body: html }) : r.abort()));
  await page.addInitScript(stubDb, item);
  await page.goto(ORIGIN);
  await page.waitForFunction("typeof pictureProblem === 'function' && typeof MIN_PIC === 'number' && state.loaded");
  const got = await page.evaluate(judge, item);
  if (got.problem) await finish(1, { problem: got.problem });
  // The picture floor reads the drawn card, which exists only when the page shows the item (an open decision).
  const shown = got.pics.length && await page.waitForSelector("#item-" + CSS_ID(item.id), { timeout: 3000 }).then(() => true, () => false);
  if (shown) {
    // Each frame posts its height once loaded; the page fits it on that message. Two frames later the card is drawn.
    await page.waitForFunction((n) => window.__dfit >= n, got.pics.length, { timeout: 5000 }).catch(() => {});
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    for (const p of got.pics) {
      const box = await page.locator(p.sel).first().boundingBox().catch(() => null);
      if (box && box.height < got.min) {
        await finish(1, { problem: "The picture of option " + p.letter + " is drawn " + Math.round(box.height) + " px tall at phone width, below the " + got.min
          + " px a picture needs, so it shows almost nothing. Its mockup is too wide for its height: set `drawn` to a narrower width, or draw the focus as a phone-shaped box." });
      }
    }
  }
  await finish(0, { problem: null });
} catch (e) {
  process.stderr.write("check_designs: unknown: " + String(e && e.message || e).split("\n")[0].slice(0, 200) + "\n");
  await finish(3);
}

// An item id as a CSS id selector part. Ids are slugs, so only a leading digit or an odd character needs escaping.
function CSS_ID(id) { return String(id).replace(/[^a-zA-Z0-9_-]/g, (c) => "\\" + c).replace(/^(\d)/, "\\3$1 "); }

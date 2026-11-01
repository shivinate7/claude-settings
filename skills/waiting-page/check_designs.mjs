// Checks the design pictures of one waiting-page item the way the page itself will draw them.
//   node check_designs.mjs --page <published page file> --item <item json file>
// Rule page-item-design (decision page-item-design): hooks/guard.py runs this at the write of an item.
// It loads the page file in headless Chromium with a stub database that holds only the item, then asks the
// page's own code: pictureProblem(item) for the sentence the page shows, and the drawn height of each option
// card picture (`.opic .dfitwrap`, at 390 px wide) against the page's own MIN_PIC. Nothing of the page's
// rules is copied here, so the page and this check cannot disagree.
// Prints one JSON line {"problem": string|null}. Exit 0 pass, 1 miss, 3 unknown (no Playwright or
// Chromium, an unreadable file, a run past its time cap). A design the page does not hold passes: the page warns in its frame.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const CAP_MS = 20_000; // under the 60 s timeout of the guard hook that runs this
const ORIGIN = "http://waiting.test/";
const WIDTH = 390; // a phone: the width where a wide design scales to a strip
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
  window.__dfit = 0; // each design frame reports its height once it has loaded; the page's own listener then fits it
  addEventListener("message", (e) => { if (e.data && e.data.dfit) window.__dfit++; });
  window.claude = { use: async (cap) => (cap === "db" ? { collection: coll, doc: (p) => coll(p.split("/")[0]).doc(p.split("/")[1]) } : null) };
}

// Runs inside the page: the page's pictureProblem, then the options whose picture the card must draw. An option with
// no design, or a design the page does not hold (it warns in the frame), has nothing to measure.
const judge = (it) => {
  const problem = pictureProblem(it);
  const pics = [];
  for (const o of it.options || []) {
    const d = optionDesigns(it, o)[0];
    if (!d || DESIGN_HTML[d.slug] == null) continue;
    pics.push({ key: o.key, letter: letterOf(it, o.key) });
  }
  return { problem, pics, min: MIN_PIC };
};

// Runs inside the page, once the frames are fitted. For each option, its picture box (`.opic .dfitwrap` of the card
// that holds the option's input, a pick-one label and a ranked div alike) read with getBoundingClientRect, and the
// scale the page gave the frame (the `a` of its transform). null when the card or the box is absent.
const measure = ({ id, pics }) => pics.map((p) => {
  const input = document.getElementById("o-" + id + "-" + p.key);
  const wrap = input && input.parentElement.querySelector(":scope > .opic .dfitwrap");
  const frame = wrap && wrap.querySelector("iframe");
  if (!wrap || !frame) return null;
  const box = wrap.getBoundingClientRect();
  return { h: box.height, w: box.width, scale: new DOMMatrix(getComputedStyle(frame).transform).a };
});

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
  if (got.pics.length) {
    // The floor reads the drawn card, which exists only when the page shows the item. No card is unknown, never a pass.
    await page.waitForFunction((id) => !!document.getElementById("item-" + id), item.id, { timeout: 3000 })
      .catch(() => unknownAfter("the page draws no card for this item, so its pictures cannot be measured"));
    // Each frame posts its height once loaded, and the page fits it on that message. Two frames later the card is drawn.
    await page.waitForFunction(() => window.__dfit >= document.querySelectorAll(".opic iframe").length, null, { timeout: 5000 })
      .catch(() => unknownAfter("the pictures did not finish loading"));
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const drawn = await page.evaluate(measure, { id: item.id, pics: got.pics });
    for (let i = 0; i < got.pics.length; i++) {
      const m = drawn[i];
      if (!m) await unknownAfter("option " + got.pics[i].letter + " has a design but the card holds no picture box");
      // MIN_PIC is the page's width floor for a picture it shrinks. It is read here as a height floor, for a shrunk picture only:
      // a picture drawn at its natural size (scale 1) is as its design made it, however small.
      if (m.scale < 0.999 && m.h < got.min) {
        await finish(1, { problem: "The picture of option " + got.pics[i].letter + " is drawn " + Math.round(m.h) + " px tall at phone width, below the " + got.min
          + " px a shrunk picture needs, so it shows almost nothing. Its design is too wide for its height: set `drawn` to a narrower width, or draw the focus as a phone-shaped box." });
      }
    }
  }
  await finish(0, { problem: null });
} catch (e) {
  process.stderr.write("check_designs: unknown: " + String(e && e.message || e).split("\n")[0].slice(0, 200) + "\n");
  await finish(3);
}

// An unknown read inside the run: say why, close the browser, exit 3.
async function unknownAfter(why) {
  process.stderr.write("check_designs: unknown: " + why + "\n");
  await finish(3);
}

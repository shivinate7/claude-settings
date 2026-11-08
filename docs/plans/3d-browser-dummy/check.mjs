// Check for the 3D browser dummy page (docs/plans/3d-browser-dummy/page.html).
// Run: verdict node docs/plans/3d-browser-dummy/check.mjs   (SHOTS_DIR sets where screenshots go; default is the OS temp folder)
// Headless Chromium draws WebGL with SwiftShader. The page needs network access to cdnjs.cloudflare.com and cdn.jsdelivr.net.
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import { mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const here = path.dirname(fileURLToPath(import.meta.url));
const url = pathToFileURL(path.join(here, "page.html")).href;
const shots = process.env.SHOTS_DIR || path.join(tmpdir(), "3d-dummy-shots");
mkdirSync(shots, { recursive: true });

const SIZES = [{ name: "390x844", width: 390, height: 844 }, { name: "1440x900", width: 1440, height: 900 }];
const SCHEMES = ["light", "dark"];
const failures = [];
let passed = 0;
const ok = (cond, label, extra = "") => { if (cond) passed++; else failures.push(`${label}${extra ? ": " + extra : ""}`); };

// Draw once and read the canvas back in the same task, so the buffer is still valid. Returns a pixel summary.
const sampleCanvas = () => {
  const api = window.__cockpit3d;
  api.render();
  const c = api.canvas, tmp = document.createElement("canvas");
  tmp.width = c.width; tmp.height = c.height;
  const cx = tmp.getContext("2d", { willReadFrequently: true });
  cx.drawImage(c, 0, 0);
  const bg = cx.getImageData(2, 2, 1, 1).data;
  const seen = new Set();
  let differs = 0, total = 0;
  for (let gy = 0; gy < 30; gy++) for (let gx = 0; gx < 40; gx++) {
    const d = cx.getImageData(Math.floor(((gx + 0.5) / 40) * c.width), Math.floor(((gy + 0.5) / 30) * c.height), 1, 1).data;
    seen.add(`${d[0] >> 3},${d[1] >> 3},${d[2] >> 3}`); total++;
    if (Math.abs(d[0] - bg[0]) + Math.abs(d[1] - bg[1]) + Math.abs(d[2] - bg[2]) > 24) differs++;
  }
  return { w: c.width, h: c.height, colours: seen.size, differs: differs / total, bg: [bg[0], bg[1], bg[2]], calls: api.info.render.calls, triangles: api.info.render.triangles };
};

const browser = await chromium.launch();
const bgBy = {};
try {
  for (const size of SIZES) for (const scheme of SCHEMES) {
    const tag = `${size.name} ${scheme}`;
    const ctx = await browser.newContext({ viewport: { width: size.width, height: size.height }, colorScheme: scheme, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    const errs = [];
    page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });
    page.on("pageerror", (e) => errs.push(String(e)));
    page.on("requestfailed", (r) => errs.push("request failed: " + r.url()));
    await page.goto(url, { waitUntil: "load" });
    await page.waitForFunction(() => document.documentElement.dataset.ready === "1" || document.documentElement.dataset.nogl === "1", null, { timeout: 60000 });

    ok(await page.evaluate(() => !document.documentElement.dataset.nogl), `${tag}: 3D drew (no fallback)`);
    ok((await page.locator("#scene canvas").count()) === 1, `${tag}: one WebGL canvas in the scene`);

    const s = await page.evaluate(sampleCanvas);
    ok(s.w > 0 && s.h > 0, `${tag}: canvas has size`, `${s.w}x${s.h}`);
    ok(s.colours >= 6 && s.differs > 0.03, `${tag}: canvas is not blank`, `${s.colours} colours, ${(s.differs * 100).toFixed(1)}% differ from the ground`);
    ok(s.calls > 0 && s.triangles > 0, `${tag}: draw calls above zero`, `calls=${s.calls} triangles=${s.triangles}`);
    bgBy[tag] = s.bg;

    const sw = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth }));
    ok(sw.sw <= sw.iw, `${tag}: no horizontal scroll`, `scrollWidth ${sw.sw} > innerWidth ${sw.iw}`);
    ok((await page.locator(".row").count()) === 44, `${tag}: plain list holds 20 items and 24 steps`);
    await page.screenshot({ path: path.join(shots, `${size.name}-${scheme}-overview.png`) });

    // A click on an item object opens the detail with its title.
    const ids = await page.evaluate(() => window.__cockpit3d.ids());
    const target = "i277";
    ok(ids.includes(target), `${tag}: item ${target} is in the scene`);
    await page.locator("#scene").scrollIntoViewIfNeeded();
    const pos = await page.evaluate((id) => window.__cockpit3d.screenPos(id), target);
    await page.mouse.click(pos.x, pos.y);
    const want = "Which page should the first 3D test copy port: this Cockpit page, or another one?";
    ok((await page.locator(".detail .title").innerText()) === want, `${tag}: click on item object opens its detail`, await page.locator(".detail .title").innerText());
    ok((await page.locator(".detail .pick").count()) === 1, `${tag}: detail shows the owner's pick`);
    ok((await page.locator('.row[data-id="i277"]').getAttribute("aria-pressed")) === "true", `${tag}: list row follows the pick`);
    await page.screenshot({ path: path.join(shots, `${size.name}-${scheme}-picked.png`) });

    // A click on a roadmap tile, after the Roadmap view refits the camera.
    await page.click('[data-view="roadmap"]');
    await page.evaluate(() => window.__cockpit3d.render());
    await page.locator("#scene").scrollIntoViewIfNeeded();
    const sp = await page.evaluate(() => window.__cockpit3d.screenPos("s:roadmap-one-writer"));
    await page.mouse.click(sp.x, sp.y);
    ok((await page.locator(".detail .title").innerText()) === "Only triage pushes to the roadmap branch", `${tag}: click on roadmap tile opens its detail`);
    await page.screenshot({ path: path.join(shots, `${size.name}-${scheme}-roadmap.png`) });

    // Keyboard: the focused scene moves the pick.
    await page.click('[data-view="all"]');
    await page.focus("#scene");
    await page.keyboard.press("Home");
    ok((await page.locator('.row[data-id="i276"]').getAttribute("aria-pressed")) === "true", `${tag}: Home picks the first object`);
    await page.keyboard.press("ArrowRight");
    ok((await page.locator('.row[data-id="i275"]').getAttribute("aria-pressed")) === "true", `${tag}: ArrowRight picks the next object`);
    await page.keyboard.press("Escape");
    ok((await page.locator(".detail .title").innerText()) === "Nothing picked", `${tag}: Esc clears the pick`);

    // On a phone the Items view fits only the items, so End (a roadmap step) is off the scene: no label may point at nothing.
    if (size.width <= 960) {
      await page.click('[data-view="items"]');
      await page.focus("#scene");
      await page.keyboard.press("End");
      await page.evaluate(() => window.__cockpit3d.render());
      ok(await page.locator("#scene .lb.sel").isHidden(), `${tag}: no pick label for an object off the scene`);
      await page.keyboard.press("Escape");
    }
    ok(errs.length === 0, `${tag}: no console errors`, errs.join(" | "));

    // Once per size, in light: a theme change redraws, the lost scene recovers, and no WebGL leaves the list working.
    if (scheme === "light") {
      const before = bgBy[`${size.name} light`];
      await page.emulateMedia({ colorScheme: "dark" });
      await page.waitForTimeout(300);
      const after = (await page.evaluate(sampleCanvas)).bg;
      ok(after[0] < before[0] - 100, `${tag}: live switch to dark repaints the scene`, `ground ${before} -> ${after}`);
      await page.emulateMedia({ colorScheme: "light" });

      await page.evaluate(() => window.__cockpit3d.loseContext());
      await page.waitForSelector('.notice[role="alert"]', { timeout: 10000 });
      ok(true, `${tag}: lost scene shows its notice`);
      ok(await page.locator("#scene .labels").isHidden(), `${tag}: lost scene hides the label pills, so none prints over the notice`);
      await page.click('[data-act="restore"]');
      await page.waitForSelector('.notice[role="alert"]', { state: "detached", timeout: 10000 });
      const again = await page.evaluate(sampleCanvas);
      ok(again.calls > 0 && again.differs > 0.03, `${tag}: "Draw it again" restores the scene`, `calls=${again.calls}`);
      ok(errs.length === 0, `${tag}: no console errors after context loss`, errs.join(" | "));

      // Forced colours: the scene keeps the page's own token colours (the ground stays light) and does not draw black.
      const fctx = await browser.newContext({ viewport: { width: size.width, height: size.height }, colorScheme: "light", forcedColors: "active", deviceScaleFactor: 1 });
      const fp = await fctx.newPage();
      const ferrs = [];
      fp.on("pageerror", (e) => ferrs.push(String(e)));
      await fp.goto(url, { waitUntil: "load" });
      await fp.waitForFunction(() => document.documentElement.dataset.ready === "1", null, { timeout: 60000 });
      const fs = await fp.evaluate(sampleCanvas);
      ok(fs.bg[0] > 200 && fs.colours >= 6 && fs.differs > 0.03, `${tag}: forced colours, the scene keeps its token colours`, `ground ${fs.bg}, ${fs.colours} colours, ${(fs.differs * 100).toFixed(1)}% differ`);
      await fp.screenshot({ path: path.join(shots, `${size.name}-forced-colours.png`) });
      ok(ferrs.length === 0, `${tag}: forced colours, no script errors`, ferrs.join(" | "));
      await fctx.close();

      const ngl = await ctx.newPage();
      const nerrs = [];
      ngl.on("pageerror", (e) => nerrs.push(String(e)));
      await ngl.addInitScript(() => {
        const g = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function (t, ...a) { return /webgl/.test(t) ? null : g.call(this, t, ...a); };
      });
      await ngl.goto(url, { waitUntil: "load" });
      await ngl.waitForFunction(() => document.documentElement.dataset.nogl === "1", null, { timeout: 60000 });
      ok((await ngl.locator("#scene.nogl").count()) === 1 && (await ngl.locator("#scene canvas").count()) === 0, `${tag}: no WebGL shows the notice in place of the scene`);
      ok(await ngl.locator(".bar3").isHidden() && await ngl.locator(".legend").isHidden(), `${tag}: no WebGL hides the view switch and the legend`);
      await ngl.click('.row[data-id="i273"]');
      ok((await ngl.locator(".detail .title").innerText()).startsWith("Test whether sessions"), `${tag}: no WebGL, a list row opens the detail`);
      ok((await ngl.evaluate(() => document.documentElement.scrollWidth <= innerWidth)), `${tag}: no WebGL, no horizontal scroll`);
      ok(nerrs.length === 0, `${tag}: no WebGL, no script errors`, nerrs.join(" | "));
      await ngl.screenshot({ path: path.join(shots, `${size.name}-nowebgl.png`) });
      await ngl.close();
    }
    await ctx.close();
  }
  // The dark ground is darker than the light ground at both sizes.
  for (const size of SIZES) ok(bgBy[`${size.name} dark`][0] < bgBy[`${size.name} light`][0] - 100, `${size.name}: dark ground differs from light ground`);
} finally {
  await browser.close();
}

if (failures.length) {
  console.log(`FAIL: ${failures.length} failed, ${passed} passed`);
  failures.forEach((f) => console.log("  - " + f));
  process.exit(1);
}
console.log(`PASS: ${passed} checks passed. Screenshots in ${shots}`);

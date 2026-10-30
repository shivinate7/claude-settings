// Fixture suite for bin/shoot (decision shoot-is-one-shared-command).
//   node --test lint/test_shoot.mjs
// A local static server on a free port stands in for an app. A stub xcrun on PATH stands in for the
// simulator tool and logs every call. The pixel checks decode each PNG in the browser's own canvas,
// not with the tool's isBlank, so a defect there cannot hide here. No Playwright or no Chromium:
// skipped on a laptop, a fail in CI (testing/skip-locally-fail-in-ci.mjs).
// The route keys steps and localStorage and the config key ignoreHTTPSErrors (the reach cases) get
// their own fixture pages. Each case reads the rendered .html and the PNG, so a shot of the wrong
// screen (a loading screen, a view a click picks, a view that needs localStorage) is a red case.
// The https case builds its own self-signed certificate with openssl into the run folder: no key or
// certificate is committed. No openssl: skipped on a laptop, a fail in CI.
// Seam: SHOOT_UNDER_TEST is the script to run, for a red run against another checkout.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { createRequire } from "node:module";
import fs from "node:fs";
import http from "node:http";
import https from "node:https";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { needEnv } from "../testing/skip-locally-fail-in-ci.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SHOOT = process.env.SHOOT_UNDER_TEST || path.join(HERE, "..", "bin", "shoot");
const require = createRequire(import.meta.url);

const PAGES = {
  "/content.html": `<!doctype html><style>body{margin:0;background:#fff;color:#111;font:48px sans-serif}
    @media (prefers-color-scheme: dark){body{background:#000;color:#eee}}</style><h1>Shoot fixture</h1><p>Known content.</p><nav style="display:none"><b>Phone nav</b></nav><div style="display:contents"><i>Wrapped</i></div>`,
  "/app/prefixed.html": `<!doctype html><style>body{margin:0;background:#fff;color:#111;font:48px sans-serif}</style><h1>Under a prefix</h1>`,
  "/blank.html": `<!doctype html><style>body{margin:0;background:#fff}</style>`,
};

// The reach fixtures. A wrong screen is white and carries one known word. The right screen is black
// (body.ready) and carries another, so the PNG and the .html can each tell the two apart.
const LOOK = `body{margin:0;background:#fff;color:#111;font:48px sans-serif}body.ready{background:#000;color:#eee}`;
Object.assign(PAGES, {
  // load fires while the page says Connecting...; a timer swaps in the real content two seconds later,
  // long enough that a slow runner still shoots the loading screen when no step waits.
  "/connecting.html": `<!doctype html><style>${LOOK}</style><p id="status">Connecting...</p><main id="app"></main>
    <script>addEventListener("load", () => setTimeout(() => { document.body.className = "ready"; document.getElementById("status").remove();
      document.getElementById("app").innerHTML = "<h1 id='ready'>Fleet dashboard: 42 units online</h1>"; }, 2000));</script>`,
  // The loading element is hidden, not removed, when the content arrives.
  "/spinner.html": `<!doctype html><style>${LOOK}</style><div id="spinner">Spinner turning</div><main id="app"></main>
    <script>setTimeout(() => { document.getElementById("spinner").style.display = "none"; document.body.className = "ready";
      document.getElementById("app").textContent = "Invoices: 7 overdue"; }, 1000);</script>`,
  // A click picks the view. The view comes in a moment after the click.
  "/menu.html": `<!doctype html><style>${LOOK}</style><h1 id="home">Home screen</h1><button id="open" style="font:inherit">Open settings</button><main id="app"></main>
    <script>document.getElementById("open").onclick = () => setTimeout(() => { document.body.className = "ready"; document.getElementById("home").remove();
      document.getElementById("open").remove(); document.getElementById("app").innerHTML = "<section id='settings'>Settings view: 3 toggles</section>"; }, 300);</script>`,
  // The second button exists only after the first click: steps must run in their listed order.
  "/chain.html": `<!doctype html><style>${LOOK}</style><button id="one" style="font:inherit">One</button><main id="app"></main>
    <script>document.getElementById("one").onclick = () => { document.getElementById("app").innerHTML = "<button id='two' style='font:inherit'>Two</button>"; };
      document.getElementById("app").onclick = (e) => { if (e.target.id === "two") { document.body.className = "ready"; document.getElementById("app").innerHTML = "<h1 id='done'>Chain complete</h1>"; } };</script>`,
  // Reads two localStorage keys while the page parses: a seed that lands later is too late.
  "/ls.html": `<!doctype html><style>${LOOK}</style><h1>Stored</h1><p id="out"></p>
    <script>const show = (k) => { const v = localStorage.getItem(k); return k + "=" + (v === null ? "unset" : encodeURIComponent(v)); };
      document.getElementById("out").textContent = show("k") + " " + show("j");</script>`,
  // A cross-origin frame (localhost against 127.0.0.1) reports what its own localStorage holds.
  "/frame-host.html": `<!doctype html><style>${LOOK}</style><p id="own"></p><p id="child">child pending</p><iframe id="f" style="width:300px;height:40px"></iframe>
    <script>const v = localStorage.getItem("k"); document.getElementById("own").textContent = "top k=" + (v === null ? "unset" : v);
      addEventListener("message", (e) => { const c = document.getElementById("child"); c.textContent = "child " + e.data; c.setAttribute("data-reported", ""); });
      document.getElementById("f").src = "http://localhost:" + location.port + "/frame-child.html";</script>`,
  "/frame-child.html": `<!doctype html><script>let v = null; try { v = localStorage.getItem("k"); } catch {} parent.postMessage("k=" + (v === null ? "unset" : v), "*");</script>`,
  // State that a click writes (localStorage and a cookie), and the pages that write it on load and read it back.
  "/state-set.html": `<!doctype html><style>${LOOK}</style><button id="save" style="font:inherit">Save</button><main id="app"></main>
    <script>document.getElementById("save").onclick = () => { localStorage.setItem("k", "clicked"); document.cookie = "c=clicked; path=/";
      document.getElementById("app").innerHTML = "<p id='saved'>Saved</p>"; };</script>`,
  "/state-write.html": `<!doctype html><style>${LOOK}</style><p>Writer</p>
    <script>localStorage.setItem("k", "loaded"); document.cookie = "c=loaded; path=/";</script>`,
  "/state-read.html": `<!doctype html><style>${LOOK}</style><p id="out"></p>
    <script>const c = document.cookie.split("; ").find((x) => x.startsWith("c=")); const v = localStorage.getItem("k");
      document.getElementById("out").textContent = "k=" + (v === null ? "unset" : v) + " c=" + (c ? c.slice(2) : "unset");</script>`,
  // Seed and steps together: the click reveals a view built from the seeded value.
  "/account.html": `<!doctype html><style>${LOOK}</style><p id="seed"></p><button id="reveal" style="font:inherit">Reveal</button><main id="app"></main>
    <script>const v = localStorage.getItem("session"); document.getElementById("seed").textContent = "session=" + (v === null ? "unset" : v);
      document.getElementById("reveal").onclick = () => { document.getElementById("app").innerHTML = "<section id='view'>Account view for " + (v === null ? "nobody" : v) + "</section>"; };</script>`,
});
let server, base, tmp, browser, tls;

// test-temp-standard: one run folder per test run, `<pid>-<UUID>`, under one temp root for this repo.
// The root and the folder name match lint/_test_temp.py, so each sweep also clears the other's crashed runs.
// This suite is the only .mjs one that uses it. A second .mjs suite is the time to give it a shared home.
const TEMP_ROOT = path.join(os.tmpdir(), "claude-settings-test-temp");
const RUN_FOLDER = /^\d+-[0-9a-f]{32}$/;
const ONE_DAY_MS = 24 * 60 * 60 * 1000;

function sweepRunFolders(root, own, now = Date.now()) {
  let names;
  try { names = fs.readdirSync(root); } catch { return; }
  for (const name of names) {
    const dir = path.join(root, name);
    if (dir === own || !RUN_FOLDER.test(name)) continue;
    try { if (fs.statSync(dir).isDirectory() && now - fs.statSync(dir).mtimeMs > ONE_DAY_MS) fs.rmSync(dir, { recursive: true, force: true }); } catch { /* another run owns it */ }
  }
}

function runFolder(root = TEMP_ROOT) {
  fs.mkdirSync(root, { recursive: true });
  const own = path.join(root, `${process.pid}-${randomUUID().replaceAll("-", "")}`);
  fs.mkdirSync(own);
  sweepRunFolders(root, own);
  return own;
}

function serve(req, res) {
  if (req.url === "/slow.html") return; // never answers: the route must time out
  const body = PAGES[req.url];
  res.writeHead(body ? 200 : 404, { "content-type": "text/html", connection: "close" });
  res.end(body || "not found");
}

before(async () => {
  tmp = runFolder();
  server = http.createServer(serve);
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(async () => {
  if (browser) await browser.close();
  server.closeAllConnections();
  server.close();
  if (tls) { tls.server.closeAllConnections(); tls.server.close(); }
  fs.rmSync(tmp, { recursive: true, force: true });
});

async function chromium(t) {
  if (browser) return browser;
  browser = await needEnv(t, "chromium", async () => require("playwright").chromium.launch());
  return browser;
}

let n = 0;
// Async on purpose: the fixture server lives in this process, so a blocking spawn would starve it.
async function run(cfg, env = {}) {
  const dir = path.join(tmp, `case-${++n}`);
  fs.mkdirSync(dir);
  const file = path.join(dir, "shoot.json");
  fs.writeFileSync(file, JSON.stringify({ baseUrl: base, ...cfg }));
  const out = path.join(dir, "out");
  const started = Date.now();
  const child = spawn(process.execPath, [SHOOT, "--config", file, "--out", out], { env: { ...process.env, ...env }, timeout: 120000 });
  let text = "";
  child.stdout.on("data", (d) => (text += d));
  child.stderr.on("data", (d) => (text += d));
  const code = await new Promise((r) => child.on("close", r));
  const pngs = fs.existsSync(out) ? fs.readdirSync(out).filter((f) => f.endsWith(".png")).sort() : [];
  return { code, out: text, dir: out, pngs, ms: Date.now() - started };
}

// Mean luminance (0-255) and the count of distinct colours, read through the browser's canvas.
async function pixels(b, file) {
  const page = await b.newPage();
  try {
    const src = "data:image/png;base64," + fs.readFileSync(file).toString("base64");
    return await page.evaluate(async (s) => {
      const img = new Image();
      img.src = s;
      await img.decode();
      const c = document.createElement("canvas");
      c.width = img.width; c.height = img.height;
      const g = c.getContext("2d");
      g.drawImage(img, 0, 0);
      const d = g.getImageData(0, 0, c.width, c.height).data;
      let sum = 0;
      const seen = new Set();
      for (let i = 0; i < d.length; i += 4) { sum += (d[i] + d[i + 1] + d[i + 2]) / 3; seen.add((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]); }
      return { mean: sum / (d.length / 4), colours: seen.size, width: img.width };
    }, src);
  } finally {
    await page.close();
  }
}

const CONTENT = { routes: [{ name: "content", path: "/content.html" }], sizes: [820, 390], themes: ["light", "dark"] };

test("one PNG per route x width x theme, each at its width, with known content not blank, dark unlike light", async (t) => {
  const b = await chromium(t);
  if (!b) return;
  const r = await run(CONTENT);
  assert.equal(r.code, 0, r.out);
  assert.match(r.out, /shoot: PASS 4 shots, 0 failed, out=/);
  assert.deepEqual(r.pngs, ["content-390-dark.png", "content-390-light.png", "content-820-dark.png", "content-820-light.png"]);
  const light = await pixels(b, path.join(r.dir, "content-820-light.png"));
  const dark = await pixels(b, path.join(r.dir, "content-820-dark.png"));
  assert.equal(light.width, 820);
  assert.equal((await pixels(b, path.join(r.dir, "content-390-light.png"))).width, 390);
  assert.ok(light.colours > 2, `known content rendered ${light.colours} colour(s): blank`);
  assert.ok(light.mean > 200 && dark.mean < 55, `light mean ${light.mean}, dark mean ${dark.mean}: the theme did not apply`);
  // The rendered page beside each PNG, for lint/label_once.py.
  const htmls = fs.readdirSync(r.dir).filter((f) => f.endsWith(".html")).sort();
  assert.deepEqual(htmls, r.pngs.map((f) => f.replace(/\.png$/, ".html")));
  const html = fs.readFileSync(path.join(r.dir, "content-820-light.html"), "utf8");
  assert.match(html, /<h1>Shoot fixture<\/h1>/);
  assert.match(html, /<nav style="display:none" hidden="">/);  // an element the browser does not show is marked
  assert.doesNotMatch(html, /<h1[^>]*hidden/);
  assert.match(html, /<div style="display:contents"><i>Wrapped<\/i><\/div>/);  // a wrapper with no box is still shown
});

test("a 404 route is a fail", async (t) => {
  if (!(await chromium(t))) return;
  const r = await run({ routes: ["/content.html", "/missing.html"], sizes: [820], themes: ["light"] });
  assert.equal(r.code, 1, r.out);
  assert.match(r.out, /shoot: FAIL missing\.html-820-light: HTTP 404/);
  assert.match(r.out, /shoot: FAIL 2 shots, 1 failed/);
});

test("a blank page is a fail, not a green PNG", async (t) => {
  if (!(await chromium(t))) return;
  const r = await run({ routes: ["/blank.html"], sizes: [820], themes: ["light"] });
  assert.equal(r.code, 1, r.out);
  assert.match(r.out, /blank\.html-820-light: blank image/);
});

test("a route that times out is a fail", async (t) => {
  if (!(await chromium(t))) return;
  const r = await run({ routes: ["/slow.html"], sizes: [820], themes: ["light"], timeoutMs: 1500 });
  assert.equal(r.code, 1, r.out);
  assert.match(r.out, /shoot: FAIL slow\.html-820-light: .*Timeout/i);
});

test("a path in baseUrl is kept for a route that starts with /", async (t) => {
  if (!(await chromium(t))) return;
  const r = await run({ baseUrl: `${base}/app/`, routes: ["/prefixed.html"], sizes: [820], themes: ["light"] });
  assert.equal(r.code, 0, r.out);
  assert.deepEqual(r.pngs, ["prefixed.html-820-light.png"]);
});

test("two routes that write one file name are a config error, not an overwrite", async () => {
  const r = await run({ routes: ["/a/b", "/a_b"], sizes: [820], themes: ["light"] });
  assert.equal(r.code, 2, r.out);
  assert.match(r.out, /both write a_b-\*\.png/);
});

test("missing Playwright: one line naming it, exit 2, no install", async () => {
  const r = await run(CONTENT, { SHOOT_PLAYWRIGHT: "playwright-not-installed-shoot-test" });
  assert.equal(r.code, 2, r.out);
  const lines = r.out.trim().split("\n");
  assert.equal(lines.length, 1, r.out);
  assert.match(lines[0], /^shoot: FAIL: Playwright is missing/);
});

// The stub answers `simctl list` with the given state, writes a PNG for `simctl io ... screenshot`,
// and logs each call's arguments.
function stubXcrun(state) {
  const bin = fs.mkdtempSync(path.join(tmp, "xcrun-"));
  const log = path.join(bin, "calls.log");
  const list = JSON.stringify({ devices: { "com.apple.CoreSimulator.SimRuntime.iOS-27-0": [{ udid: "FAKE-UDID-0001", state, name: "Fake" }] } });
  fs.writeFileSync(path.join(bin, "xcrun"), `#!/bin/sh
echo "$*" >> "${log}"
case "$*" in
  "simctl list devices -j") echo '${list}' ;;
  "simctl io FAKE-UDID-0001 screenshot "*) printf 'png' > "$5" ;;
  *) exit 64 ;;
esac
`, { mode: 0o755 });
  return { env: { PATH: `${bin}${path.delimiter}${process.env.PATH}` }, log };
}

test("simulator not booted: a skip, and shoot never boots it", { skip: process.platform === "win32" && "sh stub" }, async (t) => {
  if (!(await chromium(t))) return;
  const s = stubXcrun("Shutdown");
  const r = await run({ routes: ["/content.html"], sizes: [390], themes: ["light"], simulator: "FAKE-UDID-0001" }, s.env);
  assert.equal(r.code, 0, r.out);
  assert.match(r.out, /shoot: SKIP simulator FAKE-UDID-0001: not booted/);
  assert.match(r.out, /shoot: PASS 1 shots, 0 failed, 1 skipped/);
  const calls = fs.readFileSync(s.log, "utf8");
  assert.doesNotMatch(calls, /boot/);
  assert.doesNotMatch(calls, /screenshot/);
});

test("simulator booted: one screenshot, and still no boot call", { skip: process.platform === "win32" && "sh stub" }, async (t) => {
  if (!(await chromium(t))) return;
  const s = stubXcrun("Booted");
  const r = await run({ routes: ["/content.html"], sizes: [390], themes: ["light"], simulator: "FAKE-UDID-0001" }, s.env);
  assert.equal(r.code, 0, r.out);
  assert.match(r.out, /shoot: PASS 2 shots, 0 failed, out=/);
  assert.ok(r.pngs.includes("simulator-FAKE-UDID-0001.png"), r.pngs.join(","));
  const calls = fs.readFileSync(s.log, "utf8");
  assert.doesNotMatch(calls, /\bboot\b/);
  assert.match(calls, /simctl io FAKE-UDID-0001 screenshot /);
});

// ---- Reach: route steps, route localStorage, config ignoreHTTPSErrors ----
// A shot that passes while it shows the wrong screen is a false check. Each case below reads the
// rendered text and the PNG's own pixels, so it proves the right screen, not just a non-blank one.

const ONE = { sizes: [820], themes: ["light"] };
const route = (extra) => ({ routes: [{ path: "/content.html", ...extra }], ...ONE });
// The rendered page without its script elements: the page's own source is not what a person sees, and
// the fixture scripts hold the very words the right screen shows.
const html = (r, name) => fs.readFileSync(path.join(r.dir, name + ".html"), "utf8").replace(/<script[\s\S]*?<\/script>/g, "");
const meanOf = async (b, r, name) => (await pixels(b, path.join(r.dir, name + ".png"))).mean;

test("test-temp-standard: the run folder sweeps old sibling run folders and keeps new ones", () => {
  assert.equal(path.dirname(tmp), TEMP_ROOT);
  assert.match(path.basename(tmp), RUN_FOLDER);
  const root = path.join(tmp, "sweep-root");
  const old = path.join(root, `1-${"a".repeat(32)}`), fresh = path.join(root, `2-${"b".repeat(32)}`), other = path.join(root, "not-a-run-folder");
  for (const dir of [old, fresh, other]) fs.mkdirSync(dir, { recursive: true });
  const twoDaysAgo = new Date(Date.now() - 2 * ONE_DAY_MS);
  fs.utimesSync(old, twoDaysAgo, twoDaysAgo);
  fs.utimesSync(other, twoDaysAgo, twoDaysAgo);
  const own = runFolder(root);
  assert.match(path.basename(own), RUN_FOLDER);
  assert.ok(!fs.existsSync(old), "an old sibling run folder stays");
  assert.ok(fs.existsSync(fresh), "a new sibling run folder was swept");
  assert.ok(fs.existsSync(own), "the run's own folder was swept");
  assert.ok(fs.existsSync(other), "a folder that is not named as a run folder was swept");
});

test("no steps: the shot holds the loading screen (the fixture's race is real)", async (t) => {
  if (!(await chromium(t))) return;
  const r = await run({ routes: [{ name: "connecting", path: "/connecting.html" }], ...ONE });
  assert.equal(r.code, 0, r.out);
  assert.match(html(r, "connecting-820-light"), /Connecting\.\.\./);
});

test("steps: a wait step holds the shot until the real content is there, in the .html and the PNG", async (t) => {
  const b = await chromium(t);
  if (!b) return;
  const r = await run({ routes: [{ name: "connecting", path: "/connecting.html", steps: [{ wait: "#ready" }] }], ...ONE });
  assert.equal(r.code, 0, r.out);
  const page = html(r, "connecting-820-light");
  assert.match(page, /Fleet dashboard: 42 units online/);
  assert.doesNotMatch(page, /Connecting\.\.\./);
  // The black screen is the ready one: the wait ran before the screenshot, not only before the .html.
  assert.ok((await meanOf(b, r, "connecting-820-light")) < 55, "the PNG still shows the white Connecting screen");
});

test("steps: a wait step with state hidden holds the shot until the loading element is gone", async (t) => {
  const b = await chromium(t);
  if (!b) return;
  const r = await run({ routes: [{ name: "spinner", path: "/spinner.html", steps: [{ wait: "#spinner", state: "hidden" }] }], ...ONE });
  assert.equal(r.code, 0, r.out);
  const page = html(r, "spinner-820-light");
  assert.match(page, /Invoices: 7 overdue/);
  assert.match(page, /<div id="spinner"[^>]*hidden/);
  assert.ok((await meanOf(b, r, "spinner-820-light")) < 55, "the PNG still shows the spinner screen");
});

test("steps: a click then a wait shows the view the click picks, at every width and theme", async (t) => {
  const b = await chromium(t);
  if (!b) return;
  const r = await run({ routes: [{ name: "menu", path: "/menu.html", steps: [{ click: "#open" }, { wait: "#settings", state: "visible" }] }], sizes: [820, 390], themes: ["light", "dark"] });
  assert.equal(r.code, 0, r.out);
  assert.deepEqual(r.pngs, ["menu-390-dark.png", "menu-390-light.png", "menu-820-dark.png", "menu-820-light.png"]);
  for (const png of r.pngs) {
    const name = png.replace(/\.png$/, "");
    assert.match(html(r, name), /Settings view: 3 toggles/, name);
    assert.doesNotMatch(html(r, name), /Home screen/, name);
    assert.ok((await meanOf(b, r, name)) < 55, `${name}: the PNG still shows the home screen`);
  }
});

test("steps: they run in their listed order, each after the one before", async (t) => {
  if (!(await chromium(t))) return;
  const r = await run({ routes: [{ name: "chain", path: "/chain.html", steps: [{ click: "#one" }, { click: "#two" }, { wait: "#done" }] }], ...ONE, timeoutMs: 3000 });
  assert.equal(r.code, 0, r.out);
  assert.match(html(r, "chain-820-light"), /Chain complete/);
});

for (const [label, steps] of [
  ["a wait for a selector that never appears", [{ wait: "#never-there" }]],
  ["a click on a selector that never appears", [{ click: "#never-there" }]],
  ["a hidden wait on an element that stays visible", [{ wait: "h1", state: "hidden" }]],
]) {
  test(`steps: ${label} fails the shot, never passes it`, async (t) => {
    if (!(await chromium(t))) return;
    const r = await run({ routes: [{ name: "stuck", path: "/content.html", steps }, { name: "fine", path: "/content.html" }], ...ONE, timeoutMs: 1500 });
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /^shoot: FAIL stuck-820-light: /m);
    assert.doesNotMatch(r.out, /shoot: FAIL fine-/);
    assert.match(r.out, /shoot: FAIL 2 shots, 1 failed/);
    assert.ok(r.pngs.includes("fine-820-light.png"), "the route after the failed one was not shot");
    assert.ok(r.ms < 20000, `took ${r.ms} ms: a step is bounded by timeoutMs, not by Playwright's own default`);
  });
}

test("steps: a route that answers 404 fails on the status, before any step runs", async (t) => {
  if (!(await chromium(t))) return;
  const r = await run({ routes: [{ name: "gone", path: "/missing.html", steps: [{ wait: "#never-there" }] }], ...ONE, timeoutMs: 1500 });
  assert.equal(r.code, 1, r.out);
  assert.match(r.out, /^shoot: FAIL gone-820-light: HTTP 404/m);
  assert.equal(r.out.split("\n").filter((l) => l.startsWith("shoot: FAIL gone-")).length, 1, r.out);
});

test("localStorage: a seed is there before the page's scripts run, and never reaches the next route", async (t) => {
  if (!(await chromium(t))) return;
  const r = await run({
    routes: [
      { name: "seeded-k", path: "/ls.html", localStorage: { k: "one" } },
      { name: "plain", path: "/ls.html" },
      { name: "seeded-j", path: "/ls.html", localStorage: { j: "two" } },
    ],
    sizes: [820, 390], themes: ["light"],
  });
  assert.equal(r.code, 0, r.out);
  for (const w of [820, 390]) {
    assert.match(html(r, `seeded-k-${w}-light`), /k=one j=unset/, `seeded-k at ${w}`);
    assert.match(html(r, `plain-${w}-light`), /k=unset j=unset/, `plain at ${w}: a seed leaked from the route before it`);
    assert.match(html(r, `seeded-j-${w}-light`), /k=unset j=two/, `seeded-j at ${w}: a seed leaked from an earlier route`);
  }
});

// Any route with steps or localStorage runs in its own browser context, so what a click writes
// (localStorage, a cookie) never reaches a later route, and a route with steps starts with nothing.
test("steps: what a click writes to localStorage or a cookie never reaches the next route", async (t) => {
  if (!(await chromium(t))) return;
  const r = await run({ routes: [{ name: "setter", path: "/state-set.html", steps: [{ click: "#save" }, { wait: "#saved" }] }, { name: "reader", path: "/state-read.html" }], ...ONE });
  assert.equal(r.code, 0, r.out);
  assert.match(html(r, "reader-820-light"), /k=unset c=unset/, "state written by a click leaked into the route after it");
});

test("steps: a route with steps starts with no localStorage or cookie from an earlier route", async (t) => {
  if (!(await chromium(t))) return;
  const r = await run({ routes: [{ name: "writer", path: "/state-write.html" }, { name: "reader", path: "/state-read.html", steps: [{ wait: "#out" }] }], ...ONE });
  assert.equal(r.code, 0, r.out);
  assert.match(html(r, "reader-820-light"), /k=unset c=unset/, "state from an earlier route reached a route with steps");
});

test("localStorage: a value with quotes, a backslash, a script end tag, a newline and a template literal arrives byte for byte", async (t) => {
  if (!(await chromium(t))) return;
  const value = "it's \"quoted\" \\ back</script><b>\n`${1 + 1}` é   end";
  const r = await run({ routes: [{ name: "odd", path: "/ls.html", localStorage: { k: value } }], ...ONE });
  assert.equal(r.code, 0, r.out);
  assert.ok(html(r, "odd-820-light").includes(`k=${encodeURIComponent(value)} j=unset`), html(r, "odd-820-light"));
});

test("localStorage: the seed goes to the top frame only, never to a cross-origin frame", async (t) => {
  if (!(await chromium(t))) return;
  const r = await run({ routes: [{ name: "frames", path: "/frame-host.html", localStorage: { k: "seed" }, steps: [{ wait: "#child[data-reported]" }] }], ...ONE });
  assert.equal(r.code, 0, r.out);
  assert.match(html(r, "frames-820-light"), /top k=seed/);
  assert.match(html(r, "frames-820-light"), /child k=unset/);
});

test("a route with steps and localStorage, and a config with ignoreHTTPSErrors, work together", async (t) => {
  if (!(await chromium(t))) return;
  const r = await run({ ignoreHTTPSErrors: true, routes: [{ name: "account", path: "/account.html", localStorage: { session: "alice" }, steps: [{ click: "#reveal" }, { wait: "#view" }] }], ...ONE });
  assert.equal(r.code, 0, r.out);
  assert.match(html(r, "account-820-light"), /session=alice/);
  assert.match(html(r, "account-820-light"), /Account view for alice/);
});

test("unknown keys on the config and on a route are not refused", async (t) => {
  if (!(await chromium(t))) return;
  const r = await run({ futureKey: 1, routes: [{ path: "/content.html", futureRouteKey: { a: 1 } }], ...ONE });
  assert.equal(r.code, 0, r.out);
  assert.match(r.out, /shoot: PASS 1 shots, 0 failed, out=/);
});

// A self-signed https fixture. The certificate is built here, into the run folder, and never committed.
async function httpsFixture(t) {
  if (tls) return tls;
  const pems = await needEnv(t, "openssl", async () => {
    const key = path.join(tmp, "tls-key.pem"), cert = path.join(tmp, "tls-cert.pem");
    execFileSync("openssl", ["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", cert, "-days", "1",
      "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"], { stdio: "pipe" });
    return { key: fs.readFileSync(key), cert: fs.readFileSync(cert) };
  });
  if (!pems) return null;
  const secure = https.createServer(pems, serve);
  await new Promise((r) => secure.listen(0, "127.0.0.1", r));
  tls = { server: secure, base: `https://127.0.0.1:${secure.address().port}` };
  return tls;
}

test("ignoreHTTPSErrors true: a self-signed https app is shot, in a plain, a seeded and a stepped route", async (t) => {
  if (!(await chromium(t))) return;
  const f = await httpsFixture(t);
  if (!f) return;
  const r = await run({
    baseUrl: f.base, ignoreHTTPSErrors: true,
    routes: [
      { name: "plain", path: "/content.html" },
      { name: "seeded", path: "/ls.html", localStorage: { k: "one" } },
      { name: "stepped", path: "/menu.html", steps: [{ click: "#open" }, { wait: "#settings" }] },
    ],
    ...ONE,
  });
  assert.equal(r.code, 0, r.out);
  assert.match(r.out, /shoot: PASS 3 shots, 0 failed, out=/);
  assert.match(html(r, "seeded-820-light"), /k=one j=unset/);
  assert.match(html(r, "stepped-820-light"), /Settings view: 3 toggles/);
});

for (const [label, flag] of [["absent", {}], ["false", { ignoreHTTPSErrors: false }]]) {
  test(`ignoreHTTPSErrors ${label}: a self-signed https app fails on its certificate`, async (t) => {
    if (!(await chromium(t))) return;
    const f = await httpsFixture(t);
    if (!f) return;
    const r = await run({ baseUrl: f.base, routes: ["/content.html"], ...ONE, ...flag });
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /shoot: FAIL content\.html-820-light: .*ERR_CERT/);
  });
}

// Each malformed config is refused before any browser starts: exit 2 and one `shoot: config` line that
// names the bad key. The same list is in lint/test_compliance_probes.py (a Python probe, so no shared file).
const STEPS_BAD = [
  ["steps is an object", { click: "#a" }],
  ["steps is a string", "click #a"],
  ["steps is a number", 5],
  ["steps is an empty list", []],
  ["steps is null", null],
  ["steps is an empty string", ""],
  ["steps is the number 0", 0],
  ["a click selector that is empty", [{ click: "" }]],
  ["a click selector that is blank", [{ click: " " }]],
  ["a state that is null", [{ wait: "#a", state: null }]],
  ["a step with neither click nor wait", [{}]],
  ["a step with both click and wait", [{ click: "#a", wait: "#b" }]],
  ["a step with only a state", [{ state: "hidden" }]],
  ["a click step with a state", [{ click: "#a", state: "visible" }]],
  ["a step with another key", [{ tap: "#a" }]],
  ["a step that is a string", ["#a"]],
  ["a step that is null", [null]],
  ["a step that is a number", [5]],
  ["a step that is a list", [["click", "#a"]]],
  ["a good step, then a bad one", [{ click: "#a" }, {}]],
  ["a click selector that is a number", [{ click: 5 }]],
  ["a click selector that is null", [{ click: null }]],
  ["a click selector that is true", [{ click: true }]],
  ["a wait selector that is a list", [{ wait: ["#a"] }]],
  ["a wait selector that is an object", [{ wait: { css: "#a" } }]],
  ["a state of attached", [{ wait: "#a", state: "attached" }]],
  ["a state of detached", [{ wait: "#a", state: "detached" }]],
  ["a state that is true", [{ wait: "#a", state: true }]],
];
const STORAGE_BAD = [
  ["localStorage is a string", "k=v"],
  ["localStorage is a number", 5],
  ["localStorage is true", true],
  ["localStorage is a list", ["k", "v"]],
  ["a value that is a number", { k: 1 }],
  ["a value that is null", { k: null }],
  ["a value that is true", { k: true }],
  ["a value that is an object", { k: { a: "b" } }],
  ["a value that is a list", { k: ["v"] }],
  ["a good value, then a bad one", { a: "x", b: 2 }],
];
const HTTPS_BAD = [["a string", "yes"], ["the string true", "true"], ["the number 1", 1], ["the number 0", 0], ["a list", []], ["an object", {}]];
const REFUSED = [
  ...STEPS_BAD.map(([label, v]) => [`steps: ${label}`, /step|state|click|wait/i, route({ steps: v })]),
  ...STORAGE_BAD.map(([label, v]) => [label, /localStorage/i, route({ localStorage: v })]),
  ...HTTPS_BAD.map(([label, v]) => [`ignoreHTTPSErrors is ${label}`, /ignoreHTTPSErrors/i, { ...route({}), ignoreHTTPSErrors: v }]),
];
for (const [label, key, cfg] of REFUSED) {
  test(`config refused: ${label}`, async () => {
    const r = await run(cfg);
    assert.equal(r.code, 2, r.out);
    const line = r.out.split("\n").find((l) => l.startsWith("shoot: config "));
    assert.ok(line, `no "shoot: config" line in: ${r.out}`);
    assert.match(line.replaceAll(path.dirname(r.dir), ""), key, "the line does not name the bad key");
    assert.deepEqual(r.pngs, []);
  });
}

// Fixture suite for bin/shoot (decision shoot-is-one-shared-command).
//   node --test lint/test_shoot.mjs
// A local static server on a free port stands in for an app. A stub xcrun on PATH stands in for the
// simulator tool and logs every call. The pixel checks decode each PNG in the browser's own canvas,
// not with the tool's isBlank, so a defect there cannot hide here. No Playwright or no Chromium:
// skipped on a laptop, a fail in CI (testing/skip-locally-fail-in-ci.mjs).
// Seam: SHOOT_UNDER_TEST is the script to run, for a red run against another checkout.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { needEnv } from "../testing/skip-locally-fail-in-ci.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SHOOT = process.env.SHOOT_UNDER_TEST || path.join(HERE, "..", "bin", "shoot");
const require = createRequire(import.meta.url);

const PAGES = {
  "/content.html": `<!doctype html><style>body{margin:0;background:#fff;color:#111;font:48px sans-serif}
    @media (prefers-color-scheme: dark){body{background:#000;color:#eee}}</style><h1>Shoot fixture</h1><p>Known content.</p>`,
  "/app/prefixed.html": `<!doctype html><style>body{margin:0;background:#fff;color:#111;font:48px sans-serif}</style><h1>Under a prefix</h1>`,
  "/blank.html": `<!doctype html><style>body{margin:0;background:#fff}</style>`,
};
let server, base, tmp, browser;

before(async () => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), "shoot-test-"));
  server = http.createServer((req, res) => {
    if (req.url === "/slow.html") return; // never answers: the route must time out
    const body = PAGES[req.url];
    res.writeHead(body ? 200 : 404, { "content-type": "text/html", connection: "close" });
    res.end(body || "not found");
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(async () => {
  if (browser) await browser.close();
  server.closeAllConnections();
  server.close();
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
  const child = spawn(process.execPath, [SHOOT, "--config", file, "--out", out], { env: { ...process.env, ...env }, timeout: 120000 });
  let text = "";
  child.stdout.on("data", (d) => (text += d));
  child.stderr.on("data", (d) => (text += d));
  const code = await new Promise((r) => child.on("close", r));
  const pngs = fs.existsSync(out) ? fs.readdirSync(out).filter((f) => f.endsWith(".png")).sort() : [];
  return { code, out: text, dir: out, pngs };
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

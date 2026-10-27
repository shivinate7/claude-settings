// Browser tests for the waiting page template (skill waiting-page).
//   NODE_PATH=<dir with playwright> node --test skills/waiting-page/tests/page.test.mjs
// A stub `window.claude.use("db")` stands in for the artifact database and records every write and
// delete. No Playwright or no Chromium: skipped on a laptop, a fail in CI
// (testing/skip-locally-fail-in-ci.mjs).
// Seam: PAGE_UNDER_TEST is the page to load, for a red run against another copy.
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { needEnv } from "../../../testing/skip-locally-fail-in-ci.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE = process.env.PAGE_UNDER_TEST || path.join(HERE, "..", "page.html");
const require = createRequire(import.meta.url);
const ORIGIN = "http://waiting.test/";
const DESIGN_SLOT = '<script type="application/json" id="designData">{}</script>';

const DECISION = {
  id: "pick-a-colour", n: 27, kind: "decision", status: "open", added: "2026-10-26T00:00:00Z",
  ref: "c1, a test step", title: "Pick a colour", owner: "test thread", home: "c1", context: "Which colour?",
  options: [
    { key: "a", label: "Red", how: "h", gain: "g", lose: "l" },
    { key: "b", label: "Blue", how: "h", gain: "g", lose: "l" },
  ],
  pick: "a", why: "Red is bold.",
};
const TASK = {
  id: "plug-in-the-mac", n: 28, kind: "task", status: "open", added: "2026-10-26T00:00:00Z",
  ref: "c2, a test task", title: "Plug in the Mac", owner: "test thread", home: "c2", context: "Plug it in.",
  steps: ["Find the cable", "Plug it in"], links: [], minutes: 1,
};
const mk = (id, n, over = {}) => ({ ...DECISION, id, n, title: "Question " + n, ...over });
const LONG = "A long context that runs past three lines on a phone. ".repeat(8);

// Runs in the page before its script. Collections are maps of id to data; listeners fire on change.
function stubDb({ items, rawItems, answers, failDelete, failDeleteIn, failSet, comments, meta, groups, receipts }) {
  const data = { items: { ...Object.fromEntries(items.map((i) => [i.id, i])), ...rawItems }, answers: { ...answers }, meta: meta ? { page: meta } : {}, groups: { ...groups }, receipts: { ...receipts } };
  const subs = {}, docSubs = {};
  window.__log = [];
  const snap = (name) => ({ docs: Object.entries(data[name] || {}).map(([id, v]) => ({ id, data: () => v })) });
  const dsnap = (name, id) => ({ exists: !!(data[name] || {})[id], data: () => (data[name] || {})[id] || null });
  const fire = (name, id) => {
    (subs[name] || []).forEach((cb) => cb(snap(name)));
    (docSubs[name + "/" + id] || []).forEach((cb) => cb(dsnap(name, id)));
  };
  window.__answers = () => data.answers;
  const db = {
    collection: (name) => ({
      onSnapshot: (cb) => { (subs[name] = subs[name] || []).push(cb); setTimeout(() => cb(snap(name)), 0); return () => {}; },
      doc: (id) => ({
        set: async (body) => { if (failSet) throw { code: "denied" }; window.__log.push(["set", name, id, body]); (data[name] = data[name] || {})[id] = body; setTimeout(() => fire(name, id), 0); },
        delete: async () => { if (failDelete || failDeleteIn === name) throw { code: "denied" }; window.__log.push(["delete", name, id]); delete (data[name] || {})[id]; setTimeout(() => fire(name, id), 0); },
        onSnapshot: (cb) => { (docSubs[name + "/" + id] = docSubs[name + "/" + id] || []).push(cb); setTimeout(() => cb(dsnap(name, id)), 0); return () => {}; },
      }),
    }),
  };
  // comments: null (capability absent) or { can, canThrows, failCodes, goneThreads }.
  // failCodes rejects every send; goneThreads rejects a send into those thread ids with not_found.
  window.__sent = [];
  const cm = comments && {
    canSendToClaude: async () => { if (comments.canHangs) return new Promise(() => {}); if (comments.canThrows) throw { code: "unavailable" }; return comments.can || "available"; },
    anchorFor: async (el) => ({ path: "h1", x: 0, y: 0, tag: el.tagName }),
    sendToClaude: async (target) => {
      window.__sent.push(target);
      if (comments.sendDelay) await new Promise((r) => setTimeout(r, comments.sendDelay));
      if (comments.failCode) throw { code: comments.failCode, message: "stub" };
      if (target.threadId && (comments.goneThreads || []).includes(target.threadId)) throw { code: "not_found", message: "stub" };
      return { threadId: target.threadId || "t-new-" + window.__sent.length, commentId: "c" + window.__sent.length };
    },
  };
  window.claude = { use: async (cap) => (cap === "db" ? db : cap === "comments" ? (cm || null) : null) };
}

let browser;
const html = fs.readFileSync(PAGE, "utf8");
after(async () => { if (browser) await browser.close(); });

async function open(t, { items = [DECISION, TASK], rawItems = {}, answers = {}, failDelete = false, failDeleteIn = "", failSet = false, comments = { can: "available" }, storage = {}, meta = null, groups = {}, receipts = {}, designData = null, viewport = { width: 1280, height: 900 }, scheme = "light" } = {}) {
  browser = browser || await needEnv(t, "chromium", async () => require("playwright").chromium.launch());
  if (!browser) return null;
  const page = await browser.newPage({ viewport });
  page.setDefaultTimeout(Number(process.env.WP_TIMEOUT) || 5000);
  t.after(() => page.close());
  await page.emulateMedia({ colorScheme: scheme });
  const body = designData ? html.replace(DESIGN_SLOT, `<script type="application/json" id="designData">${JSON.stringify(designData).replace(/</g, "\\u003c")}</script>`) : html;
  // The page is served from a stand-in origin, so the init script and localStorage both apply.
  // Every other request (the fonts) is refused.
  await page.route("**/*", (r) => (r.request().url() === ORIGIN ? r.fulfill({ contentType: "text/html; charset=utf-8", body }) : r.abort()));
  await page.addInitScript(stubDb, { items, rawItems, answers, failDelete, failDeleteIn, failSet, comments, meta, groups, receipts });
  await page.addInitScript((kv) => { for (const k in kv) localStorage.setItem(k, kv[k]); }, storage);
  await page.goto(ORIGIN);
  await page.waitForFunction("state.items.length > 0"); // the stub database has delivered the items
  await page.waitForSelector(`#item-${items.length ? items[0].id : Object.keys(rawItems)[0]}`);
  return page;
}
const card = (page, it) => page.locator(`#item-${it.id}`);
const answers = (page) => page.evaluate(() => window.__answers());
const choose = (page, it, key) => page.locator(`label[for="o-${it.id}-${key}"]`).click();
const takePick = (page, it) => card(page, it).getByRole("button", { name: /Take my pick/ }).click();
const addNote = async (page, it, text) => { await card(page, it).getByRole("button", { name: "Add a note" }).click(); await page.fill(`#n-${it.id}`, text); };
const send = (page) => page.click("#send");
const written = (page) => page.waitForFunction(() => window.__log.some((l) => l[0] === "set"));
const geo = (page) => page.evaluate(() => ({
  h: document.documentElement.scrollHeight,
  cards: [...document.querySelectorAll("article.card")].map((c) => { const r = c.getBoundingClientRect(); return [c.id, Math.round(r.top + scrollY), Math.round(r.height)]; }),
}));
const SAVED_A = { [DECISION.id]: { item: DECISION.id, n: 27, at: "2026-10-26T01:00:00Z", choice: "a", note: "" } };

// ---------------------------------------------------------------- the final design

test("a rule question starts blank, my pick is starred in its card, and Take my pick fills it in one tap", async (t) => {
  const page = await open(t); if (!page) return;
  assert.equal(await page.locator(`input[name="g-${DECISION.id}"]:checked`).count(), 0, "an option is preselected");
  const star = page.locator(`label[for="o-${DECISION.id}-a"] .pick`);
  assert.match(await star.textContent(), /★.*Red is bold\./s);
  assert.equal(await page.locator(`label[for="o-${DECISION.id}-b"] .pick`).count(), 0, "the star sits on a second option");
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is open with nothing answered");
  await takePick(page, DECISION);
  assert.equal(await page.isChecked(`#o-${DECISION.id}-a`), true);
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer");
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], DECISION.id);
  const a = (await answers(page))[DECISION.id];
  assert.deepEqual([a.item, a.n, a.choice, a.note], [DECISION.id, 27, "a", "accepted pick"]);
});

test("the list has three tiers read from holds and by, then Pick stands last", async (t) => {
  const items = [
    mk("calm-dec", 1), { ...TASK, id: "calm-task", n: 2 },
    mk("due-late", 3, { by: "2026-11-30T12:00:00Z" }), mk("due-soon", 4, { by: "2026-11-02T12:00:00Z" }),
    mk("hold-new", 5, { holds: "A lane waits.", added: "2026-10-26T10:00:00Z" }), mk("hold-old", 6, { holds: "A merge waits.", added: "2026-10-25T10:00:00Z" }),
    mk("stands-1", 7, { stands: true }),
  ];
  const page = await open(t, { items }); if (!page) return;
  const order = await page.evaluate(() => [...document.querySelectorAll("section.tier")].map((s) => [s.id, s.querySelector("h2").textContent.replace(/\d+$/, ""), [...s.querySelectorAll("article.card")].map((c) => c.id.slice(5))]));
  assert.deepEqual(order, [
    ["tier-holds", "Blocking", ["hold-old", "hold-new"]],
    ["tier-due", "Upcoming", ["due-soon", "due-late"]],
    ["tier-calm", "Whenever", ["calm-dec", "calm-task"]],
    ["tier-stands", "Pick stands", ["stands-1"]],
  ]);
  const wait = await card(page, items[4]).locator(".stake.holds").textContent();
  assert.match(wait, /A lane waits\./);
});

test("related items share one frame with one sentence, in the most urgent tier of any member", async (t) => {
  const items = [mk("g-calm", 1, { group: "pair" }), mk("g-hold", 2, { group: "pair", holds: "Stuck." }), mk("loner", 3)];
  const page = await open(t, { items, groups: { pair: { title: "Answer these two together", why: "No. 2 lands only if No. 1 is yes." } } }); if (!page) return;
  const frame = page.locator("#tier-holds section.bundle#group-pair");
  assert.equal(await frame.locator("article.card").count(), 2, "both members sit in the one frame");
  assert.equal(await page.locator("#tier-calm #item-g-calm").count(), 0, "a member stayed in its own tier");
  const head = await frame.locator("header").first().textContent();
  assert.match(head, /Answer these two together/);
  assert.match(head, /No\. 2 lands only if No\. 1 is yes\./);
  assert.match(await card(page, items[0]).locator(".top").textContent(), /goes with No\. 2/);
});

test("a stands item sits in the last section, goes with the next Send, and a changed pick wins", async (t) => {
  const s1 = mk("stand-one", 7, { stands: true }), s2 = mk("stand-two", 8, { stands: true });
  const plain = mk("rule-q", 9);
  const page = await open(t, { items: [s1, s2, plain] }); if (!page) return;
  assert.equal(await page.locator("#tier-stands article.card").count(), 2);
  assert.equal(await page.isChecked(`#o-${s1.id}-a`), true, "a stood pick is not shown");
  assert.equal(await page.locator(`input[name="g-${plain.id}"]:checked`).count(), 0, "a rule question is preselected");
  assert.match(await page.locator("#barStatus").textContent(), /2 where my pick stands/);
  await choose(page, s2, "b");
  await send(page);
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 2);
  const a = await answers(page);
  assert.deepEqual([a[s1.id].choice, a[s1.id].note], ["a", "accepted pick"]);
  assert.deepEqual([a[s2.id].choice, a[s2.id].note], ["b", ""]);
  assert.equal(plain.id in a, false, "an unanswered rule question was sent");
});

test("a stands item outside the last section is never sent for the owner", async (t) => {
  const grouped = mk("grouped-stand", 1, { stands: true, group: "pair" }), mate = mk("mate", 2, { group: "pair" });
  const nopick = mk("no-pick", 3, { stands: true, pick: "zzz" });
  const page = await open(t, { items: [grouped, mate, nopick] }); if (!page) return;
  assert.equal(await page.locator("#tier-stands #item-grouped-stand").count(), 0);
  assert.equal(await page.locator(`input[name="g-${grouped.id}"]:checked`).count(), 0, "a grouped stands item is preselected");
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is open on picks nobody saw in the last section");
  assert.equal(await page.locator(`input[name="g-${nopick.id}"]:checked`).count(), 0, "a pick that is no option stood");
});

test("one Send writes every ready answer in the old record shape and leaves the rest open", async (t) => {
  const d1 = mk("d-one", 1), d2 = mk("d-two", 2), d3 = mk("d-three", 3), task = { ...TASK };
  const page = await open(t, { items: [d1, d2, d3, task] }); if (!page) return;
  await choose(page, d1, "b");
  await takePick(page, d2);
  await card(page, task).getByRole("button", { name: "Mark done" }).click();
  assert.equal(await page.locator("#send").textContent(), "Send 3 answers");
  await send(page);
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 3);
  const a = await answers(page);
  assert.deepEqual(Object.keys(a).sort(), ["d-one", "d-two", TASK.id]);
  assert.deepEqual([a["d-one"].item, a["d-one"].n, a["d-one"].choice, a["d-one"].note], ["d-one", 1, "b", ""]);
  assert.equal(a["d-two"].note, "accepted pick");
  assert.equal(a[TASK.id].done, true);
  assert.ok(!Number.isNaN(Date.parse(a["d-one"].at)), "at is an ISO time");
  assert.equal(await page.evaluate(() => window.__log.filter((l) => l[0] === "set").length), 3);
  assert.equal(await page.evaluate(() => window.__sent.length), 1, "one notice for the batch");
});

test("Send shows a stamp with the Chicago time, and Undo takes back exactly what it wrote", async (t) => {
  const d1 = mk("d-one", 1), d2 = mk("d-two", 2);
  const page = await open(t, { items: [d1, d2] }); if (!page) return;
  await takePick(page, d1); await choose(page, d2, "b");
  await send(page);
  await page.locator("#sent .stamp").waitFor();
  assert.match(await page.locator("#sent .stamp").textContent(), /Sent\s*\d\d:\d\d C[DS]T/);
  await page.locator("#undoBtn").click();
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 0);
  assert.equal(await page.locator("#sent").isHidden(), true);
  assert.equal(await page.isChecked(`#o-d-one-a`), true, "Undo lost the owner's pick");
  assert.equal(await page.isChecked(`#o-d-two-b`), true);
  assert.equal(await page.locator("#send").textContent(), "Send 2 answers");
});

test("Undo puts back the answer a change had replaced", async (t) => {
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  await card(page, DECISION).getByRole("button", { name: "Change" }).click();
  await choose(page, DECISION, "b");
  await send(page);
  await page.waitForFunction((id) => window.__answers()[id].choice === "b", DECISION.id);
  await page.locator("#undoBtn").click();
  await page.waitForFunction((id) => window.__answers()[id].choice === "a", DECISION.id);
});

test("the Undo button goes after 8 seconds", async (t) => {
  const page = await open(t); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#undoBtn").waitFor();
  await page.locator("#undoBtn").waitFor({ state: "detached", timeout: 9500 });
  assert.ok((await answers(page))[DECISION.id], "the answer went with the button");
});

test("a card becomes a receipt in place, with Change", async (t) => {
  const items = [mk("above", 1), mk("target", 2), mk("below", 3, { context: LONG })];
  const page = await open(t, { items }); if (!page) return;
  const before = await geo(page);
  await choose(page, items[1], "a");
  await send(page);
  await page.waitForFunction(() => !!window.__answers().target);
  const c = card(page, items[1]);
  await c.locator(".receipt").waitFor();
  assert.match(await c.locator(".receipt").textContent(), /You chose A: Red/);
  assert.deepEqual((await geo(page)).cards.map((x) => x[0]), before.cards.map((x) => x[0]), "the order changed");
  await c.getByRole("button", { name: "Change" }).click();
  assert.equal(await page.isChecked("#o-target-a"), true, "Change lost the saved pick");
  assert.equal(await c.locator(".receipt").count(), 0);
});

for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 800 }]) {
  test(`nothing moves when an answer is picked or sent, at ${viewport.width} wide`, async (t) => {
    const items = [
      mk("first", 1, { context: LONG, holds: "A lane waits." }), mk("second", 2, { context: LONG, stands: true }),
      { ...TASK, id: "a-task", n: 3 }, mk("third", 4, { context: LONG, by: "2030-01-01T00:00:00Z" }),
      mk("fourth", 5, { context: LONG, options: [...DECISION.options, { key: "c", label: "Green", how: "h", gain: "g", lose: "l" }] }),
    ];
    const page = await open(t, { items, viewport }); if (!page) return;
    const base = await geo(page);
    const same = async (what) => assert.deepEqual(await geo(page), base, "the page moved on " + what);
    await choose(page, items[0], "b"); await same("a pick");
    await choose(page, items[0], "a"); await same("a second pick");
    await takePick(page, items[3]); await same("Take my pick");
    await card(page, items[3]).getByRole("button", { name: "Clear" }).click(); await same("Clear");
    await card(page, items[4]).getByRole("button", { name: /Take my pick/ }).click();
    await choose(page, items[4], "c"); await same("a pick after Take my pick");
    await card(page, items[2]).getByRole("button", { name: "Mark done" }).click(); await same("Mark done");
    await send(page);
    await page.locator("#sent .stamp").waitFor();
    await page.evaluate(() => new Promise((r) => setTimeout(r, 600)));
    await same("Send");
  });
}

test("a saved answer from an earlier page shows as a receipt and nothing is written on load", async (t) => {
  const none = { item: TASK.id, n: 28, at: "2026-10-26T01:00:00Z", done: true, note: "plugged" };
  const page = await open(t, { answers: { ...SAVED_A, [TASK.id]: none } }); if (!page) return;
  assert.match(await card(page, DECISION).locator(".receipt").textContent(), /You chose A: Red/);
  assert.match(await card(page, TASK).locator(".receipt").textContent(), /Marked done/);
  assert.deepEqual(await page.evaluate(() => window.__log), []);
});

test("the receipt trail lights Read and Filed from receipts and shows only Saved without them", async (t) => {
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  const lit = () => card(page, DECISION).locator(".trail li.on").allTextContents();
  const first = (await lit()).map((x) => x.trim());
  assert.equal(first.length, 1);
  assert.match(first[0], /^Saved /);
  await page.close();
  const page2 = await open(t, { answers: SAVED_A, receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z", filed: "2026-10-26T03:00:00Z" } } });
  const on = (await card(page2, DECISION).locator(".trail li.on").allTextContents()).map((x) => x.trim());
  assert.equal(on.length, 3);
  assert.match(on[1], /Read by test thread/);
  assert.match(on[2], /Filed in c1/);
});

test("times are 24-hour Chicago time with the zone named", async (t) => {
  const page = await open(t, { items: [mk("timed", 1, { by: "2099-10-27T14:45:00Z" })] }); if (!page) return;
  const f = await page.evaluate(() => [fmt("2026-10-26T20:00:00-05:00"), fmt("2026-12-01T06:05:00Z"), fmt("2026-10-27T05:07:00Z", false)]);
  assert.deepEqual(f, ["Oct 26, 20:00 CDT", "Dec 1, 00:05 CST", "00:07 CDT"]);
  const text = await card(page, { id: "timed" }).textContent();
  assert.match(text, /Added Oct 25, 19:00 CDT/);
  assert.match(text, /Answer by Oct 27, 09:45 CDT/);
});

test("long context folds to three lines and opens on More context", async (t) => {
  const page = await open(t, { items: [mk("longone", 1, { context: LONG })] }); if (!page) return;
  const ctx = page.locator("#ctx-longone");
  assert.match(await ctx.getAttribute("class"), /clamp/);
  await page.getByRole("button", { name: "More context" }).click();
  assert.doesNotMatch(await ctx.getAttribute("class"), /clamp/);
});

test("A to C pick on the focused card, and Ctrl+Enter sends", async (t) => {
  const page = await open(t, { items: [DECISION] }); if (!page) return;
  await card(page, DECISION).locator(".title").click();
  await page.keyboard.press("b");
  assert.equal(await page.isChecked(`#o-${DECISION.id}-b`), true);
  await page.keyboard.press("Control+Enter");
  await page.waitForFunction((id) => !!window.__answers()[id], DECISION.id);
  assert.equal((await answers(page))[DECISION.id].choice, "b");
});

// ---------------------------------------------------------------- repo colour

const BRANDS = ["#b45f06", "#3d5af1", "#0a84ff", "#f47820", "#6f5ca6", "#27553f", "#0b5fff", "#ffffff", "#000000", "#ffff00", "#ff0000", "#00ff00", "#808080", "#4b5a6b", "#e6e6e6", "#1a1a1a", "#ff00ff", "#00ffff", "#7f7f00"];

// The contrast ratio is computed here from the WCAG formula, not by the page's own helper.
const CONTRAST = `
  const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const L = (h) => { h = h.replace("#", ""); const c = [0, 2, 4].map((i) => lin(parseInt(h.slice(i, i + 2), 16))); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
  const R = (a, b) => { const x = L(a), y = L(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };`;

test("every derived colour reaches 4.5:1 for any brand, light and dark", async (t) => {
  const page = await open(t); if (!page) return;
  const bad = await page.evaluate(`(() => {${CONTRAST}
    const hslHex = (h, s, l) => { s /= 100; l /= 100; const k = (n) => (n + h / 30) % 12, a = s * Math.min(l, 1 - l); const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1)); return "#" + [f(0), f(8), f(4)].map((v) => Math.round(v * 255).toString(16).padStart(2, "0")).join(""); };
    const brands = ${JSON.stringify(BRANDS)};
    for (let h = 0; h < 360; h += 15) for (const [s, l] of [[100, 50], [100, 25], [60, 70], [30, 50], [100, 90], [10, 10], [80, 40]]) brands.push(hslHex(h, s, l));
    const out = [];
    for (const b of brands) {
      const t = derive(b), chk = (what, fg, bg) => { const r = R(fg, bg); if (r < 4.5) out.push(b + " " + what + " " + r.toFixed(2)); };
      chk("header light", t.onL, t.hdrL); chk("header dark", t.onD, t.hdrD);
      chk("ink light", t.inkL, "#ffffff"); chk("ink dark", t.inkD, "#191e26");
      chk("button light", "#ffffff", t.inkL); chk("button dark", "#11151b", t.inkD);
      chk("ink on tint light", t.inkL, t.softL); chk("ink on tint dark", t.inkD, t.softD);
      for (const [k, soft] of [["holds", null], ["due", ["#fbefd9", "#35270f"]], ["good", ["#e0f2e7", "#15301f"]]]) {
        for (const [th, grounds] of [["l", [t.groundL, "#ffffff", t.softL]], ["d", [t.groundD, "#191e26", t.softD]]]) {
          const c = t[k + th]; for (const g of grounds.concat(soft ? [soft[th === "l" ? 0 : 1]] : [])) chk(k + " " + th + " on " + g, c, g);
        }
      }
      chk("blocking line light", t.onHoldsl, t.holdsl); chk("blocking line dark", t.onHoldsd, t.holdsd);
    }
    return out;
  })()`);
  assert.deepEqual(bad, []);
});

for (const scheme of ["light", "dark"]) {
  test(`the colours the page applies from one brand reach 4.5:1, ${scheme}`, async (t) => {
    const page = await open(t, { meta: { identity: { name: "Agent Q", mark: "Q", brand: "#f47820" } }, items: [mk("h", 1, { holds: "x", by: "2030-01-01T00:00:00Z" })], scheme }); if (!page) return;
    await page.waitForFunction(() => document.getElementById("repoName").textContent === "Agent Q");
    const bad = await page.evaluate(`(() => {${CONTRAST}
      const cs = getComputedStyle(document.documentElement), v = (n) => cs.getPropertyValue(n).trim();
      const hdr = getComputedStyle(document.querySelector("header.hdr")), card = getComputedStyle(document.querySelector("article.card")), body = getComputedStyle(document.body);
      const rgb = (c) => "#" + c.match(/\\d+/g).slice(0, 3).map((x) => (+x).toString(16).padStart(2, "0")).join("");
      const out = [], chk = (what, a, b) => { const r = R(a, b); if (r < 4.5) out.push(what + " " + r.toFixed(2)); };
      chk("header text", rgb(hdr.color), rgb(hdr.backgroundColor));
      chk("body text", rgb(body.color), rgb(body.backgroundColor));
      chk("button", v("--on-acc"), v("--acc"));
      chk("link ink on card", v("--acc"), rgb(card.backgroundColor));
      chk("blocking line", v("--on-holds"), v("--holds"));
      return out.concat(v("--hdr") ? [] : ["--hdr empty"]);
    })()`);
    assert.deepEqual(bad, []);
    assert.equal(await page.title(), "Agent Q: waiting on you");
  });
}

test("a page with no brand uses neutral defaults and draws no colour of its own", async (t) => {
  const page = await open(t, { meta: { identity: { name: "No Colour" } } }); if (!page) return;
  await page.waitForFunction(() => document.getElementById("repoName").textContent === "No Colour");
  assert.equal(await page.evaluate(() => document.documentElement.style.getPropertyValue("--r-hdr-l")), "");
  const page2 = await open(t, { meta: { identity: { name: "Bad", brand: "red; background: url(x)" } } });
  await page2.waitForFunction(() => document.getElementById("repoName").textContent === "Bad");
  assert.equal(await page2.evaluate(() => document.documentElement.style.getPropertyValue("--r-hdr-l")), "", "a brand that is no hex was used");
});

// ---------------------------------------------------------------- designs

test("a design shows in a sandboxed frame on its card, and the Designs tab pages through a sheet", async (t) => {
  const it = mk("with-design", 1, { designs: [{ slug: "s1", label: "Option a" }, { slug: "s2", label: "Option b" }] });
  const page = await open(t, { items: [it, mk("other", 2)], designData: { s1: "<p>one</p>", s2: "<p>two</p>" } }); if (!page) return;
  const f = card(page, it).locator("iframe.dframe");
  assert.equal(await f.getAttribute("sandbox"), "allow-scripts");
  assert.match(await f.getAttribute("srcdoc"), /one/);
  await page.evaluate(() => { window.__f = document.querySelector("article.card iframe.dframe"); });
  await choose(page, it, "a");
  assert.equal(await page.evaluate(() => document.querySelector("article.card iframe.dframe") === window.__f), true, "a pick reloaded the live preview");
  assert.match(await page.locator("#tabD").textContent(), /2/);
  await page.click("#tabD");
  await page.locator("#dsheet").waitFor();
  assert.equal(await page.locator("#dTitle").textContent(), "Option a");
  await page.click("#dNext");
  assert.equal(await page.locator("#dTitle").textContent(), "Option b");
  await page.click("#dNext"); await page.click("#dNext");
  assert.equal(await page.locator("#dStage iframe").count(), 2, "a frame was built twice");
  await page.click("#dClose");
  assert.equal(await page.locator("#dsheet").isHidden(), true);
});

test("a page with no designs has no Designs tab", async (t) => {
  const page = await open(t); if (!page) return;
  assert.equal(await page.locator("#tabD").isHidden(), true);
});

// ---------------------------------------------------------------- answers, notes and Clear

test("a decision offers None of these, and it needs a note before it sends", async (t) => {
  const page = await open(t); if (!page) return;
  const c = card(page, DECISION);
  await c.getByRole("button", { name: "None of these" }).click();
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is open on None of these with no note");
  await page.fill(`#n-${DECISION.id}`, "   ");
  assert.equal(await page.locator("#send").isDisabled(), true, "a blank note counts as a note");
  await page.fill(`#n-${DECISION.id}`, "Green, none of these fit");
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], DECISION.id);
  const a = (await answers(page))[DECISION.id];
  assert.equal(a.choice, "none");
  assert.equal(a.note, "Green, none of these fit");
  assert.equal(a.item, DECISION.id);
});

test("when the store refuses a write, the answer line can be copied", async (t) => {
  const page = await open(t, { failSet: true }); if (!page) return;
  await card(page, DECISION).getByRole("button", { name: "None of these" }).click();
  await page.fill(`#n-${DECISION.id}`, "Green");
  await send(page);
  await page.locator("#barStatus", { hasText: "Not saved (denied)" }).waitFor();
  await page.evaluate(() => { Object.defineProperty(navigator, "clipboard", { value: { writeText: async (s) => { window.__copied = s; } } }); });
  await page.click("#copy");
  assert.equal(await page.evaluate(() => window.__copied), "27 none of these (Green)");
});

test("Clear unselects a drafted pick that was never sent", async (t) => {
  const page = await open(t); if (!page) return;
  const c = card(page, DECISION);
  await choose(page, DECISION, "a");
  assert.equal(await page.isChecked(`#o-${DECISION.id}-a`), true);
  await c.getByRole("button", { name: "Clear" }).click();
  assert.equal(await page.isChecked(`#o-${DECISION.id}-a`), false, "the pick is still selected after Clear");
  assert.equal(await page.evaluate(() => localStorage.getItem("waiting.draft")), "{}");
  assert.deepEqual(await page.evaluate(() => window.__log), [], "Clear on a draft wrote to the database");
});

test("Clear on a changed answer deletes the saved record, so the item reads as unanswered", async (t) => {
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  const c = card(page, DECISION);
  await c.getByRole("button", { name: "Change" }).click();
  await c.getByRole("button", { name: "Clear" }).click();
  await page.waitForFunction((id) => !(id in window.__answers()), DECISION.id);
  assert.deepEqual(await page.evaluate(() => window.__log), [["delete", "answers", DECISION.id]]);
  assert.equal(await page.isChecked(`#o-${DECISION.id}-a`), false);
  assert.equal(await c.locator(".receipt").count(), 0);
});

test("Clear deletes a task's done mark too", async (t) => {
  const page = await open(t, { answers: { [TASK.id]: { item: TASK.id, n: 28, at: "2026-10-26T01:00:00Z", done: true, note: "" } } });
  if (!page) return;
  await card(page, TASK).getByRole("button", { name: "Change" }).click();
  await card(page, TASK).getByRole("button", { name: "Clear" }).click();
  await page.waitForFunction((id) => !(id in window.__answers()), TASK.id);
  assert.equal(await card(page, TASK).getByRole("button", { name: "Mark done" }).count(), 1);
});

test("Clear shows as soon as the owner types a note, and drops it", async (t) => {
  const page = await open(t); if (!page) return;
  await addNote(page, DECISION, "a thought");
  await card(page, DECISION).getByRole("button", { name: "Clear" }).click();
  assert.equal(await page.evaluate(() => localStorage.getItem("waiting.draft")), "{}");
  assert.equal(await page.locator(`#n-${DECISION.id}`).count(), 0, "the note box stayed");
});

test("a Clear the store refuses keeps the pick and says so", async (t) => {
  const page = await open(t, { answers: SAVED_A, failDelete: true }); if (!page) return;
  const c = card(page, DECISION);
  await c.getByRole("button", { name: "Change" }).click();
  await choose(page, DECISION, "b");
  await c.getByRole("button", { name: "Clear" }).click();
  await c.getByText("Not cleared (denied)", { exact: false }).waitFor();
  const draft = JSON.parse(await page.evaluate(() => localStorage.getItem("waiting.draft")));
  assert.equal(draft[DECISION.id] && draft[DECISION.id].choice, "b", "the draft went although the answer stayed");
  assert.equal(await page.isChecked(`#o-${DECISION.id}-b`), true);
  assert.ok((await answers(page))[DECISION.id], "the saved answer is gone");
});

test("a saved none note does not ride along when the owner picks an option", async (t) => {
  const page = await open(t, { answers: { [DECISION.id]: { item: DECISION.id, n: 27, at: "2026-10-26T01:00:00Z", choice: "none", note: "Green" } } });
  if (!page) return;
  const c = card(page, DECISION);
  assert.match(await c.locator(".receipt").textContent(), /Green/);
  await c.getByRole("button", { name: "Change" }).click();
  await choose(page, DECISION, "b");
  await send(page);
  await page.waitForFunction((id) => window.__answers()[id].choice === "b", DECISION.id);
  assert.equal((await answers(page))[DECISION.id].note, "");
});

// ---------------------------------------------------------------- the notice to Claude

const sent = (page) => page.evaluate(() => window.__sent);
const told = (page, text) => page.locator("#sentStatus", { hasText: text }).waitFor();

test("a send gives one notice that names the item and the choice", async (t) => {
  const page = await open(t); if (!page) return;
  await choose(page, DECISION, "a");
  await addNote(page, DECISION, "bold");
  await send(page);
  await told(page, "Claude was told");
  const s = await sent(page);
  assert.equal(s.length, 1);
  assert.match(s[0].text, /27 a \(bold\)/);
  assert.match(s[0].text, /test thread/);
  assert.ok(s[0].anchor, "the first notice starts an anchored thread");
  assert.ok((await answers(page))[DECISION.id], "the answer did not land");
  assert.equal(await page.evaluate(() => localStorage.getItem("waiting.thread")), "t-new-1");
});

test("a task send names the item as done", async (t) => {
  const page = await open(t); if (!page) return;
  await card(page, TASK).getByRole("button", { name: "Mark done" }).click();
  await send(page);
  await page.waitForFunction(() => window.__sent.length === 1);
  assert.match((await sent(page))[0].text, /28 done/);
});

test("a second send replies into the stored thread", async (t) => {
  const page = await open(t, { storage: { "waiting.thread": "t-old" } }); if (!page) return;
  await card(page, TASK).getByRole("button", { name: "Mark done" }).click();
  await send(page);
  await page.waitForFunction(() => window.__sent.length === 1);
  const s = await sent(page);
  assert.equal(s[0].threadId, "t-old");
  assert.equal(s[0].anchor, undefined);
});

test("Take my pick on two cards and one Send gives exactly one notice for the batch", async (t) => {
  const two = { ...DECISION, id: "pick-a-shape", n: 29, title: "Pick a shape" };
  const page = await open(t, { items: [DECISION, two, TASK] }); if (!page) return;
  await takePick(page, DECISION); await takePick(page, two);
  await send(page);
  await page.waitForFunction(() => window.__sent.length >= 1);
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 2);
  await page.evaluate(() => new Promise((r) => setTimeout(r, 300))); // a second send would land in this window
  const s = await sent(page);
  assert.equal(s.length, 1, "one notice per batch");
  assert.match(s[0].text, /27 a/);
  assert.match(s[0].text, /29 a/);
});

test("no_session sends nothing and the answer still lands", async (t) => {
  const page = await open(t, { comments: { can: "no_session" } }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await told(page, "No session was told");
  assert.equal((await sent(page)).length, 0);
  assert.ok((await answers(page))[DECISION.id]);
});

test("a send that rejects leaves the answer and says no session was told", async (t) => {
  const page = await open(t, { comments: { can: "available", failCode: "claude_unavailable" } }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await told(page, "No session was told");
  assert.equal((await sent(page)).length, 1, "no retry loop");
  assert.ok((await answers(page))[DECISION.id]);
});

test("a canSendToClaude that rejects counts as unavailable", async (t) => {
  const page = await open(t, { comments: { canThrows: true } }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await told(page, "No session was told");
  assert.ok((await answers(page))[DECISION.id]);
});

test("a page without the comments capability still sends", async (t) => {
  const page = await open(t, { comments: null }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await told(page, "No session was told");
  assert.ok((await answers(page))[DECISION.id]);
});

test("a not_found on the stored thread starts a new anchored thread", async (t) => {
  const page = await open(t, { comments: { can: "available", goneThreads: ["t-old"] }, storage: { "waiting.thread": "t-old" } });
  if (!page) return;
  await takePick(page, DECISION); await send(page);
  await told(page, "Claude was told");
  const s = await sent(page);
  assert.equal(s.length, 2);
  assert.equal(s[0].threadId, "t-old");
  assert.ok(s[1].anchor && s[1].anchor.tag === "H1", "the new thread anchors at the h1");
  assert.equal(await page.evaluate(() => localStorage.getItem("waiting.thread")), "t-new-2");
});

test("a long note with control characters is cut to 4 KiB, keeps Owners, and is plain", async (t) => {
  const page = await open(t); if (!page) return;
  await choose(page, DECISION, "a");
  await addNote(page, DECISION, "x\u0001y\u0007z" + "é".repeat(6000));
  await send(page);
  await page.waitForFunction(() => window.__sent.length === 1);
  const text = (await sent(page))[0].text;
  assert.ok(Buffer.byteLength(text, "utf8") <= 4096, "over 4 KiB");
  assert.match(text, /Owners: test thread/);
  assert.doesNotMatch(text, /[\u0000-\u0008\u000b-\u001f\u007f]/);
  assert.match(text, /x y z/);
});

test("canSendToClaude is asked before the answer write", async (t) => {
  const page = await open(t); if (!page) return;
  await choose(page, DECISION, "a");
  await page.evaluate(() => {
    window.__order = [];
    const real = state.comments.canSendToClaude;
    state.comments.canSendToClaude = async () => { window.__order.push("can"); return real(); };
    const col = state.db.collection;
    state.db.collection = (n) => { const x = col(n); const d = x.doc; x.doc = (id) => { const y = d(id); const set = y.set; y.set = async (b) => { window.__order.push("set"); return set(b); }; return y; }; return x; };
  });
  await send(page);
  await page.waitForFunction(() => window.__sent.length === 1);
  assert.deepEqual(await page.evaluate(() => window.__order), ["can", "set"]);
});

test("a batch of many items with long owners is cut to 4 KiB and keeps Owners", async (t) => {
  const many = Array.from({ length: 70 }, (_, i) => ({ ...DECISION, id: i ? "pick-" + i : DECISION.id, n: 100 + i, owner: ("owner" + i + " ").padEnd(120, "o") }));
  const page = await open(t, { items: many }); if (!page) return;
  await page.evaluate(() => document.querySelectorAll("button.takepick").forEach((b) => b.click()));
  await send(page);
  await page.waitForFunction(() => window.__sent.length >= 1);
  const text = (await sent(page))[0].text;
  assert.ok(Buffer.byteLength(text, "utf8") <= 4096, "over 4 KiB");
  assert.match(text, /Owners: owner0 /);
  assert.ok(text.endsWith("…"), "the cut did not run");
});

test("an owner name is capped at 80 characters", async (t) => {
  const long = { ...DECISION, owner: "q".repeat(300) };
  const page = await open(t, { items: [long] }); if (!page) return;
  await takePick(page, long); await send(page);
  await page.waitForFunction(() => window.__sent.length === 1);
  const text = (await sent(page))[0].text;
  assert.ok(text.includes("q".repeat(80)) && !text.includes("q".repeat(81)));
});

test("pressing Send again while a batch is in flight does nothing", async (t) => {
  const page = await open(t, { comments: { can: "available", sendDelay: 600 } }); if (!page) return;
  await takePick(page, DECISION);
  await send(page);
  await page.evaluate(() => { for (let i = 0; i < 3; i++) document.getElementById("send").click(); });
  await page.evaluate(() => new Promise((r) => setTimeout(r, 1500)));
  assert.equal((await sent(page)).length, 1, "a second notice went out");
  assert.equal((await page.evaluate(() => window.__log)).filter((l) => l[0] === "set").length, 1, "the batch saved twice");
});

test("a canSendToClaude that never answers does not hold the send", async (t) => {
  const page = await open(t, { comments: { canHangs: true } }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#sentStatus", { hasText: "No session was told" }).waitFor({ timeout: 8000 });
  assert.ok((await answers(page))[DECISION.id]);
  assert.equal((await sent(page)).length, 0);
});

test("Undo tells Claude the answers are withdrawn", async (t) => {
  const page = await open(t); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await told(page, "Claude was told");
  await page.locator("#undoBtn").click();
  await page.waitForFunction(() => window.__sent.length === 2);
  assert.match((await sent(page))[1].text, /Undone on the waiting page\. Owners: test thread\. Items: 27 are open again\./);
});

// ---------------------------------------------------------------- fix round 1

const jump = (page, ms) => page.evaluate((m) => { const real = Date.now; Date.now = () => real() + m; }, ms);

test("the Undo window follows the clock, not the timer ticks", async (t) => {
  const page = await open(t); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#undoBtn").waitFor();
  await jump(page, 9000); // a throttled tab: the clock moved, the timer did not
  await page.locator("#undoBtn").waitFor({ state: "detached", timeout: 2500 });
  assert.ok((await answers(page))[DECISION.id], "the answer went");
});

test("Undo deletes before the canSend wait", async (t) => {
  const page = await open(t, { comments: { canHangs: true } }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#undoBtn").waitFor({ timeout: 8000 });
  await page.locator("#undoBtn").click();
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 0, null, { timeout: 1500 }); // not held behind the 3 s wait
});

test("Undo refuses a delete once 8 seconds from the send have passed", async (t) => {
  const page = await open(t); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#undoBtn").waitFor();
  await page.evaluate(() => { const real = Date.now, b = document.getElementById("undoBtn"); Date.now = () => real() + 9000; b.click(); });
  await page.evaluate(() => new Promise((r) => setTimeout(r, 400)));
  assert.equal((await page.evaluate(() => window.__log)).filter((l) => l[0] === "delete").length, 0, "a delete ran after the window");
  assert.ok((await answers(page))[DECISION.id]);
});

test("Undo deletes the receipt of each item it reopens", async (t) => {
  const page = await open(t, { receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z" } } }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#undoBtn").click();
  await page.waitForFunction((id) => window.__log.some((l) => l[0] === "delete" && l[1] === "receipts" && l[2] === id), DECISION.id);
});

test("the faint text reaches 4.5:1 on chips and the ground, for any brand", async (t) => {
  const faint = [...html.matchAll(/--faint: (#[0-9a-f]{6})/gi)].map((m) => m[1]);
  assert.equal(faint.length, 3);
  const page = await open(t); if (!page) return;
  const bad = await page.evaluate(`(() => {${CONTRAST}
    const f = ${JSON.stringify(faint)}, out = [];
    const hslHex = (h, s, l) => { s /= 100; l /= 100; const k = (n) => (n + h / 30) % 12, a = s * Math.min(l, 1 - l); const g = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1)); return "#" + [g(0), g(8), g(4)].map((v) => Math.round(v * 255).toString(16).padStart(2, "0")).join(""); };
    const brands = ${JSON.stringify(BRANDS)};
    for (let h = 0; h < 360; h += 15) for (const [s, l] of [[100, 50], [100, 25], [60, 70], [100, 90], [80, 40]]) brands.push(hslHex(h, s, l));
    const chk = (w, a, b) => { const r = R(a, b); if (r < 4.5) out.push(w + " " + r.toFixed(2)); };
    chk("light chip", f[0], "#eef1f4"); chk("dark chip", f[1], "#222a35");
    for (const b of brands) { const t = derive(b); chk(b + " light ground", f[0], t.groundL); chk(b + " dark ground", f[1], t.groundD); chk(b + " light card", f[0], "#ffffff"); chk(b + " dark card", f[1], "#191e26"); }
    return out;
  })()`);
  assert.deepEqual(bad, []);
});

test("a sent chip in the overview carries a check mark, so it differs from ready by more than colour", async (t) => {
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  const content = await page.evaluate((id) => getComputedStyle(document.getElementById("c-" + id), "::before").content, DECISION.id);
  assert.match(content, /✓/);
});

test("an invalid added or by date shows no NaN and no Invalid", async (t) => {
  const page = await open(t, { items: [mk("badtime", 1, { added: "garbage", by: "nope" })] }); if (!page) return;
  const text = await page.locator("body").innerText();
  assert.doesNotMatch(text, /NaN|Invalid|undefined/);
  assert.equal(await page.locator("#tier-calm #item-badtime").count(), 1, "an invalid deadline made it Upcoming");
});

test("the template declares utf-8", () => {
  assert.match(html.slice(0, 200), /<meta charset="utf-8">/i);
});

// ---------------------------------------------------------------- fix round 2

test("a failed receipt delete does not stop Undo, the page state or the notice", async (t) => {
  const page = await open(t, { receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z" } }, failDeleteIn: "receipts" }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await told(page, "Claude was told");
  await page.locator("#undoBtn").click();
  await page.waitForFunction(() => window.__sent.length === 2);
  assert.equal(await page.evaluate((id) => id in state.answers, DECISION.id), false, "the page still shows the item as sent");
  assert.equal(await card(page, DECISION).locator(".receipt").count(), 0);
});

test("a partial Undo names every item that stayed sent", async (t) => {
  const items = [mk("d-one", 1), mk("d-two", 2), mk("d-three", 3)];
  const page = await open(t, { items }); if (!page) return;
  for (const it of items) await takePick(page, it);
  await send(page);
  await page.locator("#undoBtn").waitFor();
  await page.evaluate(() => {
    const col = state.db.collection;
    state.db.collection = (n) => { const x = col(n); const d = x.doc; x.doc = (id) => { const y = d(id); const del = y.delete; y.delete = async () => { await del(); const real = Date.now; Date.now = () => real() + 9000; }; return y; }; return x; };
    document.getElementById("undoBtn").click();
  });
  await page.locator("#barStatus", { hasText: "Too late to undo No. 1 and No. 2" }).waitFor();
});

// ---------------------------------------------------------------- the database key is the item's key

const { id: _noId, ...DECISION_NO_ID } = DECISION;
const warn = (page, key) => card(page, { id: key }).locator(".status.broken");

test("an item stored with no id field is answered under its database key", async (t) => {
  const page = await open(t, { items: [], rawItems: { k29: { ...DECISION_NO_ID, n: 29 } } }); if (!page) return;
  await choose(page, { id: "k29" }, "b");
  await send(page);
  await written(page);
  const log = await page.evaluate(() => window.__log.filter((l) => l[0] === "set"));
  assert.equal(log.length, 1);
  assert.equal(log[0][2], "k29", "the answer key");
  assert.equal(log[0][3].item, "k29");
  assert.equal(log[0][3].choice, "b");
  assert.match(await warn(page, "k29").textContent(), /no id field.*fix item 29/s);
});

test("an item whose id field differs from its key warns and is answered under the key", async (t) => {
  const page = await open(t, { items: [], rawItems: { k30: { ...DECISION, id: "other-id", n: 30 } } }); if (!page) return;
  assert.match(await warn(page, "k30").textContent(), /id field that differs.*fix item 30/s);
  await choose(page, { id: "k30" }, "a");
  await send(page);
  await written(page);
  const log = await page.evaluate(() => window.__log.filter((l) => l[0] === "set"));
  assert.deepEqual([log.length, log[0][2], log[0][3].item], [1, "k30", "k30"]);
});

test("a decision with a duplicate option key, no options, or a none key warns and Send skips it", async (t) => {
  const opt = (key) => ({ key, label: "L" + key, how: "h", gain: "g", lose: "l" });
  const rawItems = {
    "dup-keys": { ...DECISION, id: "dup-keys", n: 31, options: [opt("a"), opt("a")], pick: "a" },
    "no-opts": { ...DECISION, id: "no-opts", n: 32, options: [], pick: "a" },
    "none-key": { ...DECISION, id: "none-key", n: 33, options: [opt("none"), opt("b")], pick: "b" },
    "good": { ...DECISION, id: "good", n: 34 },
  };
  const page = await open(t, { items: [], rawItems }); if (!page) return;
  for (const k of ["dup-keys", "no-opts", "none-key"]) {
    assert.equal(await warn(page, k).count(), 1, k + " shows no warning");
    assert.match(await warn(page, k).textContent(), /cannot be answered.*fix item/s);
  }
  assert.equal(await warn(page, "good").count(), 0, "a sound item warns");
  // A staged draft on a broken item must still not go out; Send carries only the sound one.
  await page.evaluate(() => { for (const k of ["dup-keys", "none-key"]) setDraft(byId(k), { choice: "a", auto: true }); render(); });
  await takePick(page, { id: "good" });
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer");
  await send(page);
  await written(page);
  const log = await page.evaluate(() => window.__log.filter((l) => l[0] === "set").map((l) => l[2]));
  assert.deepEqual(log, ["good"]);
});

test("a bad number or kind warns and Send skips it", async (t) => {
  const rawItems = {
    "bad-n": { ...DECISION, id: "bad-n", n: "7" },
    "bad-kind": { ...TASK, id: "bad-kind", n: 8, kind: "chore" },
  };
  const page = await open(t, { items: [], rawItems }); if (!page) return;
  assert.match(await warn(page, "bad-n").textContent(), /no number/);
  assert.match(await warn(page, "bad-kind").textContent(), /neither a decision nor a task/);
  await page.evaluate(() => { setDraft(byId("bad-kind"), { done: true }); setDraft(byId("bad-n"), { choice: "a" }); render(); });
  assert.equal(await page.locator("#send").isDisabled(), true);
});

test("a blocked card says it cannot be sent, disables its controls, and Copy answers skips it", async (t) => {
  const opt = (key) => ({ key, label: "L" + key, how: "h", gain: "g", lose: "l" });
  const rawItems = {
    "dup-keys": { ...DECISION, id: "dup-keys", n: 41, options: [opt("a"), opt("a")], pick: "a" },
    "odd-opts": { ...DECISION, id: "odd-opts", n: 42, options: "a, b" },
    "good": { ...DECISION, id: "good", n: 43 },
  };
  const page = await open(t, { items: [], rawItems }); if (!page) return;
  assert.match(await warn(page, "odd-opts").textContent(), /not a list/);
  await page.evaluate(() => { setDraft(byId("dup-keys"), { choice: "a", auto: true }); render(); });
  const c = card(page, { id: "dup-keys" });
  assert.equal(await c.locator(".ready").textContent(), "This item cannot be sent.");
  assert.equal(await c.locator(".takepick").isDisabled(), true);
  assert.equal(await c.locator(".nonebtn").isDisabled(), true);
  assert.equal(await c.locator(".opts input").first().isDisabled(), true);
  await takePick(page, { id: "good" });
  assert.equal(await page.evaluate(() => answerLine()), "43 a");
});

test("an item with no id field and a duplicate option key is blocked from Send and Copy, and names the key", async (t) => {
  const opt = (key) => ({ key, label: "L" + key, how: "h", gain: "g", lose: "l" });
  const rawItems = {
    "k50": { ...DECISION_NO_ID, n: 50, options: [opt("x"), opt("x")], pick: "x" },
    "good": { ...DECISION, id: "good", n: 51 },
  };
  const page = await open(t, { items: [], rawItems }); if (!page) return;
  assert.match(await warn(page, "k50").textContent(), /share the key x/);
  await page.evaluate(() => { setDraft(byId("k50"), { choice: "x" }); render(); });
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is open for a blocked item");
  assert.equal(await page.evaluate(() => answerLine()), "");
});

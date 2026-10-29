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
        get: async () => dsnap(name, id),
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
  await page.addInitScript(() => { new MutationObserver(() => { const w = document.querySelector(".dfitwrap"); if (w && window.__firstFit === undefined) window.__firstFit = w.getBoundingClientRect().height; }).observe(document, { childList: true, subtree: true }); });
  await page.addInitScript(stubDb, { items, rawItems, answers, failDelete, failDeleteIn, failSet, comments, meta, groups, receipts });
  await page.addInitScript((kv) => { for (const k in kv) localStorage.setItem(k, kv[k]); }, storage);
  await page.goto(ORIGIN);
  await page.waitForFunction("state.items.length > 0"); // the stub database has delivered the items
  await page.waitForSelector(`#item-${items.length ? items[0].id : Object.keys(rawItems)[0]}`);
  return page;
}
const card = (page, it) => page.locator(`#item-${it.id}`);
const answers = (page) => page.evaluate(() => window.__answers());
// A tap on an option's picture opens the viewer (d9 ruling), so a pick taps the option's label text.
const choose = (page, it, key) => page.locator(`label[for="o-${it.id}-${key}"] .lab`).click();
const takePick = (page, it) => card(page, it).getByRole("button", { name: /Take my pick/ }).click();
// The keyboard way to take a pick: focus the button and press Enter. Resolves to what holds focus one frame later, so a fix that focuses in a frame still counts.
const enterTakePick = async (page, it) => {
  await page.locator(`#b-take-${it.id}`).focus();
  await page.keyboard.press("Enter");
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => r())));
  return page.evaluate(() => ({ tag: document.activeElement.tagName, id: document.activeElement.id }));
};
// After Take my pick hides, focus belongs on the input of the pick's first key, as the A to C key handler leaves it.
const assertFocusOnFirstPick = (at, it, key) => {
  assert.notEqual(at.tag, "BODY", `${it.id}: focus fell to BODY after Enter on Take my pick`);
  assert.equal(at.id, `o-${it.id}-${key}`, `${it.id}: focus is not on the first key of the pick`);
};
const addNote = async (page, it, text) => { await card(page, it).getByRole("button", { name: "Add a note" }).click(); await page.fill(`#n-${it.id}`, text); };
const send = (page) => page.click("#send");
const written = (page) => page.waitForFunction(() => window.__log.some((l) => l[0] === "set"));
const geo = (page) => page.evaluate(() => ({
  h: document.documentElement.scrollHeight,
  cards: [...document.querySelectorAll("article.card")].map((c) => { const r = c.getBoundingClientRect(); return [c.id, Math.round(r.top + scrollY), Math.round(r.height)]; }),
}));
const SAVED_A = { [DECISION.id]: { item: DECISION.id, n: 27, at: "2026-10-26T01:00:00Z", choice: "a", note: "" } };
// An option may carry design: "<slug>", and its mockup shows inside that option's card (designData holds the HTML).
const opt = (key, label, design) => ({ key, label, how: "h", gain: "g", lose: "l", ...(design ? { design } : {}) });
const DESIGNS = { s1: "<p>one</p>", s2: "<p>two</p>" };
const optFrame = (it, key) => `label.opt[for="o-${it.id}-${key}"] iframe`;

// ---------------------------------------------------------------- the final design

test("a rule question starts blank, my pick is starred in its card, and Take my pick fills it in one tap", async (t) => {
  const page = await open(t); if (!page) return;
  assert.equal(await page.locator(`input[name="g-${DECISION.id}"]:checked`).count(), 0, "an option is preselected");
  const star = page.locator(`label[for="o-${DECISION.id}-a"] .pick`);
  assert.match(await star.textContent(), /Red is bold\./);
  assert.equal(await star.locator("svg").count(), 1, "the pick box holds no inline sparkle icon");
  assert.doesNotMatch(await star.textContent(), /[★⭐]/, "the pick box still holds a star character");
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

for (const withDesigns of [false, true]) for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 800 }]) {
  test(`nothing moves when an answer is picked or sent, at ${viewport.width} wide${withDesigns ? ", with option designs" : ""}`, async (t) => {
    const items = [
      mk("first", 1, { context: LONG, holds: "A lane waits.", options: [opt("a", "Red", withDesigns ? "s1" : undefined), opt("b", "Blue with a long label that cannot fit on one line of the ready note at 390 wide", withDesigns ? "s2" : undefined)] }), mk("second", 2, { context: LONG, stands: true }),
      { ...TASK, id: "a-task", n: 3 }, mk("third", 4, { context: LONG, by: "2030-01-01T00:00:00Z" }),
      mk("fourth", 5, { context: LONG, options: [...DECISION.options, { key: "c", label: "Green", how: "h", gain: "g", lose: "l" }] }),
    ];
    const page = await open(t, { items, viewport, designData: withDesigns ? DESIGNS : null }); if (!page) return;
    await noAnchor(page);
    // With option designs, the in-card frames must be the same DOM nodes after each pick, so none reloads.
    let sent = false;
    if (withDesigns) {
      assert.equal(await page.locator("#item-first iframe").count(), 2, "the option designs have no frames in their cards");
      await page.evaluate(() => { window.__of = [...document.querySelectorAll("#item-first iframe")]; });
    }
    const base = await geo(page);
    const same = async (what) => {
      assert.deepEqual(await geo(page), base, "the page moved on " + what);
      if (withDesigns && !sent) assert.equal(await page.evaluate(() => { const now = [...document.querySelectorAll("#item-first iframe")]; return now.length === window.__of.length && now.every((f, n) => f === window.__of[n]); }), true, "an in-card frame was rebuilt on " + what);
    };
    await choose(page, items[0], "b"); await same("a pick");
    await choose(page, items[0], "a"); await same("a second pick");
    await takePick(page, items[3]); await same("Take my pick");
    await choose(page, items[3], "a"); await same("a click on the selected pick");
    await card(page, items[4]).getByRole("button", { name: /Take my pick/ }).click();
    await choose(page, items[4], "c"); await same("a pick after Take my pick");
    await card(page, items[2]).getByRole("button", { name: "Mark done" }).click(); await same("Mark done");
    sent = true;
    // A receipt holds its height only while in view (owner report 1, Oct 28 13:19 CDT, c193), so after Send only what is on screen is compared.
    const onScreen = () => page.evaluate(() => [...document.querySelectorAll("article.card")].map((c) => [c.id, c.getBoundingClientRect()]).filter(([, r]) => r.bottom > 0 && r.top < innerHeight).map(([id, r]) => [id, Math.round(r.top), Math.round(r.height)]));
    const seen = await onScreen();
    await send(page);
    await page.locator("#sent .stamp").waitFor();
    await page.evaluate(() => new Promise((r) => setTimeout(r, 600)));
    const after = (await onScreen()).slice(0, seen.length); // scroll lands on whole pixels, so a fraction of one is allowed
    assert.deepEqual(after.map((r) => r[0]), seen.map((r) => r[0]), "the cards on screen changed on Send");
    seen.forEach((r, i) => { assert.ok(Math.abs(after[i][1] - r[1]) <= 1 && Math.abs(after[i][2] - r[2]) <= 1, "what was on screen moved on Send: " + JSON.stringify([r, after[i]])); });
  });
}

test("a saved answer from an earlier page shows as a receipt and nothing is written on load", async (t) => {
  const none = { item: TASK.id, n: 28, at: "2026-10-26T01:00:00Z", done: true, note: "plugged" };
  const page = await open(t, { answers: { ...SAVED_A, [TASK.id]: none } }); if (!page) return;
  assert.match(await card(page, DECISION).locator(".receipt").textContent(), /You chose A: Red/);
  assert.match(await card(page, TASK).locator(".receipt").textContent(), /Marked done/);
  assert.deepEqual(await page.evaluate(() => window.__log), []);
});

test("an answered card without a filing shows Answered, filing pending, never waited", async (t) => {
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  const c = card(page, DECISION);
  const ans = (await c.locator(".ans").textContent()).trim();
  assert.match(ans, /^Answered, filing pending Oct \d+, \d\d:\d\d C[DS]T$/);
  assert.doesNotMatch(await c.locator(".top").textContent(), /waited|Added/i);
  assert.equal(await c.locator(".ans.filed").count(), 0);
  assert.match(await page.locator("#c-" + DECISION.id).getAttribute("aria-label"), /answered, filing pending$/);
});

test("an answered card with receipts shows Answered, filed in the home with the filed time", async (t) => {
  const page = await open(t, { answers: SAVED_A, receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z", filed: "2026-10-26T03:00:00Z" } } }); if (!page) return;
  const c = card(page, DECISION);
  assert.match((await c.locator(".ans.filed").textContent()).trim(), /^Answered, filed in c1 Oct 25, 22:00 CDT$/);
  assert.equal(await c.locator(".trail").count(), 0);
  assert.doesNotMatch(await c.locator(".top").textContent(), /waited/i);
  assert.match(await page.locator("#c-" + DECISION.id).getAttribute("aria-label"), /answered, filed$/);
  assert.match(await page.locator("#c-" + DECISION.id).getAttribute("class"), /filed/);
});

test("a read but unfiled answer shows Read by the owner beside Change", async (t) => {
  const page = await open(t, { answers: SAVED_A, receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z" } } }); if (!page) return;
  const c = card(page, DECISION);
  assert.match(await c.locator(".receipt .read").textContent(), /^Read by test thread /);
  assert.match((await c.locator(".ans").textContent()).trim(), /^Answered, filing pending /);
});

test("a receipt older than the answer is ignored: a changed answer reads filing pending", async (t) => {
  const later = { [DECISION.id]: { ...SAVED_A[DECISION.id], at: "2026-10-26T04:00:00Z" } };
  const page = await open(t, { answers: later, receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z", filed: "2026-10-26T03:00:00Z" } } }); if (!page) return;
  const c = card(page, DECISION);
  assert.match((await c.locator(".ans").textContent()).trim(), /^Answered, filing pending /);
  assert.equal(await c.locator(".ans.filed").count(), 0);
  assert.equal(await c.locator(".receipt .read").count(), 0);
  assert.doesNotMatch(await page.locator("#c-" + DECISION.id).getAttribute("class"), /filed/);
  assert.match(await page.locator("#c-" + DECISION.id).getAttribute("aria-label"), /filing pending$/);
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

// The pick is B, not the first option, so a fix that focuses the first radio of the card fails.
test("Enter on Take my pick puts focus on the pick's input, on a pick-one card", async (t) => {
  const it = mk("take-focus", 40, { pick: "b" });
  const page = await open(t, { items: [it] }); if (!page) return;
  const at = await enterTakePick(page, it);
  assert.equal(await page.isChecked(`#o-${it.id}-b`), true, "Enter did not take the pick");
  assertFocusOnFirstPick(at, it, "b");
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

// ---------------------------------------------------------------- the repo's icon (roadmap step c132)

const svgIcon = (fill, extra = "") => "data:image/svg+xml;base64," + Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32"><rect width="32" height="32" fill="${fill}"/>${extra}</svg>`).toString("base64");
const markState = (page) => page.evaluate(() => {
  const m = document.getElementById("mark"), img = m.querySelector("img");
  return { icon: m.classList.contains("icon"), img: img ? img.getAttribute("src") : null, alt: img ? img.getAttribute("alt") : null, text: m.textContent, hidden: m.hidden, tile: m.style.getPropertyValue("--tile"), aria: m.getAttribute("aria-hidden") };
});
const named = (page, name) => page.waitForFunction((n) => document.getElementById("repoName").textContent === n, name);

test("a dark icon shows on a white tile in place of the letter, alt empty and aria-hidden kept", async (t) => {
  const icon = svgIcon("#11151b");
  const page = await open(t, { meta: { identity: { name: "Compass", brand: "#f47820", icon } } }); if (!page) return;
  await page.waitForSelector("#mark.icon img");
  const m = await markState(page);
  assert.deepEqual(m, { icon: true, img: icon, alt: "", text: "", hidden: false, tile: "#ffffff", aria: "true" });
  const box = await page.evaluate(() => { const r = document.querySelector("#mark img").getBoundingClientRect(), b = document.getElementById("mark").getBoundingClientRect(); return [r.width, r.height, b.width, b.height]; });
  assert.deepEqual(box, [22, 22, 28, 28]);
});

test("a white icon gets the dark tile", async (t) => {
  const page = await open(t, { meta: { identity: { name: "Compass", brand: "#f47820", icon: svgIcon("#ffffff") } } }); if (!page) return;
  await page.waitForSelector("#mark.icon img");
  assert.equal((await markState(page)).tile, "#11151b");
});

test("an icon that is not an inline svg or png data URI, or is too long, leaves the letter", async (t) => {
  const long = "data:image/svg+xml;base64," + "A".repeat(16385 - 26);
  assert.equal(long.length, 16385);
  for (const icon of ["data:image/png;base64,AAAA", "https://example.com/icon.svg", long, "data:image/jpeg;base64,/9j/4AAQ", 42]) {
    const page = await open(t, { meta: { identity: { name: "Compass", icon } } }); if (!page) return;
    await named(page, "Compass");
    await page.waitForTimeout(150);
    const m = await markState(page);
    assert.deepEqual([m.icon, m.img, m.text, m.hidden], [false, null, "C", false], String(icon).slice(0, 40));
    await page.close();
  }
});

test("an icon leaves the header height as it was", async (t) => {
  const height = async (identity) => {
    const page = await open(t, { meta: { identity } }); if (!page) return null;
    await named(page, "Compass");
    if (identity.icon) await page.waitForSelector("#mark.icon img");
    const h = await page.evaluate(() => document.querySelector("header.hdr").getBoundingClientRect().height);
    await page.close();
    return h;
  };
  const plain = await height({ name: "Compass" }); if (plain === null) return;
  assert.equal(await height({ name: "Compass", icon: svgIcon("#11151b") }), plain);
});

test("an icon with no name or mark still shows", async (t) => {
  const page = await open(t, { meta: { identity: { icon: svgIcon("#11151b") } } }); if (!page) return;
  await page.waitForSelector("#mark.icon img");
  assert.equal((await markState(page)).hidden, false);
});

test("a meta write with the same icon keeps it shown, with no flash of the letter", async (t) => {
  const icon = svgIcon("#11151b");
  const page = await open(t, { meta: { identity: { name: "Compass", icon } } }); if (!page) return;
  await page.waitForSelector("#mark.icon img");
  const flashed = await page.evaluate(async (icon) => {
    const m = document.getElementById("mark"); let lost = false;
    new MutationObserver(() => { if (!m.classList.contains("icon") || !m.querySelector("img")) lost = true; }).observe(m, { attributes: true, childList: true });
    state.meta = { identity: { name: "Compass", brand: "#f47820", icon } }; applyIdentity();
    await new Promise((r) => setTimeout(r, 200));
    return lost;
  }, icon);
  assert.equal(flashed, false);
  assert.equal((await markState(page)).img, icon);
});

test("a decode that finishes after a newer identity is ignored", async (t) => {
  const page = await open(t, { meta: { identity: { name: "Compass" } } }); if (!page) return;
  await named(page, "Compass");
  const slow = svgIcon("#11151b", "<!--slow-->");
  await page.evaluate((slow) => {
    const decode = HTMLImageElement.prototype.decode;
    HTMLImageElement.prototype.decode = function () { const wait = this.src === slow; return decode.call(this).then(() => wait && new Promise((r) => setTimeout(r, 400))); };
    state.meta = { identity: { name: "Compass", icon: slow } }; applyIdentity();
    state.meta = { identity: { name: "Compass" } }; applyIdentity();
  }, slow);
  await page.waitForTimeout(700);
  const m = await markState(page);
  assert.deepEqual([m.icon, m.img, m.text, m.tile], [false, null, "C", ""]);
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

// An option names its picture with `design` (a slug of the item's `designs`). A look question whose options name a
// design the item lacks shows a plain warning where the picture belongs.
const LOOK_OPTS = ["a", "b", "c"].map((k) => ({ key: k, label: "Layout " + k, how: "h", gain: "g", lose: "l", design: "price-" + k }));
const GITHUB_FOLDER = "Mockups: https://github.com/shivinate7/banchi/tree/main/docs/mockups/price-history";

test("a look question with three options, a GitHub folder link and no designs shows a warning inside each option card", async (t) => {
  const it = mk("price-history-where", 30, { context: GITHUB_FOLDER, look: true, options: LOOK_OPTS.map(({ design, ...o }) => o), pick: "a" });
  const page = await open(t, { items: [it] }); if (!page) return;
  assert.equal(await card(page, it).locator(".opt .dwarn").count(), 3, "no warning in an option card");
  assert.equal(await card(page, it).locator(".dwarn").count(), 3, "a warning sits outside the option cards");
  assert.match(await card(page, it).locator(".opt .dwarn").first().textContent(), /picture/i);
  assert.equal(await card(page, it).locator("iframe.dframe").count(), 0);
});

const PICS = { "price-a": "<p>a</p>", "price-b": "<p>b</p>", "price-c": "<p>c</p>" };
const picItem = (id, n) => mk(id, n, { options: LOOK_OPTS, pick: "a", designs: LOOK_OPTS.map((o) => ({ slug: o.design, label: o.label })) });

test("each option's picture is inside its own option card; a tap on it opens the viewer and a tap on the card picks", async (t) => {
  const it = picItem("with-pictures", 31);
  const page = await open(t, { items: [it], designData: PICS }); if (!page) return;
  assert.equal(await card(page, it).locator(".dwarn").count(), 0, "a warning shows although every picture is there");
  for (const o of LOOK_OPTS) assert.equal(await card(page, it).locator(`label.opt[for="o-${it.id}-${o.key}"] .opic iframe.dframe`).count(), 1, "no picture in option " + o.key);
  assert.equal(await card(page, it).locator(".dprev").count(), 0, "a picture named by an option also shows at the front");
  const pic = card(page, it).locator(`label.opt[for="o-${it.id}-b"] .opic`);
  assert.ok((await pic.boundingBox()).height >= 40, "the picture is smaller than a thumb");
  await pic.click();
  assert.equal(await page.isChecked(`#o-${it.id}-b`), false, "a tap on the picture picked the option");
  assert.equal(await page.locator("#dsheet").isVisible(), true, "the viewer did not open");
  await page.click("#dClose");
  await card(page, it).locator(`label.opt[for="o-${it.id}-b"] .lab`).click();
  assert.equal(await page.isChecked(`#o-${it.id}-b`), true, "a tap on the card did not pick the option");
  await card(page, it).locator(`label.opt[for="o-${it.id}-c"] .how`).click();
  assert.equal(await page.isChecked(`#o-${it.id}-c`), true, "a tap on the card's text did not pick the option");
  assert.equal(await card(page, it).locator(".opt iframe.dframe").first().evaluate((f) => getComputedStyle(f).pointerEvents), "none", "the frame swallows the click");
});

const WIDE = [["a", "Layout A"], ["b", "Layout B"]];
const viewerItem = () => mk("viewer-q", 50, {
  pick: "a", options: WIDE.map(([k, l]) => ({ key: k, label: l, how: "h", gain: "g", lose: "l", design: "v-" + k })),
  designs: [{ slug: "v-a", label: "A phone", width: "Phone" }, { slug: "v-a2", option: "a", label: "A wide", width: "Wide" },
    { slug: "v-b", label: "B phone", width: "Phone" }, { slug: "v-b2", option: "b", label: "B wide", width: "Wide" }],
});
const VIEWER_DATA = { "v-a": "<p>a</p>", "v-a2": "<p>a2</p>", "v-b": "<p>b</p>", "v-b2": "<p>b2</p>" };

test("the viewer counts options times widths, steps with Prev and Next, wraps at the ends, and offers full size", async (t) => {
  const it = viewerItem();
  const page = await open(t, { items: [it], designData: VIEWER_DATA }); if (!page) return;
  await page.evaluate(() => { window.__opened = []; window.open = (u) => { window.__opened.push(String(u)); return null; }; });
  await card(page, it).locator(`label.opt[for="o-${it.id}-a"] .opic`).click();
  assert.equal(await page.locator("#dTitle").textContent(), "Layout A (Phone)");
  assert.equal(await page.locator("#dPos").textContent(), "1 of 4");
  await page.click("#dNext");
  assert.equal(await page.locator("#dTitle").textContent(), "Layout A (Wide)");
  await page.click("#dNext"); await page.click("#dNext");
  assert.equal(await page.locator("#dTitle").textContent(), "Layout B (Wide)");
  assert.equal(await page.locator("#dPos").textContent(), "4 of 4");
  await page.click("#dNext");
  assert.equal(await page.locator("#dPos").textContent(), "1 of 4", "Next does not wrap");
  await page.click("#dPrev");
  assert.equal(await page.locator("#dPos").textContent(), "4 of 4", "Prev does not wrap");
  await page.click("#dFull");
  assert.equal(await page.evaluate(() => window.__opened.length), 1, "Open full size opened nothing");
  await page.click("#dClose");
  assert.equal(await page.locator("#dsheet").isHidden(), true);
});

for (const width of [390, 1440]) {
  test(`a design's focus fills the card box whole, never cut, at ${width} wide`, async (t) => {
    const mock = '<body style="margin:0"><div style="height:700px"></div><div id="panel" style="width:300px;height:200px;background:#a62"></div><div style="height:500px"></div></body>';
    const it = mk("focus-q", 51, { pick: "a", options: [{ key: "a", label: "A", how: "h", gain: "g", lose: "l", design: "f-a" }], designs: [{ slug: "f-a", label: "A", focus: "#panel" }] });
    const page = await open(t, { items: [it], designData: { "f-a": mock }, viewport: { width, height: 900 } }); if (!page) return;
    const wrap = card(page, it).locator(".opic .dfitwrap");
    await page.waitForFunction((id) => { const w = document.querySelector(`#item-${id} .opic .dfitwrap`); return w && w.getBoundingClientRect().height > 0 && w.getBoundingClientRect().height < 400 && getComputedStyle(w.querySelector("iframe")).transform !== "none" && w.querySelector("iframe").style.transform.includes("translate"); }, it.id);
    const m = await wrap.evaluate((w) => {
      const f = w.querySelector("iframe"), r = w.getBoundingClientRect(), fr = f.getBoundingClientRect();
      const sc = fr.width / 390;
      return { wrapTop: r.top, wrapH: r.height, wrapW: r.width, panelTop: fr.top + 700 * sc, panelH: 200 * sc, panelW: 300 * sc };
    });
    assert.ok(Math.abs(m.panelTop - m.wrapTop) < 4, `the focused element starts ${m.panelTop - m.wrapTop}px from the top of the box`);
    assert.ok(m.panelH <= m.wrapH + 1, "the focused element is cut at the bottom");
    assert.ok(m.panelW <= m.wrapW + 1, "the focused element is cut at the side");
    assert.ok(m.wrapH < 260, `the box shows more than the focused element (${m.wrapH}px)`);
  });
}

test("SKILL.md and the designer agent carry the mockup convention", async () => {
  const skill = fs.readFileSync(path.join(HERE, "..", "SKILL.md"), "utf8");
  const designer = fs.readFileSync(path.join(HERE, "..", "..", "..", "agents", "designer.md"), "utf8");
  for (const [name, text] of [["SKILL.md", skill], ["designer.md", designer]]) {
    assert.match(text, /"Sample" banner/, name + " has no Sample banner line");
    assert.match(text, /"Today: <part>"/, name + " has no Today label");
    assert.match(text, /"New: <part>"/, name + " has no New label");
  }
  assert.match(skill, /`focus`/);
  assert.match(skill, /tap on (an option's|the) picture opens the viewer/i);
});

test("a design that names no option shows at the front of the item, before the options", async (t) => {
  const it = mk("loose-design", 34, { designs: [{ slug: "s1", label: "Overview" }] });
  const page = await open(t, { items: [it], designData: { s1: "<p>one</p>" } }); if (!page) return;
  const first = await card(page, it).evaluate((c) => { const f = c.querySelector(".dprev"), o = c.querySelector(".opts"); return !!f && !!o && !!(f.compareDocumentPosition(o) & Node.DOCUMENT_POSITION_FOLLOWING); });
  assert.equal(first, true);
});

test("an item with some designs but not every option's design warns in the option cards that lack one", async (t) => {
  const it = mk("half-pictures", 32, { look: true, options: LOOK_OPTS, pick: "a", designs: [{ slug: "price-a", label: "Layout a" }] });
  const page = await open(t, { items: [it], designData: { "price-a": "<p>a</p>" } }); if (!page) return;
  assert.equal(await card(page, it).locator(".opt .dwarn").count(), 2);
  assert.equal(await card(page, it).locator(`label.opt[for="o-${it.id}-a"] .dwarn`).count(), 0);
});

for (const width of [390, 1440]) {
  test(`a tall mockup is never cropped, at ${width} wide`, async (t) => {
    const it = picItem("tall", 35);
    const tall = '<body style="margin:0"><div style="height:1200px;background:#2a6">tall</div></body>';
    const page = await open(t, { items: [it], designData: { ...PICS, "price-a": tall }, viewport: { width, height: 900 } }); if (!page) return;
    const wrap = card(page, it).locator(`label.opt[for="o-${it.id}-a"] .dfitwrap`);
    await page.waitForFunction((sel) => document.querySelector(sel).getBoundingClientRect().height > 300, `#item-${it.id} label.opt .dfitwrap`);
    const m = await wrap.evaluate((w) => { const f = w.querySelector("iframe").getBoundingClientRect(), r = w.getBoundingClientRect(); return { wrapW: r.width, wrapH: r.height, frameW: f.width, frameH: f.height }; });
    const scale = m.frameW / 390;
    assert.ok(Math.abs(m.frameH - 1200 * scale) < 3, `the frame is ${m.frameH} high, the mockup ${1200 * scale}`);
    assert.ok(m.wrapH >= m.frameH - 1, "the wrapper cuts the bottom of the mockup");
    assert.ok(m.frameW <= m.wrapW + 1, "the mockup is wider than the card");
  });

  test(`a long option key stays on one line and never overlaps the title, at ${width} wide`, async (t) => {
    const it = mk("long-key", 36, { options: [
      { key: "feed-near", label: "Show the price history near the feed in a sheet", how: "h", gain: "g", lose: "l" },
      { key: "feed-far-away-key", label: "Far", how: "h", gain: "g", lose: "l" }], pick: "feed-near" });
    const page = await open(t, { items: [it], viewport: { width, height: 900 } }); if (!page) return;
    for (const o of it.options) {
      const m = await card(page, it).locator(`label.opt[for="o-${it.id}-${o.key}"]`).evaluate((l) => {
        const k = l.querySelector(".key"), b = l.querySelector(".lab");
        return { ws: getComputedStyle(k).whiteSpace, k: k.getBoundingClientRect().toJSON(), b: b.getBoundingClientRect().toJSON() };
      });
      assert.equal(m.ws, "nowrap", "the chip wraps");
      assert.ok(m.k.right <= m.b.left + 1 || m.k.bottom <= m.b.top + 1, `the chip overlaps the title for ${o.key}`);
    }
  });
}

test("an item that is not a look question never warns about pictures, with or without a named design", async (t) => {
  const plain = mk("not-a-look", 37, { options: LOOK_OPTS.map(({ design, ...o }) => o), pick: "a" });
  const named = mk("names-a-design", 38, { options: LOOK_OPTS, pick: "a" });
  const page = await open(t, { items: [plain, named] }); if (!page) return;
  assert.equal(await page.locator(".dwarn").count(), 0);
});

test("a long link in the context never widens the page on a phone", async (t) => {
  const it = mk("price-history-link", 33, { context: GITHUB_FOLDER, options: LOOK_OPTS, pick: "a" });
  const page = await open(t, { items: [it], viewport: { width: 390, height: 900 } }); if (!page) return;
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, "the page scrolls sideways");
});

test("a page with no designs has no Designs tab", async (t) => {
  const page = await open(t); if (!page) return;
  assert.equal(await page.locator("#tabD").isHidden(), true);
});

test("a decision option with a design shows it in a sandboxed frame inside its own card", async (t) => {
  const it = mk("opt-design", 1, { options: [opt("a", "Red", "s1"), opt("b", "Blue")] });
  const page = await open(t, { items: [it], designData: DESIGNS }); if (!page) return;
  const f = page.locator(optFrame(it, "a"));
  assert.equal(await f.count(), 1, "no frame inside option a's card");
  assert.equal(await f.getAttribute("sandbox"), "allow-scripts");
  assert.ok((await f.getAttribute("srcdoc")).startsWith("<p>one</p>"), "the srcdoc is not the design");
  assert.equal(await page.locator(optFrame(it, "b")).count(), 0, "option b has no design, so it has no frame");
});

test("an option whose design is missing from the page says so in its frame", async (t) => {
  const it = mk("gone-design", 1, { options: [opt("a", "Red", "nope"), opt("b", "Blue")] });
  const page = await open(t, { items: [it], designData: DESIGNS }); if (!page) return;
  assert.equal(await page.locator(optFrame(it, "a")).count(), 1, "no frame inside option a's card");
  await page.frameLocator(optFrame(it, "a")).getByText("This design is missing from the page.").waitFor();
});

test("an option design counts on the Designs tab, and the sheet pages through the option designs", async (t) => {
  const it = mk("opt-only", 1, { options: [opt("a", "Red", "s1"), opt("b", "Blue", "s2")] });
  const page = await open(t, { items: [it], designData: DESIGNS }); if (!page) return;
  assert.equal(await page.locator("#tabD").isVisible(), true, "the Designs tab is hidden");
  assert.equal(await page.locator("#dCount").textContent(), "2", "the count leaves out option designs");
  await page.click("#tabD");
  await page.locator("#dsheet").waitFor();
  const shown = () => page.locator("#dStage .dfitwrap:not(.off) iframe").getAttribute("srcdoc");
  assert.ok((await shown()).startsWith("<p>one</p>"));
  await page.click("#dNext");
  assert.ok((await shown()).startsWith("<p>two</p>"), "Next did not page to the second option design");
  await page.click("#dClose");
  assert.equal(await page.locator("#dsheet").isHidden(), true);
});

test("option rows line up across sibling cards when only one option has a design, at desktop width", async (t) => {
  const it = mk("rows", 1, { options: [
    { ...opt("a", "Red", "s1"), how: "A short way to put it." },
    { ...opt("b", "Blue"), how: "A longer way to put it, which runs onto a second line at desktop width. ".repeat(2) },
  ] });
  const page = await open(t, { items: [it], designData: DESIGNS, viewport: { width: 1280, height: 900 } }); if (!page) return;
  assert.equal(await page.locator(optFrame(it, "a")).count(), 1, "no frame inside option a's card");
  // The pick box is pinned to the bottom of its row, so the pick row is compared by bottom edge.
  const rows = await page.evaluate((id) => ["a", "b"].map((k) => {
    const l = document.querySelector(`label.opt[for="o-${id}-${k}"]`);
    const top = (sel) => Math.round(l.querySelector(sel).getBoundingClientRect().top);
    return { how: top(".how"), gain: top(".tr"), pick: Math.round(l.querySelector(".pick, .nopick").getBoundingClientRect().bottom) };
  }), it.id);
  for (const row of ["how", "gain", "pick"]) assert.ok(Math.abs(rows[0][row] - rows[1][row]) <= 1, `the ${row} rows are not level: ${rows[0][row]} and ${rows[1][row]}`);
});

for (const scheme of ["light", "dark"]) {
  test(`an option design fits a phone with no sideways scroll, ${scheme} scheme`, async (t) => {
    const it = mk("phone-design", 1, { options: [opt("a", "Red", "s1"), opt("b", "Blue")] });
    const page = await open(t, { items: [it], designData: DESIGNS, viewport: { width: 375, height: 800 }, scheme }); if (!page) return;
    const f = page.locator(optFrame(it, "a"));
    assert.equal(await f.count(), 1, "no frame inside option a's card");
    await f.scrollIntoViewIfNeeded();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, "the page scrolls sideways");
    const box = await f.boundingBox();
    assert.ok(box.x + box.width <= 375, "the option design runs past the phone width");
  });
}

// ---------------------------------------------------------------- answers, notes and withdrawing

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

const clearCount = (page) => page.getByRole("button", { name: "Clear" }).count();

test("no Clear button renders, on a fresh card, a drafted pick, a note, a task or a changed answer", async (t) => {
  const page = await open(t, { answers: { [TASK.id]: { item: TASK.id, n: 28, at: "2026-10-26T01:00:00Z", done: true, note: "" } } }); if (!page) return;
  assert.equal(await clearCount(page), 0);
  await choose(page, DECISION, "a"); await addNote(page, DECISION, "a thought");
  assert.equal(await clearCount(page), 0);
  await card(page, TASK).getByRole("button", { name: "Change" }).click();
  assert.equal(await clearCount(page), 0);
  assert.equal(await page.locator(".clearbtn").count(), 0);
});

test("a second click on the selected option unselects it, with no write", async (t) => {
  const page = await open(t); if (!page) return;
  await choose(page, DECISION, "a");
  assert.equal(await page.isChecked(`#o-${DECISION.id}-a`), true);
  await choose(page, DECISION, "a");
  assert.equal(await page.isChecked(`#o-${DECISION.id}-a`), false, "the pick is still selected after a second click");
  assert.equal(await page.evaluate(() => localStorage.getItem("waiting.draft")), "{}");
  assert.equal(await page.locator("#send").isDisabled(), true);
  assert.deepEqual(await page.evaluate(() => window.__log), []);
});

test("a second click unselects a stood pick, and it stays unselected", async (t) => {
  const it = mk("stand-solo", 7, { stands: true });
  const page = await open(t, { items: [it] }); if (!page) return;
  assert.equal(await page.isChecked(`#o-${it.id}-a`), true, "the pick does not stand");
  await choose(page, it, "a");
  assert.equal(await page.isChecked(`#o-${it.id}-a`), false, "a stood pick cannot be unselected");
  assert.equal(await page.locator("#send").isDisabled(), true, "an unselected stood pick still goes with Send");
  await takePick(page, it);
  assert.equal(await page.isChecked(`#o-${it.id}-a`), true);
  await choose(page, it, "a");
  assert.equal(await page.isChecked(`#o-${it.id}-a`), false, "a pick taken with Take my pick cannot be unselected");
});

test("emptying a note drops it", async (t) => {
  const page = await open(t); if (!page) return;
  await addNote(page, DECISION, "a thought");
  await page.fill(`#n-${DECISION.id}`, "");
  assert.equal(await page.evaluate(() => localStorage.getItem("waiting.draft")), "{}");
  assert.equal(await page.locator("#send").isDisabled(), true);
});

test("a changed answer left empty makes Send withdraw it", async (t) => {
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  const c = card(page, DECISION);
  await c.getByRole("button", { name: "Change" }).click();
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer", "withdraw is offered with the draft in place");
  await choose(page, DECISION, "a");
  assert.equal(await page.locator("#send").textContent(), "Withdraw answer");
  assert.equal(await page.locator("#send").isDisabled(), false);
  await send(page);
  await page.waitForFunction((id) => !(id in window.__answers()), DECISION.id);
  assert.deepEqual(await page.evaluate(() => window.__log), [["delete", "answers", DECISION.id]]);
  assert.equal(await page.isChecked(`#o-${DECISION.id}-a`), false);
  assert.equal(await c.locator(".receipt").count(), 0);
});

test("a task's done mark is withdrawn the same way", async (t) => {
  const page = await open(t, { answers: { [TASK.id]: { item: TASK.id, n: 28, at: "2026-10-26T01:00:00Z", done: true, note: "" } } });
  if (!page) return;
  await card(page, TASK).getByRole("button", { name: "Change" }).click();
  await card(page, TASK).getByRole("button", { name: "Mark done" }).click();
  assert.equal(await page.locator("#send").textContent(), "Withdraw answer");
  await send(page);
  await page.waitForFunction((id) => !(id in window.__answers()), TASK.id);
  assert.equal(await card(page, TASK).getByRole("button", { name: "Mark done" }).count(), 1);
});

test("a withdraw the store refuses keeps the answer and says so", async (t) => {
  const page = await open(t, { answers: SAVED_A, failDelete: true }); if (!page) return;
  const c = card(page, DECISION);
  await c.getByRole("button", { name: "Change" }).click();
  await choose(page, DECISION, "a");
  await send(page);
  await c.getByText("Not withdrawn (denied)", { exact: false }).waitFor();
  assert.ok((await answers(page))[DECISION.id], "the saved answer is gone");
});

test("a note with no option picked is an answer: choice none plus the note", async (t) => {
  const page = await open(t); if (!page) return;
  await addNote(page, DECISION, "Green please");
  assert.equal(await page.locator("#send").isDisabled(), false, "Send is shut on a note alone");
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], DECISION.id);
  const a = (await answers(page))[DECISION.id];
  assert.equal(a.choice, "none");
  assert.equal(a.note, "Green please");
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
const NOTE_ONLY = { [TASK.id]: { item: TASK.id, n: 28, at: "2026-10-26T01:00:00Z", note: "Which cable?" } };

test("a task note with no Mark done makes the card ready, live as the owner types", async (t) => {
  const page = await open(t); if (!page) return;
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is open with nothing answered");
  await addNote(page, TASK, "Which cable?");
  assert.equal(await card(page, TASK).locator(".ready").textContent(), "Ready to send: note, not done.");
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer");
  await page.fill(`#n-${TASK.id}`, "   ");
  assert.equal(await card(page, TASK).locator(".ready").textContent(), "");
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is open on a blank note");
});

test("a note-only task sends its note with no done; the notice says note, not done and the receipt says Not marked done", async (t) => {
  const page = await open(t); if (!page) return;
  await addNote(page, TASK, "Which cable?");
  assert.equal(await page.locator("#send").isDisabled(), false, "Send is shut on a note-only task");
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], TASK.id);
  const a = (await answers(page))[TASK.id];
  assert.deepEqual([a.item, a.n, a.note], [TASK.id, 28, "Which cable?"]);
  assert.ok(!("done" in a), "a note-only answer carries done");
  await page.waitForFunction(() => window.__sent.length === 1);
  assert.match((await sent(page))[0].text, /28 note, not done \(Which cable\?\)/);
  await card(page, TASK).locator(".receipt").waitFor();
  assert.match(await card(page, TASK).locator(".receipt").textContent(), /Not marked done/);
});

test("a saved note-only answer shows Not marked done with its note, and Change keeps the note", async (t) => {
  const page = await open(t, { answers: NOTE_ONLY }); if (!page) return;
  const c = card(page, TASK);
  assert.match(await c.locator(".receipt").textContent(), /Not marked done/);
  assert.match(await c.locator(".receipt .rnote").textContent(), /^Note: Which cable\?$/);
  await c.getByRole("button", { name: "Change" }).click();
  assert.equal(await page.inputValue(`#n-${TASK.id}`), "Which cable?");
  assert.equal(await c.locator(".ready").textContent(), "Ready to send: note, not done.");
  await page.fill(`#n-${TASK.id}`, "");
  assert.equal(await page.locator("#send").textContent(), "Withdraw answer");
});

test("the Copy line names a note-only task as note, not done", async (t) => {
  const page = await open(t, { failSet: true }); if (!page) return;
  await addNote(page, TASK, "Which cable?");
  assert.equal(await page.locator("#send").isDisabled(), false, "Send is shut on a note-only task");
  await send(page);
  await page.locator("#barStatus", { hasText: "Not saved (denied)" }).waitFor();
  await page.evaluate(() => { Object.defineProperty(navigator, "clipboard", { value: { writeText: async (s) => { window.__copied = s; } } }); });
  await page.click("#copy");
  assert.equal(await page.evaluate(() => window.__copied), "28 note, not done (Which cable?)");
});

test("the Copy line keeps a saved done when a draft under Change would not send", async (t) => {
  const page = await open(t, { answers: { [TASK.id]: { item: TASK.id, n: 28, at: "2026-10-26T01:00:00Z", done: true, note: "" } }, failSet: true }); if (!page) return;
  await card(page, TASK).getByRole("button", { name: "Change" }).click();
  await card(page, TASK).getByRole("button", { name: "Mark done" }).click(); // the draft is no longer done
  await addNote(page, TASK, "   ");
  await choose(page, DECISION, "a"); // a ready answer, so the failed write opens the Copy line
  await send(page);
  await page.locator("#barStatus", { hasText: "Not saved (denied)" }).waitFor();
  await page.evaluate(() => { Object.defineProperty(navigator, "clipboard", { value: { writeText: async (s) => { window.__copied = s; } } }); });
  await page.click("#copy");
  assert.equal(await page.evaluate(() => window.__copied), "27 a, 28 done");
});

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

test("a sent chip carries a mark, a ring while filing is pending and a check once filed, so it differs from ready by more than colour", async (t) => {
  const mark = (page) => page.evaluate((id) => getComputedStyle(document.getElementById("c-" + id), "::before").content, DECISION.id);
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  assert.match(await mark(page), /○/);
  await page.close();
  const page2 = await open(t, { answers: SAVED_A, receipts: { [DECISION.id]: { filed: "2026-10-26T03:00:00Z" } } }); if (!page2) return;
  assert.match(await mark(page2), /✓/);
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

// ---------------------------------------------------------------- option names, counts and the list

const WORDY = [["value", "Value for the card, shown near the feed in a sheet"], ["watch", "Watch"], ["nothing", "Nothing"]]
  .map(([key, label]) => ({ key, label, how: "h", gain: "g", lose: "l" }));

test("an option chip shows its letter by position, never a raw key longer than one character", async (t) => {
  const it = mk("long-keys", 40, { options: WORDY, pick: "watch", why: "Watch fits." });
  const page = await open(t, { items: [it] }); if (!page) return;
  const chips = await card(page, it).locator(".opt .key").allTextContents();
  assert.deepEqual(chips, ["A", "B", "C"]);
});

test("a pick is named by the option's title, shortened with an ellipsis, never by its raw key", async (t) => {
  const it = mk("pick-names", 41, { options: WORDY, pick: "value", why: "Value fits." });
  const page = await open(t, { items: [it] }); if (!page) return;
  const take = card(page, it).getByRole("button", { name: /Take my pick/ });
  const name = await take.textContent();
  assert.doesNotMatch(name, /VALUE|value\)/, "the button shows the raw key: " + name);
  assert.match(name, /^Take my pick \(Value for the card.*…\)$/, name);
  await take.click();
  const ready = await card(page, it).locator(".ready").textContent();
  assert.match(ready, /^Ready to send: Value for the card.*…, my pick\.$/, ready);
  await choose(page, it, "watch");
  assert.equal(await card(page, it).locator(".ready").textContent(), "Ready to send: Watch, your choice.");
});

test("the count digit matches the rest of its line", async (t) => {
  const page = await open(t); if (!page) return;
  const m = await page.evaluate(() => { const b = document.querySelector(".ov-prog .big b"), l = document.querySelector(".ov-prog .big"); return { b: getComputedStyle(b).fontSize, l: getComputedStyle(l).fontSize, v: getComputedStyle(b).fontVariantNumeric }; });
  assert.equal(m.b, m.l, "the digit is a different size from its line");
  assert.doesNotMatch(m.v, /slashed-zero/);
});

for (const width of [1440, 390]) {
  test(`each list entry carries its item's title, at ${width} wide`, async (t) => {
    const items = [mk("first-q", 1, { title: "Where does the price history show" }), { ...TASK, id: "second-q", n: 2, title: "Plug in the Mac" }];
    const page = await open(t, { items, viewport: { width, height: 900 } }); if (!page) return;
    for (const it of items) {
      const chip = page.locator(`#c-${it.id}`);
      assert.equal(await chip.getAttribute("title"), it.title);
      assert.ok((await chip.getAttribute("aria-label")).includes(it.title));
    }
    const shown = await page.locator("#c-first-q .nt").evaluate((e) => getComputedStyle(e).display !== "none" && e.getBoundingClientRect().width > 0).catch(() => false);
    assert.equal(shown, width > 960, width > 960 ? "no visible short title in the list" : "the short title crowds a narrow list");
  });
}

// ---------------------------------------------------------------- withdraw, undo and notes on a stood pick

test("a withdraw opens the 8-second Undo panel, and Undo puts the answer back", async (t) => {
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  const c = card(page, DECISION);
  await c.getByRole("button", { name: "Change" }).click();
  await choose(page, DECISION, "a");
  await send(page);
  await page.locator("#sent .stamp").waitFor();
  assert.match(await page.locator("#sent").textContent(), /withdrawn/i);
  assert.equal(await page.locator("#undoBtn").count(), 1, "no Undo after a withdraw");
  await page.click("#undoBtn");
  await page.waitForFunction((id) => !!window.__answers()[id], DECISION.id);
  assert.deepEqual((await answers(page))[DECISION.id], SAVED_A[DECISION.id]);
  assert.equal(await page.evaluate(() => window.__sent.length), 0, "a withdraw or its undo told a session");
});

test("a withdraw leaves an answer that changed since the page read it", async (t) => {
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  const c = card(page, DECISION);
  await c.getByRole("button", { name: "Change" }).click();
  await choose(page, DECISION, "a");
  await page.evaluate((id) => { window.__answers()[id] = { item: id, n: 27, at: "2026-10-26T05:00:00Z", choice: "b", note: "" }; }, DECISION.id);
  await send(page);
  await c.getByText("changed", { exact: false }).waitFor();
  assert.equal((await answers(page))[DECISION.id].choice, "b", "the newer answer was deleted");
  assert.deepEqual((await page.evaluate(() => window.__log)).filter((l) => l[0] === "delete"), []);
});

test("a note typed on an item whose pick stands sends the stood pick plus the note", async (t) => {
  const it = mk("stand-note", 7, { stands: true });
  const page = await open(t, { items: [it] }); if (!page) return;
  await addNote(page, it, "with a thought");
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], it.id);
  const a = (await answers(page))[it.id];
  assert.equal(a.choice, "a");
  assert.equal(a.note, "with a thought");
});

// ---------------------------------------------------------------- rank inside a tier

const order = (page) => page.evaluate(() => [...document.querySelectorAll("section.tier")].map((sec) => [sec.id, [...sec.querySelectorAll("article.card")].map((c) => c.id.slice(5))]));
const at = (day) => `2026-10-${String(day).padStart(2, "0")}T00:00:00Z`;

test("inside a tier, rank overrides age, and an item with no rank sorts after the ranked ones by age", async (t) => {
  const items = [
    mk("old-rank2", 1, { added: at(1), rank: 2 }), mk("new-rank1", 2, { added: at(5), rank: 1 }),
    mk("old-none", 3, { added: at(2) }), mk("new-none", 4, { added: at(6) }),
  ];
  const page = await open(t, { items }); if (!page) return;
  assert.deepEqual((await order(page)).find((x) => x[0] === "tier-calm")[1], ["new-rank1", "old-rank2", "old-none", "new-none"]);
});

test("a group stays together at its best member's rank", async (t) => {
  const items = [
    mk("solo-0", 1, { added: at(3), rank: 0 }), mk("grp-a", 2, { added: at(1), rank: 5, group: "g" }),
    mk("grp-b", 3, { added: at(2), rank: 1, group: "g" }), mk("solo-3", 4, { added: at(1), rank: 3 }),
  ];
  const page = await open(t, { items }); if (!page) return;
  const calm = (await order(page)).find((x) => x[0] === "tier-calm")[1];
  assert.equal(calm[0], "solo-0");
  assert.deepEqual(calm.slice(1, 3).sort(), ["grp-a", "grp-b"], "the group is split: " + calm);
  assert.equal(calm[3], "solo-3");
});

test("rank never moves an item across tiers", async (t) => {
  const items = [mk("calm-rank0", 1, { rank: 0 }), mk("hold-rank9", 2, { holds: "A lane waits.", rank: 9 }), mk("stand-rank0", 3, { stands: true, rank: 0 })];
  const page = await open(t, { items }); if (!page) return;
  const tiers = await order(page);
  assert.deepEqual(tiers.map((x) => x[0]), ["tier-holds", "tier-calm", "tier-stands"]);
  assert.deepEqual(tiers.map((x) => x[1]), [["hold-rank9"], ["calm-rank0"], ["stand-rank0"]]);
});

test("SKILL.md names the page's one writer and the rank field", async () => {
  const skill = fs.readFileSync(path.join(HERE, "..", "SKILL.md"), "utf8");
  assert.match(skill, /`writer`/);
  assert.match(skill, /`rank`/);
  assert.match(skill, /re-rank/i);
  const rule = fs.readFileSync(path.join(HERE, "..", "..", "..", "docs", "decisions", "questions-go-to-owner.md"), "utf8");
  assert.match(rule, /one writer/i);
  assert.match(rule, /`rank`/);
});

// Decision questions-go-to-owner, "Answer on the page, not in a comment thread":
// a rebuilt page drops its threads, so a session rewrites the item instead.
test("SKILL.md answers a comment by rewriting the item, never in a comment thread", async () => {
  const skill = fs.readFileSync(path.join(HERE, "..", "SKILL.md"), "utf8");
  assert.doesNotMatch(skill, /action `reply`/);
  assert.doesNotMatch(skill, /reply in the comment thread/i);
  assert.match(skill, /never reply in a comment thread/i);
  assert.match(skill, /rewrite that item/i);
});

// ---------------------------------------------------------------- round 2 looks

const PANEL = '<body style="margin:0"><div style="height:700px"></div><div id="panel" style="width:300px;height:45px;background:#a62"></div><div style="height:500px"></div></body>';
const FULLW = '<body style="margin:0;background:#2a6"><div style="width:390px;height:300px;background:#26a">x</div></body>';

for (const width of [390, 1440]) {
  test(`the View control sits under the picture and never covers it, at ${width} wide`, async (t) => {
    const it = mk("pill-q", 52, { pick: "a", options: [{ key: "a", label: "A", how: "h", gain: "g", lose: "l", design: "p-a" }], designs: [{ slug: "p-a", label: "A", focus: "#panel" }] });
    const page = await open(t, { items: [it], designData: { "p-a": PANEL }, viewport: { width, height: 900 } }); if (!page) return;
    await page.waitForFunction((id) => document.querySelector(`#item-${id} .dfitwrap`).getBoundingClientRect().height > 0, it.id);
    const m = await card(page, it).locator(".opic").evaluate((o) => { const w = o.querySelector(".dfitwrap").getBoundingClientRect(), v = o.querySelector(".view").getBoundingClientRect(); return { wrapBottom: w.bottom, wrapTop: w.top, viewTop: v.top, viewH: v.height }; });
    assert.ok(m.viewTop >= m.wrapBottom - 1, "the View control covers the picture");
    assert.ok(m.viewH >= 40, "the View control is under 40px high: " + m.viewH);
  });

  test(`the viewer head is one row, and the mockup is whole and centered, at ${width} wide`, async (t) => {
    const it = viewerItem();
    const page = await open(t, { items: [it], designData: { ...VIEWER_DATA, "v-a": FULLW }, viewport: { width, height: 900 } }); if (!page) return;
    // Stand-in for CI's wider fallback font: the one-row head is then wider than a phone.
    await page.addStyleTag({ content: ".dsh-head { letter-spacing: 1.2px }" });
    await card(page, it).locator(`label.opt[for="o-${it.id}-a"] .opic`).click();
    await page.waitForFunction(() => { const f = document.querySelector("#dStage .dframe:not(.off)"); return f && f.getBoundingClientRect().height > 60; });
    const m = await page.evaluate(() => { const f = document.querySelector("#dStage iframe").getBoundingClientRect(), h = document.querySelector(".dsh-head").getBoundingClientRect(); return { left: f.left, right: f.right, headH: h.height, close: document.querySelector("#dClose").getBoundingClientRect().right, sheetW: document.querySelector("#dsheet").scrollWidth, vw: innerWidth }; });
    assert.ok(m.headH < 70, "the viewer head is " + m.headH + "px high");
    assert.ok(m.close <= m.vw + 0.5, "Close is cut off: its right edge is " + m.close);
    assert.ok(m.sheetW <= m.vw, "the viewer scrolls sideways: " + m.sheetW + " in " + m.vw);
    assert.ok(m.right <= m.vw + 0.5 && m.left >= -0.5, "the mockup is cut: " + m.left + " to " + m.right);
    if (width > 900) assert.ok(Math.abs((m.left + m.right) / 2 - m.vw / 2) < 3, "the mockup is not centered");
    for (const id of ["dPrev", "dNext", "dFull", "dClose"]) assert.ok((await page.locator("#" + id).boundingBox()).height >= 40, id + " is under 40px");
  });
}

const WIDE_DESIGN = '<body style="margin:0;display:flex;width:1200px"><div style="width:400px;height:200px;background:#a62">1</div><div style="width:400px;height:200px;background:#26a">2</div><div id="last" style="width:400px;height:200px;background:#2a6">3</div></body>';
for (const width of [390, 1440]) {
  test(`a design drawn 1200 wide is whole in the viewer, at ${width} wide`, async (t) => {
    const it = mk("wide-q", 55, { pick: "a", options: [{ key: "a", label: "Wide", how: "h", gain: "g", lose: "l", design: "w-a" }], designs: [{ slug: "w-a", label: "Wide", drawn: 1200 }] });
    const page = await open(t, { items: [it], designData: { "w-a": WIDE_DESIGN }, viewport: { width, height: 900 } }); if (!page) return;
    await card(page, it).locator(".opic").click();
    await page.waitForFunction(() => { const f = document.querySelector("#dStage .dfitwrap:not(.off) iframe"); return f && FIT["w-a|"]; });
    const m = await page.evaluate(() => {
      const f = document.querySelector("#dStage .dfitwrap:not(.off) iframe"), r = f.getBoundingClientRect();
      return { right: r.right, left: r.left, vw: innerWidth, w: f.style.width };
    });
    const tile = await page.frameLocator("#dStage .dfitwrap:not(.off) iframe").locator("#last").boundingBox();
    const f = await page.locator("#dStage .dfitwrap:not(.off)").boundingBox();
    const sc = (await page.locator("#dStage .dfitwrap:not(.off) iframe").evaluate((e) => new DOMMatrix(getComputedStyle(e).transform).a));
    assert.equal(m.w, "1200px", "the frame is not drawn at the design's width");
    assert.ok(Math.abs(tile.x + tile.width - (f.x + f.width)) <= 2 && tile.x + tile.width <= m.vw + 0.5, `the right-most tile is cut: ends at ${tile.x + tile.width}, viewer ends at ${f.x + f.width}`);
    assert.ok(sc < 1, "the design is not scaled down");
  });
}

test("a viewer whose head cuts the title names the design in a one-line caption above it", async (t) => {
  const it = viewerItem();
  const page = await open(t, { items: [it], designData: { ...VIEWER_DATA, "v-a": FULLW }, viewport: { width: 390, height: 900 } }); if (!page) return;
  // Stand-in for CI's wider fallback font, so the head cuts "Layout A (Phone)" at 390.
  await page.addStyleTag({ content: ".dsh-head { letter-spacing: 1.2px }" });
  await card(page, it).locator(`label.opt[for="o-${it.id}-a"] .opic`).click();
  const cap = page.locator("#dCap");
  assert.equal(await cap.isVisible(), true, "no caption in the viewer");
  assert.equal(await cap.textContent(), await page.evaluate(() => dList[dAt].label));
  const m = await page.evaluate(() => { const c = document.querySelector("#dCap").getBoundingClientRect(), f = document.querySelector("#dStage .dfitwrap:not(.off)").getBoundingClientRect(); return { capBottom: c.bottom, frameTop: f.top, capH: c.height, vw: innerWidth, right: f.right }; });
  assert.ok(m.capBottom <= m.frameTop + 0.5, "the caption sits over the mockup");
  assert.ok(m.capH < 30, "the caption is more than one line: " + m.capH);
  assert.ok(m.right <= m.vw + 0.5, "the mockup is cut");
  await page.setViewportSize({ width: 1440, height: 900 });
  // The resize observer hides the caption a frame after the resize.
  await page.waitForFunction(() => { const c = document.querySelector("#dCap"); return getComputedStyle(c).display === "none"; }, null, { timeout: 2000 }).catch(() => {});
  assert.equal(await cap.isVisible(), false, "the caption shows on a wide screen, where the title fits");
});

// The caption names the design whenever the head cuts the title, and only then (design review round 2).
const TALL_DESIGN = `<body style="margin:0">${Array.from({ length: 25 }, (_, i) => `<div style="height:80px;background:hsl(${i * 14},60%,55%)">${i + 1}</div>`).join("")}</body>`;
const capItem = (labels) => mk("cap-q", 56, { pick: "a", options: labels.map((l, i) => ({ key: "abc"[i], label: l, how: "h", gain: "g", lose: "l", design: "c-" + "abc"[i] })),
  designs: labels.map((l, i) => ({ slug: "c-" + "abc"[i], label: l, width: "Phone" })) });
const capState = (page) => page.evaluate(() => { const c = document.querySelector("#dCap"), t = document.querySelector("#dTitle"), r = c.getBoundingClientRect();
  return { shown: getComputedStyle(c).display !== "none" && r.height > 0, h: r.height, text: c.textContent, cut: c.scrollWidth > c.clientWidth, label: dList[dAt].label, titleCut: t.scrollWidth > t.clientWidth }; });
async function openCap(t, labels, width, design) {
  const it = capItem(labels);
  const page = await open(t, { items: [it], designData: { "c-a": design, "c-b": "<p>b</p>" }, viewport: { width, height: 900 } }); if (!page) return null;
  // Stand-in for CI's wider fallback font.
  await page.addStyleTag({ content: ".dsh-head { letter-spacing: 1.2px }" });
  await card(page, it).locator(`label.opt[for="o-${it.id}-a"] .opic`).click();
  await page.waitForFunction(() => FIT["c-a|"] && document.querySelector("#dStage .dfitwrap:not(.off)").getBoundingClientRect().height > 60);
  return page;
}

test("a tall design with a long label is named in a caption with height, at 390 wide", async (t) => {
  const page = await openCap(t, ["Tall A layout with bands", "B"], 390, TALL_DESIGN); if (!page) return;
  const c = await capState(page);
  assert.ok(c.titleCut, "the stand-in label fits the head; the test needs a longer one");
  assert.ok(c.shown && c.h >= 14, "the caption is " + c.h + "px high, so nothing names the design");
  assert.equal(c.text, c.label); assert.ok(!c.cut, "the caption cuts the label");
});

test("at 768 wide a title the head cuts shows in the caption, and Prev to a short title hides it", async (t) => {
  const page = await openCap(t, ["Layout A in a sheet under the feed card", "B"], 768, "<p>a</p>"); if (!page) return;
  let c = await capState(page);
  assert.ok(c.titleCut, "the stand-in label fits the head; the test needs a longer one");
  assert.ok(c.shown, "the head cuts the title and no caption names the design");
  assert.equal(c.text, c.label); assert.ok(!c.cut, "the caption cuts the label");
  await page.click("#dPrev");
  c = await capState(page);
  assert.ok(!c.titleCut, "the short title is cut");
  assert.ok(!c.shown, "the caption repeats a title that fits");
});

test("a title that fits the head gets no caption, at 390 wide", async (t) => {
  const page = await openCap(t, ["A", "B"], 390, "<p>a</p>"); if (!page) return;
  const c = await capState(page);
  assert.ok(!c.titleCut, "the short title is cut");
  assert.ok(!c.shown, "the caption repeats a title that fits");
});

test("a picture's height is reserved from its declared size before it loads", async (t) => {
  const it = mk("reserve-q", 53, { pick: "a", options: [{ key: "a", label: "A", how: "h", gain: "g", lose: "l", design: "r-a" }], designs: [{ slug: "r-a", label: "A", focus: "#panel", size: { w: 600, h: 400 } }] });
  const mockup = '<body style="margin:0;width:700px"><div style="height:700px"></div><div id="panel" style="width:600px;height:400px;background:#a62"></div></body>';
  const page = await open(t, { items: [it], designData: { "r-a": mockup }, viewport: { width: 1440, height: 900 } }); if (!page) return;
  await page.waitForFunction((id) => document.querySelector(`#item-${id} iframe`).style.transform.includes("translate"), it.id);
  const first = await page.evaluate(() => window.__firstFit);
  const last = await page.evaluate((id) => document.querySelector(`#item-${id} .dfitwrap`).getBoundingClientRect().height, it.id);
  assert.ok(first && Math.abs(first - last) <= 3, `first paint ${first}, loaded ${last}`);
});

test("two designs of one slug with different focus keep their own size, and the viewer opens on the tapped option", async (t) => {
  const two = '<body style="margin:0"><div id="p1" style="width:300px;height:200px;background:#a62"></div><div id="p2" style="width:300px;height:100px;background:#26a"></div></body>';
  const it = mk("shared-q", 54, { pick: "a", options: [{ key: "a", label: "Layout A", how: "h", gain: "g", lose: "l" }, { key: "b", label: "Layout B", how: "h", gain: "g", lose: "l" }],
    designs: [{ slug: "shared", option: "a", label: "A", focus: "#p1" }, { slug: "shared", option: "b", label: "B", focus: "#p2" }] });
  const page = await open(t, { items: [it], designData: { shared: two }, viewport: { width: 1440, height: 900 } }); if (!page) return;
  await page.waitForFunction((id) => [...document.querySelectorAll(`#item-${id} .dfitwrap`)].every((w) => w.querySelector("iframe").style.transform.includes("translate")), it.id);
  const hs = await card(page, it).locator(".dfitwrap").evaluateAll((ws) => ws.map((w) => w.getBoundingClientRect().height));
  assert.ok(hs[0] > hs[1] * 1.6, "the second picture took the first one's size: " + hs);
  await card(page, it).locator(`label.opt[for="o-${it.id}-b"] .opic`).click();
  assert.match(await page.locator("#dTitle").textContent(), /^Layout B/);
});

// ---------------------------------------------------------------- each option's picture shows its own difference
const ALERT = (page, it) => card(page, it).locator("p.broken[role=alert]");
const lateRow = (state) => `<body style="margin:0"><div id="late-row">${state}</div><div id="other">x</div></body>`;
const looks = (id, n, designs, over = {}) => mk(id, n, { look: true, pick: "a", options: WIDE.map(([k, l]) => ({ key: k, label: l, how: "h", gain: "g", lose: "l", design: "o-" + k })), designs, ...over });

test("a look question whose options A and B name one design shows an alert and Send is refused", async (t) => {
  const it = mk("same-pic", 60, { look: true, pick: "a",
    options: [{ key: "a", label: "Claim filed and Lost", how: "h", gain: "g", lose: "l", design: "late" }, { key: "b", label: "Six stamps", how: "h", gain: "g", lose: "l", design: "late" }],
    designs: [{ slug: "late", label: "Late" }] });
  const page = await open(t, { items: [it], designData: { late: lateRow("alert") } }); if (!page) return;
  assert.equal(await ALERT(page, it).count(), 1, "no alert on two options with one picture");
  assert.match(await ALERT(page, it).textContent(), /A and B.*share one picture.*neither shows its own difference.*fix item 60/s);
  await page.evaluate(() => { setDraft(byId("same-pic"), { choice: "a", auto: true }); render(); });
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is open on an item whose options share a picture");
});

test("two options whose designs have different slugs but the same bytes are refused too", async (t) => {
  const it = looks("same-bytes", 61, [{ slug: "o-a", label: "A" }, { slug: "o-b", label: "B" }]);
  const page = await open(t, { items: [it], designData: { "o-a": lateRow("same"), "o-b": lateRow("same") } }); if (!page) return;
  assert.match(await ALERT(page, it).textContent(), /A and B.*share one picture/s);
});

test("a focus that matches nothing in its mockup, or is no selector, is refused and names the option", async (t) => {
  for (const [id, n, focus] of [["focus-miss", 62, "#no-such"], ["focus-bad", 63, "##("]]) {
    const it = looks(id, n, [{ slug: "o-a", label: "A" }, { slug: "o-b", label: "B", focus }]);
    const page = await open(t, { items: [it], designData: { "o-a": lateRow("one"), "o-b": lateRow("two") } }); if (!page) return;
    assert.equal(await ALERT(page, it).count(), 1, id + " shows no alert");
    assert.match(await ALERT(page, it).textContent(), /option B.*shows nothing the focus names.*fix item/s);
    assert.doesNotMatch(await ALERT(page, it).textContent(), /option A/);
  }
});

test("distinct pictures with a focus that matches show no alert; extra widths and one slug with two focuses stay free", async (t) => {
  const it = looks("own-pics", 64, [{ slug: "o-a", label: "A", focus: "#late-row" }, { slug: "o-b", label: "B", focus: "#late-row" }, { slug: "o-a", option: "a", label: "A wide", width: "Wide" }]);
  const page = await open(t, { items: [it], designData: { "o-a": lateRow("one"), "o-b": lateRow("two") } }); if (!page) return;
  assert.equal(await ALERT(page, it).count(), 0, "an alert on distinct pictures");
  await page.evaluate(() => { setDraft(byId("own-pics"), { choice: "a", auto: true }); render(); });
  assert.equal(await page.locator("#send").isDisabled(), false);
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

for (const width of [390, 1440]) {
  test(`the viewer is fitted the moment it opens, not after a later resize callback, at ${width} wide`, async (t) => {
    const it = viewerItem();
    const page = await open(t, { items: [it], designData: { ...VIEWER_DATA, "v-a": FULLW }, viewport: { width, height: 900 } }); if (!page) return;
    // Stand-in for CI's wider fallback font: the one-row head is then wider than a phone.
    await page.addStyleTag({ content: ".dsh-head { letter-spacing: 1.2px }" });
    const m = await page.evaluate((id) => {
      document.querySelector(`#item-${id} label.opt .opic`).click();
      const f = document.querySelector("#dStage iframe").getBoundingClientRect();
      return { left: f.left, right: f.right, close: document.querySelector("#dClose").getBoundingClientRect().right, sheetW: document.querySelector("#dsheet").scrollWidth, vw: innerWidth };
    }, it.id);
    assert.ok(m.close <= m.vw + 0.5, "Close is cut off on open: its right edge is " + m.close);
    assert.ok(m.sheetW <= m.vw, "the viewer scrolls sideways on open: " + m.sheetW + " in " + m.vw);
    assert.ok(m.right <= m.vw + 0.5 && m.left >= -0.5, `cut on open: ${m.left} to ${m.right}`);
    if (width > 900) assert.ok(Math.abs((m.left + m.right) / 2 - m.vw / 2) < 3, "not centered on open");
  });
}

// ---------------------------------------------------------------- c100 review defects

// Each helper wraps db.doc().delete so the test controls what a delete does inside Undo.
const hookDelete = (fn) => (page) => page.evaluate(`(() => {
  const col = state.db.collection;
  state.db.collection = (n) => { const x = col(n); const d = x.doc; x.doc = (id) => { const y = d(id); const del = y.delete; y.delete = (${fn})(n, del); return y; }; return x; };
  document.getElementById("undoBtn").click();
})()`);

test("a partial Undo lists late items with commas and one final and", async (t) => {
  const items = [mk("d-one", 1), mk("d-two", 2), mk("d-three", 3), mk("d-four", 4)];
  const page = await open(t, { items }); if (!page) return;
  for (const it of items) await takePick(page, it);
  await send(page);
  await page.locator("#undoBtn").waitFor();
  await hookDelete(`(n, del) => async () => { await del(); const real = Date.now; Date.now = () => real() + 9000; }`)(page);
  await page.locator("#barStatus", { hasText: "Too late to undo" }).waitFor();
  const text = await page.locator("#barStatus").innerText();
  assert.match(text, /Too late to undo No\. 1, No\. 2,? and No\. 3\./, text);
});

test("a failed Undo names every item it could not undo", async (t) => {
  const items = [mk("d-one", 1), mk("d-two", 2), mk("d-three", 3)];
  const page = await open(t, { items }); if (!page) return;
  for (const it of items) await takePick(page, it);
  await send(page);
  await page.locator("#undoBtn").waitFor();
  await hookDelete(`(n, del) => async () => { if (n === "answers") throw { code: "denied" }; return del(); }`)(page);
  await page.locator("#barStatus", { hasText: "Undo failed" }).waitFor();
  const text = await page.locator("#barStatus").innerText();
  for (const n of [1, 2, 3]) assert.match(text, new RegExp("No\\. " + n + "\\b"), "the bar does not name No. " + n + ": " + text);
});

test("a failed receipt delete leaves no old receipt in the page state", async (t) => {
  const page = await open(t, { receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z" } }, failDeleteIn: "receipts" }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#undoBtn").click();
  await page.waitForFunction((id) => !(id in state.answers), DECISION.id);
  assert.equal(await page.evaluate((id) => id in state.receipts, DECISION.id), false, "the old receipt is still in the page state");
});

// ---------------------------------------------------------------- c122: what differs, open this state, short titles

const diffItem = (over = {}) => mk("diff-q", 70, { pick: "a", options: [
  { key: "a", label: "Alpha", how: "same how", gain: "gain A", lose: "same lose", differs: ["gain"] },
  { key: "b", label: "Beta", how: "same how", gain: "gain B", lose: "same lose" },
], ...over });
const SETS = "Sets this option apart: ";

test("a named field gets a bar class, a not-equal sign and screen-reader words; an option with no differs shows none", async (t) => {
  const it = diffItem();
  const page = await open(t, { items: [it] }); if (!page) return;
  const a = card(page, it).locator('label.opt[for="o-diff-q-a"]'), b = card(page, it).locator('label.opt[for="o-diff-q-b"]');
  const g = a.locator(".gain");
  assert.equal(await g.evaluate((e) => e.classList.contains("dif")), true, "gain is not marked");
  assert.equal(await g.locator(".ne").textContent(), "≠");
  assert.equal(await g.locator(".ne").getAttribute("aria-hidden"), "true");
  assert.equal(await g.locator(".sr").textContent(), SETS);
  assert.equal(await a.locator(".how.dif, .lose.dif").count(), 0, "an unnamed field is marked");
  assert.equal(await b.locator(".dif, .ne").count(), 0, "an option with no differs is marked");
  assert.equal(await card(page, it).locator(".difkey").count(), 1, "the legend is not shown once");
  assert.match(await card(page, it).locator(".difkey").innerText(), /≠\s*marks what sets an option apart\./);
});

test("the page drops a named text field whose text equals every other option's, and ignores an unknown name", async (t) => {
  const it = diffItem({ options: [
    { key: "a", label: "Alpha", how: "same how", gain: "gain A", lose: "same lose", differs: ["how", "gain", "colour"] },
    { key: "b", label: "Beta", how: "same how", gain: "gain B", lose: "same lose" },
    { key: "c", label: "Gamma", how: "same how", gain: "gain C", lose: "same lose" },
  ] });
  const page = await open(t, { items: [it] }); if (!page) return;
  const a = card(page, it).locator('label.opt[for="o-diff-q-a"]');
  assert.equal(await a.locator(".how.dif").count(), 0, "how equals the others and is still marked");
  assert.equal(await a.locator(".gain.dif").count(), 1);
  assert.equal(await a.locator(".dif").count(), 1, "an unknown name marked something");
});

test("an item whose differs all drop, or that has none, shows no legend", async (t) => {
  const it = diffItem({ options: [
    { key: "a", label: "Alpha", how: "h", gain: "g", lose: "l", differs: ["how"] }, { key: "b", label: "Beta", how: "h", gain: "g", lose: "l" }] });
  const page = await open(t, { items: [it, DECISION] }); if (!page) return;
  assert.equal(await page.locator(".difkey, .ne").count(), 0);
});

test("a named picture marks the frame and the View bar and says so in its label; picture on an option with no picture is ignored", async (t) => {
  const it = looks("diff-pic", 71, [{ slug: "o-a", label: "A" }, { slug: "o-b", label: "B" }]);
  it.options[0].differs = ["picture"]; it.options[1].differs = ["picture"]; delete it.options[1].design;
  const page = await open(t, { items: [it], designData: { "o-a": lateRow("one"), "o-b": lateRow("two") } }); if (!page) return;
  const pa = card(page, it).locator('label.opt[for="o-diff-pic-a"] .opic');
  assert.equal(await pa.evaluate((e) => e.classList.contains("dif")), true);
  assert.equal(await pa.locator(".view .ne").textContent(), "≠");
  assert.match(await pa.getAttribute("aria-label"), /^View Layout A full screen\. Its picture sets this option apart$/);
  assert.equal(await card(page, it).locator('label.opt[for="o-diff-pic-b"] .dif').count(), 0, "a picture mark on an option with no picture");
});

const STATE_MOCK = '<!doctype html><body style="margin:0"><div data-state="default">d</div><div data-state="late-package" id="late-row">late</div></body>';
const stateItem = (id, n, states, over = {}) => looks(id, n, [
  { slug: "s-a", label: "A", ...(states[0] ? { state: states[0] } : {}) }, { slug: "s-b", label: "B", ...(states[1] ? { state: states[1] } : {}) }], over);
const STATE_DATA = { "s-a": STATE_MOCK, "s-b": STATE_MOCK.replace(">late<", ">late two<") };
const stateOpts = (it) => it.options.forEach((o, i) => { o.design = i ? "s-b" : "s-a"; });

test("a design with a state opens its mockup at that state, in the card frame and in the viewer", async (t) => {
  const it = stateItem("st-frame", 72, ["late-package", "late-package"]); stateOpts(it);
  const page = await open(t, { items: [it], designData: STATE_DATA }); if (!page) return;
  const fr = await (await page.locator(optFrame(it, "a")).elementHandle()).contentFrame();
  await fr.waitForLoadState();
  assert.equal(await fr.evaluate(() => location.hash), "#s=late-package");
  const src = await page.locator(optFrame(it, "a")).getAttribute("srcdoc");
  assert.ok(src.search(/<!doctype/i) < src.search(/location\.hash/), "the state script must come after the doctype, or the mockup renders in quirks mode");
});

test("the viewer names the state in its title and offers Open this state, which opens the blob at #s=<state>", async (t) => {
  const it = stateItem("st-view", 73, ["late-package", null]); stateOpts(it);
  const page = await open(t, { items: [it], designData: STATE_DATA }); if (!page) return;
  await page.evaluate(() => { window.__opened = []; window.open = (u) => { window.__opened.push(String(u)); return null; }; });
  await card(page, it).locator('label.opt[for="o-st-view-a"] .opic').click();
  assert.equal(await page.locator("#dTitle").textContent(), "Layout A (Phone), late package");
  assert.equal(await page.locator("#dCap").textContent(), "Layout A (Phone), late package");
  assert.equal(await page.locator("#dFull .lg").textContent(), "Open this state");
  assert.equal(await page.locator("#dFull").getAttribute("aria-label"), "Open the late package state of the full mockup in a new tab");
  await page.click("#dFull");
  const u = await page.evaluate(() => window.__opened);
  assert.equal(u.length, 1); assert.match(u[0], /^blob:.*#s=late-package$/);
  await page.click("#dNext");
  assert.equal(await page.locator("#dTitle").textContent(), "Layout B (Phone)", "no state: no suffix");
  assert.equal(await page.locator("#dFull .lg").textContent(), "Open full size");
  assert.equal(await page.locator("#dFull").getAttribute("aria-label"), "Open full size");
});

test("a state the mockup does not draw blocks the item and names the option; a drawn state, or two states of one slug and focus, do not", async (t) => {
  const bad = stateItem("st-bad", 74, [null, "no-such-state"]); stateOpts(bad);
  let page = await open(t, { items: [bad], designData: STATE_DATA }); if (!page) return;
  assert.equal(await ALERT(page, bad).count(), 1, "no alert");
  assert.match(await ALERT(page, bad).textContent(), /option B names a state its mockup does not draw\. Ask the session to fix item 74\./);
  await page.evaluate(() => { setDraft(byId("st-bad"), { choice: "a", auto: true }); render(); });
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is not refused");
  const ok = stateItem("st-ok", 75, ["late-package", "default"]);
  ok.designs = ok.designs.map((d, i) => ({ ...d, slug: "s-a", option: "ab"[i] })); ok.options.forEach((o) => { o.design = "s-a"; });
  page = await open(t, { items: [ok], designData: STATE_DATA }); if (!page) return;
  assert.equal(await ALERT(page, ok).count(), 0, "two states of one slug are refused as one picture");
  const same = stateItem("st-same", 76, ["late-package", "late-package"]);
  same.designs = same.designs.map((d, i) => ({ ...d, slug: "s-a", option: "ab"[i] })); same.options.forEach((o) => { o.design = "s-a"; });
  page = await open(t, { items: [same], designData: STATE_DATA }); if (!page) return;
  assert.match(await ALERT(page, same).textContent(), /A and B.*share one picture/s);
});

const shortChip = (page, it) => page.locator(`#c-${it.id}`);
test("the wide rail chip shows the short title; no or an over-long short falls back to the title; the title stays in full on the chip", async (t) => {
  const items = [mk("sh-a", 80, { title: "A very long question title for the rail", short: "Rail name" }), mk("sh-b", 81, { title: "Second long question title here" }), mk("sh-c", 82, { title: "Third long question title here", short: "x".repeat(25) })];
  const page = await open(t, { items }); if (!page) return;
  assert.equal(await shortChip(page, items[0]).locator(".nt").textContent(), "Rail name");
  assert.equal(await shortChip(page, items[1]).locator(".nt").textContent(), "Second long question title here");
  assert.equal(await shortChip(page, items[2]).locator(".nt").textContent(), "Third long question title here");
  assert.equal(await shortChip(page, items[0]).getAttribute("title"), "A very long question title for the rail");
  assert.match(await shortChip(page, items[0]).getAttribute("aria-label"), /^No\. 80, A very long question title for the rail, /);
});

const looseItem = () => mk("st-loose", 77, { designs: [{ slug: "s-a", label: "Early", state: "default" }, { slug: "s-a", label: "Late", state: "late-package" }] });

test("a front preview's Open this state opens the viewer at the design shown, even when two designs share a slug", async (t) => {
  const it = looseItem();
  const page = await open(t, { items: [it], designData: STATE_DATA }); if (!page) return;
  const btn = card(page, it).locator(".dprev .dbar button").last();
  assert.equal(await btn.textContent(), "Open this state");
  assert.equal(await btn.getAttribute("aria-label"), "Open the default state in the viewer");
  await card(page, it).locator('.dprev button[aria-label="Next design"]').click();
  assert.equal(await btn.getAttribute("aria-label"), "Open the late package state in the viewer");
  await btn.click();
  assert.equal(await page.locator("#dTitle").textContent(), "Late, late package");
  assert.equal(await page.locator("#dFull").getAttribute("aria-label"), "Open the late package state of the full mockup in a new tab");
});

test("a front preview's Open this state still opens the design shown after the items are rebuilt as new objects", async (t) => {
  const other = mk("st-first", 70, { designs: [{ slug: "s-b", label: "First item design" }] });
  const it = looseItem();
  const page = await open(t, { items: [other, it], designData: STATE_DATA }); if (!page) return;
  await page.evaluate(() => { state.items = state.items.map((x) => ({ ...x })); render(); });
  await card(page, it).locator('.dprev button[aria-label="Next design"]').click();
  await card(page, it).locator(".dprev .dbar button").last().click();
  assert.equal(await page.locator("#dTitle").textContent(), "Late, late package");
});

test("each design frame's title names its state, in the viewer stage and in the front preview", async (t) => {
  const it = looseItem();
  const page = await open(t, { items: [it], designData: STATE_DATA }); if (!page) return;
  assert.equal(await card(page, it).locator(".dprev iframe").getAttribute("title"), "Early, default");
  await page.click("#tabD");
  await page.click("#dNext");
  assert.equal(await page.locator("#dStage > .dfitwrap:not(.off) iframe").getAttribute("title"), "Late, late package");
});

test("the Designs tab viewer also names each design's state in its title", async (t) => {
  const it = looseItem();
  const page = await open(t, { items: [it], designData: STATE_DATA }); if (!page) return;
  await page.click("#tabD");
  assert.equal(await page.locator("#dTitle").textContent(), "Early, default");
  await page.click("#dNext");
  assert.equal(await page.locator("#dTitle").textContent(), "Late, late package");
  assert.equal(await page.locator("#dCap").textContent(), "Late, late package");
});

test("an Undo where one delete works and a later one fails names only the items still sent", async (t) => {
  const items = [mk("d-one", 1), mk("d-two", 2), mk("d-three", 3)];
  const page = await open(t, { items }); if (!page) return;
  for (const it of items) await takePick(page, it);
  await send(page);
  await page.locator("#undoBtn").waitFor();
  await page.evaluate(`(() => {
    const col = state.db.collection;
    state.db.collection = (n) => { const x = col(n); const d = x.doc; x.doc = (id) => { const y = d(id); const del = y.delete; y.delete = async () => { if (n === "answers" && id === "d-two") throw { code: "denied" }; return del(); }; return y; }; return x; };
    document.getElementById("undoBtn").click();
  })()`);
  await page.locator("#barStatus", { hasText: "Undo failed" }).waitFor();
  const text = await page.locator("#barStatus").innerText();
  assert.match(text, /Not undone: No\. 1 and No\. 2\./, text);
  assert.doesNotMatch(text, /No\. 3/, "No. 3 was undone and must not be named: " + text);
});

test("a named picture's not-equal sign sits inside its View bar", async (t) => {
  const it = looks("diff-ne", 78, [{ slug: "o-a", label: "A" }, { slug: "o-b", label: "B" }]);
  it.options[0].differs = ["picture"];
  const page = await open(t, { items: [it], designData: { "o-a": lateRow("one"), "o-b": lateRow("two") } }); if (!page) return;
  const m = await page.evaluate((id) => {
    const o = document.querySelector(`#item-${id} label.opt .opic.dif`), v = o.querySelector(".view").getBoundingClientRect(), n = o.querySelector(".ne").getBoundingClientRect();
    return { v: [v.left, v.top, v.right, v.bottom], n: [n.left, n.top, n.right, n.bottom] };
  }, it.id);
  assert.ok(m.n[0] >= m.v[0] - 0.5 && m.n[2] <= m.v[2] + 0.5 && m.n[1] >= m.v[1] - 0.5 && m.n[3] <= m.v[3] + 0.5, "the sign is outside the View bar: " + JSON.stringify(m));
});

// ---------------------------------------------------------------- sizes: receipt height, rail chips, option pictures (c193)
const SIZES = [2200, 1280, 390];
// Chromium's scroll anchoring would hide a missing compensation (Safari has none), so these tests switch it off.
const noAnchor = (page) => page.addStyleTag({ content: "*, html { overflow-anchor: none !important; }" });
const FILLER = Array.from({ length: 6 }, (_, i) => mk("fill-" + i, 10 + i, { context: LONG }));

for (const scheme of ["light", "dark"]) {
  test(`an answered card keeps its height only while in view, then shrinks with nothing on screen moving, ${scheme} scheme`, async (t) => {
    const target = mk("target", 2, { context: LONG });
    const items = [mk("above", 1, { context: LONG }), target, ...FILLER];
    const page = await open(t, { items, scheme, viewport: { width: 1280, height: 700 } }); if (!page) return;
    await noAnchor(page);
    const c = card(page, target);
    const full = (await c.boundingBox()).height;
    await choose(page, target, "a");
    await send(page);
    await c.locator(".receipt").waitFor();
    assert.ok((await c.boundingBox()).height >= full - 1, "the receipt gave up its height while still in view");
    // Scroll the receipt out of view above the screen, with a card on screen as the witness.
    const witness = card(page, FILLER[3]);
    await witness.scrollIntoViewIfNeeded();
    await page.evaluate(() => window.scrollBy(0, 300));
    const top = () => witness.evaluate((e) => Math.round(e.getBoundingClientRect().top));
    const at = await top();
    await page.waitForFunction(() => document.getElementById("item-target").getBoundingClientRect().bottom < 0);
    await page.waitForFunction(([id, h]) => document.getElementById(id).getBoundingClientRect().height < h - 100, ["item-target", full]);
    assert.ok(Math.abs((await top()) - at) <= 1, "what was on screen moved when the receipt shrank");
  });
}

for (const scheme of ["light", "dark"]) for (const width of SIZES) {
  test(`the rail's related-item frames and chips fit the rail at ${width}px wide, ${scheme} scheme`, async (t) => {
    const long = "A very long title that runs across the whole width of the rail and then some more ";
    const items = [1, 2, 3].map((n) => mk("pr-" + n, n, { group: "pair", title: long + n })).concat([mk("alone", 4, { title: long + "alone" })]);
    const page = await open(t, { items, scheme, viewport: { width, height: 900 }, groups: { pair: { title: "Answer these together", why: "Linked." } } }); if (!page) return;
    const m = await page.evaluate(() => {
      const r = (e) => { const b = e.getBoundingClientRect(); return { l: b.left, r: b.right }; };
      const rail = document.querySelector(".rail"), ov = rail.getBoundingClientRect();
      const frames = [...rail.querySelectorAll(".pairchips")].map(r), chips = [...rail.querySelectorAll(".nchip")].map(r);
      return { rail: r(rail), railW: ov.width, frames, chips, list: r(document.querySelector(".list")), sw: document.documentElement.scrollWidth, iw: innerWidth, stacked: innerWidth <= 960 };
    });
    assert.ok(m.frames.length >= 1, "no related-item frame in the rail");
    const slack = 1;
    for (const f of m.frames) assert.ok(f.l >= m.rail.l - slack && f.r <= m.rail.r + slack, `a frame runs past the rail: ${JSON.stringify(f)} in ${JSON.stringify(m.rail)}`);
    for (const c of m.chips) assert.ok(c.l >= m.rail.l - slack && c.r <= m.rail.r + slack, `a chip runs past the rail: ${JSON.stringify(c)} in ${JSON.stringify(m.rail)}`);
    if (!m.stacked) { assert.ok(m.railW <= 240 + slack, "the rail grew past 240px: " + m.railW); assert.ok(m.rail.r <= m.list.l + slack, "the rail overlaps the cards"); }
    assert.ok(m.sw <= m.iw, "the page scrolls sideways");
  });

  for (const [kind, extra] of [["declared size", { size: { w: 390, h: 844 } }], ["no declared size", {}], ["a focused part", { focus: "#hero", size: { w: 300, h: 200 } }]]) test(`an option's picture (${kind}) sits inside its option card at ${width}px wide, ${scheme} scheme`, async (t) => {
    const it = mk("fit-pics", 1, { options: LOOK_OPTS, pick: "a", designs: LOOK_OPTS.map((o) => ({ slug: o.design, label: o.label, ...extra })) });
    const phone = (k) => `<body style="margin:0"><div id="hero" style="width:300px;height:200px;background:#9cf">${k}</div><div style="height:644px;width:390px;background:#eee"></div></body>`;
    const designData = Object.fromEntries(LOOK_OPTS.map((o) => [o.design, phone(o.design)]));
    const page = await open(t, { items: [it], designData, scheme, viewport: { width, height: 900 } }); if (!page) return;
    await card(page, it).locator("label.opt .dfitwrap").first().scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    const m = await page.evaluate((id) => [...document.querySelectorAll(`#item-${id} label.opt`)].map((o) => {
      const b = o.getBoundingClientRect(), pw = o.querySelector(".dfitwrap"), w = pw.getBoundingClientRect();
      const text = [...o.querySelectorAll(".how, .lab, .tr, .pick, .nopick, .dwarn")].map((x) => x.getBoundingClientRect()).filter((x) => x.height > 0);
      return { card: [b.left, b.top, b.right, b.bottom], wrap: [w.left, w.top, w.right, w.bottom], text: text.map((x) => [x.top, x.bottom]) };
    }), it.id);
    for (const o of m) {
      assert.ok(o.wrap[0] >= o.card[0] - 1 && o.wrap[2] <= o.card[2] + 1, "the picture runs past the sides of its card: " + JSON.stringify(o));
      assert.ok(o.wrap[1] >= o.card[1] - 1 && o.wrap[3] <= o.card[3] + 1, "the picture runs past the bottom of its card: " + JSON.stringify(o));
      for (const [tt, tb] of o.text) assert.ok(tt >= o.wrap[3] - 1 || tb <= o.wrap[1] + 1, "the picture covers text: " + JSON.stringify(o));
    }
  });
}

test("a rail jump after Send still lands on its card when held receipts drop mid-scroll", async (t) => {
  const items = Array.from({ length: 14 }, (_, i) => mk("q" + i, i + 1, { context: LONG }));
  const page = await open(t, { items, viewport: { width: 1280, height: 800 } }); if (!page) return;
  await noAnchor(page);
  await choose(page, items[0], "a"); await choose(page, items[1], "a");
  await send(page);
  await page.locator("#item-q0 .receipt").waitFor();
  await page.click("#c-q9");
  await page.waitForTimeout(2500);
  const top = await card(page, items[9]).evaluate((e) => Math.round(e.getBoundingClientRect().top));
  assert.ok(top >= 0 && top <= 120, "the jump missed its card; it sits at " + top);
});

test("a receipt wholly below the screen drops its height without moving the page", async (t) => {
  const items = Array.from({ length: 40 }, (_, i) => mk("q" + i, i + 1, { context: LONG }));
  const page = await open(t, { items, viewport: { width: 390, height: 360 } }); if (!page) return;
  await noAnchor(page);
  await choose(page, items[0], "a");
  await page.evaluate(() => window.scrollTo(0, 60));
  const railTop = () => page.evaluate(() => Math.round(document.querySelector(".ov-prog").getBoundingClientRect().top));
  const at = await railTop();
  await send(page);
  await page.locator("#item-q0 .receipt").waitFor();
  await page.waitForTimeout(600);
  assert.ok(Math.abs((await railTop()) - at) <= 1, "the page moved when an off-screen receipt shrank");
});

// A phone mockup shows whole, so the design caps its height at 480px (docs/design/c193-sizes.md item 3); it scales to its card and stays centred.
for (const width of SIZES) test(`an option's picture is at most 480px high and centred in its card at ${width}px wide`, async (t) => {
  const it = mk("cap-pics", 1, { options: LOOK_OPTS, pick: "a", designs: LOOK_OPTS.map((o) => ({ slug: o.design, label: o.label, size: { w: 390, h: 844 } })) });
  const designData = Object.fromEntries(LOOK_OPTS.map((o) => [o.design, '<body style="margin:0"><div style="width:390px;height:844px;background:#eee"></div></body>']));
  const page = await open(t, { items: [it], designData, viewport: { width, height: 900 } }); if (!page) return;
  await card(page, it).locator("label.opt .dfitwrap").first().scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  const m = await page.evaluate((id) => [...document.querySelectorAll(`#item-${id} label.opt .opic`)].map((o) => { const w = o.querySelector(".dfitwrap").getBoundingClientRect(), b = o.getBoundingClientRect(); return { h: w.height, w: w.width, off: Math.abs((w.left + w.right) / 2 - (b.left + b.right) / 2), room: b.width }; }), it.id);
  for (const o of m) {
    assert.ok(o.h <= 481, "the picture is taller than 480px: " + o.h);
    assert.ok(o.w <= Math.min(390, o.room) + 1, "the picture is wider than its card or the mockup: " + JSON.stringify(o));
    assert.ok(o.off <= 1, "the picture is not centred: " + JSON.stringify(o));
  }
});

// The stamp settles in 200ms with no overshoot, and reduced motion shows it still (docs/design/c193-sizes.md item 4), so the bar is calm and still reads as sent.
const sentPage = async (t, reduce) => {
  const page = await open(t); if (!page) return null;
  if (reduce) await page.emulateMedia({ reducedMotion: "reduce" });
  await choose(page, DECISION, "a"); await send(page);
  await page.locator("#sent .stamp").waitFor();
  return page;
};
test("the SENT stamp settles in 200ms with no overshoot", async (t) => {
  const page = await sentPage(t, false); if (!page) return;
  const a = await page.locator("#sent .stamp").evaluate((e) => { const s = getComputedStyle(e); return [s.animationName, s.animationDuration, s.animationTimingFunction]; });
  assert.deepEqual(a, ["stamp-settle", "0.2s", "cubic-bezier(0.2, 0, 0, 1)"]);
});
test("reduced motion shows the SENT stamp still", async (t) => {
  const page = await sentPage(t, true); if (!page) return;
  assert.equal(await page.locator("#sent .stamp").evaluate((e) => getComputedStyle(e).animationName), "none");
});
test("the Sent bar keeps its parts on the page's spacing steps", async (t) => {
  const page = await sentPage(t, false); if (!page) return;
  const m = await page.evaluate(() => {
    const px = (sel, prop) => parseFloat(getComputedStyle(document.querySelector(sel))[prop]);
    return { pad: px("#sent .in", "paddingTop"), head: px("#sent .sent-head", "columnGap"), what: px("#sent .sent-what", "rowGap"), stamp: Math.round(document.querySelector("#sent .stamp").offsetHeight), inList: !!document.querySelector("#sent .sent-what .sent-list"), li: Math.round(document.querySelector("#sent .sent-list li").getBoundingClientRect().height) };
  });
  assert.deepEqual(m, { pad: 16, head: 16, what: 8, stamp: 48, inList: true, li: 28 });
});

// One containment sweep catches overflow of any kind on every state and width. A new item state is one row in STATES, a new width one entry in SWEEP_WIDTHS.
const SWEEP_WIDTHS = [320, 390, 768, 1024, 1280, 1600, 2200, 2560];
const LONGT = "A very long title that runs across the whole width of the rail and then some more ";
const TALL = '<body style="margin:0"><div style="width:390px;height:844px;background:#eee"></div></body>';
const STATES = [
  ["open", () => ({ items: [DECISION, TASK] })],
  ["draft ready", () => ({ items: [DECISION, TASK] }), (page) => choose(page, DECISION, "a")],
  ["answered, filing pending", () => ({ items: [DECISION, TASK], answers: SAVED_A })],
  ["answered, filed", () => ({ items: [DECISION, TASK], answers: SAVED_A, receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z", filed: "2026-10-26T03:00:00Z" } } })],
  ["answered, read", () => ({ items: [DECISION, TASK], answers: SAVED_A, receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z" } } })],
  ["bundle", () => ({ items: [1, 2, 3].map((n) => mk("sw-" + n, n, { group: "pair", title: LONGT + n })), groups: { pair: { title: "Answer these together", why: "Linked." } } })],
  ["pictures", () => ({ items: [mk("sw-pics", 1, { options: LOOK_OPTS, pick: "a", designs: LOOK_OPTS.map((o) => ({ slug: o.design, label: o.label, size: { w: 390, h: 844 } })) })], designData: Object.fromEntries(LOOK_OPTS.map((o) => [o.design, TALL])) })],
  ["task", () => ({ items: [TASK] })],
  ["stands", () => ({ items: [mk("sw-s1", 7, { stands: true }), mk("sw-s2", 8, { stands: true })] })],
  ["sent bar", () => ({ items: [DECISION, TASK] }), async (page) => { await choose(page, DECISION, "a"); await send(page); await page.locator("#sent .stamp").waitFor(); }],
];
// Runs in the page. Returns what crosses a box, sticks out sideways, or is cut without an ellipsis.
function sweepPage() {
  const bad = [], tol = 1.5;
  const name = (e) => e.tagName.toLowerCase() + (e.id ? "#" + e.id : "") + (e.className && typeof e.className === "string" ? "." + e.className.trim().split(/\s+/).join(".") : "");
  const boxes = [...document.querySelectorAll("article.card, #rail, #sent .in")].filter((b) => b.getBoundingClientRect().width > 0);
  for (const box of boxes) {
    const bb = box.getBoundingClientRect();
    for (const e of box.querySelectorAll("*")) {
      const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
      if (!r.width || !r.height || cs.display === "contents" || e.closest(".sr, [hidden]") || cs.position === "fixed" || (e.closest(".dfitwrap") && !e.classList.contains("dfitwrap")) || cs.visibility === "hidden") continue;
      if (r.left < bb.left - tol || r.right > bb.right + tol || r.top < bb.top - tol || r.bottom > bb.bottom + tol) bad.push("outside " + name(box) + ": " + name(e) + " " + [r.left, r.right, bb.left, bb.right].map(Math.round));
      if ((cs.overflowX === "hidden" || cs.overflowX === "clip") && e.scrollWidth > e.clientWidth + 1 && cs.textOverflow !== "ellipsis" && !e.classList.contains("dfitwrap") && !e.closest(".dfitwrap") && !cs.webkitLineClamp.match(/^[1-9]/) && !e.classList.contains("opic")) bad.push("clipped: " + name(e));
    }
  }
  if (document.documentElement.scrollWidth > innerWidth) bad.push("page scrolls sideways: " + document.documentElement.scrollWidth + " > " + innerWidth);
  return bad;
}
test("containment sweep: nothing crosses its card, the rail or the Sent bar, nothing is cut without an ellipsis, no sideways scroll", async (t) => {
  const failures = [];
  for (const scheme of ["light", "dark"]) for (const width of SWEEP_WIDTHS) for (const [state, make, act] of STATES) {
    const page = await open(t, { ...make(), scheme, viewport: { width, height: 900 } }); if (!page) return;
    if (act) await act(page);
    await page.waitForTimeout(150);
    for (const b of await page.evaluate(sweepPage)) failures.push(`${state} @${width} ${scheme}: ${b}`);
    await page.close();
  }
  assert.deepEqual(failures, []);
});

// Edge cases the sweep's fixed fixtures miss: resizing a card, a very tall mockup, the stamp across Undo ticks, a bar that must not jump.
const growItem = () => mk("grow-pics", 1, { options: LOOK_OPTS, pick: "a", designs: LOOK_OPTS.map((o) => ({ slug: o.design, label: o.label, size: { w: 390, h: 844 } })) });
const growData = (h) => Object.fromEntries(LOOK_OPTS.map((o) => [o.design, `<body style="margin:0"><div style="width:390px;height:${h}px;background:#eee"></div></body>`]));
const picBox = (page) => page.evaluate(() => [...document.querySelectorAll("#item-grow-pics label.opt")].map((o) => { const w = o.querySelector(".dfitwrap").getBoundingClientRect(), b = o.querySelector(".opic").getBoundingClientRect(); return { w: Math.round(w.width), over: Math.round(Math.max(b.left - w.left, w.right - b.right, 0)) }; }));

test("a capped picture grows back when its card widens and stays inside when it narrows", async (t) => {
  const page = await open(t, { items: [growItem()], designData: growData(844), viewport: { width: 1070, height: 900 } }); if (!page) return;
  await page.waitForTimeout(300);
  const narrow = (await picBox(page))[0].w;
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.waitForTimeout(400);
  const wide = await picBox(page);
  assert.ok(wide[0].w > narrow + 10, `the picture did not grow back: ${narrow} then ${wide[0].w}`);
  await page.setViewportSize({ width: 1066, height: 900 });
  await page.waitForTimeout(400);
  for (const b of await picBox(page)) assert.ok(b.over <= 1, "the picture runs past its card after narrowing: " + b.over);
});

test("a very tall mockup with no focus is never a thin strip", async (t) => {
  const page = await open(t, { items: [growItem()], designData: growData(3000), viewport: { width: 1280, height: 900 } }); if (!page) return;
  await page.waitForTimeout(400);
  for (const b of await picBox(page)) assert.ok(b.w >= 120, "the picture is a strip, " + b.w + "px wide");
});

test("the SENT stamp is the same element, not rebuilt, as the Undo count ticks", async (t) => {
  const page = await sentPage(t, false); if (!page) return;
  await page.evaluate(() => { window.__stamp = document.querySelector("#sent .stamp"); });
  await page.waitForTimeout(2300);
  assert.equal(await page.evaluate(() => window.__stamp.isConnected && window.__stamp === document.querySelector("#sent .stamp")), true, "the stamp was rebuilt, so it settles again each second");
  assert.match(await page.locator("#undoBtn").textContent(), /Undo send \(\d\)/);
});

for (const width of [390, 500, 600, 1280]) test(`the Sent bar keeps its height when the Undo button goes, at ${width}px wide`, async (t) => {
  const page = await open(t, { viewport: { width, height: 900 } }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#undoBtn").waitFor();
  const h = () => page.locator("#sent").evaluate((e) => Math.round(e.getBoundingClientRect().height));
  const before = await h();
  await page.locator("#undoBtn").waitFor({ state: "detached", timeout: 9500 });
  assert.ok(Math.abs((await h()) - before) <= 1, `the bar jumped from ${before} to ${await h()}`);
});

test("a receipt with no Read by centres its label and Change on one line", async (t) => {
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  const m = await card(page, DECISION).locator(".receipt .line").evaluate((l) => { const mid = (e) => { const r = e.getBoundingClientRect(); return (r.top + r.bottom) / 2; }; return [mid(l.querySelector("b")), mid(l.querySelector(".changebtn"))]; });
  assert.ok(Math.abs(m[0] - m[1]) <= 2, "the label and Change are not level: " + m);
});

test("a related-item frame of seven wraps its chips on a phone and keeps each chip at 48px", async (t) => {
  const items = Array.from({ length: 7 }, (_, i) => mk("w-" + i, i + 1, { group: "seven", title: "Item " + i }));
  const page = await open(t, { items, viewport: { width: 390, height: 900 }, groups: { seven: { title: "Seven together", why: "Linked." } } }); if (!page) return;
  const w = await page.evaluate(() => [...document.querySelectorAll(".rail .pairchips .nchip")].map((c) => Math.round(c.getBoundingClientRect().width)));
  assert.equal(w.length, 7);
  assert.ok(w.every((x) => x >= 48), "a chip shrank: " + w);
});

// ---------------------------------------------------------------- c139: an option that widens a shared tool

test("an option that widens a shared tool says it goes against the uniform ruling; other options do not", async (t) => {
  const it = mk("wide-q", 79, { pick: "b", options: [
    { key: "a", label: "Let the tool accept a second form", how: "h", gain: "g", lose: "l", widens: true },
    { key: "b", label: "The repo matches the shared form", how: "h", gain: "g", lose: "l" },
  ] });
  const page = await open(t, { items: [it] }); if (!page) return;
  const a = card(page, it).locator('label.opt[for="o-wide-q-a"]'), b = card(page, it).locator('label.opt[for="o-wide-q-b"]');
  assert.equal(await a.locator(".widens").count(), 1, "the widening option carries no label");
  assert.equal((await a.locator(".widens").innerText()).trim(), "Goes against your uniform ruling (t18)");
  assert.equal(await b.locator(".widens").count(), 0, "an option that does not widen is labelled");
});

test("the answered pill keeps a 6px gap between its wrapped rows, as the design draws it", async (t) => {
  const page = await open(t, { answers: SAVED_A, viewport: { width: 390, height: 900 } }); if (!page) return;
  assert.equal(await card(page, DECISION).locator(".ans").evaluate((e) => getComputedStyle(e).rowGap), "6px");
});

test("option pictures of different heights keep the View bars at 44px", async (t) => {
  const it = growItem();
  const data = Object.fromEntries(LOOK_OPTS.map((o, i) => [o.design, `<body style="margin:0"><div style="width:390px;height:${[844, 300, 560][i]}px;background:#eee"></div></body>`]));
  const it2 = { ...it, designs: it.designs.map((d, i) => ({ ...d, size: { w: 390, h: [844, 300, 560][i] } })) };
  const page = await open(t, { items: [it2], designData: data, viewport: { width: 1280, height: 900 } }); if (!page) return;
  await page.waitForTimeout(400);
  const hs = await page.evaluate(() => [...document.querySelectorAll("#item-grow-pics .opic .view")].map((v) => Math.round(v.getBoundingClientRect().height)));
  assert.deepEqual(hs, [44, 44, 44]);
});

test("a long unbroken receipt label wraps clear of Change at 320px", async (t) => {
  const it = { ...DECISION, options: [{ key: "a", label: "skills/waiting-page/tests/page.test.mjs-and-more", how: "h", gain: "g", lose: "l" }, DECISION.options[1]] };
  const page = await open(t, { items: [it], answers: SAVED_A, viewport: { width: 320, height: 900 } }); if (!page) return;
  const m = await card(page, it).locator(".receipt .line").evaluate((l) => ({ b: l.querySelector("b").getBoundingClientRect().right, c: l.querySelector(".changebtn").getBoundingClientRect().left }));
  assert.ok(m.b <= m.c + 1, "the label runs under Change: " + JSON.stringify(m));
});

test("a decision card with no differs mark shows no stray null or undefined text", async (t) => {
  const page = await open(t); if (!page) return;
  const stray = await page.evaluate((id) => {
    const w = document.createTreeWalker(document.getElementById("item-" + id), NodeFilter.SHOW_TEXT);
    const bad = [];
    for (let n = w.nextNode(); n; n = w.nextNode()) { const s = n.textContent.trim(); if (s === "null" || s === "undefined") bad.push(s); }
    return bad;
  }, DECISION.id);
  assert.deepEqual(stray, [], "stray text in the decision card");
});

// ---------------------------------------------------------------- c135: a question that takes several answers
// Spec: the c135 spec (Data, Answer, Page). Labels: docs/design/c135-multi.html. A multi item sets `multi: true`; `ranked: true` also orders the ticks.

// The one home of the multi fixtures; a case adds only its own fields. Option keys a to d show as letters A to D.
const COLOURS = [opt("a", "Red"), opt("b", "Blue"), opt("c", "Green"), opt("d", "Yellow")];
const multi = (id, n, over = {}) => mk(id, n, { multi: true, options: COLOURS.slice(0, 3), pick: ["a", "c"], why: "Red and Green cover it.", ...over });
const ranked = (id, n, over = {}) => multi(id, n, { ranked: true, options: COLOURS, pick: ["c", "a", "d"], ...over });
// Item 31's shape: options that can coexist, which were asked as pick-one.
const digest = (over = {}) => multi("digest", 31, { title: "Which reminders should the weekly digest send?", options: [opt("a", "Open items older than a week"), opt("b", "Picks that stood"), opt("c", "Answers that failed to save")], why: "Old items and lost answers cost you time.", ...over });
const boxes = (page, it) => card(page, it).locator(".opts input[type=checkbox]");
// The keys ticked now, in option order.
const ticked = (page, it) => page.evaluate((id) => [...document.querySelectorAll(`#item-${id} .opts input`)].filter((i) => i.checked).map((i) => i.value), it.id);
// Every case starts here, so a page that still draws the item as pick-one fails on this line.
const needBoxes = async (page, it, n) => assert.equal(await boxes(page, it).count(), n, `item ${it.n} has no ${n} checkboxes: it is drawn as pick-one`);
// A ranked card's label stretches over the whole card, so a press on its text lands on that label: press the label.
const tick = (page, it, key) => (it.ranked ? page.locator(`label[for="o-${it.id}-${key}"]`).click() : choose(page, it, key));
const labelOf = (it, key) => it.options.find((o) => o.key === key).label;
// Take my pick keeps its place when it does not apply (`.gone`, visibility hidden), so a hidden one is still one element in the card.
const takeShown = async (page, it) => {
  const b = page.locator(`#b-take-${it.id}`);
  assert.equal(await b.count(), 1, `${it.id}: Take my pick left its place in the card`);
  return b.isVisible();
};
const rankText = (page, it, key) => page.locator(`#item-${it.id} .opt:has(#o-${it.id}-${key})`).textContent();
// "2nd of 3". A card's text runs its spans together with no space, so a digit guard stands in for a word boundary.
const rank = (ord, n) => new RegExp(`(?<!\\d)${ord} of ${n}(?!\\d)`);
const moveBtn = (page, it, key, dir) => card(page, it).getByRole("button", { name: `Move ${labelOf(it, key)} ${dir}`, exact: true });
const sendOne = async (page, it) => { await send(page); await page.waitForFunction((id) => !!window.__answers()[id], it.id); return (await answers(page))[it.id]; };

test("a multi item draws checkboxes in a group, and two ticks send choice as a list of both keys", async (t) => {
  const it = digest();
  const page = await open(t, { items: [it] }); if (!page) return;
  const c = card(page, it);
  await needBoxes(page, it, 3);
  assert.equal(await c.getByRole("radiogroup").count(), 0, "the options are still a radiogroup");
  assert.equal(await c.getByRole("group", { name: /Options for No\. 31/ }).count(), 1, "the options are not a group");
  assert.equal(await c.locator("input[type=radio]").count(), 0, "a radio is left on a multi item");
  await choose(page, it, "a"); await choose(page, it, "c");
  assert.deepEqual(await ticked(page, it), ["a", "c"]);
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer");
  const a = await sendOne(page, it);
  assert.deepEqual([a.item, a.n, a.choice, a.note], [it.id, 31, ["a", "c"], ""]);
});

test("a ranked item: three ticks, one Up, and Send writes the list in the order shown", async (t) => {
  const it = ranked("rk-send", 32);
  const page = await open(t, { items: [it] }); if (!page) return;
  await needBoxes(page, it, 4);
  for (const k of ["c", "a", "d"]) await tick(page, it, k);
  assert.deepEqual(await ticked(page, it), ["a", "c", "d"]);
  for (const [k, r] of [["c", "1st"], ["a", "2nd"], ["d", "3rd"]]) assert.match(await rankText(page, it, k), rank(r, 3), `rank of ${k}`);
  await moveBtn(page, it, "a", "up").click();
  for (const [k, r] of [["a", "1st"], ["c", "2nd"], ["d", "3rd"]]) assert.match(await rankText(page, it, k), rank(r, 3), `rank of ${k} after Up`);
  const a = await sendOne(page, it);
  assert.deepEqual([a.choice, a.note], [["a", "c", "d"], ""]);
});

test("a ranked item: a new tick goes last and an untick closes the gap", async (t) => {
  const it = ranked("rk-gap", 32);
  const page = await open(t, { items: [it] }); if (!page) return;
  await needBoxes(page, it, 4);
  await tick(page, it, "c"); await tick(page, it, "a");
  assert.match(await rankText(page, it, "c"), rank("1st", 2));
  assert.match(await rankText(page, it, "a"), rank("2nd", 2));
  await tick(page, it, "d"); await tick(page, it, "b");
  assert.match(await rankText(page, it, "d"), rank("3rd", 4), "a new tick did not go last");
  assert.match(await rankText(page, it, "b"), rank("4th", 4));
  await tick(page, it, "a"); // untick the 2nd
  for (const [k, r] of [["c", "1st"], ["d", "2nd"], ["b", "3rd"]]) assert.match(await rankText(page, it, k), rank(r, 3), `rank of ${k} after the untick`);
  assert.match(await rankText(page, it, "a"), /Not in your order/);
  const a = await sendOne(page, it);
  assert.deepEqual(a.choice, ["c", "d", "b"]);
});

// Option a's three text rows are marked as what sets it apart. Each text differs from the others', so the page keeps every mark.
const MARKED = [{ ...opt("a", "Red"), how: "how A", gain: "gain A", lose: "lose A", differs: ["how", "gain", "lose"] }, opt("b", "Blue"), opt("c", "Green")];

test("a press on a marked row ticks its option, on a ranked card as on a plain multi card", async (t) => {
  const m = multi("dif-m", 34, { options: MARKED }), r = ranked("dif-r", 35, { options: MARKED });
  const page = await open(t, { items: [m, r] }); if (!page) return;
  await needBoxes(page, m, 3); await needBoxes(page, r, 3);
  // The marked row paints above the ranked card's stretched label, so a real press at its centre must still reach the label. `force` keeps a fix that
  // lays the label above the row from failing on "intercepts pointer events"; the press itself is still a real one at the row's centre.
  for (const it of [m, r]) for (const row of ["how", "gain", "lose"]) {
    const mark = page.locator(`#item-${it.id} .opt:has(#o-${it.id}-a) .${row}.dif`);
    assert.equal(await mark.count(), 1, `${it.id}: the ${row} row is not marked`);
    await mark.click({ force: true });
    assert.deepEqual(await ticked(page, it), ["a"], `${it.id}: a press on the marked ${row} row did not tick its option`);
    await mark.click({ force: true });
    assert.deepEqual(await ticked(page, it), [], `${it.id}: a second press on the marked ${row} row did not untick it`);
  }
});

test("Take my pick on a multi item writes the whole pick list with the note accepted pick, ranked or not", async (t) => {
  const m = digest(), r = ranked("rk-take", 32);
  const page = await open(t, { items: [m, r] }); if (!page) return;
  await needBoxes(page, m, 3); await needBoxes(page, r, 4);
  const take = card(page, m).getByRole("button", { name: /Take my pick/ });
  assert.match(await take.textContent(), /^Take my pick \(.*Open items.*Answers that.*\)$/, "the button does not name both picks by title");
  await take.click(); await takePick(page, r);
  assert.deepEqual(await ticked(page, m), ["a", "c"]);
  assert.deepEqual(await ticked(page, r), ["a", "c", "d"]);
  for (const [k, n] of [["c", "1st"], ["a", "2nd"], ["d", "3rd"]]) assert.match(await rankText(page, r, k), rank(n, 3), `rank of ${k}`);
  assert.equal(await takeShown(page, m), false, "Take my pick is not hidden after it was taken");
  assert.equal(await takeShown(page, r), false, "Take my pick is not hidden on a ranked item after it was taken");
  assert.match(await card(page, m).locator(".ready").textContent(), /, my pick\.$/);
  assert.equal(await page.locator("#send").textContent(), "Send 2 answers");
  await send(page);
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 2);
  const a = await answers(page);
  assert.deepEqual([a[m.id].choice, a[m.id].note], [["a", "c"], "accepted pick"]);
  assert.deepEqual([a[r.id].choice, a[r.id].note], [["c", "a", "d"], "accepted pick"]);
});

test("a note on a multi item with nothing ticked is choice none plus the note; with ticks it rides on the list", async (t) => {
  const bare = digest(), withTicks = multi("note-ticks", 32);
  const page = await open(t, { items: [bare, withTicks] }); if (!page) return;
  await needBoxes(page, bare, 3); await needBoxes(page, withTicks, 3);
  await addNote(page, bare, "Only the failed ones, as a push");
  await choose(page, withTicks, "a"); await choose(page, withTicks, "b");
  await addNote(page, withTicks, "push too");
  await send(page);
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 2);
  const a = await answers(page);
  assert.deepEqual([a[bare.id].choice, a[bare.id].note], ["none", "Only the failed ones, as a push"]);
  assert.deepEqual([a[withTicks.id].choice, a[withTicks.id].note], [["a", "b"], "push too"]);
});

test("None of these on a multi item clears the ticks, needs a note, and sends the string none", async (t) => {
  const it = digest();
  const page = await open(t, { items: [it] }); if (!page) return;
  await needBoxes(page, it, 3);
  await choose(page, it, "a");
  await card(page, it).getByRole("button", { name: "None of these" }).click();
  assert.deepEqual(await ticked(page, it), [], "a tick stayed beside None of these");
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is open on None of these with no note");
  await page.fill(`#n-${it.id}`, "Only a push");
  const a = await sendOne(page, it);
  assert.deepEqual([a.choice, a.note], ["none", "Only a push"]);
});

test("keys A to C toggle an option on a multi item, ranked or not", async (t) => {
  const m = digest(), r = ranked("rk-keys", 32);
  const page = await open(t, { items: [m, r] }); if (!page) return;
  await needBoxes(page, m, 3); await needBoxes(page, r, 4);
  await card(page, m).locator(".title").click();
  await page.keyboard.press("a"); await page.keyboard.press("c");
  assert.deepEqual(await ticked(page, m), ["a", "c"], "a key did not tick its option");
  await page.keyboard.press("a");
  assert.deepEqual(await ticked(page, m), ["c"], "a second press did not untick");
  await card(page, r).locator(".title").click();
  await page.keyboard.press("c"); await page.keyboard.press("a");
  assert.match(await rankText(page, r, "c"), rank("1st", 2));
  assert.match(await rankText(page, r, "a"), rank("2nd", 2));
  assert.deepEqual(await ticked(page, m), ["c"], "a key on the ranked card ticked the other card");
});

test("a saved multi answer lists each pick with its letter and title in order, and Change puts the list back", async (t) => {
  const m = digest(), r = ranked("rk-saved", 32);
  const at = "2026-10-26T01:00:00Z";
  const page = await open(t, { items: [m, r], answers: { [m.id]: { item: m.id, n: 31, at, choice: ["a", "c"], note: "" }, [r.id]: { item: r.id, n: 32, at, choice: ["c", "a", "d"], note: "" } } }); if (!page) return;
  const rows = async (c, tag) => (await c.locator(`.receipt ${tag} li`).allTextContents()).map((s) => s.replace(/\s+/g, " ").trim());
  const mr = await rows(card(page, m), "ul"), rr = await rows(card(page, r), "ol");
  assert.equal(mr.length, 2, "the saved card does not list the picks as a bullet list: " + mr);
  assert.match(mr[0], /^A\W*Open items older than a week$/); assert.match(mr[1], /^C\W*Answers that failed to save$/);
  assert.equal(rr.length, 3, "the saved ranked card does not list the picks as a numbered list: " + rr);
  assert.match(rr[0], /^C\W*Green$/); assert.match(rr[1], /^A\W*Red$/); assert.match(rr[2], /^D\W*Yellow$/);
  assert.match(await card(page, m).locator(".receipt").textContent(), /You chose:/);
  assert.match(await card(page, r).locator(".receipt").textContent(), /You chose, in order:/);
  await card(page, r).getByRole("button", { name: "Change" }).click();
  assert.deepEqual(await ticked(page, r), ["a", "c", "d"]);
  assert.match(await rankText(page, r, "c"), rank("1st", 3), "Change lost the order");
  assert.match(await rankText(page, r, "a"), rank("2nd", 3));
});

test("the ready line names the picks by title, shortened, never by letter, a ranked line gives the order, and Take my pick hides once the ticks equal my pick", async (t) => {
  const m = multi("rd-m", 41, { options: WORDY, pick: ["value", "watch"] }), r = ranked("rd-r", 42, { options: WORDY, pick: ["nothing", "value"] });
  const page = await open(t, { items: [m, r] }); if (!page) return;
  await needBoxes(page, m, 3); await needBoxes(page, r, 3);
  const ready = (it) => card(page, it).locator(".ready").textContent();
  assert.equal(await ready(m), "", "a ready line shows before a tick");
  await tick(page, m, "value"); await tick(page, m, "watch");
  assert.match(await ready(m), /^Ready to send: Value for the card.*… and Watch, your choice\.$/);
  await tick(page, m, "nothing");
  const three = await ready(m);
  assert.ok(three.indexOf("Value for the card") < three.indexOf("Watch") && three.indexOf("Watch") < three.indexOf("Nothing") && /^Ready to send: /.test(three) && / and /.test(three), "three picks are not named in a list: " + three);
  // The same two picks in another order than my pick (nothing, then value): the button stays, and it names my pick by title.
  await tick(page, r, "value"); await tick(page, r, "nothing");
  assert.match(await ready(r), /^Ready to send: Value for the card.*…, Nothing, your order\.$/);
  assert.equal(await takeShown(page, r), true, "Take my pick is hidden while the order differs from my pick");
  assert.match(await card(page, r).getByRole("button", { name: /Take my pick/ }).textContent(), /^Take my pick \(Nothing.*Value for the card.*…\)$/, "Take my pick does not name the picks by title");
  await takePick(page, r);
  assert.match(await ready(r), /^Ready to send: Nothing.*Value for the card.*…, my pick\.$/);
  assert.equal(await takeShown(page, r), false, "Take my pick is not hidden once the ticks equal my pick");
  // Ticking exactly my pick by hand hides it too, and the line says the order is the owner's.
  await tick(page, r, "value"); await tick(page, r, "nothing");
  await tick(page, r, "nothing");
  assert.equal(await takeShown(page, r), true, "Take my pick is hidden while only part of my pick is ticked");
  await tick(page, r, "value");
  assert.equal(await takeShown(page, r), false, "Take my pick is not hidden after the owner ticked exactly my pick");
  assert.match(await ready(r), /^Ready to send: Nothing.*Value for the card.*…, your order\.$/);
});

// An unranked multi item has no order to keep: its ticks stay in option order, whatever order they were ticked in (ruling of 15:55 CDT, c135 round 3).
test("an unranked multi item keeps its ticks in option order: C then A equals my pick a+c, hides Take my pick, and the answer and the notice read a+c", async (t) => {
  const it = multi("un-order", 61, { pick: ["a", "c"] });
  const page = await open(t, { items: [it] }); if (!page) return;
  await needBoxes(page, it, 3);
  await tick(page, it, "c");
  assert.equal(await takeShown(page, it), true, "Take my pick is hidden while only C is ticked");
  await tick(page, it, "a");
  assert.deepEqual(await ticked(page, it), ["a", "c"]);
  assert.equal(await takeShown(page, it), false, "Take my pick is not hidden after C then A, the same set as my pick");
  assert.match(await card(page, it).locator(".ready").textContent(), /^Ready to send: Red and Green, your choice\.$/, "the ready line does not name the ticks in option order");
  await send(page);
  await told(page, "Claude was told");
  const a = (await answers(page))[it.id];
  assert.deepEqual([a.choice, a.note], [["a", "c"], ""], "the answer is not in option order");
  const s = await sent(page);
  assert.equal(s.length, 1);
  assert.match(s[0].text, /(?<!\d)61 a\+c(?![+\w])/, "the notice does not read a+c: " + s[0].text);
});

// An unranked multi pick out of option order must not keep Take my pick: an unranked pick is saved and compared in option order;
// a ranked pick keeps the order it was ticked or picked in.
test("a multi item whose pick is out of option order: option-order ticks hide Take my pick, Take my pick saves option order, and a ranked pick keeps its order", async (t) => {
  const uHand = multi("po-u-hand", 81, { pick: ["c", "a"] }), uTake = multi("po-u-take", 82, { pick: ["c", "a"] });
  const rHand = ranked("po-r-hand", 83), rTake = ranked("po-r-take", 84);
  const page = await open(t, { items: [uHand, uTake, rHand, rTake] }); if (!page) return;
  await needBoxes(page, uHand, 3); await needBoxes(page, uTake, 3); await needBoxes(page, rHand, 4); await needBoxes(page, rTake, 4);
  for (const k of ["c", "a", "d"]) await tick(page, rHand, k);
  assert.equal(await takeShown(page, rHand), false, "a ranked item ticked in its pick order: Take my pick is not hidden");
  await tick(page, uHand, "a"); await tick(page, uHand, "c");
  const uShown = await takeShown(page, uHand);
  await takePick(page, uTake); await takePick(page, rTake);
  await send(page);
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 4);
  const a = await answers(page);
  assert.deepEqual([a[rTake.id].choice, a[rHand.id].choice], [["c", "a", "d"], ["c", "a", "d"]], "a ranked pick is not saved in its pick order");
  assert.deepEqual(
    { shown: uShown, take: a[uTake.id].choice, hand: a[uHand.id].choice },
    { shown: false, take: ["a", "c"], hand: ["a", "c"] },
    "an unranked pick out of option order: Take my pick must hide once the ticks are A and C, and must save option order"
  );
});

const LONGER = [opt("a", "Open items older than a week, listed oldest first"), opt("b", "Picks that stood since the last digest went out"), opt("c", "Answers that failed to save and need a second chance"), opt("d", "A fourth title that is long enough to wrap")];
for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 800 }]) {
  test(`no card moves when a box is ticked or Up and Down are pressed, at ${viewport.width} wide`, async (t) => {
    const items = [multi("mv-m", 1, { context: LONG, options: LONGER.slice(0, 3) }), ranked("mv-r", 2, { context: LONG, options: LONGER }), mk("mv-p", 3, { context: LONG })];
    const page = await open(t, { items, viewport }); if (!page) return;
    await noAnchor(page);
    await needBoxes(page, items[0], 3); await needBoxes(page, items[1], 4);
    const base = await geo(page);
    const same = async (what) => assert.deepEqual(await geo(page), base, "the page moved on " + what);
    await tick(page, items[0], "a"); await same("a first tick");
    await tick(page, items[0], "b"); await same("a second tick");
    await tick(page, items[0], "a"); await same("an untick");
    await takePick(page, items[0]); await same("Take my pick on a multi item");
    for (const k of ["c", "a", "d"]) { await tick(page, items[1], k); await same("a tick on a ranked item"); }
    await moveBtn(page, items[1], "a", "up").click(); await same("Up");
    await moveBtn(page, items[1], "d", "up").click(); await same("a second Up");
    await moveBtn(page, items[1], "d", "down").click(); await same("Down");
    const first = moveBtn(page, items[1], "a", "up");
    await first.focus(); await page.keyboard.press("Enter"); await same("Up on the first");
    await tick(page, items[1], "d"); await same("an untick on a ranked item");
    await takePick(page, items[1]); await same("Take my pick on a ranked item");
  });
}

// The ready line's box against the height its text needs. `need` comes from a probe in the same card with the line's own font and width and no clamp,
// so it does not depend on how the page reserves the space. `clip` is above 0 when the line cuts its text.
const readyFit = (page, it) => page.evaluate((id) => {
  const el = document.querySelector(`#item-${id} .ready`), cs = getComputedStyle(el);
  const mark = getComputedStyle(el, "::before").content.replace(/^["']|["']$/g, "");
  const probe = document.createElement("div");
  for (const p of ["fontFamily", "fontSize", "fontWeight", "fontStyle", "letterSpacing", "wordSpacing", "lineHeight", "wordBreak", "overflowWrap", "hyphens"]) probe.style[p] = cs[p];
  probe.style.cssText += `;position:absolute;visibility:hidden;white-space:normal;width:${el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)}px`;
  probe.textContent = (mark === "none" || mark === "normal" ? "" : mark) + el.textContent;
  el.parentNode.append(probe);
  const need = probe.getBoundingClientRect().height;
  probe.remove();
  return { box: el.getBoundingClientRect().height, need, clip: el.scrollHeight - el.clientHeight, line: parseFloat(cs.lineHeight) || 0, text: el.textContent };
}, it.id);
// Titles of exactly 28 characters, the longest a title is named at, so the ready line of n picks is as long as it gets. The first six are plain words.
const T28 = ["Open items older than a week", "Lost answers waiting a retry", "Picks that stood since a run", "Notes that have no owner yet", "Tasks a lane left undone now", "Questions older than one day", "Reconciliation notifications", "Infrastructure documentation", "Troubleshooting instructions", "Authentication notifications"];
const titles28 = (n) => T28.slice(0, n).map((l, i) => opt("abcdefghij"[i], l));
for (const viewport of [{ width: 390, height: 800 }, { width: 1280, height: 900 }]) {
  test(`a multi item's ready line reserves exactly the height of its longest line, no more and never less, at ${viewport.width} wide`, async (t) => {
    const it = multi("rl-short", 62, { options: COLOURS.slice(0, 3) });
    const page = await open(t, { items: [it], viewport }); if (!page) return;
    await noAnchor(page);
    await needBoxes(page, it, 3);
    const base = await geo(page), none = await readyFit(page, it);
    for (const k of ["a", "b", "c"]) await tick(page, it, k);
    const all = await readyFit(page, it);
    assert.equal(all.text, "Ready to send: Red, Blue and Green, your choice.");
    assert.ok(Math.abs(all.box - none.box) <= 1, `the ready line is ${none.box}px with nothing ticked and ${all.box}px with all ticked`);
    assert.ok(Math.abs(all.box - all.need) <= 1, `the ready line is ${all.box}px, and its longest text needs ${all.need}px`);
    assert.deepEqual(await geo(page), base, "a card moved between nothing ticked and all ticked");
  });

  test(`a multi item of six 28-character titles shows the tail of its ready line, your choice or my pick, and no card moves, at ${viewport.width} wide`, async (t) => {
    assert.ok(T28.every((l) => l.length === 28), "a title is not 28 characters");
    const six = titles28(6), it = multi("rl-six", 63, { options: six, pick: six.map((o) => o.key) });
    const page = await open(t, { items: [it], viewport }); if (!page) return;
    await noAnchor(page);
    await needBoxes(page, it, 6);
    const base = await geo(page), none = await readyFit(page, it);
    for (const o of six) await tick(page, it, o.key);
    const all = await readyFit(page, it);
    assert.match(all.text, /^Ready to send: .+, your choice\.$/);
    assert.ok(all.clip <= 0, `the ready line cuts its text: its content is ${all.clip}px taller than its box`);
    assert.ok(all.need <= all.box + 1, `the ready line is ${all.box}px, and its text needs ${all.need}px, so its tail is cut`);
    assert.ok(Math.abs(all.box - none.box) <= 1 && Math.abs(all.box - all.need) <= 1, `the ready line is ${none.box}px with nothing ticked, ${all.box}px with all ticked, and needs ${all.need}px`);
    assert.deepEqual(await geo(page), base, "a card moved between nothing ticked and all ticked");
    await tick(page, it, "f"); await takePick(page, it);
    const mine = await readyFit(page, it);
    assert.match(mine.text, /^Ready to send: .+, my pick\.$/);
    assert.ok(mine.clip <= 0 && mine.need <= mine.box + 1, `the ready line cuts the tail ", my pick." (box ${mine.box}px, text needs ${mine.need}px)`);
    assert.deepEqual(await geo(page), base, "a card moved on Take my pick");
  });
}

// The ruling has no line clamp: a line of ten long titles grows the box to hold it all, at the width the page has now. Head clamps at 6 lines at 390 wide.
test("a multi item's ready line is never clamped: ten 28-character titles show their whole line at 390 wide", async (t) => {
  const ten = titles28(10), it = multi("rl-ten", 64, { options: ten });
  const page = await open(t, { items: [it], viewport: { width: 390, height: 800 } }); if (!page) return;
  await noAnchor(page);
  await needBoxes(page, it, 10);
  const base = await geo(page);
  for (const o of ten) await tick(page, it, o.key);
  const all = await readyFit(page, it);
  assert.match(all.text, /^Ready to send: .+, your choice\.$/);
  assert.ok(all.line > 0 && all.need >= 7 * all.line - 1, `the line needs ${all.need}px, under 7 lines of ${all.line}px, so it cannot show a clamp of 6`);
  assert.ok(all.clip <= 0 && all.need <= all.box + 1, `the ready line is ${all.box}px and cuts its text, which needs ${all.need}px`);
  assert.ok(Math.abs(all.box - all.need) <= 1, `the ready line is ${all.box}px, and its text needs ${all.need}px`);
  assert.deepEqual(await geo(page), base, "a card moved between nothing ticked and all ticked");
});

test("Up and Down are 44px targets on each ticked card, in the Tab order, and work from the keyboard", async (t) => {
  const it = ranked("rk-keyboard", 32);
  const page = await open(t, { items: [it], viewport: { width: 390, height: 800 } }); if (!page) return;
  await needBoxes(page, it, 4);
  for (const k of ["c", "a", "d"]) await tick(page, it, k);
  for (const k of ["c", "a", "d"]) for (const dir of ["up", "down"]) {
    const b = moveBtn(page, it, k, dir);
    assert.equal(await b.count(), 1, `no Move ${labelOf(it, k)} ${dir} button`);
    const r = await b.boundingBox();
    assert.ok(r.width >= 44 && r.height >= 44, `Move ${labelOf(it, k)} ${dir} is ${r.width} by ${r.height}`);
  }
  await page.locator(`#o-${it.id}-c`).focus();
  const stops = [];
  for (let i = 0; i < 4; i++) { await page.keyboard.press("Tab"); stops.push(await page.evaluate(() => document.activeElement.getAttribute("aria-label"))); }
  assert.ok(stops.includes("Move Green up") && stops.includes("Move Green down"), "Tab does not reach Up and Down: " + stops);
  await moveBtn(page, it, "a", "up").focus(); await page.keyboard.press("Enter");
  assert.match(await rankText(page, it, "a"), rank("1st", 3), "Enter on Up did not move the card up");
  await moveBtn(page, it, "d", "up").focus(); await page.keyboard.press("Space");
  assert.match(await rankText(page, it, "d"), rank("2nd", 3), "Space on Up did not move the card up");
  const a = await sendOne(page, it);
  assert.deepEqual(a.choice, ["a", "d", "c"]);
});

test("a pick-one item is unchanged: radios in a radiogroup, and choice is one string", async (t) => {
  const page = await open(t, { items: [DECISION] }); if (!page) return;
  const c = card(page, DECISION);
  assert.equal(await c.getByRole("radiogroup").count(), 1);
  assert.equal(await c.locator("input[type=radio]").count(), 2);
  assert.equal(await c.locator("input[type=checkbox]").count(), 0, "a pick-one item drew a checkbox");
  assert.equal(await page.locator(`label[for="o-${DECISION.id}-a"] .pick`).count(), 1, "the star left the pick-one item's pick");
  await choose(page, DECISION, "b");
  const a = await sendOne(page, DECISION);
  assert.deepEqual([a.choice, typeof a.choice, a.note], ["b", "string", ""]);
});

test("a pick that stands, as a list, sits in the last section, goes with Send as the list, and a changed list wins", async (t) => {
  const s1 = multi("stand-m", 7, { stands: true }), s2 = ranked("stand-r", 8, { stands: true });
  const page = await open(t, { items: [s1, s2] }); if (!page) return;
  assert.equal(await page.locator("#tier-stands article.card").count(), 2, "a stands item with a list pick is not in the last section");
  await needBoxes(page, s1, 3); await needBoxes(page, s2, 4);
  assert.deepEqual(await ticked(page, s1), ["a", "c"], "a stood pick is not shown");
  assert.deepEqual(await ticked(page, s2), ["a", "c", "d"]);
  assert.match(await rankText(page, s2, "c"), rank("1st", 3));
  assert.match(await page.locator("#barStatus").textContent(), /2 where my pick stands/);
  await choose(page, s1, "a"); // untick: the owner's list now differs from my pick
  await send(page);
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 2);
  const a = await answers(page);
  assert.deepEqual([a[s1.id].choice, a[s1.id].note], [["c"], ""]);
  assert.deepEqual([a[s2.id].choice, a[s2.id].note], [["c", "a", "d"], "accepted pick"]);
});

test("a pick that is not a valid list shows no star and no Take my pick; a valid list does", async (t) => {
  const bad = [multi("bad-str", 51, { pick: "a" }), multi("bad-key", 52, { pick: ["a", "zzz"] }), multi("bad-dup", 53, { pick: ["a", "a"] }), multi("bad-empty", 54, { pick: [] }), mk("bad-one", 55, { pick: ["a", "b"] })];
  const good = multi("good-list", 56);
  const page = await open(t, { items: [...bad, good] }); if (!page) return;
  for (const it of [...bad.slice(0, 4), good]) await needBoxes(page, it, 3);
  assert.equal(await card(page, good).locator(".opt .pick").count(), 2, "a valid list is not starred on each pick");
  assert.match(await page.locator(`#item-${good.id} .opt:has(#o-${good.id}-a) .pick`).textContent(), /Red and Green cover it\./);
  assert.equal(await card(page, good).getByRole("button", { name: /Take my pick/ }).count(), 1);
  for (const it of bad) {
    assert.equal(await card(page, it).locator(".opt .pick").count(), 0, `${it.id}: a star shows for a bad pick`);
    assert.equal(await card(page, it).getByRole("button", { name: /Take my pick/ }).count(), 0, `${it.id}: Take my pick shows for a bad pick`);
  }
});

test("the notice to Claude writes a list pick as 31 a+c, in rank order when ranked", async (t) => {
  const m = digest(), r = ranked("rk-notice", 32);
  const page = await open(t, { items: [m, r] }); if (!page) return;
  await needBoxes(page, m, 3); await needBoxes(page, r, 4);
  await tick(page, m, "a"); await tick(page, m, "c"); await addNote(page, m, "bold");
  await tick(page, r, "c"); await tick(page, r, "a");
  await send(page);
  await told(page, "Claude was told");
  const s = await sent(page);
  assert.equal(s.length, 1);
  assert.match(s[0].text, /31 a\+c \(bold\)/);
  assert.match(s[0].text, /32 c\+a/);
});

test("Undo puts a list pick back as a draft, in its order", async (t) => {
  const m = digest(), r = ranked("rk-undo", 32);
  const page = await open(t, { items: [m, r] }); if (!page) return;
  await needBoxes(page, m, 3); await needBoxes(page, r, 4);
  await tick(page, m, "a"); await tick(page, m, "c"); await tick(page, r, "c"); await tick(page, r, "a");
  await send(page);
  await page.locator("#undoBtn").waitFor();
  await page.locator("#undoBtn").click();
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 0);
  assert.deepEqual(await ticked(page, m), ["a", "c"], "Undo lost the list");
  assert.deepEqual(await ticked(page, r), ["a", "c"]);
  assert.match(await rankText(page, r, "c"), rank("1st", 2), "Undo lost the order");
  assert.equal(await page.locator("#send").textContent(), "Send 2 answers");
});

// The first option is in no pick, so a fix that focuses the first box of the card fails. The ranked pick starts with C, so a fix that reads option order fails.
test("Enter on Take my pick puts focus on the first key of the pick, on a multi card", async (t) => {
  const it = multi("take-focus-multi", 41, { pick: ["b", "c"] });
  const page = await open(t, { items: [it] }); if (!page) return;
  await needBoxes(page, it, 3);
  const at = await enterTakePick(page, it);
  assert.deepEqual(await ticked(page, it), ["b", "c"], "Enter did not take the pick");
  assertFocusOnFirstPick(at, it, "b");
});

test("Enter on Take my pick puts focus on the first key of the pick, in rank order, on a ranked card", async (t) => {
  const it = ranked("take-focus-ranked", 42);
  const page = await open(t, { items: [it] }); if (!page) return;
  await needBoxes(page, it, 4);
  const at = await enterTakePick(page, it);
  assert.deepEqual(await ticked(page, it), ["a", "c", "d"], "Enter did not take the pick");
  assert.match(await rankText(page, it, "c"), rank("1st", 3), "the pick's first key is not ranked 1st");
  assertFocusOnFirstPick(at, it, "c");
});

test("a multi item keeps each option's picture in its card: a tap on the picture opens the viewer, a tap on the card ticks", async (t) => {
  const it = { ...picItem("multi-pics", 33), multi: true, pick: ["a", "c"] };
  const page = await open(t, { items: [it], designData: PICS }); if (!page) return;
  await needBoxes(page, it, 3);
  for (const o of LOOK_OPTS) assert.equal(await card(page, it).locator(`label.opt[for="o-${it.id}-${o.key}"] .opic iframe.dframe`).count(), 1, "no picture in option " + o.key);
  await card(page, it).locator(`label.opt[for="o-${it.id}-b"] .opic`).click();
  assert.deepEqual(await ticked(page, it), [], "a tap on the picture ticked the option");
  assert.equal(await page.locator("#dsheet").isVisible(), true, "the viewer did not open");
  await page.click("#dClose");
  await choose(page, it, "b"); await choose(page, it, "c");
  assert.deepEqual(await ticked(page, it), ["b", "c"]);
});

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
import { spawnSync } from "node:child_process";
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
// Later than the sends these cases use (the latest is LA_AT, 2026-10-29T19:05Z). An item added then is new, not seen, so its parts stay unfolded.
const ASKED_AFTER_SEND = "2026-10-30T00:00:00Z";
// The page's clock for every case that loads a closed line. A closed line ages out after LINE_AGE_H hours, so these cases set their
// closed times from this fixed now and never from the real clock, which would age the fixtures out on a later day.
const AP_NOW = "2026-11-09T18:00:00Z";

// Runs in the page before its script. Collections are maps of id to data; listeners fire on change.
// dbExtra is more database content ({collection: {id: data}}), such as the roadmap's own steps and
// meta docs, which the status part must never read. window.__reads lists every read as
// [collection, id or null]; window.__uses lists every window.claude.use(capability) call.
// noStore: the page gets no database (a view that cannot reach the store), so use("db") gives null.
// failSetText: a write to asks whose text holds it is refused with code denied, so one ask of a batch fails and the rest save.
// hold: { set: n } or { delete: n }. An asks write or delete after the first n waits at the hold until window.__release() runs; window.__held counts the calls waiting.
// A case disarms it with window.__hold = null, since the init script arms it again on every load (a reload).
function stubDb({ items, rawItems, answers, failDelete, failDeleteIn, failSet, failSetText = "", failUpdate = false, comments, meta, groups, receipts, holdReceipts, holdAsks = false, dbExtra = {}, noStore = false, hold = {}, keepItems = false }) {
  const { meta: metaExtra, ...otherExtra } = dbExtra;
  const data = { items: { ...Object.fromEntries(items.map((i) => [i.id, i])), ...rawItems }, answers: { ...answers }, meta: { ...(meta ? { page: meta } : {}), ...metaExtra }, groups: { ...groups }, receipts: { ...receipts }, ...otherExtra };
  window.__reads = []; window.__uses = [];
  window.__hold = hold; window.__held = 0;
  let openLatch; const latch = new Promise((r) => { openLatch = r; }); window.__release = () => openLatch();
  const seen = { set: 0, delete: 0 };
  const holdFor = async (op) => { const h = window.__hold; if (!h || h[op] === undefined || ++seen[op] <= h[op]) return; window.__held++; await latch; };
  // The asks are kept in the page's localStorage, so a reload finds them as the store held them.
  try { const kept = JSON.parse(localStorage.getItem("__stub.asks")); if (kept) data.asks = kept; } catch (e) {}
  const keepAsks = () => { try { localStorage.setItem("__stub.asks", JSON.stringify(data.asks || {})); } catch (e) {} };
  // keepItems (opt-in): the items' update writes, such as Mark read, are kept too, so a reload finds them as the store held them.
  if (keepItems) { try { const kept = JSON.parse(localStorage.getItem("__stub.items")); if (kept) data.items = kept; } catch (e) {} }
  const keepItemsStore = () => { if (!keepItems) return; try { localStorage.setItem("__stub.items", JSON.stringify(data.items || {})); } catch (e) {} };
  const subs = {}, docSubs = {};
  window.__log = [];
  const snap = (name) => ({ docs: Object.entries(data[name] || {}).map(([id, v]) => ({ id, data: () => v })) });
  const dsnap = (name, id) => ({ exists: !!(data[name] || {})[id], data: () => (data[name] || {})[id] || null });
  const fire = (name, id) => {
    (subs[name] || []).forEach((cb) => cb(snap(name)));
    (docSubs[name + "/" + id] || []).forEach((cb) => cb(dsnap(name, id)));
  };
  window.__answers = () => data.answers;
  // Pushes one item through the items listener, as a session adding an item after the page loaded would.
  // Writes one document as the store holds it, and tells its listeners: a session's write after the page loaded.
  window.__putDoc = (name, id, body) => { (data[name] = data[name] || {})[id] = body; fire(name, id); };
  window.__putItem = (it) => window.__putDoc("items", it.id, it);
  // holdReceipts: the receipts' first snapshot waits for window.__releaseReceipts(), so a case can act before receipts arrive.
  // holdAsks: the asks' first snapshot waits for window.__releaseAsks(), so a case can act while the answers list reads Loading.
  const listen = (name, cb) => { window.__reads.push([name, null]); (subs[name] = subs[name] || []).push(cb); if (holdReceipts && name === "receipts") window.__releaseReceipts = () => cb(snap(name)); else if (holdAsks && name === "asks") window.__releaseAsks = () => cb(snap(name)); else setTimeout(() => cb(snap(name)), 0); return () => {}; };
  const db = {
    doc: (path) => db.collection(path.split("/")[0]).doc(path.split("/")[1]),
    collection: (name) => ({
      onSnapshot: (cb) => listen(name, cb),
      orderBy: () => ({ onSnapshot: (cb) => listen(name, cb) }),
      doc: (id) => ({
        get: async () => { window.__reads.push([name, id]); return dsnap(name, id); },
        set: async (body) => { if (name === "asks") await holdFor("set"); if (failSet || (name === "asks" && failSetText && String(body.text).includes(failSetText))) throw { code: "denied" }; window.__log.push(["set", name, id, body]); (data[name] = data[name] || {})[id] = body; if (name === "asks") keepAsks(); setTimeout(() => fire(name, id), 0); },
        // A merge write, as the runtime's update: the fields given are set, the rest of the record stays. It is refused when the record is gone.
        // failUpdate refuses every asks update with permission-denied, as a store that cannot write does.
        update: async (body) => { if (failUpdate && name === "asks") throw { code: "permission-denied" }; if (!(data[name] || {})[id]) throw { code: "not-found" }; window.__log.push(["update", name, id, body]); data[name][id] = { ...data[name][id], ...body }; if (name === "asks") keepAsks(); if (name === "items") keepItemsStore(); setTimeout(() => fire(name, id), 0); },
        delete: async () => { if (name === "asks") await holdFor("delete"); if (failDelete || failDeleteIn === name) throw { code: "denied" }; window.__log.push(["delete", name, id]); delete (data[name] || {})[id]; if (name === "asks") keepAsks(); setTimeout(() => fire(name, id), 0); },
        onSnapshot: (cb) => { window.__reads.push([name, id]); (docSubs[name + "/" + id] = docSubs[name + "/" + id] || []).push(cb); setTimeout(() => cb(dsnap(name, id)), 0); return () => {}; },
      }),
    }),
  };
  // comments: null (capability absent) or { can, canThrows, failCode, goneThreads, threadFail, anchorFail }.
  // failCode rejects every send; goneThreads rejects a send into those thread ids with not_found.
  // threadFail maps a thread id to the code a send into that thread rejects with; anchorFail is the code an anchored send (no threadId) rejects with.
  window.__sent = [];
  const cm = comments && {
    canSendToClaude: async () => { if (comments.canHangs) return new Promise(() => {}); if (comments.canThrows) throw { code: "unavailable" }; return comments.can || "available"; },
    anchorFor: async (el) => ({ path: "h1", x: 0, y: 0, tag: el.tagName }),
    sendToClaude: async (target) => {
      window.__sent.push(target);
      if (comments.sendDelay) await new Promise((r) => setTimeout(r, comments.sendDelay));
      if (comments.failCode) throw { code: comments.failCode, message: "stub" };
      if (target.threadId && (comments.goneThreads || []).includes(target.threadId)) throw { code: "not_found", message: "stub" };
      if (target.threadId && comments.threadFail && comments.threadFail[target.threadId]) throw { code: comments.threadFail[target.threadId], message: "stub" };
      if (!target.threadId && comments.anchorFail) throw { code: comments.anchorFail, message: "stub" };
      return { threadId: target.threadId || "t-new-" + window.__sent.length, commentId: "c" + window.__sent.length };
    },
  };
  window.claude = { use: async (cap) => { window.__uses.push(cap); return cap === "db" ? (noStore ? null : db) : cap === "comments" ? (cm || null) : null; } };
}

let browser;
const html = fs.readFileSync(PAGE, "utf8");
// The page name, PAGE_NAME in skills/waiting-page/splice.py. Read from that file, never copied here.
function pageName() {
  const m = /^PAGE_NAME = "([^"]*)"/m.exec(fs.readFileSync(path.join(HERE, "..", "splice.py"), "utf8"));
  assert.ok(m, "splice.py has no PAGE_NAME line");
  return m[1];
}
after(async () => { if (browser) await browser.close(); });

// clock: a fixed browser time (an ISO string), so a case reads the page's clock without the real one. keepStorage: each storage key is set
// only when absent, so a reload keeps what the page wrote on the earlier load (a reload that resets storage would undo it).
// timers: the page's timers run on a fake clock, installed before load, so a case moves time on with clock.runFor and never waits on it.
async function open(t, { items = [DECISION, TASK], rawItems = {}, answers = {}, failDelete = false, failDeleteIn = "", failSet = false, failSetText = "", comments = { can: "available" }, storage = {}, meta = null, groups = {}, receipts = {}, holdReceipts = false, holdAsks = false, designData = null, dbExtra = {}, pageHtml = html, viewport = { width: 1280, height: 900 }, hasTouch = false, scheme = "light", errors = null, platform = null, noStore = false, hold = {}, clock = null, keepStorage = false, failUpdate = false, keepItems = false, timers = false } = {}) {
  browser = browser || await needEnv(t, "chromium", async () => require("playwright").chromium.launch());
  if (!browser) return null;
  // hasTouch: a touch device, so the page's pointer: coarse rules apply.
  const page = await browser.newPage({ viewport, hasTouch });
  // errors: when given, collects each uncaught page error, from the first render on.
  if (errors) page.on("pageerror", (e) => errors.push(e.message));
  page.setDefaultTimeout(Number(process.env.WP_TIMEOUT) || 5000);
  t.after(() => page.close());
  await page.emulateMedia({ colorScheme: scheme });
  const body = designData ? pageHtml.replace(DESIGN_SLOT, `<script type="application/json" id="designData">${JSON.stringify(designData).replace(/</g, "\\u003c")}</script>`) : pageHtml;
  // The page is served from a stand-in origin, so the init script and localStorage both apply.
  // Every other request (the fonts) is refused.
  await page.route("**/*", (r) => (r.request().url() === ORIGIN ? r.fulfill({ contentType: "text/html; charset=utf-8", body }) : r.abort()));
  await page.addInitScript(() => { new MutationObserver(() => { const w = document.querySelector(".dfitwrap"); if (w && window.__firstFit === undefined) window.__firstFit = w.getBoundingClientRect().height; }).observe(document, { childList: true, subtree: true }); });
  await page.addInitScript(stubDb, { items, rawItems, answers, failDelete, failDeleteIn, failSet, failSetText, failUpdate, comments, meta, groups, receipts, holdReceipts, holdAsks, dbExtra, noStore, hold, keepItems });
  await page.addInitScript(({ kv, keep }) => { for (const k in kv) { if (keep && localStorage.getItem(k) !== null) continue; localStorage.setItem(k, kv[k]); } }, { kv: storage, keep: keepStorage });
  // platform: the OS a browser reports, as navigator.platform with no userAgentData (a Windows or a Mac browser).
  if (platform) await page.addInitScript((p) => { Object.defineProperty(navigator, "platform", { get: () => p }); Object.defineProperty(navigator, "userAgentData", { get: () => undefined }); }, platform);
  if (clock) await page.clock.setFixedTime(new Date(clock));
  if (timers) await page.clock.install();
  await page.goto(ORIGIN);
  // With no store there are no items to wait for: the page is loaded once its empty state is drawn.
  if (noStore) { await page.waitForFunction("state.loaded"); return page; }
  await page.waitForFunction("state.items.length > 0"); // the stub database has delivered the items
  await page.waitForSelector(`#item-${items.length ? items[0].id : Object.keys(rawItems)[0]}`);
  return page;
}
const card = (page, it) => page.locator(`#item-${it.id}`);
const answers = (page) => page.evaluate(() => window.__answers());
// A tap on an option's picture opens the viewer (d9 ruling), so a pick taps the option's label text.
const choose = (page, it, key) => page.locator(`label[for="o-${it.id}-${key}"] .lab`).click();
// A tap on the starred option picks it. A pick partly ticked already taps only the keys not yet ticked, so the card ends with the whole pick.
const takePick = async (page, it) => {
  for (const k of [].concat(it.pick)) if (!(await page.isChecked(`#o-${it.id}-${k}`))) await tick(page, it, k);
};
const addNote = async (page, it, text) => { await page.fill(`#n-${it.id}`, text); };
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
// SENT_MOVE, where a card sent on this visit goes: "sink" (the default) moves it to the Answered section, folded; "stay" keeps it in its tier.
// page.html declares the switch as the one line below. A case sets the value by rewriting that line in the page source. On a page with no
// such line the rewrite does nothing, so a case fails on its own assertion, never on a missing name. The "stay" value is today's order.
const SENT_MOVE_LINE = 'const SENT_MOVE = "sink";';
const withSentMove = (value) => html.replace(SENT_MOVE_LINE, `const SENT_MOVE = "${value}";`);

// ---------------------------------------------------------------- the final design

test("a rule question starts blank, my pick is starred in its card, and a tap on the star fills it in", async (t) => {
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
  assert.deepEqual([a.item, a.n, a.choice, a.note], [DECISION.id, 27, "a", ""]);
});

// Two options with ids, as the page holds them when the owner picks: Red (a) and Blue (b). The one home of this list.
const IDED = [
  { key: "a", id: "red", label: "Red", how: "h", gain: "g", lose: "l" },
  { key: "b", id: "blue", label: "Blue", how: "h", gain: "g", lose: "l" },
];
// The saved answer names the option picked by its id as well as by its letter (ruling R60): a stored pick records the id,
// so a later move of the letters cannot change which option the owner meant.
test("a pick saves the id of the option picked, beside its letter", async (t) => {
  const WITH_IDS = mk("ids-decision", 40, { pick: "a", options: IDED });
  const page = await open(t, { items: [WITH_IDS] }); if (!page) return;
  await takePick(page, WITH_IDS);
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], WITH_IDS.id);
  const a = (await answers(page))[WITH_IDS.id];
  assert.equal(a.optionId, "red", "the saved answer does not carry the id of the option picked");
});

// The item as triage leaves it after a reorder: letters follow position, so Blue takes a and Red takes b. Each key stays a
// letter, so the page's letter checks read the item as valid.
const LETTERS_MOVED = [{ ...IDED[1], key: "a" }, { ...IDED[0], key: "b" }];

// A pick keeps the id and the label the option had when the owner picked it. The item re-snapshots with the letters moved
// after the pick, and Send still saves the option picked: Red, with id red and label "A: Red" as it read at pick time.
test("a pick keeps the id and label it had when picked, after the letters move", async (t) => {
  const it = mk("moved-pick", 41, { pick: "a", options: IDED });
  const page = await open(t, { items: [it] }); if (!page) return;
  await choose(page, it, "a");
  await page.evaluate((moved) => window.__putItem(moved), { ...it, options: LETTERS_MOVED });
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], it.id);
  const a = (await answers(page))[it.id];
  assert.equal(a.choice, "a", "the answer does not hold the letter the owner picked");
  assert.equal(a.optionId, "red", "the saved id is not the id of the option picked, Red");
  assert.equal(a.label, "A: Red", "the saved label is not the label the option had when it was picked");
});

// The same for a multi item: the ids of the options ticked, from before the letters moved, in the order ticked.
test("a multi pick keeps the ids it had when ticked, after the letters move", async (t) => {
  const it = mk("moved-multi", 42, { multi: true, pick: [], options: IDED });
  const page = await open(t, { items: [it] }); if (!page) return;
  await choose(page, it, "a");
  await choose(page, it, "b");
  await page.evaluate((moved) => window.__putItem(moved), { ...it, options: LETTERS_MOVED });
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], it.id);
  const a = (await answers(page))[it.id];
  assert.deepEqual(a.choice, ["a", "b"], "the answer does not hold the letters the owner ticked");
  assert.deepEqual(a.optionId, ["red", "blue"], "the saved ids are not the ids of the options ticked, from before the move");
});

// Control, green on the current head: a decision whose options carry no id saves no optionId.
test("a decision whose options carry no id saves no optionId", async (t) => {
  const page = await open(t); if (!page) return;
  await takePick(page, DECISION);
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], DECISION.id);
  const a = (await answers(page))[DECISION.id];
  assert.equal(a.choice, "a", "the answer does not hold the pick the owner made");
  assert.equal("optionId" in a, false, "a saved answer names an optionId for an option with no id");
});

// Control, green on the current head: an option's note is drawn on its card, in that option's label.
test("an option's note is drawn on its card", async (t) => {
  const it = mk("noted-option", 43, { options: [
    { key: "a", label: "Red", how: "h", gain: "g", lose: "l", note: "Now means the red that shipped." },
    { key: "b", label: "Blue", how: "h", gain: "g", lose: "l" },
  ] });
  const page = await open(t, { items: [it] }); if (!page) return;
  assert.equal(await card(page, it).locator(`label[for="o-${it.id}-a"]`).count(), 1, "option a is not drawn on the card");
  const noted = card(page, it).locator(`label[for="o-${it.id}-a"] .optnote`);
  assert.equal(await noted.count(), 1, "the option's note is not drawn on its card");
  assert.equal((await noted.textContent()).trim(), "Now means the red that shipped.", "the card draws another note than the option's");
  assert.equal(await card(page, it).locator(`label[for="o-${it.id}-b"] .optnote`).count(), 0, "a note is drawn on an option with none");
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
    ["tier-holds", "Blocking", ["hold-new", "hold-old"]],
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
  assert.deepEqual([a["d-two"].choice, a["d-two"].note], ["a", ""]);
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
  const page = await open(t, { items, pageHtml: withSentMove("stay") }); if (!page) return;
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
      // The newest blocking item sorts first, so a card above the first receipt gives the page room to scroll up.
      mk("lead", 6, { context: LONG, holds: "A lane waits.", added: "2026-10-27T00:00:00Z" }),
    ];
    const page = await open(t, { items, viewport, designData: withDesigns ? DESIGNS : null, pageHtml: withSentMove("stay") }); if (!page) return;
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
    await takePick(page, items[3]); await same("a tap on the star");
    await choose(page, items[3], "a"); await same("a click on the selected pick");
    await takePick(page, items[4]);
    await choose(page, items[4], "c"); await same("a pick after a tap on the star");
    await card(page, items[2]).getByRole("button", { name: "Mark done" }).click(); await same("Mark done");
    sent = true;
    // A Send shrinks each receipt at once (shiv, 15:06 CDT Oct 30, receipt-tightens-at-once). The anchor is the first card whose bottom is below the band's
    // top, skipping a sent card whose top is above it. The anchor keeps its top, and a card that stays keeps its height.
    await placeRel(page, items[3], "top", 40);
    const sentItems = [items[0], items[1], items[2], items[4]];
    assert.equal(await anchorOf(page, sentItems), "item-" + items[3].id, "fixture: the anchor is not the witness card");
    const rd = await sendAndRead(page, sentItems);
    const w = "item-" + items[3].id;
    assert.ok(rd.pre[w].top > rd.band.top && rd.pre[w].top < rd.band.bottom, "the witness is off the band before Send");
    const seen = Object.values(rd.pre).filter((c) => c.bottom > rd.band.top && c.top < rd.band.bottom);
    for (const [when, post] of reads(rd)) {
      assert.equal(post[w].receipt, false, "the witness became a receipt on Send");
      assert.ok(Math.abs(post[w].top - rd.pre[w].top) <= 1, `${when}: the witness moved on Send: ${rd.pre[w].top} to ${post[w].top}`);
      for (const b of seen) {
        const a = post[b.id];
        if (a.receipt && !b.receipt) assert.ok(a.h < b.h - 1, `${when}: a receipt kept its height on Send: ${b.id} ${b.h} to ${a.h}`);
        else if (!a.receipt) assert.ok(Math.abs(a.h - b.h) <= 1, `${when}: a card that stays changed height on Send: ${b.id} ${b.h} to ${a.h}`);
      }
    }
  });
}

test("a saved answer from an earlier page shows as a receipt and nothing is written on load", async (t) => {
  const none = { item: TASK.id, n: 28, at: "2026-10-26T01:00:00Z", done: true, note: "plugged" };
  const page = await open(t, { answers: { ...SAVED_A, [TASK.id]: none } }); if (!page) return;
  assert.match(await card(page, DECISION).locator(".receipt").textContent(), /You chose A: Red/);
  assert.match(await card(page, TASK).locator(".receipt").textContent(), /Marked done/);
  assert.deepEqual(await page.evaluate(() => window.__log), []);
});

test("an answered card without a filing shows Filing pending with its send time, never waited", async (t) => {
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  const c = card(page, DECISION);
  const ans = (await c.locator(".ans").textContent()).trim();
  // In the Answered section the pill drops "Answered," (answered-sink notes, pick 2): the head says it.
  assert.match(ans, /^Filing pending, sent Oct \d+, \d\d:\d\d C[DS]T$/);
  assert.doesNotMatch(await c.locator(".top").textContent(), /waited|Added/i);
  assert.equal(await c.locator(".ans.filed").count(), 0);
  assert.match(await page.locator("#c-" + DECISION.id).getAttribute("aria-label"), /answered, filing pending$/);
});

test("an answered item with a filed receipt shows one line in the Answered section, with its home and its rail chip filed", async (t) => {
  const page = await open(t, { items: [TASK, DECISION], answers: SAVED_A, receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z", filed: "2026-10-26T03:00:00Z" } } }); if (!page) return;
  await mustHave(page, `#tier-answered #line-${DECISION.n}`, `the one line of No. ${DECISION.n} in the Answered section`);
  assert.match((await page.locator(`#tier-answered #line-${DECISION.n}`).textContent()) || "", /c1/, `the line of No. ${DECISION.n} does not name its home c1`);
  assert.match(await page.locator("#c-" + DECISION.id).getAttribute("aria-label"), /answered, filed$/);
  assert.match(await page.locator("#c-" + DECISION.id).getAttribute("class"), /filed/);
});

test("a read but unfiled answer shows Read by the owner beside Change", async (t) => {
  const page = await open(t, { answers: SAVED_A, receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z" } } }); if (!page) return;
  const c = card(page, DECISION);
  assert.match(await c.locator(".receipt .read").textContent(), /^Read by test thread /);
  assert.match((await c.locator(".ans").textContent()).trim(), /^Filing pending, sent /);
});

test("a receipt older than the answer is ignored: a changed answer reads filing pending", async (t) => {
  const later = { [DECISION.id]: { ...SAVED_A[DECISION.id], at: "2026-10-26T04:00:00Z" } };
  const page = await open(t, { answers: later, receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z", filed: "2026-10-26T03:00:00Z" } } }); if (!page) return;
  const c = card(page, DECISION);
  assert.match((await c.locator(".ans").textContent()).trim(), /^Filing pending, sent /);
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
    // The title is "<repo> <page name>" on Questions.
    assert.notEqual(await page.title(), "Agent Q Queue", "the title still names the old page name Queue");
    assert.equal(await page.title(), "Agent Q " + pageName());
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
// n requestAnimationFrame callbacks: a layout that a resize or a repaint starts has run when this resolves.
const frameWait = (page, n) => page.evaluate((k) => new Promise((resolve) => { const step = (i) => (i ? requestAnimationFrame(() => step(i - 1)) : resolve()); step(k); }), n);
// A picture's fit arrives by postMessage once its frame loads, so a layout read waits for one fit per design, then three frames.
const fitAll = (page, slugs) => page.waitForFunction((ks) => ks.every((k) => Object.keys(FIT).some((x) => x.startsWith(k + "|"))), slugs).then(() => frameWait(page, 3));

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
    await page.waitForFunction(() => +document.getElementById("mark").dataset.iconRuns >= 1).catch(() => {}); // a dropped icon's pass still counts, and the assert below names a miss
    assert.ok(+(await page.getAttribute("#mark", "data-icon-runs")) >= 1, "the mark never counted its finished icon pass");
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
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))); // the observer delivers a lost icon before the next frame
    return lost;
  }, icon);
  assert.equal(flashed, false);
  assert.equal((await markState(page)).img, icon);
});

test("a decode that finishes after a newer identity is ignored", async (t) => {
  const page = await open(t, { meta: { identity: { name: "Compass" } } }); if (!page) return;
  await named(page, "Compass");
  const slow = svgIcon("#11151b", "<!--slow-->");
  const base = await page.evaluate((slow) => {
    const decode = HTMLImageElement.prototype.decode;
    // The slow decode holds on a latch the test opens, so it finishes after the newer identity's pass.
    window.__slowGo = new Promise((r) => { window.__slowRelease = r; });
    HTMLImageElement.prototype.decode = function () { const wait = this.src === slow; return decode.call(this).then(() => wait && window.__slowGo); };
    const base = +document.getElementById("mark").dataset.iconRuns;
    state.meta = { identity: { name: "Compass", icon: slow } }; applyIdentity();
    state.meta = { identity: { name: "Compass" } }; applyIdentity();
    window.__slowRelease();
    return base;
  }, slow);
  assert.ok(Number.isInteger(base), "the mark never counted its finished icon pass");
  await page.waitForFunction((b) => +document.getElementById("mark").dataset.iconRuns === b + 2, base).catch(() => {}); // the stale pass counts after the release
  assert.equal(+(await page.getAttribute("#mark", "data-icon-runs")), base + 2, "the stale pass did not count");
  const m = await markState(page);
  assert.deepEqual([m.icon, m.img, m.text, m.tile], [false, null, "C", ""], "a stale decode drew its icon over the newer identity");
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
// Option A may take a focus, a declared size or a differing picture. The other options stay plain.
const picItem = (id, n, { focus, size, differs } = {}) => mk(id, n, {
  options: LOOK_OPTS.map((o) => (o.key === "a" && differs ? { ...o, differs } : o)), pick: "a",
  designs: LOOK_OPTS.map((o) => ({ slug: o.design, label: o.label, ...(o.key === "a" && focus ? { focus, ...(size ? { size } : {}) } : {}) })),
});
// A mockup h px tall, 390 wide: a gradient over a 50px band at the end.
const TALL_PIC = (h) => `<body style="margin:0"><div style="height:${h - 50}px;background:linear-gradient(#2a6,#26a)"></div><div style="height:50px;background:#a62"></div></body>`;
const FOCUS_TALL = '<body style="margin:0"><div style="height:300px;background:#ccc"></div><div id="panel" style="width:390px;height:1700px;background:linear-gradient(#a62,#26a)"></div><div style="height:600px;background:#999"></div></body>';
// Waits until the frame has posted a mockup h px tall.
const frameSettled = (page, h) => page.waitForFunction((H) => Object.values(FIT).some((c) => c.h === H), h);
const boxSel = (id, key = "a") => `#item-${id} label.opt[for="o-${id}-${key}"] .dfitwrap`;
// The box, its scroll, and the frame's place. g is the scrollbar gutter plus any border past 1px.
const measure = (page, id, key = "a") => page.locator(boxSel(id, key)).evaluate((w) => {
  const f = w.querySelector("iframe").getBoundingClientRect(), r = w.getBoundingClientRect();
  return { w: r.width, h: r.height, top: r.top, cw: w.clientWidth, ch: w.clientHeight, sh: w.scrollHeight, st: w.scrollTop, cls: w.className, fw: f.width, fTop: f.top, fBot: r.bottom - f.bottom, g: w.offsetWidth - w.clientWidth - 2, sizer: (w.querySelector(".dsizer") || w).getBoundingClientRect().height };
});
const cueState = (page, id, key = "a") => page.locator(boxSel(id, key)).evaluate((w) => {
  const c = w.querySelector(".dcue"), t = w.querySelector(".dtop");
  return { disp: getComputedStyle(c).display, op: +getComputedStyle(c).opacity, text: c.textContent, top: +getComputedStyle(t).opacity, cls: w.className };
});

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

test("SKILL.md, reference/designs.md and the designer agent carry the mockup convention", async () => {
  // The mockup convention moved from SKILL.md to reference/designs.md, so the skill's text is read from both files.
  const skill = ["SKILL.md", path.join("reference", "designs.md")]
    .map((f) => fs.readFileSync(path.join(HERE, "..", f), "utf8")).join("\n");
  const designer = fs.readFileSync(path.join(HERE, "..", "..", "..", "agents", "designer.md"), "utf8");
  for (const [name, text] of [["SKILL.md and reference/designs.md", skill], ["designer.md", designer]]) {
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

// The owner's note on waiting-page item 55 (Oct 28, 17:50 CDT): a picture taller than its box scrolls inside it.
for (const width of [390, 1440]) {
  test(`a tall mockup scrolls inside a 480px box, is never drawn taller, and its last row is reachable, at ${width} wide`, async (t) => {
    const it = picItem("tall", 35);
    const tall = TALL_PIC(2400);
    const page = await open(t, { items: [it], designData: { ...PICS, "price-a": tall }, viewport: { width, height: 900 } }); if (!page) return;
    const wrap = card(page, it).locator(`label.opt[for="o-${it.id}-a"] .dfitwrap`);
    await page.waitForFunction((sel) => document.querySelector(sel).getBoundingClientRect().height > 300, `#item-${it.id} label.opt .dfitwrap`);
    const m = await wrap.evaluate((w) => { const f = w.querySelector("iframe").getBoundingClientRect(), r = w.getBoundingClientRect(); return { wrapW: r.width, wrapH: r.height, frameW: f.width, frameH: f.height }; });
    const scale = m.frameW / 390;
    assert.ok(Math.abs(m.frameH - 2400 * scale) < 3, `the frame is ${m.frameH} high, the mockup ${2400 * scale}`);
    assert.ok(m.wrapH <= 480, `the box is ${m.wrapH} high, over 480`);
    assert.ok(m.frameW <= m.wrapW + 1, "the mockup is wider than the card");
    await wrap.evaluate((w) => { w.scrollTop = w.scrollHeight; });
    const fBot = await wrap.evaluate((w) => w.getBoundingClientRect().bottom - w.querySelector("iframe").getBoundingClientRect().bottom);
    assert.ok(Math.abs(fBot - 1) <= 2, `the last row is ${fBot}px from the box bottom after the scroll`);
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

// ---------------------------------------------------------------- a picture taller than its box scrolls inside it
for (const width of [390, 1440]) {
  test(`a tall picture's scroll range is over 100px, and the picture fills the card's width, at ${width} wide`, async (t) => {
    const it = picItem("scroll-range", 52);
    const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(2400) }, viewport: { width, height: 900 } }); if (!page) return;
    await frameSettled(page, 2400);
    const m = await measure(page, it.id);
    assert.ok(m.sh - m.ch > 100, `the scroll range is ${m.sh - m.ch}px`);
    assert.ok(Math.abs(m.fw - m.cw) <= 1, `the picture is ${m.fw} wide in a ${m.cw} wide box: the scrollbar took some of it`);
  });
}

test("a focus box taller than the card scrolls inside the focus box and opens at its top, at 390 wide", async (t) => {
  const it = picItem("focus-tall", 51, { focus: "#panel" });
  const page = await open(t, { items: [it], designData: { ...PICS, "price-a": FOCUS_TALL }, viewport: { width: 390, height: 900 } }); if (!page) return;
  await frameSettled(page, 2600);
  await page.waitForFunction((sel) => document.querySelector(sel).querySelector("iframe").style.transform.includes("translate"), boxSel(it.id));
  const m = await measure(page, it.id);
  const sc = m.fw / 390;
  assert.ok(m.h <= 480, `the focus box is ${m.h} high, over 480`);
  assert.ok(m.sh > m.ch, "the focus box does not scroll");
  assert.ok(Math.abs(m.sh - Math.ceil(1700 * sc)) <= 2, `the scroll range is ${m.sh} high, not the focus box's ${Math.ceil(1700 * sc)}`);
  assert.equal(m.st, 0, "the box did not open at its top");
  assert.ok(Math.abs(m.fTop + 300 * sc - m.top) <= 2, "the focus does not start at the top of the box");
});

// Owner ruling, waiting-page item 84 pick b (2026-10-30 14:45 CDT), c204 option 5B: a scrolling picture draws min(221.8, column - 2 - gutter) wide.
// 221.8 is 480 x 390 / 844, the width a 390 x 844 phone picture gets. A picture that does not scroll keeps today's scale.
const SCROLL_W = (480 * 390) / 844;
// The column is the .opic that holds the box, less its padding.
const column = (page, id) => page.locator(boxSel(id)).evaluate((w) => {
  const o = w.parentElement, cs = getComputedStyle(o);
  return o.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
});
// Waits until the frame keeps one width for two frames, so a measure reads the last fit and not a first pass.
const settleFit = (page, id) => page.waitForFunction((sel) => new Promise((done) => {
  const f = document.querySelector(sel).querySelector("iframe"), a = f.getBoundingClientRect().width;
  requestAnimationFrame(() => requestAnimationFrame(() => done(Math.abs(f.getBoundingClientRect().width - a) < 0.01)));
}), boxSel(id), { polling: 50 });

for (const width of [390, 1440]) {
  test(`a tall picture in a 480px box draws min(221.8, column - 2 - gutter) wide and fills its box, with no sideways scroll, at ${width} wide`, async (t) => {
    const it = picItem("scroll-width", 57);
    const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(2400) }, viewport: { width, height: 900 } }); if (!page) return;
    await frameSettled(page, 2400);
    await settleFit(page, it.id);
    const m = await measure(page, it.id), cw = await column(page, it.id);
    const want = Math.min(SCROLL_W, cw - 2 - m.g);
    assert.ok(Math.abs(m.fw - want) <= 1, `the picture is ${m.fw} wide, not min(${SCROLL_W.toFixed(1)}, ${cw} - 2 - ${m.g}) = ${want.toFixed(1)}`);
    assert.ok(Math.abs(m.h - 480) <= 1, `the box is ${m.h} high, not 480`);
    assert.ok(m.w <= cw + 1, `the box is ${m.w} wide in a ${cw} wide column`);
    assert.ok(Math.abs(m.fw - m.cw) <= 1, `the picture is ${m.fw} wide in a ${m.cw} wide box: it does not fill the box`);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, "the page scrolls sideways");
  });

  test(`a mockup that fits whole keeps today's scale, with no scroll and no cue, at ${width} wide`, async (t) => {
    const it = picItem("fits-whole", 58);
    const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(1550) }, viewport: { width, height: 900 } }); if (!page) return;
    await frameSettled(page, 1550);
    await settleFit(page, it.id);
    const m = await measure(page, it.id);
    const want = (480 * 390) / 1550; // the mockup is scaled to the box's 480px, so it is 120.8px wide
    assert.ok(Math.abs(m.fw - want) <= 1, `the picture is ${m.fw} wide, not ${want.toFixed(1)}`);
    assert.ok(Math.abs(m.h - 480) <= 1, `the box is ${m.h} high, not 480`);
    assert.ok(!/scroll/.test(m.cls), "a picture that fits whole scrolls");
    assert.notEqual((await cueState(page, it.id)).disp, "flex", "the cue is drawn on a picture that fits whole");
  });

  test(`a tall focus box that scrolls draws min(221.8, column - 2 - gutter) wide, at ${width} wide`, async (t) => {
    const it = picItem("focus-width", 59, { focus: "#panel" });
    const page = await open(t, { items: [it], designData: { ...PICS, "price-a": FOCUS_TALL }, viewport: { width, height: 900 } }); if (!page) return;
    await frameSettled(page, 2600);
    await page.waitForFunction((sel) => document.querySelector(sel).querySelector("iframe").style.transform.includes("translate"), boxSel(it.id));
    await settleFit(page, it.id);
    const m = await measure(page, it.id), cw = await column(page, it.id);
    const want = Math.min(SCROLL_W, cw - 2 - m.g);
    assert.ok(/scroll/.test(m.cls), "the focus box does not scroll");
    assert.ok(Math.abs(m.fw - want) <= 1, `the focus picture is ${m.fw} wide, not min(${SCROLL_W.toFixed(1)}, ${cw} - 2 - ${m.g}) = ${want.toFixed(1)}`);
  });
}

// Owner ruling (waiting-page item 84 pick b, option 5B), round 2: at 1065 wide the option column binds, so a scrolling picture is column less 2 less the gutter.
// The column is read from its rect, not clientWidth, which rounds up. The budget is floor(rect width) less 2 and the gutter (docs/design/c204-sizes.md item 7).
// The box sits inside the column's edges to 0.01px, and its sizer and picture fit the budget.
const strictBox = (page, id) => page.locator(boxSel(id)).evaluate((w) => {
  const r = w.parentElement.getBoundingClientRect(), wr = w.getBoundingClientRect();
  return {
    wrapL: wr.left, wrapR: wr.right, colL: r.left, colR: r.right, colRectW: r.width,
    sizerW: w.querySelector(".dsizer").getBoundingClientRect().width,
    fw: w.querySelector("iframe").getBoundingClientRect().width,
    g: w.offsetWidth - w.clientWidth - 2,
    cls: w.className,
  };
});

test("a tall picture that scrolls at 1065 wide stays inside its column: the box, the sizer and the picture fit the column less 2 and the gutter", async (t) => {
  const it = picItem("scroll-col", 60);
  const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(2400) }, viewport: { width: 1065, height: 900 } }); if (!page) return;
  await frameSettled(page, 2400);
  await settleFit(page, it.id);
  const s = await strictBox(page, it.id), budget = Math.floor(s.colRectW) - 2 - s.g;
  assert.ok(/scroll/.test(s.cls), "the picture does not scroll");
  assert.ok(s.wrapL >= s.colL - 0.01, `the box starts at ${s.wrapL}, left of its column at ${s.colL}`);
  assert.ok(s.wrapR <= s.colR + 0.01, `the box ends at ${s.wrapR}, past its column's right edge ${s.colR}`);
  assert.ok(s.sizerW <= budget + 0.01, `the sizer is ${s.sizerW} wide, over floor(${s.colRectW}) less 2 and the gutter ${s.g} = ${budget}`);
  assert.ok(Math.abs(s.fw - budget) <= 1, `the picture is ${s.fw} wide, not ${budget}`);
});

test("a picture that differs from its siblings and scrolls at 1065 wide stays inside its column, its 3px border in the gutter", async (t) => {
  const it = picItem("dif-col", 61, { differs: ["picture"] });
  const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(2400) }, viewport: { width: 1065, height: 900 } }); if (!page) return;
  await frameSettled(page, 2400);
  await settleFit(page, it.id);
  assert.ok(await page.locator(boxSel(it.id)).evaluate((w) => !!w.closest(".opic.dif") && getComputedStyle(w).borderLeftWidth === "3px"), "the picture is not a differing picture with a 3px left border");
  const s = await strictBox(page, it.id), budget = Math.floor(s.colRectW) - 2 - s.g;
  assert.ok(/scroll/.test(s.cls), "the differing picture does not scroll");
  assert.ok(s.wrapL >= s.colL - 0.01, `the box starts at ${s.wrapL}, left of its column at ${s.colL}`);
  assert.ok(s.wrapR <= s.colR + 0.01, `the box ends at ${s.wrapR}, past its column's right edge ${s.colR}`);
  assert.ok(s.sizerW <= budget + 0.01, `the sizer is ${s.sizerW} wide, over floor(${s.colRectW}) less 2 and the gutter ${s.g} = ${budget}`);
  assert.ok(Math.abs(s.fw - budget) <= 1, `the picture is ${s.fw} wide, not ${budget}`);
});

test("a resize or a repaint keeps the owner's scroll, the same box, and the scroll hint in the picture's name", async (t) => {
  const it = picItem("once", 36);
  const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(2400) }, viewport: { width: 1440, height: 900 } }); if (!page) return;
  await frameSettled(page, 2400);
  await page.locator(boxSel(it.id)).evaluate((w) => { window.__w = w; w.scrollTop = 150; });
  assert.equal((await measure(page, it.id)).st, 150, "the owner's scroll did not take");
  await page.setViewportSize({ width: 1300, height: 900 });
  await frameWait(page, 2); // the resize fits the pictures in the frames after it
  assert.equal((await measure(page, it.id)).st, 150, "a resize moved the scroll");
  await choose(page, it, "b");
  await frameWait(page, 2); // the pick repaints in the frames after it
  const after = await page.locator(boxSel(it.id)).evaluate((w) => ({ same: w === window.__w, st: w.scrollTop }));
  assert.deepEqual(after, { same: true, st: 150 }, "a repaint replaced the box or moved its scroll");
  const label = await card(page, it).locator(`label.opt[for="o-${it.id}-a"] .opic`).getAttribute("aria-label");
  assert.match(label, /Arrow keys scroll its picture$/, "a repaint dropped the scroll hint from the name");
});

test("the cue shows before the picture's end, goes at the end, and the shades add no height, at 390 wide", async (t) => {
  const it = picItem("cue", 37);
  const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(2400) }, viewport: { width: 390, height: 900 } }); if (!page) return;
  await frameSettled(page, 2400);
  const a = await cueState(page, it.id);
  assert.equal(a.disp, "flex", "the cue is not drawn");
  assert.equal(a.op, 1, "the cue is not fully shown before the end");
  assert.equal(a.text, "↓ More");
  assert.ok(!/at-end/.test(a.cls), "the picture is at its end before any scroll");
  assert.equal(a.top, 0, "the top shade is shown before any scroll");
  const m = await measure(page, it.id);
  assert.ok(Math.abs(m.sh - m.sizer) <= 1, `the scroll height ${m.sh} is not the picture's ${m.sizer}`);
  await page.locator(boxSel(it.id)).evaluate((w) => { w.scrollTop = 200; });
  await page.waitForFunction((sel) => +getComputedStyle(document.querySelector(sel + " .dtop")).opacity === 1, boxSel(it.id));
  await page.locator(boxSel(it.id)).evaluate((w) => { w.scrollTop = w.scrollHeight; });
  await page.waitForFunction((sel) => +getComputedStyle(document.querySelector(sel + " .dcue")).opacity === 0, boxSel(it.id));
});

test("a touch drag scrolls the picture and opens nothing, and a tap opens View, at 390 wide", async (t) => {
  const it = picItem("touch", 42);
  const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(2400) }, viewport: { width: 390, height: 900 } }); if (!page) return;
  await frameSettled(page, 2400);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 1 });
  const touch = (type, points) => cdp.send("Input.dispatchTouchEvent", { type, touchPoints: points });
  await page.locator(boxSel(it.id)).scrollIntoViewIfNeeded();
  const r = await page.locator(boxSel(it.id)).boundingBox();
  const x = r.x + 40, y = r.y + 380;
  await page.locator(boxSel(it.id)).evaluate((w) => { window.__ended = false; w.addEventListener("scrollend", () => { window.__ended = true; }, { once: true }); }); // registered before the drag
  await touch("touchStart", [{ x, y }]);
  for (let i = 1; i <= 6; i++) { await touch("touchMove", [{ x, y: y - i * 40 }]); await frameWait(page, 1); }
  await touch("touchEnd", []);
  await page.waitForFunction(() => window.__ended).catch(() => {}); // the drag's scroll end; a drag that never scrolls leaves the assert below to name it
  assert.ok((await measure(page, it.id)).st > 0, "the touch drag did not scroll the picture");
  assert.equal(await page.locator("#dsheet").isVisible(), false, "the touch drag opened View");
  const r2 = await page.locator(boxSel(it.id)).boundingBox();
  await touch("touchStart", [{ x: r2.x + 40, y: r2.y + 200 }]);
  await touch("touchEnd", []);
  await page.locator("#dsheet").waitFor({ state: "visible" }).catch(() => {}); // a tap opens View at once; the assert below names a miss
  assert.equal(await page.locator("#dsheet").isVisible(), true, "the tap did not open View");
});

test("a press on the scrollbar gutter opens nothing and picks nothing, and a press on the picture opens View, at 1280 wide", async (t) => {
  const it = picItem("press", 41);
  const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(2400) }, viewport: { width: 1280, height: 900 } }); if (!page) return;
  await frameSettled(page, 2400);
  assert.ok((await measure(page, it.id)).g > 0, "this browser draws no scrollbar gutter");
  const r = await page.locator(boxSel(it.id)).boundingBox();
  await page.mouse.click(r.x + r.width - 4, r.y + 100);
  assert.equal(await page.locator("#dsheet").isVisible(), false, "a press on the scrollbar opened View");
  assert.equal(await page.isChecked(`#o-${it.id}-a`), false, "a press on the scrollbar picked the option");
  // A drag that starts on the scroll thumb and ends on the picture scrolls it; it is not a press on the picture.
  await page.mouse.move(r.x + r.width - 4, r.y + 100);
  await page.mouse.down();
  await page.mouse.move(r.x + r.width - 24, r.y + 250, { steps: 15 });
  await page.mouse.up();
  assert.equal(await page.locator("#dsheet").isVisible(), false, "a drag from the scrollbar onto the picture opened View");
  assert.equal(await page.isChecked(`#o-${it.id}-a`), false, "a drag from the scrollbar onto the picture picked the option");
  await page.mouse.click(r.x + 20, r.y + 100);
  assert.equal(await page.locator("#dsheet").isVisible(), true, "a press on the picture did not open View");
});

test("a right-button press on the scrollbar, then Escape, leaves Enter working on None of these, at 1280 wide", async (t) => {
  const it = picItem("stale-right", 43);
  const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(2400) }, viewport: { width: 1280, height: 900 } }); if (!page) return;
  await frameSettled(page, 2400);
  const r = await page.locator(boxSel(it.id)).boundingBox();
  await page.mouse.click(r.x + r.width - 4, r.y + 100, { button: "right" });
  await page.keyboard.press("Escape");
  await card(page, it).getByRole("button", { name: "None of these" }).focus();
  await page.keyboard.press("Enter");
  await page.waitForFunction((id) => document.getElementById(`b-none-${id}`)?.getAttribute("aria-pressed") === "true", it.id);
  assert.equal(await page.getAttribute(`#b-none-${it.id}`, "aria-pressed"), "true", "Enter did not press None of these: a right press on the scrollbar left a stale state");
});

test("a middle press on the scrollbar leaves Space working on an option, at 1280 wide", async (t) => {
  const it = picItem("stale-middle", 44);
  const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(2400) }, viewport: { width: 1280, height: 900 } }); if (!page) return;
  await frameSettled(page, 2400);
  const r = await page.locator(boxSel(it.id)).boundingBox();
  await page.mouse.click(r.x + r.width - 4, r.y + 100, { button: "middle" });
  await page.locator(`#o-${it.id}-b`).focus();
  await page.keyboard.press("Space");
  assert.equal(await page.isChecked(`#o-${it.id}-b`), true, "Space did not pick option b: a middle press on the scrollbar left a stale state");
});

test("a press on the picture released on the scrollbar gutter opens nothing and picks nothing, at 1280 wide", async (t) => {
  const it = picItem("press-out", 45);
  const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(2400) }, viewport: { width: 1280, height: 900 } }); if (!page) return;
  await frameSettled(page, 2400);
  const r = await page.locator(boxSel(it.id)).boundingBox();
  await page.mouse.move(r.x + 20, r.y + 100);
  await page.mouse.down();
  await page.mouse.move(r.x + r.width - 4, r.y + 160, { steps: 10 });
  await page.mouse.up();
  assert.equal(await page.locator("#dsheet").isVisible(), false, "a press on the picture released on the gutter opened View");
  assert.equal(await page.isChecked(`#o-${it.id}-a`), false, "a press on the picture released on the gutter picked the option");
});

test("the picture is one tab stop: its arrow, page and end keys scroll it, Home goes back, and Enter opens View, at 390 wide", async (t) => {
  const it = picItem("keys", 40);
  const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(2400) }, viewport: { width: 390, height: 900 } }); if (!page) return;
  await frameSettled(page, 2400);
  const opic = card(page, it).locator(`label.opt[for="o-${it.id}-a"] .opic`);
  const a = await opic.evaluate((o) => ({ label: o.getAttribute("aria-label"), tab: o.querySelector(".dfitwrap").getAttribute("tabindex"), hidden: o.querySelector(".dfitwrap").getAttribute("aria-hidden"), inert: o.querySelector("iframe").inert }));
  assert.ok(a.tab === "-1" && a.hidden === "true" && a.inert, "the wrap or its frame is a tab stop: " + JSON.stringify(a));
  assert.match(a.label, /Arrow keys scroll its picture$/, "the name lacks the scroll hint");
  await opic.focus();
  await page.keyboard.press("ArrowDown"); await page.keyboard.press("ArrowDown");
  assert.equal((await measure(page, it.id)).st, 80, "two ArrowDown presses did not scroll 80px");
  await page.keyboard.press("PageDown");
  const m = await measure(page, it.id);
  assert.equal(m.st, Math.min(80 + m.ch - 40, m.sh - m.ch), "PageDown did not scroll a page less 40px");
  await page.keyboard.press("End");
  const end = await measure(page, it.id);
  assert.ok(end.st + end.ch >= end.sh - 1, "End did not reach the end");
  const taken = await opic.evaluate((o) => { const e = new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true }); o.dispatchEvent(e); return e.defaultPrevented; });
  assert.equal(taken, false, "at the end, ArrowDown was taken from the page");
  await page.keyboard.press("Home");
  assert.equal((await measure(page, it.id)).st, 0, "Home did not go to the top");
  await page.keyboard.press("Enter");
  assert.equal(await page.locator("#dsheet").isVisible(), true, "Enter did not open View");
});

for (const scheme of ["light", "dark"]) {
  test(`the cue's pill and its text reach 4.5:1, and the box holds 480px, in the ${scheme} scheme`, async (t) => {
    const it = picItem("pill", 38);
    const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(2400) }, viewport: { width: 390, height: 900 }, scheme }); if (!page) return;
    await frameSettled(page, 2400);
    const [onFrame, onPill, h] = await page.evaluate(`(() => {${CONTRAST}
      const rgb = (c) => "#" + c.match(/\\d+/g).slice(0, 3).map((x) => (+x).toString(16).padStart(2, "0")).join("");
      const w = document.querySelector(${JSON.stringify(boxSel(it.id))}), pill = getComputedStyle(w.querySelector(".dmore"));
      return [R(rgb(pill.backgroundColor), rgb(getComputedStyle(w).backgroundColor)), R(rgb(pill.color), rgb(pill.backgroundColor)), w.getBoundingClientRect().height];
    })()`);
    assert.ok(onFrame >= 4.5, `the pill is ${onFrame.toFixed(2)}:1 on the frame`);
    assert.ok(onPill >= 4.5, `the text is ${onPill.toFixed(2)}:1 on the pill`);
    assert.ok(h <= 480, `the box is ${h} high, over 480`);
  });
}

// Each row: name, mockup, focus, mockup height, box width and height, the focus's top in the mockup, and a declared size.
const FIT_CASES = [
  ["a focus that fits", '<body style="margin:0"><div style="height:700px"></div><div id="panel" style="width:300px;height:200px;background:#a62"></div><div style="height:500px"></div></body>', "#panel", 1400, 300, 200, 700],
  ["a 1200px mockup", '<body style="margin:0"><div style="height:1200px;background:#2a6"></div></body>', undefined, 1200, 390, 1200, 0],
  ["a focus with a declared size", '<body style="margin:0;width:700px"><div style="height:700px"></div><div id="panel" style="width:600px;height:400px;background:#a62"></div></body>', "#panel", 1100, 600, 400, 700, { w: 600, h: 400 }],
];
for (const width of [390, 1280, 1440]) {
  for (const [name, mock, focus, H, bw, bh, ty, size] of FIT_CASES) {
    test(`${name} is drawn as today, with no scroll and no cue, at ${width} wide`, async (t) => {
      const it = picItem("fit", 39, { focus, size });
      const page = await open(t, { items: [it], designData: { ...PICS, "price-a": mock }, viewport: { width, height: 900 } }); if (!page) return;
      await frameSettled(page, H);
      if (focus) await page.waitForFunction((sel) => document.querySelector(sel).querySelector("iframe").style.transform.includes("translate"), boxSel(it.id));
      const m = await measure(page, it.id);
      const col = await page.locator(boxSel(it.id)).evaluate((w) => w.parentElement.clientWidth);
      const sc = Math.min(1, (col - 2) / bw, Math.max(480 / bh, 120 / bw));
      assert.equal(m.w, Math.ceil(bw * sc) + 2, "the box width");
      assert.equal(m.h, Math.ceil(bh * sc), "the box height");
      assert.ok(!/scroll/.test(m.cls), "a picture that fits scrolls");
      assert.equal(await page.locator(boxSel(it.id)).evaluate((w) => { const c = w.querySelector(".dcue"); return !c || getComputedStyle(c).display === "none"; }), true, "the cue is drawn on a picture that fits");
      const tf = await page.locator(`${boxSel(it.id)} iframe`).evaluate((f) => f.style.transform);
      assert.ok(Math.abs(+/scale\(([-\d.e]+)\)/.exec(tf)[1] - sc) < 1e-6, `the scale is not the formula's ${sc}: ${tf}`);
      if (focus) assert.ok(Math.abs(+/translate\([^,]*,\s*([-\d.e]+)px\)/.exec(tf)[1] + ty * sc) < 0.01, `the focus is not moved to ${-ty * sc}: ${tf}`);
    });
  }
}

test("a 1564px mockup at 390 wide scrolls in its box, and the cue shows", async (t) => {
  const it = picItem("scroll-edge", 56);
  const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(1564) }, viewport: { width: 390, height: 900 } }); if (!page) return;
  await frameSettled(page, 1564);
  const m = await measure(page, it.id);
  assert.ok(m.sh - m.ch > 0, `the picture does not scroll: its scroll range is ${m.sh - m.ch}px`);
  assert.equal((await cueState(page, it.id)).disp, "flex", "the cue is not drawn on a picture that scrolls");
});

test("a mockup 1px over the fitted height gives a box of at most 480 and no cue, at 390 wide", async (t) => {
  const it = picItem("edge", 53);
  const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(1561) }, viewport: { width: 390, height: 900 } }); if (!page) return;
  await frameSettled(page, 1561);
  const m = await measure(page, it.id);
  assert.ok(m.h <= 480, `the box is ${m.h} high, over 480`);
  assert.notEqual((await cueState(page, it.id)).disp, "flex", "the cue shows on a picture 1px over the fit");
});

test("a picture that differs from its siblings keeps its 3px border inside its box, and still scrolls, at 1280 wide", async (t) => {
  const it = picItem("dif", 5, { differs: ["picture"] });
  const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(2400) }, viewport: { width: 1280, height: 900 } }); if (!page) return;
  await frameSettled(page, 2400);
  await settleFit(page, it.id);
  const m = await measure(page, it.id);
  assert.ok(await page.locator(boxSel(it.id)).evaluate((w) => !!w.closest(".opic.dif")), "the picture is not marked as differing");
  // Owner ruling, waiting-page item 84 pick b (2026-10-30 14:45 CDT), c204 option 5B: the box is the scroll width plus its frame, within the column.
  const cw = await column(page, it.id), want = Math.min(SCROLL_W + 2 + m.g, cw);
  assert.ok(Math.abs(m.w - want) <= 1, `the box is ${m.w} wide, not ${want.toFixed(1)}`);
  assert.ok(m.sh - m.ch > 100 && Math.abs(m.fw - m.cw) <= 1, "the differing picture does not scroll at the content width");
});

test("a tall picture adds no sideways scroll to the page at 390 wide, even scrolled to its end", async (t) => {
  const it = picItem("sideways", 54);
  const page = await open(t, { items: [it], designData: { ...PICS, "price-a": TALL_PIC(2400) }, viewport: { width: 390, height: 900 } }); if (!page) return;
  await frameSettled(page, 2400);
  await page.locator(boxSel(it.id)).evaluate((w) => { w.scrollTop = w.scrollHeight; });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, "the page scrolls sideways");
});

// A 60-character URL has no break point, so the step must wrap inside the card rather than widen it.
const LONG_URL = "https://waiting.test/" + "a".repeat(60 - "https://waiting.test/".length);
for (const width of [430, 390, 360]) {
  test(`a task step with an unbroken 60-character URL stays inside the card and the page, at ${width} wide`, async (t) => {
    const it = { ...TASK, id: "long-url-task", n: 60, steps: [LONG_URL] };
    const page = await open(t, { items: [it], viewport: { width, height: 900 } }); if (!page) return;
    // The card's own box can stay on screen while a step inside it runs past the edge, so take the furthest right of the card and all it holds.
    const right = await card(page, it).evaluate((c) => Math.max(c.getBoundingClientRect().right, ...[...c.querySelectorAll("*")].map((e) => e.getBoundingClientRect().right)));
    assert.ok(right <= width, `the card runs to ${right} px, past the ${width} px screen`);
    const scrollW = await page.evaluate(() => document.documentElement.scrollWidth);
    assert.ok(scrollW <= width, `the page is ${scrollW} px wide on a ${width} px screen`);
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
  const page = await open(t, { items: [{ ...DECISION, added: ASKED_AFTER_SEND }, TASK], answers: { [TASK.id]: { item: TASK.id, n: 28, at: "2026-10-26T01:00:00Z", done: true, note: "" } } }); if (!page) return;
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
  assert.equal(await page.isChecked(`#o-${it.id}-a`), false, "a second click unselects a pick taken by a tap");
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

// The note box is open on every unseen open card, with no Add a note button. A sent card has no box; a card under Change is open.
test("the note box is open on every unseen open card, with no Add a note button, and a sent card shows no box until Change", async (t) => {
  const FRESH = mk("fresh-decision", 29, { added: ASKED_AFTER_SEND });
  const page = await open(t, { items: [DECISION, FRESH, { ...TASK, added: ASKED_AFTER_SEND }], answers: SAVED_A }); if (!page) return;
  assert.equal(await page.locator(`#n-${DECISION.id}`).count(), 0, "a sent card shows a note box");
  for (const it of [FRESH, TASK]) {
    assert.equal(await page.locator(`#n-${it.id}`).isVisible(), true, `${it.id}: the note box is not open on a fresh card`);
  }
  assert.equal(await page.getByRole("button", { name: "Add a note" }).count(), 0, "a card renders an Add a note button");
  await card(page, DECISION).getByRole("button", { name: "Change" }).click();
  assert.equal(await page.locator(`#n-${DECISION.id}`).isVisible(), true, "a sent card under Change shows no note box");
});

// The send bar is fixed at the bottom of the viewport. The page is scrolled so the note box starts 2px above the bar's top.
test("a focused note box at 390 wide ends above the send bar", async (t) => {
  const it = mk("note-low", 62, { context: LONG });
  const page = await open(t, { items: [mk("filler-a", 60, { context: LONG }), it, mk("filler-b", 61, { context: LONG })], viewport: { width: 390, height: 844 } }); if (!page) return;
  const edge = (id) => page.evaluate((k) => ({ bottom: document.getElementById(k).getBoundingClientRect().bottom, barTop: document.getElementById("bar").getBoundingClientRect().top }), id);
  await page.evaluate((k) => window.scrollBy(0, document.getElementById(k).getBoundingClientRect().top - document.getElementById("bar").getBoundingClientRect().top + 2), `n-${it.id}`);
  const before = await edge(`n-${it.id}`);
  assert.ok(before.bottom > before.barTop, `setup: the note box ends at ${Math.round(before.bottom)}, not under the send bar at ${Math.round(before.barTop)}`);
  await page.locator(`#n-${it.id}`).focus();
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => r())));
  const at = await edge(`n-${it.id}`);
  assert.ok(at.bottom <= at.barTop, `the focused note box ends at ${Math.round(at.bottom)}, under the send bar at ${Math.round(at.barTop)}`);
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
  // The saved note sits in the fold, closed on load (answered-sink notes, pick 2): open it to read the note.
  await need(c.locator("button.unfold"), "the saved note has no fold control");
  await c.locator("button.unfold").click();
  assert.match(await c.locator(".rnote").textContent(), /Green/);
  await c.getByRole("button", { name: "Change" }).click();
  await choose(page, DECISION, "b");
  await send(page);
  await page.waitForFunction((id) => window.__answers()[id].choice === "b", DECISION.id);
  assert.equal((await answers(page))[DECISION.id].note, "");
});

// ---------------------------------------------------------------- the notice to Claude

const sent = (page) => page.evaluate(() => window.__sent);
const told = (page, text) => page.locator("#sentStatus", { hasText: text }).waitFor();
// The wake result on the sent panel. The panel reads "Telling Claude…" until notifyClaude has returned, so this waits for that and then reads the words.
// A test asserts on the words, so a failure names its cause and not a locator timeout.
const wakeStatus = async (page) => {
  await page.locator("#sentStatus").waitFor();
  await page.waitForFunction(() => !document.getElementById("sentStatus").textContent.includes("Telling"), null, { timeout: 3000 }).catch(() => {});
  return (await page.textContent("#sentStatus")).trim();
};
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
  // The note sits in the fold, closed on load (answered-sink notes, pick 2): open it to read the note.
  await need(c.locator("button.unfold"), "the saved note-only answer has no fold control");
  await c.locator("button.unfold").click();
  assert.match(await c.locator(".rnote").textContent(), /^Note: Which cable\?$/);
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
  const page = await open(t, { items: [{ ...DECISION, added: ASKED_AFTER_SEND }, TASK], answers: { [TASK.id]: { item: TASK.id, n: 28, at: "2026-10-26T01:00:00Z", done: true, note: "" } }, failSet: true }); if (!page) return;
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
  await told(page, "A wake was sent");
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

test("a tap on each star on two cards and one Send gives exactly one notice for the batch", async (t) => {
  const two = { ...DECISION, id: "pick-a-shape", n: 29, title: "Pick a shape" };
  const page = await open(t, { items: [DECISION, two, TASK] }); if (!page) return;
  await takePick(page, DECISION); await takePick(page, two);
  await send(page);
  await page.waitForFunction(() => window.__sent.length >= 1);
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 2);
  await page.waitForFunction(() => !state.sending); // a second send can only land while this batch is in flight
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
  await told(page, "A wake was sent");
  const s = await sent(page);
  assert.equal(s.length, 2);
  assert.equal(s[0].threadId, "t-old");
  assert.ok(s[1].anchor && s[1].anchor.tag === "H1", "the new thread anchors at the h1");
  assert.equal(await page.evaluate(() => localStorage.getItem("waiting.thread")), "t-new-2");
});

// One pick sent while the stored thread rejects with `code`. anchorFail is the code the anchored retry rejects with, when it is given.
// Returns the page, the wake result and the sends, or null with no browser.
async function pickIntoStoredFail(t, { code, anchorFail = "" }) {
  const page = await open(t, { comments: { can: "available", threadFail: { "t-old": code }, anchorFail }, storage: { "waiting.thread": "t-old" } });
  if (!page) return null;
  await takePick(page, DECISION); await send(page);
  return { page, status: await wakeStatus(page), s: await sent(page) };
}
// Codes a stored thread must not retry: a rate limit or a refusal that a second thread cannot undo. Each sends once, keeps the thread and shows its code.
const NO_FALLBACK = ["rate_limited", "claude_unavailable", "consent_required", "invalid", "unavailable", "forbidden", "not_granted", "capability_disabled", "capability_removed", "transform_error"];
const storedThread = (page) => page.evaluate(() => localStorage.getItem("waiting.thread"));

test("an upstream_error on the stored thread starts a new anchored thread", async (t) => {
  const r = await pickIntoStoredFail(t, { code: "upstream_error" }); if (!r) return;
  assert.equal(r.s[0].threadId, "t-old", "the first send did not go to the stored thread");
  assert.equal(r.s.length, 2, "upstream_error on the stored thread did not start one anchored retry: " + r.s.length + " send(s)");
  assert.ok(r.s[1].anchor && r.s[1].anchor.tag === "H1", "the retry does not anchor at the h1");
  assert.match(r.status, /A wake was sent/, "the wake result does not say a wake was sent: " + JSON.stringify(r.status));
  assert.equal(await storedThread(r.page), "t-new-2", "the new thread id is not stored");
});

test("an unknown code on the stored thread starts a new anchored thread, as upstream_error does", async (t) => {
  const r = await pickIntoStoredFail(t, { code: "thread_full" }); if (!r) return;
  assert.equal(r.s[0].threadId, "t-old", "the first send did not go to the stored thread");
  assert.equal(r.s.length, 2, "an unknown code on the stored thread did not start one anchored retry: " + r.s.length + " send(s)");
  assert.ok(r.s[1].anchor && r.s[1].anchor.tag === "H1", "the retry does not anchor at the h1");
  assert.match(r.status, /A wake was sent/, "the wake result does not say a wake was sent: " + JSON.stringify(r.status));
  assert.equal(await storedThread(r.page), "t-new-2", "the new thread id is not stored");
});

for (const code of NO_FALLBACK) {
  test(`${code} on the stored thread sends once, shows ${code}, and keeps the thread`, async (t) => {
    const r = await pickIntoStoredFail(t, { code }); if (!r) return;
    assert.equal(r.s[0].threadId, "t-old", "the send did not go to the stored thread");
    assert.equal(r.s.length, 1, `${code} on the stored thread started a second send: ${r.s.length} sends`);
    assert.equal(await storedThread(r.page), "t-old", `${code} on the stored thread replaced the stored thread`);
    assert.ok(r.status.includes("No session was told"), "the wake result does not say no session was told: " + JSON.stringify(r.status));
    assert.ok(r.status.includes(code), `the wake result does not show the code ${code}: ` + JSON.stringify(r.status));
    assert.doesNotMatch(r.status, NO_THREAD, "the wake result names a thread: " + JSON.stringify(r.status));
  });
}

test("an upstream_error on the stored thread and on the anchored retry gives one retry and no third send", async (t) => {
  const r = await pickIntoStoredFail(t, { code: "upstream_error", anchorFail: "upstream_error" }); if (!r) return;
  assert.equal(r.s[0].threadId, "t-old", "the first send did not go to the stored thread");
  assert.equal(r.s.length, 2, "expected the stored send and one anchored retry, got " + r.s.length + " send(s)");
  assert.equal(await storedThread(r.page), "t-old", "a failed retry replaced the stored thread");
  assert.ok(r.status.includes("No session was told"), "the wake result does not say no session was told: " + JSON.stringify(r.status));
  assert.ok(r.status.includes("upstream_error"), "the wake result does not show upstream_error: " + JSON.stringify(r.status));
  assert.doesNotMatch(r.status, NO_THREAD, "the wake result names a thread: " + JSON.stringify(r.status));
});

test("a claude_unavailable on a first send with no stored thread shows the code", async (t) => {
  const page = await open(t, { comments: { can: "available", failCode: "claude_unavailable" } }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  const status = await wakeStatus(page);
  const s = await sent(page);
  assert.equal(s.length, 1, "a first send with no stored thread did not go out once: " + s.length + " send(s)");
  assert.ok(s[0].anchor, "the first send is not anchored");
  assert.ok(status.includes("No session was told"), "the wake result does not say no session was told: " + JSON.stringify(status));
  assert.ok(status.includes("claude_unavailable"), "the wake result does not show claude_unavailable: " + JSON.stringify(status));
  assert.doesNotMatch(status, NO_THREAD, "the wake result names a thread: " + JSON.stringify(status));
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
  for (const it of many) await takePick(page, it);
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
  await page.waitForFunction(() => window.__sent.length >= 1 && !state.sending); // the notice is out, and sendAll has cleared sending last
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
  await told(page, "A wake was sent");
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
  await frameWait(page, 2); // the stub store settles in microtasks, so a late delete lands before the next frame
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
  // TASK first: open() waits for the first item's card, and a filed item draws as one line, not a card.
  const page = await open(t, { items: [TASK, DECISION], answers: SAVED_A }); if (!page) return;
  assert.match(await mark(page), /○/);
  await page.close();
  const page2 = await open(t, { items: [TASK, DECISION], answers: SAVED_A, receipts: { [DECISION.id]: { filed: "2026-10-26T03:00:00Z" } } }); if (!page2) return;
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
  await told(page, "A wake was sent");
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

test("a pick is named by the option's title in the ready line, shortened with an ellipsis, never by its raw key", async (t) => {
  const it = mk("pick-names", 41, { options: WORDY, pick: "value", why: "Value fits." });
  const page = await open(t, { items: [it] }); if (!page) return;
  await takePick(page, it);
  const ready = await card(page, it).locator(".ready").textContent();
  assert.doesNotMatch(ready, /VALUE|value\)/, "the ready line shows the raw key: " + ready);
  assert.match(ready, /^Ready to send: Value for the card.*…, your choice\.$/, ready);
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
  assert.deepEqual((await order(page)).find((x) => x[0] === "tier-calm")[1], ["new-rank1", "old-rank2", "new-none", "old-none"]);
});

// Inside a tier the newest ask comes first, so the freshest asks are the ones answered first.
test("inside a tier, the newest item comes first, and rank still leads", async (t) => {
  const items = [
    mk("calm-old", 1, { added: at(1) }), mk("calm-new", 2, { added: at(9) }), mk("calm-mid", 3, { added: at(5) }),
    mk("hold-old", 4, { added: at(1), holds: "A lane waits." }), mk("hold-new", 5, { added: at(9), holds: "A lane waits." }),
    mk("rank-old", 6, { added: at(2), rank: 0, stands: true }), mk("rank-new", 7, { added: at(8), rank: 1, stands: true }),
  ];
  const page = await open(t, { items }); if (!page) return;
  const by = Object.fromEntries(await order(page));
  assert.deepEqual(by["tier-calm"], ["calm-new", "calm-mid", "calm-old"]);
  assert.deepEqual(by["tier-holds"], ["hold-new", "hold-old"]);
  assert.deepEqual(by["tier-stands"], ["rank-old", "rank-new"], "rank must still lead age");
});

// A group sits at its newest member's time, as the Answered section does; an item with no valid date comes last among the new items.
test("inside a tier, a group sits at its newest member, and an undated item comes last among the new items", async (t) => {
  const items = [
    mk("solo-mid", 1, { added: at(5) }), mk("solo-old", 2, { added: at(1) }), mk("undated", 3, { added: "garbage" }),
    mk("grp-old", 4, { added: at(2), group: "g" }), mk("grp-new", 5, { added: at(9), group: "g" }),
  ];
  const page = await open(t, { items }); if (!page) return;
  assert.deepEqual((await order(page)).find((x) => x[0] === "tier-calm")[1], ["grp-new", "grp-old", "solo-mid", "solo-old", "undated"]);
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

// The skill's text: SKILL.md plus every reference/*.md, since its steps moved into reference/. A check on what the skill says reads all of it.
function skillText() {
  const dir = path.join(HERE, "..", "reference");
  const refs = fs.readdirSync(dir).filter((f) => f.endsWith(".md")).sort();
  assert.ok(refs.length > 0, "reference/ has no .md file, so the skill's text would be SKILL.md alone");
  return [fs.readFileSync(path.join(HERE, "..", "SKILL.md"), "utf8"), ...refs.map((f) => fs.readFileSync(path.join(dir, f), "utf8"))].join("\n");
}

test("the skill names the page's one writer and the rank field", async () => {
  const skill = skillText();
  assert.match(skill, /`writer`/);
  assert.match(skill, /`rank`/);
  assert.match(skill, /re-rank/i);
  const rule = fs.readFileSync(path.join(HERE, "..", "..", "..", "docs", "decisions", "questions-go-to-owner.md"), "utf8");
  assert.match(rule, /one writer/i);
  assert.match(rule, /`rank`/);
});

// Decision questions-go-to-owner, "Answer on the page, not in a comment thread":
// a rebuilt page drops its threads, so a session rewrites the item instead.
test("the skill answers a comment by rewriting the item, never in a comment thread", async () => {
  const skill = skillText();
  assert.doesNotMatch(skill, /action `reply`/);
  assert.doesNotMatch(skill, /reply in the comment thread/i);
  assert.match(skill, /never reply in a comment thread/i);
  assert.match(skill, /rewrite that item/i);
});

// ---------------------------------------------------------------- seen items sink

// A seen item is open, has no answer, and was added before the last send. Inside its tier it sinks
// below the new items and folds until the owner unfolds it. lastSend here is a closed item's last answer.
const SENT_AT = at(10);
const sentItem = () => mk("sent-closed", 90, { status: "closed", lastAnswer: { choice: "a", at: SENT_AT, note: "" } });
const idsInSection = async (page, k) => (await order(page)).find((x) => x[0] === "tier-" + k)[1];
const seenOf = (page, it) => card(page, it).getAttribute("data-seen");
const optsShown = (page, it) => card(page, it).locator(".opts").isVisible();

// An item the owner still owes never folds: only an answered card folds. Its options show with no fold control.
// The new item is a task: a seen decision would lead a task on kind alone, so only the seen sink puts it last.
test("a seen, owed decision sinks under a new one in Whenever, and its options show with no fold press", async (t) => {
  const seen = mk("seen-old", 1, { added: at(5) }), fresh = { ...TASK, id: "fresh-new", n: 2, added: at(20) };
  const page = await open(t, { items: [seen, fresh, sentItem()] }); if (!page) return;
  assert.equal(await seenOf(page, seen), "true", "the seen item is not marked seen");
  assert.notEqual(await seenOf(page, fresh), "true", "the new item is marked seen");
  assert.deepEqual(await idsInSection(page, "calm"), ["fresh-new", "seen-old"], "the seen decision leads the new task in Whenever");
  assert.equal(await card(page, fresh).locator("ol.steps").isVisible(), true, "a new task's steps are hidden");
  assert.equal(await card(page, seen).locator("button.unfold").count(), 0, "a seen, owed decision has a fold control");
  assert.equal(await optsShown(page, seen), true, "a seen, owed decision's options are hidden until a fold press");
});

// A seen, owed task has no fold control: its steps and its command show at once.
test("a seen, owed task's steps and command show with no fold press", async (t) => {
  const seen = { ...TASK, id: "seen-task", n: 37, title: "Seen task", added: at(5), steps: ["Open a terminal", "Paste the command and run it"], command: "echo seen" };
  const page = await open(t, { items: [seen, sentItem()] }); if (!page) return;
  assert.equal(await seenOf(page, seen), "true", "the seen task is not marked seen");
  assert.equal(await card(page, seen).locator("button.unfold").count(), 0, "a seen, owed task has a fold control");
  assert.equal(await card(page, seen).locator("ol.steps").isVisible(), true, "a seen, owed task's steps are hidden");
  assert.equal(await card(page, seen).locator(".cmd").isVisible(), true, "a seen, owed task's command is hidden");
});

// A seen card answered on the page, then changed to an empty draft (a withdraw pending), has no fold control to lock: its options stay open.
test("a withdraw pending on a seen card that was answered on the page leaves no fold to lock, and its options stay open", async (t) => {
  const seen = mk("seen-answered", 1, { added: at(5) });
  const page = await open(t, { items: [seen, sentItem()], pageHtml: withSentMove("stay") }); if (!page) return;
  const c = card(page, seen);
  assert.equal(await seenOf(page, seen), "true", "the card is not seen");
  assert.equal(await c.locator("button.unfold").count(), 0, "a seen, owed card has a fold control");
  await choose(page, seen, "a");
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], seen.id);
  await c.getByRole("button", { name: "Change" }).click();
  await choose(page, seen, "a"); // the owner empties the draft: Send will withdraw the saved answer
  assert.equal(await page.locator("#send").textContent(), "Withdraw answer");
  assert.equal(await c.locator("button.unfold").count(), 0, "a seen card changed on the page has a fold control");
  assert.equal(await optsShown(page, seen), true, "a seen card changed on the page hides its options under a pending withdraw");
});

test("a group seen at load counts as new once a member is added after load, and sorts in the new part", async (t) => {
  const a = mk("grp-a", 1, { group: "pair", added: at(5) }), b = mk("grp-b", 2, { group: "pair", added: at(5) });
  const page = await open(t, { items: [a, b, mk("solo-seen", 3, { added: at(5) }), sentItem()] }); if (!page) return;
  assert.equal(await seenOf(page, a), "true", "the group is not seen at load");
  const late = mk("grp-c", 4, { group: "pair", added: at(20) });
  await page.evaluate((it) => window.__putItem(it), late);
  await card(page, late).waitFor();
  for (const it of [a, b, late]) assert.notEqual(await seenOf(page, it), "true", `${it.id} is still seen after its group gained a new member`);
  const ids = await page.evaluate(() => [...document.querySelectorAll("article.card, #seen-div")].map((e) => e.id));
  const divider = ids.indexOf("seen-div");
  assert.ok(divider >= 0, "no seen divider on the page");
  for (const it of [a, b, late]) assert.ok(ids.indexOf("item-" + it.id) < divider, `${it.id} sorts below the seen divider`);
});

// Fold ids come from the number, so two items that share a number must still get their own. The owed pair draws no fold control;
// the answered pair folds, and each fold id is on one element.
test("two items with the same number: owed ones draw no fold, and answered ones get unique fold ids", async (t) => {
  const owed = [mk("same-n-a", 7, { added: at(5) }), mk("same-n-b", 7, { added: at(5) })];
  const sunk = [mk("same-n-c", 7, { added: at(6), reply: "Thanks, noted." }), mk("same-n-d", 7, { added: at(6), reply: "Thanks, noted." })];
  const page = await open(t, { items: [...owed, ...sunk], answers: { ...answerOf(sunk[0]), ...answerOf(sunk[1]) } }); if (!page) return;
  for (const it of owed) assert.equal(await card(page, it).locator("button.unfold").count(), 0, `${it.id}: an owed item has a fold control`);
  for (const it of sunk) {
    await need(card(page, it).locator("button.unfold"), `${it.id}: an answered item with a reply has no fold control`);
    const target = await card(page, it).locator("button.unfold").getAttribute("aria-controls");
    const count = await page.evaluate((id) => document.querySelectorAll('[id="' + id + '"]').length, target);
    assert.equal(count, 1, `${it.id}: fold id "${target}" is on ${count} elements`);
  }
});

// A push of an unrelated item re-renders the page; the note box the owner is typing in must keep its caret.
test("typing in a note box keeps the caret when an unrelated item arrives", async (t) => {
  const page = await open(t); if (!page) return;
  const ta = page.locator(`#n-${DECISION.id}`), other = mk("caret-other", 9);
  await ta.fill("hello world");
  await ta.evaluate((el) => { el.focus(); el.setSelectionRange(5, 5); window.__ta = el; });
  await page.evaluate((it) => window.__putItem(it), other);
  await card(page, other).waitFor();
  const after = await page.evaluate((id) => { const el = document.getElementById("n-" + id); return { same: el === window.__ta, value: el.value, start: el.selectionStart, focused: document.activeElement === el }; }, DECISION.id);
  assert.equal(after.same, true, "the note box was rebuilt by an unrelated push");
  assert.equal(after.value, "hello world", "the note text changed");
  assert.equal(after.start, 5, `the caret moved to ${after.start}`);
  assert.equal(after.focused, true, "the note box lost focus");
});

// The seen divider's words say what is true of every seen card: asked before the last Send. An answered seen card stays below it until reload.
test("the seen divider reads Asked before, and never claims a card is not answered", async (t) => {
  const seen = mk("seen-divider", 1, { added: at(5) });
  const page = await open(t, { items: [seen, sentItem()] }); if (!page) return;
  const words = (await page.locator("#seen-div").textContent()).replace(/\s+/g, " ").trim();
  assert.match(words, /Asked before/, `the divider reads "${words}"`);
  assert.doesNotMatch(words, /not answered/i, "the divider claims a seen card is not answered");
});

// A sunk card taken to Change draws its fold with the label of its parts. Each case reads that label off the fold.
// A sunk decision with one option labels its fold in the singular.
test("a sunk decision with one option, taken to Change, labels its fold Show the 1 option", async (t) => {
  const it = mk("sunk-one-option", 1, { added: at(5), options: [opt("a", "Red")] });
  const page = await open(t, { items: [it], answers: answerOf(it) }); if (!page) return;
  assert.equal(await sectionOf(page, it), "tier-answered", `No. ${it.n} is not in the Answered section`);
  await card(page, it).getByRole("button", { name: "Change" }).click();
  const fold = card(page, it).locator("button.unfold");
  await need(fold, `No. ${it.n} has no fold control after Change`);
  assert.equal((await fold.locator(".uf-show").textContent()).trim(), "Show the 1 option", `the fold label of No. ${it.n} is not "Show the 1 option"`);
});

// A sunk task with one step labels its fold in the singular.
test("a sunk task with one step, taken to Change, labels its fold Show the 1 step", async (t) => {
  const it = { ...TASK, id: "sunk-one-step", n: 41, title: "One step", added: at(5), steps: ["Open a terminal"] };
  const page = await open(t, { items: [it], answers: { [it.id]: { item: it.id, n: it.n, at: ANSWERED_AT, done: true, note: "" } } }); if (!page) return;
  assert.equal(await sectionOf(page, it), "tier-answered", `No. ${it.n} is not in the Answered section`);
  await card(page, it).getByRole("button", { name: "Change" }).click();
  const fold = card(page, it).locator("button.unfold");
  await need(fold, `No. ${it.n} has no fold control after Change`);
  assert.equal((await fold.locator(".uf-show").textContent()).trim(), "Show the 1 step", `the fold label of No. ${it.n} is not "Show the 1 step"`);
});

// A sunk task with no steps and no command has no count to show, so its fold names its own parts and no zero count.
test("a sunk task with no steps and no command, taken to Change, labels its fold Show Mark done and the note, not a zero count", async (t) => {
  const it = { ...TASK, id: "sunk-bare", n: 42, title: "Bare task", added: at(5), steps: [] };
  const page = await open(t, { items: [it], answers: { [it.id]: { item: it.id, n: it.n, at: ANSWERED_AT, done: true, note: "" } } }); if (!page) return;
  assert.equal(await sectionOf(page, it), "tier-answered", `No. ${it.n} is not in the Answered section`);
  await card(page, it).getByRole("button", { name: "Change" }).click();
  const fold = card(page, it).locator("button.unfold");
  await need(fold, `No. ${it.n} has no fold control after Change`);
  assert.equal((await fold.locator(".uf-show").textContent()).trim(), "Show Mark done and the note", `the fold label of No. ${it.n} is not "Show Mark done and the note"`);
  assert.doesNotMatch(await card(page, it).textContent(), /\b0 steps\b/, `the card of No. ${it.n} counts steps that do not exist`);
});

test("a seen item sinks below a new one even when the seen item holds the higher rank", async (t) => {
  const seen = mk("seen-ranked", 1, { added: at(5), rank: 1 }), fresh = mk("fresh-ranked", 2, { added: at(20), rank: 2 });
  const page = await open(t, { items: [seen, fresh, sentItem()] }); if (!page) return;
  assert.deepEqual(await idsInSection(page, "calm"), ["fresh-ranked", "seen-ranked"]);
  assert.equal(await seenOf(page, seen), "true", "the seen item is not marked seen");
});

// The new item is a task: a seen decision would lead a task on kind alone, so only the seen sink puts it last.
test("a seen item with a draft keeps its options open and still sinks", async (t) => {
  const seen = mk("draft-seen", 1, { added: at(5) }), fresh = { ...TASK, id: "draft-fresh", n: 2, added: at(20) };
  const storage = { "waiting.draft": JSON.stringify({ [seen.id]: { choice: "b" } }) };
  const page = await open(t, { items: [seen, fresh, sentItem()], storage }); if (!page) return;
  assert.equal(await seenOf(page, seen), "true", "the seen item is not marked seen");
  assert.deepEqual(await idsInSection(page, "calm"), ["draft-fresh", "draft-seen"], "the seen decision leads the new task in Whenever");
  assert.equal(await optsShown(page, seen), true, "a seen item with a draft is folded");
});

test("a seen stood pick sinks under a new one in Pick stands, and its options stay open", async (t) => {
  // The seen pick holds the better rank, so only the seen sink puts it last.
  const seen = mk("stand-seen", 1, { added: at(5), stands: true, rank: 1 }), fresh = mk("stand-fresh", 2, { added: at(20), stands: true, rank: 2 });
  const page = await open(t, { items: [seen, fresh, sentItem()] }); if (!page) return;
  assert.equal(await seenOf(page, seen), "true", "the seen stood pick is not marked seen");
  assert.deepEqual(await idsInSection(page, "stands"), ["stand-fresh", "stand-seen"], "the seen stood pick leads the new one in Pick stands");
  assert.equal(await optsShown(page, seen), true, "a seen stood pick is folded");
});

test("with no answer anywhere, nothing is seen and Whenever stays newest first", async (t) => {
  const older = mk("no-send-old", 1, { added: at(5) }), newer = mk("no-send-new", 2, { added: at(20) });
  const page = await open(t, { items: [older, newer] }); if (!page) return;
  assert.deepEqual(await idsInSection(page, "calm"), ["no-send-new", "no-send-old"]);
  for (const it of [older, newer]) {
    assert.notEqual(await seenOf(page, it), "true", `${it.id} is marked seen with no lastSend`);
    assert.equal(await optsShown(page, it), true, `${it.id} folds with no lastSend`);
  }
});

test("a group with one new member is new as a whole, so a seen item in its tier sinks under it", async (t) => {
  // The seen solo holds the better rank, and the group holds rank 2, so only the seen sink puts the solo under the group.
  const solo = mk("g-solo", 1, { added: at(8), rank: 1 });
  const older = mk("g-old", 2, { added: at(5), group: "pair", rank: 2 }), newer = mk("g-new", 3, { added: at(20), group: "pair", rank: 2 });
  const page = await open(t, { items: [solo, older, newer, sentItem()] }); if (!page) return;
  assert.equal(await seenOf(page, solo), "true", "the seen item is not marked seen");
  assert.notEqual(await seenOf(page, older), "true", "a group with a new member is marked seen");
  assert.notEqual(await seenOf(page, newer), "true", "the new member is marked seen");
  assert.deepEqual(await idsInSection(page, "calm"), ["g-new", "g-old", "g-solo"], "the seen solo sits above the group in Whenever");
});

// ---------------------------------------------------------------- a reply or a step since the last visit
// An item is new when its replied time is later than both the owner's last Send and the
// viewer's last visit (waiting.visit, an ISO time the page writes on load after it reads the marks). A roadmap step is new when
// its updatedAt is later than that visit. Items and steps share the one visit time. A new answered card opens at load and
// carries the mark; an owed card never folds. The mark uses the asks' green New answer style, so no case asserts a colour.
const VISIT_AT = "2026-10-27T00:00:00Z";
const VISIT = { "waiting.visit": VISIT_AT };
// The page's clock for the cases that load a page: fixed, so the visit the page writes is known without the real clock.
const LOAD_AT = "2026-11-06T18:00:00Z";
// Later than the last Send (ANSWERED_AT, 2026-10-26T01:00Z) and later than the visit.
const REPLIED_AT = "2026-10-28T09:00:00Z";
const NEW_MARK = "New reply since your last Send";
// An answered item with a reply. Its fold holds the note and the reply, so the fold has parts to open.
const repliedCard = (over = {}) => mk("reply-sunk", 1, { added: at(5), reply: "Thanks, noted.", replied: REPLIED_AT, ...over });
// The mark's name as a reader hears it: its aria-label, else its words (hidden tail included). Null when the card draws no mark.
const markName = async (page, it) => {
  const m = card(page, it).locator(".newmark");
  if ((await m.count()) === 0) return null;
  return m.first().evaluate((el) => (el.getAttribute("aria-label") || el.textContent).replace(/\s+/g, " ").trim());
};

// Case 1: a reply newer than the last Send and the visit opens the answered card at load, and the card carries the mark.
test("an answered item whose reply is newer than the last Send and the last visit opens at load, with the New reply mark", async (t) => {
  const it = repliedCard();
  const page = await open(t, { items: [it], answers: answerOf(it, "a", { note: "Kept the red one." }), storage: VISIT }); if (!page) return;
  assert.equal(await sectionOf(page, it), "tier-answered", `No. ${it.n} is not in the Answered section`);
  const fold = card(page, it).locator("button.unfold");
  await need(fold, `No. ${it.n} has no fold control`);
  assert.equal(await fold.getAttribute("aria-expanded"), "true", `No. ${it.n} is folded on load, though its reply is newer than the last Send and the visit`);
  assert.equal(await card(page, it).locator(".rnote").isVisible(), true, `No. ${it.n} hides its note on load`);
  assert.equal(await markName(page, it), NEW_MARK, `No. ${it.n} draws no New reply mark`);
});

// Case 2: Change on the reopened card locks its fold open and keeps the mark for the visit.
test("a Change on a reopened card keeps its fold locked open, and the New reply mark stays shown", async (t) => {
  const it = repliedCard();
  const page = await open(t, { items: [it], answers: answerOf(it, "a", { note: "Kept the red one." }), storage: VISIT }); if (!page) return;
  const c = card(page, it), fold = c.locator("button.unfold");
  await c.getByRole("button", { name: "Change" }).click();
  await need(fold, `No. ${it.n} has no fold control after Change`);
  assert.equal(await fold.getAttribute("aria-expanded"), "true", "Change left the fold closed");
  assert.equal(await fold.getAttribute("aria-disabled"), "true", "Change left the fold unlocked");
  assert.equal(await markName(page, it), NEW_MARK, `Change dropped the New reply mark on No. ${it.n}`);
});

// Change, then an emptied draft: Send will withdraw the saved answer. The fold stays locked open until the withdraw is sent or cancelled.
test("a fold stays locked open while a Change's emptied draft waits to be withdrawn", async (t) => {
  const it = repliedCard();
  const page = await open(t, { items: [it], answers: answerOf(it, "a"), storage: VISIT }); if (!page) return;
  const c = card(page, it), fold = c.locator("button.unfold");
  await c.getByRole("button", { name: "Change" }).click();
  await choose(page, it, "a");
  assert.equal(await page.locator("#send").textContent(), "Withdraw answer", `No. ${it.n} does not offer Withdraw once its draft is emptied`);
  await need(fold, `No. ${it.n} has no fold control under a pending withdraw`);
  assert.equal(await fold.getAttribute("aria-disabled"), "true", `No. ${it.n} unlocks its fold under a pending withdraw`);
});

// A reply older than the last Send stays folded, with no mark.
test("a reply older than the last Send stays folded, with no New reply mark", async (t) => {
  const it = repliedCard({ replied: "2026-10-26T00:30:00Z" });
  const page = await open(t, { items: [it], answers: answerOf(it, "a", { note: "Kept the red one." }), storage: VISIT }); if (!page) return;
  const fold = card(page, it).locator("button.unfold");
  await need(fold, `No. ${it.n} has no fold control`);
  assert.equal(await fold.getAttribute("aria-expanded"), "false", `No. ${it.n} opens on load for a reply older than the last Send`);
  assert.equal(await markName(page, it), null, `No. ${it.n} draws a New reply mark for a reply older than the last Send`);
});

// A reply later than the last Send but earlier than the last visit stays folded, with no mark.
test("a reply later than the last Send but earlier than the last visit stays folded, with no New reply mark", async (t) => {
  const it = repliedCard({ replied: "2026-10-26T12:00:00Z" });
  const page = await open(t, { items: [it], answers: answerOf(it, "a", { note: "Kept the red one." }), storage: VISIT }); if (!page) return;
  const fold = card(page, it).locator("button.unfold");
  await need(fold, `No. ${it.n} has no fold control`);
  assert.equal(await fold.getAttribute("aria-expanded"), "false", `No. ${it.n} opens on load for a reply earlier than the last visit`);
  assert.equal(await markName(page, it), null, `No. ${it.n} draws a New reply mark for a reply earlier than the last visit`);
});

// Case 3: a sunk item whose lastAnswer holds the owner's own answer, with no replied time, stays folded and draws no mark after a
// Send on the open page. lastAnswer alone is no reply.
test("a sunk item with lastAnswer set and no replied time stays folded with no New reply mark after a Send", async (t) => {
  const sunk = mk("sunk-same", 1, { added: at(5), lastAnswer: { choice: "a", at: ANSWERED_AT, note: "" } }), fresh = mk("send-fresh", 2, { added: NEW_ADDED });
  const page = await open(t, { items: [sunk, fresh], answers: answerOf(sunk), storage: VISIT, clock: LOAD_AT }); if (!page) return;
  assert.equal(await sectionOf(page, sunk), "tier-answered", `No. ${sunk.n} is not in the Answered section`);
  const fold = card(page, sunk).locator("button.unfold");
  await need(fold, `No. ${sunk.n} has no fold control`);
  assert.equal(await fold.getAttribute("aria-expanded"), "false", `No. ${sunk.n} is folded open on load with no replied time`);
  assert.equal(await markName(page, sunk), null, `No. ${sunk.n} draws a New reply mark with no replied time`);
  await choose(page, fresh, "b");
  await send(page);
  await written(page);
  assert.equal(await fold.getAttribute("aria-expanded"), "false", `a Send on the open page opened No. ${sunk.n}`);
  assert.equal(await markName(page, sunk), null, `a Send on the open page drew a New reply mark on No. ${sunk.n}`);
});

// Case 4: a Send on the open page moves no card and no mark. The card layout and the New reply mark read the same after it.
test("a Send on the open page moves no card and no New reply mark", async (t) => {
  const reply = repliedCard(), fresh = mk("send-open", 2, { added: NEW_ADDED });
  const page = await open(t, { items: [reply, fresh], answers: answerOf(reply, "a", { note: "Kept the red one." }), storage: VISIT, clock: LOAD_AT, pageHtml: withSentMove("stay") }); if (!page) return;
  assert.equal(await sectionOf(page, reply), "tier-answered", `No. ${reply.n} is not in the Answered section`);
  const before = await layout(page), markBefore = await markName(page, reply);
  assert.equal(markBefore, NEW_MARK, `No. ${reply.n} draws no New reply mark before the Send`);
  await choose(page, fresh, "b");
  await send(page);
  await written(page);
  await card(page, fresh).locator(".receipt").waitFor();
  assert.deepEqual(await layout(page), before, "a Send on the open page moved a card");
  assert.equal(await markName(page, reply), markBefore, `a Send on the open page changed the mark on No. ${reply.n}`);
});

// Case 5: a step updated after the visit draws open, and its row names the update.
test("a step updated after the last visit draws open, and its row says Updated since your last visit", async (t) => {
  const steps = stepsOf([["c1", "v2", 1, "active"], ["a2", "v2", 2, "todo"]]);
  steps.a2.updatedAt = REPLIED_AT;
  const page = await open(t, { pageHtml: phasePage(steps), storage: VISIT }); if (!page) return;
  await assertBaked(page, steps);
  await openStatus(page);
  const row = page.locator('button[data-row="a2"]');
  await need(row, "the step a2 has no row in the phase list");
  assert.equal(await row.getAttribute("aria-expanded"), "true", "a2 draws closed though it was updated after the last visit");
  assert.match(await page.locator("#s-a2").getAttribute("class"), /\bopen\b/, "a2's row does not carry the open class");
  const label = await row.getAttribute("aria-label");
  assert.match(label, /\. Updated since your last visit$/, `the row label is "${label}"`);
});

// A step updated before the last visit stays closed, with no Updated words.
test("a step updated before the last visit stays closed, with no Updated words", async (t) => {
  const steps = stepsOf([["c1", "v2", 1, "active"], ["a2", "v2", 2, "todo"]]);
  const page = await open(t, { pageHtml: phasePage(steps), storage: VISIT }); if (!page) return;
  await assertBaked(page, steps);
  await openStatus(page);
  const row = page.locator('button[data-row="a2"]');
  await need(row, "the step a2 has no row in the phase list");
  assert.equal(await row.getAttribute("aria-expanded"), "false", "a2 draws open though it was last updated before the visit");
  assert.doesNotMatch(await row.getAttribute("aria-label"), /Updated since your last visit/, "a2's row names an update before the visit");
});

// Case 6: a replied time moves no card. The same page with and without replied draws every card in the same section and order.
test("card order is the same with and without replied", async (t) => {
  const plain = [mk("order-seen", 1, { added: at(5) }), mk("order-new", 2, { added: NEW_ADDED }), mk("order-sunk", 3, { added: at(6), reply: "Thanks, noted." })];
  const dated = plain.map((it) => ({ ...it, replied: REPLIED_AT }));
  const answers = answerOf(plain[2]);
  const before = await open(t, { items: plain, answers, storage: VISIT }); if (!before) return;
  const layoutBefore = await layout(before);
  assert.equal(layoutBefore.length, 3, "the page did not draw the three cards");
  const after = await open(t, { items: dated, answers, storage: VISIT }); if (!after) return;
  assert.deepEqual(await layout(after), layoutBefore, "a replied time moved a card");
});

// Case 7: after load, waiting.visit holds the load's time. The page's clock is fixed at LOAD_AT, so the time the page writes is
// LOAD_AT. The stored visit starts at VISIT_AT, earlier than LOAD_AT, so a page that writes nothing fails here.
test("after load, waiting.visit holds an ISO time no earlier than the load's start", async (t) => {
  const page = await open(t, { storage: VISIT, clock: LOAD_AT }); if (!page) return;
  const visit = await page.evaluate(() => localStorage.getItem("waiting.visit"));
  assert.match(visit ?? "", /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/, `waiting.visit is "${visit}", not an ISO time`);
  assert.ok(Date.parse(visit) >= Date.parse(LOAD_AT), `waiting.visit is "${visit}", earlier than the load's start ${LOAD_AT}`);
});

// Case 8: with storage kept, the first load marks the card and the step, and a reload after it marks neither. The first load's
// checks run first, so a page that marks nothing fails there, not at the reload.
test("a reload that keeps storage drops the first load's marks: the card and the step fold and close again", async (t) => {
  const it = repliedCard();
  const steps = stepsOf([["c1", "v2", 1, "active"], ["a2", "v2", 2, "todo"]]);
  steps.a2.updatedAt = REPLIED_AT;
  const page = await open(t, { pageHtml: phasePage(steps), items: [it], answers: answerOf(it, "a", { note: "Kept the red one." }), storage: VISIT, keepStorage: true, clock: LOAD_AT }); if (!page) return;
  const fold = card(page, it).locator("button.unfold");
  await need(fold, `No. ${it.n} has no fold control on the first load`);
  assert.equal(await fold.getAttribute("aria-expanded"), "true", "the first load does not open the reply card");
  assert.equal(await markName(page, it), NEW_MARK, `the first load draws no New reply mark on No. ${it.n}`);
  await openStatus(page);
  const row = page.locator('button[data-row="a2"]');
  await need(row, "the step a2 has no row in the phase list");
  assert.equal(await row.getAttribute("aria-expanded"), "true", "the first load does not open the updated step");
  // The reload runs the page's load again, with the visit the first load wrote (storage is kept, not reset).
  await page.reload();
  await page.waitForFunction("state.items.length > 0");
  await page.waitForSelector(`#item-${it.id}`);
  assert.equal(await markName(page, it), null, `after a reload No. ${it.n} still draws the New reply mark`);
  const again = card(page, it).locator("button.unfold");
  await need(again, `No. ${it.n} has no fold control after a reload`);
  assert.equal(await again.getAttribute("aria-expanded"), "false", "after a reload the reply card is open again");
  await openStatus(page);
  const rowAgain = page.locator('button[data-row="a2"]');
  await need(rowAgain, "the step a2 has no row after a reload");
  assert.equal(await rowAgain.getAttribute("aria-expanded"), "false", "after a reload the updated step is open again");
  assert.doesNotMatch(await rowAgain.getAttribute("aria-label"), /Updated since your last visit/, "after a reload the updated step still says Updated");
});

// ---------------------------------------------------------------- answered sink

// An answered item sinks to the Answered section: after the open tiers, before Arbiter rulings, folded to its answer line.
// Membership is frozen at load, so an answer sent on the page moves nothing until a reload. Each case leads with sectionOf(),
// which reads no tier id, so a page without the section fails on the placement and never on a crash.
const ANSWERED_AT = "2026-10-26T01:00:00Z";
// An open item added after ANSWERED_AT is new, not seen, so its parts stay unfolded.
const NEW_ADDED = at(28);
const answerOf = (it, choice = "a", over = {}) => ({ [it.id]: { item: it.id, n: it.n, at: ANSWERED_AT, choice, note: "", ...over } });
// The id of the section (section.tier) that holds the card, or null.
const sectionOf = (page, it) => page.evaluate((id) => { const el = document.getElementById("item-" + id); const s = el && el.closest("section.tier"); return s ? s.id : null; }, it.id);
// The ids of the cards under a selector, in page order. A selector that matches nothing gives [].
const cardsIn = (page, sel) => page.evaluate((s) => [...document.querySelectorAll(s + " article.card")].map((c) => c.id.slice(5)), sel);
const sectionIds = (page) => page.evaluate(() => [...document.querySelectorAll("#list > section.tier")].map((s) => s.id));
// Each card with the section that holds it, in page order. Equal before and after a push means nothing moved.
// lines: also the folded line of each item in place of its card (an article with id line-<n>), so a card that folds to a line keeps its place.
const layout = (page, lines = false) => page.evaluate((lines) => [...document.querySelectorAll(lines ? "article.card, article[id^='line-']" : "article.card")].map((c) => [c.closest("section.tier")?.id ?? null, c.id]), lines);
// The href of the rail row that a chip sits in, or null.
const railRowOf = (page, it) => page.evaluate((id) => { const c = document.getElementById("c-" + id); const row = c && c.closest(".ov-tier"); const a = row && row.querySelector("a.ov-head"); return a ? a.getAttribute("href") : null; }, it.id);

// ---------------------------------------------------------------- answered sink: arrivals on top, and a card sent on this visit
// The names start "answered-sink:", so `--test-name-pattern answered-sink:` runs this block. An arrival (an item not on the page at load)
// goes to the top of its tier under either SENT_MOVE value. Cards that are open at load keep today's order.
// The chip ids of a tier's rail row, in order; [] when the row is absent.
const railChipsIn = (page, k) => page.evaluate((key) => {
  const head = document.querySelector(`#rail a.ov-head[href="#tier-${key}"]`);
  const row = head && head.closest(".ov-tier");
  return row ? [...row.querySelectorAll(".chips-n .nchip")].map((c) => c.id.slice(2)) : [];
}, k);
// Resolves once the store holds an answer for each id.
const waitAnswered = (page, ids) => page.waitForFunction((list) => list.every((id) => !!window.__answers()[id]), ids);

// Case 1: three cards answered on this visit and one open card, all ranked at load. An item that arrives after load is first in its tier
// and first in its tier's rail row, under each value. Only the arrival's place is asserted: the order of the load-time cards is SENT_MOVE's to set.
for (const value of ["stay", "sink"]) {
  test(`answered-sink: an item that arrives after load is first in its tier and in its rail row, above the cards answered on this visit (SENT_MOVE ${value})`, async (t) => {
    const sent = [1, 2, 3].map((n) => mk("arr-sent-" + n, n, { added: at(n), rank: n }));
    const open1 = mk("arr-open", 4, { added: at(4), rank: 4 });
    const page = await open(t, { items: [...sent, open1], pageHtml: withSentMove(value) }); if (!page) return;
    for (const it of sent) await choose(page, it, "a");
    await send(page);
    await waitAnswered(page, sent.map((it) => it.id));
    const arrival = mk("arr-new", 9, { added: at(28) });
    await page.evaluate((it) => window.__putItem(it), arrival);
    await card(page, arrival).waitFor();
    assert.equal(await sectionOf(page, arrival), "tier-calm", `No. ${arrival.n} is not in the open tier`);
    assert.equal((await cardsIn(page, "#tier-calm"))[0], arrival.id, `No. ${arrival.n} is not first in its tier`);
    assert.equal((await railChipsIn(page, "calm"))[0], arrival.id, `No. ${arrival.n}'s rail chip is not first in its tier's row`);
  });
}

// Case 2, sink: a card sent on this visit moves to the Answered section, folded. The next open card takes its slot in the tier.
test("answered-sink: a card sent on this visit moves to the Answered section, folded, and the open cards keep their order (SENT_MOVE sink)", async (t) => {
  // The sent card is the newest, so it heads its tier; the next open card takes its slot. Newest first puts o1 above o2.
  const sent = mk("send-sink", 1, { added: at(3) }), o1 = mk("send-open-1", 2, { added: at(2) }), o2 = mk("send-open-2", 3, { added: at(1) });
  const page = await open(t, { items: [sent, o1, o2], pageHtml: withSentMove("sink") }); if (!page) return;
  // A note gives the sunk card a fold with something in it; a fold with nothing to hide would say something false.
  await choose(page, sent, "a");
  await addNote(page, sent, "Kept it.");
  await send(page);
  await waitAnswered(page, [sent.id]);
  await card(page, sent).locator(".receipt").waitFor();
  assert.equal(await sectionOf(page, sent), "tier-answered", `No. ${sent.n} did not move to the Answered section after its Send`);
  const fold = card(page, sent).locator("button.unfold");
  await need(fold, `No. ${sent.n} has no fold control in the Answered section`);
  assert.equal(await fold.getAttribute("aria-expanded"), "false", `No. ${sent.n} is not folded after its Send`);
  assert.deepEqual(await cardsIn(page, "#tier-calm"), [o1.id, o2.id], `the open cards of the tier do not hold their order above the sent card`);
  assert.deepEqual(await railChipsIn(page, "calm"), [o1.id, o2.id], "the open tier's rail chips do not follow its cards");
  assert.ok((await railChipsIn(page, "answered")).includes(sent.id), `No. ${sent.n}'s rail chip is not in the Answered row`);
});

// Case 2, stay: a card sent on this visit keeps its place in its tier, and so do its rail chips. This is today's order.
test("answered-sink: a card sent on this visit keeps its place in its tier, and its rail chips keep theirs (SENT_MOVE stay)", async (t) => {
  const sent = mk("send-stay", 1, { added: at(1) }), o1 = mk("send-stay-1", 2, { added: at(2) }), o2 = mk("send-stay-2", 3, { added: at(3) });
  const page = await open(t, { items: [sent, o1, o2], pageHtml: withSentMove("stay") }); if (!page) return;
  const before = await layout(page), chipsBefore = await railChipsIn(page, "calm");
  await choose(page, sent, "a");
  await send(page);
  await waitAnswered(page, [sent.id]);
  await card(page, sent).locator(".receipt").waitFor();
  assert.deepEqual(await layout(page), before, "a Send on the open page moved a card");
  assert.deepEqual(await railChipsIn(page, "calm"), chipsBefore, "a Send moved a rail chip");
});

// Change on a card sent this visit (SENT_MOVE sink): the card reopens in place, in the Answered section, as a Change on a sunk card does.
test("answered-sink: a Change on a card sent this visit reopens it in place in the Answered section, its fold locked open (SENT_MOVE sink)", async (t) => {
  const sent = mk("change-sent", 1, { added: at(1) }), o1 = mk("change-open", 2, { added: at(2) });
  const page = await open(t, { items: [sent, o1], pageHtml: withSentMove("sink") }); if (!page) return;
  await choose(page, sent, "a");
  await addNote(page, sent, "Kept it."); // a note gives the sunk card a fold, as in the case above
  await send(page);
  await waitAnswered(page, [sent.id]);
  await card(page, sent).locator(".receipt").waitFor();
  assert.equal(await sectionOf(page, sent), "tier-answered", `No. ${sent.n} did not move to the Answered section after its Send`);
  const answeredBefore = await cardsIn(page, "#tier-answered");
  const c = page.locator(`#tier-answered #item-${sent.id}`);
  await c.getByRole("button", { name: "Change" }).click();
  assert.equal(await sectionOf(page, sent), "tier-answered", `Change moved No. ${sent.n} out of the Answered section`);
  assert.deepEqual(await cardsIn(page, "#tier-answered"), answeredBefore, "Change moved a card within the Answered section");
  const fold = c.locator("button.unfold");
  await need(fold, `No. ${sent.n} has no fold control after Change`);
  assert.equal(await fold.getAttribute("aria-expanded"), "true", "Change left the fold closed");
  assert.equal(await fold.getAttribute("aria-disabled"), "true", "Change left the fold unlocked");
  assert.equal(await c.locator(".opts").isVisible(), true, "the options did not open under Change");
});

// Case 3: the arrival is first before a reload. After a reload with the same data it is in its normal rank and age place, and the cards
// saved before the load sit in the Answered section.
test("answered-sink: a reload with the same data puts the former arrival in its normal rank and age place, and the sunk cards in the Answered section", async (t) => {
  const sent = [1, 2].map((n) => mk("rl-sent-" + n, n, { added: at(n) }));
  const open1 = mk("rl-open", 3, { added: at(3), rank: 1 });
  const page = await open(t, { items: [...sent, open1] }); if (!page) return;
  for (const it of sent) await choose(page, it, "a");
  await send(page);
  await waitAnswered(page, sent.map((it) => it.id));
  const arrival = mk("rl-arrival", 9, { added: at(28) });
  await page.evaluate((it) => window.__putItem(it), arrival);
  await card(page, arrival).waitFor();
  assert.equal((await cardsIn(page, "#tier-calm"))[0], arrival.id, `No. ${arrival.n} is not first in its tier before the reload`);
  const again = await open(t, { items: [...sent, open1, arrival], answers: await answers(page) }); if (!again) return;
  for (const it of sent) assert.equal(await sectionOf(again, it), "tier-answered", `No. ${it.n}, saved before the load, is not in the Answered section`);
  assert.deepEqual(await cardsIn(again, "#tier-calm"), [open1.id, arrival.id], "after the reload the former arrival is not in its normal rank and age place");
});

// Case 4 (regression): a saved card with a lane sinks at load, folded, with its Filing pending pill and "waits on lane" said once.
// A sunk card with no note, last answer or reply has nothing to fold, so it draws no fold control.
test("answered-sink: a sunk card with no note, last answer or reply shows no fold control", async (t) => {
  const it = mk("bare-sunk", 1, { added: at(5) }), other = mk("bare-open", 2, { added: NEW_ADDED });
  const page = await open(t, { items: [it, other], answers: answerOf(it) }); if (!page) return;
  assert.equal(await sectionOf(page, it), "tier-answered", `No. ${it.n} is not in the Answered section`);
  assert.equal(await card(page, it).locator("button.unfold").count(), 0, `No. ${it.n} draws a fold control with nothing to hide`);
});

test("answered-sink: a saved card with a lane sinks at load, folded, with its Filing pending pill and its lane said once", async (t) => {
  const it = mk("lane-sunk", 1, { added: at(5), lane: "ci-done-comment" }), other = mk("lane-open", 2, { added: NEW_ADDED });
  const page = await open(t, { items: [it, other], answers: answerOf(it, "a", { note: "Kept the red one." }) }); if (!page) return;
  assert.equal(await sectionOf(page, it), "tier-answered", `No. ${it.n} is not in the Answered section`);
  const c = card(page, it), fold = c.locator("button.unfold");
  await need(fold, `No. ${it.n} has no fold control`);
  assert.equal(await fold.getAttribute("aria-expanded"), "false", `No. ${it.n} is not folded at load`);
  assert.match(flat(await c.locator(".top").innerText()), /Filing pending, sent .*waits on lane ci-done-comment$/, `No. ${it.n}'s top row is not Filing pending, sent, then the lane`);
  const said = (await c.textContent()).split("waits on lane").length - 1;
  assert.equal(said, 1, `No. ${it.n} says "waits on lane" ${said} times`);
});

// Case 5 (regression, #1345): a reply that arrives on a card sunk at load opens its fold in place. No card moves.
test("answered-sink: a reply that arrives on a card sunk at load opens its fold in place, and no card moves", async (t) => {
  const it = mk("live-reply", 1, { added: at(5) }), other = mk("live-open", 2, { added: NEW_ADDED });
  const page = await open(t, { items: [it, other], answers: answerOf(it, "a", { note: "Kept the red one." }), storage: VISIT }); if (!page) return;
  assert.equal(await sectionOf(page, it), "tier-answered", `No. ${it.n} is not in the Answered section`);
  const fold = card(page, it).locator("button.unfold");
  await need(fold, `No. ${it.n} has no fold control`);
  assert.equal(await fold.getAttribute("aria-expanded"), "false", `No. ${it.n} is open before any reply`);
  const before = await layout(page);
  await page.evaluate((item) => window.__putItem(item), { ...it, reply: "Thanks, noted.", replied: REPLIED_AT });
  await page.waitForFunction((id) => document.querySelector(`#item-${id} button.unfold`)?.getAttribute("aria-expanded") === "true", it.id).catch(() => {});
  assert.equal(await fold.getAttribute("aria-expanded"), "true", `a reply that arrived on the open page did not open No. ${it.n}`);
  assert.equal(await markName(page, it), NEW_MARK, `No. ${it.n} draws no New reply mark for its new reply`);
  assert.deepEqual(await layout(page), before, "the reply moved a card");
});

test("an answered item sinks to the Answered section, after the open tiers and before Arbiter rulings, folded to its answer line", async (t) => {
  const ans = mk("sink-ans", 1, { added: at(5) }), open1 = mk("sink-open", 2, { added: NEW_ADDED });
  const page = await open(t, { items: [ans, open1, ARBITER], answers: answerOf(ans, "a", { note: "Kept the red one." }) }); if (!page) return;
  assert.equal(await sectionOf(page, ans), "tier-answered", `No. ${ans.n} is not in the Answered section`);
  assert.deepEqual(await sectionIds(page), ["tier-calm", "tier-answered", "tier-ruled"], "the Answered section is not between the open tiers and Arbiter rulings");
  assert.deepEqual(await cardsIn(page, "#tier-calm"), [open1.id], "the open item left its tier, or the answered item stayed in it");
  const c = page.locator(`#tier-answered #item-${ans.id}`), fold = c.locator("button.unfold");
  assert.doesNotMatch(await c.getAttribute("class"), /\b(holds|due|calm|stands)\b/, "the answered card keeps its tier class");
  await need(fold, `No. ${ans.n} in the Answered section has no fold control`);
  assert.equal(await fold.getAttribute("aria-expanded"), "false", "the answered card is not folded on load");
  assert.equal(await c.locator(".rnote").isVisible(), false, "the note shows on the folded card");
  assert.match(await c.locator(".receipt").textContent(), /You chose A: Red/, "the answer line is missing from the folded card");
});

test("an answered item already filed shows one line in the Answered section, with its home", async (t) => {
  const filed = mk("filed-sunk", 1, { added: at(5) }), open1 = mk("filed-open", 2, { added: NEW_ADDED });
  const page = await open(t, { items: [open1, filed], answers: answerOf(filed), receipts: { [filed.id]: { read: "2026-10-26T02:00:00Z", filed: "2026-10-26T03:00:00Z" } } }); if (!page) return;
  assert.deepEqual(await cardsIn(page, "#tier-calm"), [open1.id], "the open item left its tier");
  await mustHave(page, `#tier-answered #line-${filed.n}`, `the one line of No. ${filed.n} in the Answered section`);
  const words = ((await page.locator(`#tier-answered #line-${filed.n}`).textContent()) || "").replace(/\s+/g, " ").trim();
  assert.ok(words.includes("c1"), `the line of No. ${filed.n} does not name its home c1: "${words}"`);
});

test("an open card answered on the page stays in its tier until reload, and a fresh load sinks it to the Answered section", async (t) => {
  const it = mk("order-send", 1, { added: at(5) }), other = mk("order-other", 2, { added: NEW_ADDED });
  const page = await open(t, { items: [it, other], pageHtml: withSentMove("stay") }); if (!page) return;
  await choose(page, it, "a");
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], it.id);
  await card(page, it).locator(".receipt").waitFor();
  assert.deepEqual(await cardsIn(page, "#tier-calm"), [other.id, it.id], "the card answered on the open page left its tier before reload");
  const again = await open(t, { items: [it, other], answers: await answers(page) }); if (!again) return;
  assert.equal(await sectionOf(again, it), "tier-answered", `No. ${it.n} is not in the Answered section after a reload`);
  assert.deepEqual(await cardsIn(again, "#tier-calm"), [other.id], "after a reload the open item is not alone in its tier");
});

test("in the Answered section, a receipt that arrives after load moves no card, and a read-only receipt leaves the answer unfiled", async (t) => {
  const filed = mk("late-filed", 1, { added: at(5) }), reads = mk("late-read", 2, { added: at(6) }), open1 = mk("late-open", 3, { added: NEW_ADDED });
  const page = await open(t, { items: [open1, filed, reads], answers: { ...answerOf(filed), ...answerOf(reads) } }); if (!page) return;
  assert.equal(await sectionOf(page, filed), "tier-answered", `No. ${filed.n} is not in the Answered section`);
  assert.equal(await sectionOf(page, reads), "tier-answered", `No. ${reads.n} is not in the Answered section`);
  const before = await layout(page);
  // The receipts arrive after the items and answers, through the page's own store handle.
  await page.evaluate(async ([a, b]) => { await state.db.collection("receipts").doc(a).set({ filed: "2026-10-26T03:00:00Z" }); await state.db.collection("receipts").doc(b).set({ read: "2026-10-26T02:00:00Z" }); }, [filed.id, reads.id]);
  await page.waitForFunction((id) => !!document.getElementById("c-" + id)?.classList.contains("filed"), filed.id);
  await page.waitForFunction((id) => !!document.querySelector(`#item-${id} .receipt .read`), reads.id);
  // The filed item is one line now, in place of its card. The other cards keep their places.
  await mustHave(page, `#tier-answered #line-${filed.n}`, `the one line of No. ${filed.n} in the Answered section, in place of its card`);
  // The filed card's place is the folded line's place: the same section, at the same index. The other cards keep theirs.
  assert.deepEqual(await layout(page, true), before.map(([sec, id]) => (id === "item-" + filed.id ? [sec, "line-" + filed.n] : [sec, id])), `a receipt that arrived after load moved a card, or moved the line of No. ${filed.n} out of its place`);
  const ro = page.locator(`#tier-answered #item-${reads.id}`);
  await need(ro.locator(".ans"), `No. ${reads.n} in the Answered section has no answer pill`);
  assert.equal(await ro.locator(".ans.filed").count(), 0, `a read-only receipt marks No. ${reads.n} filed`);
  assert.match((await ro.locator(".ans").textContent()).trim(), /^Filing pending, sent /, `No. ${reads.n} does not read filing pending`);
  assert.match(await ro.locator(".receipt .read").textContent(), /^Read by test thread /, "the read line is missing");
  assert.equal(await page.evaluate((id) => document.getElementById("c-" + id).classList.contains("filed"), reads.id), false, `the rail chip for No. ${reads.n} is marked filed`);
});

test("in the Answered section, a group sinks only when every member is answered; a half-answered group stays whole in its tier", async (t) => {
  const half = [mk("half-ans", 1, { group: "half", added: at(5) }), mk("half-open", 2, { group: "half", added: NEW_ADDED })];
  const all = [mk("all-a", 3, { group: "all", added: at(6) }), mk("all-b", 4, { group: "all", added: at(7) })];
  const page = await open(t, { items: [...half, ...all], answers: { ...answerOf(half[0]), ...answerOf(all[0]), ...answerOf(all[1]) } }); if (!page) return;
  assert.deepEqual(await cardsIn(page, "#tier-calm #group-half"), [half[1].id, half[0].id], "the half-answered group is not whole in its tier");
  assert.equal(await page.locator(`#tier-answered #item-${half[0].id}`).count(), 0, "the answered member of a half-answered group sank");
  assert.equal(await sectionOf(page, all[0]), "tier-answered", "the fully answered group is not in the Answered section");
  assert.deepEqual(await cardsIn(page, "#tier-answered #group-all"), all.map((x) => x.id), "the fully answered group did not sink whole, as one frame");
});

test("Change on a folded card in the Answered section keeps it there, open, with its fold locked open", async (t) => {
  const it = mk("change-sunk", 1, { added: at(5) }), other = mk("change-open", 2, { added: NEW_ADDED });
  const page = await open(t, { items: [it, other], answers: answerOf(it, "a", { note: "Kept it." }) }); if (!page) return;
  assert.equal(await sectionOf(page, it), "tier-answered", `No. ${it.n} is not in the Answered section`);
  const c = page.locator(`#tier-answered #item-${it.id}`);
  await c.getByRole("button", { name: "Change" }).click();
  assert.equal(await sectionOf(page, it), "tier-answered", "Change moved the card out of the Answered section");
  const fold = c.locator("button.unfold");
  await need(fold, `No. ${it.n} has no fold control after Change`);
  assert.equal(await fold.getAttribute("aria-expanded"), "true", "Change left the fold closed");
  assert.equal(await fold.getAttribute("aria-disabled"), "true", "Change left the fold unlocked");
  assert.equal(await c.locator(".opts").isVisible(), true, "the options did not open under Change");
  assert.equal(await page.isChecked(`#o-${it.id}-a`), true, "Change lost the saved pick");
});

test("the rail gives the Answered section its own row, takes answered items out of their tier row, and the counts agree with the section", async (t) => {
  const ans = mk("rail-ans", 1, { added: at(5) }), open1 = mk("rail-open", 2, { added: NEW_ADDED }), open2 = mk("rail-open2", 3, { added: NEW_ADDED });
  const page = await open(t, { items: [ans, open1, open2], answers: answerOf(ans) }); if (!page) return;
  const home = await railRowOf(page, ans);
  assert.equal(home, "#tier-answered", `the chip for No. ${ans.n} sits in the rail row ${home}, not the Answered row`);
  const row = page.locator('#rail a.ov-head[href="#tier-answered"]');
  await need(row, "the rail has no Answered row");
  const sectionCount = (await cardsIn(page, "#tier-answered")).length;
  assert.equal((await row.locator(".ct").textContent()).trim(), String(sectionCount), "the Answered row count is not the section's size");
  assert.equal((await page.locator('#rail a.ov-head[href="#tier-calm"] .ct').textContent()).trim(), "2", "the Whenever row does not count only the open items left in it");
  const rows = await page.evaluate(() => [...document.querySelectorAll("#rail a.ov-head")].map((a) => a.getAttribute("href")));
  assert.ok(rows.indexOf("#tier-answered") > rows.indexOf("#tier-calm"), `the Answered row is not after the tier rows: ${rows.join(" ")}`);
  // A page with no answered item draws no Answered section and no Answered row, as the rulings section draws only with rulings.
  const none = await open(t, { items: [mk("empty-open", 1, { added: at(5) })] }); if (!none) return;
  assert.equal(await none.locator("#tier-answered").count(), 0, "an empty Answered section is drawn");
  assert.equal(await none.locator('#rail a.ov-head[href="#tier-answered"]').count(), 0, "an empty Answered row is in the rail");
});

test("unfold in the Answered section shows what the fold holds, and a card with nothing to hide has no unfold control", async (t) => {
  const withNote = mk("fold-note", 1, { added: at(5), reply: "Thanks, noted." }), bare = mk("fold-none", 2, { added: at(6) });
  const page = await open(t, { items: [withNote, bare], answers: { ...answerOf(withNote, "a", { note: "Kept the red one." }), ...answerOf(bare) } }); if (!page) return;
  assert.equal(await sectionOf(page, withNote), "tier-answered", `No. ${withNote.n} is not in the Answered section`);
  assert.equal(await sectionOf(page, bare), "tier-answered", `No. ${bare.n} is not in the Answered section`);
  const c = page.locator(`#tier-answered #item-${withNote.id}`), fold = c.locator("button.unfold");
  await need(fold, `No. ${withNote.n} has a note and a reply but no unfold control`);
  assert.equal(await fold.getAttribute("aria-expanded"), "false", "the fold is open on load");
  assert.equal(await c.locator(".rnote").isVisible(), false, "the note shows before unfold");
  assert.equal(await c.locator(`#rp-${withNote.id}`).isVisible(), false, "the reply shows before unfold");
  const show = (await fold.locator(".uf-show").textContent()).trim();
  assert.match(show, /^Show your note\b.*\bthe reply$/, `the fold label reads "${show}"`);
  await fold.click();
  assert.equal(await fold.getAttribute("aria-expanded"), "true", "unfold did not open the fold");
  assert.equal(await c.locator(".rnote").isVisible(), true, "unfold did not show the note");
  assert.equal(await c.locator(`#rp-${withNote.id}`).isVisible(), true, "unfold did not show the reply");
  assert.equal(await page.locator(`#tier-answered #item-${bare.id} button.unfold`).count(), 0, "a card with nothing to hide has an unfold control");
});

// ---------------------------------------------------------------- answered sink: fold lock, rail chip, freeze gate, group title

test("Answered section: a sunk card whose saved answer has a restored draft keeps its fold unlocked, and the press opens it", async (t) => {
  const it = mk("draft-sunk", 1, { added: at(5) }), other = mk("draft-other", 2, { added: NEW_ADDED });
  const page = await open(t, { items: [it, other], answers: answerOf(it, "a", { note: "Kept it." }), storage: { "waiting.draft": JSON.stringify({ [it.id]: { choice: "b" } }) } }); if (!page) return;
  assert.equal(await sectionOf(page, it), "tier-answered", `No. ${it.n} is not in the Answered section`);
  const c = page.locator(`#tier-answered #item-${it.id}`), fold = c.locator("button.unfold");
  await need(fold, `No. ${it.n} has a note but no fold control`);
  // A saved answer never locks its fold: the draft is not the answer the owner saved, so a lock would leave a dead button.
  assert.notEqual(await fold.getAttribute("aria-disabled"), "true", `the fold of No. ${it.n} is locked by a draft its saved answer does not hold`);
  await fold.click();
  assert.equal(await fold.getAttribute("aria-expanded"), "true", `the fold of No. ${it.n} stays shut after the press`);
  assert.equal(await c.locator(".rnote").isVisible(), true, `the fold of No. ${it.n} reads open but its note is hidden`);
});

// A closed line is in the Answered section and in no card, so a rail count that reads only the answered items misses it. The
// section's own count holds it, so the rail's Answered row must match that count.
test("answered-rail: with only a closed line, the rail has an Answered row that counts it, as the section does", async (t) => {
  const open1 = mk("rail-closed-open", 1, { added: NEW_ADDED });
  const page = await open(t, { items: [open1], rawItems: { [AP_CLOSED.id]: AP_CLOSED }, clock: AP_NOW }); if (!page) return;
  await mustHave(page, `#rail #c-${open1.id}`, `the rail chip of the open No. ${open1.n}`);
  await mustHave(page, `#tier-answered #line-${AP_CLOSED.n}`, `the line of the closed No. ${AP_CLOSED.n} in the Answered section`);
  const railRow = page.locator('#rail a.ov-head[href="#tier-answered"]');
  await need(railRow, `the rail has no Answered row, but the Answered section holds No. ${AP_CLOSED.n}`);
  const section = (await page.locator("#tier-answered .rhead .ct").textContent()).trim();
  assert.equal((await railRow.locator(".ct").textContent()).trim(), section, "the rail's Answered count is not the section's count, closed lines included");
});

test("answered-rail: a closed line and an answered item both count in the rail's Answered row, as in the section", async (t) => {
  const ans = mk("rail-closed-ans", 1, { added: at(5) }), open1 = mk("rail-closed-open2", 2, { added: NEW_ADDED });
  const page = await open(t, { items: [ans, open1], answers: answerOf(ans), rawItems: { [AP_CLOSED.id]: AP_CLOSED }, clock: AP_NOW }); if (!page) return;
  await mustHave(page, `#rail #c-${open1.id}`, `the rail chip of the open No. ${open1.n}`);
  await mustHave(page, `#tier-answered #item-${ans.id}`, `the card of the answered No. ${ans.n} in the Answered section`);
  await mustHave(page, `#tier-answered #line-${AP_CLOSED.n}`, `the line of the closed No. ${AP_CLOSED.n} in the Answered section`);
  const railRow = page.locator('#rail a.ov-head[href="#tier-answered"]');
  await need(railRow, `the rail has no Answered row, but the Answered section holds two items`);
  const section = (await page.locator("#tier-answered .rhead .ct").textContent()).trim();
  assert.equal((await railRow.locator(".ct").textContent()).trim(), section, "the rail's Answered count is not the section's count, closed lines included");
});

test("Answered section: with the section folded by its head, a rail chip of a sunk item opens the section and brings the card into view", async (t) => {
  const it = mk("chip-sunk", 1, { added: at(5) });
  const filler = Array.from({ length: 6 }, (_, i) => mk("chip-open-" + i, 10 + i, { added: NEW_ADDED, context: LONG }));
  const page = await open(t, { items: [...filler, it], answers: answerOf(it), viewport: { width: 1280, height: 400 } }); if (!page) return;
  assert.equal(await sectionOf(page, it), "tier-answered", `No. ${it.n} is not in the Answered section`);
  const head = page.locator("#b-answered");
  await head.click();
  assert.equal(await head.getAttribute("aria-expanded"), "false", "the head did not fold the section, so the chip case cannot start");
  await page.locator(`#c-${it.id}`).click();
  assert.equal(await head.getAttribute("aria-expanded"), "true", `the rail chip for No. ${it.n} did not open the folded Answered section`);
  // A smooth scroll takes a moment; the wait ends when the card is in view, and the check below reads where it landed.
  await page.waitForFunction((id) => { const r = document.getElementById("item-" + id).getBoundingClientRect(); return r.top >= 0 && r.top < innerHeight; }, it.id).catch(() => {});
  const top = await page.evaluate((id) => document.getElementById("item-" + id).getBoundingClientRect().top, it.id);
  assert.ok(top >= 0 && top < 400, `the card for No. ${it.n} sits ${Math.round(top)}px from the top, outside the 400px view`);
});

test("Answered section: a Send made before the first receipts snapshot keeps its card in its tier when the receipts arrive", async (t) => {
  const it = mk("window-send", 1, { added: at(5) }), other = mk("window-other", 2, { added: NEW_ADDED });
  const page = await open(t, { items: [it, other], holdReceipts: true, pageHtml: withSentMove("stay") }); if (!page) return;
  await choose(page, it, "a");
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], it.id);
  await card(page, it).locator(".receipt").waitFor();
  await page.evaluate(() => window.__releaseReceipts());
  await page.waitForFunction(() => feed.receipts === true);
  assert.equal(await sectionOf(page, it), "tier-calm", `No. ${it.n}, answered before the receipts came, left its tier when they arrived`);
  assert.deepEqual(await cardsIn(page, "#tier-calm"), [other.id, it.id], "the open page re-sorted when the receipts arrived");
});

test("Answered section: a fully answered group's bundle head reads Answered together, not Answer these together", async (t) => {
  const all = [mk("bundle-a", 1, { group: "all", added: at(5) }), mk("bundle-b", 2, { group: "all", added: at(6) })];
  const page = await open(t, { items: [...all, mk("bundle-open", 3, { added: NEW_ADDED })], answers: { ...answerOf(all[0]), ...answerOf(all[1]) } }); if (!page) return;
  assert.equal(await sectionOf(page, all[0]), "tier-answered", `No. ${all[0].n} is not in the Answered section`);
  const head = page.locator("#tier-answered #group-all > header > b");
  await need(head, "the fully answered group has no bundle head in the Answered section");
  const words = (await head.textContent()).trim();
  assert.equal(words, "Answered together", `the bundle head reads "${words}"`);
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
// ---------------------------------------------------------------- the Ask box (step page-ask-box)
// Contract: docs/design/page-ask-box-notes.md on design/page-ask-box, sections 3, 5, 6 and 8.
// The notes name no ids, so the selectors take the mockup's: #askText (the box), #askSend, #askUndo.
const ASK_TEXT = "Can the waiting page take a question from me?";
const ASK_ANSWERED = { id: "ask-an1", text: "Can I see the lane queue?", at: "2026-10-30T09:00:00Z", owner: "triage", answered: "2026-10-30T10:00:00Z", reply: "Yes. It is on the Status tab." };
// A missing control fails by name, not by a wait that times out.
async function mustHave(page, sel, what) {
  const n = await page.locator(sel).first().waitFor({ state: "attached", timeout: 3000 }).then(() => 1, () => 0);
  assert.equal(n, 1, `no ${what}: ${sel} is missing`);
}
// A text the page shows, as its box. A text the page does not show fails with the text named.
// scope: a selector the text must sit under, such as DIS_SHOWN. A Dismissed line keeps the thread's text in its .dt span, so a check that means the thread is shown passes a scope.
async function shownBox(page, text, scope = "") {
  const loc = (scope ? page.locator(scope) : page).getByText(text, { exact: typeof text === "string" }).first();
  const shown = await loc.waitFor({ state: "visible", timeout: 3000 }).then(() => true, () => false);
  assert.ok(shown, `the page does not show: ${text}`);
  return loc.boundingBox();
}

// The stack under the box, from the design (docs/design/page-ask-queue-notes.md): Add to list is #askAdd, Undo is #askUndo,
// Send stays #askSend, the list is ol.stack under the heading "Not sent yet", and the line under the buttons is .sline.
// A row's buttons are found by the names the design gives them: "Edit ask N", "Remove ask N", "Done", "Undo remove".
const ASK = { box: "#askText", add: "#askAdd", send: "#askSend", undo: "#askUndo", rows: "ol.stack > li", words: "ol.stack > li .stext", ask: "li.askc" };
const stackWords = (page) => page.locator(ASK.words).allInnerTexts();
const askWrites = (page) => page.evaluate(() => window.__log.filter((l) => l[0] === "set" && l[1] === "asks").map((l) => l[3]));
// Each waits, up to 1.5 s, for the store to hold n writes or deletes. The caller asserts the count, so a wait that gives up fails by name.
const waitAskWrites = (page, n) => page.waitForFunction((k) => window.__log.filter((l) => l[0] === "set" && l[1] === "asks").length >= k, n, { timeout: 1500 }).catch(() => {});
const waitAskDeletes = (page, n) => page.waitForFunction((k) => window.__log.filter((l) => l[0] === "delete" && l[1] === "asks").length >= k, n, { timeout: 1500 }).catch(() => {});
// Whether the line under the buttons holds the words, once it shows them or at 3 s. Never throws, so a missing line fails by name.
const lineHas = (page, words) => page.waitForFunction((w) => { const l = document.querySelector("#asks .sline"); return !!l && l.textContent.includes(w); }, words, { timeout: 3000 }).then(() => true, () => false);
// A button found by its accessible name. A missing one fails by name, as mustHave does.
async function mustHaveNamed(scope, name, what) {
  const n = await scope.getByRole("button", { name, exact: true }).first().waitFor({ state: "attached", timeout: 3000 }).then(() => 1, () => 0);
  assert.equal(n, 1, `no ${what}: no button named "${name}"`);
}
// Types an ask and presses Add to list: the words leave the box and wait in the list, and nothing is written.
async function addToList(page, text) {
  await mustHave(page, ASK.box, "Ask box");
  await page.fill(ASK.box, text);
  await mustHave(page, ASK.add, "Add to list button");
  await page.click(ASK.add);
}
// Types an ask and presses Send, then waits for its write. The button must be on, so a press that cannot go fails by name.
async function sendTyped(page, text) {
  await mustHave(page, ASK.box, "Ask box");
  await page.fill(ASK.box, text);
  await mustHave(page, ASK.send, "Send ask button");
  assert.equal(await page.locator(ASK.send).isDisabled(), false, `Send ask is off with "${text}" typed`);
  const before = (await askWrites(page)).length;
  await page.click(ASK.send);
  await waitAskWrites(page, before + 1);
}

test("Send ask writes asks/<id> with only the id, the text and the time", async (t) => {
  const page = await open(t); if (!page) return;
  await mustHave(page, "#askText", "Ask box");
  await page.fill("#askText", ASK_TEXT);
  await mustHave(page, "#askSend", "Send ask button");
  await page.click("#askSend");
  await page.waitForFunction(() => window.__log.some((l) => l[0] === "set" && l[1] === "asks"));
  const log = await page.evaluate(() => window.__log);
  const asks = log.filter((l) => l[0] === "set" && l[1] === "asks");
  assert.equal(asks.length, 1, "Send wrote " + asks.length + " asks records");
  const [, , key, body] = asks[0];
  assert.match(key, /^ask-[0-9a-z]+$/, "the key is not ask-<id>: " + key);
  assert.deepEqual(Object.keys(body).sort(), ["at", "id", "text"], "the record holds " + Object.keys(body).join(", "));
  assert.equal(body.id, key, "the id field is not the key");
  assert.equal(body.text, ASK_TEXT, "the text is not the owner's words");
  assert.match(body.at, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/, "at is not an ISO time: " + body.at);
  assert.deepEqual(log.filter((l) => l[0] === "set" && l[1] !== "asks"), [], "Send wrote another collection");
});

test("Undo deletes asks/<id> and puts the ask back in the list, and the box keeps what was typed", async (t) => {
  const page = await open(t); if (!page) return;
  await mustHave(page, "#askText", "Ask box");
  await page.fill("#askText", ASK_TEXT);
  await mustHave(page, "#askSend", "Send ask button");
  await page.click("#askSend");
  await page.waitForFunction(() => window.__log.some((l) => l[0] === "set" && l[1] === "asks"));
  const key = await page.evaluate(() => window.__log.find((l) => l[0] === "set" && l[1] === "asks")[2]);
  await mustHave(page, "#askUndo", "Undo control");
  await page.click("#askUndo");
  await page.waitForFunction(() => window.__log.some((l) => l[0] === "delete" && l[1] === "asks"));
  const dels = await page.evaluate(() => window.__log.filter((l) => l[0] === "delete" && l[1] === "asks").map((l) => l[2]));
  assert.deepEqual(dels, [key], "Undo deleted " + JSON.stringify(dels) + ", not " + key);
  // Undo puts the ask back in the list; the box is the owner's and Undo never writes it.
  assert.equal(await page.inputValue("#askText"), "", "Undo put the text back in the box, not the list: " + JSON.stringify(await page.inputValue("#askText")));
  assert.deepEqual(await stackWords(page), [ASK_TEXT], "Undo did not put the ask back in the list");
});

test("the asks list is newest first by at, whatever order the records came in", async (t) => {
  // Insertion order and id order both differ from newest first, so only a sort by at passes.
  const asks = {
    "ask-zz1": { id: "ask-zz1", text: "Middle ask text", at: "2026-10-30T09:00:00Z" },
    "ask-aa1": { id: "ask-aa1", text: "Newest ask text", at: "2026-10-31T09:00:00Z" },
    "ask-mm1": { id: "ask-mm1", text: "Oldest ask text", at: "2026-10-29T09:00:00Z" },
  };
  const page = await open(t, { dbExtra: { asks } }); if (!page) return;
  const top = {};
  for (const text of ["Newest ask text", "Middle ask text", "Oldest ask text"]) top[text] = (await shownBox(page, text)).y;
  assert.ok(top["Newest ask text"] < top["Middle ask text"] && top["Middle ask text"] < top["Oldest ask text"], "the asks are not newest first: " + JSON.stringify(top));
});

test("a seen answer folds to one button row, and Show answer opens its reply", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [ASK_ANSWERED.id]: ASK_ANSWERED } }, storage: { "waiting.askSeen": "2026-10-31T00:00:00Z" } }); if (!page) return;
  await shownBox(page, ASK_ANSWERED.text);
  assert.equal(await page.getByText(ASK_ANSWERED.reply, { exact: true }).isVisible(), false, "a seen answer is open");
  const show = page.getByRole("button", { name: "Show answer" });
  assert.equal(await show.count(), 1, "no Show answer control on the folded ask");
  await show.click();
  await shownBox(page, ASK_ANSWERED.reply);
});

test("an answer the viewer has not seen stays open, with the New answer mark", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [ASK_ANSWERED.id]: ASK_ANSWERED } }, storage: { "waiting.askSeen": "2026-10-29T00:00:00Z" } }); if (!page) return;
  await shownBox(page, ASK_ANSWERED.reply);
  await shownBox(page, "New answer");
});

test("a waiting ask says who has not read it, or who read it and is working on it", async (t) => {
  const asks = {
    "ask-w01": { id: "ask-w01", text: "Nobody has read this yet", at: "2026-10-31T08:00:00Z" },
    "ask-w02": { id: "ask-w02", text: "The writer has read this", at: "2026-10-31T07:00:00Z", owner: "triage", read: "2026-10-31T07:30:00Z" },
  };
  const page = await open(t, { dbExtra: { asks } }); if (!page) return;
  await shownBox(page, "Waiting for triage to read it.");
  await shownBox(page, /^Read by triage/);
  await shownBox(page, /Waiting for its answer\./);
  assert.equal(await page.getByText("Waiting for triage to read it.", { exact: true }).count(), 1, "the read ask also says it waits to be read");
});

// Red cases for the Ask box: no stray null, the cap on new answers, the 4000-character limit, Ctrl+Enter, paste and Copy ask.
test("the Ask section never shows the text null, in the waiting, answered and sent states", async (t) => {
  const asks = {
    "ask-n-wait": { id: "ask-n-wait", text: "A question still waiting", at: "2026-10-31T08:00:00Z" },
    "ask-n-fresh": { id: "ask-n-fresh", text: "A fresh answer", at: "2026-10-30T08:00:00Z", owner: "triage", answered: "2026-10-31T10:00:00Z", reply: "Yes, it does." },
    "ask-n-seen": { id: "ask-n-seen", text: "A seen answer", at: "2026-10-29T08:00:00Z", owner: "triage", answered: "2026-10-30T10:00:00Z", reply: "Yes, it did." },
  };
  const page = await open(t, { dbExtra: { asks }, storage: { "waiting.askSeen": "2026-10-30T11:00:00Z" } }); if (!page) return;
  await shownBox(page, "A question still waiting");
  const stray = () => page.evaluate(() => { const s = document.getElementById("asks").textContent, i = s.indexOf("null"); return i < 0 ? "" : s.slice(Math.max(0, i - 60), i + 10); });
  const waiting = await stray();
  assert.equal(waiting, "", "the waiting and answered states show the text null: " + JSON.stringify(waiting));
  await page.fill("#askText", "A new ask for the list");
  await mustHave(page, "#askSend", "Send ask button");
  await page.click("#askSend");
  await page.waitForFunction(() => window.__log.some((l) => l[0] === "set" && l[1] === "asks"));
  assert.ok(await lineHas(page, "Sent"), "the sent state shows no line under the buttons");
  const sent = await stray();
  assert.equal(sent, "", "the sent state shows the text null: " + JSON.stringify(sent));
});

test("a new answer to an ask older than the newest 3 answered asks stays open in view, not behind Show older asks", async (t) => {
  // Three answers seen at the last visit fill the cap. The new answer is older by at, so it sits fourth in the list.
  const seen = (n, at) => ({ id: "ask-s" + n, text: "Seen answer " + n, at, owner: "triage", answered: "2026-10-30T10:00:00Z", reply: "Seen reply " + n + "." });
  const asks = {
    "ask-s1": seen(1, "2026-10-30T08:00:00Z"),
    "ask-s2": seen(2, "2026-10-30T07:00:00Z"),
    "ask-s3": seen(3, "2026-10-30T06:00:00Z"),
    "ask-new": { id: "ask-new", text: "Old ask, new answer", at: "2026-10-01T09:00:00Z", owner: "triage", answered: "2026-10-31T08:00:00Z", reply: "The answer that came after the last visit." },
    "ask-old": { id: "ask-old", text: "Oldest seen answer", at: "2026-09-15T09:00:00Z", owner: "triage", answered: "2026-10-02T08:00:00Z", reply: "Seen long ago." },
  };
  const page = await open(t, { dbExtra: { asks }, storage: { "waiting.askSeen": "2026-10-31T00:00:00Z" } }); if (!page) return;
  await shownBox(page, "The answer that came after the last visit.");
  // Only the seen answer past the cap stays behind the button.
  assert.equal(await page.getByRole("button", { name: "Show 1 older ask", exact: true }).count(), 1, "the button does not say Show 1 older ask");
});

// The Ask seen stamp is written only while the Ask section is on screen, so the owner has seen the asks. On a hidden tab an answer
// that arrives would otherwise count as seen at the next load.
const TAB_SEED = "2026-10-31T00:00:00Z", TAB_HIDE = "2026-10-31T06:00:00Z", TAB_HIDE_STAMP = "2026-10-31T06:00:00.000Z", TAB_CLOSE_STAMP = "2026-10-31T09:00:00.000Z";
const TAB_ARRIVED_AT = "2026-10-31T08:00:00Z", TAB_CLOSE = "2026-10-31T09:00:00Z";
const TAB_SHORT = { width: 1280, height: 400 };
const TAB_ASKS = () => ({
  "ask-s1": { id: "ask-s1", text: "Seen answer 1", at: "2026-10-30T08:00:00Z", owner: "triage", answered: "2026-10-30T10:00:00Z", reply: "Seen reply 1." },
  "ask-s2": { id: "ask-s2", text: "Seen answer 2", at: "2026-10-30T07:00:00Z", owner: "triage", answered: "2026-10-30T10:00:00Z", reply: "Seen reply 2." },
  "ask-s3": { id: "ask-s3", text: "Seen answer 3", at: "2026-10-30T06:00:00Z", owner: "triage", answered: "2026-10-30T10:00:00Z", reply: "Seen reply 3." },
  "ask-old": { id: "ask-old", text: "Oldest seen answer", at: "2026-09-15T09:00:00Z", owner: "triage", answered: "2026-10-02T08:00:00Z", reply: "Seen long ago." },
});
const TAB_ARRIVED = { id: "ask-arrived", text: "Asked before the tab hid", at: "2026-10-01T09:00:00Z", owner: "triage", answered: TAB_ARRIVED_AT, reply: "The answer that arrived while the tab was hidden." };
// On screen: the section overlaps the viewport.
const asksOnScreen = (page) => page.evaluate(() => { const r = document.getElementById("asks").getBoundingClientRect(); return r.bottom > 0 && r.top < window.innerHeight; });
// On screen: the answers list (#askList) overlaps the viewport. The Ask seen stamp is measured on this list, not on the section.
const listOnScreen = (page) => page.evaluate(() => { const r = document.getElementById("askList").getBoundingClientRect(); return r.bottom > 0 && r.top < window.innerHeight; });
// A tab hides as a browser hides it: document.hidden turns true, then visibilitychange fires.
const hideTab = (page) => page.evaluate(() => { Object.defineProperty(document, "hidden", { value: true, configurable: true }); document.dispatchEvent(new Event("visibilitychange")); });
const seenStamp = (page) => page.evaluate(() => localStorage.getItem("waiting.askSeen"));
const tabOpen = (t) => open(t, { dbExtra: { asks: TAB_ASKS() }, storage: { "waiting.askSeen": TAB_SEED }, keepStorage: true, clock: TAB_HIDE, viewport: TAB_SHORT });

test("the Ask seen stamp does not move on a hidden tab while the Ask section is off screen: visibilitychange", async (t) => {
  const page = await tabOpen(t); if (!page) return;
  assert.equal(await asksOnScreen(page), false, "the Ask section is on screen at load, so this case cannot show a hidden tab's stamp");
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_SEED, "hiding the tab with the Ask section off screen moved the Ask seen stamp");
});
test("the Ask seen stamp does not move when the page closes while the Ask section is off screen: pagehide", async (t) => {
  const page = await tabOpen(t); if (!page) return;
  assert.equal(await asksOnScreen(page), false, "the Ask section is on screen at load, so this case cannot show a closing page's stamp");
  await page.evaluate(() => window.dispatchEvent(new Event("pagehide")));
  assert.equal(await seenStamp(page), TAB_SEED, "the page closing with the Ask section off screen moved the Ask seen stamp");
});
test("an answer that arrives while the tab is hidden is new at the next load, not behind Show older asks", async (t) => {
  const page = await tabOpen(t); if (!page) return;
  assert.equal(await asksOnScreen(page), false, "the Ask section is on screen at load, so the answer cannot arrive on a hidden tab");
  await hideTab(page);
  // The answer lands in the store while the tab is hidden. The close that follows comes after it.
  await page.evaluate((asks) => localStorage.setItem("__stub.asks", JSON.stringify(asks)), { ...TAB_ASKS(), [TAB_ARRIVED.id]: TAB_ARRIVED });
  await page.clock.setFixedTime(new Date(TAB_CLOSE));
  await page.reload();
  await shownBox(page, "Seen answer 1");
  assert.equal(await page.locator(`#row-${TAB_ARRIVED.id} .newmark`).count(), 1, "the answer that arrived while the tab was hidden has no New answer mark at the next load");
});
test("the Ask seen stamp moves when the tab hides while the Ask section is on screen", async (t) => {
  const page = await tabOpen(t); if (!page) return;
  await page.locator("#asks").scrollIntoViewIfNeeded();
  await page.waitForFunction(() => { const r = document.getElementById("askList").getBoundingClientRect(); return r.bottom > 0 && r.top < window.innerHeight; });
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_HIDE_STAMP, "hiding the tab with the Ask section on screen did not stamp the asks as seen");
});
// pagehide is the second path that stamps: a page closing on a visible tab with the answers list on screen stamps it too.
test("the Ask seen stamp moves when the page closes while the Ask section is on screen: pagehide", async (t) => {
  const page = await tabOpen(t); if (!page) return;
  await page.locator("#asks").scrollIntoViewIfNeeded();
  assert.equal(await listOnScreen(page), true, "the answers list is off screen after the Ask section is scrolled into view, so this case cannot show a closing page's stamp");
  assert.equal(await page.evaluate(() => document.hidden), false, "the tab reads as hidden, so this case cannot show a visible page closing");
  assert.equal(await seenStamp(page), TAB_SEED, "scrolling the Ask section into view moved the Ask seen stamp");
  await page.clock.setFixedTime(new Date(TAB_CLOSE));
  await page.evaluate(() => window.dispatchEvent(new Event("pagehide")));
  assert.equal(await seenStamp(page), TAB_CLOSE_STAMP, "the page closing with the Ask section on screen did not stamp the asks as seen");
});
test("the Ask seen stamp stays at the hide time when the page closes on a hidden tab after an answer lands: pagehide", async (t) => {
  // The Ask section is below the fold at load. The owner scrolls it into view, as the on-screen case above does, so the hide stamps it.
  const page = await open(t, { dbExtra: { asks: TAB_ASKS() }, storage: { "waiting.askSeen": TAB_SEED }, keepStorage: true, clock: TAB_HIDE }); if (!page) return;
  await page.locator("#asks").scrollIntoViewIfNeeded();
  assert.equal(await listOnScreen(page), true, "the answers list is off screen after the Ask section is scrolled into view, so this case cannot show a hidden tab's stamp");
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_HIDE_STAMP, "hiding the tab with the Ask section on screen did not stamp the asks as seen");
  // An answer lands in the store while the tab is still hidden. The page then closes, later, still hidden, with the Ask section laid out where it was.
  await page.evaluate((asks) => localStorage.setItem("__stub.asks", JSON.stringify(asks)), { ...TAB_ASKS(), [TAB_ARRIVED.id]: TAB_ARRIVED });
  await page.clock.setFixedTime(new Date(TAB_CLOSE));
  await page.evaluate(() => window.dispatchEvent(new Event("pagehide")));
  assert.equal(await seenStamp(page), TAB_HIDE_STAMP, "the page closing on a hidden tab moved the Ask seen stamp to the close time, past an answer that arrived while the tab was hidden");
  await page.reload();
  await shownBox(page, "Seen answer 1");
  assert.equal(await page.locator(`#row-${TAB_ARRIVED.id} .newmark`).count(), 1, "the answer that arrived while the tab was hidden has no New answer mark at the next load");
});

// An answer the owner has not seen, listed below the fold: answered after the seen stamp and before the tab hides.
const BELOW_ASK = { id: "ask-below", text: "An answer listed below the fold", at: "2026-10-31T03:00:00Z", owner: "triage", answered: "2026-10-31T04:00:00Z", reply: "It is below the fold." };
// A phone height. At this height the answers list starts below the fold when the section's top sits 300 px down.
const PHONE_SHORT = { width: 390, height: 700 };
const scrollTopTo = (page, sel, px) => page.evaluate(([s, p]) => window.scrollTo(0, document.querySelector(s).getBoundingClientRect().top + scrollY - p), [sel, px]);

test("an answer listed below the fold is not seen when the tab hides, so its New answer mark survives the next load", async (t) => {
  const page = await open(t, { dbExtra: { asks: { ...TAB_ASKS(), [BELOW_ASK.id]: BELOW_ASK } }, storage: { "waiting.askSeen": TAB_SEED }, keepStorage: true, clock: TAB_HIDE, viewport: PHONE_SHORT }); if (!page) return;
  await scrollTopTo(page, "#asks", 300);
  assert.equal(await asksOnScreen(page), true, "the Ask section is off screen, so this case cannot show a hidden tab's stamp");
  assert.equal(await listOnScreen(page), false, "the answers list is on screen, so this case cannot show an answer below the fold");
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_SEED, "hiding the tab with the answers list below the fold moved the Ask seen stamp");
  await page.clock.setFixedTime(new Date(TAB_CLOSE));
  await page.reload();
  await shownBox(page, "Seen answer 1");
  assert.equal(await page.locator(`#row-${BELOW_ASK.id} .newmark`).count(), 1, "the answer below the fold has no New answer mark at the next load");
});
test("the Ask seen stamp moves when the tab hides with the answers list on screen, at a phone height", async (t) => {
  const page = await open(t, { dbExtra: { asks: { ...TAB_ASKS(), [BELOW_ASK.id]: BELOW_ASK } }, storage: { "waiting.askSeen": TAB_SEED }, keepStorage: true, clock: TAB_HIDE, viewport: PHONE_SHORT }); if (!page) return;
  await scrollTopTo(page, "#askList", 300);
  assert.equal(await listOnScreen(page), true, "the answers list is off screen, so this case cannot show a hidden tab's stamp");
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_HIDE_STAMP, "hiding the tab with the answers list on screen did not stamp the asks as seen");
});

// A tab hides with the answers list on screen, then the page is restored from the back-forward cache and is visible again. The restore
// sends visibilitychange only when visibilityEvent is true. The browser's own event order on a restore is unmeasured: this models both paths.
const TAB_LATER = "2026-10-31T07:00:00Z", TAB_LATER_STAMP = "2026-10-31T07:00:00.000Z";
// The shared start of the restore cases: the tab hides with the answers list on screen, and the page goes into the back-forward cache.
async function hiddenAndCached(t) {
  const page = await tabOpen(t); if (!page) return null;
  await page.locator("#asks").scrollIntoViewIfNeeded();
  assert.equal(await listOnScreen(page), true, "the answers list is off screen at the first hide, so this case cannot show a hide that stamps");
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_HIDE_STAMP, "the first hide with the answers list on screen did not stamp, so this case cannot show the later switch");
  await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent("pagehide", { persisted: true })));
  return page;
}
async function hideThenRestore(t, visibilityEvent) {
  const page = await hiddenAndCached(t); if (!page) return null;
  await page.evaluate((sendEvent) => {
    Object.defineProperty(document, "hidden", { value: false, configurable: true });
    window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
    if (sendEvent) document.dispatchEvent(new Event("visibilitychange"));
  }, visibilityEvent);
  assert.equal(await page.evaluate(() => document.hidden), false, "the restored page reads as hidden, so this case cannot show a later switch");
  assert.equal(await listOnScreen(page), true, "the answers list is off screen after the restore, so this case cannot show a later switch");
  await page.clock.setFixedTime(new Date(TAB_LATER));
  return page;
}
test("the Ask seen stamp moves on the tab switch after a bfcache restore, with no visibilitychange on the restore", async (t) => {
  const page = await hideThenRestore(t, false); if (!page) return;
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_LATER_STAMP, "the tab switch after a bfcache restore did not stamp the asks as seen");
});
test("the Ask seen stamp moves on the tab switch after a bfcache restore that sends visibilitychange: control", async (t) => {
  const page = await hideThenRestore(t, true); if (!page) return;
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_LATER_STAMP, "the tab switch after a bfcache restore with visibilitychange did not stamp the asks as seen");
});

// The answers list shows a placeholder while the store has not answered, or cannot be read. The placeholder is inside #askList, so the
// stamp must not count it as the asks the owner has seen.
test("the Ask seen stamp does not move when the tab hides while the asks load: the Loading placeholder", async (t) => {
  const page = await open(t, { dbExtra: { asks: TAB_ASKS() }, storage: { "waiting.askSeen": TAB_SEED }, keepStorage: true, clock: TAB_HIDE, viewport: TAB_SHORT, holdAsks: true }); if (!page) return;
  await page.locator("#asks").scrollIntoViewIfNeeded();
  assert.match(await page.textContent("#askList"), /Loading your asks/, "the answers list does not read Loading, so this case cannot show a hide while the asks load");
  assert.equal(await listOnScreen(page), true, "the answers list is off screen, so this case cannot show a hide that stamps");
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_SEED, "hiding the tab while the asks load moved the Ask seen stamp: no answer was listed, and the stamp counts it as seen");
});
test("the Ask seen stamp does not move when the tab hides while the asks cannot be read: the placeholder", async (t) => {
  const page = await open(t, { noStore: true, storage: { "waiting.askSeen": TAB_SEED }, keepStorage: true, clock: TAB_HIDE, viewport: TAB_SHORT }); if (!page) return;
  await page.locator("#asks").scrollIntoViewIfNeeded();
  assert.match(await page.textContent("#askList"), /cannot be read/, "the answers list does not read cannot-be-read, so this case cannot show a hide with no asks to read");
  assert.equal(await listOnScreen(page), true, "the answers list is off screen, so this case cannot show a hide that stamps");
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_SEED, "hiding the tab while the asks cannot be read moved the Ask seen stamp: no answer was listed, and the stamp counts it as seen");
});
test("the Ask seen stamp moves when the tab hides with rows shown after the asks load: control", async (t) => {
  const page = await open(t, { dbExtra: { asks: TAB_ASKS() }, storage: { "waiting.askSeen": TAB_SEED }, keepStorage: true, clock: TAB_HIDE, viewport: TAB_SHORT, holdAsks: true }); if (!page) return;
  await page.evaluate(() => window.__releaseAsks());
  await shownBox(page, "Seen answer 1");
  await page.locator("#asks").scrollIntoViewIfNeeded();
  assert.equal(await listOnScreen(page), true, "the answers list is off screen, so this case cannot show a hide that stamps");
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_HIDE_STAMP, "hiding the tab with rows shown did not stamp the asks as seen");
});

// A fresh answer on an older thread sorts below the newer threads, so it can sit under the fold while the list still overlaps the viewport.
const FRESH_OLD = { id: "ask-fresh-old", text: "Old ask, answered after the seen mark", at: "2026-10-01T09:00:00Z", owner: "triage", answered: "2026-10-31T04:00:00Z", reply: "The answer that came after the seen mark, on an older thread." };
const rowOnScreen = (page, id) => page.evaluate((k) => { const r = document.getElementById("row-" + k).getBoundingClientRect(); return r.bottom > 0 && r.top < window.innerHeight; }, id);
test("a fresh answer below the fold keeps its New answer mark when the answers list only overlaps the fold", async (t) => {
  const page = await open(t, { dbExtra: { asks: { ...TAB_ASKS(), [FRESH_OLD.id]: FRESH_OLD } }, storage: { "waiting.askSeen": TAB_SEED }, keepStorage: true, clock: TAB_HIDE, viewport: TAB_SHORT }); if (!page) return;
  await scrollTopTo(page, "#askList", TAB_SHORT.height - 40);
  assert.equal(await listOnScreen(page), true, "the answers list is off screen, so this case cannot show an overlap with the fold");
  assert.equal(await page.locator(`#row-${FRESH_OLD.id}`).count(), 1, "the fresh answer is not listed, so this case cannot show it below the fold");
  assert.equal(await rowOnScreen(page, FRESH_OLD.id), false, "the fresh answer is in view, so this case cannot show an answer below the fold");
  await hideTab(page);
  await page.clock.setFixedTime(new Date(TAB_CLOSE));
  await page.reload();
  await shownBox(page, "Seen answer 1");
  assert.equal(await page.locator(`#row-${FRESH_OLD.id} .newmark`).count(), 1, "the fresh answer below the fold lost its New answer mark: the hide stamped it as seen");
});
test("the Ask seen stamp moves when the tab hides with a fresh answer in view: control", async (t) => {
  const page = await open(t, { dbExtra: { asks: { ...TAB_ASKS(), [FRESH_OLD.id]: FRESH_OLD } }, storage: { "waiting.askSeen": TAB_SEED }, keepStorage: true, clock: TAB_HIDE, viewport: TAB_SHORT }); if (!page) return;
  await page.locator(`#row-${FRESH_OLD.id}`).scrollIntoViewIfNeeded();
  assert.equal(await rowOnScreen(page, FRESH_OLD.id), true, "the fresh answer is not in view, so this case cannot show a hide that stamps");
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_HIDE_STAMP, "hiding the tab with a fresh answer in view did not stamp the asks as seen");
});

// A newer answer to a row the owner has already seen. Its data-new key is new, so it is unseen: the row's earlier key does not carry over.
// The answers list still overlaps the fold, with the row below it, so the hide must not stamp past the newer answer.
test("a newer answer to a row already seen, listed below the fold, does not move the Ask seen stamp when the tab hides", async (t) => {
  const page = await open(t, { dbExtra: { asks: { ...TAB_ASKS(), [FRESH_OLD.id]: FRESH_OLD } }, storage: { "waiting.askSeen": TAB_SEED }, keepStorage: true, clock: TAB_HIDE, viewport: TAB_SHORT }); if (!page) return;
  await page.locator(`#row-${FRESH_OLD.id}`).scrollIntoViewIfNeeded();
  assert.equal(await rowOnScreen(page, FRESH_OLD.id), true, "the row is not in view, so the owner has not seen it");
  await page.waitForFunction((k) => [...askSeenNew].some((s) => s.startsWith(k)), FRESH_OLD.id);
  await scrollTopTo(page, "#askList", TAB_SHORT.height - 40);
  assert.equal(await listOnScreen(page), true, "the answers list is off screen, so this case cannot show a hide that stamps");
  assert.equal(await rowOnScreen(page, FRESH_OLD.id), false, "the row is in view, so this case cannot show a newer answer below the fold");
  // A newer answer to the same row lands while the tab is still visible. Its time is before the hide.
  const NEWER = { ...FRESH_OLD, reply: "Answer 2 on the same older thread.", answered: "2026-10-31T05:00:00Z" };
  await page.evaluate((a) => window.__putDoc("asks", a.id, a), NEWER);
  await page.waitForFunction((k) => /Answer 2 on the same older thread/.test(document.getElementById("row-" + k).textContent), FRESH_OLD.id);
  assert.equal(await listOnScreen(page), true, "the newer answer moved the answers list off screen, so this case cannot show a hide that stamps");
  assert.equal(await rowOnScreen(page, FRESH_OLD.id), false, "the newer answer brought the row into view, so this case cannot show an answer below the fold");
  assert.equal(await page.locator(`#row-${FRESH_OLD.id} .newmark`).count(), 1, "the newer answer has no New answer mark, so it is not a new answer");
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_SEED, "hiding the tab with a newer answer below the fold moved the Ask seen stamp past it");
  await page.evaluate((asks) => localStorage.setItem("__stub.asks", JSON.stringify(asks)), { ...TAB_ASKS(), [FRESH_OLD.id]: NEWER });
  await page.clock.setFixedTime(new Date(TAB_CLOSE));
  await page.reload();
  await shownBox(page, "Seen answer 1");
  assert.equal(await page.locator(`#row-${FRESH_OLD.id} .newmark`).count(), 1, "the newer answer lost its New answer mark at the next load: the hide stamped it as seen");
});

// A New answer row the owner saw, then scrolled above the fold while the answers list stays on screen. The row was read, so the hide stamps.
// NARROW is a 300 px wide screen.
const SEEN_ROW = { id: "ask-seen-row", text: "New row the owner scrolls past", at: "2026-10-30T12:00:00Z", owner: "triage", answered: "2026-10-31T03:00:00Z", reply: "The reply the owner reads." };
const NARROW = { width: 300, height: 400 };
const seenRowOpen = (t) => open(t, { dbExtra: { asks: { ...TAB_ASKS(), [SEEN_ROW.id]: SEEN_ROW } }, storage: { "waiting.askSeen": TAB_SEED }, keepStorage: true, clock: TAB_HIDE, viewport: NARROW });
test("a New answer row the owner saw, then scrolled above the fold, still stamps the asks as seen on the hide", async (t) => {
  const page = await seenRowOpen(t); if (!page) return;
  await page.locator("#asks").scrollIntoViewIfNeeded();
  await page.locator("#row-" + SEEN_ROW.id).scrollIntoViewIfNeeded();
  assert.equal(await page.locator(`#row-${SEEN_ROW.id} .newmark`).count(), 1, "the row has no New answer mark, so this case cannot show a New row scrolled away");
  assert.equal(await rowOnScreen(page, SEEN_ROW.id), true, "the New row is not in view before the owner scrolls past it, so this case cannot show a row seen and then scrolled away");
  await page.evaluate((k) => window.scrollBy(0, document.getElementById("row-" + k).getBoundingClientRect().bottom + 30), SEEN_ROW.id);
  assert.equal(await rowOnScreen(page, SEEN_ROW.id), false, "the New row is still in view after the scroll, so this case cannot show a row above the fold");
  assert.equal(await listOnScreen(page), true, "the answers list is off screen after the scroll, so this case cannot show a hide with the list on screen");
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_HIDE_STAMP, "the owner saw the New answer row and scrolled past it, and the hide did not stamp the asks as seen");
});
test("the Ask seen stamp moves when the tab hides with the New answer row in view, 300 px wide: control", async (t) => {
  const page = await seenRowOpen(t); if (!page) return;
  await page.locator("#row-" + SEEN_ROW.id).scrollIntoViewIfNeeded();
  assert.equal(await rowOnScreen(page, SEEN_ROW.id), true, "the New row is not in view, so this case cannot show a hide that stamps");
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_HIDE_STAMP, "hiding the tab with the New answer row in view did not stamp the asks as seen");
});

// A reply in a folded thread is answered after the seen mark. Its answer shows as a folded reply row (.fwait), which carries no New answer
// mark, so the stamp check does not see it. Below the fold it has not been read, so the hide must not stamp past it.
const FOLD_ROOT = { id: "ask-fold-root", text: "Folded thread root", at: "2026-09-20T09:00:00Z", owner: "triage", answered: "2026-10-02T08:00:00Z", reply: "Folded root reply." };
const FOLD_REPLY = { id: "ask-fold-reply", text: "Follow-up in the folded thread", at: "2026-10-20T09:00:00Z", re: FOLD_ROOT.id };
const FOLD_REPLY_ANSWERED = { ...FOLD_REPLY, reply: "Follow-up answer.", answered: "2026-10-31T05:00:00Z" };
const foldNoticeOnScreen = (page, k) => page.evaluate((id) => { const r = document.querySelector("#row-" + id + " .fwait").getBoundingClientRect(); return r.bottom > 0 && r.top < window.innerHeight; }, k);
test("a folded thread's fresh reply answer below the fold does not move the Ask seen stamp, and its notice shows at the next load", async (t) => {
  const page = await open(t, { dbExtra: { asks: { ...TAB_ASKS(), [FOLD_ROOT.id]: FOLD_ROOT, [FOLD_REPLY.id]: FOLD_REPLY } }, storage: { "waiting.askSeen": TAB_SEED }, keepStorage: true, clock: TAB_HIDE, viewport: TAB_SHORT }); if (!page) return;
  assert.equal(await page.locator(`#row-${FOLD_ROOT.id}.folded`).count(), 1, "the thread is not folded at load, so this case cannot show a folded reply's answer");
  await page.evaluate((a) => window.__putDoc("asks", a.id, a), FOLD_REPLY_ANSWERED);
  await page.waitForFunction((s) => /Answer from/.test(document.querySelector(s) ? document.querySelector(s).textContent : ""), `#row-${FOLD_ROOT.id} .fwait`);
  await page.evaluate((k) => window.scrollBy(0, document.querySelector("#row-" + k + " .fwait").getBoundingClientRect().top - innerHeight - 10), FOLD_ROOT.id);
  assert.equal(await listOnScreen(page), true, "the answers list is off screen, so this case cannot show a hide that stamps");
  assert.equal(await foldNoticeOnScreen(page, FOLD_ROOT.id), false, "the folded reply's answer is in view, so this case cannot show an answer below the fold");
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_SEED, "hiding the tab with a folded reply's answer below the fold moved the Ask seen stamp past it");
  await page.evaluate((asks) => localStorage.setItem("__stub.asks", JSON.stringify(asks)), { ...TAB_ASKS(), [FOLD_ROOT.id]: FOLD_ROOT, [FOLD_REPLY.id]: FOLD_REPLY_ANSWERED });
  await page.clock.setFixedTime(new Date(TAB_CLOSE));
  await page.reload();
  await shownBox(page, "Seen answer 1");
  assert.equal(await page.locator(`#row-${FOLD_ROOT.id} .newmark`).count(), 1, "the folded reply's answer has no New answer mark at the next load: the hide stamped it as seen");
});

// The control for the refusal above: a folded reply's fresh answer in view at the hide does move the stamp, so the refusal is not a stamp that never moves.
test("the Ask seen stamp moves when the tab hides with a folded thread's fresh reply answer in view: control", async (t) => {
  const page = await open(t, { dbExtra: { asks: { ...TAB_ASKS(), [FOLD_ROOT.id]: FOLD_ROOT, [FOLD_REPLY.id]: FOLD_REPLY } }, storage: { "waiting.askSeen": TAB_SEED }, keepStorage: true, clock: TAB_HIDE, viewport: TAB_SHORT }); if (!page) return;
  assert.equal(await page.locator(`#row-${FOLD_ROOT.id}.folded`).count(), 1, "the thread is not folded at load, so this case cannot show a folded reply's answer");
  await page.evaluate((a) => window.__putDoc("asks", a.id, a), FOLD_REPLY_ANSWERED);
  await page.waitForFunction((s) => /Answer from/.test(document.querySelector(s) ? document.querySelector(s).textContent : ""), `#row-${FOLD_ROOT.id} .fwait`);
  await page.locator(`#row-${FOLD_ROOT.id} .fwait`).scrollIntoViewIfNeeded();
  assert.equal(await foldNoticeOnScreen(page, FOLD_ROOT.id), true, "the folded reply's answer is not in view, so this case cannot show a hide that stamps");
  assert.equal(await listOnScreen(page), true, "the answers list is off screen, so this case cannot show a hide that stamps");
  await hideTab(page);
  assert.equal(await seenStamp(page), TAB_HIDE_STAMP, "hiding the tab with a folded reply's answer in view did not stamp the asks as seen");
});

// The restore's pageshow is still queued when the tab hides. The page's record of visibility is the one from before the restore, so the
// hide must still stamp.
test("the Ask seen stamp moves on a tab hide that runs before the queued pageshow after a bfcache restore", async (t) => {
  const page = await hiddenAndCached(t); if (!page) return;
  await page.clock.setFixedTime(new Date(TAB_LATER));
  await page.evaluate(() => Object.defineProperty(document, "hidden", { value: false, configurable: true }));
  assert.equal(await page.evaluate(() => document.hidden), false, "the restored page reads as hidden, so this case cannot show a hide after a restore");
  assert.equal(await listOnScreen(page), true, "the answers list is off screen after the restore, so this case cannot show a hide that stamps");
  // The hide runs, then the queued pageshow is delivered.
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", { value: true, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
    window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
  });
  assert.equal(await seenStamp(page), TAB_LATER_STAMP, "the hide that ran before the queued pageshow did not stamp the asks as seen");
});

test("Send ask never cuts a text over 4000 characters: it stores the full text, or writes nothing and shows a notice", async (t) => {
  const page = await open(t); if (!page) return;
  await mustHave(page, "#askText", "Ask box");
  await page.fill("#askText", ASK_TEXT);
  const short = await page.textContent("#askHint");
  const long = "0123456789".repeat(420); // 4200 characters
  // A value set in script is not held to the box's maxlength, as a draft or an Undo can leave it.
  await page.evaluate((v) => { const b = document.getElementById("askText"); b.value = v; b.dispatchEvent(new Event("input", { bubbles: true })); }, long);
  await mustHave(page, "#askSend", "Send ask button");
  if (await page.locator("#askSend").isDisabled()) {
    // Over the limit Send ask is off, so nothing is written, the words stay in the box, and the hint gives the limit.
    const off = await page.evaluate(() => window.__log.filter((l) => l[0] === "set" && l[1] === "asks").length);
    assert.equal(off, 0, "Send ask wrote " + off + " asks records while it was off");
    assert.equal(await page.inputValue("#askText"), long, "the words in the box changed while Send ask was off");
    const notice = (await page.textContent("#askHint")).trim();
    assert.ok(notice && notice !== short.trim() && /4000|limit/i.test(notice) && await page.locator("#askHint").isVisible(), "no limit notice in the hint: " + JSON.stringify(notice));
    return;
  }
  await page.click("#askSend");
  await page.waitForFunction(() => window.__log.some((l) => l[0] === "set" && l[1] === "asks"), null, { timeout: 1500 }).catch(() => {});
  const sets = await page.evaluate(() => window.__log.filter((l) => l[0] === "set" && l[1] === "asks").map((l) => l[3]));
  if (sets.length) {
    assert.equal(sets.length, 1, "Send wrote " + sets.length + " asks records");
    assert.equal(sets[0].text.length, long.length, `Send ask stored ${sets[0].text.length} of ${long.length} characters, with no notice`);
    assert.equal(sets[0].text, long, "the stored text is not the owner's words");
    return;
  }
  // No write: the words stay in the box, and the hint row says why.
  assert.equal(await page.inputValue("#askText"), long, "Send ask wrote nothing and dropped the typed words");
  const hint = (await page.textContent("#askHint")).trim();
  assert.ok(hint && hint !== short.trim() && await page.locator("#askHint").isVisible(), "Send ask wrote nothing and showed no notice");
});

test("Undo after more typing in the 8-second window keeps the typed words in the box and puts the whole ask back in the list", async (t) => {
  const page = await open(t); if (!page) return;
  const sent = "0123456789".repeat(395); // 3950 characters: under the limit, so Send takes it whole
  await mustHave(page, "#askText", "Ask box");
  await page.fill("#askText", sent);
  await mustHave(page, "#askSend", "Send ask button");
  await page.click("#askSend");
  await page.waitForFunction(() => window.__log.some((l) => l[0] === "set" && l[1] === "asks"));
  await mustHave(page, "#askUndo", "Undo control");
  const typed = "Typed after the send. ".repeat(6); // 126 characters, typed inside the window
  await page.fill("#askText", typed);
  await page.click("#askUndo");
  await page.waitForFunction(() => window.__log.some((l) => l[0] === "delete" && l[1] === "asks"));
  // Undo never writes the box, so the typed words stay as typed, and the whole 3950-character ask is back in the list.
  assert.equal(await page.inputValue("#askText"), typed, "Undo changed the typed words in the box");
  const back = await stackWords(page);
  assert.deepEqual(back.map((w) => w.length), [sent.length], `Undo put back ${JSON.stringify(back.map((w) => w.length))} characters in the list, not ${sent.length}`);
});

test("Ctrl+Enter with focus on Send ask writes no answer while an answer is staged", async (t) => {
  const page = await open(t, { items: [DECISION] }); if (!page) return;
  await card(page, DECISION).locator(".title").click();
  await page.keyboard.press("b");
  await page.fill("#askText", ASK_TEXT);
  await mustHave(page, "#askSend", "Send ask button");
  assert.equal(await page.locator("#send").isDisabled(), false, "no answer is staged, so the case proves nothing");
  await page.focus("#askSend");
  await page.keyboard.press("Control+Enter");
  await page.waitForFunction(() => window.__log.some((l) => l[0] === "set" && l[1] === "answers"), null, { timeout: 1500 }).catch(() => {});
  const writes = await page.evaluate(() => window.__log.filter((l) => l[0] === "set" && l[1] === "answers").length);
  assert.equal(writes, 0, "Ctrl+Enter on Send ask wrote " + writes + " answers record(s)");
});

test("pasting 4200 characters into the ask box keeps all of them and shows the over-limit notice", async (t) => {
  const page = await open(t); if (!page) return;
  await mustHave(page, "#askText", "Ask box");
  await page.fill("#askText", ASK_TEXT);
  const short = (await page.textContent("#askHint")).trim();
  const long = "0123456789".repeat(420); // 4200 characters
  // insertText takes the same route as a paste, so the box's maxlength applies to it as it does to a paste.
  await page.fill("#askText", "");
  await page.click("#askText");
  await page.keyboard.insertText(long);
  const value = await page.inputValue("#askText");
  assert.equal(value.length, long.length, `the box holds ${value.length} of ${long.length} pasted characters`);
  const hint = (await page.textContent("#askHint")).trim();
  const shown = await page.locator("#askHint").isVisible();
  assert.ok(shown && hint !== short && /4000|limit/i.test(hint), "no over-limit notice in the hint: " + JSON.stringify(hint));
});

test("over the limit, Send ask is disabled, or a press changes the hint to the notice", async (t) => {
  const page = await open(t); if (!page) return;
  await mustHave(page, "#askText", "Ask box");
  await mustHave(page, "#askSend", "Send ask button");
  const over = "0123456789".repeat(420); // 4200 characters, set as a draft or an Undo can leave it
  await page.evaluate((v) => { const b = document.getElementById("askText"); b.value = v; b.dispatchEvent(new Event("input", { bubbles: true })); }, over);
  if (!(await page.locator("#askSend").isDisabled())) {
    const before = (await page.textContent("#askHint")).trim();
    await page.click("#askSend");
    await page.waitForFunction((b) => document.getElementById("askHint").textContent.trim() !== b || window.__log.some((l) => l[0] === "set" && l[1] === "asks"), before, { timeout: 1500 }).catch(() => {});
    const after = (await page.textContent("#askHint")).trim();
    assert.notEqual(after, before, "Send ask is enabled over the limit, and a press leaves the hint as it was");
  }
  const writes = await page.evaluate(() => window.__log.filter((l) => l[0] === "set" && l[1] === "asks").length);
  assert.equal(writes, 0, "Send ask wrote an ask over the limit");
});

test("Copy ask after a failed write changes the hint to the copy result", async (t) => {
  const page = await open(t, { failSet: true }); if (!page) return;
  await mustHave(page, "#askText", "Ask box");
  await page.fill("#askText", ASK_TEXT);
  await mustHave(page, "#askSend", "Send ask button");
  await page.click("#askSend");
  assert.ok(await lineHas(page, "Not saved"), "the not-saved words are not on the line under the buttons");
  await page.evaluate(() => { Object.defineProperty(navigator, "clipboard", { value: { writeText: async (s) => { window.__copied = s; } } }); });
  await mustHave(page, "#askCopy", "Copy ask button");
  await page.click("#askCopy");
  await page.waitForFunction(() => /Copied\. Paste it in chat\.|Select and copy the text in the box\./.test(document.getElementById("askHint").textContent), null, { timeout: 1500 }).catch(() => {});
  const hint = (await page.textContent("#askHint")).trim();
  assert.match(hint, /Copied\. Paste it in chat\.|Select and copy the text in the box\./, "after Copy ask the hint still says: " + JSON.stringify(hint));
});

// ---------------------------------------------------------------- reply to an answered ask (step ask-reply-back)
// Contract: docs/design/ask-reply-back-notes.md, sections 1-8; the mockup is docs/design/ask-reply-back.html.
// A reply is one new asks/<id> record {id, text, at, re}, sent through the Ask box's path: one Undo lock, one wake comment.
// Per thread, keyed by the root ask id <k>: #reply-<k> (Reply), form #rf-<k>, textarea #rt-<k>, hint #rh-<k>,
// Close #rx-<k>, Send reply #rs-<k>, Copy reply #rc-<k>. The thread's line is .sline in .replyend; its Undo is #askUndo.
const RPL_ROOT = ASK_ANSWERED.id;
const RPL_TEXT = "Did round 3 change the rail guard?";
// ASK_ANSWERED is answered after RPL_NEW, so it opens as a new answer. Every answer is before RPL_SEEN, so each one folds.
const RPL_NEW = { "waiting.askSeen": "2026-10-29T00:00:00Z" };
const RPL_SEEN = { "waiting.askSeen": "2026-10-31T00:00:00Z" };
// RPL_SEEN_AP is after AP_ASK's answer, so that answer folds. RPL_SEEN is before it, so it reads the answer as new.
const RPL_SEEN_AP = { "waiting.askSeen": "2026-11-10T19:00:00Z" };
const RPL_ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/;
// An answer a session gave to a reply: a reply to it names this record in re, not the root ask.
const RPL_DEEP = { id: "ask-rpl-deep", text: "Is the rail guard still unchanged?", at: "2026-10-31T08:00:00Z", re: RPL_ROOT, owner: "lane tier-fold", answered: "2026-10-31T09:00:00Z", reply: "No. The rail guard is unchanged." };
const rplKeys = (page) => page.evaluate(() => window.__log.filter((l) => l[0] === "set" && l[1] === "asks").map((l) => l[2]));
const rplLast = async (page) => (await rplKeys(page)).at(-1);
// Whether the page sends a wake comment with these words, once it has or at 3 s. Never throws, so a missing comment fails by name.
const wakeHas = (page, words) => page.waitForFunction((w) => window.__sent.some((s) => String(s.text).includes(w)), words, { timeout: 3000 }).then(() => true, () => false);
// Whether the line under the reply's thread holds the words, once it shows them or at 3 s. Never throws.
const rplLineHas = (page, words) => page.waitForFunction((w) => { const l = document.querySelector(".replyend .sline"); return !!l && l.textContent.includes(w); }, words, { timeout: 3000 }).then(() => true, () => false);
// Presses Reply on the answered ask and waits for its box. A Reply that is not there fails by name.
async function openReply(page, root) {
  await mustHave(page, `#reply-${root}`, "Reply control on the answered ask");
  await page.click(`#reply-${root}`);
  await mustHave(page, `#rt-${root}`, "reply box");
}
// Presses Send reply in the open box, then waits for its write. The button must be on, so a press that cannot go fails by name.
async function sendReply(page, root) {
  await mustHave(page, `#rs-${root}`, "Send reply button");
  assert.equal(await page.locator(`#rs-${root}`).isDisabled(), false, "Send reply is off with the reply typed");
  const before = (await askWrites(page)).length;
  await page.click(`#rs-${root}`);
  await waitAskWrites(page, before + 1);
}
async function replyTo(page, root, text) {
  await openReply(page, root);
  await page.fill(`#rt-${root}`, text);
  await sendReply(page, root);
}

test("reply to an answer: Reply shows only on an unfolded answered ask, not on a waiting ask or a folded row", async (t) => {
  const seen = { id: "ask-rpl-seen", text: "A seen answer", at: "2026-10-27T09:00:00Z", owner: "triage", answered: "2026-10-27T10:00:00Z", reply: "A seen reply." };
  const waiting = { id: "ask-rpl-wait", text: "A question still waiting", at: "2026-10-31T08:00:00Z" };
  const page = await open(t, { dbExtra: { asks: { [RPL_ROOT]: ASK_ANSWERED, [seen.id]: seen, [waiting.id]: waiting } }, storage: RPL_NEW }); if (!page) return;
  // Each card is on the page before its Reply is looked for, so an absent Reply is a missing one.
  await shownBox(page, ASK_ANSWERED.reply);
  await mustHave(page, `#reply-${RPL_ROOT}`, "Reply on the unfolded answered ask");
  assert.equal(await page.getAttribute(`#reply-${RPL_ROOT}`, "aria-controls"), `rf-${RPL_ROOT}`, "Reply does not control its reply box");
  const atEnd = await page.locator(`#reply-${RPL_ROOT}`).evaluate((b) => { const li = b.closest("li.askc"), end = b.closest(".replyend"), th = li && li.querySelector(".thread"); return !!end && !!th && !!(th.compareDocumentPosition(end) & Node.DOCUMENT_POSITION_FOLLOWING); });
  assert.equal(atEnd, true, "Reply is not at the end of its thread, after .thread");
  await shownBox(page, waiting.text);
  assert.equal(await page.locator(`#reply-${waiting.id}`).count(), 0, "Reply shows on a waiting ask");
  await shownBox(page, seen.text);
  await mustHave(page, `button.frow[data-ask="${seen.id}"]`, "folded row of the seen answer");
  assert.equal(await page.locator(`#reply-${seen.id}`).count(), 0, "Reply shows on a folded row");
  await page.click(`button.frow[data-ask="${seen.id}"]`);
  await mustHave(page, `#reply-${seen.id}`, "Reply after Show answer on the seen answer");
});

test("reply to an answer: Send reply writes one asks record {id, text, at, re} and nothing else, and the parent is never written", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [RPL_ROOT]: ASK_ANSWERED } }, storage: RPL_NEW }); if (!page) return;
  await replyTo(page, RPL_ROOT, RPL_TEXT);
  const log = await page.evaluate(() => window.__log);
  const writes = log.filter((l) => l[0] === "set" || l[0] === "delete");
  assert.deepEqual(writes.map((l) => [l[0], l[1]]), [["set", "asks"]], "Send reply made these writes: " + JSON.stringify(writes.map((l) => [l[0], l[1]])));
  const [, , key, body] = writes[0];
  assert.match(key, /^ask-[0-9a-z]+$/, "the key is not ask-<id>: " + key);
  assert.deepEqual(Object.keys(body).sort(), ["at", "id", "re", "text"], "the record holds " + Object.keys(body).join(", "));
  assert.equal(body.id, key, "the id field is not the key");
  assert.equal(body.text, RPL_TEXT, "the text is not the owner's words");
  assert.equal(body.re, RPL_ROOT, "re is " + JSON.stringify(body.re) + ", not the ask the reply follows");
  assert.match(body.at, RPL_ISO, "at is not an ISO time: " + body.at);
  assert.equal(log.some((l) => l[2] === RPL_ROOT), false, "the parent record was written or deleted");
});

test("reply to an answer: a reply to a reply's answer names that newest answered record in re, not the root ask", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [RPL_ROOT]: ASK_ANSWERED, [RPL_DEEP.id]: RPL_DEEP } }, storage: RPL_NEW }); if (!page) return;
  await replyTo(page, RPL_ROOT, "A second question about the rail guard.");
  const body = (await askWrites(page))[0];
  assert.equal(body.re, RPL_DEEP.id, "re is " + JSON.stringify(body.re) + ", not the newest answered record " + RPL_DEEP.id);
});

test("reply to an answer: the wake comment names the reply's id, the re id and the parent's owner, in the notes' words", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [RPL_ROOT]: ASK_ANSWERED } }, storage: RPL_NEW }); if (!page) return;
  await replyTo(page, RPL_ROOT, RPL_TEXT);
  const key = await rplLast(page);
  const words = `Replied on the waiting page. Writer: triage. Ask ${key} re ${RPL_ROOT}, answered by triage: ${RPL_TEXT}`;
  assert.equal(await wakeHas(page, words), true, "no wake comment with the words " + JSON.stringify(words) + "; sent: " + JSON.stringify((await sent(page)).map((s) => s.text)));
});

test("reply to an answer: the wake comment of a reply to a reply's answer names that answer's owner, so the writer routes to it", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [RPL_ROOT]: ASK_ANSWERED, [RPL_DEEP.id]: RPL_DEEP } }, storage: RPL_NEW }); if (!page) return;
  const text = "A second question about the rail guard.";
  await replyTo(page, RPL_ROOT, text);
  const key = await rplLast(page);
  const words = `Replied on the waiting page. Writer: triage. Ask ${key} re ${RPL_DEEP.id}, answered by lane tier-fold: ${text}`;
  assert.equal(await wakeHas(page, words), true, "no wake comment with the words " + JSON.stringify(words) + "; sent: " + JSON.stringify((await sent(page)).map((s) => s.text)));
});

test("reply to an answer: Undo within 8 s deletes only the reply's record, never the parent, and the words go back in the reply box", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [RPL_ROOT]: ASK_ANSWERED } }, storage: RPL_NEW }); if (!page) return;
  await replyTo(page, RPL_ROOT, RPL_TEXT);
  const key = await rplLast(page);
  await mustHave(page, "#askUndo", "Undo control on the reply's line");
  await page.click("#askUndo");
  await waitAskDeletes(page, 1);
  const dels = await page.evaluate(() => window.__log.filter((l) => l[0] === "delete").map((l) => [l[1], l[2]]));
  assert.deepEqual(dels, [["asks", key]], "Undo deleted " + JSON.stringify(dels) + ", not only the reply " + key);
  await mustHave(page, `#rt-${RPL_ROOT}`, "reply box after Undo");
  assert.equal(await page.inputValue(`#rt-${RPL_ROOT}`), RPL_TEXT, "Undo did not put the words back in the reply box");
  assert.equal(await rplLineHas(page, "Undone. Your reply is back in the box, not sent."), true, "the reply's line does not say it was undone");
  assert.equal(await wakeHas(page, `Undone on the waiting page. Ask ${key} is withdrawn.`), true, "no withdrawn wake for the reply " + key);
});

test("reply to an answer: a reply's Undo count holds Send ask off, with the hint that says so", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [RPL_ROOT]: ASK_ANSWERED } }, storage: RPL_NEW }); if (!page) return;
  await replyTo(page, RPL_ROOT, RPL_TEXT);
  await mustHave(page, ASK.box, "Ask box");
  await page.fill(ASK.box, ASK_TEXT);
  await mustHave(page, ASK.send, "Send ask button");
  assert.equal(await page.locator(ASK.send).isDisabled(), true, "Send ask is on while the reply's Undo count runs");
  assert.match((await page.textContent("#askHint")) ?? "", /Send turns on when the Undo count ends\./, "the Ask box does not say why Send ask is off");
});

test("reply to an answer: an ask's Undo count holds Send reply off, with the reply's hint that says so", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [RPL_ROOT]: ASK_ANSWERED } }, storage: RPL_NEW }); if (!page) return;
  await sendTyped(page, ASK_TEXT);
  await openReply(page, RPL_ROOT);
  await page.fill(`#rt-${RPL_ROOT}`, RPL_TEXT);
  await mustHave(page, `#rs-${RPL_ROOT}`, "Send reply button");
  assert.equal(await page.locator(`#rs-${RPL_ROOT}`).isDisabled(), true, "Send reply is on while the ask's Undo count runs");
  assert.match((await page.textContent(`#rh-${RPL_ROOT}`)) ?? "", /Send reply turns on when the Undo count ends\./, "the reply box does not say why Send reply is off");
});

test("reply to an answer: a waiting reply counts in the Ask count and the rail, shows under its folded parent, and is never behind Show older asks", async (t) => {
  const parent = { id: "ask-rpl-old", text: "An old question, answered long ago", at: "2026-10-20T09:00:00Z", owner: "triage", answered: "2026-10-21T10:00:00Z", reply: "The old answer." };
  const mine = { id: "ask-rpl-mine", text: "My reply under the old answer", at: "2026-10-31T08:00:00Z", re: parent.id };
  // Three newer answers fill the three shown, so the old thread is the fourth: older than all of them.
  const newer = [
    { id: "ask-rpl-n1", text: "A newer answer 1", at: "2026-10-27T09:00:00Z", owner: "triage", answered: "2026-10-27T10:00:00Z", reply: "A newer reply 1." },
    { id: "ask-rpl-n2", text: "A newer answer 2", at: "2026-10-26T09:00:00Z", owner: "triage", answered: "2026-10-26T10:00:00Z", reply: "A newer reply 2." },
    { id: "ask-rpl-n3", text: "A newer answer 3", at: "2026-10-25T09:00:00Z", owner: "triage", answered: "2026-10-25T10:00:00Z", reply: "A newer reply 3." },
  ];
  const asks = Object.fromEntries([parent, mine, ...newer].map((a) => [a.id, a]));
  const page = await open(t, { dbExtra: { asks }, storage: RPL_SEEN }); if (!page) return;
  assert.equal((await page.textContent("#askCount")).trim(), "1", "the Ask count does not count the waiting reply");
  assert.equal((await page.textContent('a.ov-head[href="#asks"] .ct')).trim(), "1", "the rail's Ask count does not count the waiting reply");
  assert.equal(await page.locator(`button.frow[data-ask="${parent.id}"]`).count(), 1, "the old answer's thread is not on the page: it sits behind Show older asks");
  assert.equal(await page.locator("#askOlder").count(), 0, "a Show older asks button still hides the thread with a waiting reply");
  const fwait = page.locator(`li.askc.folded:has(button.frow[data-ask="${parent.id}"]) p.fwait`);
  assert.equal(await fwait.count(), 1, "the waiting reply does not show under its folded parent");
  const line = (await fwait.textContent()) ?? "";
  assert.ok(line.includes("Your reply: " + mine.text) && line.includes("Waiting for triage to read it."), "the line under the parent says: " + JSON.stringify(line));
  assert.equal(await page.locator("#askList li.askc:not(.folded)", { hasText: mine.text }).count(), 0, "the waiting reply shows as its own row, not only under its parent");
});

test("reply to an answer: a reply the store refuses keeps its words in the box, and Copy reply copies its re id and words", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [RPL_ROOT]: ASK_ANSWERED } }, storage: RPL_NEW, failSetText: "Refused reply" }); if (!page) return;
  const text = "Refused reply: can the rail guard change?";
  await openReply(page, RPL_ROOT);
  await page.fill(`#rt-${RPL_ROOT}`, text);
  await mustHave(page, `#rs-${RPL_ROOT}`, "Send reply button");
  await page.click(`#rs-${RPL_ROOT}`);
  await page.waitForFunction((id) => /Not saved/.test(document.getElementById(id)?.textContent || ""), `rh-${RPL_ROOT}`, { timeout: 3000 }).catch(() => {});
  const hint = ((await page.textContent(`#rh-${RPL_ROOT}`)) ?? "").trim();
  assert.match(hint, /^Not saved \(/, "the refused reply's hint does not say it was not saved: " + JSON.stringify(hint));
  assert.match(hint, /Your reply is still in the box/, "the hint does not say the reply is still in the box: " + JSON.stringify(hint));
  assert.equal(await page.inputValue(`#rt-${RPL_ROOT}`), text, "the refused reply lost its words");
  assert.equal(await page.locator(`#rs-${RPL_ROOT}`).isDisabled(), false, "Send reply is off after a refused save, so it cannot try again");
  await mustHave(page, `#rc-${RPL_ROOT}`, "Copy reply button");
  await page.evaluate(() => { Object.defineProperty(navigator, "clipboard", { value: { writeText: async (s) => { window.__copied = s; } } }); });
  await page.click(`#rc-${RPL_ROOT}`);
  await page.waitForFunction(() => typeof window.__copied === "string", null, { timeout: 3000 }).catch(() => {});
  assert.equal(await page.evaluate(() => window.__copied), `re ${RPL_ROOT}: ${text}`, "Copy reply did not copy the re id and the words");
});

test("reply to an answer: an empty reply box keeps Send reply off and says why; over 4000 characters it is off with the limit words and nothing is cut", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [RPL_ROOT]: ASK_ANSWERED } }, storage: RPL_NEW }); if (!page) return;
  await openReply(page, RPL_ROOT);
  await mustHave(page, `#rs-${RPL_ROOT}`, "Send reply button");
  assert.equal(await page.locator(`#rs-${RPL_ROOT}`).isDisabled(), true, "Send reply is on with an empty box");
  assert.match((await page.textContent(`#rh-${RPL_ROOT}`)) ?? "", /Send reply turns on once you type\./, "the empty box does not say why Send reply is off");
  const over = "Reply word. ".repeat(400).trim();
  await page.fill(`#rt-${RPL_ROOT}`, over);
  assert.equal(await page.locator(`#rs-${RPL_ROOT}`).isDisabled(), true, "Send reply is on over 4000 characters");
  const hint = ((await page.textContent(`#rh-${RPL_ROOT}`)) ?? "").trim();
  assert.ok(hint.includes(`Your reply is ${over.length} characters. The limit is 4000.`) && hint.includes("Nothing was cut."), "the over-limit hint says: " + JSON.stringify(hint));
  assert.equal(await page.inputValue(`#rt-${RPL_ROOT}`), over, "the words in the reply box were cut");
  assert.deepEqual(await rplKeys(page), [], "a write happened while Send reply was off");
});

test("reply to an answer: a reply closed as a draft is in the reply box after a reload, and its Send names the same re", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [RPL_ROOT]: ASK_ANSWERED } }, storage: RPL_NEW }); if (!page) return;
  await openReply(page, RPL_ROOT);
  await page.fill(`#rt-${RPL_ROOT}`, RPL_TEXT);
  await mustHave(page, `#rx-${RPL_ROOT}`, "Close button of the reply box");
  await page.click(`#rx-${RPL_ROOT}`);
  await page.reload();
  await page.waitForFunction("state.items.length > 0");
  await openReply(page, RPL_ROOT);
  assert.equal(await page.inputValue(`#rt-${RPL_ROOT}`), RPL_TEXT, "the draft did not survive the reload");
  await sendReply(page, RPL_ROOT);
  const body = (await askWrites(page))[0];
  assert.equal(body.text, RPL_TEXT, "the reply sent after the reload has the words " + JSON.stringify(body.text));
  assert.equal(body.re, RPL_ROOT, "the reply sent after the reload names re " + JSON.stringify(body.re) + ", not " + RPL_ROOT);
});

test("reply to an answer: Reply stays at the thread's end while a reply waits, and a second reply names the same re", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [RPL_ROOT]: ASK_ANSWERED } }, storage: RPL_NEW }); if (!page) return;
  await replyTo(page, RPL_ROOT, RPL_TEXT);
  const first = await rplLast(page);
  // The first reply's Undo count ends, as it does for a visit that waits: the reply then waits in its thread.
  await jump(page, 9000);
  await mustHave(page, `.thread .myreply[id="${first}"]`, "the waiting reply in its thread");
  await openReply(page, RPL_ROOT);
  await page.fill(`#rt-${RPL_ROOT}`, "A second reply in the same thread.");
  await sendReply(page, RPL_ROOT);
  const bodies = await askWrites(page);
  assert.equal(bodies.length, 2, "the second reply made " + bodies.length + " asks writes in all");
  assert.equal(bodies[1].re, RPL_ROOT, "the second reply names re " + JSON.stringify(bodies[1].re) + ", not the root ask " + RPL_ROOT);
});

test("reply to an answer: words typed while the reply saves stay in the box", async (t) => {
  const LATER = "Also, does the Status tab show it?";
  // The reply's write waits at the hold, so the words typed next land while it saves.
  const page = await open(t, { dbExtra: { asks: { [RPL_ROOT]: ASK_ANSWERED } }, storage: RPL_NEW, hold: { set: 0 } }); if (!page) return;
  await openReply(page, RPL_ROOT);
  await page.fill(`#rt-${RPL_ROOT}`, RPL_TEXT);
  await mustHave(page, `#rs-${RPL_ROOT}`, "Send reply button");
  await page.click(`#rs-${RPL_ROOT}`);
  assert.equal(await page.waitForFunction(() => window.__held > 0).then(() => true, () => false), true, "the reply's write never reached the store");
  await mustHave(page, `#rt-${RPL_ROOT}`, "reply box while the reply saves");
  await page.click(`#rt-${RPL_ROOT}`);
  await page.keyboard.press("End");
  await page.keyboard.type(" " + LATER);
  await page.evaluate(() => window.__release());
  await mustHave(page, "#askUndo", "Undo control once the reply saved");
  // A send closes the box, and Reply reopens the words that were not sent (notes, sections 1 and 2).
  const draft = (await page.evaluate((key) => localStorage.getItem(key), `waiting.replyDraft.${RPL_ROOT}`)) ?? "";
  assert.equal(draft.trim(), LATER, "the stored draft after the send is " + JSON.stringify(draft) + ", not the words typed while the reply saved");
  await openReply(page, RPL_ROOT);
  const box = await page.inputValue(`#rt-${RPL_ROOT}`);
  assert.equal(box.trim(), LATER, "the reply box holds " + JSON.stringify(box) + ", not the words typed while the reply saved");
});

test("reply to an answer: a refused reply keeps focus in the reply form", async (t) => {
  const text = "Refused reply: can the rail guard change?";
  const page = await open(t, { dbExtra: { asks: { [RPL_ROOT]: ASK_ANSWERED } }, storage: RPL_NEW, failSetText: "Refused reply" }); if (!page) return;
  await openReply(page, RPL_ROOT);
  await page.fill(`#rt-${RPL_ROOT}`, text);
  await mustHave(page, `#rs-${RPL_ROOT}`, "Send reply button");
  await page.click(`#rs-${RPL_ROOT}`);
  const refused = await page.waitForFunction((id) => /Not saved/.test(document.getElementById(id)?.textContent || ""), `rh-${RPL_ROOT}`, { timeout: 3000 }).then(() => true, () => false);
  assert.equal(refused, true, "the refused reply's hint does not say Not saved");
  const active = await page.evaluate(() => { const a = document.activeElement; return a && a !== document.body ? a.id || a.tagName : "BODY"; });
  assert.ok([`rt-${RPL_ROOT}`, `rs-${RPL_ROOT}`].includes(active), "after the refused reply focus is on " + active + ", not the reply form");
});

// ---------------------------------------------------------------- Mark read on an answered ask (step ask-dismiss)
// Contract: docs/design/ask-dismiss-notes.md, sections 1-8; the mockup is docs/design/ask-dismiss.html.
// Mark read writes `dismissed` (an ISO time) on the thread's root ask, with update. Mark unread writes `dismissed: null`. Nothing is deleted.
// Per thread, keyed by the root ask id <k>: #dis-<k> (Mark read), #dw-<k> (the reason while it is off), #res-<k> (Mark unread),
// li#row-<k>.askc.dropped (the Marked read line). The unfold is #askDismissed, and the read list is ol#askDList.
const DIS_ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;
const DIS_OFF = "your reply waits: no Mark read until it has its answer";
const DIS_EMPTY = "No ask on the list. Type above, and a session answers here.";
// The rows of the main list that are asks, not a Marked read line (its .dt holds the root text) and not the read list.
const DIS_SHOWN = "ol.asklist:not(.dlist) > li.askc:not(.dropped)";
// DIS_KEEP is the control: it has no dismissed field, so it shows on load in every case.
const DIS_KEEP = { id: "ask-dis-keep", text: "Can the Status tab show the lane queue?", at: "2026-10-29T09:00:00Z", owner: "triage", answered: "2026-10-29T10:00:00Z", reply: "Yes. It is on the Status tab." };
// Dismissed, with no answer later than the dismiss: hidden on load.
const DIS_HIDDEN = { id: "ask-dis-hid", text: "Did the rail guard change in round 3?", at: "2026-10-28T08:00:00Z", owner: "triage", answered: "2026-10-28T09:00:00Z", reply: "No. The rail guard is unchanged.", dismissed: "2026-10-30T12:00:00Z" };
const DIS_OLD = { id: "ask-dis-old", text: "Is the old lane queue still running?", at: "2026-10-20T08:00:00Z", owner: "triage", answered: "2026-10-20T09:00:00Z", reply: "Yes, it is running.", dismissed: "2026-10-21T08:00:00Z" };
// Dismissed, but a reply in its thread was answered after the dismiss: the thread shows again.
const DIS_LATER = { id: "ask-dis-late", text: "Is the queue page still on the Status tab?", at: "2026-10-27T08:00:00Z", owner: "triage", answered: "2026-10-27T09:00:00Z", reply: "Yes.", dismissed: "2026-10-28T12:00:00Z" };
const DIS_LATER_REPLY = { id: "ask-dis-late-r", text: "Has the queue page changed since?", at: "2026-10-31T08:00:00Z", re: DIS_LATER.id, owner: "lane tier-fold", answered: "2026-10-31T09:00:00Z", reply: "No. It has not changed." };
// Dismissed, then a reply came in and still waits: the thread shows again, whatever dismissed says.
const DIS_WAITED = { id: "ask-dis-wd", text: "Dismissed before a reply came in", at: "2026-10-26T08:00:00Z", owner: "triage", answered: "2026-10-26T09:00:00Z", reply: "Yes.", dismissed: "2026-10-27T08:00:00Z" };
const DIS_WAITED_REPLY = { id: "ask-dis-wd-r", text: "A new question on the dismissed ask", at: "2026-10-31T10:00:00Z", re: DIS_WAITED.id };
// A reply to DIS_HIDDEN that comes in after the thread is restored this visit, and waits for its answer.
const DIS_HIDDEN_REPLY = { id: "ask-dis-hid-r", text: "Does the rail guard need its own test?", at: "2026-10-31T10:00:00Z", re: DIS_HIDDEN.id };
// The routed ask of the Mark read cases below and of the ask-phase-out block. Answered after READ_FROM, with a home: one line, with Mark read beside it.
const AP_ASK = { id: "ask-ap-routed", text: "Which step holds the one-line rule?", at: "2026-10-30T09:00:00Z", owner: "triage", answered: "2026-11-10T18:01:00Z", reply: "Routed to step ask-phase-out. The rest is on the Status tab.", home: "step:ask-phase-out" };
// A reply in the thread that still waits for its answer.
const DIS_WAIT ={ id: "ask-dis-wait", text: "Is the queue still right after the fix?", at: "2026-10-31T08:00:00Z", re: AP_ASK.id };
const dismissWrites = (page) => page.evaluate(() => window.__log.filter((l) => l[0] === "update" && l[1] === "asks").map((l) => ({ id: l[2], body: l[3] })));
// Waits, up to 1.5 s, for the store to hold n asks updates. The caller asserts the count, so a wait that gives up fails by name.
const waitUpdates = (page, n) => page.waitForFunction((k) => window.__log.filter((l) => l[0] === "update" && l[1] === "asks").length >= k, n, { timeout: 1500 }).catch(() => {});
// The record as the store holds it, from the stub's kept copy. Null when the store has no such record.
const storedAsk = (page, id) => page.evaluate((k) => ((JSON.parse(localStorage.getItem("__stub.asks") || "null")) || {})[k] || null, id);
// Presses Mark read on the thread and waits for its update. The button must be on, so a press that cannot go fails by name.
async function pressDismiss(page, root) {
  await mustHave(page, `#dis-${root}`, "Mark read on the answered ask");
  assert.notEqual(await page.getAttribute(`#dis-${root}`, "aria-disabled"), "true", "Mark read is off on the answered ask");
  const before = (await dismissWrites(page)).length;
  await page.click(`#dis-${root}`);
  await waitUpdates(page, before + 1);
}

test("dismiss control: a thread with no dismissed field shows on load, and no Show read unfold draws", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [ASK_ANSWERED.id]: ASK_ANSWERED, [DIS_KEEP.id]: DIS_KEEP } }, storage: RPL_NEW }); if (!page) return;
  await shownBox(page, ASK_ANSWERED.text, DIS_SHOWN);
  await shownBox(page, DIS_KEEP.text, DIS_SHOWN);
  assert.equal(await page.locator("#askDismissed").count(), 0, "a Show read unfold draws with nothing dismissed");
});

test("dismiss: the open card's Mark read sits at the thread's end beside Reply, Reply first, and names its ask", async (t) => {
  const root = AP_ASK.id;
  const page = await open(t, { dbExtra: { asks: { [root]: AP_ASK } }, storage: RPL_NEW }); if (!page) return;
  // A routed ask is one line until it is opened: its card, with Reply and Mark read at the end, is what this case reads.
  await mustHave(page, `button.frow[data-ask="${root}"]`, "the one line of the routed ask");
  await page.click(`button.frow[data-ask="${root}"]`);
  await mustHave(page, `#dis-${root}`, "Mark read on the answered ask");
  const at = await page.locator(`#dis-${root}`).evaluate((b, id) => {
    const row = b.closest(".endrow"), end = b.closest(".replyend"), reply = document.getElementById("reply-" + id);
    return { tag: b.tagName, inRow: !!row && !!end && end.contains(row), replyFirst: !!reply && !!row && row.contains(reply) && !!(reply.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING), label: b.getAttribute("aria-label") };
  }, root);
  assert.equal(at.tag, "BUTTON", "Mark read is a " + at.tag + ", not a button");
  assert.equal(at.inRow, true, "Mark read is not in the thread's .endrow, under .replyend");
  assert.equal(at.replyFirst, true, "Mark read does not come after Reply in the same .endrow");
  assert.equal(at.label, "Mark read: " + AP_ASK.text, "Mark read is labelled " + JSON.stringify(at.label));
});

test("dismiss: Mark read writes dismissed, an ISO time, on the root ask with update, never set or delete, and the owner's text and the reply survive", async (t) => {
  const root = AP_ASK.id;
  const page = await open(t, { dbExtra: { asks: { [root]: AP_ASK } }, storage: RPL_NEW }); if (!page) return;
  await pressDismiss(page, root);
  const ups = await dismissWrites(page);
  assert.equal(ups.length, 1, "Mark read made " + ups.length + " update writes on asks, not one");
  assert.equal(ups[0].id, root, "Mark read updated " + ups[0].id + ", not the root ask " + root);
  assert.deepEqual(Object.keys(ups[0].body), ["dismissed"], "the update writes " + Object.keys(ups[0].body).join(", ") + ", not only dismissed");
  assert.match(ups[0].body.dismissed, DIS_ISO, "dismissed is not an ISO time: " + ups[0].body.dismissed);
  const bad = await page.evaluate(() => window.__log.filter((l) => (l[0] === "set" || l[0] === "delete") && l[1] === "asks"));
  assert.deepEqual(bad, [], "Mark read made set or delete writes on asks: " + JSON.stringify(bad.map((l) => [l[0], l[2]])));
  const kept = await storedAsk(page, root);
  assert.equal(kept && kept.text, AP_ASK.text, "the stored text is " + JSON.stringify(kept && kept.text) + ", not the owner's words");
  assert.equal(kept && kept.reply, AP_ASK.reply, "the stored reply is " + JSON.stringify(kept && kept.reply) + ", not the session's reply");
  assert.equal(kept && kept.dismissed, ups[0].body.dismissed, "the stored dismissed is " + JSON.stringify(kept && kept.dismissed));
});

test("dismiss: the thread stays in place as a Marked read line with Mark unread and no Undo count, and focus moves to the line", async (t) => {
  const root = AP_ASK.id;
  const page = await open(t, { dbExtra: { asks: { [root]: AP_ASK } }, storage: RPL_NEW }); if (!page) return;
  // Each focus move from the press on, so a miss names where focus went and what took it.
  await page.evaluate(() => {
    const name = (e) => (e ? (e.id ? "#" + e.id : e.tagName.toLowerCase()) + (e.isConnected ? "" : "(removed)") : "none");
    window.__focusMoves = [];
    for (const k of ["focusin", "focusout"]) document.addEventListener(k, (e) => window.__focusMoves.push(k.slice(5) + " " + name(e.target)), true);
    for (const k of ["blur", "focus"]) window.addEventListener(k, (e) => { if (e.target === window) window.__focusMoves.push("window " + k); });
  });
  await pressDismiss(page, root);
  await mustHave(page, `li#row-${root}.askc.dropped`, "the Marked read line in the thread's place");
  // One step reads the line and focus together. A locator found in one step and read in a second can hold a line a re-render has replaced.
  const line = await page.evaluate((id) => { const r = document.getElementById("row-" + id), sl = r ? r.querySelector(":scope > p.sline:not(.dline)") : null, a = document.activeElement; return { text: r ? r.textContent.replace(/\s+/g, " ").trim() : "", tabindex: r ? r.getAttribute("tabindex") : null, liRole: r ? r.getAttribute("role") : null, lineRole: sl ? sl.getAttribute("role") : null, focused: !!r && a === r, at: a ? (a.id ? "#" + a.id : a.tagName.toLowerCase()) : "none", moves: (window.__focusMoves ? window.__focusMoves.join(", ") : "trace lost, the page reloaded") + " (document has focus: " + document.hasFocus() + ")", restore: !!r && !!r.querySelector("#res-" + id), undo: !!document.getElementById("dun-" + id) }; }, root);
  assert.ok(line.text.startsWith("Marked read. " + AP_ASK.text), "the Marked read line reads " + JSON.stringify(line.text));
  assert.equal(line.restore, true, "the Marked read line has no Mark unread");
  assert.equal(line.undo, false, "the Marked read line has an Undo count, not Mark unread alone");
  assert.equal(line.tabindex, "-1", "the Marked read line has tabindex " + line.tabindex + ", not -1");
  assert.equal(line.lineRole, "status", "the Marked read line's p.sline has role " + line.lineRole + ", not status");
  assert.equal(line.liRole, null, "the Marked read line's li has role " + line.liRole + ", not none: its p.sline carries status");
  assert.equal(line.focused, true, "focus is not on the Marked read line: it is on " + line.at + "; focus moves: " + line.moves);
});

test("dismiss: a dismissed thread is hidden on load, and one with an answer later than its dismissed, or a reply waiting, shows again", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [DIS_KEEP.id]: DIS_KEEP, [DIS_HIDDEN.id]: DIS_HIDDEN, [DIS_LATER.id]: DIS_LATER, [DIS_LATER_REPLY.id]: DIS_LATER_REPLY, [DIS_WAITED.id]: DIS_WAITED, [DIS_WAITED_REPLY.id]: DIS_WAITED_REPLY } }, storage: RPL_NEW }); if (!page) return;
  // The control is drawn first, so a thread missing from the page is missing from a drawn list.
  await shownBox(page, DIS_KEEP.text, DIS_SHOWN);
  assert.equal(await page.getByText(DIS_HIDDEN.text, { exact: true }).count(), 0, "the dismissed thread with no later answer is on the list at load");
  await shownBox(page, DIS_LATER.text, DIS_SHOWN);
  await shownBox(page, DIS_LATER_REPLY.text, DIS_SHOWN);
  // A dismissed root under a reply that waits: its folded row shows the root text again.
  await shownBox(page, DIS_WAITED.text, DIS_SHOWN);
});

test("dismiss: Show N read asks opens the read list, newest first, with Mark unread beside each thread", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [DIS_KEEP.id]: DIS_KEEP, [DIS_HIDDEN.id]: DIS_HIDDEN, [DIS_OLD.id]: DIS_OLD } }, storage: RPL_NEW }); if (!page) return;
  await shownBox(page, DIS_KEEP.text, DIS_SHOWN);
  await mustHave(page, "#askDismissed", "Show read asks unfold");
  const label = ((await page.textContent("#askDismissed")) || "").replace(/\s+/g, " ").trim();
  assert.ok(label.includes("Show 2 read asks"), "the unfold reads " + JSON.stringify(label));
  await page.click("#askDismissed");
  await mustHave(page, "ol#askDList.asklist.dlist", "read list");
  assert.equal(await page.getAttribute("ol#askDList", "aria-label"), "Read asks, newest first", "the read list has the wrong label");
  const order = await page.$$eval("ol#askDList .frow", (rows) => rows.map((r) => r.dataset.ask));
  assert.deepEqual(order, [DIS_HIDDEN.id, DIS_OLD.id], "the read list holds " + JSON.stringify(order) + ", not the two threads newest first");
  for (const it of [DIS_HIDDEN, DIS_OLD]) assert.equal(await page.locator(`ol#askDList #res-${it.id}`).count(), 1, "no Mark unread beside " + JSON.stringify(it.text) + " in the read list");
});

test("dismiss: Mark unread writes dismissed null with update, the line says the thread joins the list at the next load, and it returns after a reload", async (t) => {
  const root = AP_ASK.id;
  const page = await open(t, { dbExtra: { asks: { [root]: AP_ASK } }, storage: RPL_NEW }); if (!page) return;
  await pressDismiss(page, root);
  await mustHave(page, `#res-${root}`, "Mark unread on the Marked read line");
  const before = (await dismissWrites(page)).length;
  await page.click(`#res-${root}`);
  await waitUpdates(page, before + 1);
  const ups = await dismissWrites(page);
  assert.equal(ups.length - before, 1, "Mark unread made " + (ups.length - before) + " update writes, not one");
  assert.deepEqual(ups.at(-1).body, { dismissed: null }, "Mark unread wrote " + JSON.stringify(ups.at(-1).body) + ", not dismissed: null");
  // The line stays where it is and says when the thread returns. Mark read takes Mark unread's place.
  await mustHave(page, `li#row-${root} #dis-${root}`, "Mark read in place of Mark unread on the line");
  assert.equal(await page.locator(`li#row-${root} #res-${root}`).count(), 0, "Mark unread is still on the line");
  const said = ((await page.locator(`li#row-${root}`).textContent()) || "").replace(/\s+/g, " ").trim();
  assert.ok(said.includes("It joins the list at the next load."), "the line reads " + JSON.stringify(said));
  // The next load draws the thread again, and the stored record has dismissed null.
  await page.reload();
  await shownBox(page, AP_ASK.text, DIS_SHOWN);
  assert.equal(await page.locator("#askDismissed").count(), 0, "the restored thread is still under Show read asks after a reload");
  const kept = await storedAsk(page, root);
  assert.ok(kept && kept.dismissed === null, "the stored dismissed is " + JSON.stringify(kept && kept.dismissed) + ", not null");
});

test("dismiss: a thread dismissed at load and restored this visit shows in the main list when a reply in it then waits", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [DIS_KEEP.id]: DIS_KEEP, [DIS_HIDDEN.id]: DIS_HIDDEN } }, storage: RPL_NEW }); if (!page) return;
  await shownBox(page, DIS_KEEP.text, DIS_SHOWN);
  await mustHave(page, "#askDismissed", "Show read asks unfold");
  await page.click("#askDismissed");
  await mustHave(page, `ol#askDList #res-${DIS_HIDDEN.id}`, "Mark unread in the read list");
  const before = (await dismissWrites(page)).length;
  await page.click(`ol#askDList #res-${DIS_HIDDEN.id}`);
  await waitUpdates(page, before + 1);
  const said = await page.waitForFunction(() => document.body.textContent.includes("It joins the list at the next load."), null, { timeout: 3000 }).then(() => true, () => false);
  assert.equal(said, true, "the restore does not say It joins the list at the next load.");
  // A reply comes in after the restore, as a session's write after the page loaded, and waits for its answer.
  await page.evaluate((r) => window.__putDoc("asks", r.id, r), DIS_HIDDEN_REPLY);
  // The main list is the scope, so it is asserted before the read list is checked away.
  await mustHave(page, `${DIS_SHOWN}#row-${DIS_HIDDEN.id}`, "restored thread in the main list");
  assert.equal(await page.locator("#askDismissed").count(), 0, "the restored thread is still under Show read asks");
});

test("dismiss: while a reply in the thread waits, Mark read is off and says why, and a folded row with that reply has no Mark read", async (t) => {
  const root = AP_ASK.id;
  const page = await open(t, { dbExtra: { asks: { [root]: AP_ASK, [DIS_WAIT.id]: DIS_WAIT } }, storage: RPL_NEW }); if (!page) return;
  await mustHave(page, `#dis-${root}`, "Mark read on the answered ask with a reply waiting");
  assert.equal(await page.getAttribute(`#dis-${root}`, "aria-disabled"), "true", "Mark read is on while its reply waits");
  const reason = ((await page.textContent(`#dw-${root}`)) || "").trim();
  assert.equal(reason, DIS_OFF, "the reason reads " + JSON.stringify(reason));
  assert.ok(((await page.getAttribute(`#dis-${root}`, "aria-describedby")) || "").split(" ").includes(`dw-${root}`), "Mark read is not described by its reason");
  // The press is read straight after it, in a second evaluate, so a write the handler makes has landed.
  await page.evaluate((id) => document.getElementById(id).click(), `dis-${root}`);
  const writes = await page.evaluate(() => window.__log.filter((l) => l[0] === "update").length);
  assert.equal(writes, 0, "a press on the off Mark read wrote " + writes + " update(s)");
  const folded = await open(t, { dbExtra: { asks: { [root]: AP_ASK, [DIS_WAIT.id]: DIS_WAIT } }, storage: RPL_SEEN_AP }); if (!folded) return;
  await mustHave(folded, `button.frow[data-ask="${root}"]`, "the folded row of the answered ask");
  await mustHave(folded, "li.askc.folded .fwait", "the waiting reply line under the folded row");
  assert.equal(await folded.locator(`[id="dis-${root}"]`).count(), 0, "a folded row with a waiting reply has a Mark read");
});

test("dismiss: on a folded answered row, Mark read sits beside the row button, never inside it, and writes dismissed", async (t) => {
  const root = AP_ASK.id;
  const page = await open(t, { dbExtra: { asks: { [root]: AP_ASK } }, storage: RPL_SEEN_AP }); if (!page) return;
  await mustHave(page, `button.frow[data-ask="${root}"]`, "folded row of the answered ask");
  await mustHave(page, `#dis-${root}`, "Mark read on the folded row");
  const at = await page.locator(`#dis-${root}`).evaluate((b) => { const li = b.closest("li.askc"), row = li && li.querySelector(".frow"); return { withd: !!li && li.classList.contains("folded") && li.classList.contains("withd"), inRow: !!row && row.contains(b), beside: !!row && b.parentElement === row.parentElement }; });
  assert.equal(at.withd, true, "the folded row lacks the li.askc.folded.withd classes");
  assert.equal(at.inRow, false, "Mark read is inside the folded row's button");
  assert.equal(at.beside, true, "Mark read is not beside the folded row's button");
  await pressDismiss(page, root);
  const ups = await dismissWrites(page);
  assert.equal(ups.length, 1, "Mark read on the folded row made " + ups.length + " update writes, not one");
  assert.equal(ups[0].id, root, "Mark read on the folded row updated " + ups[0].id + ", not " + root);
  assert.match(ups[0].body.dismissed, DIS_ISO, "dismissed is not an ISO time: " + ups[0].body.dismissed);
});

test("dismiss: when the write is refused, the thread stays on the list, Mark read stays on, and the line says why", async (t) => {
  const root = AP_ASK.id;
  const page = await open(t, { dbExtra: { asks: { [root]: AP_ASK } }, storage: RPL_NEW, failUpdate: true }); if (!page) return;
  // The refused line sits in the open card's reply end, so the one line is opened first.
  await mustHave(page, `button.frow[data-ask="${root}"]`, "the one line of the routed ask");
  await page.click(`button.frow[data-ask="${root}"]`);
  await mustHave(page, `#dis-${root}`, "Mark read on the answered ask");
  await page.click(`#dis-${root}`);
  assert.equal(await rplLineHas(page, "Not marked read (permission-denied)"), true, "the refused Mark read does not say Not marked read (permission-denied)");
  assert.equal(await rplLineHas(page, "It stays on the list."), true, "the refused Mark read does not say It stays on the list.");
  await shownBox(page, AP_ASK.text, DIS_SHOWN);
  assert.notEqual(await page.getAttribute(`#dis-${root}`, "aria-disabled"), "true", "Mark read is off after a refused write, so it cannot try again");
});

test("dismiss: when Mark unread is refused, the thread stays read and the line says it stays read", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [DIS_HIDDEN.id]: DIS_HIDDEN } }, storage: RPL_NEW, failUpdate: true }); if (!page) return;
  await mustHave(page, "#askDismissed", "Show read asks unfold");
  await page.click("#askDismissed");
  await mustHave(page, `ol#askDList #res-${DIS_HIDDEN.id}`, "Mark unread in the read list");
  await page.click(`ol#askDList #res-${DIS_HIDDEN.id}`);
  const said = await page.waitForFunction(() => document.body.textContent.includes("Not marked unread (permission-denied). It stays read."), null, { timeout: 3000 }).then(() => true, () => false);
  assert.equal(said, true, "the refused Mark unread does not say Not marked unread (permission-denied). It stays read.");
  await mustHave(page, `ol#askDList #res-${DIS_HIDDEN.id}`, "the thread still in the read list after the refused Mark unread");
});

test("dismiss: with every ask dismissed, the list says No ask on the list, and the Show read unfold stays", async (t) => {
  const page = await open(t, { dbExtra: { asks: { [DIS_HIDDEN.id]: DIS_HIDDEN, [DIS_OLD.id]: DIS_OLD } }, storage: RPL_NEW }); if (!page) return;
  await mustHave(page, "#askDismissed", "Show read asks unfold, with nothing else on the list");
  const list = ((await page.textContent("#askList")) || "").replace(/\s+/g, " ").trim();
  assert.ok(list.includes(DIS_EMPTY), "the list reads " + JSON.stringify(list) + ", not the empty sentence");
  assert.equal(await page.locator("#askList li.askc").count(), 0, "a thread is still drawn on the list");
});

test("dismiss: a read list of 12 threads draws all 12, newest first", async (t) => {
  const many = Array.from({ length: 12 }, (_, i) => ({ id: "ask-dis-m" + String(i).padStart(2, "0"), text: "Dismissed ask " + (i + 1), at: new Date(Date.UTC(2026, 8, 1 + i, 9)).toISOString(), owner: "triage", answered: new Date(Date.UTC(2026, 8, 1 + i, 10)).toISOString(), reply: "Answer " + (i + 1), dismissed: new Date(Date.UTC(2026, 8, 1 + i, 11)).toISOString() }));
  const asks = Object.fromEntries([DIS_KEEP, ...many].map((a) => [a.id, a]));
  const page = await open(t, { dbExtra: { asks }, storage: RPL_NEW }); if (!page) return;
  await shownBox(page, DIS_KEEP.text, DIS_SHOWN);
  await mustHave(page, "#askDismissed", "Show read asks unfold");
  const label = ((await page.textContent("#askDismissed")) || "").replace(/\s+/g, " ").trim();
  assert.ok(label.includes("Show 12 read asks"), "the unfold reads " + JSON.stringify(label));
  await page.click("#askDismissed");
  await mustHave(page, "ol#askDList.asklist.dlist", "read list");
  const order = await page.$$eval("ol#askDList .frow", (rows) => rows.map((r) => r.dataset.ask));
  assert.deepEqual(order, [...many].reverse().map((a) => a.id), "the read list holds " + order.length + " rows, not the 12 threads newest first");
});

test("dismiss: with no store, the list says it cannot be read and no Mark read is drawn", async (t) => {
  const page = await open(t, { noStore: true }); if (!page) return;
  await shownBox(page, "Your asks cannot be read in this view.");
  assert.equal(await page.locator('[id^="dis-"], .dismiss').count(), 0, "a Mark read is drawn with no store");
});

// Owner pick 480 a (09:14 CST Nov 10): Mark read follows the reply's home. An answered ask with no home draws no Mark read. The routed
// ask on the same page is the control: its Mark read must be there, so the no-home check cannot pass on an empty list.
for (const [label, storage] of [["a new answer", RPL_NEW], ["a seen answer", RPL_SEEN_AP]]) {
  test(`ask-no-home: an answered ask with no home draws no Mark read, and the routed ask beside it does (${label})`, async (t) => {
    const page = await open(t, { dbExtra: { asks: { [AP_ASK.id]: AP_ASK, [ASK_ANSWERED.id]: ASK_ANSWERED } }, storage }); if (!page) return;
    await mustHave(page, `li#row-${AP_ASK.id}`, `the row of the routed ask ${AP_ASK.id}`);
    await mustHave(page, `li#row-${ASK_ANSWERED.id}`, `the row of the ask with no home ${ASK_ANSWERED.id}`);
    await needButton(page.locator(`li#row-${AP_ASK.id}`), /^Mark read/, `Mark read on the routed ask ${AP_ASK.id}, the control`);
    const bare = await page.locator(`li#row-${ASK_ANSWERED.id}`).getByRole("button", { name: /^Mark read/ }).count();
    assert.equal(bare, 0, `the ask with no home ${ASK_ANSWERED.id} draws a Mark read control, and pick 480 a draws none`);
  });
}

// ---------------------------------------------------------------- ask-phase-out: one line, then Mark read (step ask-phase-out)
// Contract: docs/design/ask-phase-out-notes.md, sections 2 to 5 and 7; the mockup is docs/design/ask-phase-out.html.
// Rulings: owner pick 480 a (09:14 CST Nov 10): a routed ask or answered item shows one line, and Mark read takes it off the
// list. Coordinator fold (10:57 CST Nov 10): a closed item with a `closed` time stays as one line in Answered until Mark read;
// a closed item with no `closed` time counts as read and never comes back. The act is Mark read, its undo Mark unread.
// A routed ask has a home and a reply, and no record in its thread waits. A routed item is a closed item with a `closed` time,
// or an open item with a filed receipt and no waits.
// Every case lists an open, unanswered item first (TASK), so open() waits for an id that every build keeps.
// READ_FROM, the ship time of the one-line rule, is 2026-11-10T18:00:00Z. AP_ASK (18:01Z) is answered after it, so it is a line;
// AP_EARLY (17:59Z) is answered before it, so it reads as read. Both are in the past: Mark read stamps dismissed with the page's
// clock, and an answer later than that stamp keeps the ask on the list.
const AP_EARLY = { id: "ask-ap-early", text: "Was the one-line rule routed before the ship time?", at: "2026-11-10T16:00:00Z", owner: "triage", answered: "2026-11-10T17:59:00Z", reply: "Routed to step ask-phase-out before the ship time.", home: "step:ask-phase-out" };
const AP_CLOSED = mk("ap-closed", 70, { status: "closed", closed: "2026-11-09T15:00:00Z", home: "step:ask-phase-out", reply: "Filed as step ask-phase-out. The record stays there." });
// Closed before the ship time: no `closed` field, so it counts as read.
const AP_CLOSED_OLD = mk("ap-closed-old", 71, { status: "closed", home: "step:ask-phase-out", reply: "Old answer, closed before the ship time." });
// Closed and already marked read: it sits under Show read items.
const AP_READ = mk("ap-read", 72, { status: "closed", closed: "2026-11-09T15:00:00Z", dismissed: "2026-11-09T16:00:00Z", home: "step:ask-phase-out", reply: "Read already. It is on the Status tab." });
// An open item that carries the two new fields: the page must draw both, so no field warning shows on its card.
const AP_FIELDS = mk("ap-fields", 73, { closed: "2026-11-09T15:00:00Z", dismissed: "2026-11-09T16:00:00Z" });
const AP_UNKNOWN = mk("ap-unknown", 74, { zzzNotAField: "x" });
const AP_FILED = mk("ap-filed", 75, { added: at(5) });
const AP_PENDING = mk("ap-pending", 76, { added: at(6) });
const AP_OPEN = TASK;
// A closed item with no home and a title too long for one row: its head keeps the number, the title and the home on one row.
const AP_LONG_TITLE = "A closed item whose title runs on and on and on and on, so that it cannot fit one row at tablet or desktop width and must be cut ".repeat(2);
const AP_LONG = mk("ap-long", 77, { status: "closed", closed: "2026-11-09T15:00:00Z", home: "", title: AP_LONG_TITLE, reply: "Filed with no home." });
// The newer of two closed lines in the Answered section. AP_CLOSED (No. 70) closed at 15:00 the same day, so it sits under this one.
const AP_NEWER = mk("ap-newer", 78, { status: "closed", closed: "2026-11-09T16:00:00Z", home: "step:ask-phase-out", title: "Newer line", reply: "Newer." });
// A closed item with a home, a long title and a New reply: the row whose head must fit at tablet and phone width.
const AP_LONG_HOME = mk("ap-long-home", 79, { status: "closed", closed: "2026-11-09T15:00:00Z", home: "step:ask-phase-out", title: AP_LONG_TITLE, reply: "Filed as step ask-phase-out.", replied: "2026-10-28T09:00:00Z" });
const apWrites = (page, coll) => page.evaluate((c) => window.__log.filter((l) => l[0] === "update" && l[1] === c).map((l) => ({ id: l[2], body: l[3] })), coll);
const apBad = (page, coll) => page.evaluate((c) => window.__log.filter((l) => (l[0] === "set" || l[0] === "delete") && l[1] === c), coll);
// Waits, up to 1.5 s, for the store to hold n updates of one collection. The caller asserts the count, so a wait that gives up fails by name.
const apWaitUpdates = (page, coll, n) => page.waitForFunction(([c, k]) => window.__log.filter((l) => l[0] === "update" && l[1] === c).length >= k, [coll, n], { timeout: 1500 }).catch(() => {});
// A button found by its accessible name in a scope. A missing one fails by name, and the press is returned when it is there.
async function needButton(scope, re, what) {
  const n = await scope.getByRole("button", { name: re }).first().waitFor({ state: "attached", timeout: 3000 }).then(() => 1, () => 0);
  assert.equal(n, 1, `no ${what}`);
  return scope.getByRole("button", { name: re }).first();
}

test("ask-phase-out: a routed ask shows one line with its home and its short reply, and the line has Mark read, not the full card", async (t) => {
  const page = await open(t, { items: [AP_OPEN], dbExtra: { asks: { [AP_ASK.id]: AP_ASK } }, storage: RPL_SEEN }); if (!page) return;
  await mustHave(page, `li#row-${AP_ASK.id}`, `row of the routed ask ${AP_ASK.id}`);
  const row = page.locator(`li#row-${AP_ASK.id}`);
  await needButton(row, /^Mark read/, "Mark read button on the routed ask");
  const said = ((await row.textContent()) || "").replace(/\s+/g, " ");
  assert.ok(said.includes(AP_ASK.home), `the line of the routed ask does not show its home ${AP_ASK.home}`);
  assert.ok(said.includes("Routed to step ask-phase-out."), "the line of the routed ask does not show its short reply");
  assert.equal(await row.locator(`#reply-${AP_ASK.id}`).count(), 0, "the routed ask is drawn in full, with its Reply button, not as one line");
});

test("ask-phase-out: a routed ask answered before READ_FROM reads as read: no line on the list, and it sits under Show read asks", async (t) => {
  const page = await open(t, { items: [AP_OPEN], dbExtra: { asks: { [AP_EARLY.id]: AP_EARLY, [DIS_KEEP.id]: DIS_KEEP } }, storage: RPL_SEEN }); if (!page) return;
  await shownBox(page, DIS_KEEP.text, DIS_SHOWN); // the list has drawn, so the absence below is real
  assert.equal(await page.locator(`${DIS_SHOWN}#row-${AP_EARLY.id}`).count(), 0, `the routed ask ${AP_EARLY.id}, answered before READ_FROM, is drawn as a line on the list`);
  await mustHave(page, "#askDismissed", "Show read asks unfold, which holds the read asks");
  await page.click("#askDismissed");
  await mustHave(page, `ol#askDList li#row-${AP_EARLY.id}`, `the routed ask ${AP_EARLY.id} in the read list`);
});

test("ask-phase-out: Mark read on a routed ask writes dismissed with update, deletes nothing, keeps the record, and the ask leaves the list at the next load", async (t) => {
  const page = await open(t, { items: [AP_OPEN], dbExtra: { asks: { [AP_ASK.id]: AP_ASK, [DIS_KEEP.id]: DIS_KEEP } }, storage: RPL_SEEN }); if (!page) return;
  await shownBox(page, DIS_KEEP.text, DIS_SHOWN);
  const press = await needButton(page.locator(`li#row-${AP_ASK.id}`), /^Mark read/, "Mark read button on the routed ask");
  const before = (await apWrites(page, "asks")).length;
  await press.click();
  await apWaitUpdates(page, "asks", before + 1);
  const ups = (await apWrites(page, "asks")).slice(before);
  assert.equal(ups.length, 1, `Mark read made ${ups.length} update writes on asks, not one`);
  assert.equal(ups[0].id, AP_ASK.id, `Mark read updated ${ups[0].id}, not ${AP_ASK.id}`);
  assert.deepEqual(Object.keys(ups[0].body), ["dismissed"], `the update writes ${Object.keys(ups[0].body).join(", ")}, not only dismissed`);
  assert.match(ups[0].body.dismissed, DIS_ISO, `dismissed is not an ISO time: ${ups[0].body.dismissed}`);
  assert.deepEqual(await apBad(page, "asks"), [], "Mark read made a set or a delete on asks");
  const kept = await storedAsk(page, AP_ASK.id);
  assert.equal(kept && kept.text, AP_ASK.text, `the stored text is ${JSON.stringify(kept && kept.text)}, not the owner's words`);
  assert.equal(kept && kept.reply, AP_ASK.reply, `the stored reply is ${JSON.stringify(kept && kept.reply)}, not the session's reply`);
  assert.equal(kept && kept.home, AP_ASK.home, `the stored home is ${JSON.stringify(kept && kept.home)}`);
  await page.reload();
  await shownBox(page, DIS_KEEP.text, DIS_SHOWN);
  assert.equal(await page.locator(`${DIS_SHOWN}#row-${AP_ASK.id}`).count(), 0, "the marked ask is still on the list after the next load");
});

test("ask-phase-out: the read asks list is labelled Read asks, each row says Mark unread, and no Dismiss or Restore word is on the Ask area", async (t) => {
  const page = await open(t, { items: [AP_OPEN], dbExtra: { asks: { [DIS_KEEP.id]: DIS_KEEP, [DIS_HIDDEN.id]: DIS_HIDDEN, [DIS_OLD.id]: DIS_OLD } }, storage: RPL_NEW }); if (!page) return;
  await shownBox(page, DIS_KEEP.text, DIS_SHOWN);
  const fold = page.getByRole("button", { name: /Show \d+ read asks?/ });
  assert.equal(await fold.count(), 1, "no Show read asks fold: the read threads are not behind one button");
  await fold.click();
  const list = page.locator('ol[aria-label="Read asks, newest first"]');
  assert.equal(await list.count(), 1, "the read list is not labelled Read asks, newest first");
  assert.equal(await list.getByRole("button", { name: /^Mark unread/ }).count(), 2, "read list rows do not each have a Mark unread");
  const words = (await page.locator("#askList").textContent()) || "";
  assert.doesNotMatch(words, /Dismiss|Restore|Dismissed/, "the Ask area still says Dismiss, Dismissed or Restore");
});

test("ask-phase-out: a closed item with a closed time shows as one line in the Answered section, with its home, its short reply and Mark read", async (t) => {
  const page = await open(t, { items: [AP_OPEN, AP_CLOSED], clock: AP_NOW }); if (!page) return;
  await mustHave(page, "#tier-answered", `an Answered section for No. ${AP_CLOSED.n}, a closed item with a closed time`);
  await mustHave(page, `#tier-answered #line-${AP_CLOSED.n}`, `one line of No. ${AP_CLOSED.n} in the Answered section`);
  const line = page.locator(`#tier-answered #line-${AP_CLOSED.n}`);
  const said = ((await line.textContent()) || "").replace(/\s+/g, " ");
  assert.ok(said.includes("step:ask-phase-out"), `the line of No. ${AP_CLOSED.n} does not show its home`);
  assert.ok(said.includes("Filed as step ask-phase-out."), `the line of No. ${AP_CLOSED.n} does not show its short reply`);
  await needButton(line, new RegExp(`^Mark read: No\\. ${AP_CLOSED.n},`), `Mark read on the line of No. ${AP_CLOSED.n}`);
  assert.equal(await line.locator(".opts").count(), 0, `the line of No. ${AP_CLOSED.n} draws options`);
});

test("ask-phase-out: Mark read on a closed item's line writes dismissed with update on items, sets and deletes nothing, and the line has no Mark read after the press", async (t) => {
  const page = await open(t, { items: [AP_OPEN, AP_CLOSED], clock: AP_NOW }); if (!page) return;
  await mustHave(page, `#tier-answered #line-${AP_CLOSED.n}`, `one line of No. ${AP_CLOSED.n}`);
  const press = await needButton(page.locator(`#tier-answered #line-${AP_CLOSED.n}`), new RegExp(`^Mark read: No\\. ${AP_CLOSED.n},`), `Mark read on the line of No. ${AP_CLOSED.n}`);
  await press.click();
  await apWaitUpdates(page, "items", 1);
  const ups = await apWrites(page, "items");
  assert.equal(ups.length, 1, `Mark read made ${ups.length} update writes on items, not one`);
  assert.equal(ups[0].id, AP_CLOSED.id, `Mark read updated ${ups[0].id}, not ${AP_CLOSED.id}`);
  assert.deepEqual(Object.keys(ups[0].body), ["dismissed"], `the update writes ${Object.keys(ups[0].body).join(", ")}, not only dismissed`);
  assert.match(ups[0].body.dismissed, DIS_ISO, `dismissed is not an ISO time: ${ups[0].body.dismissed}`);
  assert.deepEqual(await apBad(page, "items"), [], "Mark read made a set or a delete on items");
  assert.equal(await page.locator("#tier-answered").getByRole("button", { name: new RegExp(`^Mark read: No\\. ${AP_CLOSED.n},`) }).count(), 0, `the line of No. ${AP_CLOSED.n} still has Mark read after the press`);
});

test("ask-phase-out: a closed line marked read leaves the Answered list on reload, and sits behind Show read items", async (t) => {
  const page = await open(t, { items: [AP_OPEN, AP_CLOSED], keepItems: true, clock: AP_NOW }); if (!page) return;
  // Setup: before Mark read, the line of No. 70 is in the Answered list.
  await mustHave(page, `#tier-answered #line-${AP_CLOSED.n}`, `the line of No. ${AP_CLOSED.n} in the Answered section before Mark read`);
  const press = await needButton(page.locator(`#tier-answered #line-${AP_CLOSED.n}`), new RegExp(`^Mark read: No\\. ${AP_CLOSED.n},`), `Mark read on the line of No. ${AP_CLOSED.n}`);
  await press.click();
  await apWaitUpdates(page, "items", 1);
  const ups = await apWrites(page, "items");
  assert.equal(ups.length, 1, `Mark read made ${ups.length} update writes on items, not one, so the reload below would not hold the mark`);
  await page.reload();
  await page.waitForFunction("state.items.length > 0");
  await mustHave(page, `#item-${TASK.id}`, `the open task ${TASK.id} after the reload`);
  // Scope first: the Answered section is drawn, with the read item behind its fold, so the absence below is real.
  await mustHave(page, "#tier-answered", "the Answered section after the reload");
  await mustHave(page, "#readItems", "the Show read items fold in the Answered section after the reload");
  assert.equal(await page.locator(`#tier-answered #line-${AP_CLOSED.n}`).count(), 0, `the line of No. ${AP_CLOSED.n}, marked read, is in the Answered list after a reload`);
  // Control: the line sits behind the fold, so it is moved, not lost.
  await page.click("#readItems");
  await mustHave(page, `#readItemList #line-${AP_CLOSED.n}`, `the line of No. ${AP_CLOSED.n} in the read items list after the reload`);
});

test("ask-phase-out: Mark read on a closed item's line leaves a Marked read. line in its place this visit, with Mark unread", async (t) => {
  const page = await open(t, { items: [AP_OPEN, AP_CLOSED], clock: AP_NOW }); if (!page) return;
  const press = await needButton(page.locator(`#tier-answered #line-${AP_CLOSED.n}`), new RegExp(`^Mark read: No\\. ${AP_CLOSED.n},`), `Mark read on the line of No. ${AP_CLOSED.n}`);
  await press.click();
  await apWaitUpdates(page, "items", 1);
  await mustHave(page, `#tier-answered article#line-${AP_CLOSED.n}.askc.dropped`, `the Marked read line of No. ${AP_CLOSED.n} in its place in the Answered section`);
  // One step reads the line, so a re-render between two reads cannot split them.
  const line = await page.evaluate(({ n, id }) => {
    const r = document.getElementById("line-" + n), sl = r ? r.querySelector(":scope > p.sline") : null;
    return { text: r ? r.textContent.replace(/\s+/g, " ").trim() : "", tabindex: r ? r.getAttribute("tabindex") : null, lineRole: sl ? sl.getAttribute("role") : null,
      restore: !!r && !!r.querySelector("#ires-" + id) };
  }, { n: AP_CLOSED.n, id: AP_CLOSED.id });
  assert.ok(line.text.startsWith(`Marked read. No. ${AP_CLOSED.n}, ${AP_CLOSED.title}`), `the Marked read line reads ${JSON.stringify(line.text)}`);
  assert.equal(line.restore, true, `the Marked read line of No. ${AP_CLOSED.n} has no Mark unread`);
  assert.equal(line.tabindex, "-1", `the Marked read line of No. ${AP_CLOSED.n} has tabindex ${line.tabindex}, not -1`);
  assert.equal(line.lineRole, "status", `the Marked read line's p.sline has role ${line.lineRole}, not status`);
});

test("ask-phase-out: Mark read on a closed item's line moves focus to its Marked read line, and the Answered sub-line says a marked line stays until the next load", async (t) => {
  const page = await open(t, { items: [AP_OPEN, AP_CLOSED], clock: AP_NOW }); if (!page) return;
  // Scope first: the press is the Mark read button of the line of No. 70, and no other element.
  const press = await needButton(page.locator(`#tier-answered #line-${AP_CLOSED.n}`), new RegExp(`^Mark read: No\\. ${AP_CLOSED.n},`), `Mark read on the line of No. ${AP_CLOSED.n}`);
  assert.equal(await press.evaluate((b, n) => { const l = b.closest("article"); return !!l && l.id === "line-" + n; }, AP_CLOSED.n), true, `the Mark read press is not on the line of No. ${AP_CLOSED.n}`);
  await press.click();
  await apWaitUpdates(page, "items", 1);
  await mustHave(page, `#tier-answered article#line-${AP_CLOSED.n}.askc.dropped`, `the Marked read line of No. ${AP_CLOSED.n} in its place`);
  const focused = await page.evaluate(() => (document.activeElement && document.activeElement.id) || "");
  assert.equal(focused, `line-${AP_CLOSED.n}`, `focus is on ${focused ? "#" + focused : "the body"} after Mark read, not on the Marked read line of No. ${AP_CLOSED.n}`);
  // Scope first: the sub-line sits in the Answered section's header.
  await mustHave(page, "#tier-answered header .rsub", "the sub-line of the Answered section");
  const sub = ((await page.locator("#tier-answered header .rsub").textContent()) || "").replace(/\s+/g, " ").trim();
  assert.ok(sub.includes("A line you mark read stays as Marked read until the next load."), `the Answered sub-line reads ${JSON.stringify(sub)}, not the line-stays sentence`);
});

test("ask-phase-out: a read item sits under Show read items, and Mark unread on it writes dismissed null with update", async (t) => {
  const page = await open(t, { items: [AP_OPEN, AP_READ], clock: AP_NOW }); if (!page) return;
  const fold = page.getByRole("button", { name: /Show \d+ read items?/ });
  assert.equal(await fold.count(), 1, `no Show read items fold: No. ${AP_READ.n}, a read item, is not behind one button`);
  await fold.click();
  await mustHave(page, "#readItemList", "read items list");
  const press = await needButton(page.locator("#readItemList"), new RegExp(`^Mark unread: No\\. ${AP_READ.n},`), `Mark unread on No. ${AP_READ.n} in the read items list`);
  await press.click();
  await apWaitUpdates(page, "items", 1);
  const ups = await apWrites(page, "items");
  assert.equal(ups.length, 1, `Mark unread made ${ups.length} update writes on items, not one`);
  assert.equal(ups[0].id, AP_READ.id, `Mark unread updated ${ups[0].id}, not ${AP_READ.id}`);
  assert.deepEqual(ups[0].body, { dismissed: null }, `Mark unread wrote ${JSON.stringify(ups[0].body)}, not dismissed: null`);
});

test("ask-phase-out: control: a closed item with no closed time counts as read, and it is nowhere on the page", async (t) => {
  const page = await open(t, { items: [AP_OPEN, AP_CLOSED_OLD] }); if (!page) return;
  assert.equal(await page.locator("#tier-answered").count(), 0, "the Answered section is drawn for a closed item with no closed time");
  assert.equal(await page.getByText("Old answer, closed before the ship time.").count(), 0, "the reply of a closed item with no closed time is on the page");
  assert.equal(await page.getByRole("button", { name: /^Mark read/ }).count(), 0, "a closed item with no closed time has a Mark read");
  assert.equal(await page.getByRole("button", { name: /Show \d+ read items?/ }).count(), 0, "a closed item with no closed time is behind Show read items");
});

test("ask-phase-out: the itemFields block names closed and dismissed, so the page draws them and the guard accepts their write", () => {
  const m = /<script type="application\/json" id="itemFields">([^<]*)<\/script>/.exec(html);
  assert.ok(m, "the page has no itemFields block");
  const fields = JSON.parse(m[1]);
  assert.ok(fields.includes("closed"), "itemFields has no closed: the page warns on a closed item's field, and the guard refuses its write");
  assert.ok(fields.includes("dismissed"), "itemFields has no dismissed: the page warns on a dismissed item's field, and the guard refuses its write");
});

test("ask-phase-out: an open item carrying closed and dismissed draws no unknown-field warning on its card", async (t) => {
  const page = await open(t, { items: [AP_OPEN, AP_FIELDS] }); if (!page) return;
  await mustHave(page, `#item-${AP_FIELDS.id}`, `card of No. ${AP_FIELDS.n}`);
  assert.equal(await card(page, AP_FIELDS).getByText(/^Which fields?$/).count(), 0, `card of No. ${AP_FIELDS.n} warns that a field is not drawn`);
});

test("ask-phase-out: control: an unknown field on an item still draws its Which field warning", async (t) => {
  const page = await open(t, { items: [AP_OPEN, AP_UNKNOWN] }); if (!page) return;
  await mustHave(page, `#item-${AP_UNKNOWN.id}`, `card of No. ${AP_UNKNOWN.n}`);
  assert.equal(await card(page, AP_UNKNOWN).getByText(/^Which fields?$/).count(), 1, `card of No. ${AP_UNKNOWN.n} does not warn about its unknown field`);
});

test("ask-phase-out: an answered item filed and not waiting shows one line in the Answered section, with its home", async (t) => {
  const page = await open(t, { items: [AP_OPEN, AP_FILED], answers: answerOf(AP_FILED), receipts: { [AP_FILED.id]: { read: "2026-10-26T02:00:00Z", filed: "2026-10-26T03:00:00Z" } } }); if (!page) return;
  await mustHave(page, `#tier-answered #line-${AP_FILED.n}`, `one line of No. ${AP_FILED.n} in the Answered section`);
  const said = ((await page.locator(`#tier-answered #line-${AP_FILED.n}`).textContent()) || "").replace(/\s+/g, " ");
  assert.ok(said.includes("c1"), `the line of No. ${AP_FILED.n} does not name its home c1: ${JSON.stringify(said)}`);
  await needButton(page.locator(`#tier-answered #line-${AP_FILED.n}`), new RegExp(`^Mark read: No\\. ${AP_FILED.n},`), `Mark read on the line of No. ${AP_FILED.n}`);
});

test("ask-phase-out: control: a filing-pending answer keeps today's card, with Change, no Mark read, and its rail chip in the Answered row", async (t) => {
  const page = await open(t, { items: [AP_OPEN, AP_PENDING], answers: answerOf(AP_PENDING) }); if (!page) return;
  await mustHave(page, `#tier-answered #item-${AP_PENDING.id}`, `card of No. ${AP_PENDING.n}, filing pending, in the Answered section`);
  const c = card(page, AP_PENDING);
  assert.match(((await c.locator(".ans").textContent()) || "").trim(), /^Filing pending/, `card of No. ${AP_PENDING.n} does not read Filing pending`);
  await needButton(c, /^Change$/, `Change on the card of No. ${AP_PENDING.n}`);
  assert.equal(await page.getByRole("button", { name: /^Mark read/ }).count(), 0, "a filing-pending answer has a Mark read");
  assert.ok((await railChipsIn(page, "answered")).includes(AP_PENDING.id), `the rail Answered row has no chip for No. ${AP_PENDING.n}`);
});

test("ask-phase-out: control: no Mark all control is drawn with a routed ask and a closed item", async (t) => {
  const page = await open(t, { items: [AP_OPEN, AP_CLOSED], dbExtra: { asks: { [AP_ASK.id]: AP_ASK } }, storage: RPL_SEEN, clock: AP_NOW }); if (!page) return;
  assert.equal(await page.getByRole("button", { name: /Mark all/i }).count(), 0, "a Mark all control is drawn");
});

// ---------------------------------------------------------------- ask-phase-out: a read item is counted where it is drawn (step ask-phase-out)
// A routed item is answered and filed, with no lane and no waits, so it draws as one line. Read at load (`dismissed` on its record), it sits
// behind Show read items. Taken to Change there, it draws as a card, and the Answered header and the rail count that card. A read item that a
// session gives a lane or waits is a card from the load on, and it is counted where it is drawn too.
const APR_FILED = { read: "2026-10-26T02:00:00Z", filed: "2026-10-26T03:00:00Z" };
const APR_ROUTED = mk("apr-routed", 77, { added: at(7), dismissed: "2026-11-09T16:00:00Z" });
const APR_LANE = mk("apr-lane", 78, { added: at(8), dismissed: "2026-11-09T16:00:00Z", lane: "ci-done-comment" });
const APR_WAITS = mk("apr-waits", 79, { added: at(9), dismissed: "2026-11-09T16:00:00Z", waits: { repo: "shivinate7/claude-settings", run: 123 } });
const APR_UNREAD = mk("apr-unread", 80, { added: at(10) });
// A page whose store holds one answered, filed item as `it`, with no read mark unless `it` carries one. The open TASK keeps open() waiting for a card.
const aprOpen = (t, it) => open(t, { items: [AP_OPEN], rawItems: { [it.id]: it }, answers: answerOf(it), receipts: { [it.id]: APR_FILED } });
const answeredHeader = async (page) => ((await page.locator("#tier-answered .rhead .ct").textContent()) || "").trim();
// The owner's way to a read item's card: Show read items, Show answer on its line, then Change on the answer.
async function changeReadItem(page, it) {
  await mustHave(page, "#readItems", `the Show read items fold that holds No. ${it.n}`);
  await page.click("#readItems");
  await mustHave(page, `#readItemList #lrow-${it.id}`, `the line of No. ${it.n} in Show read items`);
  await page.click(`#readItemList #lrow-${it.id}`);
  await mustHave(page, `#readItemList #line-${it.n} button.changebtn`, `Change on the answer of No. ${it.n}`);
  await page.click(`#readItemList #line-${it.n} button.changebtn`);
  await mustHave(page, `#tier-answered #item-${it.id}`, `the card of No. ${it.n} in the Answered section after Change`);
}

test("ask-phase-out: control: a routed item read at load counts 0 in the Answered header while it sits behind Show read items", async (t) => {
  const page = await aprOpen(t, APR_ROUTED); if (!page) return;
  await mustHave(page, "#readItems", `the Show read items fold that holds No. ${APR_ROUTED.n}`);
  const got = await answeredHeader(page);
  assert.equal(got, "0", `the Answered header counts ${got} while No. ${APR_ROUTED.n} is behind Show read items`);
});

test("ask-phase-out: control: an unread routed item counts 1 in the Answered header before and after Change", async (t) => {
  const page = await aprOpen(t, APR_UNREAD); if (!page) return;
  await mustHave(page, `#tier-answered #line-${APR_UNREAD.n}`, `the line of No. ${APR_UNREAD.n} in the Answered section`);
  const before = await answeredHeader(page);
  assert.equal(before, "1", `the Answered header counts ${before} before Change, with No. ${APR_UNREAD.n} drawn as a line`);
  await mustHave(page, `#tier-answered #lrow-${APR_UNREAD.id}`, `Show answer on the line of No. ${APR_UNREAD.n}`);
  await page.click(`#tier-answered #lrow-${APR_UNREAD.id}`);
  await mustHave(page, `#tier-answered #line-${APR_UNREAD.n} button.changebtn`, `Change on the answer of No. ${APR_UNREAD.n}`);
  await page.click(`#tier-answered #line-${APR_UNREAD.n} button.changebtn`);
  await mustHave(page, `#tier-answered #item-${APR_UNREAD.id}`, `the card of No. ${APR_UNREAD.n} after Change`);
  const after = await answeredHeader(page);
  assert.equal(after, "1", `the Answered header counts ${after} after Change, with No. ${APR_UNREAD.n} drawn as a card`);
});

test("ask-phase-out: a routed item read at load, taken to Change from Show read items, is counted in the Answered header", async (t) => {
  const page = await aprOpen(t, APR_ROUTED); if (!page) return;
  await changeReadItem(page, APR_ROUTED);
  const got = await answeredHeader(page);
  assert.equal(got, "1", `the Answered header counts ${got}, but No. ${APR_ROUTED.n} is drawn as a card in the section`);
});

test("ask-phase-out: the rail's Answered row counts the card of a read routed item taken to Change", async (t) => {
  const page = await aprOpen(t, APR_ROUTED); if (!page) return;
  await changeReadItem(page, APR_ROUTED);
  const row = page.locator('#rail a.ov-head[href="#tier-answered"]');
  await need(row, `the rail has no Answered row, but No. ${APR_ROUTED.n} is drawn as a card in the Answered section`);
  const got = (await row.locator(".ct").textContent()).trim();
  assert.equal(got, "1", `the rail's Answered row counts ${got}, but No. ${APR_ROUTED.n} is drawn as a card`);
});

test("ask-phase-out: a read item that a session gives a lane is counted in the Answered header where it is drawn", async (t) => {
  const page = await aprOpen(t, APR_LANE); if (!page) return;
  await mustHave(page, `#tier-answered #item-${APR_LANE.id}`, `the card of No. ${APR_LANE.n} in the Answered section`);
  const got = await answeredHeader(page);
  assert.equal(got, "1", `the Answered header counts ${got}, but No. ${APR_LANE.n} is drawn as a card in the section`);
});

test("ask-phase-out: a read item that a session gives waits is counted in the Answered header where it is drawn", async (t) => {
  const page = await aprOpen(t, APR_WAITS); if (!page) return;
  await mustHave(page, `#tier-answered #item-${APR_WAITS.id}`, `the card of No. ${APR_WAITS.n} in the Answered section`);
  const got = await answeredHeader(page);
  assert.equal(got, "1", `the Answered header counts ${got}, but No. ${APR_WAITS.n} is drawn as a card in the section`);
});

// ---------------------------------------------------------------- ask-phase-out: the line head, the read list's Mark unread, the rail's order
test("ask-phase-out: Mark unread in the read asks list is quiet, as it is in the read items list", async (t) => {
  const page = await open(t, { items: [AP_OPEN, AP_READ], dbExtra: { asks: { [DIS_KEEP.id]: DIS_KEEP, [DIS_HIDDEN.id]: DIS_HIDDEN } }, storage: RPL_NEW, clock: AP_NOW }); if (!page) return;
  await shownBox(page, DIS_KEEP.text, DIS_SHOWN);
  await mustHave(page, "#askDismissed", "Show read asks unfold");
  await page.click("#askDismissed");
  await mustHave(page, `ol#askDList #res-${DIS_HIDDEN.id}`, "Mark unread in the read asks list");
  const askCls = await page.locator(`ol#askDList #res-${DIS_HIDDEN.id}`).getAttribute("class");
  await mustHave(page, "#readItems", "Show read items unfold");
  await page.click("#readItems");
  await mustHave(page, `#ires-${AP_READ.id}`, "Mark unread in the read items list");
  const itemCls = await page.locator(`#ires-${AP_READ.id}`).getAttribute("class");
  assert.match(itemCls, /\bquiet\b/, "the read items list does not draw Mark unread quiet, so it is no reference: " + itemCls);
  assert.doesNotMatch(askCls, /\balt\b/, "Mark unread in the read asks list is the loud bordered press: " + askCls);
  assert.match(askCls, /\bquiet\b/, "Mark unread in the read asks list is not quiet: " + askCls);
});

for (const width of [768, 1280]) {
  test(`ask-phase-out: a long closed title at ${width} px is cut with an ellipsis, on one row with its number and home`, async (t) => {
    const page = await open(t, { items: [AP_OPEN, AP_LONG], viewport: { width, height: 900 }, clock: AP_NOW }); if (!page) return;
    await mustHave(page, "#line-77 .fhead", "the head of the long-title line");
    await mustHave(page, "#line-77 .fno", "the number of the long-title line");
    await mustHave(page, "#line-77 .ftext", "the title of the long-title line");
    await mustHave(page, "#line-77 .hometag", "the home tag of the long-title line");
    const g = await page.evaluate(() => {
      const q = (s) => document.querySelector("#line-77 " + s), box = (e) => e.getBoundingClientRect();
      const no = q(".fno"), tx = q(".ftext"), pill = q(".hometag"), head = q(".fhead");
      // A centre, not a top: the title and the home tag differ in height, so on one row their tops differ.
      const centre = (e) => { const b = box(e); return b.top + b.height / 2; };
      return {
        overflow: getComputedStyle(tx).textOverflow, cut: tx.scrollWidth > tx.clientWidth,
        centres: [centre(no), centre(tx), centre(pill)],
        right: box(pill).right, headRight: box(head).right, headH: box(head).height,
        line: parseFloat(getComputedStyle(tx).lineHeight) || 22,
      };
    });
    assert.equal(g.overflow, "ellipsis", "the long title has text-overflow " + g.overflow + ", not ellipsis");
    assert.equal(g.cut, true, "the long title is not cut: it fits its box");
    assert.ok(Math.max(...g.centres) - Math.min(...g.centres) < 3, "the number, the title and the home are not on one row: centres " + g.centres.map((c) => c.toFixed(1)).join(", "));
    assert.ok(g.headH < g.line * 1.6, "the head is " + g.headH + "px tall, more than one text row");
    assert.ok(g.right <= g.headRight + 0.5, "the home pill leaves the head");
  });
}

// The home pill is how a line shows its routing, and a gap shows as "No home named" (notes section 2). So its text stays whole at
// tablet and desktop width, beside a long title. The room is the pill's box less its side padding. The text is read as a range,
// because a cut text keeps its full width in the layout. No. 77 has a long title and no home, so it shows the gap. No. 79 has a long title,
// a New reply and a home, so it is the pill that must stay whole beside a long title. Each row's cause is its own line in the message.
test("ask-phase-out: the home pill of a line keeps its whole text at 768 and 1280 px, beside a long title", async (t) => {
  const causes = [];
  for (const width of [768, 1280]) {
    const at = `at ${width} px`;
    const page = await open(t, { items: [AP_OPEN, AP_LONG, AP_CLOSED, AP_LONG_HOME], storage: RPL_NEW, viewport: { width, height: 900 }, clock: AP_NOW }); if (!page) return;
    await mustHave(page, `#line-${AP_CLOSED.n} .hometag`, `the home pill of No. ${AP_CLOSED.n} ${at}`);
    await mustHave(page, `#line-${AP_LONG.n} .hometag`, `the home pill of No. ${AP_LONG.n} ${at}`);
    // The scope comes first: the New reply mark and the home pill of the long-title row with a home are drawn before they are measured.
    await mustHave(page, `#line-${AP_LONG_HOME.n} .fhead .newmark`, `the New reply mark of No. ${AP_LONG_HOME.n} ${at}`);
    await mustHave(page, `#line-${AP_LONG_HOME.n} .hometag`, `the home pill of No. ${AP_LONG_HOME.n} ${at}`);
    for (const n of [AP_CLOSED.n, AP_LONG.n, AP_LONG_HOME.n]) {
      const p = await page.evaluate((sel) => {
        const pill = document.querySelector(sel), cs = getComputedStyle(pill), range = document.createRange();
        range.selectNodeContents(pill.lastChild);
        return { scroll: pill.scrollWidth, client: pill.clientWidth, text: range.getBoundingClientRect().width, room: pill.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) };
      }, `#line-${n} .hometag`);
      if (p.scroll > p.client) causes.push(`${at}: the home pill of No. ${n} is cut: it scrolls ${p.scroll} px in a box ${p.client} px wide`);
      if (p.text > p.room + 0.5) causes.push(`${at}: the text of the home pill of No. ${n} is cut: the text is ${p.text.toFixed(1)} px wide, the room is ${p.room} px`);
    }
    await page.close();
  }
  assert.equal(causes.length, 0, "the home pill of a line is cut beside a long title:\n" + causes.join("\n"));
});

// Below 701 px the head of a line wraps (page.html, the 701px rule). From 701 px it is one row, so the list runs to 701 px, the first one-row
// width. At each width the case checks that, with the New reply mark drawn, the head's children stay inside the head, the title keeps 60 px,
// and the home pill does not cover Show answer. Each width's cause is its own line in the message, so one width's failure does not hide the others.
test("ask-phase-out: at 521 to 701 px a long title beside the New reply mark keeps its head's children inside the head, a 60 px title and a home clear of Show answer", async (t) => {
  const row = AP_LONG_HOME;
  const causes = [];
  for (const width of [521, 600, 640, 650, 700, 701]) {
    const at = `at ${width} px`;
    const page = await open(t, { items: [AP_OPEN, row], storage: RPL_NEW, viewport: { width, height: 900 }, clock: AP_NOW }); if (!page) return;
    // The scope comes first: the mark, the head's parts and Show answer are drawn before any of them is measured.
    await mustHave(page, `#line-${row.n} .fhead .newmark`, `the New reply mark on No. ${row.n} ${at}`);
    assert.equal((await page.textContent(`#line-${row.n} .fhead .newmark`)).trim(), "New reply", `the mark on No. ${row.n} ${at} does not read New reply`);
    await mustHave(page, `#line-${row.n} .fhead .ftext`, `the title of No. ${row.n} ${at}`);
    await mustHave(page, `#line-${row.n} .fhead .hometag`, `the home pill of No. ${row.n} ${at}`);
    await mustHave(page, `#line-${row.n} .fgo`, `Show answer on No. ${row.n} ${at}`);
    const goText = await page.textContent(`#line-${row.n} .fgo`);
    assert.match(goText, /Show answer/, `the control on No. ${row.n} ${at} is not Show answer: ${JSON.stringify(goText)}`);
    const g = await page.evaluate((n) => {
      const q = (s) => document.querySelector(`#line-${n} ${s}`);
      const r = (e) => { const b = e.getBoundingClientRect(); return { left: b.left, right: b.right, top: b.top, bottom: b.bottom, width: b.width }; };
      const head = q(".fhead");
      return { head: r(head), kids: [...head.children].map((k) => [k.className, r(k)]), title: r(q(".ftext")), pill: r(q(".hometag")), go: r(q(".fgo")) };
    }, row.n);
    assert.ok(g.go.width > 1, `Show answer on No. ${row.n} ${at} is ${g.go.width.toFixed(1)} px wide, so it is clipped and not drawn`);
    const spill = g.kids.filter(([, b]) => b.right > g.head.right + 0.5).map(([c, b]) => `${c.split(" ")[0]} ends ${(b.right - g.head.right).toFixed(1)} px past the head`);
    if (spill.length) causes.push(`${at}: a child of the head ends past its right edge: ${spill.join(", ")}`);
    if (g.title.width < 60) causes.push(`${at}: the title is ${g.title.width.toFixed(1)} px wide, under 60 px`);
    const ox = Math.min(g.pill.right, g.go.right) - Math.max(g.pill.left, g.go.left), oy = Math.min(g.pill.bottom, g.go.bottom) - Math.max(g.pill.top, g.go.top);
    if (ox > 0 && oy > 0) causes.push(`${at}: the home pill covers Show answer by ${ox.toFixed(1)} px`);
    await page.close();
  }
  assert.equal(causes.length, 0, "the head of a line with the New reply mark does not fit its row:\n" + causes.join("\n"));
});

test("ask-phase-out: the rail's Answered row follows the Answered section's order, newest answer first", async (t) => {
  const sent = { item: TASK.id, n: 28, at: "2026-10-26T01:00:00Z", done: true, note: "" };
  const page = await open(t, { items: [DECISION, TASK, AP_CLOSED, AP_NEWER], answers: { [TASK.id]: sent }, clock: AP_NOW }); if (!page) return;
  await mustHave(page, "#line-78", "the newer closed line");
  await mustHave(page, "#tier-answered", "the Answered section");
  await mustHave(page, '#rail a.ov-head[href="#tier-answered"]', "the Answered row of the rail");
  const r = await page.evaluate(() => {
    const sec = [...document.querySelectorAll('#tier-answered [id^="line-"], #tier-answered [id^="item-"]')].map((e) => e.id.startsWith("line-") ? +e.id.slice(5) : e.id);
    const head = document.querySelector('#rail a.ov-head[href="#tier-answered"]');
    const rail = [...head.parentElement.querySelectorAll(".nchip .no")].map((e) => +e.textContent);
    return { sec, rail };
  });
  const secN = r.sec.map((x) => (x === "item-" + TASK.id ? TASK.n : x));
  assert.deepEqual(secN, [AP_NEWER.n, AP_CLOSED.n, TASK.n], "the Answered section is not newest first: " + JSON.stringify(secN));
  assert.deepEqual(r.rail, secN, "the rail's Answered row " + JSON.stringify(r.rail) + " is not in the section's order " + JSON.stringify(secN));
});

// ---------------------------------------------------------------- answered-lines-age-out: a closed line ages out to read (step answered-lines-age-out)
// Ruling: a closed item stays one line in Answered until its closed time is older than the age, a top-level `const LINE_AGE_H`
// (a number of hours) in page.html. Past the age it reads as read at load, so it sits behind Show N read items, as a line read at
// load does. A reply later than the close brings it back, however old the close. The page writes nothing for it: no set, no
// update, no delete, and no session writes dismissed. Every time here is set from AP_NOW, the fixed clock above, so an age is exact.
const agoIso = (ms) => new Date(Date.parse(AP_NOW) - ms).toISOString();
const DAY_MS = 864e5, MIN_MS = 6e4;
// 30 days before the load is past any age the owner picks.
const agedLine = (id, n, over = {}) => mk(id, n, { status: "closed", closed: agoIso(30 * DAY_MS), home: "step:answered-lines-age-out", reply: "Filed as step answered-lines-age-out.", ...over });
const AGE_AGED = agedLine("age-aged", 80);
// Closed a minute before the load: well inside any age.
const AGE_YOUNG = mk("age-young", 81, { status: "closed", closed: agoIso(MIN_MS), home: "step:answered-lines-age-out", reply: "Filed a minute before the load." });
// Closed 30 days before the load and replied an hour after that: the reply is later than the close, so the line stays.
const AGE_REPLIED = agedLine("age-replied", 82, { replied: agoIso(30 * DAY_MS - 36e5) });

test("answered-lines-age-out: a closed line older than the age leaves Answered for Show read items; a younger line and a line with a later reply stay, and the page writes nothing", async (t) => {
  const page = await open(t, { items: [AP_OPEN, AGE_AGED, AGE_YOUNG, AGE_REPLIED], clock: AP_NOW }); if (!page) return;
  // Scope first: the two lines that must draw are in Answered, so the absence of the aged line below means something.
  await mustHave(page, `#tier-answered #line-${AGE_YOUNG.n}`, `the younger line of No. ${AGE_YOUNG.n} in Answered`);
  await mustHave(page, `#tier-answered #line-${AGE_REPLIED.n}`, `the line of No. ${AGE_REPLIED.n}, replied after it closed, in Answered`);
  await frameWait(page, 3);
  assert.deepEqual(await apBad(page, "items"), [], "the page set or deleted an item at load");
  assert.deepEqual(await apWrites(page, "items"), [], "the page updated an item at load, with no press");
  assert.equal(await page.locator(`#tier-answered #line-${AGE_AGED.n}`).count(), 0, `the line of No. ${AGE_AGED.n}, closed 30 days before the load, still draws in Answered`);
  await mustHave(page, "#readItems", "the Show read items fold, which holds the aged line");
  await page.click("#readItems");
  await mustHave(page, `#readItemList #line-${AGE_AGED.n}`, `the aged line of No. ${AGE_AGED.n} in the read items list`);
});

test("answered-lines-age-out: twelve aged lines sit behind Show 12 read items, and none draws in Answered", async (t) => {
  const FULL = Array.from({ length: 12 }, (_, i) => agedLine("age-full-" + i, 100 + i));
  const page = await open(t, { items: [AP_OPEN, ...FULL], clock: AP_NOW }); if (!page) return;
  // Scope first: the Answered section is drawn, with the fold that holds the twelve lines.
  await mustHave(page, "#tier-answered", "the Answered section, which holds the aged lines behind its fold");
  assert.equal(await page.locator('#tier-answered article[id^="line-"]').count(), 0, "twelve aged lines still draw as lines in Answered");
  await mustHave(page, "#tier-answered p.allread", "the All read. line, since no line is left in Answered");
  await mustHave(page, "#readItems", "the Show read items fold for the twelve aged lines");
  const foldWords = ((await page.locator("#readItems").textContent()) || "").replace(/\s+/g, " ");
  assert.ok(foldWords.includes("Show 12 read items"), `the fold reads ${JSON.stringify(foldWords)}, not Show 12 read items`);
  await page.click("#readItems");
  assert.equal(await page.locator('#readItemList article[id^="line-"]').count(), 12, "the read items list does not hold all twelve aged lines");
});

test("answered-lines-age-out: a line a minute under the age draws in Answered, and one a minute over it sits behind Show read items", async (t) => {
  // The first page holds a line 30 days old. Code with no age-out fails here by that line, never by a missing constant; the edge is read only after it.
  const first = await open(t, { items: [AP_OPEN, AGE_AGED], clock: AP_NOW }); if (!first) return;
  await mustHave(first, "#tier-answered", "the Answered section of the first page");
  assert.equal(await first.locator(`#tier-answered #line-${AGE_AGED.n}`).count(), 0, `the line of No. ${AGE_AGED.n}, closed 30 days before the load, still draws in Answered`);
  const ageH = await first.evaluate(() => (typeof LINE_AGE_H === "number" ? LINE_AGE_H : null));
  assert.equal(typeof ageH, "number", "page.html has no top-level number LINE_AGE_H, the one age constant");
  const UNDER = mk("age-under", 83, { status: "closed", closed: agoIso(ageH * 36e5 - MIN_MS), home: "step:answered-lines-age-out", reply: "Closed a minute under the age." });
  const OVER = mk("age-over", 84, { status: "closed", closed: agoIso(ageH * 36e5 + MIN_MS), home: "step:answered-lines-age-out", reply: "Closed a minute over the age." });
  const page = await open(t, { items: [AP_OPEN, UNDER, OVER], clock: AP_NOW }); if (!page) return;
  await mustHave(page, "#tier-answered", "the Answered section of the edge page");
  await mustHave(page, `#tier-answered #line-${UNDER.n}`, `the line of No. ${UNDER.n}, a minute under the age, in Answered`);
  assert.equal(await page.locator(`#tier-answered #line-${OVER.n}`).count(), 0, `the line of No. ${OVER.n}, a minute over the age, still draws in Answered`);
  await mustHave(page, "#readItems", "the Show read items fold, which holds the line a minute over the age");
  await page.click("#readItems");
  await mustHave(page, `#readItemList #line-${OVER.n}`, `the line of No. ${OVER.n} in the read items list`);
});

test("answered-lines-age-out: a line Mark unread wrote (dismissed null) is the owner's mark, never aged out: it draws in Answered at the next load, with Mark read", async (t) => {
  const page = await open(t, { items: [AP_OPEN, AGE_AGED], keepItems: true, clock: AP_NOW }); if (!page) return;
  await mustHave(page, "#readItems", "Show read items fold, which holds the aged line before Mark unread");
  await page.click("#readItems");
  const unread = await needButton(page.locator("#readItemList"), new RegExp(`^Mark unread: No\\. ${AGE_AGED.n},`), `Mark unread on the aged line of No. ${AGE_AGED.n}`);
  const before = (await apWrites(page, "items")).length;
  await unread.click();
  await apWaitUpdates(page, "items", before + 1);
  const ups = (await apWrites(page, "items")).slice(before);
  assert.equal(ups.length, 1, `Mark unread made ${ups.length} update writes on items, not one, so the reload below would not hold the mark`);
  assert.deepEqual(ups[0].body, { dismissed: null }, `Mark unread wrote ${JSON.stringify(ups[0].body)}, not dismissed: null`);
  await page.reload();
  await page.waitForFunction("state.items.length > 0");
  await mustHave(page, `#item-${AP_OPEN.id}`, `the open task ${AP_OPEN.id} after the reload`);
  await mustHave(page, "#tier-answered", "the Answered section after the reload");
  await mustHave(page, `#tier-answered #line-${AGE_AGED.n}`, `line of No. ${AGE_AGED.n}, marked unread, in Answered after the reload`);
  await needButton(page.locator(`#tier-answered #line-${AGE_AGED.n}`), new RegExp(`^Mark read: No\\. ${AGE_AGED.n},`), `Mark read on the line of No. ${AGE_AGED.n}`);
});

test("answered-lines-age-out: the read items list is newest first by max(read, closed), so an aged line sorts by when it closed", async (t) => {
  // OLDER has the higher No., so a sort by No. alone puts it first and gets it wrong. DISMISSED was read 30 days before the load, after it closed.
  const OLDER = agedLine("age-order-old", 85, { closed: agoIso(31 * DAY_MS) });
  const NEWER = agedLine("age-order-new", 86, { closed: agoIso(29 * DAY_MS) });
  const DISMISSED = mk("age-order-read", 87, { status: "closed", closed: agoIso(31 * DAY_MS), dismissed: agoIso(30 * DAY_MS), home: "step:answered-lines-age-out", reply: "Read by the owner." });
  const page = await open(t, { items: [AP_OPEN, OLDER, NEWER, DISMISSED], clock: AP_NOW }); if (!page) return;
  await mustHave(page, "#readItems", "Show read items fold, which holds the three read lines");
  await page.click("#readItems");
  await mustHave(page, "#readItemList", "read items list");
  const label = await page.getAttribute("#readItemList", "aria-label");
  assert.match(label || "", /newest first/, `the read items list is labelled ${JSON.stringify(label)}, not newest first`);
  const order = await page.locator('#readItemList article[id^="line-"]').evaluateAll((els) => els.map((e) => e.id));
  assert.deepEqual(order, [`line-${NEWER.n}`, `line-${DISMISSED.n}`, `line-${OLDER.n}`], `the read items list is ${JSON.stringify(order)}, not newest by max(read, closed)`);
});

// ---------------------------------------------------------------- the ask stack: Add to list, one Send, one Undo for the batch

// The reach line of the ask row that holds the text, or "" when no row holds it. Reads the page, never waits.
const reachOf = (page, text) => page.evaluate(([sel, t]) => { const li = [...document.querySelectorAll(sel)].find((c) => c.textContent.includes(t)); const s = li && li.querySelector(".astate"); return s ? s.textContent.trim() : ""; }, [ASK.ask, text]);

test("Add to list stacks asks in typed order, past three, and nothing reaches the store until Send", async (t) => {
  const page = await open(t); if (!page) return;
  await mustHave(page, ASK.box, "Ask box");
  await mustHave(page, ASK.add, "Add to list button");
  assert.equal(await page.locator(ASK.add).isDisabled(), true, "Add to list is on with the box empty");
  // Twelve asks, past the design's three: the stack has no cap, and each row keeps its place in typed order.
  const words = Array.from({ length: 12 }, (_, i) => `Stacked ask number ${i + 1}`);
  for (const w of words) await addToList(page, w);
  assert.equal(await page.inputValue(ASK.box), "", "Add to list left the words in the box");
  assert.deepEqual(await stackWords(page), words, "the stack is not the 12 asks in typed order");
  const writes = (await askWrites(page)).length;
  assert.equal(writes, 0, `Add to list wrote ${writes} asks records before Send`);
});

test("Edit keeps a stacked ask's place and number, Remove keeps its place, and Send writes the edited and kept asks only", async (t) => {
  const page = await open(t); if (!page) return;
  for (const w of ["Edit me first", "Remove me second", "Keep me third"]) await addToList(page, w);
  assert.deepEqual(await stackWords(page), ["Edit me first", "Remove me second", "Keep me third"], "the stack is not the three asks in typed order");
  // Edit opens the row in place under its number. Done closes it with the new words, and no row moves.
  await mustHaveNamed(page, "Edit ask 1", "Edit control on ask 1");
  await page.getByRole("button", { name: "Edit ask 1", exact: true }).click();
  await page.getByRole("textbox", { name: "Ask 1", exact: true }).fill("Edited first");
  await page.locator(ASK.rows).nth(0).getByRole("button", { name: "Done", exact: true }).click();
  assert.deepEqual(await stackWords(page), ["Edited first", "Remove me second", "Keep me third"], "Edit did not keep ask 1 in its place");
  // Remove keeps the row where it was, marked as removed.
  await mustHaveNamed(page, "Remove ask 2", "Remove control on ask 2");
  await page.getByRole("button", { name: "Remove ask 2", exact: true }).click();
  assert.match(await page.locator(ASK.rows).nth(1).textContent(), /Removed: .*Remove me second/, "Remove did not mark ask 2 as removed in its place");
  // Send writes what is left, and never the removed ask: the store is the proof.
  assert.equal(await page.locator(ASK.send).isDisabled(), false, "Send is off with two asks left in the stack");
  await page.click(ASK.send);
  await waitAskWrites(page, 2);
  const sent = (await askWrites(page)).map((b) => b.text);
  assert.deepEqual(sent, ["Edited first", "Keep me third"], "Send wrote " + JSON.stringify(sent) + ", not the edited and kept asks");
});

test("the stack survives a reload: stacked asks show under Not sent yet again, and the box stays empty", async (t) => {
  const page = await open(t); if (!page) return;
  await addToList(page, "Survives the reload, first");
  await addToList(page, "Survives the reload, second");
  assert.equal((await stackWords(page)).length, 2, "the stack did not hold both asks before the reload");
  await page.reload();
  await page.waitForFunction("state.items.length > 0");
  await page.waitForSelector(`#item-${DECISION.id}`);
  await page.waitForFunction((sel) => document.querySelectorAll(sel).length > 0, ASK.rows, { timeout: 3000 }).catch(() => {});
  await shownBox(page, "Not sent yet");
  const after = await stackWords(page);
  assert.deepEqual(after, ["Survives the reload, first", "Survives the reload, second"], "after a reload the stack shows " + JSON.stringify(after));
  assert.equal(await page.inputValue(ASK.box), "", "after a reload the box holds words that were only stacked");
  assert.equal((await askWrites(page)).length, 0, "the stack reached the store on reload");
});

test("Send writes every stacked ask and the typed box, each with one shared at", async (t) => {
  const page = await open(t); if (!page) return;
  await addToList(page, "Batch ask one");
  await addToList(page, "Batch ask two");
  await page.fill(ASK.box, "Batch ask three, typed");
  assert.equal(await page.locator(ASK.send).isDisabled(), false, "Send is off with two asks stacked and one typed");
  await page.click(ASK.send);
  await waitAskWrites(page, 3);
  const sets = await askWrites(page);
  assert.equal(sets.length, 3, `Send wrote ${sets.length} asks records, not the 3 in the list and the box`);
  assert.deepEqual(sets.map((b) => b.text), ["Batch ask one", "Batch ask two", "Batch ask three, typed"], "Send wrote the wrong asks");
  const ats = new Set(sets.map((b) => b.at));
  assert.equal(ats.size, 1, `the asks of one Send carry ${ats.size} times, not one shared at`);
});

test("one 8-second Undo takes back the send and puts the ask back in the list, and the box keeps what was typed", async (t) => {
  const page = await open(t); if (!page) return;
  await sendTyped(page, "Undo batch ask");
  await mustHave(page, ASK.undo, "Undo control");
  // Typing inside the window keeps the count on view: 7 s in, about one second is left.
  await jump(page, 7000);
  await page.fill(ASK.box, "Typed after the send");
  await mustHave(page, ASK.undo, "Undo control 7 s in");
  await page.click(ASK.undo);
  await waitAskDeletes(page, 1);
  const [written] = await askWrites(page);
  const deleted = await page.evaluate(() => window.__log.filter((l) => l[0] === "delete" && l[1] === "asks").map((l) => l[2]));
  assert.deepEqual(deleted, [written.id], "Undo deleted " + JSON.stringify(deleted) + ", not " + written.id);
  const box = await page.inputValue(ASK.box);
  assert.equal(box, "Typed after the send", "Undo changed the box: " + JSON.stringify(box));
  assert.deepEqual(await stackWords(page), ["Undo batch ask"], "Undo did not put the ask back in the list");
});

test("Send stays off while the Undo count runs, so a second send cannot end the first Undo", async (t) => {
  const page = await open(t); if (!page) return;
  await sendTyped(page, "First ask, in the Undo window");
  await page.fill(ASK.box, "Second ask, typed while Undo counts");
  // Scope first: the Undo is still counting, so the Send button is the subject.
  await mustHave(page, ASK.undo, "Undo control while typing");
  assert.equal(await page.locator(ASK.send).isDisabled(), true, "Send is on while Undo counts, so a second send would end the first Undo");
  await jump(page, 9000);
  await page.fill(ASK.box, "Second ask, after the window");
  assert.equal(await page.locator(ASK.send).isDisabled(), false, "Send stays off after the Undo count has ended");
  assert.equal((await askWrites(page)).length, 1, "a second Send wrote while Undo counted");
});

test("each sent ask shows its own reach, and the told fact shows once on the line under the buttons, not on each row", async (t) => {
  const page = await open(t, { meta: { writer: WRITER } }); if (!page) return;
  await sendTyped(page, "Reach ask one");
  await jump(page, 9000);
  await sendTyped(page, "Reach ask two");
  const [one] = await askWrites(page);
  // A session reads the first ask. Nothing reads the second.
  await page.evaluate((body) => window.__putDoc("asks", body.id, { ...body, owner: "lane status-fold", read: "2026-11-03T17:44:00Z" }), one);
  await page.waitForFunction(([sel, w]) => [...document.querySelectorAll(sel)].some((c) => c.textContent.includes(w) && c.textContent.includes("Read by")), [ASK.ask, "Reach ask one"], { timeout: 3000 }).catch(() => {});
  assert.match(await reachOf(page, "Reach ask one"), /^Read by lane status-fold /, "the first ask does not show its own reach");
  assert.equal(await reachOf(page, "Reach ask two"), `Waiting for ${WRITER} to read it.`, "the second ask does not show its own reach");
  const line = await page.evaluate(() => { const l = document.querySelector("#asks .sline"); return l ? l.textContent.trim() : ""; });
  assert.match(line, /A wake was sent\./, "the told fact is not on the line under the buttons: " + JSON.stringify(line));
  const repeats = await page.evaluate((sel) => [...document.querySelectorAll(sel)].filter((c) => /wake was sent|No session was told/.test(c.textContent)).length, ASK.ask);
  assert.equal(repeats, 0, `${repeats} ask row(s) repeat the told fact`);
});

test("a failed ask stays in the list with its words and Copy ask, and the other asks are sent", async (t) => {
  const page = await open(t, { failSetText: "Denied ask two" }); if (!page) return;
  await addToList(page, "Saved ask one");
  await addToList(page, "Denied ask two");
  await page.fill(ASK.box, "Saved ask three");
  await page.click(ASK.send);
  await waitAskWrites(page, 2);
  await page.waitForFunction((sel) => [...document.querySelectorAll(sel)].some((li) => li.textContent.includes("Not saved")), ASK.rows, { timeout: 3000 }).catch(() => {});
  const sets = (await askWrites(page)).map((b) => b.text);
  assert.deepEqual(sets, ["Saved ask one", "Saved ask three"], "the other asks were not all sent: " + JSON.stringify(sets));
  const failed = page.locator(ASK.rows, { hasText: "Denied ask two" });
  assert.equal(await failed.count(), 1, "the failed ask is not in the list");
  assert.match(await failed.textContent(), /Not saved \([\w-]*denied\)/, "the failed row does not say it was not saved, and why");
  assert.equal(await failed.getByRole("button", { name: "Copy ask", exact: true }).count(), 1, "the failed row has no Copy ask");
});

test("asks made in one batch get ids that sort in the order they were made, so the last-typed ask sorts on top", async (t) => {
  const page = await open(t); if (!page) return;
  // A batch shares one at, so the list breaks the tie by id, newest id first (askAll). The ids must rise in the order they are made.
  const made = await page.evaluate(() => (typeof askId === "function" ? Array.from({ length: 50 }, () => askId()) : null));
  assert.ok(made, "the page has no askId(), so the ids of a batch cannot be checked");
  const bad = made.findIndex((id, i) => i > 0 && !(made[i - 1] < id));
  assert.equal(bad, -1, bad < 0 ? "" : `ask ${made[bad]} was made after ${made[bad - 1]} but does not sort after it`);
});

// ---------------------------------------------------------------- stacked asks across a reload, Undo races, the Undo window and the hint words

// A reload as a viewer sees it. The stub keeps the asks, and the page keeps its stack and draft. The hold is disarmed here, as the init script arms it on every load.
async function reopen(page) {
  await page.reload();
  await page.waitForFunction("state.items.length > 0");
  await page.waitForSelector(`#item-${DECISION.id}`);
  await page.waitForFunction(() => document.getElementById("askList").children.length > 0, null, { timeout: 3000 }).catch(() => {});
  await page.evaluate(() => { window.__hold = null; });
}
// Ends on the condition that a Send has ended: the stack head no longer reads Sending. No clock is read.
const sendDone = (page) => page.waitForFunction(() => { const s = document.getElementById("askStack"); return !s || !s.textContent.includes("Sending"); }, null, { timeout: 3000 }).catch(() => {});
const askDeletes = (page) => page.evaluate(() => window.__log.filter((l) => l[0] === "delete" && l[1] === "asks").map((l) => l[2]));
// The words of each ask the store holds, as the store kept them through a reload.
const storedTexts = (page) => page.evaluate(() => Object.values(JSON.parse(localStorage.getItem("__stub.asks") || "{}")).map((a) => a.text));
const hintText = async (page) => (await page.textContent("#askHint")).trim();
// The words of the line under the buttons, without its Undo button, whose count is not part of the words.
const lineWords = (page) => page.evaluate(() => { const l = document.querySelector("#asks .sline"); if (!l) return ""; const c = l.cloneNode(true); c.querySelectorAll("button").forEach((b) => b.remove()); return c.textContent.trim(); });
// True once a stacked ask that Send could not save shows its row with Not saved. False when no row says so.
const failedRowShown = (page) => page.waitForFunction(() => [...document.querySelectorAll("ol.stack > li")].some((li) => li.textContent.includes("Not saved")), null, { timeout: 3000 }).then(() => true, () => false);
const MID = ["Mid-send ask one", "Mid-send ask two", "Mid-send ask three"];

test("a reload in the middle of a Send does not bring back the ask already written", async (t) => {
  // The second write waits at the hold, so ask one is written and the batch is not done.
  const page = await open(t, { hold: { set: 1 } }); if (!page) return;
  for (const w of MID) await addToList(page, w);
  await page.click(ASK.send);
  await page.waitForFunction(() => window.__held >= 1);
  await reopen(page);
  assert.deepEqual(await stackWords(page), MID.slice(1), "after a reload the stack shows " + JSON.stringify(await stackWords(page)));
});

test("the Send after a reload writes an ask already written once, not twice", async (t) => {
  const page = await open(t, { hold: { set: 1 } }); if (!page) return;
  for (const w of MID) await addToList(page, w);
  await page.click(ASK.send);
  await page.waitForFunction(() => window.__held >= 1);
  await reopen(page);
  assert.equal(await page.locator(ASK.send).isDisabled(), false, "Send is off after the reload, with asks still in the stack");
  await page.click(ASK.send);
  await sendDone(page);
  const texts = await storedTexts(page), copies = texts.filter((x) => x === MID[0]).length;
  assert.equal(copies, 1, `"${MID[0]}" is in the store ${copies} times after the second Send`);
});

test("a reload in the middle of Undo keeps every ask, in the store or in the stack", async (t) => {
  // The first delete lands, and the second waits at the hold: the reload falls between two deletes.
  const page = await open(t, { hold: { delete: 1 } }); if (!page) return;
  const words = ["Mid-undo ask one", "Mid-undo ask two", "Mid-undo ask three"];
  for (const w of words) await addToList(page, w);
  await page.click(ASK.send);
  await waitAskWrites(page, 3);
  await sendDone(page);
  await mustHave(page, ASK.undo, "Undo control");
  await page.click(ASK.undo);
  await page.waitForFunction(() => window.__held >= 1);
  await reopen(page);
  const stored = await storedTexts(page), stack = await stackWords(page);
  const lost = words.filter((w) => !stored.includes(w) && !stack.includes(w));
  assert.deepEqual(lost, [], `a reload in the middle of Undo lost ${JSON.stringify(lost)}`);
});

test("a Send is refused while Undo's delete is still awaited, even after the 8 s window has passed", async (t) => {
  const page = await open(t, { hold: { delete: 0 } }); if (!page) return;
  await sendTyped(page, "Race ask one");
  await mustHave(page, ASK.undo, "Undo control");
  await page.click(ASK.undo);
  await page.waitForFunction(() => window.__held >= 1); // the delete waits at the hold
  await jump(page, 9000); // the 8 s window passes while the delete waits
  await page.fill(ASK.box, "Race ask two, typed");
  assert.equal(await page.locator(ASK.send).isDisabled(), true, "Send is on while Undo's delete is still awaited");
  // Ctrl+Enter reaches sendAsk by its own route, so the refusal must hold there too. Read straight after the press: nothing waits on a clock.
  const before = (await askWrites(page)).length;
  await page.focus(ASK.box);
  await page.keyboard.press("Control+Enter");
  const after = (await askWrites(page)).length;
  assert.equal(after, before, `Ctrl+Enter wrote ${after - before} ask(s) while Undo's delete was still awaited`);
  await page.evaluate(() => window.__release());
  await waitAskDeletes(page, 1);
  assert.equal(await page.inputValue(ASK.box), "Race ask two, typed", "Undo changed the typed words");
  assert.ok((await stackWords(page)).includes("Race ask one"), "Undo did not put its ask back in the list once its delete ended");
});

test("Undo deletes nothing after its 8 s window has passed, though a delete was already waiting", async (t) => {
  const page = await open(t, { hold: { delete: 0 } }); if (!page) return;
  const words = ["Window ask one", "Window ask two", "Window ask three"];
  for (const w of words) await addToList(page, w);
  await page.click(ASK.send);
  await waitAskWrites(page, 3);
  await sendDone(page);
  await mustHave(page, ASK.undo, "Undo control");
  await page.click(ASK.undo);
  await page.waitForFunction(() => window.__held >= 1); // the first delete starts inside the window, and waits
  await jump(page, 9000); // the window passes before that delete lands
  await page.evaluate(() => window.__release());
  await waitAskDeletes(page, 1);
  const dels = await askDeletes(page);
  assert.equal(dels.length, 1, `Undo deleted ${dels.length} asks; only the delete that started inside the 8 s window may go`);
});

test("Undo with three asks sent takes back all three and puts them back in the list in order", async (t) => {
  const page = await open(t); if (!page) return;
  const words = ["Three undo one", "Three undo two", "Three undo three"];
  for (const w of words) await addToList(page, w);
  await page.click(ASK.send);
  await waitAskWrites(page, 3);
  await sendDone(page);
  const sent = (await askWrites(page)).map((b) => b.id);
  assert.equal(sent.length, 3, `Send wrote ${sent.length} asks, not 3`);
  await mustHave(page, ASK.undo, "Undo control");
  await page.click(ASK.undo);
  await waitAskDeletes(page, 3);
  assert.deepEqual((await askDeletes(page)).sort(), sent.slice().sort(), "Undo did not delete all three asks");
  assert.deepEqual(await stackWords(page), words, "Undo did not put all three back in the list, in order");
});

test("asks sent in one batch share one at, and the list shows the last-typed ask on top", async (t) => {
  const page = await open(t); if (!page) return;
  const words = ["Tie ask one", "Tie ask two", "Tie ask three"];
  for (const w of words) await addToList(page, w);
  await page.click(ASK.send);
  await waitAskWrites(page, 3);
  await sendDone(page);
  const ats = new Set((await askWrites(page)).map((b) => b.at));
  assert.equal(ats.size, 1, `the batch carries ${ats.size} times, so the list must break a tie by id`);
  const shown = await page.locator("#askList .atext").allInnerTexts();
  assert.deepEqual(shown, [...words].reverse(), "the list does not show the last-typed ask on top: " + JSON.stringify(shown));
});

test("Ctrl+Enter while the Undo count runs writes no ask", async (t) => {
  const page = await open(t); if (!page) return;
  await sendTyped(page, "Counting ask one");
  await mustHave(page, ASK.undo, "Undo control");
  await page.fill(ASK.box, "Ctrl+Enter ask two");
  await page.focus(ASK.box);
  await page.keyboard.press("Control+Enter");
  const writes = (await askWrites(page)).length;
  assert.equal(writes, 1, `Ctrl+Enter wrote ${writes - 1} ask(s) while the Undo count ran`);
});

test("a Send of two asks tells Claude once, with the batch comment words", async (t) => {
  const page = await open(t, { meta: { writer: WRITER } }); if (!page) return;
  for (const w of ["Batch wake one", "Batch wake two"]) await addToList(page, w);
  await page.click(ASK.send);
  await page.waitForFunction(() => window.__sent.length >= 1, null, { timeout: 3000 }).catch(() => {});
  const sent = await page.evaluate(() => window.__sent.map((s) => s.text));
  assert.equal(sent.length, 1, `the batch told Claude ${sent.length} times, not once`);
  assert.match(sent[0], new RegExp(`^Asked on the waiting page\\. Writer: ${WRITER}\\. 2 asks: ask-[0-9a-z]+: Batch wake one; ask-[0-9a-z]+: Batch wake two\\.$`), "the batch comment words changed: " + JSON.stringify(sent[0]));
});

test("a failed Undo says which asks stay sent, with the code", async (t) => {
  const page = await open(t, { failDeleteIn: "asks" }); if (!page) return;
  await sendTyped(page, "Undo that fails");
  await mustHave(page, ASK.undo, "Undo control");
  await page.click(ASK.undo);
  assert.ok(await lineHas(page, "Undo failed"), "the line under the buttons does not say Undo failed");
  const line = await lineWords(page);
  assert.match(line, /^Undo failed \(denied\)\. 1 ask stays sent\.$/, "the Undo-failed line changed: " + JSON.stringify(line));
});

test("when every ask fails to save, the line says so and Copy ask shows in the slot", async (t) => {
  const page = await open(t, { failSet: true }); if (!page) return;
  for (const w of ["All fail one", "All fail two"]) await addToList(page, w);
  await page.click(ASK.send);
  assert.ok(await lineHas(page, "Not saved"), "the line under the buttons does not say Not saved");
  const line = await lineWords(page);
  assert.match(line, /^Not saved \(denied\)\. Your 2 asks are kept in the list: copy them and paste them in chat\.$/, "the all-failed line changed: " + JSON.stringify(line));
  assert.equal(await page.locator("#askSlot #askCopy").count(), 1, "the all-failed state shows no Copy ask in the slot");
});

test("with no store, Add to list is off, as Send is", async (t) => {
  const page = await open(t, { noStore: true }); if (!page) return;
  await mustHave(page, ASK.box, "Ask box");
  await page.fill(ASK.box, "Typed box words");
  assert.equal(await page.locator(ASK.send).isDisabled(), true, "Send ask is on with no store");
  assert.equal(await page.locator(ASK.add).isDisabled(), true, "Add to list is on with no store, where an ask could never be saved");
});

test("with no store, Copy ask copies only the box, not the asks stacked on this view", async (t) => {
  const page = await open(t, { noStore: true, storage: { "waiting.askStack": JSON.stringify(["Kept stack words"]) } }); if (!page) return;
  await mustHave(page, ASK.box, "Ask box");
  await page.fill(ASK.box, "Typed box words");
  await page.evaluate(() => { Object.defineProperty(navigator, "clipboard", { value: { writeText: async (s) => { window.__copied = s; } } }); });
  await mustHave(page, "#askSlot #askCopy", "Copy ask button");
  await page.click("#askSlot #askCopy");
  const copied = await page.evaluate(() => window.__copied);
  assert.equal(copied, "Typed box words", "Copy ask copied " + JSON.stringify(copied) + ", not only the box");
});

test("the clipboard fallback for Copy answers says the text is in the box, not below", async (t) => {
  const page = await open(t, { noStore: true }); if (!page) return;
  await page.evaluate(() => { Object.defineProperty(navigator, "clipboard", { value: { writeText: async () => { throw new Error("refused"); } } }); });
  await mustHave(page, "#copy", "Copy answers button");
  await page.click("#copy");
  await page.waitForFunction(() => !document.getElementById("copyBox").hidden, null, { timeout: 3000 }).catch(() => {});
  const note = (await page.textContent("#barStatus")).trim();
  assert.doesNotMatch(note, /below/, "the clipboard note says the text is below, but the box is not below it: " + JSON.stringify(note));
  assert.match(note, /box/, "the clipboard note does not point at the read-only box: " + JSON.stringify(note));
});

test("the clipboard fallback note for Copy answers does not sit beside the read-only copy box", async (t) => {
  const page = await open(t, { noStore: true }); if (!page) return;
  await page.evaluate(() => { Object.defineProperty(navigator, "clipboard", { value: { writeText: async () => { throw new Error("refused"); } } }); });
  await mustHave(page, "#copy", "Copy answers button");
  await page.click("#copy");
  await page.waitForFunction(() => !document.getElementById("copyBox").hidden, null, { timeout: 3000 }).catch(() => {});
  assert.equal(await page.evaluate(() => !document.getElementById("copyBox").hidden), true, "Copy answers did not show the read-only copy box");
  const rows = await page.evaluate(() => { const s = document.getElementById("barStatus").getBoundingClientRect(), c = document.getElementById("copyBox").getBoundingClientRect(); return { status: [s.top, s.bottom], box: [c.top, c.bottom] }; });
  const sameRow = rows.status[0] < rows.box[1] && rows.box[0] < rows.status[1];
  assert.equal(sameRow, false, "the clipboard note shares a row with the read-only copy box: " + JSON.stringify(rows));
});

test("Undo counting with one ask not saved and the box empty: the hint says Send ask tries it again, not Add to list", async (t) => {
  const page = await open(t, { failSetText: "Denied ask two" }); if (!page) return;
  await addToList(page, "Saved ask one");
  await addToList(page, "Denied ask two");
  await page.click(ASK.send);
  assert.equal(await failedRowShown(page), true, "the ask that Send could not save shows no Not saved row");
  await mustHave(page, ASK.undo, "Undo control");
  assert.equal(await page.locator(ASK.add).isDisabled(), true, "Add to list is on with the box empty");
  const hint = await hintText(page);
  assert.doesNotMatch(hint, /Add to list stays on/, "the hint says Add to list stays on while Add is off: " + JSON.stringify(hint));
  assert.match(hint, /Send ask tries the one not saved again when the Undo count ends\./, "the hint does not say Send ask tries the one not saved again: " + JSON.stringify(hint));
});

test("Undo counting with the box empty: the hint gives the counting words, with no Add to list clause", async (t) => {
  const page = await open(t); if (!page) return;
  await sendTyped(page, "Counting ask, box empty");
  await mustHave(page, ASK.undo, "Undo control");
  assert.equal(await page.inputValue(ASK.box), "", "the box is not empty");
  const hint = await hintText(page);
  assert.doesNotMatch(hint, /Add to list|once you type/, "the hint offers Add to list or says once you type, while Add is off and Send waits: " + JSON.stringify(hint));
  assert.match(hint, /Send turns on when the Undo count ends\./, "the hint is not the counting hint: " + JSON.stringify(hint));
});

// Storage refused: every write to the browser's storage throws, as in a window that blocks it. Set once the page has loaded.
const refuseStorage = (page) => page.evaluate(() => { const no = () => { throw new Error("denied"); }; Storage.prototype.setItem = no; Storage.prototype.removeItem = no; });
// Sends the asks, then presses Undo with its first delete held. The 8 s window passes while that delete waits, so it lands
// after the window and the asks after it are late. Returns the page once the late line shows.
async function lateUndo(t, texts) {
  const page = await open(t, { hold: { delete: 0 } }); if (!page) return null;
  for (const w of texts) await addToList(page, w);
  await page.click(ASK.send);
  await waitAskWrites(page, texts.length);
  await sendDone(page);
  await mustHave(page, ASK.undo, "Undo control");
  await page.click(ASK.undo);
  await page.waitForFunction(() => window.__held >= 1);
  await jump(page, 9000);
  await page.evaluate(() => window.__release());
  await waitAskDeletes(page, 1);
  await lineHas(page, "Too late to undo");
  return page;
}

test("the late line pins its words for one ask and for more than one", async (t) => {
  const one = await lateUndo(t, ["Late ask one", "Late ask two"]); if (!one) return;
  const oneLine = await lineWords(one);
  const many = await lateUndo(t, ["Late ask three", "Late ask four", "Late ask five"]); if (!many) return;
  const manyLine = await lineWords(many);
  assert.equal(oneLine, "Too late to undo 1 ask. It stays sent.", "the one-ask late line is " + JSON.stringify(oneLine));
  assert.equal(manyLine, "Too late to undo 2 asks. They stay sent.", "the plural late line is " + JSON.stringify(manyLine));
});

test("after the late line, focus is on the ask text box, as after an Undo that finishes", async (t) => {
  const page = await lateUndo(t, ["Focus ask one", "Focus ask two"]); if (!page) return;
  const focused = await page.evaluate(() => (document.activeElement && document.activeElement.id) || "");
  assert.equal(focused, "askText", "after the late line focus is on " + JSON.stringify(focused) + ", not on the ask box");
});

test("while Undo's deletes run, the line says Taking back and the Undo control has the spent look, with no count", async (t) => {
  const page = await open(t, { hold: { delete: 0 } }); if (!page) return;
  for (const w of ["Taking ask one", "Taking ask two", "Taking ask three"]) await addToList(page, w);
  await page.click(ASK.send);
  await waitAskWrites(page, 3);
  await sendDone(page);
  await mustHave(page, ASK.undo, "Undo control");
  await page.click(ASK.undo);
  await page.waitForFunction(() => window.__held >= 1); // the first delete waits at the hold, inside the window
  await lineHas(page, "Taking back");
  const line = await lineWords(page);
  assert.match(line, /^Taking back 3 asks…/, "the line while Undo's deletes run is " + JSON.stringify(line));
  const undo = await page.evaluate(() => { const b = document.getElementById("askUndo"); if (!b) return { gone: true }; return { gone: false, spent: b.classList.contains("spent"), visibility: getComputedStyle(b).visibility }; });
  assert.ok(undo.gone || (undo.spent && undo.visibility === "hidden"), "Undo is not off with no count while its deletes run: " + JSON.stringify(undo));
  await page.evaluate(() => window.__release());
});

test("while Undo's delete runs after its 8 s window, the hint says Send turns on when Undo is done", async (t) => {
  const page = await open(t, { hold: { delete: 0 } }); if (!page) return;
  await sendTyped(page, "Done hint ask");
  await mustHave(page, ASK.undo, "Undo control");
  await page.click(ASK.undo);
  await page.waitForFunction(() => window.__held >= 1);
  await jump(page, 9000); // the window passes while the delete waits
  await page.waitForFunction(() => document.getElementById("askHint").textContent.includes("Undo is done"), null, { timeout: 3000 }).catch(() => {});
  const hint = await hintText(page);
  assert.match(hint, /Send turns on when Undo is done\./, "the hint while Undo runs after its window is " + JSON.stringify(hint));
  await page.evaluate(() => window.__release());
});

test("with storage refused, a Send that empties the list and the box shows no hint about a lost list", async (t) => {
  const page = await open(t); if (!page) return;
  await refuseStorage(page);
  await sendTyped(page, "Refused storage ask");
  await mustHave(page, ASK.undo, "Undo control");
  assert.equal(await page.locator(ASK.rows).count(), 0, "the list has rows after Send, so this is not the empty case");
  assert.equal(await page.inputValue(ASK.box), "", "the box is not empty after Send");
  const hint = await hintText(page);
  assert.doesNotMatch(hint, /would not keep your list/, "the hint says a reload would lose the list, with the list and the box empty: " + JSON.stringify(hint));
});

test("with storage refused and an ask in the list, Copy ask shows in the slot", async (t) => {
  const page = await open(t); if (!page) return;
  await refuseStorage(page);
  await addToList(page, "Refused list ask");
  await mustHave(page, ASK.rows, "the list row");
  assert.match(await hintText(page), /would not keep your list/, "precondition: the page did not find the list unkeepable");
  assert.equal(await page.locator("#askSlot #askCopy").count(), 1, "Copy ask is not in the slot while a reload would lose the list");
});

for (const width of [360, 390]) {
  test(`with Copy answers shown at ${width} wide, the bar status sits on its own full-width row`, async (t) => {
    const page = await open(t, { noStore: true, viewport: { width, height: 800 } }); if (!page) return;
    await stubClipboard(page, true);
    await mustHave(page, "#copy", "Copy answers button");
    await page.click("#copy");
    await page.waitForFunction(() => !document.getElementById("copyBox").hidden, null, { timeout: 3000 }).catch(() => {});
    assert.equal(await page.evaluate(() => !document.getElementById("copyBox").hidden), true, "Copy answers did not show the copy box");
    const m = await page.evaluate(() => ({ bar: document.querySelector("#bar > .in").getBoundingClientRect().width, status: document.getElementById("barStatus").getBoundingClientRect().width }));
    assert.ok(m.status >= m.bar * 0.9, `the bar status is ${Math.round(m.status)} px wide in a ${Math.round(m.bar)} px bar; it should sit on its own full-width row`);
  });
}

// ---------------------------------------------------------------- focus after Undo, the hint in the window, the bar status width

// Undo's first delete waits at the hold, so focus and the hint are read while Undo runs, inside its window.
test("after an Undo press by click or Enter, focus is on the ask box while its delete runs, never on the body", async (t) => {
  const lost = [];
  for (const how of ["click", "Enter"]) {
    const page = await open(t, { hold: { delete: 0 } }); if (!page) return;
    await sendTyped(page, "Focus after an Undo by " + how);
    await mustHave(page, ASK.undo, "Undo control");
    await page.focus(ASK.undo);
    // Scope first: the Undo button has focus before it is pressed.
    assert.equal(await page.evaluate(() => document.activeElement.id), "askUndo", `before the Undo ${how}, focus is not on Undo`);
    if (how === "click") await page.click(ASK.undo); else await page.keyboard.press("Enter");
    await page.waitForFunction(() => window.__held >= 1);
    const focused = await page.evaluate(() => document.activeElement.id || document.activeElement.tagName);
    if (focused !== "askText") lost.push(`${how} leaves focus on ${focused}`);
    await page.evaluate(() => window.__release());
  }
  assert.deepEqual(lost, [], "focus is not on the ask box after an Undo press: " + lost.join("; "));
});

test("when the Undo count ends while the Undo button has focus, focus moves to the ask box, not the body", async (t) => {
  const page = await open(t); if (!page) return;
  await sendTyped(page, "Focus when the count ends");
  await mustHave(page, ASK.undo, "Undo control");
  await page.focus(ASK.undo);
  // Scope first: Undo has focus while its count is still running.
  assert.equal(await page.evaluate(() => document.activeElement.id), "askUndo", "Undo does not have focus before the count ends");
  await jump(page, 9000); // the count ends; the page's one-second tick spends the button
  const spent = () => { const b = document.getElementById("askUndo"); return !!b && b.classList.contains("spent"); };
  await page.waitForFunction(spent, null, { timeout: 3000 }).catch(() => {});
  assert.equal(await page.evaluate(spent), true, "the Undo count ended but Undo is not spent");
  const focused = await page.evaluate(() => document.activeElement.id || document.activeElement.tagName);
  assert.equal(focused, "askText", `after the Undo count ends with Undo focused, focus is on ${focused}, not the ask box`);
});

test("after a failed Undo, focus is on the ask box, not the body", async (t) => {
  const page = await open(t, { failDelete: true }); if (!page) return;
  await sendTyped(page, "Focus after a failed Undo");
  await mustHave(page, ASK.undo, "Undo control");
  await page.focus(ASK.undo);
  // Scope first: Undo has focus when it is pressed and its delete fails.
  assert.equal(await page.evaluate(() => document.activeElement.id), "askUndo", "Undo does not have focus before it is pressed");
  await page.click(ASK.undo);
  assert.equal(await lineHas(page, "Undo failed"), true, "the failed Undo shows no Undo failed line");
  const focused = await page.evaluate(() => document.activeElement.id || document.activeElement.tagName);
  assert.equal(focused, "askText", `after a failed Undo focus is on ${focused}, not the ask box`);
});

test("while an in-window Undo's delete runs, the hint says Send turns on when Undo is done, not when the count ends", async (t) => {
  // The page's clock is fixed at LOAD_AT, so the Undo window cannot pass while the delete is held, however slow the runner.
  const page = await open(t, { hold: { delete: 0 }, clock: LOAD_AT }); if (!page) return;
  await sendTyped(page, "Hint inside the window");
  await mustHave(page, ASK.undo, "Undo control");
  await page.click(ASK.undo);
  await page.waitForFunction(() => window.__held >= 1);
  // Scope first: the window has not passed, so the Undo count is still running while the delete waits.
  assert.equal(await page.evaluate(() => undoLeft(askState.sent) > 0), true, "the Undo window has already passed, so this is not the in-window case");
  const hint = await hintText(page);
  assert.match(hint, /Send turns on when Undo is done\./, "the hint while an in-window Undo runs is " + JSON.stringify(hint));
  assert.doesNotMatch(hint, /Undo count ends/, "the hint says the Undo count ends while Undo is already running: " + JSON.stringify(hint));
  await page.evaluate(() => window.__release());
});

test("with Copy answers shown at 800 and 1280 wide, the bar status stays inline with its buttons, not on its own row", async (t) => {
  const ownRow = [];
  for (const width of [800, 1280]) {
    const page = await open(t, { noStore: true, viewport: { width, height: 800 } }); if (!page) return;
    await stubClipboard(page, true);
    await mustHave(page, "#copy", "Copy answers button");
    await page.click("#copy");
    await page.waitForFunction(() => !document.getElementById("copyBox").hidden, null, { timeout: 3000 }).catch(() => {});
    assert.equal(await page.evaluate(() => !document.getElementById("copyBox").hidden), true, `at ${width} wide, Copy answers did not show the copy box`);
    // Scope first: the status has words to lay out, so its row is measured.
    const r = await page.evaluate(() => { const s = document.getElementById("barStatus").getBoundingClientRect(), c = document.getElementById("copy").getBoundingClientRect(); return { status: [s.top, s.bottom], copy: [c.top, c.bottom] }; });
    assert.ok(r.status[1] > r.status[0], `at ${width} wide, the bar status has no text to lay out: ${JSON.stringify(r.status)}`);
    // Inline: the status and Copy answers share a row, so their vertical extents overlap.
    const shared = r.status[0] < r.copy[1] && r.copy[0] < r.status[1];
    if (!shared) ownRow.push(`${width} px: status ${JSON.stringify(r.status.map(Math.round))}, Copy answers ${JSON.stringify(r.copy.map(Math.round))}`);
  }
  assert.deepEqual(ownRow, [], "the bar status takes its own row at 800 or 1280 wide, where it should stay inline: " + ownRow.join("; "));
});

test("an edit still open when the page reloads comes back open, with the words typed in it", async (t) => {
  const page = await open(t); if (!page) return;
  await addToList(page, "Edit survives the reload");
  await mustHaveNamed(page, "Edit ask 1", "Edit control on ask 1");
  await page.getByRole("button", { name: "Edit ask 1", exact: true }).click();
  await page.getByRole("textbox", { name: "Ask 1", exact: true }).fill("Edit survives, changed");
  await reopen(page);
  const edit = page.getByRole("textbox", { name: "Ask 1", exact: true });
  assert.equal(await edit.count(), 1, "the edit left open did not come back after the reload");
  assert.equal(await edit.inputValue(), "Edit survives, changed", "the edit came back with other words");
});

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

// ---------------------------------------------------------------- the mockup draw width has one home
// FIT_W is the width a mockup is laid out at. A CSS rule or a comment that repeats the number goes stale when FIT_W moves.
const FIT_W_DECL = /const FIT_W = (\d+)/;
// A restatement is FIT_W's number as a width value: after width, min-width, max-width, minWidth or maxWidth and a colon or
// equals sign, or followed by the word wide. The width may be an attribute (width="390"), a dotted style property
// (el.style.width = "390px", el.style.maxWidth = "390px"), the second argument of setAttribute("width", 390), or any argument
// of calc(, min(, max( or clamp(, quoted or not, with one level of brackets inside it: min(calc(100% - 20px), 390px) counts. Strings, comments
// and templates are read as plain text, so a restatement counts wherever it stands. A count, a font weight, a height, a gap or
// a sibling number is not one: 3900, 1390, 0.390, a390, #390 (a hex colour), "390 units", gap: min(100%, 390px).
// A media or container condition is a breakpoint that CSS cannot read FIT_W in, so it is skipped.
const WIDTH_BEFORE = /(?:^|[\s;{(,"'.])(?:(?:min|max)-?)?width(?:["']?\s*[:=]\s*|["']\s*,\s*)(?:["']?(?:calc|min|max|clamp)\((?:[^();{}]|\([^();{}]*\))*)?["']?$/i, WIDE_AFTER = /^(?:px)?\s+wide\b/i, AT_RULE = /^\s*@(?:container|media)\b/;
function restatements(src, num) {
  const decl = FIT_W_DECL.exec(src), own = decl ? decl.index + decl[0].length - decl[1].length : -1;
  const lines = src.split("\n"), again = new RegExp(`(?<![\\w.#])${num}(?!\\d|\\.\\d)`, "g"), found = new Set();
  for (const m of src.matchAll(again)) {
    if (m.index === own) continue;
    const n = src.slice(0, m.index).split("\n").length, start = src.lastIndexOf("\n", m.index - 1) + 1;
    const width = WIDTH_BEFORE.test(src.slice(start, m.index)) || WIDE_AFTER.test(src.slice(m.index + num.length, m.index + num.length + 12));
    if (width && !AT_RULE.test(lines[n - 1])) found.add(n);
  }
  return [...found].map((n) => `line ${n}: ${lines[n - 1].trim().slice(0, 100)}`);
}

test("the mockup draw width is written once in the page, in FIT_W", () => {
  const decl = FIT_W_DECL.exec(html);
  assert.ok(decl, "page.html has no `const FIT_W = <number>` declaration");
  const found = restatements(html, decl[1]);
  assert.deepEqual(found, [], `page.html restates the draw width ${decl[1]} as a width value outside FIT_W:\n  ${found.join("\n  ")}\n`
    + "Remedy: if the number is the draw width, read FIT_W in its place. If it is another width that only equals FIT_W by chance, "
    + "the scan has no exception for it: tell the owner, and do not write the number another way.");
});

test("the restatement scan finds a width behind a comment opener in a string, in a template and after a lone quote, and skips other numbers", () => {
  const src = [
    "const FIT_W = 390;",
    "const u = 'style=\"width:390px\"';",
    'const c = "/* width: 390 */";',
    'const h = "# width=390";',
    "const t = `a",
    "b width: 390 c`;",
    "<p>Don't</p> 390 wide",
    "const other = 3900 + 1390 + 0.390 + 390.5 + a390 + #390;",
  ].join("\n");
  assert.deepEqual(restatements(src, "390"), [
    "line 2: const u = 'style=\"width:390px\"';", 'line 3: const c = "/* width: 390 */";', 'line 4: const h = "# width=390";', "line 6: b width: 390 c`;", "line 7: <p>Don't</p> 390 wide",
  ]);
});

test("the restatement scan finds a width written as an attribute, a style assignment, a setAttribute argument or a calc value", () => {
  const src = [
    "const FIT_W = 390;",
    '<img width="390" alt="">',
    "<svg width='390'></svg>",
    'el.style.width = "390px";',
    'el.setAttribute("width", 390);',
    "div { width: calc(390px); }",
  ].join("\n");
  assert.deepEqual(restatements(src, "390"), [
    'line 2: <img width="390" alt="">',
    "line 3: <svg width='390'></svg>",
    'line 4: el.style.width = "390px";',
    'line 5: el.setAttribute("width", 390);',
    "line 6: div { width: calc(390px); }",
  ]);
});

test("the restatement scan finds a width inside min(), max() or clamp(), quoted or not, and a camelCase maxWidth or minWidth", () => {
  const src = [
    "const FIT_W = 390;",
    "div { width: min(100%, 390px); }",
    "div { width: clamp(300px, 100%, 390px); }",
    "div { width: min(calc(100% - 20px), 390px); }",
    "div { min-width: max(390px, 50%); }",
    'el.style.maxWidth = "390px";',
    'el.style.minWidth = "390px";',
    "const s = { maxWidth: 390 };",
    'el.style.width = "min(100%, 390px)";',
  ].join("\n");
  assert.deepEqual(restatements(src, "390"), [
    "line 2: div { width: min(100%, 390px); }",
    "line 3: div { width: clamp(300px, 100%, 390px); }",
    "line 4: div { width: min(calc(100% - 20px), 390px); }",
    "line 5: div { min-width: max(390px, 50%); }",
    'line 6: el.style.maxWidth = "390px";',
    'line 7: el.style.minWidth = "390px";',
    "line 8: const s = { maxWidth: 390 };",
    'line 9: el.style.width = "min(100%, 390px)";',
  ], "the scan misses a width inside min(), max(), clamp(), or a camelCase maxWidth or minWidth, or one whose function value is quoted");
});

test("the restatement scan skips a number equal to FIT_W that is not a width value: a count, a font weight, a breakpoint, a height, a gap, a max-height", () => {
  const src = [
    "const FIT_W = 390;",
    "const rows = 390; // the count of rows",
    '<td>390 units</td> <i style="font-weight: 390"></i>',
    "@container (min-width: 390px) { .pk { gap: 16px } }",
    'el.style.height = "390px";',
    'el.setAttribute("height", 390);',
    "div { gap: min(100%, 390px); padding: clamp(8px, 2vw, 390px); }",
    "div { width: min(100%, 300px); padding: 390px; }",
    'el.style.maxHeight = "390px";',
    "const widthRatio = 390; const s = { maxHeight: 390 };",
  ].join("\n");
  assert.deepEqual(restatements(src, "390"), []);
});

test("a mockup frame is laid out at the width FIT_W holds", async (t) => {
  const narrow = Number(FIT_W_DECL.exec(html)[1]) - 30;
  const pageHtml = html.replace(FIT_W_DECL, `const FIT_W = ${narrow}`);
  assert.notEqual(pageHtml, html, "FIT_W was not rewritten");
  const it = picItem("fit-width-q", 71);
  const page = await open(t, { items: [it], designData: PICS, pageHtml }); if (!page) return;
  const widths = await card(page, it).locator(".opic iframe.dframe").evaluateAll((fs) => fs.map((f) => getComputedStyle(f).width));
  assert.deepEqual(widths, LOOK_OPTS.map(() => `${narrow}px`), "a frame keeps a width of its own, not FIT_W");
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
// The key of items/<key> is the item's id. The id field is optional and ignored, so a missing one or a differing one is no warning.

const { id: _noId, ...DECISION_NO_ID } = DECISION;
const warn = (page, key) => card(page, { id: key }).locator(".status.broken");

// The doc key is the item id (roadmap step page-item-id-check).
test("an item stored with no id field shows no warning, sorts by n, and is answered under its database key", async (t) => {
  const rawItems = { low: { ...DECISION, id: "low", n: 20 }, k29: { ...DECISION_NO_ID, n: 29 }, high: { ...DECISION, id: "high", n: 40 } };
  const page = await open(t, { items: [], rawItems }); if (!page) return;
  assert.equal(await card(page, { id: "k29" }).count(), 1, "no card for the item");
  assert.equal(await warn(page, "k29").count(), 0, "a warning shows for an item with no id field");
  assert.deepEqual(await cardsIn(page, "#tier-calm"), ["high", "k29", "low"], "the card is not sorted by n among its items");
  await choose(page, { id: "k29" }, "b");
  await send(page);
  await written(page);
  const log = await page.evaluate(() => window.__log.filter((l) => l[0] === "set"));
  assert.equal(log.length, 1);
  assert.equal(log[0][2], "k29", "the answer key");
  assert.equal(log[0][3].item, "k29");
  assert.equal(log[0][3].choice, "b");
});

test("an item whose id field differs from its key shows no warning, sorts by n, and is answered under the key", async (t) => {
  const rawItems = { low: { ...DECISION, id: "low", n: 20 }, k30: { ...DECISION, id: "other-id", n: 30 }, high: { ...DECISION, id: "high", n: 40 } };
  const page = await open(t, { items: [], rawItems }); if (!page) return;
  assert.equal(await card(page, { id: "k30" }).count(), 1, "no card for the item");
  assert.equal(await warn(page, "k30").count(), 0, "a warning shows for an id field that differs from the key");
  assert.deepEqual(await cardsIn(page, "#tier-calm"), ["high", "k30", "low"], "the card is not sorted by n among its items");
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
  await takePick(page, { ...DECISION, id: "good" });
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
  assert.equal(await c.locator(".nonebtn").isDisabled(), true);
  assert.equal(await c.locator(".opts input").first().isDisabled(), true);
  assert.equal(await page.locator("#n-dup-keys").isDisabled(), true, "the note box of a blocked card is open");
  await takePick(page, { ...DECISION, id: "good" });
  assert.equal(await page.evaluate(() => answerLine()), "43 a");
});

test("an item with a duplicate option key is blocked from Send and Copy, and names the key", async (t) => {
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

// The preview's button closes over the design it drew. A rename that lands later leaves that closure with the old label, so the click
// falls to the slug-and-state match (openShown). With two designs of that slug and state, the viewer opens on neither.
const renameDesign = (page, itemId, from, to) => page.evaluate(([id, a, b]) => {
  state.items = state.items.map((x) => (x.id === id ? { ...x, designs: x.designs.map((d) => (d.label === a ? { ...d, label: b } : d)) } : x));
  render();
}, [itemId, from, to]);
const previewLabel = (page, it) => card(page, it).locator(".dprev .dbar > span").first().textContent();
test("a shown preview whose design was renamed opens nothing when another design shares its slug and state", async (t) => {
  const it = mk("st-twin", 76, { designs: [{ slug: "s-a", label: "Sibling", state: "default" }, { slug: "s-a", label: "Early", state: "default" }] });
  const page = await open(t, { items: [it], designData: STATE_DATA }); if (!page) return;
  await card(page, it).locator('.dprev button[aria-label="Next design"]').click();
  assert.equal(await previewLabel(page, it), "Early", "the preview does not show Early before the rename");
  await renameDesign(page, it.id, "Early", "Renamed");
  assert.equal(await previewLabel(page, it), "Early", "the preview redrew after the rename, so the click takes the exact match, not the fallback");
  await card(page, it).locator(".dprev .dbar button").last().click();
  const title = await page.locator("#dTitle").textContent();
  assert.equal(await page.locator("#dsheet").isHidden(), true, `Open this state opened the viewer on "${title}", the first of two designs with the shown slug and state`);
});
test("a shown preview whose design was renamed still opens its one design of the same slug and state", async (t) => {
  const it = looseItem();
  const page = await open(t, { items: [it], designData: STATE_DATA }); if (!page) return;
  await renameDesign(page, it.id, "Early", "Early renamed");
  await card(page, it).locator(".dprev .dbar button").last().click();
  assert.equal(await page.locator("#dTitle").textContent(), "Early renamed, default", "Open this state did not open the one design of that slug and state");
});
test("a shown preview whose slug and state match no design opens nothing", async (t) => {
  const it = looseItem();
  const page = await open(t, { items: [it], designData: STATE_DATA }); if (!page) return;
  await page.evaluate((id) => { state.items = state.items.map((x) => (x.id === id ? { ...x, designs: x.designs.map((d) => (d.label === "Early" ? { ...d, slug: "s-z" } : d)) } : x)); render(); }, it.id);
  await card(page, it).locator(".dprev .dbar button").last().click();
  assert.equal(await page.locator("#dsheet").isHidden(), true, "Open this state opened the viewer with no design of the shown slug and state");
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

// The send cases (shiv, 15:06 CDT Oct 30, receipt-tightens-at-once). The visible band runs from the header's bottom edge to the top of the bar.
// On a Send, the anchor is the first card whose bottom is below the band's top, skipping a sent card whose top is above it. The anchor keeps its top,
// and the cards below it rise by what the sent cards drop.
const LEADS = [1, 2, 3].map((n) => mk("lead-" + n, n, { context: LONG }));
const HOLDS = [1, 2, 3].map((n) => mk("hold-" + n, n, { context: LONG, holds: "A lane waits." }));
// Scrolls so the card's top or bottom edge sits `offset` px below the band's top edge. A negative offset puts it above the band.
const placeRel = (page, it, edge, offset) => page.evaluate(([id, e, o]) => {
  const bt = document.querySelector(".hdr").getBoundingClientRect().bottom;
  const r = document.getElementById("item-" + id).getBoundingClientRect();
  window.scrollTo({ top: scrollY + r[e] - (bt + o), behavior: "instant" });
}, [it.id, edge, offset]);
// The page can reflow after its first frames, and scroll anchoring follows a reflow, so the card is placed again once the frames settle.
const settleAt = async (page, it, edge, offset) => { await frameWait(page, 3); await placeRel(page, it, edge, offset); await frameWait(page, 3); await placeRel(page, it, edge, offset); };
const cardMap = (page) => page.evaluate(() => Object.fromEntries([...document.querySelectorAll("article.card")].map((c) => { const r = c.getBoundingClientRect(); return [c.id, { id: c.id, top: r.top, bottom: r.bottom, h: r.height, receipt: !!c.querySelector(":scope > .receipt") }]; })));
const bandOf = (page) => page.evaluate(() => ({ top: document.querySelector(".hdr").getBoundingClientRect().bottom, bottom: document.getElementById("bar").getBoundingClientRect().top }));
// The anchor the rule picks for these sent cards, read before Send.
const anchorOf = (page, sent) => page.evaluate((ids) => {
  const bt = document.querySelector(".hdr").getBoundingClientRect().bottom;
  for (const c of document.querySelectorAll("article.card")) {
    const r = c.getBoundingClientRect();
    if (r.bottom <= bt) continue;
    if (ids.includes(c.id) && r.top < bt) continue;
    return c.id;
  }
  return null;
}, sent.map((it) => "item-" + it.id));
// The page lists a tier newest first, so a case whose cards sit in array order stamps each item's added day from its place: the first item is the newest.
const inArrayOrder = (items) => items.map((it, i) => ({ ...it, added: at(28 - i) }));
// Scroll anchoring stays off unless the case asks for it.
// sentMove names the SENT_MOVE value a case pins (see withSentMove); none keeps the page's own value.
const openSend = async (t, { items, width, height, scheme, anchored, sentMove, timers }) => {
  const page = await open(t, { items: inArrayOrder(items), scheme, timers, viewport: { width, height }, pageHtml: sentMove ? withSentMove(sentMove) : undefined });
  if (page && !anchored) await noAnchor(page);
  return page;
};
// Sends the cards, then reads the page as each receipt appears, once the Sent panel renders, and after two frames.
async function sendAndRead(page, sent) {
  const pre = await cardMap(page), band = await bandOf(page);
  await send(page);
  for (const it of sent) await card(page, it).locator(".receipt").waitFor();
  const atOnce = await cardMap(page);
  await page.locator("#sent .stamp").waitFor();
  await frameWait(page, 2);
  return { pre, band, atOnce, settled: await cardMap(page) };
}
const reads = (rd) => [["at once", rd.atOnce], ["after two frames", rd.settled]];
// The sent card drops its height, the anchor keeps its top, and the card below rises by the drop.
function checkRise(pre, post, when, sentIt, anchorIt, belowIt) {
  const S = "item-" + sentIt.id, A = "item-" + anchorIt.id, B = "item-" + belowIt.id;
  const drop = pre[S].h - post[S].h;
  assert.ok(drop >= 100, `${when}: the receipt kept its open height of ${pre[S].h}px; it is ${post[S].h}px`);
  assert.ok(Math.abs(post[A].top - pre[A].top) <= 1, `${when}: the anchor moved on Send: ${pre[A].top} to ${post[A].top}`);
  assert.ok(Math.abs(post[B].top - (pre[B].top - drop)) <= 1, `${when}: the card below did not rise by the drop of ${drop}px: ${pre[B].top} to ${post[B].top}`);
}

// A card sent with the card above it partly on screen: that card keeps its top, and the cards below rise.
async function sendBelowPartial(t, { width, scheme, anchored }) {
  // At 390 wide the sent card is taller than the phone's screen, so the viewport is taller to keep the card below on screen.
  const above = mk("above", 4), sent = mk("sent", 5), below = mk("below", 6);
  const page = await openSend(t, { items: [...LEADS, above, sent, below, ...FILLER], width, height: width === 390 ? 1000 : 800, scheme, anchored, sentMove: "stay" }); if (!page) return;
  await choose(page, sent, "a");
  await settleAt(page, above, "bottom", 30);
  assert.equal(await anchorOf(page, [sent]), "item-above", "fixture: the card above is not the anchor");
  const rd = await sendAndRead(page, [sent]);
  for (const [when, post] of reads(rd)) checkRise(rd.pre, post, when, sent, above, below);
}

// A card sent as the topmost card on screen, its top inside the band: its top stays, and the card below rises.
async function sendTopOfBand(t, { scheme }) {
  const sent = mk("sent", 4, { context: LONG }), below = mk("below", 5);
  const page = await openSend(t, { items: [...HOLDS, sent, below, ...FILLER], width: 1280, height: 800, scheme, anchored: false, sentMove: "stay" }); if (!page) return;
  await choose(page, sent, "a");
  await settleAt(page, sent, "top", 20);
  assert.equal(await anchorOf(page, [sent]), "item-sent", "fixture: the sent card is not the topmost card on screen");
  const rd = await sendAndRead(page, [sent]);
  for (const [when, post] of reads(rd)) checkRise(rd.pre, post, when, sent, sent, below);
}

// Two cards sent together: the first is wholly above the band, the second starts inside it. The second keeps its top, and the card below rises by the second's drop.
async function sendTwoOneAbove(t, { width, scheme }) {
  const wholly = mk("wholly-above", 4, { context: LONG }), visible = mk("visible", 5, { context: LONG }), below = mk("below", 6);
  const page = await openSend(t, { items: [...LEADS, wholly, visible, below, ...FILLER], width, height: 800, scheme, anchored: false, sentMove: "stay" }); if (!page) return;
  await choose(page, wholly, "a");
  await choose(page, visible, "b");
  await settleAt(page, wholly, "bottom", -4);
  assert.equal(await anchorOf(page, [wholly, visible]), "item-visible", "fixture: the second card is not the anchor");
  const rd = await sendAndRead(page, [wholly, visible]);
  const V = "item-visible", W = "item-wholly-above", B = "item-below";
  for (const [when, post] of reads(rd)) {
    const drop = rd.pre[V].h - post[V].h;
    assert.ok(rd.pre[W].h - post[W].h >= 100, `${when}: the card wholly above the band kept its open height: it is ${post[W].h}px`);
    assert.ok(drop >= 100, `${when}: the visible receipt kept its open height of ${rd.pre[V].h}px; it is ${post[V].h}px`);
    assert.ok(Math.abs(post[V].top - rd.pre[V].top) <= 1, `${when}: the visible card moved on Send: ${rd.pre[V].top} to ${post[V].top}`);
    assert.ok(Math.abs(post[B].top - (rd.pre[B].top - drop)) <= 1, `${when}: the card below did not rise by ${drop}px: ${rd.pre[B].top} to ${post[B].top}`);
  }
}

// A tall card at 390 wide, its top above the band and its bottom inside it: the card below keeps its top, and the receipt lands just above it.
async function sendTallOverBand(t, { scheme }) {
  const tall = mk("tall", 4, { context: LONG }), below = mk("below", 5);
  const page = await openSend(t, { items: [...LEADS, tall, below, ...FILLER], width: 390, height: 800, scheme, anchored: false, sentMove: "stay" }); if (!page) return;
  await choose(page, tall, "a");
  await settleAt(page, tall, "bottom", 60);
  assert.equal(await anchorOf(page, [tall]), "item-below", "fixture: the card below is not the anchor");
  const rd = await sendAndRead(page, [tall]);
  const T = "item-tall", N = "item-below";
  const gap = rd.pre[N].top - rd.pre[T].bottom;
  for (const [when, post] of reads(rd)) {
    assert.ok(rd.pre[T].h - post[T].h >= 100, `${when}: the receipt kept its open height of ${rd.pre[T].h}px; it is ${post[T].h}px`);
    assert.ok(Math.abs(post[N].top - rd.pre[N].top) <= 1, `${when}: the card below moved on Send: ${rd.pre[N].top} to ${post[N].top}`);
    assert.ok(Math.abs(post[T].bottom - (post[N].top - gap)) <= 1, `${when}: the receipt does not land just above the card below: ${post[T].bottom} against ${post[N].top - gap}`);
  }
}

// A card sent with the card below it starting under the bar: the sent card keeps its top, and the card below rises.
async function sendOverUnderBar(t, { scheme }) {
  const sent = mk("sent", 4, { context: LONG }), below = mk("under-bar", 5);
  const page = await openSend(t, { items: [...HOLDS, sent, below, ...FILLER], width: 1280, height: 800, scheme, anchored: false, sentMove: "stay" }); if (!page) return;
  await choose(page, sent, "a");
  await settleAt(page, sent, "top", 60);
  assert.equal(await anchorOf(page, [sent]), "item-sent", "fixture: the sent card is not the anchor");
  const rd = await sendAndRead(page, [sent]);
  assert.ok(rd.pre["item-under-bar"].top >= rd.band.bottom - 1, `fixture: the card below starts above the bar: ${rd.pre["item-under-bar"].top} against ${rd.band.bottom}`);
  for (const [when, post] of reads(rd)) checkRise(rd.pre, post, when, sent, sent, below);
}

// Under SENT_MOVE "sink" a Send takes the card out of its tier, so nothing on screen may jump. Positions are viewport tops: the page may
// scroll to keep its rail growth out of view, so the scroll position is not asserted. A card above the sent card keeps its viewport top,
// and the open card below takes the sent card's top, or, when the sent card is last in its tier, the cards above it hold still.
async function sinkSendInView(t, { width, anchored = false }) {
  const sent = mk("sink-sent", 4, { context: LONG }), below = mk("sink-below", 5, { context: LONG });
  const page = await openSend(t, { items: [...LEADS, sent, below, ...FILLER], width, height: 800, scheme: "light", anchored, sentMove: "sink" }); if (!page) return;
  await choose(page, sent, "a");
  await settleAt(page, sent, "top", 60);
  const rd = await sendAndRead(page, [sent]);
  const S = "item-sink-sent", B = "item-sink-below";
  assert.ok(rd.pre[S].top >= rd.band.top && rd.pre[S].top < rd.band.bottom, `fixture: the sent card is not in view before Send at ${rd.pre[S].top}`);
  const above = Object.keys(rd.pre).filter((id) => id !== S && rd.pre[id].top < rd.pre[S].top - 1);
  assert.ok(above.length >= 3, `fixture: ${above.length} cards sit above the sent card`);
  for (const [when, post] of reads(rd)) for (const id of above) assert.ok(Math.abs(post[id].top - rd.pre[id].top) <= 1, `${when}: ${id} moved on screen on Send: ${rd.pre[id].top} to ${post[id].top}`);
  const took = reads(rd).map(([when, post]) => `${when} ${post[B].top}`).join(", ");
  assert.ok(reads(rd).every(([, post]) => Math.abs(post[B].top - rd.pre[S].top) <= 2), `the open card below did not take the sent card's top ${rd.pre[S].top}: ${took}`);
}
async function sinkSendLastInTier(t, { width, anchored = false }) {
  const sent = mk("sink-last", 4, { context: LONG });
  // Nothing in a later tier: a stood pick there would go with the Send. The card is tall enough to scroll to the band.
  const page = await openSend(t, { items: [...HOLDS, ...LEADS, sent], width, height: 800, scheme: "light", anchored, sentMove: "sink" }); if (!page) return;
  await choose(page, sent, "a");
  await settleAt(page, sent, "top", 60);
  assert.equal(await sectionOf(page, sent), "tier-calm", "fixture: the sent card is not in the open tier");
  const rd = await sendAndRead(page, [sent]);
  const S = "item-sink-last";
  assert.ok(rd.pre[S].top >= rd.band.top && rd.pre[S].top < rd.band.bottom, `fixture: the sent card is not in view before Send at ${rd.pre[S].top}`);
  assert.equal(await sectionOf(page, sent), "tier-answered", `No. ${sent.n} did not move to the Answered section after its Send`);
  const above = Object.keys(rd.pre).filter((id) => id !== S && rd.pre[id].top < rd.pre[S].top - 1);
  assert.ok(above.length >= 3, `fixture: ${above.length} cards sit above the sent card`);
  for (const [when, post] of reads(rd)) for (const id of above) assert.ok(Math.abs(post[id].top - rd.pre[id].top) <= 1, `${when}: ${id} moved on Send: ${rd.pre[id].top} to ${post[id].top}`);
}
for (const width of [1280, 390]) {
  test(`answered-sink: a sent card in view: the open card below takes its top, and nothing above it moves on screen, at ${width} wide (SENT_MOVE sink)`, async (t) => {
    await sinkSendInView(t, { width });
  });
  test(`answered-sink: a sent card last in its tier: nothing above it moves on screen, at ${width} wide (SENT_MOVE sink)`, async (t) => {
    await sinkSendLastInTier(t, { width });
  });
}
// The two 390 cases again with the browser's scroll anchoring on. The cases above keep it off, so they stay as they are.
test("answered-sink: a sent card in view, with scroll anchoring on: the open card below takes its top, and nothing above it moves on screen, at 390 wide (SENT_MOVE sink)", async (t) => {
  await sinkSendInView(t, { width: 390, anchored: true });
});
test("answered-sink: a sent card last in its tier, with scroll anchoring on: nothing above it moves on screen, at 390 wide (SENT_MOVE sink)", async (t) => {
  await sinkSendLastInTier(t, { width: 390, anchored: true });
});

// Scroll anchoring stays on in the cases below: they test what a reader's browser does with the page's own compensation. A card in view
// is one whose box overlaps the band the owner reads, from the header's bottom edge to the top of the bar.
const inViewIds = (pre, band) => Object.keys(pre).filter((id) => pre[id].top < band.bottom && pre[id].bottom > band.top);
const answeredRow = (page) => page.locator('#rail a.ov-head[href="#tier-answered"]').count();
const SENT_TALL = LONG.repeat(3);

// The first sink Send adds the rail's Answered row, which on a narrow screen sits above the list. The cards in view above the sent card keep
// their viewport tops, and the open card below takes the sent card's top. A card below that one moves up by the sent card's leaving.
async function sinkRailRowHolds(t, { width }) {
  const sent = mk("rail-sent", 4, { context: LONG }), below = mk("rail-below", 5, { context: LONG });
  const page = await openSend(t, { items: [...LEADS, sent, below, ...FILLER], width, height: 800, scheme: "light", anchored: true, sentMove: "sink" }); if (!page) return;
  await choose(page, sent, "a");
  await settleAt(page, sent, "top", 60);
  const rd = await sendAndRead(page, [sent]);
  const S = "item-rail-sent", B = "item-rail-below";
  assert.ok(rd.pre[S].top >= rd.band.top && rd.pre[S].top < rd.band.bottom, `fixture: the sent card is not in view before Send at ${rd.pre[S].top}`);
  assert.equal(await answeredRow(page), 1, "the Send did not add the Answered row to the rail");
  const shift = rd.pre[B].top - rd.pre[S].top;
  for (const [when, post] of reads(rd)) {
    for (const id of inViewIds(rd.pre, rd.band)) {
      if (id === S || id === B) continue;
      const want = rd.pre[id].top < rd.pre[S].top ? rd.pre[id].top : rd.pre[id].top - shift;
      assert.ok(Math.abs(post[id].top - want) <= 2, `${when}: ${id} moved on screen on Send: ${rd.pre[id].top} to ${post[id].top}`);
    }
    assert.ok(Math.abs(post[B].top - rd.pre[S].top) <= 2, `${when}: the open card below did not take the sent card's top ${rd.pre[S].top}: ${post[B].top}`);
  }
}

// A card sent with its top above the screen's top edge, at a desktop width. The sent card leaves above the cards in view, so they keep their viewport tops.
async function sinkSendPartlyAbove(t) {
  const sent = mk("part-sent", 4, { context: SENT_TALL }), below = mk("part-below", 5, { context: LONG });
  const page = await openSend(t, { items: [...LEADS, sent, below, ...FILLER], width: 1280, height: 800, scheme: "light", anchored: true, sentMove: "sink" }); if (!page) return;
  await choose(page, sent, "a");
  await settleAt(page, sent, "top", -300);
  const rd = await sendAndRead(page, [sent]);
  const S = "item-part-sent";
  assert.ok(rd.pre[S].top < rd.band.top && rd.pre[S].bottom > rd.band.top + 100, `fixture: the sent card is not partly above the screen: top ${rd.pre[S].top}, bottom ${rd.pre[S].bottom}`);
  for (const [when, post] of reads(rd)) for (const id of inViewIds(rd.pre, rd.band)) {
    if (id === S) continue;
    assert.ok(Math.abs(post[id].top - rd.pre[id].top) <= 2, `${when}: ${id} moved on screen on Send: ${rd.pre[id].top} to ${post[id].top}`);
  }
}

// Undo of the Send that added the Answered row, on a phone. Once the row is gone, every card in view is back at its pre-Send viewport top.
async function sinkUndoRailRow(t) {
  const sent = mk("undo-sent", 4, { context: LONG }), below = mk("undo-below", 5, { context: LONG });
  const page = await openSend(t, { items: [...LEADS, sent, below, ...FILLER], width: 390, height: 800, scheme: "light", anchored: true, sentMove: "sink" }); if (!page) return;
  await choose(page, sent, "a");
  await settleAt(page, sent, "top", 60);
  const pre = await cardMap(page), band = await bandOf(page);
  await send(page);
  await card(page, sent).locator(".receipt").waitFor();
  await page.locator("#sent .stamp").waitFor();
  await frameWait(page, 2);
  assert.equal(await answeredRow(page), 1, "the Send did not add the Answered row to the rail");
  await page.locator("#undoBtn").click();
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 0);
  await frameWait(page, 2);
  assert.equal(await answeredRow(page), 0, "the Answered row stayed on the rail after Undo");
  const back = await cardMap(page);
  // The returning card goes back to its own slot, so only the cards it did not pass are checked.
  const S = "item-undo-sent";
  for (const id of inViewIds(pre, band)) {
    if (id === S) continue;
    assert.ok(Math.abs(back[id].top - pre[id].top) <= 2, `${id} moved on screen on Undo: ${pre[id].top} to ${back[id].top}`);
  }
}
for (const width of [390, 800]) {
  test(`answered-sink: the first Send that adds the rail's Answered row keeps the cards in view, with scroll anchoring on, at ${width} wide (SENT_MOVE sink)`, async (t) => {
    await sinkRailRowHolds(t, { width });
  });
}
test("answered-sink: a card sent with its top above the screen keeps the cards in view, with scroll anchoring on, at 1280 wide (SENT_MOVE sink)", async (t) => {
  await sinkSendPartlyAbove(t);
});
test("answered-sink: Undo of the Send that added the Answered row moves no card in view, with scroll anchoring on, at 390 wide (SENT_MOVE sink)", async (t) => {
  await sinkUndoRailRow(t);
});

// Scroll anchoring stays on in every case below. A Send is a script click, not a mouse press, since a press moves the focus to the Send button.
const focusedId = (page) => page.evaluate(() => (document.activeElement && document.activeElement.id) || "");
// A frame's load event does not reach the window in capture, so each frame counts its own load. A frame moved in the DOM reloads, and a new one is caught when it is added.
const watchLoads = (page) => page.evaluate(() => {
  window.__loads = 0;
  const bump = () => { window.__loads++; };
  const on = (f) => { if (f.tagName === "IFRAME") f.addEventListener("load", bump); };
  const attach = (n) => { if (n.nodeType === 1) { on(n); n.querySelectorAll("iframe").forEach(on); } };
  document.querySelectorAll("iframe").forEach(on);
  new MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach(attach))).observe(document.body, { childList: true, subtree: true });
});

// Focus on a radio of a card below the sent card (or above it, as a control), then a Send that sinks the sent card. Returns what the reader sees.
async function sinkWithFocusBelow(t, { focusOn }) {
  const sent = mk("rec-sent", 4), radio = mk("rec-radio", 5), frame = mk("rec-frame", 6, { designs: [{ slug: "s1", label: "Option a" }] });
  const page = await open(t, { items: inArrayOrder([...LEADS, sent, radio, frame, ...FILLER]), designData: { s1: "<p>one</p>" }, viewport: { width: 1280, height: 800 }, pageHtml: withSentMove("sink") }); if (!page) return null;
  await choose(page, sent, "a");
  await settleAt(page, sent, "top", 60);
  const target = focusOn === "above" ? LEADS[0] : radio, radioId = "o-" + target.id + "-a";
  const frames = await page.locator("#item-rec-frame iframe.dframe").count();
  await page.locator("#" + radioId).focus();
  const focused = await focusedId(page);
  await watchLoads(page);
  await page.evaluate(() => document.getElementById("send").click());
  await card(page, sent).locator(".receipt").waitFor();
  await page.locator("#sent .stamp").waitFor();
  await frameWait(page, 3);
  return { frames, focused, radioId, active: await focusedId(page), loads: await page.evaluate(() => window.__loads) };
}
test("answered-sink: a Send that sinks a card keeps the focus on a radio below it, with scroll anchoring on, at 1280 wide (SENT_MOVE sink)", async (t) => {
  const r = await sinkWithFocusBelow(t, { focusOn: "below" }); if (!r) return;
  assert.equal(r.focused, r.radioId, "fixture: the radio below the sent card did not take the focus before Send");
  assert.equal(r.active, r.radioId, `focus left the radio below the sent card on Send: now on "${r.active}"`);
});
test("answered-sink: a Send that sinks a card reloads no design frame below it, with scroll anchoring on, at 1280 wide (SENT_MOVE sink)", async (t) => {
  const r = await sinkWithFocusBelow(t, { focusOn: "below" }); if (!r) return;
  assert.equal(r.frames, 1, "fixture: the design frame below the sent card is not there");
  assert.equal(r.loads, 0, "a design frame below the sent card reloaded on Send");
});
test("answered-sink: control: a Send that sinks a card keeps the focus on a radio above it, with scroll anchoring on, at 1280 wide (SENT_MOVE sink)", async (t) => {
  const r = await sinkWithFocusBelow(t, { focusOn: "above" }); if (!r) return;
  assert.equal(r.focused, r.radioId, "fixture: the radio above the sent card did not take the focus before Send");
  assert.equal(r.active, r.radioId, `focus left the radio above the sent card on Send: now on "${r.active}"`);
});

// A sent card taller than the view, its top above the screen and its bottom below it. The next open card must take the sent card's old top,
// and the view must not move to the card above. The control is a short card in view: the same rule, with nothing to hold.
async function sinkSpanOrShort(t, { spanning }) {
  // A long context folds after three lines, so the tall card carries many options instead.
  const tallOpts = Array.from({ length: 24 }, (_, i) => opt(String.fromCharCode(97 + i), "Option " + (i + 1)));
  const sent = mk("span-sent", 4, spanning ? { options: tallOpts } : {}), below = mk("span-below", 5, { context: LONG });
  const page = await openSend(t, { items: [...LEADS, sent, below, ...FILLER], width: 390, height: 800, scheme: "light", anchored: true, sentMove: "sink" }); if (!page) return;
  await choose(page, sent, "a");
  await settleAt(page, sent, "top", spanning ? -300 : 60);
  const rd = await sendAndRead(page, [sent]);
  const S = "item-span-sent", B = "item-span-below";
  if (spanning) assert.ok(rd.pre[S].top < 0 && rd.pre[S].bottom > 800 && rd.pre[S].h > 800, `fixture: the sent card does not span the view: top ${rd.pre[S].top}, bottom ${rd.pre[S].bottom}, height ${rd.pre[S].h}`);
  for (const [when, post] of reads(rd)) assert.ok(Math.abs(post[B].top - rd.pre[S].top) <= 2, `${when}: the next open card is at ${post[B].top}, not at the sent card's old top ${rd.pre[S].top}`);
}
test("answered-sink: a sent card taller than the view, with scroll anchoring on: the next open card takes its top and the view stays, at 390 wide (SENT_MOVE sink)", async (t) => {
  await sinkSpanOrShort(t, { spanning: true });
});
test("answered-sink: control: a sent card shorter than the view, with scroll anchoring on: the next open card takes its top, at 390 wide (SENT_MOVE sink)", async (t) => {
  await sinkSpanOrShort(t, { spanning: false });
});

// Undo of a Send from a card whose top sits at `want` in the viewport. Undo returns the card, and it must come back at its pre-Send top.
async function undoFromTop(t, { width, want }) {
  const sent = mk("undo-top", 4, { context: LONG }), below = mk("undo-top-below", 5, { context: LONG });
  const page = await openSend(t, { items: [...LEADS, sent, below, ...FILLER], width, height: 800, scheme: "light", anchored: true, sentMove: "sink" }); if (!page) return;
  await choose(page, sent, "a");
  const bt = (await bandOf(page)).top;
  await settleAt(page, sent, "top", want - bt);
  const S = "item-undo-top";
  const pre = await cardMap(page);
  assert.ok(Math.abs(pre[S].top - want) <= 2, `fixture: the sent card's top is ${pre[S].top}, not ${want}`);
  await send(page);
  await card(page, sent).locator(".receipt").waitFor();
  await page.locator("#sent .stamp").waitFor();
  await frameWait(page, 2);
  await page.locator("#undoBtn").click();
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 0);
  await frameWait(page, 3);
  const back = await cardMap(page);
  assert.ok(Math.abs(back[S].top - pre[S].top) <= 2, `the card came back at ${back[S].top}, not at its pre-Send top ${pre[S].top}`);
}
test("answered-sink: Undo of a Send from a card that starts above the screen returns it to its pre-Send top, with scroll anchoring on, at 390 wide (SENT_MOVE sink)", async (t) => {
  await undoFromTop(t, { width: 390, want: -76 });
});
test("answered-sink: Undo of a Send from a card that starts above the screen returns it to its pre-Send top, with scroll anchoring on, at 1280 wide (SENT_MOVE sink)", async (t) => {
  await undoFromTop(t, { width: 1280, want: -76 });
});
test("answered-sink: control: Undo of a Send from a card in view returns it to its pre-Send top, with scroll anchoring on, at 390 wide (SENT_MOVE sink)", async (t) => {
  await undoFromTop(t, { width: 390, want: 60 });
});

// An answer that arrives without a Send, on a card in view: the card keeps its height while in view, and drops once wholly off the screen.
async function answerWithoutSend(t, { width, scheme }) {
  const inView = mk("in-view", 4, { context: LONG }), below = mk("below", 5);
  const page = await openSend(t, { items: [...LEADS, inView, below, ...FILLER], width, height: 800, scheme, anchored: false, timers: true }); if (!page) return;
  await settleAt(page, inView, "top", 40);
  const pre = await cardMap(page);
  const I = "item-in-view", B = "item-below";
  // The answer comes from the database, as another session's save would, so the page sends nothing of its own.
  await page.evaluate(async (id) => { const db = await window.claude.use("db"); await db.collection("answers").doc(id).set({ item: id, n: 4, at: "2026-10-30T14:00:00Z", choice: "a", note: "" }); }, inView.id);
  await card(page, inView).locator(".receipt").waitFor();
  assert.equal(await page.evaluate(() => window.__log.filter((l) => l[0] === "set").length), 1, "the page wrote an answer of its own");
  const atOnce = await cardMap(page);
  assert.ok(atOnce[I].h >= pre[I].h - 1, `an answer without a Send dropped its height at once: ${pre[I].h}px to ${atOnce[I].h}px`);
  await page.clock.runFor(700); // a card in view is never dropped on a timer: the fake clock runs past any drop timer, with no wait
  const held = await cardMap(page);
  assert.ok(Math.abs(held[I].h - pre[I].h) <= 1, `an answer without a Send changed the card's height while in view: ${pre[I].h}px to ${held[I].h}px`);
  assert.ok(Math.abs(held[B].top - pre[B].top) <= 1, `an answer without a Send moved the card below: ${pre[B].top} to ${held[B].top}`);
  // The card wholly off the screen drops its height, and the card below, still on screen, keeps its top.
  await page.evaluate((id) => { const b = document.getElementById(id).getBoundingClientRect().bottom; window.scrollBy(0, b + 4); }, I);
  const scrolled = await cardMap(page);
  assert.ok(scrolled[B].bottom > 0 && scrolled[B].top < 800,`fixture: the card below is off the screen after the scroll at ${scrolled[B].top}`);
  await page.waitForFunction(([id, h]) => document.getElementById(id).getBoundingClientRect().height < h - 100, [I, pre[I].h]);
  const dropped = await cardMap(page);
  assert.ok(Math.abs(dropped[B].top - scrolled[B].top) <= 1, `the card below moved when the held card dropped: ${scrolled[B].top} to ${dropped[B].top}`);
}

for (const scheme of ["light", "dark"]) for (const width of [1280, 390]) {
  test(`a card sent with the card above it partly on screen keeps that card's top, and the cards below rise, at ${width} wide, ${scheme} scheme`, async (t) => {
    await sendBelowPartial(t, { width, scheme, anchored: false });
  });
  test(`a card sent with the card above it partly on screen keeps that card's top with scroll anchoring on, at ${width} wide, ${scheme} scheme`, async (t) => {
    await sendBelowPartial(t, { width, scheme, anchored: true });
  });
}

for (const scheme of ["light", "dark"]) {
  test(`a card sent as the topmost card on screen keeps its top, and the card below rises, ${scheme} scheme`, async (t) => {
    await sendTopOfBand(t, { scheme });
  });
}

for (const scheme of ["light", "dark"]) for (const width of [1280, 390]) {
  test(`two cards sent together, one wholly above the band: the other keeps its top, and the card below rises, at ${width} wide, ${scheme} scheme`, async (t) => {
    await sendTwoOneAbove(t, { width, scheme });
  });
}

for (const scheme of ["light", "dark"]) {
  test(`a tall card at 390 wide sent over the band's top edge: the card below keeps its top, and the receipt lands just above it, ${scheme} scheme`, async (t) => {
    await sendTallOverBand(t, { scheme });
  });
}

for (const scheme of ["light", "dark"]) {
  test(`a card sent with the card below under the bar: the sent card keeps its top, and the card below rises, ${scheme} scheme`, async (t) => {
    await sendOverUnderBar(t, { scheme });
  });
}

for (const scheme of ["light", "dark"]) for (const width of [1280, 390]) {
  test(`an answer that arrives without a Send keeps its height while in view, and drops once wholly off the screen, at ${width} wide, ${scheme} scheme`, async (t) => {
    await answerWithoutSend(t, { width, scheme });
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
    await fitAll(page, LOOK_OPTS.map((o) => o.design));
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

test("a rail jump after Send lands on its card", async (t) => {
  const items = Array.from({ length: 14 }, (_, i) => mk("q" + i, i + 1, { context: LONG }));
  const page = await open(t, { items: inArrayOrder(items), viewport: { width: 1280, height: 800 } }); if (!page) return;
  await noAnchor(page);
  await choose(page, items[0], "a"); await choose(page, items[1], "a");
  await send(page);
  await page.locator("#item-q0 .receipt").waitFor();
  await page.evaluate(() => { window.__ended = false; window.addEventListener("scrollend", () => { window.__ended = true; }, { once: true }); }); // registered before the jump
  await page.click("#c-q9");
  await page.waitForFunction(() => window.__ended).catch(() => {}); // the jump's scroll end; a jump that never scrolls leaves the band assert to name it
  // The card lands inside the band, just under the header's bottom edge.
  const band = await bandOf(page);
  const top = await card(page, items[9]).evaluate((e) => Math.round(e.getBoundingClientRect().top));
  assert.ok(top >= band.top - 1 && top <= band.top + 120, `the jump missed its card; it sits at ${top}, band top ${band.top}`);
});

test("a receipt wholly below the screen drops its height without moving the page", async (t) => {
  const items = Array.from({ length: 40 }, (_, i) => mk("q" + i, i + 1, { context: LONG }));
  const page = await open(t, { items, viewport: { width: 390, height: 360 } }); if (!page) return;
  await noAnchor(page);
  await choose(page, items[0], "a");
  await page.evaluate(() => window.scrollTo(0, 60));
  const railTop = () => page.evaluate(() => Math.round(document.querySelector(".ov-prog").getBoundingClientRect().top));
  const at = await railTop(), h0 = await card(page, items[0]).evaluate((e) => e.getBoundingClientRect().height);
  await send(page);
  await page.locator("#item-q0 .receipt").waitFor();
  await page.waitForFunction((h) => document.getElementById("item-q0").getBoundingClientRect().height < h - 1, h0).catch(() => {}); // the card drops once its receipt is off screen, after a short timer
  assert.ok((await card(page, items[0]).evaluate((e) => e.getBoundingClientRect().height)) < h0 - 1, "the card did not drop its height once its receipt was off screen");
  assert.ok(Math.abs((await railTop()) - at) <= 1, "the page moved when an off-screen receipt shrank");
});

// A phone mockup shows whole, so the design caps its height at 480px (docs/design/c193-sizes.md item 3); it scales to its card and stays centred.
for (const width of SIZES) test(`an option's picture is at most 480px high and centred in its card at ${width}px wide`, async (t) => {
  const it = mk("cap-pics", 1, { options: LOOK_OPTS, pick: "a", designs: LOOK_OPTS.map((o) => ({ slug: o.design, label: o.label, size: { w: 390, h: 844 } })) });
  const designData = Object.fromEntries(LOOK_OPTS.map((o) => [o.design, '<body style="margin:0"><div style="width:390px;height:844px;background:#eee"></div></body>']));
  const page = await open(t, { items: [it], designData, viewport: { width, height: 900 } }); if (!page) return;
  await card(page, it).locator("label.opt .dfitwrap").first().scrollIntoViewIfNeeded();
  await fitAll(page, LOOK_OPTS.map((o) => o.design));
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
// The filed row lists TASK first: a filed item draws as one line, and open() waits for the first item's card.
const SWEEP_WIDTHS = [320, 390, 768, 1024, 1280, 1600, 2200, 2560];
const LONGT = "A very long title that runs across the whole width of the rail and then some more ";
const TALL = '<body style="margin:0"><div style="width:390px;height:844px;background:#eee"></div></body>';
const STATES = [
  ["open", () => ({ items: [DECISION, TASK] })],
  ["draft ready", () => ({ items: [DECISION, TASK] }), (page) => choose(page, DECISION, "a")],
  ["answered, filing pending", () => ({ items: [DECISION, TASK], answers: SAVED_A })],
  ["answered, filed", () => ({ items: [TASK, DECISION], answers: SAVED_A, receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z", filed: "2026-10-26T03:00:00Z" } } })],
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
    const spec = make();
    const page = await open(t, { ...spec, scheme, viewport: { width, height: 900 } }); if (!page) return;
    if (act) await act(page);
    if (spec.designData) await fitAll(page, Object.keys(spec.designData)); // a picture's layout is final only after its frame posts its fit
    await frameWait(page, 3); // the state's layout settles in its frames
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
  await fitAll(page, LOOK_OPTS.map((o) => o.design));
  const narrow = (await picBox(page))[0].w;
  await page.setViewportSize({ width: 1280, height: 900 });
  await frameWait(page, 3); // the card's width changes, and the picture follows it in the frames after
  const wide = await picBox(page);
  assert.ok(wide[0].w > narrow + 10, `the picture did not grow back: ${narrow} then ${wide[0].w}`);
  await page.setViewportSize({ width: 1066, height: 900 });
  await frameWait(page, 3); // the card's width changes, and the picture follows it in the frames after
  for (const b of await picBox(page)) assert.ok(b.over <= 1, "the picture runs past its card after narrowing: " + b.over);
});

test("a very tall mockup with no focus is never a thin strip", async (t) => {
  const page = await open(t, { items: [growItem()], designData: growData(3000), viewport: { width: 1280, height: 900 } }); if (!page) return;
  await fitAll(page, LOOK_OPTS.map((o) => o.design));
  for (const b of await picBox(page)) assert.ok(b.w >= 120, "the picture is a strip, " + b.w + "px wide");
});

test("the SENT stamp is the same element, not rebuilt, as the Undo count ticks", async (t) => {
  const page = await sentPage(t, false); if (!page) return;
  await page.evaluate(() => { window.__stamp = document.querySelector("#sent .stamp"); });
  const undoCount = () => page.locator("#undoBtn").textContent().then((s) => { const m = /\((\d+)\)/.exec(s); return m ? +m[1] : NaN; });
  const start = await undoCount();
  await page.waitForFunction((s) => { const m = /\((\d+)\)/.exec(document.getElementById("undoBtn").textContent); return !!m && +m[1] <= s - 2; }, start).catch(() => {}); // two ticks of the count pass, and the stamp must survive them
  assert.ok(start - (await undoCount()) >= 2, "the Undo count did not tick twice");
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
  assert.equal((await a.locator(".widens").innerText()).trim(), "Goes against your ruling: a repo changes to fit a shared tool, never the tool to fit a repo");
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
  await fitAll(page, LOOK_OPTS.map((o) => o.design));
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

// ---------------------------------------------------------------- c190: links on an option card, and a task's command
// Each link row and command block id follows the item's id, as the option radios do.
const LINK = { label: "Merge sample-repo#374 on GitHub", url: "https://github.example.test/sample-repo/pull/374" };
// Option a has a link and option b none, so one card holds the links row and the other a nolinks span.
const LINKED = mk("linked-pick", 29, {
  options: [
    { key: "a", label: "Merge it", how: "Mark it ready and press Merge.", gain: "g", lose: "l", links: [LINK] },
    { key: "b", label: "Wait", how: "Leave it open.", gain: "g", lose: "l" },
  ],
  pick: "a", why: "It lands now.",
});
const PLAIN = mk("plain-pick", 30); // no option has a link
const CMD = "cd ~/sample-repo\n\necho \"a < b & 'c'\"\n  git status --short";
const CMD_LINES = CMD.split("\n").map((l) => l.trim()).filter(Boolean);
const RUN = { ...TASK, id: "run-the-command", n: 31, title: "Run the command", steps: ["Open a terminal", "Paste the command and run it"], command: CMD, links: [{ label: "Sample repo on GitHub", url: "https://github.example.test/sample-repo" }] };
const WIDE_RUN = { ...RUN, id: "wide-command", n: 32, title: "Deploy the release", command: "npm run deploy -- --environment production --region us-east-1 --confirm --message 'a line that runs past the width of a phone and must wrap, not scroll'\n" + CMD };
// Ruling (shiv, 2026-10-30 14:47 CDT): a task's command is {powershell, mac}, one string per shell, each in its own block.
// A string command keeps the legacy render that RUN and WIDE_RUN above test.
const PS_CMD = "Set-Location ~/sample-repo\nWrite-Output \"a < b & 'c'\"";
const PS_LINES = PS_CMD.split("\n").map((l) => l.trim()).filter(Boolean);
const BOTH = { ...TASK, id: "both-shells", n: 34, title: "Clear the cache", steps: ["Open a terminal", "Paste the command below and run it"], command: { powershell: PS_CMD, mac: CMD } };
const MAC_ONLY = { ...BOTH, id: "mac-only", n: 35, title: "Clear the Mac cache", command: { mac: CMD } };
const BOTH_WIDE = { ...BOTH, id: "wide-both", n: 36, title: "Deploy on both shells", command: { powershell: "Invoke-Deploy -Environment production -Region us-east-1 -Confirm -Message 'a line that runs past the width of a phone and must wrap, not scroll'\n" + PS_CMD, mac: WIDE_RUN.command } };
const STATUS_REFUSED = "Not copied. The text is selected; copy it by hand.";
// A missing element fails with its own message, not as a locator timeout.
const need = async (loc, msg) => assert.equal(await loc.count(), 1, msg);
const boxHeight = async (loc) => (await loc.boundingBox())?.height ?? 0;
// Waits up to 3 s for a page condition; a miss returns false, so the assert names it.
const holds = (page, fn, arg = null) => page.waitForFunction(fn, arg, { timeout: 3000 }).then(() => true, () => false);
// The clipboard either takes the text into window.__copied or refuses it, as a frame without permission does.
const stubClipboard = (page, refuse) => page.evaluate((no) => { Object.defineProperty(navigator, "clipboard", { value: { writeText: async (s) => { if (no) throw new Error("denied"); window.__copied = s; } } }); }, refuse);

test("a decision option's link sits between its how text and its timing rows, names where it opens, and a card with no link keeps its rows", async (t) => {
  const page = await open(t, { items: [LINKED, PLAIN] }); if (!page) return;
  const row = card(page, LINKED).locator(`#k-${LINKED.id}-a`);
  await need(row, "no links row on option a");
  const place = await row.evaluate((e) => ({ inOpt: !!e.closest("label.opt"), afterHow: !!e.previousElementSibling?.classList.contains("how"), beforeTr: !!e.nextElementSibling?.classList.contains("tr") }));
  assert.deepEqual(place, { inOpt: true, afterHow: true, beforeTr: true }, "the links row is not between the how text and the timing rows");
  const link = row.locator("a");
  await need(link, "the links row holds no link");
  const got = await link.evaluate((a) => ({ href: a.getAttribute("href"), target: a.getAttribute("target"), rel: a.getAttribute("rel"), text: a.textContent, arrow: a.querySelector('span[aria-hidden="true"]')?.textContent, sr: a.querySelector("span.sr")?.textContent }));
  assert.equal(got.href, LINK.url);
  assert.equal(got.target, "_blank");
  assert.equal(got.rel, "noopener");
  assert.ok(got.text.startsWith(LINK.label), "the link text is not its label");
  assert.equal(got.arrow, "↗", "the arrow is not in a span hidden from screen readers");
  assert.equal(got.sr, ", opens in a new tab", "no screen-reader words say where the link opens");
  assert.equal(await page.getByRole("link", { name: LINK.label + ", opens in a new tab", exact: true }).count(), 1, "the link is not named for where it opens");
  assert.equal(await card(page, LINKED).locator(".opts.olinks").count(), 1, "the options do not take the olinks class");
  assert.equal(await card(page, LINKED).locator(`label[for="o-${LINKED.id}-b"] span.nolinks`).count(), 1, "an option with no link has no nolinks span");
  assert.equal(await card(page, PLAIN).locator(".opts.olinks").count(), 0, "a card with no link took the olinks class");
  assert.equal(await card(page, PLAIN).locator(".opts a, .opts .links").count(), 0, "a card with no link shows a link");
});

test("a tap on an option's link opens it in a new tab and leaves the radio unchecked; a tap on the card still picks", async (t) => {
  const page = await open(t, { items: [LINKED] }); if (!page) return;
  const link = card(page, LINKED).locator(`#k-${LINKED.id}-a a`);
  await need(link, "no link on option a");
  await page.context().route("**/*", (r) => r.abort()); // the new tab loads nothing
  const [tab] = await Promise.all([page.context().waitForEvent("page", { timeout: 5000 }), link.click()]);
  await tab.close();
  assert.equal(await page.isChecked(`#o-${LINKED.id}-a`), false, "a tap on the link checked the option");
  assert.equal(await card(page, LINKED).locator(".opt.sel").count(), 0, "a tap on the link selected the card");
  assert.equal(await page.locator("#send").isDisabled(), true, "a tap on the link made an answer");
  await card(page, LINKED).locator(`label[for="o-${LINKED.id}-a"] .how`).click();
  assert.equal(await page.isChecked(`#o-${LINKED.id}-a`), true, "a tap on the card did not pick the option");
});

test("a task's link has the same screen-reader name as an option's link", async (t) => {
  const page = await open(t, { items: [RUN] }); if (!page) return;
  assert.equal(await page.getByRole("link", { name: "Sample repo on GitHub, opens in a new tab", exact: true }).count(), 1, "the task link is not named for where it opens");
});

test("a task's command sits after its steps, closed behind Show the command, and Copy writes it exactly while it is closed", async (t) => {
  const page = await open(t, { items: [RUN] }); if (!page) return;
  const box = card(page, RUN).locator(".cmd");
  await need(box, "no command block on a task with a command");
  const place = await box.evaluate((e) => ({ afterSteps: !!e.previousElementSibling?.classList.contains("steps"), beforeLinks: !!e.nextElementSibling?.classList.contains("links") }));
  assert.deepEqual(place, { afterSteps: true, beforeLinks: true }, "the command block is not between the steps and the links");
  const more = box.locator("details");
  await need(more, "the command is not in a closed disclosure");
  assert.equal(await more.evaluate((d) => d.open), false, "the disclosure starts open");
  assert.equal((await more.locator("summary").textContent()).trim(), "Show the command");
  const copy = box.locator("button.cmd-copy");
  await need(copy, "no Copy button on the command");
  assert.equal(await copy.getAttribute("aria-label"), "Copy the command for No. 31");
  assert.equal(await copy.evaluate((b) => !!b.closest("details")), false, "Copy sits inside the disclosure");
  assert.equal(await copy.innerText(), "Copy", "Copy does not read Copy at first");
  assert.ok((await box.textContent()).includes(`echo "a < b & 'c'"`), "the command does not show < and & as written");
  await stubClipboard(page, false);
  await copy.click();
  assert.equal(await holds(page, (id) => !!document.querySelector("#item-" + id + " .cmd.copied"), RUN.id), true, "a copy that worked did not mark the block copied");
  assert.equal(await page.evaluate(() => window.__copied), CMD, "Copy did not write the command exactly");
  assert.equal(await copy.innerText(), "Copied", "the button does not say Copied");
});

test("a copy the browser refuses opens the command, selects its text, and says so in words", async (t) => {
  const page = await open(t, { items: [RUN] }); if (!page) return;
  const box = card(page, RUN).locator(".cmd");
  await need(box, "no command block on a task with a command");
  await stubClipboard(page, true);
  await box.locator("button.cmd-copy").click();
  assert.equal(await holds(page, (id) => !!document.querySelector("#item-" + id + " .cmd.failed"), RUN.id), true, "a refused copy did not mark the block failed");
  assert.equal(await box.locator("details").evaluate((d) => d.open), true, "a refused copy did not open the command");
  await need(box.locator("[aria-live]"), "no status line in the command block");
  assert.equal((await box.locator("[aria-live]").textContent()).trim(), STATUS_REFUSED, "the status does not say the copy failed");
  const sel = await page.evaluate(() => getSelection().toString());
  for (const line of CMD_LINES) assert.ok(sel.includes(line), "the command text is not selected: " + line);
  assert.equal(await box.evaluate((e) => e.classList.contains("copied")), false, "a refused copy marked the block copied");
  assert.equal(await page.evaluate(() => window.__copied), undefined, "a refused copy wrote something");
});

test("a task with no command shows no command block, and a task with one shows it", async (t) => {
  const page = await open(t, { items: [RUN, TASK] }); if (!page) return;
  assert.equal(await card(page, RUN).locator(".cmd").count(), 1, "the task with a command has no command block");
  assert.equal(await card(page, TASK).locator(".cmd").count(), 0, "a task with no command shows a command block");
});

for (const scheme of ["light", "dark"]) for (const width of [390, 1280]) {
  test(`links and Copy are 44px tall or more, and a long command wraps without sideways scroll, at ${width} wide, ${scheme} scheme`, async (t) => {
    const page = await open(t, { items: [LINKED, WIDE_RUN], scheme, viewport: { width, height: 900 } }); if (!page) return;
    const link = card(page, LINKED).locator(`#k-${LINKED.id}-a a`);
    await need(link, "no link on option a");
    assert.ok((await boxHeight(link)) >= 44, "the option link is under 44px tall");
    const box = card(page, WIDE_RUN).locator(".cmd");
    await need(box, "no command block on the wide task");
    await need(box.locator("summary"), "the command has no disclosure to open");
    await box.locator("summary").click();
    const copy = box.locator("button.cmd-copy");
    await need(copy, "no Copy button on the wide task");
    assert.ok((await boxHeight(copy)) >= 44, "Copy is under 44px tall");
    await need(box.locator(".cmd-text"), "no command text in the block");
    assert.equal(await box.locator(".cmd-text").evaluate((e) => e.scrollWidth <= e.clientWidth + 1), true, "the command runs past its block");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, "the page scrolls sideways");
  });
}

test("a task with a command for each shell shows two blocks, each closed behind its own summary, with its own Copy", async (t) => {
  const page = await open(t, { items: [BOTH] }); if (!page) return;
  assert.equal(await card(page, BOTH).locator(".cmd").count(), 2, "a task with a command for each shell does not show two blocks");
  for (const [shell, label] of [["ps", "PowerShell"], ["mac", "Mac"]]) {
    const box = card(page, BOTH).locator(`#cmd-${BOTH.id}-${shell}`);
    await need(box, `no ${label} command block`);
    const more = box.locator("details");
    await need(more, `the ${label} command is not in a closed disclosure`);
    assert.equal(await more.evaluate((d) => d.open), false, `the ${label} disclosure starts open`);
    assert.equal((await more.locator("summary").textContent()).trim(), `Show the ${label} command`, `the ${label} summary is not Show the ${label} command`);
    await need(box.locator(`#cc-${BOTH.id}-${shell}`), `the ${label} text has no id cc-${BOTH.id}-${shell}`);
    const copy = box.locator("button.cmd-copy");
    await need(copy, `no Copy on the ${label} command`);
    assert.equal(await copy.getAttribute("aria-label"), `Copy the ${label} command for No. ${BOTH.n}`, `the ${label} Copy is not named for its shell`);
    assert.equal(await copy.getAttribute("aria-controls"), `cc-${BOTH.id}-${shell}`, `the ${label} Copy does not control its own text`);
    assert.equal(await copy.evaluate((b) => !!b.closest("details")), false, `the ${label} Copy sits inside its disclosure`);
  }
});

test("Copy on each shell's block writes that shell's string exactly, while its block is closed", async (t) => {
  const page = await open(t, { items: [BOTH] }); if (!page) return;
  await stubClipboard(page, false);
  for (const [shell, text] of [["ps", PS_CMD], ["mac", CMD]]) {
    const box = card(page, BOTH).locator(`#cmd-${BOTH.id}-${shell}`);
    await need(box, `no ${shell} command block`);
    assert.equal(await box.locator("details").evaluate((d) => d.open), false, `the ${shell} block is open before Copy`);
    await box.locator("button.cmd-copy").click();
    assert.equal(await holds(page, ({ id, shell }) => !!document.querySelector(`#cmd-${id}-${shell}.copied`), { id: BOTH.id, shell }), true, `a copy that worked did not mark the ${shell} block copied`);
    assert.equal(await page.evaluate(() => window.__copied), text, `Copy did not write the ${shell} command exactly`);
  }
});

for (const [platform, first, label] of [["Win32", "ps", "PowerShell"], ["MacIntel", "mac", "Mac"]]) {
  test(`on ${platform} the ${label} block comes first`, async (t) => {
    const page = await open(t, { items: [BOTH], platform }); if (!page) return;
    const order = await card(page, BOTH).locator(".cmd").evaluateAll((els) => els.map((e) => e.id));
    const second = first === "ps" ? "mac" : "ps";
    assert.deepEqual(order, [`cmd-${BOTH.id}-${first}`, `cmd-${BOTH.id}-${second}`], `on ${platform} the blocks are not in this order`);
  });
}

test("a command with only a mac string shows one Mac block and no PowerShell block, never a fallback label", async (t) => {
  const page = await open(t, { items: [MAC_ONLY] }); if (!page) return;
  const one = card(page, MAC_ONLY);
  assert.equal(await one.locator(".cmd").count(), 1, "a mac-only command did not show exactly one block");
  await need(one.locator(`#cmd-${MAC_ONLY.id}-mac`), "no Mac command block");
  assert.equal(await one.locator(`#cmd-${MAC_ONLY.id}-ps`).count(), 0, "a mac-only command shows a PowerShell block");
  assert.equal((await one.locator(".cmd-more > summary").textContent()).trim(), "Show the Mac command", "the mac-only summary is not Show the Mac command");
  assert.equal((await one.textContent()).includes("PowerShell"), false, "a mac-only command names PowerShell on the page");
});

test("a refused copy on one shell's block opens and selects only that block", async (t) => {
  const page = await open(t, { items: [BOTH] }); if (!page) return;
  await stubClipboard(page, true);
  const ps = card(page, BOTH).locator(`#cmd-${BOTH.id}-ps`), mac = card(page, BOTH).locator(`#cmd-${BOTH.id}-mac`);
  await need(ps, "no PowerShell command block");
  await need(mac, "no Mac command block");
  await ps.locator("button.cmd-copy").click();
  assert.equal(await holds(page, (id) => !!document.querySelector("#cmd-" + id + "-ps.failed"), BOTH.id), true, "a refused PowerShell copy did not mark its block failed");
  assert.equal(await ps.locator("details").evaluate((d) => d.open), true, "a refused copy did not open its own block");
  assert.equal(await mac.locator("details").evaluate((d) => d.open), false, "a refused copy opened the other block");
  assert.equal(await mac.evaluate((e) => e.classList.contains("failed")), false, "a refused copy marked the other block failed");
  const sel = await page.evaluate(() => getSelection().toString());
  for (const line of PS_LINES) assert.ok(sel.includes(line), "the PowerShell text is not selected: " + line);
  for (const line of CMD_LINES) assert.equal(sel.includes(line), false, "the Mac text is selected: " + line);
  assert.equal(await page.evaluate(() => window.__copied), undefined, "a refused copy wrote something");
});

for (const scheme of ["light", "dark"]) for (const width of [390, 1280]) {
  test(`both shells' Copy is 44px tall or more, and neither command block scrolls sideways, at ${width} wide, ${scheme} scheme`, async (t) => {
    const page = await open(t, { items: [BOTH_WIDE], scheme, viewport: { width, height: 900 } }); if (!page) return;
    for (const shell of ["ps", "mac"]) {
      const box = card(page, BOTH_WIDE).locator(`#cmd-${BOTH_WIDE.id}-${shell}`);
      await need(box, `no ${shell} command block on the wide task`);
      const copy = box.locator("button.cmd-copy");
      await need(copy, `no Copy on the ${shell} block`);
      assert.ok((await boxHeight(copy)) >= 44, `the ${shell} Copy is under 44px tall`);
      await box.locator("summary").click();
      await need(box.locator(".cmd-text"), `no ${shell} command text in the block`);
      assert.equal(await box.evaluate((e) => e.scrollWidth <= e.clientWidth + 1), true, `the ${shell} block scrolls sideways`);
      assert.equal(await box.locator(".cmd-text").evaluate((e) => e.scrollWidth <= e.clientWidth + 1), true, `the ${shell} command runs past its block`);
    }
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, "the page scrolls sideways");
  });
}

// A links value that is a string, not a list, must not break the page. The card still renders, with no links row.
test("an option whose links is a string, not a list, renders with no page error and no links row", async (t) => {
  const errors = [];
  const it = mk("string-links", 33, {
    options: [
      { key: "a", label: "Merge it", how: "Mark it ready and press Merge.", gain: "g", lose: "l", links: "https://github.example.test/sample-repo/pull/374" },
      { key: "b", label: "Wait", how: "Leave it open.", gain: "g", lose: "l" },
    ],
    pick: "a", why: "It lands now.",
  });
  const page = await open(t, { items: [it], errors }).catch((e) => { errors.push("open: " + e.message.split("\n")[0]); return null; });
  if (!page) { assert.deepEqual(errors, [], "the page threw on a string links value"); return; }
  await frameWait(page, 2); // a page error can land a tick after the card appears
  assert.deepEqual(errors, [], "the page threw on a string links value");
  assert.equal(await card(page, it).locator(".opt").count(), 2, "the option cards did not render");
  assert.equal(await card(page, it).locator(".links").count(), 0, "a string links value shows a links row");
});

// ---------------------------------------------------------------- one page: the Status tab (lane c136)
// The roadmap data block is built by skills/roadmap/build.py --block and spliced into PAGE by
// skills/waiting-page/splice.py, as the writer republishes it (tests/merged_page.py does both).
// The status panel reads only window.ROADMAP_DATA, never the artifact database.

const MERGED = path.join(HERE, "merged_page.py");
function mergedPage(...flags) {
  const r = spawnSync(process.env.PYTHON || "python3", [MERGED, "--page", PAGE, ...flags], { encoding: "utf8", maxBuffer: 1 << 28 });
  assert.equal(r.status, 0, "the roadmap build or the splice failed: " + (r.stderr || r.error));
  return r.stdout;
}
// Database content the status panel must never show: the roadmap's own collections in the live database.
const LEAKED_STEP = "Leaked database step", LEAKED_TILE = "Leaked database tile";
const LEAK = {
  steps: { leak1: { title: LEAKED_STEP, status: "active", phase: "cleanup", order: 0, note: "n", updatedAt: "2026-10-26T00:00:00Z" } },
  meta: { phases: { cleanup: { metrics: [{ label: LEAKED_TILE, value: "9 of 9" }] } }, cull: { stopRule: "leak" }, advisor: { text: "leak" } },
};
// The waiting part reads items, answers, groups, receipts and meta/page. A read of anything else is the status part's.
const statusRead = (r) => r[0] === "steps" || r[0] === "topics" || (r[0] === "meta" && r[1] !== "page");
const statusTab = (page) => page.getByRole("tab", { name: "Status", exact: true });
async function openStatus(page) {
  const tab = statusTab(page);
  assert.equal(await tab.count(), 1, "the page has no Status tab (role=tab, name Status)");
  const id = await tab.getAttribute("aria-controls");
  assert.ok(id, "the Status tab does not name its panel with aria-controls");
  const panel = page.locator("#" + id);
  assert.equal(await panel.isHidden(), true, "the Status panel shows before its tab is pressed");
  await tab.click();
  await panel.waitFor({ state: "visible" });
  await frameWait(page, 3); // a late read would land here
  return panel;
}
// Whether any visible or hidden text of the page matches (a yes or no, so a red run does not print the page).
const shows = async (page, re) => re.test(await page.locator("body").textContent());
const waitingShape = (page) => page.evaluate(() => ({
  tiers: [...document.querySelectorAll("section.tier")].map((s) => [s.id, [...s.querySelectorAll("article.card")].map((c) => c.id)]),
  bar: document.getElementById("barStatus").textContent,
  send: document.getElementById("send").textContent,
}));
// Waits for the title, then returns the real one, so a red run names what the title was.
const titleOf = async (page, want) => { await page.waitForFunction((w) => document.title === w, want).catch(() => {}); return page.title(); };

test("saved answers survive a rebuild and republish", async (t) => {
  const page = await open(t, { pageHtml: mergedPage(), items: [DECISION], answers: SAVED_A, dbExtra: LEAK }); if (!page) return;
  assert.match(await card(page, DECISION).locator(".receipt").textContent(), /You chose A: Red/);
  assert.match((await card(page, DECISION).locator(".ans").textContent()).trim(), /^Filing pending, sent /);
  const usesBefore = await page.evaluate(() => window.__uses.length);
  const panel = await openStatus(page);
  assert.match(await panel.textContent(), /Baked roadmap step zebra/, "the status panel does not show the baked roadmap");
  assert.equal(await shows(page, /Leaked database/), false, "the status panel shows database content");
  assert.deepEqual((await page.evaluate(() => window.__reads)).filter(statusRead), [], "the status part reads the live database");
  assert.equal(await page.evaluate(() => window.__uses.length), usesBefore, "opening Status calls window.claude.use");
  assert.deepEqual((await page.evaluate(() => window.__log)).filter((l) => l[1] === "answers"), [], "a document in answers/ was written or deleted");
  assert.deepEqual(await answers(page), SAVED_A);
});

test("with no roadmap data the Status tab says unknown with a reason, and the waiting part is unchanged", async (t) => {
  const items = [DECISION, TASK];
  const shipped = await open(t, { items, dbExtra: LEAK }); if (!shipped) return; // PAGE as shipped: its roadmap block is empty
  const built = await open(t, { pageHtml: mergedPage("--no-roadmap"), items, dbExtra: LEAK }); // ROADMAP_DATA = null
  const before = await waitingShape(shipped);
  assert.ok(before.tiers.length > 0 && before.send, "the waiting part drew nothing: " + JSON.stringify(before));
  assert.deepEqual(await waitingShape(built), before, "the roadmap block changed the waiting part");
  assert.equal(await statusTab(built).count(), 1, "the page has no Status tab (role=tab, name Status)");
  assert.equal(await statusTab(built).isVisible(), true, "the tab row hides Status when no item has a design");
  for (const [name, page] of [["as shipped", shipped], ["no record branch", built]]) {
    const text = await (await openStatus(page)).textContent();
    assert.match(text, /unknown/i, name + ": the status panel does not say unknown");
    // The build knows why (no record branch), so its page says so. The shipped page has no build info to quote.
    if (page === built) assert.match(text, /\bno\b[^.]{0,40}\b(roadmap|record branch)\b/i, name + ": the status panel gives no reason");
    assert.doesNotMatch(text, /signed in/i, name + ": the status panel tells the owner to sign in, which is false here");
    assert.equal(await shows(page, /Leaked database/), false, name + ": the status panel shows database content");
    assert.deepEqual((await page.evaluate(() => window.__reads)).filter(statusRead), [], name + ": the status part reads the live database");
  }
});

test("a note typed on an item survives a press of Status and back, because Status hides #qView and never removes it", async (t) => {
  const page = await open(t); if (!page) return;
  await addNote(page, DECISION, "keep this draft");
  await page.evaluate(() => { window.__qView = document.getElementById("qView"); });
  const panel = await openStatus(page);
  assert.equal(await page.locator("#qView").count(), 1, "Status removed #qView");
  assert.equal(await page.locator("#qView").isHidden(), true, "Questions still shows under Status");
  await page.click("#tabQ");
  await page.locator("#qView").waitFor({ state: "visible" });
  assert.equal(await panel.isHidden(), true, "Status still shows on Questions");
  assert.equal(await page.evaluate(() => document.getElementById("qView") === window.__qView), true, "#qView was rebuilt");
  assert.equal(await page.inputValue(`#n-${DECISION.id}`), "keep this draft");
});

// The title is "<repo> <page name>" on Questions and on Status. Status adds no suffix.
test("the document title names the repo and is the same on both tabs: <repo> <page name>", async (t) => {
  const page = await open(t, { meta: { identity: { name: "Compass" } } }); if (!page) return;
  const want = "Compass " + pageName();
  assert.equal(await titleOf(page, want), want);
  await openStatus(page);
  assert.equal(await titleOf(page, want), want, "the Status tab adds a suffix to the title");
  await page.click("#tabQ");
  assert.equal(await titleOf(page, want), want);
});

// With no identity name the title is the page name alone, on both tabs.
test("with no identity name the document title is the page name alone, on both tabs", async (t) => {
  const page = await open(t); if (!page) return;
  const want = pageName();
  assert.equal(await titleOf(page, want), want);
  await openStatus(page);
  assert.equal(await titleOf(page, want), want, "the Status tab adds a suffix to the title");
});

// setTitle cuts the repo name to 40 characters, so a longer name shows its first 40.
test("a repo name over 40 characters is cut to 40 in the title", async (t) => {
  const name = "Repo-" + "x".repeat(60);
  const page = await open(t, { meta: { identity: { name } } }); if (!page) return;
  const want = name.slice(0, 40) + " " + pageName();
  assert.equal(await titleOf(page, want), want);
});

// The static <title> in page.html is the page name. setTitle adds the repo name at run time.
test("page.html's static title is the page name, read from splice.py", () => {
  const staticTitle = html.match(/<title>([^<]*)<\/title>/);
  assert.ok(staticTitle, "page.html has no static <title>");
  assert.notEqual(staticTitle[1], "Queue", "page.html's static title is still the old name Queue");
  assert.equal(staticTitle[1], pageName());
});

// ---------------------------------------------------------------- one page: the phase rail at phone widths (lane c136)
// The rail's current phase carries a dot, so its name has the least room. From 320 to 540px of page
// width, in light and dark, with each of the five real phases (Clean up, Organize, Design, Roll out,
// Later) current in turn: no phase name may break inside a word, and the dot may not sit alone on a line
// below its name (design notes, item 16: 5 columns only while each name with the dot sits on one line).
// The sweep must cross the rail's change from 3 to 5 columns, or it pins nothing about where that change
// sits. Each word is measured with a Range: more than one client rect is a word on two lines. The dot is
// alone when its top is at or below the bottom of its name's last text line. The width is swept on one
// page with setViewportSize, so the rail re-lays out as it does when a phone turns or a window is dragged.
// The web fonts are blocked, so the rail is set in whatever fallback font the runner has, and a threshold
// that holds for that font may fail in a wider one. So each case runs twice: in the runner's own font, and
// with the page's --body forced to "DejaVu Sans", a wide font that the ubuntu CI images ship. The forced
// run proves the font applied (installed, set on the rail, measured in the rail), and fails, never skips,
// when it did not. The range reaches 540px so a threshold that rises for the wide font still shows 5 columns.

const RAIL_WIDTHS = Array.from({ length: 540 - 320 + 1 }, (_, i) => 320 + i);
const RAIL_FONTS = [{ label: "default", force: null }, { label: "DejaVu Sans", force: "DejaVu Sans" }];
const RAIL_PHASES = [["cleanup", "Clean up"], ["organize", "Organize"], ["design", "Design"], ["rollout", "Roll out"], ["later", "Later"]];
// Overrides --body on the page (the rail sets its text with var(--body)); the !important beats the :root rule.
const forceRailFont = (page, family) => page.addStyleTag({ content: `:root { --body: "${family}", sans-serif !important; }` });
// Measures "Organize" (a word of the rail) as the rail sets it, and again in a probe span with the same
// weight and size but a named family. An installed family measures the same with a serif or a monospace
// fallback; a missing one does not. The "no such font" pair shows the probe tells two fallbacks apart on
// this runner.
const railFontProbe = (page, family) => page.evaluate((family) => {
  const nm = [...document.querySelectorAll(".prail .nm > span:first-child")].find((s) => s.textContent === "Organize");
  const cs = getComputedStyle(nm);
  const range = document.createRange();
  range.selectNodeContents(document.createTreeWalker(nm, NodeFilter.SHOW_TEXT).nextNode());
  const width = (fam) => {
    const s = document.createElement("span");
    s.textContent = "Organize";
    s.style.cssText = `position:absolute;visibility:hidden;white-space:nowrap;letter-spacing:${cs.letterSpacing};font:${cs.fontWeight} ${cs.fontSize} ${fam}`;
    document.body.append(s);
    const w = s.getBoundingClientRect().width;
    s.remove();
    return w;
  };
  return {
    family: cs.fontFamily, rail: range.getBoundingClientRect().width,
    namedSerif: width(`"${family}", serif`), namedMono: width(`"${family}", monospace`),
    noneSerif: width('"No Such Font 7f3a", serif'), noneMono: width('"No Such Font 7f3a", monospace'),
  };
}, family);
const assertRailFont = async (page, family) => {
  const f = await railFontProbe(page, family);
  assert.ok(f.family.startsWith(`"${family}"`), `the rail's font-family is ${f.family}, not "${family}": the forced font did not reach the rail`);
  assert.notEqual(f.noneSerif, f.noneMono, "the font probe cannot tell a serif fallback from a monospace one on this runner");
  assert.ok(Math.abs(f.namedSerif - f.namedMono) < 0.01, `"${family}" is not installed on this runner (the probe fell back to another font), so this sweep would prove nothing about it`);
  assert.ok(Math.abs(f.rail - f.namedSerif) < 0.05, `the rail sets "Organize" ${f.rail}px wide, but "${family}" sets it ${f.namedSerif}px: the rail is not rendered in the forced font`);
};
const railWords = (page) => page.evaluate(() => {
  const words = [], split = [];
  let dotAlone = false;
  for (const nm of document.querySelectorAll(".prail .nm > span:first-child")) {
    const walk = document.createTreeWalker(nm, NodeFilter.SHOW_TEXT);
    let lastBottom = -Infinity;
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      for (const m of n.textContent.matchAll(/\S+/g)) {
        const r = document.createRange();
        r.setStart(n, m.index); r.setEnd(n, m.index + m[0].length);
        words.push(m[0]);
        const rects = r.getClientRects();
        if (rects.length > 1) split.push(m[0]);
        for (const q of rects) lastBottom = Math.max(lastBottom, q.bottom);
      }
    }
    const dot = nm.querySelector(".here");
    if (dot && dot.getBoundingClientRect().top >= lastBottom) dotAlone = true;
  }
  const rail = document.querySelector(".prail");
  return { words, split, dotAlone, cols: getComputedStyle(rail).gridTemplateColumns.split(" ").length, box: Math.round(rail.getBoundingClientRect().width) };
});
// "372-380px Organize current: dot alone on a line": the widths of each kind of hit as runs.
const hitRuns = (hits) => {
  const byKey = new Map();
  for (const { w, key } of hits) byKey.set(key, [...(byKey.get(key) || []), w]);
  return [...byKey].map(([key, ws]) => {
    const runs = [];
    for (const w of ws) { const last = runs[runs.length - 1]; if (last && last[1] === w - 1) last[1] = w; else runs.push([w, w]); }
    return runs.map(([a, b]) => (a === b ? a : a + "-" + b) + "px").join(", ") + " " + key;
  }).join("; ");
};

for (const scheme of ["light", "dark"]) {
  for (const [phase, name] of RAIL_PHASES) {
    for (const font of RAIL_FONTS) {
      test(`no phase name breaks inside a word or leaves its dot alone at any page width from 320 to 540px, ${name} current, ${scheme} theme, ${font.label} font`, async (t) => {
        const page = await open(t, { pageHtml: mergedPage("--current", phase), viewport: { width: RAIL_WIDTHS[0], height: 900 }, scheme }); if (!page) return;
        if (font.force) await forceRailFont(page, font.force);
        await openStatus(page);
        assert.equal(await page.locator(".prail > button").count(), 5, "the rail does not hold the five phases");
        assert.equal(await page.locator(".prail .here").count(), 1, "the rail marks no single current phase");
        assert.equal(await page.locator(".prail .nm:has(.here) > span:first-child").textContent(), name, "the current phase is not " + name);
        if (font.force) await assertRailFont(page, font.force);
        const hits = [], cols = new Set();
        for (const w of RAIL_WIDTHS) {
          await page.setViewportSize({ width: w, height: 900 });
          const m = await railWords(page); // the reads force a layout, so the container queries have resolved
          assert.deepEqual(m.words, ["Clean", "up", "Organize", "Design", "Roll", "out", "Later"], `${w}px: the rail's words`);
          cols.add(m.cols);
          for (const word of m.split) hits.push({ w, key: `${name} current, ${font.label} font: "${word}" breaks inside the word`, box: m.box });
          if (m.dotAlone) hits.push({ w, key: `${name} current, ${font.label} font: dot alone on a line`, box: m.box });
        }
        assert.deepEqual([...cols].sort(), [3, 5], "the sweep does not cross the rail's change from 3 to 5 columns, so it pins no threshold; columns seen: " + [...cols]);
        assert.equal(hits.length, 0, `the rail breaks at ${hits[0] && hits[0].w}px page width (rail box ${hits[0] && hits[0].box}px), ${hits[0] && hits[0].key}; every hit: ${hitRuns(hits)}`);
      });
    }
  }
}

test("merged_page.py refuses --current with --no-roadmap, since a repo with no roadmap has no current phase", () => {
  const r = spawnSync(process.env.PYTHON || "python3", [MERGED, "--page", PAGE, "--no-roadmap", "--current", "organize"], { encoding: "utf8" });
  assert.equal(r.status, 2, "exit status of the refusal: " + r.status);
  assert.match(r.stderr, /--current needs a roadmap/);
  assert.equal(r.stdout, "", "the refusal printed a page");
});

// ---------------------------------------------------------------- one page: the phase list draws every step (Status tab)
// The rail holds one button per phase that has a step: the five known phases in their order, and any other
// phase id a step carries, ordered by its smallest order and then by id, with Later last. A step with no
// phase, or an empty one, is in "No phase". Every fixture goes through merged_page.py --data, so the roadmap
// build bakes it as it bakes a real repo, and the case checks the baked steps before it asks the page anything.

// The steps of a fixture, keyed by file stem (the step id). A row is [id, phase, order, status]; an undefined
// phase leaves the key out, so the step has no phase at all.
const stepsOf = (rows) => Object.fromEntries(rows.map(([id, phase, order, status = "todo"]) => [id, {
  title: "Step " + id, status, order, note: "n", updatedAt: "2026-10-26T00:00:00Z", ...(phase === undefined ? {} : { phase }),
}]));
// The page built from a fixture. make_repo adds a cleanup step c1 unless the fixture names one, so a fixture names its own c1.
function phasePage(steps, phases = {}) {
  assert.ok(steps.c1, "the fixture names no c1: make_repo would add its own cleanup step c1");
  return mergedPage("--data", JSON.stringify({ steps, meta: { phases } }));
}
// Each step's phase, id to phase, null where the step has none. Fixture and baked data are compared in this form.
const phaseOf = (steps) => Object.fromEntries(Object.entries(steps).map(([id, s]) => [id, s.phase ?? null]));
// Before any phase is asked about: the build bakes every fixture step under the fixture's phase, so a red below is the page's.
async function assertBaked(page, steps) {
  const baked = await page.evaluate(() => Object.fromEntries(Object.entries(window.ROADMAP_DATA.steps).map(([id, s]) => [id, s.phase ?? null])));
  assert.deepEqual(baked, phaseOf(steps), "the roadmap build did not bake the fixture's steps under their phases, so the page is not the one the case set up");
}
// The names on the rail, in order, one per phase button.
const railNames = (page) => page.locator(".prail > button .nm > span:first-child").allTextContents();
// The step ids the phase list draws now: the rows of the phase shown, open and done.
const listedIds = (page) => page.locator("#svPhases [data-row]").evaluateAll((rows) => rows.map((r) => r.getAttribute("data-row")));
// Presses each rail button in turn, and returns the step ids the phase list drew under each button's name.
async function listedByPhase(page) {
  // A null prototype: a phase named __proto__ would otherwise set the prototype of a plain object, not a key.
  const out = Object.create(null);
  const count = await page.locator(".prail > button").count();
  for (let i = 0; i < count; i++) {
    const button = page.locator(".prail > button").nth(i);
    const name = await button.locator(".nm > span:first-child").textContent();
    await button.click();
    out[name] = await listedIds(page);
  }
  return out;
}

// (a) The degen shape: every step in one foreign phase. The tab is not blank, and each step's title is drawn.
test("the phase list draws a repo whose steps all sit in one foreign phase: the phase shows, and every step title is drawn", async (t) => {
  const steps = stepsOf([["c1", "v2", 1, "active"], ["a2", "v2", 2], ["a3", "v2", 3, "done"]]);
  const page = await open(t, { pageHtml: phasePage(steps) }); if (!page) return;
  await assertBaked(page, steps);
  await openStatus(page);
  assert.deepEqual(await railNames(page), ["v2"], "the rail does not name the one phase the steps hold, v2: it shows the five known phases only");
  const titles = await page.locator("#svPhases .ttl").allTextContents();
  for (const [id, s] of Object.entries(steps)) assert.ok(titles.includes(s.title), `step ${id} (${s.title}) is not drawn in the phase list, though its phase v2 is shown`);
});

// (b) The home shape: known phases that hold steps, foreign phases by their smallest order, Later last.
test("the phase list draws a home-shaped repo: known phases that hold steps, then foreign phases by their first order, Later last, every step drawn", async (t) => {
  const steps = stepsOf([["c1", "now", 1], ["n2", "now", 2, "done"], ["d3", "duo", 4], ["d4", "duo", 5], ["o5", "owner", 7], ["l6", "later", 9]]);
  const page = await open(t, { pageHtml: phasePage(steps) }); if (!page) return;
  await assertBaked(page, steps);
  await openStatus(page);
  assert.deepEqual(await railNames(page), ["now", "duo", "owner", "Later"], "the rail does not hold the phases that have steps, foreign ones by their smallest order, Later last, and no empty known phase");
  const drawn = Object.values(await listedByPhase(page)).flat();
  for (const id of Object.keys(steps)) assert.ok(drawn.includes(id), `step ${id} is drawn under no phase of the rail: the phase list hides it`);
});

// (b, tie) Foreign phases whose smallest order is the same sit in id order. File order would put zeta first.
test("the phase list orders foreign phases with the same smallest order by id", async (t) => {
  const steps = stepsOf([["a1", "zeta", 5], ["c1", "zeta", 3], ["z2", "alpha", 3]]);
  const page = await open(t, { pageHtml: phasePage(steps) }); if (!page) return;
  await assertBaked(page, steps);
  await openStatus(page);
  assert.deepEqual(await railNames(page), ["alpha", "zeta"], "the rail does not put alpha before zeta: a tie on the smallest order goes by phase id");
});

// (b, current) Where the plan stands is the first shown phase with an open step. Now is shown but all done, so Duo is current.
test("the phase list: Where the plan stands names the first shown phase with an open step, Duo here, not Later", async (t) => {
  const steps = stepsOf([["c1", "now", 1, "done"], ["d3", "duo", 4], ["l6", "later", 9]]);
  const page = await open(t, { pageHtml: phasePage(steps) }); if (!page) return;
  await assertBaked(page, steps);
  await openStatus(page);
  assert.equal(await page.locator(".prail .here").count(), 1, "the rail marks no single current phase");
  assert.equal(await page.locator(".prail .nm:has(.here) > span:first-child").textContent(), "duo", "the current phase on the rail is not duo, the first shown phase with an open step");
  assert.equal(await page.locator("#svNow .ph").textContent(), "duo", "the Where the plan stands block does not name duo as the current phase");
});

// (c) A foreign phase takes its name from meta.phases.<id>.name when that is a non-empty string, else its id.
test("the phase list names a foreign phase from meta.phases when that name is a non-empty string, else by its id", async (t) => {
  const steps = stepsOf([["c1", "v2", 1], ["d3", "duo", 2], ["o5", "owner", 3]]);
  const phases = { v2: { name: "Version two" }, duo: { name: "" }, owner: { name: 7 } };
  const page = await open(t, { pageHtml: phasePage(steps, phases) }); if (!page) return;
  await assertBaked(page, steps);
  await openStatus(page);
  assert.deepEqual(await railNames(page), ["Version two", "duo", "owner"], "the rail does not name each foreign phase from meta.phases.<id>.name when it is a non-empty string, else by its id");
});

// (d) A step with no phase key, and one with an empty phase, are both drawn under one phase named No phase.
test("the phase list draws a step with no phase, or an empty one, under No phase", async (t) => {
  const steps = stepsOf([["c1", undefined, 1, "active"], ["e2", "", 2]]);
  const page = await open(t, { pageHtml: phasePage(steps) }); if (!page) return;
  await assertBaked(page, steps);
  await openStatus(page);
  assert.deepEqual(await railNames(page), ["No phase"], "the rail does not hold one No phase button for the steps with no phase");
  await page.locator(".prail > button", { hasText: "No phase" }).click();
  const ids = await listedIds(page);
  assert.ok(ids.includes("c1"), "step c1, with no phase key, is not drawn under No phase");
  assert.ok(ids.includes("e2"), "step e2, with an empty phase, is not drawn under No phase");
});

// (b, full size) The shape of claude-settings: the five known phases and seven more, two steps each, twenty-four in all.
// The orders run later, then the seven others, then the four known phases before Later. So a sort by order alone
// puts Later first, and a foreign phase with a small order must still sit between Roll out and Later.
test("the phase list at full size puts the seven others between Roll out and Later, by their smallest order, and draws every step", async (t) => {
  const others = ["now", "next", "page", "checks", "ci", "merge", "records"];
  const rows = [];
  let order = 1;
  for (const phase of ["later", ...others, "cleanup", "organize", "design", "rollout"]) for (const k of [1, 2]) rows.push([phase === "cleanup" && k === 1 ? "c1" : `${phase}-${k}`, phase, order++]);
  const steps = stepsOf(rows);
  const page = await open(t, { pageHtml: phasePage(steps) }); if (!page) return;
  await assertBaked(page, steps);
  await openStatus(page);
  assert.deepEqual(await railNames(page), ["Clean up", "Organize", "Design", "Roll out", ...others, "Later"], "the rail is not the known phases in their order, then the others by their smallest order, then Later last");
  const drawn = Object.values(await listedByPhase(page)).flat();
  for (const id of Object.keys(steps)) assert.ok(drawn.includes(id), `step ${id} is drawn under no phase of the rail: the phase list hides it`);
});

// Green control: the five known phases all hold steps, so the rail keeps the five names in today's order.
test("the phase list keeps the five known names in today's order when all five phases hold steps", async (t) => {
  const page = await open(t, { pageHtml: mergedPage("--current", "organize") }); if (!page) return;
  await openStatus(page);
  assert.deepEqual(await railNames(page), ["Clean up", "Organize", "Design", "Roll out", "Later"], "the five known names or their order changed");
});

// Phase ids that name a member of Object.prototype. The page keeps per-phase state in plain objects, so each id must
// read as its own key, never as an inherited member: its steps draw, and the rail names the phase by its id.
for (const name of ["__proto__", "constructor", "toString"]) {
  test(`the phase list draws every step of a phase named ${name}, and names that phase by its id`, async (t) => {
    const steps = stepsOf([["c1", name, 1, "active"], ["a2", name, 2], ["a3", name, 3, "done"]]);
    const page = await open(t, { pageHtml: phasePage(steps) }); if (!page) return;
    await assertBaked(page, steps);
    await openStatus(page);
    assert.deepEqual(await railNames(page), [name], `the rail does not name the one phase the steps hold, ${name}, by its id`);
    const drawn = Object.values(await listedByPhase(page)).flat();
    for (const id of Object.keys(steps)) assert.ok(drawn.includes(id), `step ${id} is not drawn in the phase ${name}`);
  });
}

// A phase that is not a non-empty string (a number, null, an object) is no phase: its step goes under No phase.
// An object phase on an open step crashes the roadmap build (skills/roadmap/build.py upkeep, an unhashable dict), so
// that case's step is done: it tests the page's handling, not the build's crash, which the case reports elsewhere.
for (const [label, phase, status] of [["a number", 5, "active"], ["null", null, "active"], ["an object", {}, "done"]]) {
  test(`the phase list draws a step whose phase is ${label} under No phase`, async (t) => {
    const steps = stepsOf([["c1", phase, 1, status]]);
    const page = await open(t, { pageHtml: phasePage(steps) }); if (!page) return;
    await assertBaked(page, steps);
    await openStatus(page);
    assert.deepEqual(await railNames(page), ["No phase"], `the rail does not hold one No phase button for a step whose phase is ${label}`);
    await page.locator(".prail > button", { hasText: "No phase" }).click();
    assert.ok((await listedIds(page)).includes("c1"), `step c1, whose phase is ${label}, is not drawn under No phase`);
  });
}

// ---------------------------------------------------------------- the stalled band on the Status tab (lane doing-needs-live-lane)
// The build writes window.ROADMAP_BUILD.stalled and the page only draws it. These cases set that key on a built page, so the
// band is proved apart from the build. Mockup: docs/design/stalled-band.html, option "Words once": the action once in the
// band, and the rows carry marks only.

// The built page's ROADMAP_BUILD block: the one regex that reads it. withStalled rewrites it; the --live case reads it back.
const BUILD_BLOCK = /window\.ROADMAP_BUILD = (\{.*\});<\/script>/;
function withStalled(html, stalled) {
  assert.match(html, BUILD_BLOCK, "the built page has no ROADMAP_BUILD block to set the stalled read on");
  return html.replace(BUILD_BLOCK, (_, j) => {
    const b = JSON.parse(j);
    if (stalled === undefined) delete b.stalled; else b.stalled = stalled;
    return "window.ROADMAP_BUILD = " + JSON.stringify(b).replace(/</g, "\\u003c") + ";</script>";
  });
}
const NO_ITEMS = { itemsWhy: "" };
// c1, a2, a5 stalled (a2 landed, a5 with a pause that holds no one to decide it); a3 paused; a4 has a live lane; d6 is doing with a live lane.
function stalledFixture() {
  const steps = stepsOf([["c1", "cleanup", 1, "doing"], ["a2", "cleanup", 2, "doing"], ["a3", "cleanup", 3, "doing"], ["a4", "cleanup", 4, "active"], ["a5", "cleanup", 5, "doing"], ["d6", "cleanup", 6, "doing"]]);
  steps.a3.paused = { why: "Waits for a month of CI numbers.", decides: "owner", at: "2026-11-05T16:20:00-06:00", by: "triage" };
  return steps;
}
const STALLED = {
  why: "", steps: [{ id: "c1", fix: "todo" }, { id: "a2", fix: ["#9"] }, { id: "a5", fix: "todo" }], paused: ["a3"],
  badPause: [{ id: "a5", why: "it names no one to decide" }], items: [{ n: 14, lane: "fold-done-steps" }], itemsWhy: "",
};
const stalledPage = (stalled) => withStalled(phasePage(stalledFixture()), stalled);
const band = (page) => page.locator("#stBand");
// The band's text on one line. A page with no band fails here by name, before a text read waits out its timeout.
async function bandText(page) {
  assert.equal(await band(page).count(), 1, "the Status tab draws no stalled band (#stBand)");
  return (await band(page).textContent()).replace(/\s+/g, " ");
}

test("the stalled band counts each stalled step and each item whose lane is gone, and names what to do once", async (t) => {
  const page = await open(t, { pageHtml: stalledPage(STALLED) }); if (!page) return;
  await openStatus(page);
  const text = await bandText(page);
  assert.match(text, /Stalled:\s*4/, "the band does not count 3 steps and 1 item as Stalled: 4: " + text);
  for (const id of ["c1", "a2", "a5"]) assert.equal(await band(page).locator(`button[data-go="${id}"]`).count(), 1, `the band does not list step ${id}`);
  assert.match(text, /Step c1/, "the band shows no step title");
  assert.match(text, /done: landed in #9/, "a landed step does not say it is done and where it landed");
  assert.match(text, /Pause not counted: it names no one to decide/, "a pause the build refused is not said");
  assert.match(text, /Item\s*14/);
  assert.match(text, /fold-done-steps/);
  assert.match(text, /lane gone/);
  assert.equal((text.match(/Triage resumes, pauses or closes each/g) || []).length, 1, "the action words are not in the band exactly once");
  assert.equal(await shows(page, /Resume, pause or done/), false, "a row repeats the action words");
  assert.equal(await band(page).evaluate((el) => el.classList.contains("hot")), true, "a band with something stalled has no red edge");
});

test("the paused fold stays closed while something is stalled, and gives why, who decides and when", async (t) => {
  const page = await open(t, { pageHtml: stalledPage(STALLED) }); if (!page) return;
  await openStatus(page);
  const fold = band(page).locator("details.pz");
  assert.equal(await fold.count(), 1, "the band has no paused fold");
  assert.equal(await fold.evaluate((d) => d.open), false, "the paused fold is open with steps stalled");
  assert.match((await fold.locator("summary").textContent()).replace(/\s+/g, " "), /Paused:\s*1/);
  await fold.locator("summary").click();
  const text = (await fold.textContent()).replace(/\s+/g, " ");
  assert.match(text, /Step a3/);
  assert.match(text, /Waits for a month of CI numbers\./);
  assert.match(text, /Owner decides; paused Nov 5, 16:20 CST/);
});

test("with nothing stalled but a pause the band says so and opens the paused fold", async (t) => {
  const page = await open(t, { pageHtml: stalledPage({ why: "", steps: [], paused: ["a3"], badPause: [], items: [], ...NO_ITEMS }) }); if (!page) return;
  await openStatus(page);
  const text = await bandText(page);
  assert.match(text, /No stalled step/);
  assert.doesNotMatch(text, /Stalled:/);
  assert.equal(await band(page).locator("details.pz").evaluate((d) => d.open), true, "the paused fold is shut with nothing stalled");
  assert.equal(await band(page).evaluate((el) => el.classList.contains("hot")), false, "an empty band has a red edge");
});

test("with nothing stalled and nothing paused the band is one quiet line", async (t) => {
  const page = await open(t, { pageHtml: stalledPage({ why: "", steps: [], paused: [], badPause: [], items: [], ...NO_ITEMS }) }); if (!page) return;
  await openStatus(page);
  const text = await bandText(page);
  assert.match(text, /No stalled step/);
  assert.equal(await band(page).locator("li, details").count(), 0, "a zero band draws more than its one line");
});

test("steps not read: the band says not read and why, never none and never zero", async (t) => {
  const unread = { why: "unknown (steps unknown)", steps: null, paused: [], badPause: [], items: null, itemsWhy: "unknown (steps unknown)" };
  for (const [name, html] of [["a null read", stalledPage(unread)], ["a build with no stalled key", stalledPage(undefined)]]) {
    const page = await open(t, { pageHtml: html }); if (!page) return;
    await openStatus(page);
    const text = await bandText(page);
    assert.match(text, /not read/i, name + ": the band does not say not read: " + text);
    assert.doesNotMatch(text, /No stalled step|Stalled:\s*\d/, name + ": an unread band claims a count: " + text);
  }
  const page = await open(t, { pageHtml: stalledPage(unread) }); if (!page) return;
  await openStatus(page);
  assert.match(await bandText(page), /steps unknown/, "the band hides the build's reason");
});

test("items not read: the step list shows and the items part says not read, never none", async (t) => {
  const page = await open(t, { pageHtml: stalledPage({ why: "", steps: [{ id: "c1", fix: "todo" }], paused: [], badPause: [], items: null, itemsWhy: "unknown (live file rows carry no lane yet)" }) }); if (!page) return;
  await openStatus(page);
  const text = await bandText(page);
  assert.match(text, /Stalled:\s*1/, text);
  assert.match(text, /Waiting items/);
  assert.match(text, /not read/i);
  assert.doesNotMatch(text, /\bnone\b|No waiting item/i, "an unread items part reads as none");
});

test("a stalled step's row carries a Stalled mark, a paused one a Paused mark, and each says its word once", async (t) => {
  const page = await open(t, { pageHtml: stalledPage(STALLED) }); if (!page) return;
  await openStatus(page);
  assert.equal(await page.locator('#s-c1 [aria-label="Stalled"]').count(), 1, "the stalled row has no Stalled mark");
  assert.equal(await page.locator('#s-a3 [aria-label="Paused"]').count(), 1, "the paused row has no Paused mark");
  assert.equal(await page.locator('#s-a4 .meta .tag').count(), 0, "a step with a live lane carries a tag");
  assert.doesNotMatch(await page.locator("#s-c1 .meta").innerText(), /Stalled/, "the row repeats the word the band says");
  assert.match(await page.locator("#s-c1 .rrow").getAttribute("aria-label"), /Stalled/, "a screen reader does not hear the row is stalled");
  assert.match(await page.locator("#s-a3 .rrow").getAttribute("aria-label"), /Paused/);
});

// The where-you-are line and the Latest changes feed read a stalled step's state. Its status is active, as a doing step's is.
const STALLED_C1 = { why: "", steps: [{ id: "c1", fix: "todo" }], paused: [], badPause: [], items: [], ...NO_ITEMS };
const whereLine = async (page) => (await page.locator("#svNow > div").first().textContent()).replace(/\s+/g, " ");
const doingNowRow = (page, id) => page.locator("#svNow > div", { has: page.getByRole("heading", { name: "Doing now", exact: true }) }).locator(`li:has(.id:text-is("${id}"))`);
test("the where-you-are line does not count a stalled step as in progress", async (t) => {
  const page = await open(t, { pageHtml: withStalled(phasePage(stepsOf([["c1", "cleanup", 1, "doing"]])), STALLED_C1) }); if (!page) return;
  await openStatus(page);
  // Scope: step c1 is in Doing now, marked Stalled.
  assert.equal(await doingNowRow(page, "c1").locator('[role="img"][aria-label="Stalled"]').count(), 1, "step c1 is not in Doing now, marked Stalled");
  const where = await whereLine(page);
  assert.doesNotMatch(where, /in progress/, "the where-you-are line counts the stalled step as in progress: " + where);
});
test("the Latest changes row of a stalled step reads Stalled, not In progress", async (t) => {
  const page = await open(t, { pageHtml: withStalled(phasePage(stepsOf([["c1", "cleanup", 1, "doing"]])), STALLED_C1) }); if (!page) return;
  await openStatus(page);
  assert.equal(await doingNowRow(page, "c1").locator('[role="img"][aria-label="Stalled"]').count(), 1, "step c1 is not in Doing now, marked Stalled");
  const row = page.locator("#svSide ul.feed li", { has: page.locator('button[data-go="c1"]') });
  assert.equal(await row.count(), 1, "step c1 has no row in Latest changes");
  const mark = row.locator('[role="img"]');
  assert.equal(await mark.count(), 1, "the Latest changes row of step c1 has no state mark");
  const label = await mark.getAttribute("aria-label");
  assert.notEqual(label, "In progress", "the Latest changes row of stalled step c1 reads In progress");
  assert.equal(label, "Stalled", "the Latest changes row of stalled step c1 does not read Stalled");
});
test("a doing step that is not stalled still counts as in progress in the where-you-are line", async (t) => {
  const steps = stepsOf([["d6", "cleanup", 1, "doing"], ["c1", "cleanup", 2, "todo"]]);
  const page = await open(t, { pageHtml: withStalled(phasePage(steps), { why: "", steps: [], paused: [], badPause: [], items: [], ...NO_ITEMS }) }); if (!page) return;
  await openStatus(page);
  const where = await whereLine(page);
  assert.match(where, /1 in progress/, "the where-you-are line does not count the doing step as in progress: " + where);
});

test("the Changes log row of a stalled step reads Stalled, not In progress", async (t) => {
  const page = await open(t, { pageHtml: withStalled(phasePage(stepsOf([["c1", "cleanup", 1, "doing"]])), STALLED_C1) }); if (!page) return;
  await openStatus(page);
  const row = page.locator("#svDays .ev", { has: page.locator('button[data-go="c1"]') });
  assert.equal(await row.count(), 1, "step c1 has no row in the Changes log");
  const mark = row.locator('[role="img"]');
  assert.equal(await mark.count(), 1, "the Changes log row of step c1 has no state mark");
  const label = await mark.getAttribute("aria-label");
  assert.notEqual(label, "In progress", "the Changes log row of stalled step c1 reads In progress");
  assert.equal(label, "Stalled", "the Changes log row of stalled step c1 does not read Stalled");
});
test("a doing step that is not stalled still reads In progress in the Changes log", async (t) => {
  const steps = stepsOf([["d6", "cleanup", 1, "doing"], ["c1", "cleanup", 2, "todo"]]);
  const page = await open(t, { pageHtml: withStalled(phasePage(steps), { why: "", steps: [], paused: [], badPause: [], items: [], ...NO_ITEMS }) }); if (!page) return;
  await openStatus(page);
  const row = page.locator("#svDays .ev", { has: page.locator('button[data-go="d6"]') });
  assert.equal(await row.count(), 1, "step d6 has no row in the Changes log");
  assert.equal(await row.locator('[role="img"]').getAttribute("aria-label"), "In progress", "the Changes log row of the doing step does not read In progress");
});

// A paused step keeps status active, as a stalled one does. The count, the Latest changes feed and the Changes log never read it In progress.
const PAUSED_STALL = { why: "", steps: [], paused: ["a3"], badPause: [], items: [], ...NO_ITEMS };
const pausedSteps = () => {
  const s = stepsOf([["a3", "cleanup", 1, "doing"], ["c1", "cleanup", 2, "todo"]]);
  s.a3.paused = { why: "Waits for a month of CI numbers.", decides: "owner", at: "2026-11-05T16:20:00-06:00", by: "triage" };
  return s;
};
test("the where-you-are line does not count a paused step as in progress", async (t) => {
  const page = await open(t, { pageHtml: withStalled(phasePage(pausedSteps()), PAUSED_STALL) }); if (!page) return;
  await openStatus(page);
  // Scope: step a3 is in Doing now, marked Paused.
  assert.equal(await doingNowRow(page, "a3").locator('[role="img"][aria-label="Paused"]').count(), 1, "step a3 is not in Doing now, marked Paused");
  const where = await whereLine(page);
  assert.doesNotMatch(where, /in progress/, "the where-you-are line counts the paused step as in progress: " + where);
});
test("the Latest changes row of a paused step reads Paused, not In progress", async (t) => {
  const page = await open(t, { pageHtml: withStalled(phasePage(pausedSteps()), PAUSED_STALL) }); if (!page) return;
  await openStatus(page);
  assert.equal(await doingNowRow(page, "a3").locator('[role="img"][aria-label="Paused"]').count(), 1, "step a3 is not in Doing now, marked Paused");
  const row = page.locator("#svSide ul.feed li", { has: page.locator('button[data-go="a3"]') });
  assert.equal(await row.count(), 1, "step a3 has no row in Latest changes");
  const mark = row.locator('[role="img"]');
  assert.equal(await mark.count(), 1, "the Latest changes row of step a3 has no state mark");
  const label = await mark.getAttribute("aria-label");
  assert.notEqual(label, "In progress", "the Latest changes row of paused step a3 reads In progress");
  assert.equal(label, "Paused", "the Latest changes row of paused step a3 does not read Paused");
});
test("the Changes log row of a paused step reads Paused, not In progress", async (t) => {
  const page = await open(t, { pageHtml: withStalled(phasePage(pausedSteps()), PAUSED_STALL) }); if (!page) return;
  await openStatus(page);
  assert.equal(await doingNowRow(page, "a3").locator('[role="img"][aria-label="Paused"]').count(), 1, "step a3 is not in Doing now, marked Paused");
  const row = page.locator("#svDays .ev", { has: page.locator('button[data-go="a3"]') });
  assert.equal(await row.count(), 1, "step a3 has no row in the Changes log");
  const mark = row.locator('[role="img"]');
  assert.equal(await mark.count(), 1, "the Changes log row of step a3 has no state mark");
  const label = await mark.getAttribute("aria-label");
  assert.notEqual(label, "In progress", "the Changes log row of paused step a3 reads In progress");
  assert.equal(label, "Paused", "the Changes log row of paused step a3 does not read Paused");
});
test("a doing step that is not stalled or paused reads In progress in all three places", async (t) => {
  const steps = stepsOf([["d6", "cleanup", 1, "doing"], ["c1", "cleanup", 2, "todo"]]);
  const page = await open(t, { pageHtml: withStalled(phasePage(steps), { why: "", steps: [], paused: [], badPause: [], items: [], ...NO_ITEMS }) }); if (!page) return;
  await openStatus(page);
  const where = await whereLine(page);
  assert.match(where, /1 in progress/, "the where-you-are line does not count the doing step as in progress: " + where);
  const feedMark = page.locator("#svSide ul.feed li", { has: page.locator('button[data-go="d6"]') }).locator('[role="img"]');
  assert.equal(await feedMark.getAttribute("aria-label"), "In progress", "the Latest changes row of the doing step does not read In progress");
  const logMark = page.locator("#svDays .ev", { has: page.locator('button[data-go="d6"]') }).locator('[role="img"]');
  assert.equal(await logMark.getAttribute("aria-label"), "In progress", "the Changes log row of the doing step does not read In progress");
});

// The phase bars draw one cell per step: done, then active, then blocked. A stalled or paused step keeps status active, so a bar that
// counts the status alone draws it as active. The bars are aria-hidden, so the cells are read by their class. stalledFixture: c1 stalled,
// a3 paused, a5 stalled, a4 and d6 in progress. Each bar must show two active cells, and the where-you-are bar already does.
async function actCells(page, scope) {
  assert.equal(await page.locator(`${scope} .segbar`).count(), 1, `${scope} has no phase bar (.segbar)`);
  return page.locator(`${scope} .segbar i.act`).count();
}
async function stalledPaused(page) {
  assert.equal(await doingNowRow(page, "c1").locator('[role="img"][aria-label="Stalled"]').count(), 1, "step c1 is not in Doing now, marked Stalled");
  assert.equal(await doingNowRow(page, "a3").locator('[role="img"][aria-label="Paused"]').count(), 1, "step a3 is not in Doing now, marked Paused");
  assert.equal(await actCells(page, "#svNow"), 2, "the where-you-are bar does not draw the two steps in progress as active");
}
test("the rail's phase bar draws no stalled or paused step as active", async (t) => {
  const page = await open(t, { pageHtml: stalledPage(STALLED) }); if (!page) return;
  await openStatus(page);
  await stalledPaused(page);
  const act = await actCells(page, '#svRail button[data-phase="cleanup"]');
  assert.equal(act, 2, `the rail's cleanup bar draws ${act} active cells for two steps in progress: a stalled or paused step is drawn as active`);
});
test("the phase head's bar draws no stalled or paused step as active", async (t) => {
  const page = await open(t, { pageHtml: stalledPage(STALLED) }); if (!page) return;
  await openStatus(page);
  await stalledPaused(page);
  const act = await actCells(page, "#svPhases .ph-head");
  assert.equal(act, 2, `the phase head's bar draws ${act} active cells for two steps in progress: a stalled or paused step is drawn as active`);
});

test("Doing now shows the stalled or paused mark in place of the in-progress mark", async (t) => {
  const page = await open(t, { pageHtml: stalledPage(STALLED) }); if (!page) return;
  await openStatus(page);
  // Scoped to the Doing now list: Up next draws its own li for each step, so #svNow alone matches those too.
  const doingNow = page.locator("#svNow > div", { has: page.getByRole("heading", { name: "Doing now", exact: true }) });
  const row = (id) => doingNow.locator(`li:has(.id:text-is("${id}"))`);
  for (const id of ["c1", "a3", "d6"]) assert.equal(await row(id).count(), 1, `step ${id} is not in Doing now`);
  const mark = async (id) => { assert.equal(await row(id).locator('[role="img"]').count(), 1, `step ${id} in Doing now has no state mark`); return row(id).locator('[role="img"]').getAttribute("aria-label"); };
  assert.equal(await mark("c1"), "Stalled");
  assert.equal(await mark("a3"), "Paused");
  assert.equal(await row("a4").count(), 1, "step a4 is not in Doing now, so its mark is not read");
  assert.equal(await row("a4").locator('[role="img"]').count(), 0, "a step with a live lane shows a state mark");
});

test("a doing step with a live lane reads In progress, not To do", async (t) => {
  const page = await open(t, { pageHtml: stalledPage({ why: "", steps: [], paused: [], badPause: [], items: [], ...NO_ITEMS }) }); if (!page) return;
  await openStatus(page);
  assert.equal(await page.locator("#s-d6").count(), 1, "step d6 has no row in the Status list");
  assert.match(await page.locator("#s-d6 .rrow").getAttribute("aria-label"), /In progress/, "a doing step does not read In progress");
  assert.equal(await page.locator("#s-d6").evaluate((li) => li.classList.contains("active")), true);
});

test("zero stalled steps with the items not read: the band does not say No stalled step, and shows the items not-read line", async (t) => {
  const page = await open(t, { pageHtml: stalledPage({ why: "", steps: [], paused: [], badPause: [], items: null, itemsWhy: "unknown (live file rows carry no lane yet)" }) }); if (!page) return;
  await openStatus(page);
  const text = await bandText(page);
  assert.doesNotMatch(text, /No stalled step/, "the band says No stalled step with its items not read: " + text);
  assert.match(text, /Waiting items/, "the band shows no waiting-items part: " + text);
  assert.match(text, /not read/i, "the waiting-items part does not say not read: " + text);
});

test("items not read: the line says fixed words, and the build's reason sits behind a closed What the build said", async (t) => {
  const page = await open(t, { pageHtml: stalledPage({ why: "", steps: [{ id: "c1", fix: "todo" }], paused: [], badPause: [], items: null, itemsWhy: "unknown (live file rows carry no lane yet)" }) }); if (!page) return;
  await openStatus(page);
  const shown = await band(page).innerText();
  assert.doesNotMatch(shown, /live file rows carry no lane yet/, "the build's reason for the items shows inline: " + JSON.stringify(shown));
  assert.match(shown, /not read/i, "the waiting-items line does not say not read: " + JSON.stringify(shown));
  const why = band(page).locator("details").filter({ hasText: "live file rows carry no lane yet" });
  assert.equal(await why.count(), 1, "the build's reason for the items is in no What the build said disclosure");
  assert.equal(await why.evaluate((d) => d.open), false, "the items' What the build said disclosure is open");
});

test("a paused row's time sits inside a .num element", async (t) => {
  const page = await open(t, { pageHtml: stalledPage(STALLED) }); if (!page) return;
  await openStatus(page);
  const fold = band(page).locator("details.pz");
  assert.equal(await fold.count(), 1, "the band has no paused fold");
  await fold.locator("summary").click();
  const times = await fold.locator("li .num").allTextContents();
  assert.ok(times.some((x) => /16:20/.test(x)), "the paused time of step a3 is not inside a .num element: " + JSON.stringify(times));
});

// In progress tells the owner that someone is working on the step. A stalled or paused step has no one working on it, so its row must read its own word.
test("a stalled or paused row reads Stalled or Paused in its status, label and mark, never In progress", async (t) => {
  const page = await open(t, { pageHtml: stalledPage(STALLED) }); if (!page) return;
  await openStatus(page);
  for (const [id, word] of [["c1", "Stalled"], ["a3", "Paused"]]) {
    const row = page.locator(`#s-${id}`);
    assert.equal(await row.count(), 1, `step ${id} has no row in the Status list`);
    const status = (await row.locator(".rbody dd").first().textContent()).trim();
    assert.equal(status, word, `the status of step ${id} reads ${status}, not ${word}`);
    assert.doesNotMatch(await row.locator(".rrow").getAttribute("aria-label"), /In progress/, `the row label of step ${id} reads In progress`);
    assert.doesNotMatch(await row.textContent(), /In progress/, `the row of step ${id} says In progress`);
    assert.equal(await row.locator('[aria-label*="In progress"]').count(), 0, `a mark in the row of step ${id} is labelled In progress`);
  }
});

// ---------------------------------------------------------------- the row tint: a stalled row takes the stalled colour, a paused row none (lane nfp-stalled-row-tint)
// The tint and the edge are on the row's .rrow. A stalled row takes the page's own red tint, --holds mixed 14% into --surface as .dl.bad
// draws it, and a 3px left edge in --holds. A paused row takes no tint and a 3px left edge in --muted. The in-progress row (a4, with a live
// lane) keeps --acc-soft and --acc. A to-do row takes neither. Each expected value is computed on the row, in each scheme. Each row's mark is
// checked first, so a red names the tint or the edge and not the label.
// The probe helpers are copied from the roadmap test file, which does not export its own, and no shared test module holds one yet, so this file keeps a copy.
const probeOf = (loc, prop, value) => loc.evaluate((el, [p, v]) => {
  const s = document.createElement("span");
  s.style[p] = v;
  el.appendChild(s);
  const out = getComputedStyle(s)[p];
  s.remove();
  return out;
}, [prop, value]);
const computedOf = (loc, prop) => loc.evaluate((el, p) => getComputedStyle(el)[p], prop);
const STALLED_TINT = "color-mix(in srgb, var(--holds) 14%, var(--surface))";
test("the row tint: a stalled row's background is the stalled tint and its left edge --holds, in light and dark", async (t) => {
  const page = await open(t, { pageHtml: stalledPage(STALLED) }); if (!page) return;
  await openStatus(page);
  assert.equal(await page.locator('#s-c1 [aria-label="Stalled"]').count(), 1, "step c1 is not marked Stalled: there is no stalled row to tint");
  const row = page.locator("#s-c1 .rrow");
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    const bg = await computedOf(row, "backgroundColor"), wantBg = await probeOf(row, "backgroundColor", STALLED_TINT);
    assert.equal(bg, wantBg, `in ${scheme} the stalled row's background is ${bg}, not the stalled tint ${wantBg}`);
    const edge = await computedOf(row, "boxShadow"), wantEdge = await probeOf(row, "boxShadow", "inset 3px 0 0 var(--holds)");
    assert.equal(edge, wantEdge, `in ${scheme} the stalled row's left edge is ${edge}, not the 3px --holds edge ${wantEdge}`);
  }
});
test("the row tint: a paused row takes no tint and a 3px left edge in --muted, in light and dark", async (t) => {
  const page = await open(t, { pageHtml: stalledPage(STALLED) }); if (!page) return;
  await openStatus(page);
  assert.equal(await page.locator('#s-a3 [aria-label="Paused"]').count(), 1, "step a3 is not marked Paused: there is no paused row to clear");
  const row = page.locator("#s-a3 .rrow");
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    const bg = await computedOf(row, "backgroundColor"), wantBg = await probeOf(row, "backgroundColor", "transparent");
    assert.equal(bg, wantBg, `in ${scheme} the paused row keeps a tint: its background is ${bg}, not none`);
    const edge = await computedOf(row, "boxShadow"), wantEdge = await probeOf(row, "boxShadow", "inset 3px 0 0 var(--muted)");
    assert.equal(edge, wantEdge, `in ${scheme} the paused row's left edge is ${edge}, not the 3px --muted edge ${wantEdge}`);
  }
});
test("control: the row tint: an in-progress row keeps the --acc-soft tint and its 3px --acc edge, in light and dark", async (t) => {
  const page = await open(t, { pageHtml: stalledPage(STALLED) }); if (!page) return;
  await openStatus(page);
  assert.match(await page.locator("#s-a4 .rrow").getAttribute("aria-label"), /In progress/, "step a4 does not read In progress");
  const row = page.locator("#s-a4 .rrow");
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    const bg = await computedOf(row, "backgroundColor"), wantBg = await probeOf(row, "backgroundColor", "var(--acc-soft)");
    assert.equal(bg, wantBg, `in ${scheme} the in-progress row's background is ${bg}, not the --acc-soft tint ${wantBg}`);
    const edge = await computedOf(row, "boxShadow"), wantEdge = await probeOf(row, "boxShadow", "inset 3px 0 0 var(--acc)");
    assert.equal(edge, wantEdge, `in ${scheme} the in-progress row's left edge is ${edge}, not the 3px --acc edge ${wantEdge}`);
  }
});

// The stalled fixture has no to-do step, so the to-do control adds one (t7) to it, in the same phase.
const stalledWithTodoPage = () => {
  const steps = stalledFixture();
  Object.assign(steps, stepsOf([["t7", "cleanup", 7, "todo"]]));
  return withStalled(phasePage(steps), STALLED);
};
test("control: the row tint: a to-do row beside a stalled one keeps no tint and no stalled edge, in light and dark", async (t) => {
  const page = await open(t, { pageHtml: stalledWithTodoPage() }); if (!page) return;
  await openStatus(page);
  assert.equal(await page.locator('#s-c1 [aria-label="Stalled"]').count(), 1, "step c1 is not marked Stalled: there is no stalled row beside the to-do row");
  assert.match(await page.locator("#s-t7 .rrow").getAttribute("aria-label"), /To do/, "step t7 does not read To do");
  const row = page.locator("#s-t7 .rrow");
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    const bg = await computedOf(row, "backgroundColor"), wantBg = await probeOf(row, "backgroundColor", "transparent");
    assert.equal(bg, wantBg, `in ${scheme} the to-do row takes a tint: its background is ${bg}, not none`);
    const edge = await computedOf(row, "boxShadow"), wantEdge = await probeOf(row, "boxShadow", "none");
    assert.equal(edge, wantEdge, `in ${scheme} the to-do row has a left edge ${edge}, not none`);
  }
});
// A paused title keeps the in-progress title's weight: it is read against that title, not against a literal.
test("the row tint: a paused row's title has the in-progress title's font weight", async (t) => {
  const page = await open(t, { pageHtml: stalledPage(STALLED) }); if (!page) return;
  await openStatus(page);
  assert.equal(await page.locator('#s-a3 [aria-label="Paused"]').count(), 1, "step a3 is not marked Paused: there is no paused title to compare");
  assert.match(await page.locator("#s-a4 .rrow").getAttribute("aria-label"), /In progress/, "step a4 does not read In progress: there is no in-progress title to compare with");
  const paused = await computedOf(page.locator("#s-a3 .rrow .ttl"), "fontWeight"), active = await computedOf(page.locator("#s-a4 .rrow .ttl"), "fontWeight");
  assert.equal(paused, active, `the paused step's title is weight ${paused}, not the in-progress title's ${active}`);
});
// The paused title's match with the in-progress title means something only if that title is bolder than a plain one. With both titles
// plain, the paused match above passes, so this case fails: it is the anchor for that match.
test("the row tint: the in-progress title is bolder than a to-do title", async (t) => {
  const page = await open(t, { pageHtml: stalledWithTodoPage() }); if (!page) return;
  await openStatus(page);
  assert.match(await page.locator("#s-a4 .rrow").getAttribute("aria-label"), /In progress/, "step a4 does not read In progress");
  assert.match(await page.locator("#s-t7 .rrow").getAttribute("aria-label"), /To do/, "step t7 does not read To do");
  const active = await computedOf(page.locator("#s-a4 .rrow .ttl"), "fontWeight"), todo = await computedOf(page.locator("#s-t7 .rrow .ttl"), "fontWeight");
  assert.ok(Number(active) > Number(todo), `the in-progress title is weight ${active}, not bolder than the to-do title's ${todo}`);
});
// A paused row keeps no tint at rest, but takes the hover fill when the pointer is on it. The rule that gives it the fill is
// .rsteps .pzd-row > .rrow:hover: it outranks the paused row's own background: none, which the plain .rrow:hover fill cannot beat.
// The fill is read from a to-do row of the same page, hovered first, so no colour is copied from the page's CSS: a tint change moves both
// rows and the test follows. The to-do row's fill must not read transparent, or the test would pass on a page that draws no fill at all.
test("the row tint: a paused row takes the hover fill when the pointer is on it, in light and dark", async (t) => {
  const page = await open(t, { pageHtml: stalledWithTodoPage() }); if (!page) return;
  await openStatus(page);
  assert.equal(await page.locator('#s-a3 [aria-label="Paused"]').count(), 1, "step a3 is not marked Paused: there is no paused row to hover");
  const row = page.locator("#s-a3 .rrow"), todo = page.locator("#s-t7 .rrow");
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    await todo.hover();
    const wantBg = await computedOf(todo, "backgroundColor");
    assert.notEqual(wantBg, await probeOf(todo, "backgroundColor", "transparent"), `in ${scheme} the hovered to-do row's fill ${wantBg} reads as transparent here, so there is no fill to compare`);
    await row.hover();
    const bg = await computedOf(row, "backgroundColor");
    assert.equal(bg, wantBg, `in ${scheme} the hovered paused row's background is ${bg}, not the to-do row's hover fill ${wantBg}`);
  }
});
// Control: a hovered to-do row takes the fill that the page's .rrow:hover rule declares, and no rule overrides it. The expected fill is read
// from that rule's declaration, not from a row: a row compared with itself could never fail. A tint change moves the declaration and the
// test follows. The declared fill must not read transparent, or the test would pass on a page that draws no fill at all. It stays green on a page without the paused-row hover rule.
test("control: the row tint: a to-do row takes the hover fill when the pointer is on it, in light and dark", async (t) => {
  const page = await open(t, { pageHtml: stalledWithTodoPage() }); if (!page) return;
  await openStatus(page);
  assert.match(await page.locator("#s-t7 .rrow").getAttribute("aria-label"), /To do/, "step t7 does not read To do");
  const row = page.locator("#s-t7 .rrow");
  const declared = await page.evaluate(() => {
    const find = (rules) => {
      for (const r of rules) {
        if (r.selectorText === ".rrow:hover") return r.style.getPropertyValue("background");
        if (r.cssRules) { const v = find(r.cssRules); if (v) return v; }
      }
      return "";
    };
    for (const sheet of document.styleSheets) {
      let v = "";
      try { v = find(sheet.cssRules); } catch { continue; }  // a sheet from another origin has no readable rules
      if (v) return v;
    }
    return "";
  });
  assert.ok(declared, "the page has no .rrow:hover rule with a background to read the hover fill from");
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    const wantBg = await probeOf(row, "backgroundColor", declared);
    assert.notEqual(wantBg, await probeOf(row, "backgroundColor", "transparent"), `in ${scheme} the .rrow:hover fill ${declared} reads as transparent here, so there is no fill to compare`);
    await row.hover();
    const bg = await computedOf(row, "backgroundColor");
    assert.equal(bg, wantBg, `in ${scheme} the hovered to-do row's background is ${bg}, not the .rrow:hover fill ${wantBg}`);
  }
});

test("merged_page.py --live hands its JSON to the build as the live file", () => {
  const live = { readAt: new Date().toISOString(), threads: [], pulls: [] };
  const html = mergedPage("--live", JSON.stringify(live));
  const b = JSON.parse(BUILD_BLOCK.exec(html)[1]);
  assert.ok(b.live && Array.isArray(b.live.threads), "the build did not read the live file: " + JSON.stringify(b.live ?? null));
});

// The Live work cases share one live file and one way to open the Status tab on it. The read time is fixed, so no case depends on the clock.
// A case passes only the keys it changes; JSON.stringify drops an undefined key, so { pulls: undefined } builds a file with no pulls list.
const LIVE_READ = "2026-11-10T12:00:00Z";
const liveFile = (over = {}) => ({ readAt: LIVE_READ, branches: [], sessions: [], ...over });
async function liveStatus(t, over) {
  const page = await open(t, { pageHtml: mergedPage("--live", JSON.stringify(liveFile(over))) });
  if (page) await openStatus(page);
  return page;
}
const PULL_ONLY = { pulls: [{ number: 7, title: "Lane pull seven", branch: "lane-seven" }] };

// A live file with no threads list: the read stays valid, so the Status tab shows its open pull request and the read time.
// Only the thread count is unknown, so the page never reads "No thread is open" for it (a made-up zero).
test("the Status tab with a live file that has no threads list shows its pull request and the read as valid", async (t) => {
  const page = await liveStatus(t, PULL_ONLY); if (!page) return;
  // The live work line is the one whose label reads Live work: the stalled band is also a line, and it may be a not-read one.
  const line = page.locator(".livenone").filter({ hasText: "Live work" });
  const shown = (await line.count()) ? (await line.first().textContent()).replace(/\s+/g, " ") : "(no live work line)";
  assert.equal(await page.locator("details.live").count(), 1, "the Status tab draws live work as not read, not its pull request: " + shown);
  const text = (await page.locator("details.live").textContent()).replace(/\s+/g, " ");
  assert.match(text, /1 open pull request/, "the live work does not count the open pull request: " + text);
  assert.match(text, /#7/, "the live work does not show open pull request #7: " + text);
  assert.match(text, /Lane pull seven/, "the live work does not show the title of open pull request #7: " + text);
  assert.doesNotMatch(text, /not read/, "the live work reads not read with its pulls and read valid: " + text);
  assert.doesNotMatch(text, /No thread is open/, "the live work reads no threads, a made-up zero: " + text);
});

// The control for that case: a live file with no pulls list is not read, whatever its threads list holds.
test("control: the Status tab with a live file that has no pulls list reads live work not read", async (t) => {
  const page = await liveStatus(t, { pulls: undefined, threads: [] }); if (!page) return;
  assert.equal(await page.locator("details.live").count(), 0, "the Status tab draws live work with no pulls list as a panel, not as not read");
  const line = page.locator(".livenone").filter({ hasText: "Live work" });
  assert.equal(await line.count(), 1, "the Status tab draws no live work line for a live file with no pulls list");
  assert.match((await line.textContent()).replace(/\s+/g, " "), /not read/, "the live work line does not say not read");
});

// The threads-unknown marker in the Live work summary. A pill reads as a thread state (failed and stopped share its colour), so an
// unknown thread count gets a dashed ring and the words, the same ring the panel draws for a line not read.
const summaryText = (page) => page.locator("details.live > summary").textContent().then((s) => s.replace(/\s+/g, " ").trim());

test("the threads-unknown marker is a ring and the words in the summary, with no threads list", async (t) => {
  const page = await liveStatus(t, PULL_ONLY); if (!page) return;
  assert.equal(await page.locator("details.live").count(), 1, "the Status tab does not draw live work as a panel");
  const marker = page.locator("details.live > summary .thr-unk");
  assert.equal(await marker.count(), 1, "the summary has no .thr-unk marker: " + (await summaryText(page)));
  assert.equal((await marker.textContent()).trim(), "threads unknown", "the .thr-unk marker does not read threads unknown");
  assert.equal(await marker.locator(".rg.unk").count(), 1, "the .thr-unk marker has no .rg.unk ring");
});

test("the threads-unknown marker is not a tag pill in the summary, with no threads list", async (t) => {
  const page = await liveStatus(t, PULL_ONLY); if (!page) return;
  assert.equal(await page.locator("details.live").count(), 1, "the Status tab does not draw live work as a panel");
  assert.equal(await page.locator("details.live > summary .tag", { hasText: "threads unknown" }).count(), 0,
    "a .tag pill in the summary reads threads unknown, the look of a thread state: " + (await summaryText(page)));
});

test("the threads-unknown marker lays out as one inline row whose words do not wrap, with no threads list", async (t) => {
  const page = await liveStatus(t, PULL_ONLY); if (!page) return;
  assert.equal(await page.locator("details.live").count(), 1, "the Status tab does not draw live work as a panel");
  const marker = page.locator("details.live > summary .thr-unk");
  assert.equal(await marker.count(), 1, "the summary has no .thr-unk marker to lay out");
  // The summary is a flex box, so the marker is a flex item and Chromium blockifies its computed display: inline-flex reads as flex.
  // The probe sits in the same summary, so it blockifies the same way and the two values compare.
  const wantDisplay = await probeOf(page.locator("details.live > summary"), "display", "inline-flex");
  assert.equal(await computedOf(marker, "display"), wantDisplay, `the marker's display is not inline-flex, so its ring and words do not sit on one row (want ${wantDisplay})`);
  assert.equal(await computedOf(marker, "whiteSpace"), "nowrap", "the marker's white-space is not nowrap, so its words may break over lines");
});

test("the threads-unknown marker's ring is in the open panel's thread count row, with no threads list", async (t) => {
  const page = await liveStatus(t, PULL_ONLY); if (!page) return;
  assert.equal(await page.locator("details.live").count(), 1, "the Status tab does not draw live work as a panel");
  await page.locator("details.live > summary").click();
  const row = page.locator("details.live li", { hasText: "Thread count" });
  assert.equal(await row.count(), 1, "the open panel has no thread count row");
  assert.equal(await row.isVisible(), true, "the thread count row is not shown when the live work panel is open");
  assert.equal(await row.locator(".rg.unk").count(), 1, "the thread count row has no .rg.unk ring, so it reads unknown without the mark the summary carries: " + (await row.textContent()).replace(/\s+/g, " ").trim());
});

// The controls: an empty threads list is a real zero and gets no marker, and a list with threads keeps each thread's pill and no marker.
test("control: an empty threads list draws no threads-unknown marker and no threads-unknown pill", async (t) => {
  const page = await liveStatus(t, { ...PULL_ONLY, threads: [] }); if (!page) return;
  assert.equal(await page.locator("details.live > summary").count(), 1, "the live work summary is missing");
  assert.match(await summaryText(page), /1 open pull request/, "the summary does not show its open pull request, so the case did not draw the summary");
  assert.equal(await page.locator("details.live > summary .thr-unk").count(), 0, "an empty threads list draws a threads-unknown marker: zero is a real read, not unknown");
  assert.equal(await page.locator("details.live > summary .tag", { hasText: "threads unknown" }).count(), 0, "an empty threads list draws a threads-unknown pill");
});

test("control: a failed and a stopped thread keep their tag pills and draw no threads-unknown marker", async (t) => {
  const threads = [{ title: "Failing lane", state: "failed" }, { title: "Stopped lane", state: "stopped" }];
  const page = await liveStatus(t, { ...PULL_ONLY, threads }); if (!page) return;
  const summary = page.locator("details.live > summary");
  assert.equal(await summary.count(), 1, "the live work summary is missing");
  assert.equal(await summary.locator(".tag.st-failed", { hasText: "1 failed" }).count(), 1, "the summary's failed thread is not a .tag pill: " + (await summaryText(page)));
  assert.equal(await summary.locator(".tag.st-stopped", { hasText: "1 stopped" }).count(), 1, "the summary's stopped thread is not a .tag pill: " + (await summaryText(page)));
  assert.equal(await summary.locator(".thr-unk").count(), 0, "a list of threads draws a threads-unknown marker");
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

test("a tap on the stars of a multi item and a ranked item writes each whole pick list, ranked or not", async (t) => {
  const m = digest(), r = ranked("rk-take", 32);
  const page = await open(t, { items: [m, r] }); if (!page) return;
  await needBoxes(page, m, 3); await needBoxes(page, r, 4);
  await takePick(page, m); await takePick(page, r);
  assert.deepEqual(await ticked(page, m), ["a", "c"]);
  assert.deepEqual(await ticked(page, r), ["a", "c", "d"]);
  for (const [k, n] of [["c", "1st"], ["a", "2nd"], ["d", "3rd"]]) assert.match(await rankText(page, r, k), rank(n, 3), `rank of ${k}`);
  assert.match(await card(page, m).locator(".ready").textContent(), /^Ready to send: .+, your choice\.$/);
  assert.equal(await page.locator("#send").textContent(), "Send 2 answers");
  await send(page);
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 2);
  const a = await answers(page);
  assert.deepEqual(a[m.id].choice, ["a", "c"]);
  assert.deepEqual(a[r.id].choice, ["c", "a", "d"]);
  assert.deepEqual([a[m.id].note, a[r.id].note], ["", ""]);
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

test("the ready line names the picks by title, shortened, never by letter, and a ranked line gives the order", async (t) => {
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
  // Picks ticked in the order value, then nothing: the ranked line gives that order, not the pick's.
  await tick(page, r, "value"); await tick(page, r, "nothing");
  assert.match(await ready(r), /^Ready to send: Value for the card.*…, Nothing, your order\.$/);
});

// An unranked multi item has no order to keep: its ticks stay in option order, whatever order they were ticked in (ruling of 15:55 CDT, c135 round 3).
test("an unranked multi item keeps its ticks in option order: C then A equals my pick a+c, and the answer and the notice read a+c", async (t) => {
  const it = multi("un-order", 61, { pick: ["a", "c"] });
  const page = await open(t, { items: [it] }); if (!page) return;
  await needBoxes(page, it, 3);
  await tick(page, it, "c");
  await tick(page, it, "a");
  assert.deepEqual(await ticked(page, it), ["a", "c"]);
  assert.match(await card(page, it).locator(".ready").textContent(), /^Ready to send: Red and Green, your choice\.$/, "the ready line does not name the ticks in option order");
  await send(page);
  await told(page, "A wake was sent");
  const a = (await answers(page))[it.id];
  assert.deepEqual([a.choice, a.note], [["a", "c"], ""], "the answer is not in option order");
  const s = await sent(page);
  assert.equal(s.length, 1);
  assert.match(s[0].text, /(?<!\d)61 a\+c(?![+\w])/, "the notice does not read a+c: " + s[0].text);
});

// An unranked pick out of option order is saved in option order; a ranked pick keeps the order it was ticked or tapped in.
test("a multi item whose pick is out of option order: an unranked pick saves in option order, and a ranked pick keeps its order", async (t) => {
  const uHand = multi("po-u-hand", 81, { pick: ["c", "a"] }), uTake = multi("po-u-take", 82, { pick: ["c", "a"] });
  const rHand = ranked("po-r-hand", 83), rTake = ranked("po-r-take", 84);
  const page = await open(t, { items: [uHand, uTake, rHand, rTake] }); if (!page) return;
  await needBoxes(page, uHand, 3); await needBoxes(page, uTake, 3); await needBoxes(page, rHand, 4); await needBoxes(page, rTake, 4);
  for (const k of ["c", "a", "d"]) await tick(page, rHand, k);
  await tick(page, uHand, "a"); await tick(page, uHand, "c");
  await takePick(page, uTake); await takePick(page, rTake);
  await send(page);
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 4);
  const a = await answers(page);
  assert.deepEqual([a[rTake.id].choice, a[rHand.id].choice], [["c", "a", "d"], ["c", "a", "d"]], "a ranked pick is not saved in its pick order");
  assert.deepEqual([a[uTake.id].choice, a[uHand.id].choice], [["a", "c"], ["a", "c"]], "an unranked pick out of option order is not saved in option order");
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
    await takePick(page, items[0]); await same("a tap on the stars of a multi item");
    for (const k of ["c", "a", "d"]) { await tick(page, items[1], k); await same("a tick on a ranked item"); }
    await moveBtn(page, items[1], "a", "up").click(); await same("Up");
    await moveBtn(page, items[1], "d", "up").click(); await same("a second Up");
    await moveBtn(page, items[1], "d", "down").click(); await same("Down");
    const first = moveBtn(page, items[1], "a", "up");
    await first.focus(); await page.keyboard.press("Enter"); await same("Up on the first");
    await tick(page, items[1], "d"); await same("an untick on a ranked item");
    await takePick(page, items[1]); await same("a tap on the stars of a ranked item");
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

  test(`a multi item of six 28-character titles shows the tail of its ready line, and no card moves, at ${viewport.width} wide`, async (t) => {
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
    assert.match(mine.text, /^Ready to send: .+, your choice\.$/);
    assert.ok(mine.clip <= 0 && mine.need <= mine.box + 1, `the ready line cuts its tail (box ${mine.box}px, text needs ${mine.need}px)`);
    assert.deepEqual(await geo(page), base, "a card moved on a tap on the star");
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

test("a pick that is not a valid list shows no star; a valid list does", async (t) => {
  const bad = [multi("bad-str", 51, { pick: "a" }), multi("bad-key", 52, { pick: ["a", "zzz"] }), multi("bad-dup", 53, { pick: ["a", "a"] }), multi("bad-empty", 54, { pick: [] }), mk("bad-one", 55, { pick: ["a", "b"] })];
  const good = multi("good-list", 56);
  const page = await open(t, { items: [...bad, good] }); if (!page) return;
  for (const it of [...bad.slice(0, 4), good]) await needBoxes(page, it, 3);
  assert.equal(await card(page, good).locator(".opt .pick").count(), 2, "a valid list is not starred on each pick");
  assert.match(await page.locator(`#item-${good.id} .opt:has(#o-${good.id}-a) .pick`).textContent(), /Red and Green cover it\./);
  for (const it of bad) assert.equal(await card(page, it).locator(".opt .pick").count(), 0, `${it.id}: a star shows for a bad pick`);
});

// The starred option is the one control for a pick: a tap on it readies the card. The stood card has no tap, because its pick already stands.
test("a tap on the star readies each card, and no card draws a Take my pick button", async (t) => {
  const single = mk("nb-single", 70), multiPick = digest(), rk = ranked("nb-rank", 71), stood = mk("nb-stood", 72, { stands: true });
  const page = await open(t, { items: [single, multiPick, rk, stood] }); if (!page) return;
  const endings = [[single, /^Ready to send: .+, your choice\.$/], [multiPick, /^Ready to send: .+, your choice\.$/], [rk, /^Ready to send: .+, your order\.$/]];
  for (const [it, ending] of endings) {
    await takePick(page, it);
    assert.match(await card(page, it).locator(".ready").textContent(), ending, `${it.id}: a tap on the star did not ready the card`);
  }
  assert.equal(await page.locator('[id^="b-take-"]').count(), 0, "a card draws a Take my pick button");
  assert.equal(await page.locator(".takepick").count(), 0, "a card draws a takepick button");
});

test("the notice to Claude writes a list pick as 31 a+c, in rank order when ranked", async (t) => {
  const m = digest(), r = ranked("rk-notice", 32);
  const page = await open(t, { items: [m, r] }); if (!page) return;
  await needBoxes(page, m, 3); await needBoxes(page, r, 4);
  await tick(page, m, "a"); await tick(page, m, "c"); await addNote(page, m, "bold");
  await tick(page, r, "c"); await tick(page, r, "a");
  await send(page);
  await told(page, "A wake was sent");
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

const FILL = [mk("take-fill-1", 50), mk("take-fill-2", 51), mk("take-fill-3", 52)];
const TAKE_CARDS = {
  "pick-one": () => mk("take-clear", 43, { options: COLOURS, pick: "a" }),
  "multi A and D": () => multi("take-clear-multi", 44, { options: COLOURS, pick: ["a", "d"] }),
};

// "Nothing on the page moves" (page.html, top comment): an option already between the header and the bar needs no scroll, so a tap on its star leaves scrollY as it was.
// `gap` is the px from the header's bottom to option A's top. A scroll that moves the page, even by 10px, fails.
// The taps run in the DOM, so a tap on a star below the bar does not scroll the page to reach it.
const stillAfterTap = async (t, it, width, gap) => {
  const page = await open(t, { items: [it, ...FILL], viewport: { width, height: 800 } }); if (!page) return;
  const m = await page.evaluate(({ id, gap }) => {
    const hdr = document.querySelector(".hdr").getBoundingClientRect().bottom, bar = document.querySelector(".bar").getBoundingClientRect().top;
    const o = document.getElementById(`o-${id}-a`).closest(".opt");
    scrollBy(0, o.getBoundingClientRect().top - (hdr + gap));
    const r = o.getBoundingClientRect();
    return { y: scrollY, top: Math.round(r.top), bottom: Math.round(r.bottom), hdr: Math.round(hdr), bar: Math.round(bar) };
  }, { id: it.id, gap });
  assert.ok(m.y > 0 && m.top >= m.hdr && m.bottom <= m.bar, `${it.id}: option A was not placed in view with the page scrolled: ${JSON.stringify(m)}`);
  await page.evaluate(({ id, keys }) => { for (const k of keys) document.querySelector(`label[for="o-${id}-${k}"]`).click(); }, { id: it.id, keys: [].concat(it.pick) });
  assert.equal(await page.evaluate(() => scrollY), m.y, `${it.id}: a tap on the star scrolled the page`);
};
// Option A starts 56px under the 44px header, so 100px from the top of the screen: whole and clear of the 64px scroll margin. A scroll that centres it moves the page.
for (const width of [390, 1280]) for (const [kind, build] of Object.entries(TAKE_CARDS)) {
  test(`a tap on the star does not scroll the page when the pick's option is already in view, ${kind}, at ${width} wide`, (t) => stillAfterTap(t, build(), width, 56));
}
// Option A is fully visible 10px under the header, inside the 64px scroll margin. These cards hold two options, so both fit at 390 wide.
const NEAR_CARDS = {
  "pick-one": () => mk("take-near", 45, { pick: "a" }),
  "multi A and B": () => multi("take-near-multi", 46, { options: COLOURS.slice(0, 2), pick: ["a", "b"] }),
};
for (const width of [390, 1280]) for (const [kind, build] of Object.entries(NEAR_CARDS)) {
  test(`a tap on the star does not scroll the page when the pick's option sits 10px under the header, ${kind}, at ${width} wide`, (t) => stillAfterTap(t, build(), width, 10));
}

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

// ---------------------------------------------------------------- c190 with c135: option links on a multi card and on a ranked card
// Option a has a link and a short how; option b has none and a long how, so a missing links row or a missing row track shows as a gap.
const linkedMulti = (id, n, over = {}) => multi(id, n, { options: [
  { ...opt("a", "Red"), how: "A short way to put it.", links: [LINK] },
  { ...opt("b", "Blue"), how: "A longer way to put it, which runs onto a second line at desktop width. ".repeat(2) },
  opt("c", "Green"),
], ...over });
const linkedRanked = (id, n, over = {}) => linkedMulti(id, n, { ranked: true, pick: ["c", "a"], ...over });

// Each card's rows are checked at a phone width, where the cards stack, and at a desktop width, where they sit side by side.
for (const width of [390, 1280]) for (const [kind, make, pics] of [["multi", linkedMulti, false], ["ranked", linkedRanked, false], ["ranked with pictures", linkedRanked, true]]) {
  test(`option links on a ${kind} card show after the how text, and the cards' rows line up, at ${width} wide`, async (t) => {
    const it = make("lk-" + kind.replace(/\W/g, ""), 40);
    if (pics) it.options = it.options.map((o, i) => (i < 2 ? { ...o, design: "s1" } : o));
    const page = await open(t, { items: [it], designData: pics ? DESIGNS : null, viewport: { width, height: 900 } }); if (!page) return;
    await needBoxes(page, it, 3);
    await need(card(page, it).locator(`#k-${it.id}-a`), "no links row on option a");
    assert.equal(await page.getByRole("link", { name: LINK.label + ", opens in a new tab", exact: true }).count(), 1, "the link is not named for where it opens");
    assert.equal(await card(page, it).locator(".opts.olinks").count(), 1, "the options do not take the olinks class");
    assert.equal(await card(page, it).locator(`.opt:has(#o-${it.id}-b) span.nolinks`).count(), 1, "an option with no link has no nolinks span");
    if (it.ranked) assert.equal(await card(page, it).locator(".opts.ranked.olinks").count(), 1, "the ranked options lost a class");
    // Each child box, as offsets from its card: top rows from the top edge, pinned rows (pick, rank) from the bottom edge.
    // `abs` is the page position, which compares rows across cards that sit side by side.
    const cards = await page.evaluate((id) => ["a", "b", "c"].map((k) => {
      const o = document.querySelector(`#item-${id} .opt:has(#o-${id}-${k})`), ob = o.getBoundingClientRect();
      const child = (sel) => {
        const e = o.querySelector(sel);
        if (!e) return null;
        const b = e.getBoundingClientRect();
        return { top: b.top - ob.top, bottom: ob.bottom - b.bottom, abs: b.top, box: [b.left, b.top, b.right, b.bottom], inside: b.top >= ob.top - 1 && b.bottom <= ob.bottom + 1 && b.left >= ob.left - 1 && b.right <= ob.right + 1 };
      };
      return { top: ob.top, height: ob.height, head: child(".head"), how: child(".how"), links: child(".links, .nolinks"), tr: child(".tr"), pic: child(".opic"), pick: child(".pick, .nopick"), rank: child(".rank") };
    }), it.id);
    const near = (x, y) => Math.abs(x - y) <= 1;
    let sideBySide = 0;
    cards.forEach((c, i) => {
      const k = "abc"[i];
      for (const row of ["how", "links", "tr", "pick"]) assert.ok(c[row], `${kind}: option ${k} has no ${row} box`);
      if (it.ranked) assert.ok(c.rank, `${kind}: option ${k} has no rank box`);
      if (pics) assert.ok(c.pic, `${kind}: option ${k} has no picture box`);
      for (const row of ["head", "how", "links", "tr", "pic", "pick", "rank"]) if (c[row]) assert.ok(c[row].inside, `${kind}: the ${row} box of option ${k} sits outside its own card, at ${width} wide`);
      // Rows stack without overlap: a row that runs into the next one would put a button over the pick text.
      const kids = ["head", "how", "links", "tr", "pic", "pick", "rank"].filter((n) => c[n]);
      for (let x = 0; x < kids.length; x++) for (let y = x + 1; y < kids.length; y++) {
        const [a, b] = [c[kids[x]].box, c[kids[y]].box];
        const overlap = a[0] < b[2] - 1 && b[0] < a[2] - 1 && a[1] < b[3] - 1 && b[1] < a[3] - 1;
        assert.ok(!overlap, `${kind}: the ${kids[x]} and ${kids[y]} boxes of option ${k} overlap, at ${width} wide`);
      }
      assert.ok(c.links.top > c.how.top && c.tr.top > c.links.top, `${kind}: option ${k}: the links row is not between the how text and the timing rows`);
    });
    for (let i = 0; i < cards.length; i++) for (let j = i + 1; j < cards.length; j++) {
      const p = cards[i], q = cards[j], pair = `options ${"abc"[i]} and ${"abc"[j]}`;
      for (const row of ["pick", "rank"]) if (p[row] && q[row]) assert.ok(near(p[row].bottom, q[row].bottom), `${kind}: the ${row} rows of ${pair} are not level, at ${width} wide`);
      if (!near(p.top, q.top)) continue; // stacked cards each run their own top rows, which follow their own text and pictures
      sideBySide++;
      for (const row of ["how", "links", "tr", "pic"]) if (p[row] && q[row]) assert.ok(near(p[row].abs, q[row].abs), `${kind}: the ${row} rows of ${pair} are not level, at ${width} wide`);
      assert.ok(near(p.height, q.height), `${kind}: the cards of ${pair} differ in height, at ${width} wide`);
    }
    if (width === 1280) assert.ok(sideBySide > 0, `${kind}: the cards do not sit side by side at 1280, so the level check compared nothing`);
  });
}

test("a press on an option's link opens it and ticks nothing, on a multi card and on a ranked card", async (t) => {
  const m = linkedMulti("lk-press-m", 41), r = linkedRanked("lk-press-r", 42);
  const page = await open(t, { items: [m, r] }); if (!page) return;
  await needBoxes(page, m, 3); await needBoxes(page, r, 3);
  await page.context().route("**/*", (rt) => rt.abort()); // the new tab loads nothing
  for (const it of [m, r]) {
    const link = card(page, it).locator(`#k-${it.id}-a a`);
    await need(link, `${it.id}: no link on option a`);
    // A real press at the link's centre: on a ranked card the label's overlay must not take it.
    const [tab] = await Promise.all([page.context().waitForEvent("page", { timeout: 5000 }).catch(() => assert.fail(`${it.id}: a press on the link did not open it`)), link.click()]);
    await tab.close();
    assert.deepEqual(await ticked(page, it), [], `${it.id}: a press on the link ticked the option`);
    assert.equal(await card(page, it).locator(".opt.sel").count(), 0, `${it.id}: a press on the link selected the card`);
    await tick(page, it, "a");
    assert.deepEqual(await ticked(page, it), ["a"], `${it.id}: a press on the label did not tick the option`);
  }
});

for (const width of [390, 1280]) test(`a press on the empty part of a ranked option's links row ticks the option, at ${width} wide`, async (t) => {
  // A short link leaves an empty part of the row to its right at both widths; the long link fills the row at 1280.
  const r = linkedRanked("lk-empty-r", 43, { options: [{ ...opt("a", "Red"), how: "A short way to put it.", links: [{ label: "Repo", url: LINK.url }] }, opt("b", "Blue"), opt("c", "Green")] });
  const page = await open(t, { items: [r], viewport: { width, height: 900 } }); if (!page) return;
  await needBoxes(page, r, 3);
  const row = card(page, r).locator(`#k-${r.id}-a`), link = row.locator("a");
  await need(row, `${r.id}: no links row on option a`);
  const rb = await row.boundingBox(), lb = await link.boundingBox();
  // 20px in from the row's right edge, past the link: the press must land on the row's empty part, not on the link.
  const x = rb.x + rb.width - 20, y = rb.y + rb.height / 2;
  assert.ok(x < lb.x || x > lb.x + lb.width, `${r.id}: the press point is over the link`);
  await page.mouse.click(x, y);
  assert.deepEqual(await ticked(page, r), ["a"], `${r.id}: a press on the empty part of the links row did not tick the option, at ${width} wide`);
});

// ---------------------------------------------------------------- lane page-shows-last-answer: the last answer, the reply and the lane
// Spec: docs/design/last-answer-notes.md (picks 1A, 2A, 3A, and the copy in its section 4). Three item fields drive it:
// `lastAnswer` ({choice?, done?, note?, at}), `reply` (a string) and `lane` (a lane branch slug). Each case sets them on an item
// and reads the card, by visible text and by where the part sits. The panel is found by its aria-label (notes, section 4).
const LA_AT = "2026-10-29T19:05:00Z"; // 14:05 CDT
const LA_NAMES = ["Your last answer and the reply", "Your last answer", "The reply"];
const LA_LONG = "A long reply that runs past three lines on a phone. ".repeat(8).trim(); // 415 characters
const laPanel = (page, it) => card(page, it).locator(LA_NAMES.map((n) => `[aria-label="${n}"]`).join(", "));
const flat = (s) => s.replace(/\s+/g, " ").trim();
// The panel's text, flattened. Every case needs exactly one panel, so a page that draws none fails on this line at once.
const laText = async (page, it) => {
  assert.equal(await laPanel(page, it).count(), 1, `${it.id}: no single panel labelled "${LA_NAMES.join('", "')}"`);
  return flat(await laPanel(page, it).innerText());
};
const laBox = (loc) => loc.evaluate((e) => { const r = e.getBoundingClientRect(); return { top: r.top + scrollY, bottom: r.bottom + scrollY, left: r.left + scrollX, right: r.right + scrollX, h: r.height }; });
const laSaved = (it, choice = "a") => ({ [it.id]: { item: it.id, n: it.n, at: "2026-10-26T01:00:00Z", choice, note: "" } });
const laReply = (page, it) => card(page, it).getByText(/^Reply: /);
// How many lines of text the reply shows now: its box height over the height of one line in the same element.
const laReplyLines = (page, it) => laReply(page, it).evaluate((e) => {
  const probe = e.cloneNode(false); probe.removeAttribute("id"); probe.textContent = "x";
  e.parentNode.insertBefore(probe, e); const one = probe.getBoundingClientRect().height; probe.remove();
  return e.getBoundingClientRect().height / one;
});

test("a decision's last answer shows its letter and label, then its note, with the time in US Central 24-hour", async (t) => {
  const it = mk("la-one", 1, { lastAnswer: { choice: "b", note: "Only if it is cheap.", at: LA_AT } });
  const page = await open(t, { items: [it] }); if (!page) return;
  const p = await laText(page, it);
  assert.match(p, /Your last answer, Oct 29, 14:05 CDT/);
  assert.match(p, /You chose B: Blue\./);
  assert.match(p, /Note: Only if it is cheap\./);
  assert.ok(p.indexOf("Your last answer") < p.indexOf("You chose B") && p.indexOf("You chose B") < p.indexOf("Note:"), "head, answer, note are not in that order: " + p);
  assert.doesNotMatch(p, /\b[AP]M\b|UTC|19:05/, "the time is not US Central 24-hour: " + p);
  assert.equal(await laPanel(page, it).getAttribute("aria-label"), "Your last answer");
  assert.doesNotMatch(p, /Reply:/);
});

test("the last answer's time names the zone and keeps midnight as 00, in summer and in winter", async (t) => {
  const cdt = mk("la-cdt", 1, { lastAnswer: { choice: "a", at: "2026-10-29T05:30:00Z" } });
  const cst = mk("la-cst", 2, { lastAnswer: { choice: "a", at: "2026-12-05T06:30:00Z" } });
  const page = await open(t, { items: [cdt, cst] }); if (!page) return;
  assert.match(await laText(page, cdt), /Your last answer, Oct 29, 00:30 CDT/);
  assert.match(await laText(page, cst), /Your last answer, Dec 5, 00:30 CST/);
});

test("a last answer whose time does not parse shows 'Your last answer' with no time and no stray comma", async (t) => {
  const it = mk("la-badat", 1, { lastAnswer: { choice: "a", at: "not a time" } });
  const page = await open(t, { items: [it] }); if (!page) return;
  const p = await laText(page, it);
  assert.match(p, /^Your last answer(?!,)/, "the head is not 'Your last answer' alone: " + p);
  assert.doesNotMatch(p, /Invalid|NaN|undefined/);
  assert.match(p, /You chose A: Red\./);
});

test("the note 'accepted pick' is not shown in the last answer, as the receipt hides it", async (t) => {
  const it = mk("la-accepted", 1, { lastAnswer: { choice: "a", note: "accepted pick", at: LA_AT } });
  const page = await open(t, { items: [it] }); if (!page) return;
  const p = await laText(page, it);
  assert.match(p, /You chose A: Red\./);
  assert.doesNotMatch(p, /accepted pick|Note:/, "the pick's own note shows: " + p);
});

test("a last answer with no choice on a decision shows its head and note and no answer line", async (t) => {
  const it = mk("la-noans", 1, { lastAnswer: { note: "Why not green?", at: LA_AT } });
  const page = await open(t, { items: [it] }); if (!page) return;
  const p = await laText(page, it);
  assert.match(p, /Your last answer, Oct 29, 14:05 CDT/);
  assert.match(p, /Note: Why not green\?/);
  assert.doesNotMatch(p, /You chose|None of these|[Mm]arked done/, "an answer line shows with no choice: " + p);
});

test("a last answer of none reads 'None of these.' with its note", async (t) => {
  const it = mk("la-none", 1, { lastAnswer: { choice: "none", note: "Neither. Keep the old rail.", at: LA_AT } });
  const page = await open(t, { items: [it] }); if (!page) return;
  const p = await laText(page, it);
  assert.match(p, /None of these\./);
  assert.match(p, /Note: Neither\. Keep the old rail\./);
  assert.doesNotMatch(p, /You chose/);
});

test("a last answer that is a list shows each pick by letter and label, and a ranked list shows a numbered list in order", async (t) => {
  const m = multi("la-multi", 1, { lastAnswer: { choice: ["a", "c"], at: LA_AT } });
  const r = ranked("la-ranked", 2, { lastAnswer: { choice: ["c", "a"], at: LA_AT } });
  const page = await open(t, { items: [m, r] }); if (!page) return;
  const items = (it) => laPanel(page, it).locator("li").allTextContents().then((l) => l.map((s) => flat(s).replace(/ /g, "")));
  assert.match(await laText(page, m), /You chose:/);
  assert.deepEqual(await items(m), ["ARed", "CGreen"]);
  assert.equal(await laPanel(page, m).locator("ol").count(), 0, "an unranked list is numbered");
  assert.match(await laText(page, r), /You chose, in order:/);
  assert.deepEqual(await items(r), ["CGreen", "ARed"]);
  assert.equal(await laPanel(page, r).locator("ol").count(), 1, "a ranked list is not a numbered list");
});

test("a last answer that names a key no longer in options never shows the key, for one key and for a list", async (t) => {
  const one = mk("la-gone", 1, { lastAnswer: { choice: "pinned", at: LA_AT } });
  const list = multi("la-gone-list", 2, { lastAnswer: { choice: ["a", "pinned"], at: LA_AT } });
  const page = await open(t, { items: [one, list] }); if (!page) return;
  const p = await laText(page, one), q = await laText(page, list);
  assert.match(p, /You chose an option that is no longer listed\./);
  assert.doesNotMatch(p, /pinned|You chose [A-Z]:/, "the raw key or a letter shows: " + p);
  assert.match(q, /You chose options that are no longer listed\./);
  assert.doesNotMatch(q, /pinned|Red/, "the raw key shows, or the one valid pick is listed: " + q);
  assert.equal(await laPanel(page, list).locator("li").count(), 0, "a list that holds a lost key is still drawn as picks");
});

test("a task's last answer reads 'Marked done.' when done is true and 'Not marked done.' otherwise", async (t) => {
  const done = { ...TASK, id: "la-done", n: 3, lastAnswer: { done: true, at: LA_AT } };
  const not = { ...TASK, id: "la-notdone", n: 4, lastAnswer: { note: "It asks for an Apple ID. Which one?", at: LA_AT } };
  const page = await open(t, { items: [done, not] }); if (!page) return;
  const d = await laText(page, done), n = await laText(page, not);
  assert.match(d, /Your last answer, Oct 29, 14:05 CDT/);
  assert.match(d, /(^| )Marked done\./);
  assert.doesNotMatch(d, /Not marked done|You chose/);
  assert.match(n, /Not marked done\./);
  assert.match(n, /Note: It asks for an Apple ID\. Which one\?/);
  assert.doesNotMatch(n, /(^| )Marked done\./);
});

test("the reply shows as 'Reply: <text>', alone or after the last answer, and the panel is named for what it holds", async (t) => {
  const both = mk("rp-both", 1, { lastAnswer: { choice: "a", at: LA_AT }, reply: "I added option C. Pick again." });
  const last = mk("rp-last", 2, { lastAnswer: { choice: "a", at: LA_AT } });
  const only = mk("rp-only", 3, { reply: "Your comment asked where the motion values live." });
  const page = await open(t, { items: [both, last, only] }); if (!page) return;
  const b = await laText(page, both);
  assert.match(b, /Reply: I added option C\. Pick again\./);
  assert.ok(b.indexOf("Your last answer") < b.indexOf("Reply:"), "the reply is not after the last answer: " + b);
  assert.equal(await laPanel(page, both).getAttribute("aria-label"), "Your last answer and the reply");
  assert.equal(await laPanel(page, last).getAttribute("aria-label"), "Your last answer");
  assert.doesNotMatch(await laText(page, last), /Reply:/);
  const o = await laText(page, only);
  assert.equal(await laPanel(page, only).getAttribute("aria-label"), "The reply");
  assert.match(o, /Reply: Your comment asked where the motion values live\./);
  assert.doesNotMatch(o, /Your last answer/);
});

test("a reply over 220 characters folds to three lines with More of the reply, and Less folds it again", async (t) => {
  const it = mk("rp-long", 1, { reply: LA_LONG });
  const page = await open(t, { items: [it] }); if (!page) return;
  const more = card(page, it).getByRole("button", { name: "More of the reply", exact: true });
  await need(more, "no More of the reply button on a long reply");
  const folded = await laReplyLines(page, it);
  assert.ok(folded > 2.9 && folded < 3.1, `a folded reply shows ${folded} lines, not 3`);
  assert.equal(await more.getAttribute("aria-expanded"), "false");
  await more.click();
  const less = card(page, it).getByRole("button", { name: "Less", exact: true });
  await need(less, "More of the reply did not become Less");
  assert.equal(await less.getAttribute("aria-expanded"), "true");
  const unfolded = await laReplyLines(page, it);
  assert.ok(unfolded > 3.5, `an opened reply shows ${unfolded} lines, not all of it`);
  assert.ok(flat(await card(page, it).textContent()).includes(LA_LONG), "the opened reply is cut");
  await less.click();
  assert.ok((await laReplyLines(page, it)) < 3.1, "Less did not fold the reply");
  await need(card(page, it).getByRole("button", { name: "More of the reply", exact: true }), "Less did not become More of the reply");
});

test("a reply of 220 characters has no More of the reply button, and one of 221 has it", async (t) => {
  const word = "ab ".repeat(100);
  const at220 = mk("rp-220", 1, { reply: word.slice(0, 220) }), at221 = mk("rp-221", 2, { reply: word.slice(0, 221) });
  const page = await open(t, { items: [at220, at221] }); if (!page) return;
  assert.equal(await laPanel(page, at220).count(), 1, "a reply of 220 characters draws no panel");
  assert.equal(await card(page, at220).getByRole("button", { name: "More of the reply" }).count(), 0, "a reply of 220 characters is folded");
  assert.equal(await card(page, at221).getByRole("button", { name: "More of the reply", exact: true }).count(), 1, "a reply of 221 characters is not folded");
});

test("an opened reply stays open while the owner picks an option, and does not open the context", async (t) => {
  const it = mk("rp-keep", 1, { context: LONG, reply: LA_LONG });
  const page = await open(t, { items: [it] }); if (!page) return;
  await need(card(page, it).getByRole("button", { name: "More of the reply", exact: true }), "no More of the reply button");
  await card(page, it).getByRole("button", { name: "More of the reply", exact: true }).click();
  assert.match(await page.locator(`#ctx-${it.id}`).getAttribute("class"), /clamp/, "More of the reply opened the context");
  await need(card(page, it).getByRole("button", { name: "More context", exact: true }), "More of the reply changed the context's button");
  await choose(page, it, "b"); // a pick repaints the card
  await need(card(page, it).getByRole("button", { name: "Less", exact: true }), "the reply folded when the card repainted");
  assert.ok((await laReplyLines(page, it)) > 3.5, "the reply folded when the card repainted");
  assert.match(await page.locator(`#ctx-${it.id}`).getAttribute("class"), /clamp/);
});

// Enter on the reply's button keeps keyboard focus on it through the repaint that the press causes.
test("Enter on More of the reply keeps focus on that button, which then reads Less", async (t) => {
  const it = mk("rp-focus", 1, { reply: LA_LONG });
  const page = await open(t, { items: [it] }); if (!page) return;
  const more = card(page, it).getByRole("button", { name: "More of the reply", exact: true });
  await need(more, "no More of the reply button on a long reply");
  await more.focus();
  await page.keyboard.press("Enter");
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => r())));
  await need(card(page, it).getByRole("button", { name: "Less", exact: true }), "More of the reply did not become Less");
  const at = await page.evaluate(() => ({ tag: document.activeElement.tagName, text: document.activeElement.textContent.trim(), controls: document.activeElement.getAttribute("aria-controls") }));
  assert.deepEqual(at, { tag: "BUTTON", text: "Less", controls: "rp-" + it.id }, "focus did not stay on the reply's button after Enter");
});

// The context's More button keeps keyboard focus through the repaint its press causes, as the reply's button does.
test("Enter on More context keeps focus on that button, which then reads Less", async (t) => {
  const it = mk("cx-focus", 1, { context: LONG });
  const page = await open(t, { items: [it] }); if (!page) return;
  const more = card(page, it).getByRole("button", { name: "More context", exact: true });
  await need(more, "no More context button on a long context");
  await more.focus();
  await page.keyboard.press("Enter");
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => r())));
  await need(card(page, it).getByRole("button", { name: "Less", exact: true }), "More context did not become Less");
  const at = await page.evaluate(() => ({ tag: document.activeElement.tagName, text: document.activeElement.textContent.trim(), controls: document.activeElement.getAttribute("aria-controls") }));
  assert.deepEqual(at, { tag: "BUTTON", text: "Less", controls: "ctx-" + it.id }, "focus did not stay on the context's button after Enter");
});
test("More context still controls its context and reads Less once it is open", async (t) => {
  const it = mk("cx-guard", 1, { context: LONG });
  const page = await open(t, { items: [it] }); if (!page) return;
  const more = card(page, it).getByRole("button", { name: "More context", exact: true });
  await need(more, "no More context button on a long context");
  assert.equal(await more.getAttribute("aria-controls"), "ctx-" + it.id, "More context does not control its context");
  await more.click();
  const less = card(page, it).getByRole("button", { name: "Less", exact: true });
  await need(less, "More context did not become Less");
  assert.equal(await less.getAttribute("aria-expanded"), "true", "Less does not say the context is expanded");
  assert.equal(await less.getAttribute("aria-controls"), "ctx-" + it.id, "Less does not control its context");
});

// Each button of an item's alternatives names its item after its visible words (docs/design/a11y.md).
test("None of these, Park and Mark done name their item in the accessible name", async (t) => {
  const page = await open(t, { items: [DECISION, TASK] }); if (!page) return;
  await need(card(page, DECISION).getByRole("button", { name: "None of these on No. 27", exact: true }), "the decision card has no None of these button named None of these on No. 27");
  await need(card(page, DECISION).getByRole("button", { name: "Park No. 27", exact: true }), "the decision card has no Park button named Park No. 27");
  await need(card(page, TASK).getByRole("button", { name: "Mark done on No. 28", exact: true }), "the task card has no Mark done button named Mark done on No. 28");
  await need(card(page, TASK).getByRole("button", { name: "Park No. 28", exact: true }), "the task card has no Park button named Park No. 28");
});
test("the alternatives' buttons still start with their visible words", async (t) => {
  const page = await open(t, { items: [DECISION, TASK] }); if (!page) return;
  await need(card(page, DECISION).getByRole("button", { name: /^None of these/ }), "the None of these button does not start with its visible words");
  await need(card(page, DECISION).getByRole("button", { name: /^Park/ }), "the Park button on the decision card does not start with its visible word");
  await need(card(page, TASK).getByRole("button", { name: /^Mark done/ }), "the Mark done button does not start with its visible words");
});

test("a lane shows 'waits on lane <slug>' as one text run in the top row, after the wait, and adds no row", async (t) => {
  const on = mk("ln-on", 1, { lane: "ci-done-comment" }), off = mk("ln-off", 2);
  const page = await open(t, { items: [on, off] }); if (!page) return;
  const top = card(page, on).locator(".top");
  await need(top.getByText("waits on lane ci-done-comment", { exact: true }), "the top row has no single text run 'waits on lane ci-done-comment'");
  assert.match((await top.innerText()).replace(/\s+/g, " "), /waited .* waits on lane ci-done-comment$/, "the lane does not follow the wait in the top row");
  assert.equal(await card(page, on).getByText(/waits on lane/i).count(), 1, "the lane shows more than once on the card");
  assert.equal(await laPanel(page, on).count(), 0, "a lane alone draws a last-answer panel");
  assert.equal(await card(page, off).getByText(/waits on lane/i).count(), 0);
  assert.ok(Math.abs((await laBox(card(page, on))).h - (await laBox(card(page, off))).h) <= 1, "the lane added height to the card");
});

test("on an open card the panel sits after the stake lines, before the context, and stays put while an option is picked", async (t) => {
  const it = mk("pl-1a", 1, { added: ASKED_AFTER_SEND, holds: "A lane waits.", by: new Date(Date.now() + 3 * 864e5).toISOString(), lastAnswer: { choice: "a", note: "Only if cheap.", at: LA_AT }, reply: "I added option C. Pick again." });
  const page = await open(t, { items: [it] }); if (!page) return;
  const c = card(page, it);
  await laText(page, it);
  const title = await laBox(c.locator(".title")), holds = await laBox(c.locator(".stake.holds")), due = await laBox(c.locator(".stake.due"));
  const th = await laBox(laPanel(page, it)), ctx = await laBox(c.getByText("Which colour?", { exact: true })), opts = await laBox(c.locator(".opts"));
  assert.ok(title.bottom <= holds.top + 1 && holds.bottom <= due.top + 1, "the stake lines are not first under the title");
  assert.ok(th.top >= due.bottom - 1, `the panel starts at ${th.top}, above the last stake line's end at ${due.bottom}`);
  assert.ok(th.bottom <= ctx.top + 1, `the panel ends at ${th.bottom}, below the context's start at ${ctx.top}`);
  assert.ok(ctx.bottom <= opts.top + 1, "the context is not above the options");
  const before = await laText(page, it), rel = th.top - (await laBox(c)).top;
  await choose(page, it, "b"); // an unsent pick: nothing in the panel changes
  assert.equal(await laText(page, it), before, "picking an option changed the panel");
  assert.ok(Math.abs((await laBox(laPanel(page, it))).top - (await laBox(c)).top - rel) <= 1, "picking an option moved the panel");
});

test("a card with a saved answer keeps its receipt where it lands today, holds the thread in its fold below it, and shows the lane in the top row", async (t) => {
  const it = mk("rc-thread", 7, { lane: "ci-done-comment", lastAnswer: { choice: "b", note: "Only if cheap.", at: LA_AT }, reply: "I added option C. Pick again." });
  const plain = mk("rc-plain", 8);
  const page = await open(t, { items: [it, plain], answers: { ...laSaved(it, "a"), ...laSaved(plain, "a") } }); if (!page) return;
  const c = card(page, it), rc = c.locator(".receipt:has(.changebtn)");
  await need(rc, "the saved answer's receipt (with its Change button) is gone");
  assert.match(await c.getAttribute("class"), /answered/);
  assert.match(flat(await rc.innerText()), /You chose A: Red\./);
  assert.doesNotMatch(flat(await rc.innerText()), /Blue|Reply:|Your last answer/, "the thread is inside the receipt");
  // The thread sits in the fold, closed on load (answered-sink notes, pick 2): hidden until the owner unfolds the card.
  assert.equal(await laPanel(page, it).isVisible(), false, "the thread shows before the owner unfolds the card");
  await need(c.locator("button.unfold"), "the saved card with a thread has no fold control");
  await c.locator("button.unfold").click();
  const p = await laText(page, it);
  assert.match(p, /Your last answer, Oct 29, 14:05 CDT/);
  assert.match(p, /You chose B: Blue\./);
  assert.match(p, /Reply: I added option C\. Pick again\./);
  const r = await laBox(rc), th = await laBox(laPanel(page, it));
  assert.ok(th.top >= r.bottom - 1, `the thread starts at ${th.top}, above the receipt's end at ${r.bottom}`);
  const rp = await laBox(card(page, plain).locator(".receipt:has(.changebtn)")), at = (e, b) => b.top - e.top;
  assert.ok(Math.abs(at(await laBox(c), r) - at(await laBox(card(page, plain)), rp)) <= 1, "the thread moved the receipt from where it lands today");
  assert.match((await c.locator(".top").innerText()).replace(/\s+/g, " "), /Filing pending, sent .*waits on lane ci-done-comment$/, "the lane is not in the top row after the pill");
  assert.equal(await laPanel(page, plain).count(), 0, "a saved card with no thread fields drew a panel");
  assert.deepEqual(await card(page, plain).evaluate((e) => [...e.children].map((k) => k.tagName + "." + k.className)), ["DIV.top", "H3.title", "DIV.receipt"], "a saved card with no thread fields is not drawn as today");
});

test("pressing Change on a saved card with a thread opens the card with one panel, between the title and the context", async (t) => {
  const it = mk("rc-change", 7, { lastAnswer: { choice: "b", at: LA_AT }, reply: "I added option C. Pick again." });
  const page = await open(t, { items: [it], answers: laSaved(it, "a") }); if (!page) return;
  const c = card(page, it);
  await laText(page, it);
  await c.getByRole("button", { name: "Change", exact: true }).click();
  await need(c.locator(".opts"), "Change did not open the card");
  assert.doesNotMatch(await c.getAttribute("class"), /answered/);
  await laText(page, it); // still exactly one panel
  const title = await laBox(c.locator(".title")), th = await laBox(laPanel(page, it)), ctx = await laBox(c.getByText("Which colour?", { exact: true }));
  assert.ok(th.top >= title.bottom - 1 && th.bottom <= ctx.top + 1, "the panel is not between the title and the context");
});

test("a card with none of lastAnswer, reply and lane draws as today, and so does one whose three fields are empty", async (t) => {
  const plainD = mk("as-d", 1), plainT = { ...TASK, id: "as-t", n: 2 };
  const emptyD = mk("em-d", 3, { reply: "", lane: "", lastAnswer: null }), emptyT = { ...TASK, id: "em-t", n: 4, reply: "", lane: "", lastAnswer: null };
  const page = await open(t, { items: [plainD, plainT, emptyD, emptyT] }); if (!page) return;
  const shape = (it) => card(page, it).evaluate((c) => ({ kids: [...c.children].map((e) => e.tagName + "." + e.className), top: c.querySelector(".top").innerText.replace(/No\. \d+/, "").replace(/\s+/g, " ").trim() }));
  // The children of a plain open card, read from page.html at 2b66f6a3 plus the always-open note box (step note-always-open): a build that adds a wrapper or a row to a card with nothing to show fails here.
  const TODAY = { decision: ["DIV.top", "H3.title", "P.ctx", "P.about", "DIV.opts", "P.ready", "DIV.alts", "DIV.note", "P.dest"], task: ["DIV.top", "H3.title", "P.ctx", "P.about", "OL.steps", "P.ready", "DIV.alts", "DIV.note", "P.dest"] };
  for (const [plain, empty] of [[plainD, emptyD], [plainT, emptyT]]) {
    assert.equal(await laPanel(page, plain).count() + await laPanel(page, empty).count(), 0, `${plain.id}: a panel is drawn with nothing to show`);
    assert.doesNotMatch(await card(page, plain).innerText() + await card(page, empty).innerText(), /Your last answer|Reply:|waits on lane/i);
    assert.deepEqual((await shape(plain)).kids, TODAY[plain.kind], `${plain.id}: a card with no thread fields is not drawn as today`);
    assert.deepEqual(await shape(empty), await shape(plain), `${empty.id}: empty fields change the card`);
  }
});

for (const scheme of ["light", "dark"]) test(`a long lane slug and an unbroken reply stay inside their card at 390 wide, open and saved, ${scheme} scheme`, async (t) => {
  const url = "https://example.test/" + "very-long-path-segment-".repeat(6);
  const fields = { lane: "a-very-long-lane-branch-slug-".repeat(4), lastAnswer: { choice: "b", note: url, at: LA_AT }, reply: url };
  const open1 = mk("ov-open", 1, fields), saved1 = mk("ov-saved", 2, fields);
  const page = await open(t, { items: [open1, saved1], answers: laSaved(saved1), scheme, viewport: { width: 390, height: 900 } }); if (!page) return;
  await laText(page, open1); await laText(page, saved1);
  const m = await page.evaluate(() => ({
    sw: document.documentElement.scrollWidth, iw: innerWidth,
    out: [...document.querySelectorAll("article.card")].flatMap((c) => [...c.querySelectorAll(".top *, [aria-label^='Your last answer'] *, [aria-label='The reply'] *, [aria-label^='Your last answer'], [aria-label='The reply']")].filter((e) => e.getBoundingClientRect().right > c.getBoundingClientRect().right + 0.5).map((e) => c.id + " " + e.tagName + "." + e.className)),
  }));
  assert.ok(m.sw <= m.iw, `the page scrolls sideways: ${m.sw} over ${m.iw}`);
  assert.deepEqual(m.out, [], "an element runs past its card's right edge");
});

// The list of fields an item may carry is the page's own, in one JSON block, so a writer and a guard read it and the page warns by it.
// The block is read from the loaded page, as a browser parses it.
test("page.html carries one itemFields JSON block whose list holds reply, lastAnswer and lane and every field a fixture item has", async (t) => {
  const page = await open(t, { items: [DECISION] }); if (!page) return;
  const blocks = await page.evaluate(() => [...document.querySelectorAll("script#itemFields")].map((e) => ({ type: e.getAttribute("type"), text: e.textContent })));
  assert.equal(blocks.length, 1, 'page.html has no single <script type="application/json" id="itemFields">');
  assert.equal(blocks[0].type, "application/json");
  const list = JSON.parse(blocks[0].text);
  assert.ok(Array.isArray(list) && list.every((f) => typeof f === "string"), "itemFields is not a list of strings");
  assert.equal(new Set(list).size, list.length, "itemFields repeats a field");
  for (const f of ["reply", "lastAnswer", "lane"]) assert.ok(list.includes(f), `itemFields lacks ${f}`);
  for (const f of [...Object.keys(DECISION), ...Object.keys(TASK)]) assert.ok(list.includes(f), `itemFields lacks ${f}, a field the page reads today`);
});

// Rule ux-machine-text-hidden: the warning is one plain sentence, and the field names and the word itemFields sit in a closed disclosure.
test("an item with a field the page does not list shows one plain warning, and its field names sit in a closed disclosure", async (t) => {
  const odd = mk("odd-field", 1, { zzflavour: "mint", zzspin: 3 });
  const page = await open(t, { items: [odd] }); if (!page) return;
  await need(card(page, odd), "the item with an unknown field is not drawn");
  const warn = card(page, odd).locator('[role="status"]:visible');
  await need(warn, "the unknown-field warning is not one visible status line");
  const shown = flat(await warn.innerText());
  assert.doesNotMatch(shown, /zzflavour|zzspin|itemFields/, `the visible warning names a field: ${shown}`);
  assert.equal((shown.match(/[.!?](\s|$)/g) || []).length, 1, `the visible warning is not one sentence: ${shown}`);
  const box = card(page, odd).locator("details").filter({ hasText: "zzflavour" });
  await need(box, "the field names are not in a closed disclosure");
  assert.equal(await box.evaluate((d) => d.open), false, "the disclosure starts open");
  const NAMES = ["zzflavour", "zzspin", "itemFields"];
  for (const name of NAMES) {
    assert.ok((await box.getByText(name).count()) >= 1, `the disclosure does not hold ${name}`);
    assert.equal(await box.getByText(name).first().isVisible(), false, `${name} shows before the disclosure is opened`);
  }
  await box.locator("summary").click();
  assert.equal(await box.evaluate((d) => d.open), true, "the disclosure did not open");
  for (const name of NAMES) assert.equal(await box.getByText(name).first().isVisible(), true, `${name} is not shown once the disclosure is open`);
});

test("items with only listed fields show no unknown-field warning, new fields included", async (t) => {
  const fine = mk("fine-fields", 1, { reply: "Pick again.", lane: "some-lane", lastAnswer: { choice: "a", note: "n", at: LA_AT } });
  const page = await open(t, { items: [fine, DECISION, TASK] }); if (!page) return;
  assert.doesNotMatch(await page.locator("body").innerText(), /lastAnswer/, "a listed field was reported as unknown");
  assert.equal(await page.locator(".status.broken, [role=alert]").count(), 0, "a sound item shows a warning");
});

// ---------------------------------------------------------------- lane page-item-waits-on: an item that waits on a CI run or a PR
// Spec: docs/design/page-item-waits-notes.md (its picks: plain words for a run, "PR #n" for a PR, one span with a lane,
// the ring badge, Change kept) and the mockup docs/design/page-item-waits.html. The field `waits` is {repo, run} or {repo, pr}.
// An item with waits, a lastAnswer and no answers record is answered by its wait: it sinks to the Answered section, its badge
// reads "Sent <lastAnswer time>", and its rail chip says answered and waits. With waits and no lastAnswer it stays an open ask in
// its tier, with the wait span. Each case reads the card, its rail chip or its section, by where the part sits.
const WT_REPO = "shivinate7/q_max";
const WT_RUN = 41861801325;
const WT_AT = "2026-11-03T20:10:00Z"; // 14:10 CST: the time of the item's last answer
const WT_RUN_URL = `https://github.com/${WT_REPO}/actions/runs/${WT_RUN}`;
const WT_PR_URL = (pr) => `https://github.com/${WT_REPO}/pull/${pr}`;
// The copy may name the repo as " in q_max", since the page does not know its own repo yet (notes, section 1). Either form is the copy.
const RUN_COPY = /^waits on a CI run( in q_max)?$/;
const PR_COPY = (pr) => new RegExp(`^waits on PR #${pr}( in q_max)?$`);
const OPEN_TIERS = ["tier-holds", "tier-due", "tier-calm", "tier-stands"];
// No. 154 as the writer keeps it: a decision with its last answer on lastAnswer and no answers record. Each case adds the fields it tests.
const no154 = (over = {}) => mk("wt-154", 154, { title: "Pick the merge order for the q_max fix", ...over });
const ANSWERED = { choice: "a", at: WT_AT };
// A link's words as a reader hears them: its text without the arrow and the screen-reader words after it.
const wordsOf = (s) => flat(s.replace(/↗/g, "").replace(/, opens in a new tab/g, ""));
const linkWords = async (loc) => wordsOf(await loc.textContent());
const chipLabel = (page, it) => page.locator("#c-" + it.id).getAttribute("aria-label");

test("page-item-waits-on: No. 154 as stored today, answered on lastAnswer with no waits, is an owner ask in its tier (control)", async (t) => {
  const it = no154({ lastAnswer: ANSWERED });
  const page = await open(t, { items: [it] }); if (!page) return;
  const home = await sectionOf(page, it);
  assert.equal(home, "tier-calm", `No. 154 without waits is in ${home}, not in its open tier`);
  assert.doesNotMatch(await card(page, it).getAttribute("class"), /answered/, "No. 154 without waits is drawn as answered");
  assert.match(await chipLabel(page, it), /, open$/, "the rail chip of No. 154 without waits does not say open");
});

test("page-item-waits-on: No. 154 waiting on a CI run sits in the Answered section, with a Sent badge, the run link and an answered chip", async (t) => {
  const it = no154({ lastAnswer: ANSWERED, waits: { repo: WT_REPO, run: WT_RUN } });
  // A stale filed receipt for the item (its answer was closed once): the badge still reads Sent, never filed.
  const page = await open(t, { items: [it], receipts: { [it.id]: { filed: "2026-11-03T21:30:00Z" } } }); if (!page) return;
  assert.equal(await sectionOf(page, it), "tier-answered", "No. 154 is not in the Answered section");
  const c = card(page, it), badge = c.locator(".top .ans");
  await need(badge, "No. 154 has no badge in its top row");
  assert.equal(flat(await badge.textContent()), "Sent Nov 3, 14:10 CST", "the badge is not Sent with the last answer's time");
  assert.doesNotMatch(await badge.getAttribute("class"), /filed/, "the badge draws a filed tick");
  const link = c.locator(`.top a[href="${WT_RUN_URL}"]`);
  await need(link, "No. 154's top row has no link to its CI run");
  assert.match(await linkWords(link), RUN_COPY, "the run link does not read 'waits on a CI run'");
  const chip = await chipLabel(page, it);
  assert.match(chip, /, answered, waits on a CI run( in q_max)?$/, `the rail chip reads "${chip}", not answered and waiting on a CI run`);
  const cls = await page.locator("#c-" + it.id).getAttribute("class");
  assert.match(cls, /\bsent\b/, "the rail chip is not drawn as sent");
  assert.doesNotMatch(cls, /filed/, "the rail chip is drawn as filed");
  assert.match(flat(await c.locator(".receipt").innerText()), /You chose A: Red\./, "the answer line is not drawn from lastAnswer");
});

test("page-item-waits-on: No. 154 waiting on PR #1011 links the PR, and its copy reads waits on PR #1011", async (t) => {
  const it = no154({ lastAnswer: ANSWERED, waits: { repo: WT_REPO, pr: 1011 } });
  const page = await open(t, { items: [it] }); if (!page) return;
  const link = card(page, it).locator(`.top a[href="${WT_PR_URL(1011)}"]`);
  await need(link, "No. 154's top row has no link to PR #1011");
  assert.match(await linkWords(link), PR_COPY(1011), "the PR link does not read 'waits on PR #1011'");
});

test("page-item-waits-on: No. 154 with a lane and a wait shows one span, 'waits on lane cache-split and PR #1011', and only PR #1011 is its link", async (t) => {
  const it = no154({ lastAnswer: ANSWERED, lane: "cache-split", waits: { repo: WT_REPO, pr: 1011 } });
  const page = await open(t, { items: [it] }); if (!page) return;
  const spans = card(page, it).locator(".top .onlane");
  const n = await spans.count();
  assert.equal(n, 1, `the top row has ${n} lane or wait spans, not one`);
  assert.match(wordsOf(await spans.first().textContent()), /^waits on lane cache-split and PR #1011( in q_max)?$/, "the span does not read 'waits on lane cache-split and PR #1011'");
  const inner = spans.first().locator("a");
  await need(inner, "the span has no link");
  assert.equal(await inner.getAttribute("href"), WT_PR_URL(1011), "the span's link is not PR #1011");
  assert.match(await linkWords(inner), /^PR #1011( in q_max)?$/, "the link holds more than PR #1011");
});

test("page-item-waits-on: No. 154 with waits and no lastAnswer stays an open ask in its tier, with the wait span and an open chip", async (t) => {
  const it = no154({ waits: { repo: WT_REPO, pr: 1011 } });
  const page = await open(t, { items: [it] }); if (!page) return;
  const home = await sectionOf(page, it);
  assert.ok(OPEN_TIERS.includes(home), `No. 154 with no lastAnswer is in ${home}, not in an open tier`);
  const link = card(page, it).locator(`.top a[href="${WT_PR_URL(1011)}"]`);
  await need(link, "No. 154 with no lastAnswer has no wait span linking PR #1011");
  assert.match(await linkWords(link), PR_COPY(1011), "the wait span does not read 'waits on PR #1011'");
  assert.doesNotMatch(await card(page, it).getAttribute("class"), /answered/, "No. 154 with no lastAnswer is drawn as answered");
  assert.match(await chipLabel(page, it), /, open$/, "the rail chip of No. 154 with no lastAnswer does not say open");
});

test("page-item-waits-on: No. 154 waiting on a run is never folded under Asked before, though it was added before the last answer", async (t) => {
  const seenOpen = mk("wt-seen-open", 2, { added: at(5) });
  const it = no154({ added: at(5), lastAnswer: ANSWERED, waits: { repo: WT_REPO, run: WT_RUN } });
  const page = await open(t, { items: [it, seenOpen] }); if (!page) return;
  assert.equal(await sectionOf(page, it), "tier-answered", "No. 154 is not in the Answered section, so it can sit under Asked before");
  assert.equal(await card(page, it).getAttribute("data-seen"), null, "No. 154 is marked seen");
  assert.deepEqual(await cardsIn(page, "#tier-calm"), [seenOpen.id], "No. 154 is in the Whenever tier, under the Asked before line");
});

test("page-item-waits-on: in the Answered section No. 154 sorts by its lastAnswer time among the items with answer records", async (t) => {
  const it = no154({ lastAnswer: ANSWERED, waits: { repo: WT_REPO, run: WT_RUN } });
  const newer = mk("wt-rec-new", 2, { added: at(5) }), older = mk("wt-rec-old", 3, { added: at(5) });
  const records = { ...answerOf(newer, "a", { at: "2026-11-04T08:00:00Z" }), ...answerOf(older, "a", { at: "2026-10-26T01:00:00Z" }) };
  const page = await open(t, { items: [it, newer, older], answers: records }); if (!page) return;
  assert.deepEqual(await cardsIn(page, "#tier-answered"), [newer.id, it.id, older.id], "the Answered section is not newest first, with No. 154 at its lastAnswer time");
});

test("page-item-waits-on: itemFields lists waits, and No. 154 with waits draws no unknown-field warning", async (t) => {
  const it = no154({ lastAnswer: ANSWERED, waits: { repo: WT_REPO, run: WT_RUN } });
  const page = await open(t, { items: [it] }); if (!page) return;
  const list = JSON.parse(await page.locator("script#itemFields").textContent());
  assert.ok(list.includes("waits"), "itemFields does not list waits");
  assert.doesNotMatch(await card(page, it).innerText(), /does not draw/, "No. 154 draws the unknown-field warning for waits");
});

test("page-item-waits-on: No. 154 waiting on a run: Change reopens it on lastAnswer, an emptied pick offers no Withdraw, and a Send writes its answer and deletes nothing", async (t) => {
  const it = no154({ lastAnswer: ANSWERED, waits: { repo: WT_REPO, run: WT_RUN } });
  const page = await open(t, { items: [it] }); if (!page) return;
  const c = card(page, it), change = c.getByRole("button", { name: "Change", exact: true });
  await need(change, "No. 154 has no Change button");
  await change.click();
  await need(c.locator(".opts"), "Change did not open No. 154's options");
  assert.equal(await page.isChecked(`#o-${it.id}-a`), true, "Change did not reopen No. 154 on its last pick");
  // A click on the chosen option empties the pick, as it does on a saved answer. Send would withdraw only a saved answer.
  await choose(page, it, "a");
  assert.doesNotMatch(await page.locator("#send").textContent(), /Withdraw/, "an emptied pick on No. 154 offers to withdraw an answer");
  await choose(page, it, "b");
  await send(page);
  assert.ok(await holds(page, (id) => !!window.__answers()[id], it.id), "Send wrote no answer for No. 154");
  assert.equal((await answers(page))[it.id].choice, "b", "the answer written for No. 154 is not its new pick");
  assert.deepEqual(await page.evaluate(() => window.__log.filter((l) => l[0] === "delete")), [], "Send deleted a record for No. 154");
});

// A wait value is valid when it is a positive whole number, or a string of digits with no leading zero. Any other value is malformed.
const WT_BAD = [0, "0", "012", -5, "abc"];

test("page-item-waits-on: No. 154 with stands, waits and lastAnswer is staged for nothing: the bar counts only the other item, and Send writes no answer for No. 154", async (t) => {
  const it = no154({ stands: true, lastAnswer: ANSWERED, waits: { repo: WT_REPO, run: WT_RUN } });
  const other = mk("wt-other", 2, { added: "2026-11-04T09:00:00Z" }); // added after the last answer, so it is new and unfolded
  const page = await open(t, { items: [it, other] }); if (!page) return;
  await need(card(page, it), "No. 154 has no card");
  assert.equal(await page.locator("#send").isDisabled(), true, "No. 154 is staged though nothing is picked for the other item");
  await choose(page, other, "b");
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer", "the bar counts No. 154 among the ready answers");
  await send(page);
  assert.ok(await holds(page, (id) => !!window.__answers()[id], other.id), "Send wrote no answer for the other item");
  assert.equal(it.id in (await answers(page)), false, "Send wrote answers/wt-154 for an item answered by its wait");
});

test("page-item-waits-on: a run or PR number that is malformed with lastAnswer stays an open ask in its tier", async (t) => {
  const bad = [];
  WT_BAD.forEach((v, i) => {
    bad.push(mk("wt-bad-run-" + i, 160 + i, { title: "Malformed run " + JSON.stringify(v), lastAnswer: ANSWERED, waits: { repo: WT_REPO, run: v } }));
    bad.push(mk("wt-bad-pr-" + i, 170 + i, { title: "Malformed pr " + JSON.stringify(v), lastAnswer: ANSWERED, waits: { repo: WT_REPO, pr: v } }));
  });
  const page = await open(t, { items: bad }); if (!page) return;
  for (const it of bad) {
    const home = await sectionOf(page, it);
    assert.ok(OPEN_TIERS.includes(home), `${it.title} is in ${home}, not in an open tier`);
    assert.equal(await card(page, it).locator(".top a").count(), 0, `${it.title} draws a wait link`);
  }
});

test("page-item-waits-on: a run or PR given as a string of digits with no leading zero reads answered, as a number does", async (t) => {
  const run = no154({ lastAnswer: ANSWERED, waits: { repo: WT_REPO, run: String(WT_RUN) } });
  const pr = mk("wt-str-pr", 155, { title: "Pick the PR order", lastAnswer: ANSWERED, waits: { repo: WT_REPO, pr: "1011" } });
  const page = await open(t, { items: [run, pr] }); if (!page) return;
  assert.equal(await sectionOf(page, run), "tier-answered", "No. 154 with a string run is not in the Answered section");
  await need(card(page, run).locator(`.top a[href="${WT_RUN_URL}"]`), "No. 154 with a string run has no link to its CI run");
  assert.equal(await sectionOf(page, pr), "tier-answered", "No. 155 with a string PR is not in the Answered section");
  await need(card(page, pr).locator(`.top a[href="${WT_PR_URL(1011)}"]`), "No. 155 with a string PR has no link to PR #1011");
});

// An arbiter ruling (decision session-tiers, Arbiter, "On the page"): the writer files it as a closed item with arbiter: true,
// home = the ruling's record id, pick = the ruled option, why and ruled. Every case keeps DECISION open and first: open() waits
// for an open card, so a red run fails on the arbiter assertions, not on that wait.
const ARBITER = mk("arbiter-d901", 901, { status: "closed", arbiter: true, home: "D-901", pick: "a", why: "The arbiter ruled Red.", ruled: "2026-10-30T17:40:00Z" });
const overturn = (from) => from.getByRole("button", { name: /^Overturn/ });

test("a closed arbiter item shows as one card with its record id, the ruled option and one Overturn button", async (t) => {
  const page = await open(t, { items: [DECISION, ARBITER] }); if (!page) return;
  await need(card(page, ARBITER), "the closed arbiter item has no card");
  assert.equal(await page.locator('[id^="item-"]').count(), 2, "the arbiter item is not drawn as exactly one card");
  const text = await card(page, ARBITER).innerText();
  assert.match(text, /D-901/, "the card does not name the ruling's record");
  assert.match(text, /Red/, "the card does not name the ruled option");
  assert.doesNotMatch(text, /Blue/, "the card names an option the arbiter did not rule");
  assert.equal(await overturn(card(page, ARBITER)).count(), 1, "the card has not exactly one Overturn button");
});

test("Overturn then Send writes an overturn answer for the item and writes nothing to items", async (t) => {
  const page = await open(t, { items: [DECISION, ARBITER] }); if (!page) return;
  await need(overturn(card(page, ARBITER)), "the arbiter card has no Overturn button");
  await overturn(card(page, ARBITER)).click();
  await send(page);
  assert.ok(await holds(page, (id) => !!window.__answers()[id], ARBITER.id), "Send wrote no answer for the arbiter item");
  const a = (await answers(page))[ARBITER.id];
  assert.deepEqual([a.item, a.choice], [ARBITER.id, "overturn"]);
  assert.deepEqual(await page.evaluate(() => window.__log.filter((l) => l[1] === "items")), [], "an Overturn wrote or deleted an items doc");
});

test("a closed item with no arbiter flag stays hidden next to a closed arbiter item", async (t) => {
  const plain = mk("closed-plain", 902, { status: "closed" });
  const page = await open(t, { items: [DECISION, ARBITER, plain] }); if (!page) return;
  await need(card(page, ARBITER), "the closed arbiter item has no card");
  assert.equal(await card(page, plain).count(), 0, "a closed item with no arbiter flag is shown");
  assert.equal(await page.locator('[id^="item-"]').count(), 2, "the page draws a card for a closed item that is no ruling");
  assert.equal(await overturn(page).count(), 1, "the page offers Overturn on more than the arbiter item");
});

// An answer or a draft that is no overturn. A ruling was an open item once, so a saved answer or a draft under its id
// may hold an option key ("a"). Only choice "overturn" is an overturn; any other record under a ruling's id is stale.
const staleAnswer = { [ARBITER.id]: { item: ARBITER.id, n: 901, at: "2026-10-30T18:00:00Z", choice: "a", note: "" } };
const staleDraft = { "waiting.draft": JSON.stringify({ [ARBITER.id]: { choice: "a" } }) };
const overturnAnswer = { [ARBITER.id]: { item: ARBITER.id, n: 901, at: "2026-10-30T18:00:00Z", choice: "overturn", note: "" } };
const pressed = (page) => overturn(card(page, ARBITER)).getAttribute("aria-pressed");

test("a saved answer that is no overturn does not read as an overturn on the ruling card", async (t) => {
  const page = await open(t, { items: [DECISION, ARBITER], answers: staleAnswer }); if (!page) return;
  await need(card(page, ARBITER), "the closed arbiter item has no card");
  assert.doesNotMatch(await card(page, ARBITER).innerText(), /You overturned/, "a saved answer with choice a shows as an overturn");
  assert.equal(await overturn(card(page, ARBITER)).count(), 1, "the ruling card no longer offers Overturn");
  assert.equal(await pressed(page), "false", "the ruling card shows as overturned");
});

test("a stale pick draft under a ruling's id is not sent", async (t) => {
  const page = await open(t, { items: [DECISION, ARBITER], storage: staleDraft }); if (!page) return;
  await need(card(page, ARBITER), "the closed arbiter item has no card");
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is open on a stale pick draft alone");
  await choose(page, DECISION, "a");
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer", "Send counts the stale draft");
  await send(page);
  await holds(page, (id) => !!window.__answers()[id], DECISION.id);
  assert.equal(ARBITER.id in await answers(page), false, "Send wrote an answer for the ruling from a stale draft");
});

test("the Copy line leaves out a stale pick draft under a ruling's id", async (t) => {
  const page = await open(t, { items: [DECISION, ARBITER], storage: staleDraft, failSet: true }); if (!page) return;
  await need(card(page, ARBITER), "the closed arbiter item has no card");
  await choose(page, DECISION, "a"); // a ready answer, so the failed write opens the Copy line
  await send(page);
  await page.locator("#barStatus", { hasText: "Not saved (denied)" }).waitFor();
  await stubClipboard(page, false);
  await page.click("#copy");
  const copied = await page.evaluate(() => window.__copied);
  assert.doesNotMatch(copied, /901/, "the Copy line carries the stale pick draft of the ruling: " + copied);
  assert.equal(copied, "27 a");
});

test("a ruling is no open question: the counts and the bar count only the open item, and All answered shows with the ruling unpressed", async (t) => {
  const page = await open(t, { items: [DECISION, ARBITER] }); if (!page) return;
  await need(card(page, ARBITER), "the closed arbiter item has no card");
  const count = async () => (await page.locator("#qCount").textContent()).trim();
  assert.equal(await count(), "1", "the Questions count includes the ruling");
  assert.match(await page.locator("#barStatus").innerText(), /\b1 stays open/, "the bar does not count the one open item as staying open");
  assert.doesNotMatch(await page.locator("#barStatus").innerText(), /All answered/, "All answered shows with an open item");
  await overturn(card(page, ARBITER)).click();
  assert.equal(await count(), "1", "a pressed Overturn changes the Questions count");
  assert.match(await page.locator("#barStatus").innerText(), /\b1 stays open/, "a pressed Overturn changes the stay-open count");
  await overturn(card(page, ARBITER)).click(); // unpress: the ruling stands unpressed
  await choose(page, DECISION, "a"); await send(page);
  await page.locator("#barStatus", { hasText: "All answered." }).waitFor();
  assert.equal(await count(), "0", "the Questions count still includes the ruling");
  assert.doesNotMatch(await page.locator("#barStatus").innerText(), /stays? open/, "the bar counts the unpressed ruling as staying open");
  assert.equal(await pressed(page), "false", "answering the open item pressed the Overturn");
});

test("the bar reads 2 stay open. with two open items, the plural form", async (t) => {
  const page = await open(t, { items: [DECISION, TASK] }); if (!page) return;
  assert.match(await page.locator("#barStatus").innerText(), /\b2 stay open\./, "the bar does not read 2 stay open. with two open items");
});

test("Undo of a sent overturn removes the answer and the ruling card is back, with no receipt", async (t) => {
  const page = await open(t, { items: [DECISION, ARBITER] }); if (!page) return;
  await need(overturn(card(page, ARBITER)), "the arbiter card has no Overturn button");
  await overturn(card(page, ARBITER)).click();
  await send(page);
  assert.ok(await holds(page, (id) => !!window.__answers()[id], ARBITER.id), "Send wrote no answer for the arbiter item");
  assert.match(await card(page, ARBITER).innerText(), /You overturned/, "the sent overturn shows no receipt");
  await page.locator("#undoBtn").click();
  assert.ok(await holds(page, (id) => !(id in window.__answers()), ARBITER.id), "Undo left the overturn answer");
  assert.deepEqual(await page.evaluate((id) => window.__log.filter((l) => l[0] === "delete" && l[1] === "answers" && l[2] === id), ARBITER.id), [["delete", "answers", ARBITER.id]], "Undo did not delete answers/<id>");
  assert.deepEqual(await page.evaluate(() => window.__log.filter((l) => l[1] === "items")), [], "an Undo wrote or deleted an items doc");
  assert.equal(await card(page, ARBITER).locator(".receipt").count(), 0, "the ruling card still shows a receipt");
  assert.doesNotMatch(await card(page, ARBITER).innerText(), /You overturned/, "the ruling card still says it was overturned");
  // Undo hands the owner's pick back as a draft, as it does on a decision (undoSend): the Overturn is pressed again but unsent.
  assert.equal(await pressed(page), "true", "Undo lost the owner's pressed Overturn");
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer", "the undone overturn is not ready to send again");
});

test("Withdraw of a sent overturn removes the answer and the ruling card is back, unpressed", async (t) => {
  const page = await open(t, { items: [DECISION, ARBITER], answers: overturnAnswer }); if (!page) return;
  await need(card(page, ARBITER), "the closed arbiter item has no card");
  assert.match(await card(page, ARBITER).innerText(), /You overturned/, "a saved overturn shows no receipt");
  await card(page, ARBITER).getByRole("button", { name: "Change" }).click();
  assert.equal(await pressed(page), "true", "Change on a saved overturn does not bring the pressed Overturn back");
  await overturn(card(page, ARBITER)).click(); // unpress: nothing is left to send
  assert.equal(await page.locator("#send").textContent(), "Withdraw answer");
  await send(page);
  assert.ok(await holds(page, (id) => !(id in window.__answers()), ARBITER.id), "Withdraw left the overturn answer");
  assert.deepEqual(await page.evaluate(() => window.__log), [["delete", "answers", ARBITER.id]], "Withdraw wrote more than the one delete of answers/<id>");
  assert.equal(await card(page, ARBITER).locator(".receipt").count(), 0, "the ruling card still shows a receipt");
  assert.doesNotMatch(await card(page, ARBITER).innerText(), /You overturned/, "the ruling card still says it was overturned");
  assert.equal(await pressed(page), "false", "the ruling card is not back to its unpressed state");
});

// ---------------------------------------------------------------- parked lines: Unpark and Drop

// A parked line is a .pk in .parked .pk-list, with two .btn.pkb acts. A meta/page.parked entry is { id, ref, note }.
// An entry with no id has no store key, so its acts stay off. A press stages an act; Send writes answers/park.<id>.
const PARK_A = { id: "ci-cap-raise", ref: "Step ci-cap-raise, a 20-minute cap for one CI job", note: "Wait until the mutation job is split." };
const PARK_B = { id: "rail-filed-count", ref: "D41, a count of filed answers on the rail", note: "Wait for a month of use first." };
const PARK_NOID = { ref: "Debt label-once-js, the label check reads script text", note: "Low harm. Look again in December." };
const PARK_META = { writer: "triage", parked: [PARK_A, PARK_B] };
// A dot is in no item slug, so a park key never meets an item's key.
const parkKey = (p) => "park." + p.id;
const parkLine = (page, p) => page.locator(".parked .pk-list .pk", { hasText: p.ref });
const parkBtn = (page, p, act) => parkLine(page, p).locator(".btn.pkb", { hasText: act === "unpark" ? "Unpark" : "Drop" });
// The meta doc and the answers arrive after the items. Wait until the page holds them, then read the DOM.
const parkLoaded = (page, key = null) => page.waitForFunction((k) => !!(state.meta && state.meta.parked) && (k === null || !!state.answers[k]), key, { timeout: 3000 }).catch(() => {});
// Off is aria-disabled (the line stays focusable) or the disabled attribute.
const parkOff = async (b) => (await b.getAttribute("aria-disabled")) === "true" || (await b.isDisabled());
// Each write as [kind, collection, id]: the body of a set is left out, so a case compares the write, not its content.
const parkWrites = (page) => page.evaluate(() => window.__log.filter((l) => l[0] === "set" || l[0] === "delete").map((l) => l.slice(0, 3)));
// The sent badge on a line ("Unpark sent", "Drop sent"). It renders after the write, so wait for it, then return it.
const parkBadge = async (page, p, text) => { await parkLine(page, p).locator(".ans", { hasText: text }).waitFor({ timeout: 3000 }).catch(() => {}); return parkLine(page, p).locator(".ans", { hasText: text }); };

test("Unpark then Send writes the parked act as an unpark record and no other write", async (t) => {
  const page = await open(t, { items: [DECISION], meta: PARK_META }); if (!page) return;
  const dialogs = []; page.on("dialog", (d) => { dialogs.push(d.message()); d.dismiss(); });
  await parkLoaded(page);
  await need(parkBtn(page, PARK_A, "unpark"), "the parked line has no Unpark button");
  await parkBtn(page, PARK_A, "unpark").click();
  assert.deepEqual(dialogs, [], "a press opened a dialog");
  assert.deepEqual(await parkWrites(page), [], "a press wrote before Send");
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer", "the Send bar does not count the staged Unpark");
  await send(page);
  await page.waitForFunction((k) => !!window.__answers()[k], parkKey(PARK_A));
  const rec = (await answers(page))[parkKey(PARK_A)];
  assert.deepEqual(Object.keys(rec).sort(), ["act", "at", "id", "note", "parked", "ref"], "the park record has the wrong fields");
  assert.deepEqual([rec.parked, rec.id, rec.act, rec.ref, rec.note], [true, PARK_A.id, "unpark", PARK_A.ref, PARK_A.note]);
  assert.ok(!Number.isNaN(Date.parse(rec.at)), "at is not an ISO time");
  await need(await parkBadge(page, PARK_A, "Unpark sent"), "the line shows no Unpark sent badge after Send");
  assert.deepEqual(await parkWrites(page), [["set", "answers", parkKey(PARK_A)]], "Send wrote more than the one park record");
});

test("Drop then Send writes the parked act as a drop record, and the line strikes at once", async (t) => {
  const page = await open(t, { items: [DECISION], meta: PARK_META }); if (!page) return;
  await parkLoaded(page);
  await need(parkBtn(page, PARK_A, "drop"), "the parked line has no Drop button");
  await parkBtn(page, PARK_A, "drop").click();
  assert.match((await parkLine(page, PARK_A).getAttribute("class")) || "", /\bdrop\b/, "the staged Drop does not strike the line");
  assert.deepEqual(await parkWrites(page), [], "a Drop press wrote before Send");
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer", "the Send bar does not count the staged Drop");
  await send(page);
  await page.waitForFunction((k) => !!window.__answers()[k], parkKey(PARK_A));
  const rec = (await answers(page))[parkKey(PARK_A)];
  assert.deepEqual([rec.parked, rec.id, rec.act, rec.ref, rec.note], [true, PARK_A.id, "drop", PARK_A.ref, PARK_A.note]);
  await need(await parkBadge(page, PARK_A, "Drop sent"), "the line shows no Drop sent badge after Send");
  assert.deepEqual(await parkWrites(page), [["set", "answers", parkKey(PARK_A)]], "Send wrote more than the one park record");
});

test("Undo after a parked Send deletes the park record and hands the press back as a draft", async (t) => {
  const page = await open(t, { items: [DECISION], meta: PARK_META }); if (!page) return;
  await parkLoaded(page);
  await need(parkBtn(page, PARK_A, "unpark"), "the parked line has no Unpark button");
  await parkBtn(page, PARK_A, "unpark").click();
  await send(page);
  await page.waitForFunction((k) => !!window.__answers()[k], parkKey(PARK_A));
  await page.locator("#undoBtn").waitFor({ timeout: 3000 }).catch(() => {});
  await need(page.locator("#undoBtn"), "Send shows no Undo after a parked act");
  await page.locator("#undoBtn").click();
  await page.waitForFunction((k) => !(k in window.__answers()), parkKey(PARK_A));
  assert.deepEqual((await parkWrites(page)).filter((l) => l[0] === "delete"), [["delete", "answers", parkKey(PARK_A)]], "Undo did not delete answers/park.<id> once");
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer", "Undo did not hand the Unpark back as a draft");
});

test("a parked line with no id has both acts off, a press on it stages nothing, and a line with an id stays live", async (t) => {
  const page = await open(t, { items: [DECISION], meta: { writer: "triage", parked: [PARK_A, PARK_NOID] } }); if (!page) return;
  await parkLoaded(page);
  await need(parkLine(page, PARK_NOID), "the line with no id is not a .pk in .parked .pk-list");
  for (const act of ["unpark", "drop"]) {
    const b = parkBtn(page, PARK_NOID, act);
    await need(b, "the line with no id has no " + act + " button");
    assert.equal(await parkOff(b), true, act + " is on for a line with no id");
    await b.click({ force: true });
  }
  assert.equal(await page.locator("#send").isDisabled(), true, "a press on a line with no id staged an act");
  assert.deepEqual(await parkWrites(page), [], "a press on a line with no id wrote to the store");
  assert.equal(await parkOff(parkBtn(page, PARK_A, "unpark")), false, "the Unpark on a line with an id is off");
});

test("an existing park answer shows Unpark sent on its line at load, and counts toward no item", async (t) => {
  const saved = { [parkKey(PARK_A)]: { parked: true, id: PARK_A.id, act: "unpark", ref: PARK_A.ref, note: PARK_A.note, at: "2026-11-01T17:42:00.000Z" } };
  const page = await open(t, { items: [DECISION], meta: PARK_META, answers: saved }); if (!page) return;
  await parkLoaded(page, parkKey(PARK_A));
  await need(parkLine(page, PARK_A), "the parked line is not a .pk in .parked .pk-list");
  await need(await parkBadge(page, PARK_A, "Unpark sent"), "the line shows no Unpark sent badge on load");
  assert.equal(await page.locator("#send").isDisabled(), true, "a saved park answer counts as a ready act");
  const bar = await page.locator("#barStatus").innerText();
  assert.match(bar, /\b1 stays open/, "the bar does not count the open item: " + bar);
  assert.doesNotMatch(bar, /All answered/, "a park answer counts as the answer to an item: " + bar);
});

// Park keys are park.<id>. These cases read a park line only through its own key and its own id: never through an item's
// key, an Object.prototype name, or a DOM id that another element already holds.
const PARK_X = { id: "x", ref: "Line x, a parked line whose id shares a prefix with an item", note: "Hold it." };
const PARK_C = { id: "constructor", ref: "Line constructor, a parked line whose id is an Object.prototype name", note: "Keep it." };
const PARK_H = { id: "h", ref: "Line h, a parked line with the id h", note: "Keep it." };

test("a park line never reads an item's answer, and Unpark then Send leaves that answer alone", async (t) => {
  const itemAnswer = { item: "park-x", n: 1, at: "2026-11-01T17:00:00.000Z", choice: "a", note: "" };
  const page = await open(t, { items: [mk("park-x", 1)], meta: { writer: "triage", parked: [PARK_X] }, answers: { "park-x": itemAnswer } }); if (!page) return;
  await parkLoaded(page);
  await need(parkLine(page, PARK_X), "the parked line is not a .pk in .parked .pk-list");
  assert.equal(await parkLine(page, PARK_X).locator(".ans").count(), 0, "line x shows a sent badge it never sent, read from the item park-x");
  await need(parkBtn(page, PARK_X, "unpark"), "the parked line has no Unpark button");
  await parkBtn(page, PARK_X, "unpark").click();
  await send(page);
  await page.waitForFunction((k) => !!window.__answers()[k], parkKey(PARK_X));
  assert.deepEqual((await answers(page))["park-x"], itemAnswer, "Unpark and Send changed the item's answer under park-x");
  assert.deepEqual((await parkWrites(page)).filter((l) => l[2] === "park-x"), [], "Send wrote under the item's key park-x");
});

test("every DOM id on the page is unique, with two parked entries that have no id and one with the id h", async (t) => {
  const noA = { ref: "No id line A, a line the writer has not prepared", note: "A." };
  const noB = { ref: "No id line B, a line the writer has not prepared", note: "B." };
  const page = await open(t, { items: [DECISION], meta: { writer: "triage", parked: [noA, noB, PARK_H] } }); if (!page) return;
  await parkLoaded(page);
  await need(parkLine(page, PARK_H), "the line with the id h is not a .pk in .parked .pk-list");
  await need(parkLine(page, noB), "the second line with no id is not a .pk in .parked .pk-list");
  const dupes = await page.evaluate(() => { const seen = new Set(), out = []; document.querySelectorAll("[id]").forEach((el) => { if (seen.has(el.id)) out.push(el.id); seen.add(el.id); }); return out; });
  assert.deepEqual(dupes, [], "duplicate DOM ids: " + dupes.join(", "));
});

test("a parked entry with the id constructor has both acts on, and Unpark stages and sends it", async (t) => {
  const page = await open(t, { items: [DECISION], meta: { writer: "triage", parked: [PARK_C] } }); if (!page) return;
  await parkLoaded(page);
  await need(parkLine(page, PARK_C), "the line with the id constructor is not a .pk in .parked .pk-list");
  for (const act of ["unpark", "drop"]) {
    const b = parkBtn(page, PARK_C, act);
    await need(b, "the line with the id constructor has no " + act + " button");
    assert.equal(await parkOff(b), false, act + " is off for the id constructor");
  }
  await parkBtn(page, PARK_C, "unpark").click();
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer", "the staged Unpark on the id constructor is not counted");
  await send(page);
  await page.waitForFunction((k) => !!window.__answers()[k], parkKey(PARK_C));
});

test("a failed Send with a staged park act: the Copy text carries the park act", async (t) => {
  const page = await open(t, { items: [DECISION], meta: PARK_META, failSet: true }); if (!page) return;
  await parkLoaded(page);
  await need(parkBtn(page, PARK_A, "unpark"), "the parked line has no Unpark button");
  await parkBtn(page, PARK_A, "unpark").click();
  await send(page);
  await page.locator("#barStatus", { hasText: "Not saved (denied)" }).waitFor();
  await stubClipboard(page, false);
  await page.click("#copy");
  const copied = await page.evaluate(() => window.__copied);
  assert.ok(typeof copied === "string" && copied.includes(PARK_A.ref), "the Copy text leaves out the staged park act: " + copied);
});

test("Change then clear on a sent park line, then Send, deletes answers/park.<id>", async (t) => {
  const saved = { [parkKey(PARK_A)]: { parked: true, id: PARK_A.id, act: "unpark", ref: PARK_A.ref, note: PARK_A.note, at: "2026-11-01T17:42:00.000Z" } };
  const page = await open(t, { items: [DECISION], meta: PARK_META, answers: saved }); if (!page) return;
  await parkLoaded(page, parkKey(PARK_A));
  await need(await parkBadge(page, PARK_A, "Unpark sent"), "the line shows no Unpark sent badge on load");
  const change = parkLine(page, PARK_A).locator("button", { hasText: "Change" });
  await need(change, "the sent park line has no Change button");
  await change.click();
  const unpark = parkBtn(page, PARK_A, "unpark");
  if ((await unpark.getAttribute("aria-pressed")) === "true") await unpark.click();
  assert.equal(await page.locator("#send").textContent(), "Withdraw answer", "Send does not offer to withdraw the cleared park line");
  await send(page);
  await page.waitForFunction((k) => !(k in window.__answers()), parkKey(PARK_A));
  assert.deepEqual(await parkWrites(page), [["delete", "answers", parkKey(PARK_A)]], "Withdraw did not delete answers/park.<id> once");
});

test("at 1280 wide, sending a park act does not move the parked lines below it", async (t) => {
  const page = await open(t, { items: [DECISION], meta: { writer: "triage", parked: [PARK_A, PARK_B, PARK_X] }, viewport: { width: 1280, height: 900 } }); if (!page) return;
  await parkLoaded(page);
  await need(parkBtn(page, PARK_A, "unpark"), "the parked line has no Unpark button");
  await parkBtn(page, PARK_A, "unpark").click();
  const rows = () => page.evaluate(() => [...document.querySelectorAll(".parked .pk-list .pk")].map((el) => ({ text: el.textContent, top: el.getBoundingClientRect().top })));
  const before = await rows();
  await send(page);
  await page.locator("#sent").waitFor({ state: "visible", timeout: 3000 }).catch(() => {}); // the Sent panel shows after any Send, whatever the key
  const after = await rows();
  const acted = before.findIndex((r) => r.text.includes(PARK_A.ref));
  assert.ok(acted >= 0 && before.length === 3 && after.length === 3, "expected three parked lines, got " + before.length + " before and " + after.length + " after");
  for (let i = acted + 1; i < before.length; i++) {
    assert.ok(after[i].text.includes(before[i].text.slice(0, 20)), "parked lines changed order on Send");
    assert.ok(Math.abs(after[i].top - before[i].top) <= 0.5, "the line below the sent park act moved by " + (after[i].top - before[i].top).toFixed(2) + "px: " + before[i].text.slice(0, 40));
  }
});

// The meta listener runs keepRouted(was, now) and then renders. These cases make the same two calls, so the list change
// goes through the same code the writer's update does.
const changeMeta = (page, parked) => page.evaluate((list) => { const was = state.meta; state.meta = { writer: "triage", parked: list }; keepRouted(was, state.meta); render(); }, parked);

test("a sent park line whose entry leaves the list while in view shows the filled badge and keeps its height", async (t) => {
  const saved = { [parkKey(PARK_A)]: { parked: true, id: PARK_A.id, act: "unpark", ref: PARK_A.ref, note: PARK_A.note, at: "2026-11-01T17:42:00.000Z" } };
  const page = await open(t, { items: [DECISION], meta: PARK_META, answers: saved, viewport: { width: 1280, height: 900 } }); if (!page) return;
  await parkLoaded(page, parkKey(PARK_A));
  await need(await parkBadge(page, PARK_A, "Unpark sent"), "the line shows no Unpark sent badge on load");
  const line = parkLine(page, PARK_A);
  await line.scrollIntoViewIfNeeded();
  const sentBox = await line.boundingBox();
  assert.ok(sentBox && sentBox.y >= 0 && sentBox.y < 900, "the line is not in view before its entry leaves");
  await changeMeta(page, [PARK_B]); // the writer drops PARK_A while its line is in view
  await need(line, "the line left the page when its entry left the list");
  await need(line.locator(".ans.filed", { hasText: "Unparked" }), "the line shows no filled Unparked badge");
  const routedBox = await line.boundingBox();
  assert.ok(Math.abs(routedBox.height - sentBox.height) <= 0.5, "the line changed height from " + sentBox.height + " to " + routedBox.height);
});

test("a stored park draft whose entry is gone is pruned on load, and a later entry with the same id is not pre-staged", async (t) => {
  const storage = { "waiting.draft": JSON.stringify({ [parkKey(PARK_A)]: { act: "unpark" } }) };
  const page = await open(t, { items: [DECISION], meta: { writer: "triage", parked: [PARK_B] }, storage }); if (!page) return;
  await parkLoaded(page);
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("waiting.draft") || "{}"));
  assert.equal(parkKey(PARK_A) in stored, false, "the draft of a gone entry is still in waiting.draft: " + JSON.stringify(stored));
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is open on the draft of a gone entry");
  await changeMeta(page, [PARK_A, PARK_B]); // a later entry with the same id
  await need(parkLine(page, PARK_A), "the later entry with the same id is not on the page");
  assert.equal(await parkBtn(page, PARK_A, "unpark").getAttribute("aria-pressed"), "false", "a later entry with the same id is pre-staged");
  assert.equal(await page.locator("#send").isDisabled(), true, "a later entry with the same id is ready to send");
});

// ---------------------------------------------------------------- Park on every open card (page-park-any-item)

// A Park press sits in .alts on an open card: after None of these on a decision, after Mark done on a task. A press stages
// {act:"park"} and writes nothing. Send writes answers/<id> as {act, at, item, n, note}, with no choice, done or parked field.
const parkPress = (page, it) => page.locator(`#b-park-${it.id}`);
const pressedOf = (loc) => loc.getAttribute("aria-pressed");
const PARK_RECORD_KEYS = ["act", "at", "item", "n", "note"];
const altsOf = async (page, it) => (await card(page, it).locator(".alts > button").allTextContents()).map((s) => s.trim());
// The record Send wrote under the id, once the store holds it.
const recordOf = async (page, id) => { await page.waitForFunction((k) => !!window.__answers()[k], id); return (await answers(page))[id]; };

test("a Park press on a decision card stages with no write, and Send writes one park record with exactly five keys", async (t) => {
  const page = await open(t, { items: [DECISION] }); if (!page) return;
  await need(parkPress(page, DECISION), "the decision card has no Park button");
  assert.deepEqual(await altsOf(page, DECISION), ["None of these", "Park"], "Park is not in .alts after None of these");
  assert.match((await parkPress(page, DECISION).getAttribute("class")) || "", /\bparkbtn\b/, "the Park button has no parkbtn class");
  assert.equal(await pressedOf(parkPress(page, DECISION)), "false", "Park starts pressed");
  await parkPress(page, DECISION).click();
  assert.equal(await pressedOf(parkPress(page, DECISION)), "true", "a Park press did not press Park");
  assert.deepEqual(await page.evaluate(() => window.__log), [], "a Park press wrote before Send");
  assert.equal(await card(page, DECISION).locator(".ready").textContent(), "Ready to send: park.", "the ready line does not name the staged Park");
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer", "the Send bar does not count the staged Park");
  await send(page);
  const rec = await recordOf(page, DECISION.id);
  assert.deepEqual(Object.keys(rec).sort(), PARK_RECORD_KEYS, "the park record has the wrong fields: " + Object.keys(rec).join(", "));
  assert.deepEqual([rec.act, rec.item, rec.n, rec.note], ["park", DECISION.id, 27, ""], "the park record has the wrong values");
  assert.ok(!Number.isNaN(Date.parse(rec.at)), "at is not an ISO time");
  assert.deepEqual(await parkWrites(page), [["set", "answers", DECISION.id]], "Send wrote more than the one park record");
});

test("a Park press on a task card stages with no write, and Send writes one park record with no done field", async (t) => {
  const page = await open(t, { items: [TASK] }); if (!page) return;
  await need(parkPress(page, TASK), "the task card has no Park button");
  assert.deepEqual(await altsOf(page, TASK), ["Mark done", "Park"], "Park is not in .alts after Mark done");
  await parkPress(page, TASK).click();
  assert.equal(await pressedOf(parkPress(page, TASK)), "true", "a Park press did not press Park on the task");
  assert.deepEqual(await page.evaluate(() => window.__log), [], "a Park press wrote before Send");
  assert.equal(await card(page, TASK).locator(".ready").textContent(), "Ready to send: park.", "the ready line does not name the staged Park on the task");
  await send(page);
  const rec = await recordOf(page, TASK.id);
  assert.deepEqual(Object.keys(rec).sort(), PARK_RECORD_KEYS, "the task park record has the wrong fields: " + Object.keys(rec).join(", "));
  assert.deepEqual([rec.act, rec.item, rec.n, rec.note], ["park", TASK.id, 28, ""], "the task park record has the wrong values");
  assert.deepEqual(await parkWrites(page), [["set", "answers", TASK.id]], "Send wrote more than the one park record");
});

test("a staged Park with a typed note is ready, and Send writes the note in the park record", async (t) => {
  const page = await open(t, { items: [DECISION] }); if (!page) return;
  await need(parkPress(page, DECISION), "the decision card has no Park button");
  await parkPress(page, DECISION).click();
  await addNote(page, DECISION, "Wait for the mutation job.");
  assert.equal(await card(page, DECISION).locator(".ready").textContent(), "Ready to send: park.", "a typed note changes the staged Park's ready line");
  assert.equal(await page.locator("#send").isDisabled(), false, "Send is shut on a staged Park with a note");
  await send(page);
  const rec = await recordOf(page, DECISION.id);
  assert.deepEqual(Object.keys(rec).sort(), PARK_RECORD_KEYS, "the park record with a note has the wrong fields: " + Object.keys(rec).join(", "));
  assert.deepEqual([rec.act, rec.item, rec.n, rec.note], ["park", DECISION.id, 27, "Wait for the mutation job."], "the park record lost the typed note");
});

test("a Park press overrides a stood pick, and Send writes the park record with no choice", async (t) => {
  const it = mk("stand-park", 7, { stands: true });
  const page = await open(t, { items: [it] }); if (!page) return;
  assert.equal(await page.isChecked(`#o-${it.id}-a`), true, "the pick does not stand");
  await need(parkPress(page, it), "the card with a stood pick has no Park button");
  await parkPress(page, it).click();
  assert.equal(await pressedOf(parkPress(page, it)), "true", "a Park press did not press Park on a stood pick");
  await send(page);
  const rec = await recordOf(page, it.id);
  assert.ok(!("choice" in rec), "the stood pick went with the park record: " + JSON.stringify(rec));
  assert.deepEqual(Object.keys(rec).sort(), PARK_RECORD_KEYS, "the park record over a stood pick has the wrong fields: " + Object.keys(rec).join(", "));
  assert.deepEqual([rec.act, rec.item, rec.note], ["park", it.id, ""], "the park record over a stood pick has the wrong values");
});

test("Park toggles off on a second press, a pick, None of these or Mark done clears it, and Park clears each of them", async (t) => {
  const page = await open(t, { items: [DECISION, TASK] }); if (!page) return;
  const dp = () => parkPress(page, DECISION), tp = () => parkPress(page, TASK);
  const none = () => card(page, DECISION).getByRole("button", { name: "None of these" });
  const done = () => card(page, TASK).getByRole("button", { name: "Mark done" });
  await need(dp(), "the decision card has no Park button");
  await need(tp(), "the task card has no Park button");
  // A second press clears the staged Park: no write, Send shut, no ready line.
  await dp().click();
  await dp().click();
  assert.equal(await pressedOf(dp()), "false", "a second Park press did not clear Park");
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is open on a cleared Park");
  assert.equal(await card(page, DECISION).locator(".ready").textContent(), "", "the ready line still names a cleared Park");
  assert.deepEqual(await page.evaluate(() => window.__log), [], "toggling Park wrote");
  // A picked option clears Park, and Park clears the picked option.
  await choose(page, DECISION, "a");
  await dp().click();
  assert.equal(await pressedOf(dp()), "true", "Park did not press over a picked option");
  assert.equal(await page.isChecked(`#o-${DECISION.id}-a`), false, "Park did not clear the picked option");
  await choose(page, DECISION, "a");
  assert.equal(await pressedOf(dp()), "false", "a picked option did not clear Park");
  assert.equal(await page.isChecked(`#o-${DECISION.id}-a`), true, "a picked option was not picked after Park");
  // None of these clears Park, and Park clears None of these.
  await dp().click();
  await none().click();
  assert.equal(await pressedOf(dp()), "false", "None of these did not clear Park");
  assert.equal(await pressedOf(none()), "true", "None of these did not press");
  await dp().click();
  assert.equal(await pressedOf(dp()), "true", "Park did not press over None of these");
  assert.equal(await pressedOf(none()), "false", "Park did not clear None of these");
  // Mark done clears Park, and Park clears Mark done.
  await tp().click();
  await done().click();
  assert.equal(await pressedOf(tp()), "false", "Mark done did not clear Park");
  assert.equal(await pressedOf(done()), "true", "Mark done did not press");
  await tp().click();
  assert.equal(await pressedOf(tp()), "true", "Park did not press over Mark done");
  assert.equal(await pressedOf(done()), "false", "Park did not clear Mark done");
  assert.equal(await page.locator("#send").textContent(), "Send 2 answers", "the two staged Parks are not both counted");
  assert.deepEqual(await page.evaluate(() => window.__log), [], "the toggles wrote before Send");
});

test("Undo within 8 s after a Park Send deletes the park record and hands the Park back as a draft", async (t) => {
  const page = await open(t, { items: [DECISION] }); if (!page) return;
  await need(parkPress(page, DECISION), "the decision card has no Park button");
  await parkPress(page, DECISION).click();
  await send(page);
  await recordOf(page, DECISION.id);
  await page.locator("#undoBtn").waitFor({ timeout: 3000 }).catch(() => {});
  await need(page.locator("#undoBtn"), "Send shows no Undo after a Park");
  await page.locator("#undoBtn").click();
  await page.waitForFunction((k) => !(k in window.__answers()), DECISION.id);
  assert.deepEqual((await parkWrites(page)).filter((l) => l[0] === "delete"), [["delete", "answers", DECISION.id]], "Undo did not delete answers/<id> once");
  assert.equal(await pressedOf(parkPress(page, DECISION)), "true", "Undo did not hand the Park back as a draft");
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer", "the undone Park is not ready to send again");
});

test("a sent Park shows the receipt Parked. with Change, and Change then a pick sends a normal choice record", async (t) => {
  const page = await open(t, { items: [DECISION] }); if (!page) return;
  await need(parkPress(page, DECISION), "the decision card has no Park button");
  await parkPress(page, DECISION).click();
  await send(page);
  await recordOf(page, DECISION.id);
  const c = card(page, DECISION);
  await c.locator(".receipt").waitFor({ timeout: 3000 }).catch(() => {});
  await need(c.locator(".receipt"), "the sent Park card shows no receipt");
  assert.match(await c.locator(".receipt").textContent(), /Parked\./, "the receipt does not read Parked.");
  await need(c.getByRole("button", { name: "Change" }), "the sent Park receipt has no Change button");
  await c.getByRole("button", { name: "Change" }).click();
  await choose(page, DECISION, "a");
  await send(page);
  await page.waitForFunction((k) => !!window.__answers()[k] && window.__answers()[k].choice === "a", DECISION.id);
  const rec = (await answers(page))[DECISION.id];
  assert.deepEqual(Object.keys(rec).sort(), ["at", "choice", "item", "label", "n", "note"], "the changed answer is not a normal choice record: " + Object.keys(rec).join(", "));
  assert.equal(rec.choice, "a", "the changed answer lost the picked option");
});

test("a parked line keeps only Unpark and Drop, and no Park press is drawn on a .pk line", async (t) => {
  const page = await open(t, { items: [DECISION], meta: PARK_META }); if (!page) return;
  await parkLoaded(page);
  await need(parkLine(page, PARK_A), "the parked line is not a .pk in .parked .pk-list");
  assert.deepEqual(await parkLine(page, PARK_A).locator(".btn.pkb").evaluateAll((els) => els.map((e) => e.id)), ["pk-unpark-" + PARK_A.id, "pk-drop-" + PARK_A.id], "a parked line has acts other than Unpark and Drop");
  assert.equal(await parkLine(page, PARK_A).locator("[id^='b-park-'], .parkbtn").count(), 0, "a parked line draws a Park press");
});

// Controls: these pass on the code as it stands. A blocked card and a ruling card draw no live Park press.
test("control: a blocked decision card's Park press is off, a press on it stages nothing, and Send writes no record for it", async (t) => {
  const opt = (key) => ({ key, label: "L" + key, how: "h", gain: "g", lose: "l" });
  const rawItems = {
    "dup-keys": { ...DECISION, id: "dup-keys", n: 41, options: [opt("a"), opt("a")], pick: "a" },
    "good": { ...DECISION, id: "good", n: 43 },
  };
  const page = await open(t, { items: [], rawItems }); if (!page) return;
  const blocked = { ...DECISION, id: "dup-keys" }, good = { ...DECISION, id: "good" };
  await need(parkPress(page, blocked), "the blocked decision card has no Park button");
  assert.equal(await card(page, blocked).locator(".ready").textContent(), "This item cannot be sent.", "the card is not blocked");
  assert.equal(await parkOff(parkPress(page, blocked)), true, "the blocked card's Park press is on");
  await parkPress(page, blocked).click({ force: true }); // a real press on the disabled button: it changes nothing
  assert.equal(await pressedOf(parkPress(page, blocked)), "false", "a press on the blocked card's Park staged it");
  await need(parkPress(page, good), "the good decision card has no Park button");
  assert.equal(await parkOff(parkPress(page, good)), false, "the good card's Park press is off");
  await takePick(page, good);
  await send(page);
  await page.waitForFunction(() => !!window.__answers()["good"]);
  assert.equal("dup-keys" in await answers(page), false, "Send wrote a record for the blocked card");
  assert.deepEqual((await parkWrites(page)).filter((l) => l[2] === "dup-keys"), [], "a write named the blocked card");
});

test("control: an arbiter ruling card draws no Park press, and an open decision beside it keeps one", async (t) => {
  const page = await open(t, { items: [DECISION, ARBITER] }); if (!page) return;
  await need(card(page, ARBITER), "the closed arbiter item has no card");
  await need(parkPress(page, DECISION), "the open decision card has no Park button");
  assert.equal(await page.locator(`#b-park-${ARBITER.id}`).count(), 0, "the ruling card draws a Park press");
  assert.equal(await card(page, ARBITER).locator(".parkbtn").count(), 0, "the ruling card has a parkbtn");
});

// Item 10 (windows-live-checks) in the state the owner saw: the item is open, and its parked line and park answer still exist.
const W10 = mk("windows-live-checks", 10, { title: "Windows live checks" });
const W10_PARK = { id: W10.id, ref: "Step windows-live-checks, the Windows live checks", note: "Triage removes this line." };

test("an open item whose stale parked line and park answer remain shows its options and draws no parked line or Unpark sent badge", async (t) => {
  const saved = { [parkKey(W10_PARK)]: { parked: true, id: W10.id, act: "unpark", ref: W10_PARK.ref, note: W10_PARK.note, at: "2026-11-04T23:44:00.000Z" } };
  const page = await open(t, { items: [W10], meta: { writer: "triage", parked: [W10_PARK] }, answers: saved }); if (!page) return;
  await parkLoaded(page, parkKey(W10_PARK));
  await need(card(page, W10), "the open item has no card");
  assert.equal(await page.locator(`label[for="o-${W10.id}-a"]`).count(), 1, "the open item shows no option a");
  assert.equal(await page.locator(`label[for="o-${W10.id}-b"]`).count(), 1, "the open item shows no option b");
  assert.equal(await page.locator("#pk-line-" + W10.id).count(), 0, "the Parked by you block draws a line for the open item " + W10.id);
  assert.equal(await page.locator(".parked .ans", { hasText: "Unpark sent" }).count(), 0, "the Parked by you block shows an Unpark sent badge for the open item " + W10.id);
});

test("a parked line whose id is no open item still draws with its Unpark sent badge, beside an open item", async (t) => {
  const saved = { [parkKey(PARK_A)]: { parked: true, id: PARK_A.id, act: "unpark", ref: PARK_A.ref, note: PARK_A.note, at: "2026-11-01T17:42:00.000Z" } };
  const page = await open(t, { items: [W10], meta: { writer: "triage", parked: [PARK_A] }, answers: saved }); if (!page) return;
  await parkLoaded(page, parkKey(PARK_A));
  await need(card(page, W10), "the open item has no card");
  await need(parkLine(page, PARK_A), "the parked line with no open item is not drawn");
  await need(await parkBadge(page, PARK_A, "Unpark sent"), "the parked line with no open item shows no Unpark sent badge");
});

// ---------------------------------------------------------------- what the page says after a send: a wake, a paste in chat, a none key
// SKILL.md forbids a session to reply in a comment thread, so no line the page shows may send the owner there.
const NO_THREAD = /thread/i;
const WRITER = "home-triage-4";
const NOT_TOLD_TEXT = "No session was told. It waits for " + WRITER + "'s next wake or turn start.";
// An answer is read by each item's owner, not by the writer, so its unsent line names no writer.
const ANSWER_NOT_TOLD = "No session was told. Each owner reads its answer at its next wake or turn start.";
// The ask hint says "Telling Claude…" while the wake result is pending. A test waits for that result, not for a clock.
// The told words sit on the line under the buttons, so a test waits for that line's result, not for a clock.
const sentLineSettled = (page) => page.waitForFunction(() => { const l = document.querySelector("#asks .sline"); const s = l ? l.textContent : ""; return s.includes("Sent") && !s.includes("Telling"); }, null, { timeout: 3000 }).catch(() => {});
// Types an ask and sends it, then returns the line under the buttons once the wake result has landed. "" when the page has no such line.
async function sentLine(page, text) {
  await mustHave(page, "#askText", "Ask box");
  await page.fill("#askText", text);
  await mustHave(page, "#askSend", "Send ask button");
  await page.click("#askSend");
  await sentLineSettled(page);
  return page.evaluate(() => { const l = document.querySelector("#asks .sline"); return l ? l.textContent.trim() : ""; });
}

test("an ask sent while a session can take a comment says a wake was sent, never that Claude was told", async (t) => {
  const page = await open(t, { meta: { writer: WRITER }, comments: { can: "available" } }); if (!page) return;
  const line = await sentLine(page, ASK_TEXT);
  assert.match(line, /A wake was sent\./, "the line under the buttons does not say a wake was sent: " + JSON.stringify(line));
  assert.doesNotMatch(line, /Claude was told/, "the line under the buttons still says Claude was told: " + JSON.stringify(line));
});

test("an ask whose stored thread rejects upstream_error says a wake was sent, after one anchored retry", async (t) => {
  const page = await open(t, { meta: { writer: WRITER }, comments: { can: "available", threadFail: { "t-old": "upstream_error" } }, storage: { "waiting.thread": "t-old" } }); if (!page) return;
  const line = await sentLine(page, ASK_TEXT);
  const s = await sent(page);
  assert.equal(s[0].threadId, "t-old", "the ask did not first go to the stored thread");
  assert.match(line, /A wake was sent\./, "the line under the buttons does not say a wake was sent after the anchored retry: " + JSON.stringify(line));
  assert.equal(s.length, 2, "the ask did not get one anchored retry: " + s.length + " send(s)");
});

test("an ask sent with no session to tell says what happens next, and names no thread", async (t) => {
  const page = await open(t, { meta: { writer: WRITER }, comments: { can: "no_session" } }); if (!page) return;
  const line = await sentLine(page, ASK_TEXT);
  assert.ok(line.includes(NOT_TOLD_TEXT), "the line under the buttons does not say what happens next: " + JSON.stringify(line));
  assert.doesNotMatch(line, NO_THREAD, "the line under the buttons names a thread: " + JSON.stringify(line));
});

test("an answer sent with no session to tell says each owner reads it at its next wake, and names no thread or writer", async (t) => {
  const page = await open(t, { meta: { writer: WRITER }, comments: { can: "no_session" } }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await told(page, "No session was told");
  const status = (await page.textContent("#sentStatus")).trim();
  assert.ok(status.includes(ANSWER_NOT_TOLD), "the sent panel does not say each owner reads its answer at its next wake: " + JSON.stringify(status));
  assert.doesNotMatch(status, NO_THREAD, "the sent panel names a thread: " + JSON.stringify(status));
  assert.ok(!status.includes(WRITER), "the sent panel names the writer, but each owner reads its own answer: " + JSON.stringify(status));
});

test("a failed Send tells the owner to paste the copied answers in chat, and names no thread", async (t) => {
  const page = await open(t, { failSet: true }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#barStatus", { hasText: "Not saved (denied)" }).waitFor();
  const bar = (await page.textContent("#barStatus")).trim();
  assert.ok(bar.includes("Copy the answers and paste them in chat."), "the failed-save note does not say to paste the copied answers in chat: " + JSON.stringify(bar));
  assert.doesNotMatch(bar, NO_THREAD, "the failed-save note names a thread: " + JSON.stringify(bar));
});

// One decision whose options are given, with a pick on its first key that is not none. Returns its warning, or null with no browser.
const optWith = (key, label) => ({ key, label, how: "h", gain: "g", lose: "l" });
const optNoLabel = (key) => ({ key, how: "h", gain: "g", lose: "l" });
async function noneKeyWarning(t, options) {
  const pick = options.find((o) => o.key !== "none").key;
  const page = await open(t, { items: [], rawItems: { "none-key": { ...DECISION, id: "none-key", n: 33, options, pick } } }); if (!page) return null;
  return (await warn(page, "none-key").textContent()).trim();
}
// The warning names the option by its letter and label, then gives the reason. The head is the part before the reason.
function assertNoneWarning(text, head) {
  assert.ok(text.includes(head + ' The page keeps that key for "None of these", so this decision cannot be answered.'), "the none-key warning does not read " + JSON.stringify(head) + ": " + JSON.stringify(text));
  assert.doesNotMatch(text, /undefined/, "the none-key warning prints undefined: " + JSON.stringify(text));
}

test("a none key warning names its option by letter and label", async (t) => {
  const text = await noneKeyWarning(t, [optWith("none", "Keep the old way"), optWith("b", "Blue")]); if (text === null) return;
  assertNoneWarning(text, 'Option A, "Keep the old way", has the key none.');
});

test("a none key label over 28 characters is cut with an ellipsis in the warning", async (t) => {
  const text = await noneKeyWarning(t, [optWith("none", "Keep the existing layout for every reader"), optWith("b", "Blue")]); if (text === null) return;
  assertNoneWarning(text, 'Option A, "Keep the existing layout fo…", has the key none.');
  assert.doesNotMatch(text, /for every reader/, "the none-key warning shows the whole label: " + JSON.stringify(text));
});

test("a none key with no label names its letter only, and prints no undefined", async (t) => {
  const text = await noneKeyWarning(t, [optWith("a", "Red"), optNoLabel("none")]); if (text === null) return;
  assertNoneWarning(text, "Option B has the key none.");
});

test("a none key with a blank label names its letter only, and prints no empty quotes", async (t) => {
  const text = await noneKeyWarning(t, [optWith("a", "Red"), optWith("none", "   ")]); if (text === null) return;
  assertNoneWarning(text, "Option B has the key none.");
  assert.doesNotMatch(text, /""/, "the none-key warning prints empty quotes: " + JSON.stringify(text));
});

test("the copy confirmation names no thread", async (t) => {
  const page = await open(t, { failSet: true }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#barStatus", { hasText: "Not saved (denied)" }).waitFor();
  await stubClipboard(page, false);
  await page.click("#copy");
  await page.locator("#barStatus", { hasText: "Copied" }).waitFor();
  const bar = (await page.textContent("#barStatus")).trim();
  assert.doesNotMatch(bar, NO_THREAD, "the copy confirmation names a thread: " + JSON.stringify(bar));
});

test("a parked line with no id says the writer has not prepared it, and names no thread", async (t) => {
  const page = await open(t, { items: [DECISION], meta: { writer: "triage", parked: [PARK_NOID] } }); if (!page) return;
  await parkLoaded(page);
  await need(parkLine(page, PARK_NOID), "the line with no id is not a .pk in .parked .pk-list");
  const why = (await parkLine(page, PARK_NOID).locator(".pk-why").first().textContent()).trim();
  assert.match(why, /has not prepared this line yet/, "the no-id line does not say the writer has not prepared it: " + JSON.stringify(why));
  assert.doesNotMatch(why, NO_THREAD, "the no-id line names a thread: " + JSON.stringify(why));
});

// ---------------------------------------------------------------- an option with no label: the ready line names its letter
// The page never prints a raw key or "undefined". An option with no title is named by its letter, as its chip is.
test("a pick of an option with no label names its letter on the ready line", async (t) => {
  const it = mk("no-label-pick", 41, { options: [optWith("a", "Red"), optNoLabel("b")], pick: "a" });
  const page = await open(t, { items: [it] }); if (!page) return;
  await page.locator('label[for="o-no-label-pick-b"]').click();
  const ready = (await card(page, it).locator(".ready").textContent()).trim();
  assert.equal(ready, "Ready to send: B, your choice.", "the ready line does not name the option by its letter: " + JSON.stringify(ready));
});

test("a pick of an option with a blank label names its letter on the ready line", async (t) => {
  const it = mk("blank-label-pick", 42, { options: [optWith("a", "Red"), optWith("b", "   ")], pick: "a" });
  const page = await open(t, { items: [it] }); if (!page) return;
  await page.locator('label[for="o-blank-label-pick-b"]').click();
  const ready = (await card(page, it).locator(".ready").textContent()).trim();
  assert.equal(ready, "Ready to send: B, your choice.", "the ready line does not name the option by its letter: " + JSON.stringify(ready));
});

test("a two-pick with an option that has no label names that option by its letter on the ready line", async (t) => {
  const it = mk("no-label-two", 43, { multi: true, options: [optWith("a", "Red"), optNoLabel("b")], pick: ["a", "b"] });
  const page = await open(t, { items: [it] }); if (!page) return;
  await needBoxes(page, it, 2);
  await page.locator('label[for="o-no-label-two-a"]').click();
  await page.locator('label[for="o-no-label-two-b"]').click();
  const ready = (await card(page, it).locator(".ready").textContent()).trim();
  assert.equal(ready, "Ready to send: Red and B, your choice.", "the two-pick ready line does not name the unlabelled option by its letter: " + JSON.stringify(ready));
});

// ---------------------------------------------------------------- pins: a failed withdraw and a view with no store say "in chat"
// Pins, not red cases: these lines are green on the current page. They hold the wording the page says now, so a
// thread line coming back fails here.
test("a withdraw the store refuses says to paste the answer in chat, and names no thread", async (t) => {
  const page = await open(t, { answers: SAVED_A, failDelete: true }); if (!page) return;
  const c = card(page, DECISION);
  await c.getByRole("button", { name: "Change" }).click();
  await choose(page, DECISION, "a");
  await send(page);
  const note = c.getByText("Not withdrawn (denied)", { exact: false }).first();
  await note.waitFor();
  const text = (await note.textContent()).trim();
  assert.match(text, /in chat/, "the withdraw note does not say to paste in chat: " + JSON.stringify(text));
  assert.doesNotMatch(text, NO_THREAD, "the withdraw note names a thread: " + JSON.stringify(text));
});

test("a view that cannot reach the store says to paste its answers in chat, and names no thread", async (t) => {
  const page = await open(t, { items: [], noStore: true }); if (!page) return;
  const empty = page.locator("#list .empty").first();
  await empty.waitFor();
  const text = (await empty.textContent()).trim();
  assert.match(text, /in chat/, "the no-store empty state does not say to paste in chat: " + JSON.stringify(text));
  assert.doesNotMatch(text, NO_THREAD, "the no-store empty state names a thread: " + JSON.stringify(text));
});

// ---------------------------------------------------------------- the bars and the words: stalled and paused (lane nfp-stalled-kind-color)
// The Status tab's bars draw a stalled step and a paused step as their own cells, in the roadmap's order. barsStalled is the stalled
// fixture with 24 to-do steps: a full phase of 30 steps, and a to-do cell to compare with. c1, a2, a5 stalled; a3 paused; a4, d6 in progress.
const barsStalled = () => ({ ...stalledFixture(), ...stepsOf(Array.from({ length: 24 }, (_, i) => ["t" + (i + 7), "cleanup", i + 7, "todo"])) });
const barsPage = () => withStalled(phasePage(barsStalled()), STALLED);
const BARS_W = [["the Now card's bar", "#svNow .segbar"], ["the rail's cleanup bar", '#svRail button[data-phase="cleanup"] .segbar'], ["the phase head's bar", "#svPhases .ph-head .segbar"]];
const W_ORDER = ["act", "act", "stl", "stl", "stl", "pzd", ...Array(24).fill("")];
const wCellKinds = (page, scope) => page.locator(`${scope} > i`).evaluateAll((els) => els.map((e) => e.className));
test("the bars draw a stalled and a paused step as their own cells, in the order done, in progress, stalled, paused, to do", async (t) => {
  const page = await open(t, { pageHtml: barsPage() }); if (!page) return;
  await openStatus(page);
  for (const [name, scope] of BARS_W) {
    assert.equal(await page.locator(scope).count(), 1, `${name} is missing (${scope})`);
    assert.deepEqual(await wCellKinds(page, scope), W_ORDER, `${name} does not draw a stalled or paused step as its own cell, in order`);
  }
});
// barsBlocked: a done step and a blocked step in place of two to-do steps, so all six kinds show in one phase of 30 cells.
const barsBlocked = () => ({ ...barsStalled(), ...stepsOf([["t29", "cleanup", 29, "done"], ["t30", "cleanup", 30, "blocked"]]) });
const barsBlockedPage = () => withStalled(phasePage(barsBlocked()), STALLED);
const W_ORDER_BLK = ["done", "act", "act", "stl", "stl", "stl", "pzd", "blk", ...Array(22).fill("")];
test("the bars draw a blocked step after a stalled and a paused one, in the order done, in progress, stalled, paused, blocked, to do", async (t) => {
  const page = await open(t, { pageHtml: barsBlockedPage() }); if (!page) return;
  await openStatus(page);
  for (const [name, scope] of BARS_W) {
    assert.equal(await page.locator(scope).count(), 1, `${name} is missing (${scope})`);
    assert.deepEqual(await wCellKinds(page, scope), W_ORDER_BLK, `${name} does not draw the blocked step after the paused one, in order`);
  }
});
test("a stalled cell and a paused cell look different from a to-do cell in each bar", async (t) => {
  const page = await open(t, { pageHtml: barsPage() }); if (!page) return;
  await openStatus(page);
  const look = (loc) => loc.evaluate((el) => { const s = getComputedStyle(el); return [s.backgroundImage, s.backgroundColor, s.boxShadow].join(" | "); });
  for (const [name, scope] of BARS_W) {
    const todo = page.locator(`${scope} > i:not([class])`);
    const plainCount = await todo.count();
    assert.equal(plainCount, 24, `${name} draws ${plainCount} to-do cells, not 24: a stalled or paused step is drawn as to do`);
    const plain = await look(todo.first());
    assert.equal(await page.locator(`${scope} > i.stl`).count(), 3, `${name} draws no stalled cell (i.stl) for the three stalled steps`);
    assert.equal(await page.locator(`${scope} > i.pzd`).count(), 1, `${name} draws no paused cell (i.pzd)`);
    assert.notEqual(await look(page.locator(`${scope} > i.stl`).first()), plain, `${name}: the stalled cell looks like a to-do cell`);
    assert.notEqual(await look(page.locator(`${scope} > i.pzd`)), plain, `${name}: the paused cell looks like a to-do cell`);
  }
});
test("control: a phase with nothing stalled or paused draws no stalled or paused cell in any bar", async (t) => {
  const steps = stepsOf([["d6", "cleanup", 1, "doing"], ["c1", "cleanup", 2, "todo"]]);
  const page = await open(t, { pageHtml: withStalled(phasePage(steps), { why: "", steps: [], paused: [], badPause: [], items: [], ...NO_ITEMS }) }); if (!page) return;
  await openStatus(page);
  for (const [name, scope] of BARS_W) {
    assert.equal(await page.locator(scope).count(), 1, `${name} is missing (${scope})`);
    assert.deepEqual(await wCellKinds(page, scope), ["act", ""], `${name} draws a stalled or paused cell with none stalled or paused`);
  }
});
test("the rail's cleanup button names its stalled and paused steps in its label", async (t) => {
  const page = await open(t, { pageHtml: barsPage() }); if (!page) return;
  await openStatus(page);
  const btn = page.locator('#svRail button[data-phase="cleanup"]');
  assert.equal(await btn.count(), 1, "the rail has no cleanup button");
  assert.match((await btn.getAttribute("aria-label")) || "", /3 stalled, 1 paused/, "the rail's cleanup label does not name the stalled and paused steps");
});
test("the phase head's text names its stalled and paused steps", async (t) => {
  const page = await open(t, { pageHtml: barsPage() }); if (!page) return;
  await openStatus(page);
  const prog = page.locator("#svPhases .ph-head .prog");
  assert.equal(await prog.count(), 1, "the phase head has no progress part (.prog)");
  const text = (await prog.locator(".sr").allTextContents()).join(" ").replace(/\s+/g, " ");
  assert.match(text, /3 stalled, 1 paused/, "the phase head's text does not name the stalled and paused steps: " + text);
});
// The rail's label and the phase head's text name a blocked step in the form of the stalled and paused words, when the bar draws one.
test("the rail's cleanup button names its blocked step in its label, as its bar draws it", async (t) => {
  const page = await open(t, { pageHtml: barsBlockedPage() }); if (!page) return;
  await openStatus(page);
  assert.equal(await page.locator('#svRail button[data-phase="cleanup"] .segbar > i.blk').count(), 1, "the rail's cleanup bar draws no blocked cell (i.blk)");
  const label = (await page.locator('#svRail button[data-phase="cleanup"]').getAttribute("aria-label")) || "";
  assert.match(label, /, 1 blocked\b/, `the rail's cleanup label does not name the blocked step: "${label}"`);
});
test("the phase head's text names its blocked step, as its bar draws it", async (t) => {
  const page = await open(t, { pageHtml: barsBlockedPage() }); if (!page) return;
  await openStatus(page);
  assert.equal(await page.locator("#svPhases .ph-head .segbar > i.blk").count(), 1, "the phase head's bar draws no blocked cell (i.blk)");
  const text = (await page.locator("#svPhases .ph-head .prog .sr").allTextContents()).join(" ").replace(/\s+/g, " ");
  assert.match(text, /, 1 blocked\b/, `the phase head's text does not name the blocked step: "${text}"`);
});
test("control: the rail's cleanup label and the phase head's text name no blocked step when none is drawn", async (t) => {
  const page = await open(t, { pageHtml: barsPage() }); if (!page) return;
  await openStatus(page);
  assert.equal(await page.locator("#svPhases .ph-head .segbar > i.blk").count(), 0, "the phase head's bar draws a blocked cell with no blocked step");
  const label = (await page.locator('#svRail button[data-phase="cleanup"]').getAttribute("aria-label")) || "";
  const text = (await page.locator("#svPhases .ph-head .prog .sr").allTextContents()).join(" ");
  assert.doesNotMatch(label, /blocked/, `the rail's cleanup label names a blocked step that is not there: "${label}"`);
  assert.doesNotMatch(text, /blocked/, `the phase head's text names a blocked step that is not there: "${text}"`);
});
// The rail's label and the phase head's text name the in-progress steps too, as their bars draw them: barsPage has two (a4, d6).
test("the rail's cleanup button names its in-progress steps in its label, as its bar draws them", async (t) => {
  const page = await open(t, { pageHtml: barsPage() }); if (!page) return;
  await openStatus(page);
  assert.equal(await page.locator('#svRail button[data-phase="cleanup"] .segbar > i.act').count(), 2, "the rail's cleanup bar does not draw the two in-progress steps (i.act)");
  const label = (await page.locator('#svRail button[data-phase="cleanup"]').getAttribute("aria-label")) || "";
  assert.match(label, /\b2 in progress\b/, `the rail's cleanup label does not name the in-progress steps: "${label}"`);
});
test("the phase head's text names its in-progress steps, as its bar draws them", async (t) => {
  const page = await open(t, { pageHtml: barsPage() }); if (!page) return;
  await openStatus(page);
  assert.equal(await page.locator("#svPhases .ph-head .segbar > i.act").count(), 2, "the phase head's bar does not draw the two in-progress steps (i.act)");
  const text = (await page.locator("#svPhases .ph-head .prog .sr").allTextContents()).join(" ").replace(/\s+/g, " ");
  assert.match(text, /\b2 in progress\b/, `the phase head's text does not name the in-progress steps: "${text}"`);
});
// Control: a phase with no in-progress step names none, in the rail's label or the phase head's text.
test("control: the rail's cleanup label and the phase head's text name no in-progress step when none is drawn", async (t) => {
  const page = await open(t, { pageHtml: withStalled(phasePage(blockedSteps()), noStalled) }); if (!page) return;
  await openStatus(page);
  assert.equal(await page.locator("#svPhases .ph-head .segbar > i.act").count(), 0, "the phase head's bar draws an in-progress cell with no in-progress step");
  const label = (await page.locator('#svRail button[data-phase="cleanup"]').getAttribute("aria-label")) || "";
  const text = (await page.locator("#svPhases .ph-head .prog .sr").allTextContents()).join(" ");
  assert.doesNotMatch(label, /in progress/, `the rail's cleanup label names an in-progress step that is not there: "${label}"`);
  assert.doesNotMatch(text, /in progress/, `the phase head's text names an in-progress step that is not there: "${text}"`);
});
// The Now card's bar counts a blocked step as blocked, as the rail's bar and the phase head's bar do.
const blockedSteps = () => stepsOf([["c1", "cleanup", 1, "todo"], ["d1", "cleanup", 2, "done"], ["b2", "cleanup", 3, "blocked"], ["t3", "cleanup", 4, "todo"]]);
const noStalled = { why: "", steps: [], paused: [], badPause: [], items: [], ...NO_ITEMS };
test("the Now card's bar draws a blocked step as blocked, not as to do", async (t) => {
  const page = await open(t, { pageHtml: withStalled(phasePage(blockedSteps()), noStalled) }); if (!page) return;
  await openStatus(page);
  assert.equal(await page.locator("#svNow .segbar").count(), 1, "the Now card has no phase bar (#svNow .segbar)");
  assert.equal(await page.locator("#svNow .segbar > i.blk").count(), 1, "the Now card's bar draws the blocked step as to do: no blocked cell (i.blk)");
});
test("control: the rail's cleanup bar draws a blocked step as blocked", async (t) => {
  const page = await open(t, { pageHtml: withStalled(phasePage(blockedSteps()), noStalled) }); if (!page) return;
  await openStatus(page);
  assert.equal(await page.locator('#svRail button[data-phase="cleanup"] .segbar').count(), 1, "the rail has no cleanup bar");
  assert.equal(await page.locator('#svRail button[data-phase="cleanup"] .segbar > i.blk').count(), 1, "the rail's cleanup bar does not draw the blocked step as blocked");
});
// The Now card's count line (renderNow, line "N of M done, K in progress") names the stalled and paused steps, as notes item 3 says.
test("the Now card's count line names the stalled and paused steps", async (t) => {
  const page = await open(t, { pageHtml: barsPage() }); if (!page) return;
  await openStatus(page);
  // The first .lead of the Now card is the count line; the second is "Whole plan".
  const lead = page.locator("#svNow > div:first-child > .lead");
  assert.ok((await lead.count()) > 0, "the Now card has no count line (#svNow > div:first-child > .lead)");
  const text = (await lead.first().textContent()).replace(/\s+/g, " ");
  assert.match(text, /3 stalled, 1 paused/, "the Now card's count line does not name the stalled and paused steps: " + text);
});
test("the Now card's count line names the blocked step when the Now card's bar draws one", async (t) => {
  const page = await open(t, { pageHtml: barsBlockedPage() }); if (!page) return;
  await openStatus(page);
  assert.equal(await page.locator("#svNow .segbar > i.blk").count(), 1, "the Now card's bar draws no blocked cell (i.blk)");
  const lead = page.locator("#svNow > div:first-child > .lead");
  assert.ok((await lead.count()) > 0, "the Now card has no count line (#svNow > div:first-child > .lead)");
  const text = (await lead.first().textContent()).replace(/\s+/g, " ");
  assert.match(text, /, 1 blocked/, "the Now card's count line does not name the blocked step: " + text);
});

// ---------------------------------------------------------------- a to-do or done step listed paused or stalled (lane nfp-stalled-kind-color)
// The band on the Status tab takes a listed step into its count and its rows only when it is doing, as the roadmap's band does (its
// cases are in skills/roadmap/tests/page.test.mjs). Each case lists doing step a beside step x, so the count is 1 when x is left out
// and 2 when it is not. This file keeps its own read shape, as its countLinesW copy notes; the roadmap file has the same shape.
const bandRead = (kind, ids) => kind === "stalled"
  ? { why: "", steps: ids.map((id) => ({ id, fix: "todo" })), paused: [], badPause: [], items: [], ...NO_ITEMS }
  : { why: "", steps: [], paused: ids, badPause: [], items: [], ...NO_ITEMS };
const BAND_WORD = { stalled: "Stalled", paused: "Paused" };
for (const kind of ["stalled", "paused"]) for (const status of ["todo", "done"]) {
  test(`the band counts a ${status} step listed ${kind} in neither its count nor a row, and still counts the doing step beside it`, async (t) => {
    const steps = stepsOf([["c1", "cleanup", 1, "todo"], ["a", "cleanup", 2, "doing"], ["x", "cleanup", 3, status]]);
    const page = await open(t, { pageHtml: withStalled(phasePage(steps), bandRead(kind, ["a", "x"])) }); if (!page) return;
    await openStatus(page);
    for (const id of ["a", "x"]) assert.equal(await page.locator(`#s-${id}`).count(), 1, `step ${id} has no row in the Status list`);
    assert.equal(await band(page).locator('button[data-go="a"]').count(), 1, `the band draws no row for doing step a listed ${kind}`);
    const text = await bandText(page);
    assert.match(text, new RegExp(`${BAND_WORD[kind]}:\\s*1(?!\\d)`), `the band counts the ${status} step x listed ${kind} as well as doing step a: ${text}`);
    assert.equal(await band(page).locator('button[data-go="x"]').count(), 0, `the band draws a row for the ${status} step x listed ${kind}`);
  });
}
// Control: a listed id with no step in the plan keeps its count and its row, named Untitled step, as before the band read steps.
for (const kind of ["stalled", "paused"]) {
  test(`control: a ${kind} id with no step in the plan keeps its count and its row, named Untitled step`, async (t) => {
    const steps = stepsOf([["c1", "cleanup", 1, "todo"], ["a", "cleanup", 2, "doing"]]);
    const page = await open(t, { pageHtml: withStalled(phasePage(steps), bandRead(kind, ["a", "zz"])) }); if (!page) return;
    await openStatus(page);
    assert.equal(await page.locator("#s-a").count(), 1, "step a has no row in the Status list");
    const text = await bandText(page);
    assert.match(text, new RegExp(`${BAND_WORD[kind]}:\\s*2(?!\\d)`), `the band does not count the listed id zz with no step as ${BAND_WORD[kind]}: ${text}`);
    assert.equal(await band(page).locator('button[data-go="zz"]').count(), 1, "the band draws no row for the listed id zz with no step");
    assert.match(await band(page).locator('button[data-go="zz"]').textContent(), /Untitled step/, "the row of the listed id zz with no step is not named Untitled step");
  });
}

// The edge, as on the roadmap: a to-do step listed paused (t1) and a done step listed stalled (d1), beside to-do c1 and doing a2. Each
// place reads the step's own status. EDGE_W_FULL is the same at full size: 30 steps, so each bar draws every cell.
const EDGE_W = () => {
  const s = stepsOf([["c1", "cleanup", 1, "todo"], ["t1", "cleanup", 2, "todo"], ["d1", "cleanup", 3, "done"], ["a2", "cleanup", 4, "doing"]]);
  s.t1.paused = { why: "Waits for a month of CI numbers.", decides: "owner", at: "2026-11-05T16:20:00-06:00", by: "triage" };
  return s;
};
const EDGE_W_FULL = () => ({ ...EDGE_W(), ...stepsOf(Array.from({ length: 26 }, (_, i) => ["t" + (i + 5), "cleanup", i + 5, "todo"])) });
const EDGE_W_READ = { why: "", steps: [{ id: "d1", fix: "todo" }], paused: ["t1"], badPause: [], items: [], ...NO_ITEMS };
const edgePage = (steps = EDGE_W()) => withStalled(phasePage(steps), EDGE_W_READ);
test("the row labels of a to-do step listed paused and a done step listed stalled read To do and Done", async (t) => {
  const page = await open(t, { pageHtml: edgePage() }); if (!page) return;
  await openStatus(page);
  for (const [id, word] of [["t1", "To do"], ["d1", "Done"]]) {
    assert.equal(await page.locator(`#s-${id}`).count(), 1, `step ${id} has no row in the Status list`);
    const label = (await page.locator(`#s-${id} .rrow`).getAttribute("aria-label")) || "";
    assert.ok(label.startsWith(`${id}, ${word}:`), `step ${id} is ${word} and listed, but its row label reads "${label}"`);
    assert.equal(await page.locator(`#s-${id} .tag.stl, #s-${id} .tag.pzd`).count(), 0, `step ${id} is ${word} and listed, but its row carries a Stalled or Paused tag`);
  }
});
test("the where-you-are line counts neither the to-do step listed paused nor the done step listed stalled", async (t) => {
  const page = await open(t, { pageHtml: edgePage() }); if (!page) return;
  await openStatus(page);
  const where = await whereLine(page);
  assert.match(where, /1 in progress/, "the where-you-are line does not count the doing step a2: " + where);
  assert.doesNotMatch(where, /stalled/, "the where-you-are line counts a done step as stalled: " + where);
  assert.doesNotMatch(where, /paused/, "the where-you-are line counts a to-do step as paused: " + where);
});
test("the bars draw a to-do step listed paused and a done step listed stalled as to-do and done cells, at full size", async (t) => {
  const page = await open(t, { pageHtml: edgePage(EDGE_W_FULL()) }); if (!page) return;
  await openStatus(page);
  for (const [name, scope] of BARS_W) {
    assert.equal(await page.locator(scope).count(), 1, `${name} is missing (${scope})`);
    assert.deepEqual(await wCellKinds(page, scope), ["done", "act", ...Array(28).fill("")], `${name} draws a listed step as a stalled or paused cell`);
  }
});
const feedRowMark = (page, id) => page.locator("#svSide ul.feed li", { has: page.locator(`button[data-go="${id}"]`) }).locator('[role="img"]');
const logRowMark = (page, id) => page.locator("#svDays .ev", { has: page.locator(`button[data-go="${id}"]`) }).locator('[role="img"]');
test("Latest changes and the Changes log read the to-do step listed paused and the done step listed stalled as their own status", async (t) => {
  const page = await open(t, { pageHtml: edgePage() }); if (!page) return;
  await openStatus(page);
  for (const [id, word] of [["t1", "To do"], ["d1", "Done"]]) {
    for (const [where, mark] of [["Latest changes", feedRowMark(page, id)], ["the Changes log", logRowMark(page, id)]]) {
      assert.equal(await mark.count(), 1, `step ${id} has no state mark in ${where}`);
      const label = await mark.getAttribute("aria-label");
      assert.equal(label, word, `step ${id} is ${word} and listed, but its row in ${where} reads ${label}`);
    }
  }
});

// The Now card's count line: a group (", 1 stalled") is never split across lines. Lines are read from the word boxes: a line that starts
// with a group word or a separator, or ends on a bare number, has broken a group. The helper is a copy of the roadmap test's
// (skills/roadmap/tests/page.test.mjs): the two pages' test files keep their own helpers.
const GROUP_WORDS_W = new Set(["in", "progress", "done", "stalled", "paused", "blocked"]);
const bareOf = (w) => w.replace(/[.,·]/g, "");
async function countLinesW(page, sel) {
  return page.evaluate((s) => {
    const root = document.querySelector(s);
    if (!root) return null;
    const words = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const re = /\S+/g;
      for (let m = re.exec(node.data); m; m = re.exec(node.data)) {
        const range = document.createRange();
        range.setStart(node, m.index);
        range.setEnd(node, m.index + m[0].length);
        const r = range.getClientRects()[0];
        if (r) words.push({ w: m[0], y: (r.top + r.bottom) / 2 });
      }
    }
    const lines = [];
    for (const { w, y } of words) {
      const last = lines[lines.length - 1];
      if (last && Math.abs(last.y - y) < 4) last.words.push(w); else lines.push({ y, words: [w] });
    }
    return lines.map((l) => l.words);
  }, sel);
}
// A phone width wraps the line, so the break assert below keeps the group check from passing on a line that never wraps. 360 is where
// the nowrap rule decides: without it "1" ends one line and "paused" starts the next. 1280 does not wrap, so it has no break assert.
for (const width of [360, 390, 1280]) test(`the Now card's count line keeps each group whole at ${width} wide, with blocked, stalled and paused steps`, async (t) => {
  const page = await open(t, { pageHtml: barsBlockedPage(), viewport: { width, height: 900 } }); if (!page) return;
  await openStatus(page);
  const lines = await countLinesW(page, "#svNow > div:first-child > .lead");
  assert.ok(lines && lines.length, "the Now card has no count line (#svNow > div:first-child > .lead)");
  const text = lines.map((l) => l.join(" ")).join(" | ");
  if (width < 1280) assert.ok(lines.length >= 2, `at ${width} wide the count line does not wrap, so the group check proves nothing: ${text}`);
  const starts = lines.find((l) => bareOf(l[0]) === "" || GROUP_WORDS_W.has(bareOf(l[0])));
  assert.equal(starts, undefined, `at ${width} wide a line of the count line starts inside a group: ${text}`);
  const ends = lines.find((l) => /^\d+$/.test(bareOf(l[l.length - 1])));
  assert.equal(ends, undefined, `at ${width} wide a line of the count line ends on a bare number: ${text}`);
});
// ---------------------------------------------------------------- touch sizes and the dashed edge

// The touch rules read pointer: coarse. A touch page must match it and a fine page must not, or a size check proves nothing.
const coarse = (page) => page.evaluate(() => matchMedia("(pointer: coarse)").matches);
const railRows = (page) => page.locator("#rail a.ov-head");
const railChips = (page) => page.locator("#rail .nchip");
const sizes = (loc, key) => loc.evaluateAll((els, k) => els.map((e) => [e.getAttribute(k) || e.id, e.getBoundingClientRect().height]), key);
// A computed colour as hex. Read: rgb(r, g, b) and color(srgb r g b), both opaque. Any other form is null: the check reads no colour it cannot parse.
const hexOf = (css) => {
  const s = /^color\(srgb ([\d.]+) ([\d.]+) ([\d.]+)\)$/.exec(css), r = /^rgb\((\d+), (\d+), (\d+)\)$/.exec(css);
  const v = s ? s.slice(1).map((x) => Math.round(+x * 255)) : r ? r.slice(1).map(Number) : null;
  return v ? "#" + v.map((x) => x.toString(16).padStart(2, "0")).join("") : null;
};
// The WCAG ratio of two hex colours, through the CONTRAST helper.
const ratioOf = (page, fg, bg) => page.evaluate(`(() => {${CONTRAST} return R(${JSON.stringify(fg)}, ${JSON.stringify(bg)}); })()`);
// The dashed buttons of a card, each read unpressed: a pressed one draws its solid edge, which is not this check.
const dashEdges = async (page, buttons) => {
  const edges = [];
  for (const [label, pre, it] of buttons) {
    const btn = page.locator(`#${pre}-${it.id}`);
    await need(btn, `No. ${it.n} has no ${label} button`);
    assert.notEqual(await btn.getAttribute("aria-pressed"), "true", `${label} on No. ${it.n} is pressed, so it does not draw the unpressed edge`);
    edges.push({
      what: `${label} on No. ${it.n}`,
      edge: await btn.evaluate((el) => getComputedStyle(el).borderTopColor),
      card: await card(page, it).evaluate((el) => getComputedStyle(el).backgroundColor),
      page: await page.evaluate(() => getComputedStyle(document.body).backgroundColor),
    });
  }
  return edges;
};
// One failure line per edge and ground that reads under 3:1, or that the check cannot read.
const edgeBad = async (page, edges, scheme) => {
  const bad = [];
  for (const e of edges) for (const [where, bg] of [["card", e.card], ["page", e.page]]) {
    const fg = hexOf(e.edge), back = hexOf(bg);
    if (!fg || !back) { bad.push(`${e.what} has a colour the check cannot read on the ${where} in the ${scheme} scheme: edge ${e.edge}, ground ${bg}`); continue; }
    const r = await ratioOf(page, fg, back);
    if (r < 3) bad.push(`${e.what} edge is ${r.toFixed(2)}:1 on the ${where} in the ${scheme} scheme, under 3:1`);
  }
  return bad;
};

// The dashed buttons draw an unpressed edge that must reach 3:1. Overturn on a ruling card is one of them.
for (const scheme of ["light", "dark"]) {
  test(`the unpressed None of these, Mark done, Park and Overturn buttons draw an edge of 3:1 or more on their card and on the page, ${scheme} scheme`, async (t) => {
    const page = await open(t, { items: [DECISION, TASK, ARBITER], scheme }); if (!page) return;
    const edges = await dashEdges(page, [["None of these", "b-none", DECISION], ["Mark done", "b-done", TASK], ["Park", "b-park", DECISION], ["Park", "b-park", TASK], ["Overturn", "b-over", ARBITER]]);
    assert.deepEqual(await edgeBad(page, edges, scheme), []);
  });
  // A seen card is tinted (color-mix of --surface and --ground), so its ground is not the plain card: its edge is read against that tint too.
  test(`the unpressed None of these and Park buttons on a seen card draw an edge of 3:1 or more on the tinted card and on the page, ${scheme} scheme`, async (t) => {
    const seen = mk("seen-old", 1, { added: at(5) });
    const page = await open(t, { items: [seen, sentItem()], scheme }); if (!page) return;
    assert.equal(await seenOf(page, seen), "true", `No. ${seen.n} is not drawn as a seen card, so its tint is not tested`);
    const edges = await dashEdges(page, [["None of these", "b-none", seen], ["Park", "b-park", seen]]);
    assert.deepEqual(await edgeBad(page, edges, scheme), []);
  });
}

// A pressed dash button draws the solid ink edge (.btn.dash[aria-pressed="true"]). Each case reads the unpressed button first, so a
// dashed edge is the control, then presses it. The ink colour comes from a probe that reads --ink, never from a copy of its value.
const inkColor = (page) => page.evaluate(() => { const p = document.createElement("i"); p.style.color = "var(--ink)"; document.body.append(p); const c = getComputedStyle(p).color; p.remove(); return c; });
const edgeOf = (loc) => loc.evaluate((el) => ({ style: getComputedStyle(el).borderTopStyle, color: getComputedStyle(el).borderTopColor }));
const overPress = (page, it) => page.locator(`#b-over-${it.id}`);
const nonePress = (page, it) => page.locator(`#b-none-${it.id}`);
const donePress = (page, it) => page.locator(`#b-done-${it.id}`);
for (const scheme of ["light", "dark"]) {
  test(`a pressed Park on an open decision card draws a solid ink edge, and an unpressed one a dashed edge, ${scheme} scheme`, async (t) => {
    const page = await open(t, { items: [DECISION], scheme }); if (!page) return;
    await need(card(page, DECISION), `No. ${DECISION.n} is not on the page`);
    await need(parkPress(page, DECISION), "the decision card has no Park button");
    const off = await edgeOf(parkPress(page, DECISION));
    assert.equal(off.style, "dashed", "an unpressed Park does not draw a dashed edge: " + off.style);
    await parkPress(page, DECISION).click();
    assert.equal(await pressedOf(parkPress(page, DECISION)), "true", "a Park press did not press Park");
    const on = await edgeOf(parkPress(page, DECISION));
    assert.equal(on.style, "solid", "a pressed Park does not draw a solid edge: " + on.style);
    assert.equal(on.color, await inkColor(page), "a pressed Park's edge is not the ink colour: " + on.color);
  });
  test(`a pressed Drop on a parked line draws a solid ink edge, and an unpressed one a dashed edge, ${scheme} scheme`, async (t) => {
    const page = await open(t, { items: [DECISION], meta: PARK_META, scheme }); if (!page) return;
    await parkLoaded(page);
    await need(parkLine(page, PARK_A), "the parked line is not on the page");
    await need(parkBtn(page, PARK_A, "drop"), "the parked line has no Drop button");
    const off = await edgeOf(parkBtn(page, PARK_A, "drop"));
    assert.equal(off.style, "dashed", "an unpressed Drop does not draw a dashed edge: " + off.style);
    await parkBtn(page, PARK_A, "drop").click();
    assert.equal(await pressedOf(parkBtn(page, PARK_A, "drop")), "true", "a Drop press did not press Drop");
    const on = await edgeOf(parkBtn(page, PARK_A, "drop"));
    assert.equal(on.style, "solid", "a pressed Drop does not draw a solid edge: " + on.style);
    assert.equal(on.color, await inkColor(page), "a pressed Drop's edge is not the ink colour: " + on.color);
  });
  test(`a pressed Overturn on a closed arbiter card draws a solid ink edge, and an unpressed one a dashed edge, ${scheme} scheme`, async (t) => {
    const page = await open(t, { items: [DECISION, ARBITER], scheme }); if (!page) return;
    await need(card(page, ARBITER), `No. ${ARBITER.n} is not on the page`);
    await need(overPress(page, ARBITER), "the arbiter card has no Overturn button");
    const off = await edgeOf(overPress(page, ARBITER));
    assert.equal(off.style, "dashed", "an unpressed Overturn does not draw a dashed edge: " + off.style);
    await overPress(page, ARBITER).click();
    assert.equal(await pressedOf(overPress(page, ARBITER)), "true", "an Overturn press did not press Overturn");
    const on = await edgeOf(overPress(page, ARBITER));
    assert.equal(on.style, "solid", "a pressed Overturn does not draw a solid edge: " + on.style);
    assert.equal(on.color, await inkColor(page), "a pressed Overturn's edge is not the ink colour: " + on.color);
  });
  test(`a pressed None of these on a decision draws a solid ink edge, and an unpressed one a dashed edge, ${scheme} scheme`, async (t) => {
    const page = await open(t, { items: [DECISION], scheme }); if (!page) return;
    await need(card(page, DECISION), `No. ${DECISION.n} is not on the page`);
    await need(nonePress(page, DECISION), "the decision card has no None of these button");
    const off = await edgeOf(nonePress(page, DECISION));
    assert.equal(off.style, "dashed", "an unpressed None of these does not draw a dashed edge: " + off.style);
    await nonePress(page, DECISION).click();
    assert.equal(await pressedOf(nonePress(page, DECISION)), "true", "a None of these press did not press None of these");
    const on = await edgeOf(nonePress(page, DECISION));
    assert.equal(on.style, "solid", "a pressed None of these does not draw a solid edge: " + on.style);
    assert.equal(on.color, await inkColor(page), "a pressed None of these edge is not the ink colour: " + on.color);
  });
  test(`a pressed Mark done on a task draws a solid ink edge, and an unpressed one a dashed edge, ${scheme} scheme`, async (t) => {
    const page = await open(t, { items: [TASK], scheme }); if (!page) return;
    await need(card(page, TASK), `No. ${TASK.n} is not on the page`);
    await need(donePress(page, TASK), "the task card has no Mark done button");
    const off = await edgeOf(donePress(page, TASK));
    assert.equal(off.style, "dashed", "an unpressed Mark done does not draw a dashed edge: " + off.style);
    await donePress(page, TASK).click();
    assert.equal(await pressedOf(donePress(page, TASK)), "true", "a Mark done press did not press Mark done");
    const on = await edgeOf(donePress(page, TASK));
    assert.equal(on.style, "solid", "a pressed Mark done does not draw a solid edge: " + on.style);
    assert.equal(on.color, await inkColor(page), "a pressed Mark done edge is not the ink colour: " + on.color);
  });
}

// The rail rows share .ov-head. Its 44px floor is for a coarse pointer only: the fine page stays exactly 32px, so a 44px floor for every pointer fails here.
test("each rail row is 44px tall or more on a coarse pointer, and 32px on a fine one, at 390 wide", async (t) => {
  const items = [DECISION, TASK, ARBITER];
  const page = await open(t, { items, answers: SAVED_A, hasTouch: true, viewport: { width: 390, height: 844 } }); if (!page) return;
  assert.equal(await coarse(page), true, "the touch page does not match pointer: coarse, so the touch rule is not tested");
  for (const href of ["#tier-answered", "#tier-ruled", "#asks"]) await need(page.locator(`#rail a.ov-head[href="${href}"]`), `the rail has no row ${href}`);
  const bad = (await sizes(railRows(page), "href")).filter(([, h]) => h < 44).map(([href, h]) => `rail row ${href} is ${h.toFixed(1)}px tall on a coarse pointer, under 44px`);
  const fine = await open(t, { items, answers: SAVED_A, viewport: { width: 390, height: 844 } }); if (!fine) return;
  assert.equal(await coarse(fine), false, "the fine page matches pointer: coarse, so the fine control is not tested");
  assert.ok((await railRows(fine).count()) >= 3, "the fine rail draws fewer than 3 rows, so the control measures nothing");
  const fineBad = (await sizes(railRows(fine), "href")).filter(([, h]) => h !== 32).map(([href, h]) => `rail row ${href} is ${h.toFixed(1)}px tall on a fine pointer, not 32px`);
  assert.deepEqual([...bad, ...fineBad], []);
});

// The rail's chips are 32px on a fine pointer and 44px on a coarse one. Fine stays exactly 32px.
for (const width of [390, 1280]) {
  test(`each rail chip is 44px tall or more on a coarse pointer, and 32px on a fine one, at ${width} wide`, async (t) => {
    const items = [DECISION, TASK, mk("pair-a", 3, { group: "pair" }), mk("pair-b", 4, { group: "pair" })];
    const page = await open(t, { items, hasTouch: true, viewport: { width, height: 900 } }); if (!page) return;
    assert.equal(await coarse(page), true, "the touch page does not match pointer: coarse, so the touch rule is not tested");
    assert.ok((await railChips(page).count()) >= 4, `the rail draws ${await railChips(page).count()} chips, under 4, so the measure is empty`);
    assert.ok((await page.locator("#rail .pairchips .nchip").count()) >= 2, "the rail draws no grouped pair, so the pair chips are not measured");
    const bad = (await sizes(railChips(page), "id")).filter(([, h]) => h < 44).map(([id, h]) => `rail chip ${id} is ${h.toFixed(1)}px tall on a coarse pointer, under 44px`);
    const fine = await open(t, { items, viewport: { width, height: 900 } }); if (!fine) return;
    assert.equal(await coarse(fine), false, "the fine page matches pointer: coarse, so the fine control is not tested");
    const fineBad = (await sizes(railChips(fine), "id")).filter(([, h]) => h !== 32).map(([id, h]) => `rail chip ${id} is ${h.toFixed(1)}px tall on a fine pointer, not 32px`);
    assert.deepEqual([...bad, ...fineBad], []);
  });
}

// ---------------------------------------------------------------- the recommended option, and the answer's label
// `recommended` is a key, or a list of keys on a multi item, that the page stars. The star falls back to `pick` for an
// old item. The star and the stood line say "Recommended". Each saved decision answer carries `label` beside `choice`:
// "A: <option label>" for a pick, a list of those for a multi item, "none of these" for none. `choice` stays the key.

test("the star sits on the recommended option, not on the pick", async (t) => {
  const it = mk("rec-star", 40, { recommended: "b", pick: "a" });
  const page = await open(t, { items: [it] }); if (!page) return;
  assert.equal(await page.locator(`label[for="o-${it.id}-b"] .pick`).count(), 1, "the star is not on the recommended option b");
  assert.equal(await page.locator(`label[for="o-${it.id}-a"] .pick`).count(), 0, "the star still sits on the pick a");
});

test("an old item with no recommended stars its pick", async (t) => {
  const it = mk("old-pick", 41, { pick: "b" });
  const page = await open(t, { items: [it] }); if (!page) return;
  assert.equal(await page.locator(`label[for="o-${it.id}-b"] .pick`).count(), 1, "the star is not on the pick b of an old item");
  assert.equal(await page.locator(`label[for="o-${it.id}-a"] .pick`).count(), 0, "the star sits on a with no recommended");
});

test("the star is named Recommended in its label and its tooltip", async (t) => {
  const page = await open(t); if (!page) return;
  const star = page.locator(`label[for="o-${DECISION.id}-a"] .pick .spark`);
  assert.equal(await star.getAttribute("aria-label"), "Recommended", "the star's label is not Recommended");
  assert.equal(await star.getAttribute("title"), "Recommended", "the star's tooltip is not Recommended");
});

test("a stood pick says The recommended option goes with your next Send.", async (t) => {
  const it = mk("stood-rec", 42, { stands: true });
  const page = await open(t, { items: [it] }); if (!page) return;
  assert.equal(await card(page, it).locator(".ready").textContent(), "The recommended option goes with your next Send.");
});

test("an item that names recommended draws no field warning", async (t) => {
  const it = mk("rec-field", 43, { recommended: "b" });
  const page = await open(t, { items: [it] }); if (!page) return;
  assert.equal((await card(page, it).textContent()).includes("Which field"), false, "the card warns a field the page does not draw");
});

test("a pick-one answer carries its label, A: Red, beside its choice", async (t) => {
  const page = await open(t); if (!page) return;
  await takePick(page, DECISION);
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], DECISION.id);
  const a = (await answers(page))[DECISION.id];
  assert.equal(a.choice, "a", "the choice is no longer the key");
  assert.ok(typeof a.label === "string", "the answer has no label: " + JSON.stringify(a));
  assert.match(a.label, /^a: Red$/i);
});

test("a none answer carries the label none of these, and its choice stays none", async (t) => {
  const page = await open(t); if (!page) return;
  await addNote(page, DECISION, "Green please");
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], DECISION.id);
  const a = (await answers(page))[DECISION.id];
  assert.equal(a.choice, "none");
  assert.ok(typeof a.label === "string", "the none answer has no label: " + JSON.stringify(a));
  assert.match(a.label, /^none of these$/i);
});

test("a multi answer carries a list of labels, one per tick, beside its list of keys", async (t) => {
  const it = multi("label-multi", 44);
  const page = await open(t, { items: [it] }); if (!page) return;
  await needBoxes(page, it, 3);
  await takePick(page, it);
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], it.id);
  const a = (await answers(page))[it.id];
  assert.deepEqual(a.choice, ["a", "c"], "the multi choice is no longer the list of keys");
  assert.ok(Array.isArray(a.label), "the multi answer has no list of labels: " + JSON.stringify(a));
  assert.equal(a.label.length, 2);
  assert.match(a.label[0], /^a: Red$/i);
  assert.match(a.label[1], /^c: Green$/i);
});

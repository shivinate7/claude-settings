// Browser cases for the waiting page's sort and tier labels (docs/design/tier-sort-notes.md: ruling Q1, points 1, 3 and 4).
// Blocking sorts by arrival, new before seen, the most `stops` (a group takes its best member's), rank, then age. Each order
// is worked out at load and kept. A Blocking card's top row shows "stops N", a group head shows its count once, and each tier
// head has one line that names its key.
//   NODE_PATH=<dir with playwright> node --test skills/waiting-page/tests/page_tier_sort.test.mjs
// The stub database and open() below are a copy of page.test.mjs's, trimmed to what these cases use. That file runs its
// cases when it is imported, so its helpers cannot be imported, and moving them into a shared module would edit the file
// the repo sub-group cases also change.
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { needEnv } from "../../../testing/skip-locally-fail-in-ci.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.join(HERE, "..", "page.html"), "utf8");
const require = createRequire(import.meta.url);
const ORIGIN = "http://waiting.test/";
let browser;
after(async () => { if (browser) await browser.close(); });

const DECISION = {
  id: "pick-a-colour", n: 27, kind: "decision", status: "open", added: "2026-10-26T00:00:00Z",
  ref: "c1, a test step", title: "Pick a colour", owner: "test thread", home: "c1", context: "Which colour?",
  options: [
    { key: "a", label: "Red", how: "h", gain: "g", lose: "l" },
    { key: "b", label: "Blue", how: "h", gain: "g", lose: "l" },
  ],
  pick: "a", why: "Red is bold.",
};
const mk = (id, n, over = {}) => ({ ...DECISION, id, n, title: "Question " + n, ...over });
// A Blocking item: `holds` names what waits. A case adds `stops` when it counts it.
const blk = (id, n, over = {}) => mk(id, n, { holds: "Lane " + id + " waits on your word.", ...over });
const at = (day) => `2026-10-${String(day).padStart(2, "0")}T00:00:00Z`;
const SENT_AT = at(10);
const ASKED_AFTER_SEND = "2026-10-30T00:00:00Z";
const LATER = "2026-11-20T00:00:00Z";
const sentItem = () => mk("sent-closed", 90, { status: "closed", lastAnswer: { choice: "a", at: SENT_AT, note: "" } });

// The stub database: each collection is a map of id to data, and each write fires its listeners. window.__putItem is a session's
// write after load; window.__answers reads the answers the page wrote.
function stubDb({ items, answers, groups }) {
  const data = { items: Object.fromEntries(items.map((i) => [i.id, i])), answers: { ...answers }, groups: { ...groups }, receipts: {}, meta: {} };
  window.__log = [];
  const subs = {};
  const snap = (name) => ({ docs: Object.entries(data[name] || {}).map(([id, v]) => ({ id, data: () => v })) });
  const dsnap = (name, id) => ({ exists: !!(data[name] || {})[id], data: () => (data[name] || {})[id] || null });
  const fire = (name) => (subs[name] || []).forEach((cb) => cb(snap(name)));
  window.__answers = () => data.answers;
  window.__putItem = (it) => { data.items[it.id] = it; fire("items"); };
  const listen = (name, cb) => { (subs[name] = subs[name] || []).push(cb); setTimeout(() => cb(snap(name)), 0); return () => {}; };
  const docRef = (name, id) => ({
    get: async () => dsnap(name, id),
    set: async (body) => { window.__log.push(["set", name, id, body]); (data[name] = data[name] || {})[id] = body; setTimeout(() => fire(name), 0); },
    update: async (body) => { if (!(data[name] || {})[id]) throw { code: "not-found" }; data[name][id] = { ...data[name][id], ...body }; setTimeout(() => fire(name), 0); },
    delete: async () => { delete (data[name] || {})[id]; setTimeout(() => fire(name), 0); },
    onSnapshot: (cb) => { setTimeout(() => cb(dsnap(name, id)), 0); return () => {}; },
  });
  const db = {
    doc: (p) => docRef(p.split("/")[0], p.split("/")[1]),
    collection: (name) => ({
      onSnapshot: (cb) => listen(name, cb),
      orderBy: () => ({ onSnapshot: (cb) => listen(name, cb) }),
      doc: (id) => docRef(name, id),
    }),
  };
  window.claude = { use: async (cap) => (cap === "db" ? db : null) };
}

// Loads the page with these items and waits until the first one is drawn. Each case gets its own browser page.
async function open(t, { items, answers = {}, groups = {} }) {
  browser = browser || await needEnv(t, "chromium", async () => require("playwright").chromium.launch());
  if (!browser) return null;
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  page.setDefaultTimeout(Number(process.env.WP_TIMEOUT) || 5000);
  t.after(() => page.close());
  // The page is served from a stand-in origin, so the init script and localStorage both apply. Every other request is refused.
  await page.route("**/*", (r) => (r.request().url() === ORIGIN ? r.fulfill({ contentType: "text/html; charset=utf-8", body: html }) : r.abort()));
  await page.addInitScript(stubDb, { items, answers, groups });
  await page.goto(ORIGIN);
  await page.waitForFunction("state.items.length > 0");
  await page.waitForSelector(`#item-${items[0].id}`);
  return page;
}

// The card ids of tier `k`, in the order the page draws them.
async function tierIds(page, k) {
  const tiers = await page.evaluate(() => [...document.querySelectorAll("section.tier")].map((s) => [s.id, [...s.querySelectorAll("article.card")].map((c) => c.id.slice(5))]));
  const tier = tiers.find((x) => x[0] === "tier-" + k);
  assert.ok(tier, `no tier-${k} section on the page`);
  return tier[1];
}

// The top row of `it`'s card in tier `k`. The card's place in the tier is asserted first, so a missing card fails by name.
async function topIn(page, k, it) {
  const scope = page.locator(`#tier-${k} #item-${it.id}`);
  assert.equal(await scope.count(), 1, `No. ${it.n} is not in tier-${k}`);
  return scope.locator(".top").textContent();
}

const choose = (page, it, key) => page.locator(`label[for="o-${it.id}-${key}"] .lab`).click();

// ---------------------------------------------------------------- Blocking order: arrival, new before seen, most stops, rank, age

test("Blocking: the item that stops more work sits above an older one that stops less", async (t) => {
  const older = blk("stops-one", 1, { added: at(1), stops: ["lane a"] });
  const newer = blk("stops-three", 2, { added: at(5), stops: ["lane a", "PR #1201", "lane b"] });
  const page = await open(t, { items: [older, newer] }); if (!page) return;
  assert.deepEqual(await tierIds(page, "holds"), [newer.id, older.id]);
});

test("Blocking: the most stops comes before the writer's rank", async (t) => {
  const ranked = blk("rank-first", 1, { added: at(1), rank: 0, stops: ["lane a"] });
  const stopping = blk("rank-last", 2, { added: at(2), rank: 5, stops: ["lane a", "lane b"] });
  const page = await open(t, { items: [ranked, stopping] }); if (!page) return;
  assert.deepEqual(await tierIds(page, "holds"), [stopping.id, ranked.id]);
});

test("Blocking: rank breaks a tie in stops", async (t) => {
  const older = blk("tie-old", 1, { added: at(1), rank: 3, stops: ["lane a", "lane b"] });
  const newer = blk("tie-new", 2, { added: at(5), rank: 1, stops: ["lane c", "lane d"] });
  const page = await open(t, { items: [older, newer] }); if (!page) return;
  assert.deepEqual(await tierIds(page, "holds"), [newer.id, older.id]);
});

test("Blocking: age breaks a tie in stops and rank", async (t) => {
  const older = blk("age-old", 1, { added: at(1), stops: ["lane a"] });
  const newer = blk("age-new", 2, { added: at(5), stops: ["lane b"] });
  const page = await open(t, { items: [older, newer] }); if (!page) return;
  assert.deepEqual(await tierIds(page, "holds"), [older.id, newer.id]);
});

test("Blocking: an item with holds and no stops counts zero, so it sits after the counted ones", async (t) => {
  const bare = blk("bare-old", 1, { added: at(1) });
  const counted = blk("counted-new", 2, { added: at(9), stops: ["lane a"] });
  const page = await open(t, { items: [bare, counted] }); if (!page) return;
  assert.deepEqual(await tierIds(page, "holds"), [counted.id, bare.id]);
});

test("Blocking: a group takes its best member's stops, not its oldest member's", async (t) => {
  const solo = blk("solo-two", 1, { added: at(1), stops: ["lane a", "lane b"] });
  const grpBare = blk("grp-bare", 2, { added: at(4), group: "pair" });
  const grpMore = blk("grp-three", 3, { added: at(5), group: "pair", stops: ["lane c", "lane d", "lane e"] });
  const page = await open(t, { items: [solo, grpBare, grpMore] }); if (!page) return;
  const ids = await tierIds(page, "holds");
  assert.deepEqual(ids.slice(2), [solo.id], "the solo item with two stops is not last: " + ids.join(", "));
  assert.deepEqual(ids.slice(0, 2).sort(), [grpBare.id, grpMore.id].sort(), "the group is split: " + ids.join(", "));
});

test("Blocking: an item that arrives after load sorts first, whatever its stops", async (t) => {
  const old = blk("arr-old", 1, { added: at(1), stops: ["lane a", "lane b", "lane c"] });
  const page = await open(t, { items: [old] }); if (!page) return;
  const late = blk("arr-late", 9, { added: at(28) });
  await page.evaluate((it) => window.__putItem(it), late);
  await page.locator(`#tier-holds #item-${late.id}`).waitFor();
  assert.deepEqual(await tierIds(page, "holds"), [late.id, old.id]);
});

test("Blocking: a new item sits above a seen one, whatever the seen one stops", async (t) => {
  const seen = blk("seen-many", 1, { added: at(5), stops: ["lane a", "lane b", "lane c", "lane d", "lane e"] });
  const fresh = blk("fresh-none", 2, { added: ASKED_AFTER_SEND });
  const page = await open(t, { items: [seen, fresh, sentItem()] }); if (!page) return;
  assert.equal(await page.locator(`#item-${seen.id}`).getAttribute("data-seen"), "true", "the older item is not seen");
  assert.deepEqual(await tierIds(page, "holds"), [fresh.id, seen.id]);
});

test("Upcoming and Whenever keep their own keys, and ignore stops", async (t) => {
  const soon = mk("due-soon", 1, { added: at(3), by: "2026-11-05T00:00:00Z" });
  const soonerStops = mk("due-later-stops", 2, { added: at(1), by: LATER, stops: ["lane a", "lane b", "lane c"] });
  const calmOld = mk("calm-old", 3, { added: at(1) });
  const calmNew = mk("calm-new-stops", 4, { added: at(5), stops: ["lane a", "lane b", "lane c"] });
  const page = await open(t, { items: [soon, soonerStops, calmOld, calmNew] }); if (!page) return;
  assert.deepEqual(await tierIds(page, "due"), [soon.id, soonerStops.id], "Upcoming is not nearest deadline first");
  assert.deepEqual(await tierIds(page, "calm"), [calmOld.id, calmNew.id], "Whenever is not oldest first");
});

// ---------------------------------------------------------------- the order is worked out at load and kept

test("a writer's update and a Send on the open page move no Blocking card", async (t) => {
  const first = blk("held-first", 1, { added: at(1), rank: 1 });
  const second = blk("held-second", 2, { added: at(2), rank: 2 });
  const pick = mk("whenever-pick", 3, { added: at(3) });
  const page = await open(t, { items: [first, second, pick] }); if (!page) return;
  assert.deepEqual(await tierIds(page, "holds"), [first.id, second.id], "the load order is not rank order");
  // The writer moves the second item to the top while the page is open: rank 0 and three stops.
  await page.evaluate((it) => window.__putItem(it), { ...second, rank: 0, stops: ["lane a", "lane b", "lane c"] });
  await page.waitForFunction((id) => (state.items.find((i) => i.id === id) || {}).rank === 0, second.id);
  await choose(page, pick, "a");
  await page.click("#send");
  await page.waitForFunction((id) => !document.querySelector(`#tier-calm #item-${id}`), pick.id);
  assert.deepEqual(await tierIds(page, "holds"), [first.id, second.id], "a writer's update and a Send re-sorted Blocking");
});

// ---------------------------------------------------------------- the count on the card, the group head, and the tier key lines

test("a Blocking card's top row shows stops N, N the length of its list", async (t) => {
  const three = blk("count-three", 1, { added: at(1), stops: ["lane fix-proxy", "PR #1201", "lane b"] });
  const many = blk("count-many", 2, { added: at(2), stops: Array.from({ length: 12 }, (_, i) => "lane s" + i) });
  const page = await open(t, { items: [three, many] }); if (!page) return;
  assert.match(await topIn(page, "holds", three), /\bstops 3\b/, `No. ${three.n} has no "stops 3" in its top row`);
  assert.match(await topIn(page, "holds", many), /\bstops 12\b/, `No. ${many.n} has no "stops 12" in its top row`);
});

test("a card with no stops, or an empty list, shows no count", async (t) => {
  const none = blk("no-stops", 1, { added: at(1) });
  const empty = blk("empty-stops", 2, { added: at(2), stops: [] });
  const page = await open(t, { items: [none, empty] }); if (!page) return;
  for (const it of [none, empty]) assert.doesNotMatch(await topIn(page, "holds", it), /stops/, `No. ${it.n} shows a count`);
});

test("a group shows its count once, in its head, and no member card shows one", async (t) => {
  const one = blk("grp-one", 1, { added: at(1), group: "pair", stops: ["lane fix-proxy", "lane shared"] });
  const two = blk("grp-two", 2, { added: at(2), group: "pair", stops: ["lane shared", "PR #1201"] });
  const page = await open(t, { items: [one, two] }); if (!page) return;
  const frame = page.locator("#tier-holds section.bundle#group-pair");
  assert.equal(await frame.count(), 1, "the two members are not one frame in Blocking");
  const head = await frame.locator("header").first().textContent();
  assert.equal((head.match(/stops \d+/g) || []).length, 1, "the group head does not show its count once: " + head);
  // Three distinct entries across the two members: the shared lane counts once.
  assert.match(head, /\bstops 3\b/, "the group head count is not 3: " + head);
  for (const it of [one, two]) assert.doesNotMatch(await topIn(page, "holds", it), /stops/, `No. ${it.n} shows a count of its own`);
});

test("each tier head has one line that names its key, and the line shows once on the page", async (t) => {
  const held = blk("key-held", 1, { added: at(1), stops: ["lane a"] });
  const due = mk("key-due", 2, { added: at(2), by: LATER });
  const calm = mk("key-calm", 3, { added: at(3) });
  const page = await open(t, { items: [held, due, calm] }); if (!page) return;
  const keys = [
    ["holds", /Most stopped work first, then triage['’]s order, then oldest\./i],
    ["due", /Triage['’]s order first, then nearest deadline, then oldest\./i],
    ["calm", /Triage['’]s order first, then decisions, then oldest\./i],
  ];
  for (const [k] of keys) assert.equal(await page.locator(`#tier-${k}`).count(), 1, `no tier-${k} section on the page`);
  const body = await page.evaluate(() => document.body.innerText);
  for (const [k, re] of keys) {
    const section = await page.locator(`#tier-${k}`).innerText();
    assert.match(section, re, `tier-${k} has no line that names its key`);
    const shown = (body.match(new RegExp(re.source, "gi")) || []).length;
    assert.equal(shown, 1, `tier-${k}'s key line shows ${shown} times on the page`);
  }
});

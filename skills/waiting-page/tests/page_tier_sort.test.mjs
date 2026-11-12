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
function stubDb({ items, answers, groups, meta, holdMeta, failMeta, metaFirst }) {
  const data = { items: Object.fromEntries(items.map((i) => [i.id, i])), answers: { ...answers }, groups: { ...groups }, receipts: {}, meta: meta ? { page: meta } : {} };
  window.__log = [];
  const subs = {};
  // holdMeta: the meta document's listener is kept, and window.__releaseMeta delivers it. The stub has no clock, so a case names the moment meta arrives.
  const heldMeta = [];
  window.__releaseMeta = () => heldMeta.splice(0).forEach((cb) => cb(dsnap("meta", "page")));
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
    onSnapshot: (cb, failed) => {
      // failMeta: the read fails, and window.__metaFailed says so once the failure is delivered.
      if (name === "meta" && failMeta) setTimeout(() => { window.__metaFailed = true; if (failed) failed({ code: "unavailable" }); }, 0);
      else if (name === "meta" && holdMeta) heldMeta.push(cb);
      // metaFirst: the page subscribes to items before meta, so a synchronous meta arrives before any item: a load with the meta present.
      else if (name === "meta" && metaFirst) cb(dsnap(name, id));
      else setTimeout(() => cb(dsnap(name, id)), 0);
      return () => {};
    },
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
async function open(t, { items, answers = {}, groups = {}, meta, holdMeta = false, failMeta = false, metaFirst = false }) {
  browser = browser || await needEnv(t, "chromium", async () => require("playwright").chromium.launch());
  if (!browser) return null;
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  page.setDefaultTimeout(Number(process.env.WP_TIMEOUT) || 5000);
  t.after(() => page.close());
  // The page is served from a stand-in origin, so the init script and localStorage both apply. Every other request is refused.
  await page.route("**/*", (r) => (r.request().url() === ORIGIN ? r.fulfill({ contentType: "text/html; charset=utf-8", body: html }) : r.abort()));
  await page.addInitScript(stubDb, { items, answers, groups, meta, holdMeta, failMeta, metaFirst });
  await page.goto(ORIGIN);
  await page.waitForFunction("state.items.length > 0");
  // A held or failed meta draws no card until it settles, so a case with one waits on its own marker instead.
  if (!holdMeta && !failMeta) await page.waitForSelector(`#item-${items[0].id}`);
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
  assert.deepEqual(await tierIds(page, "holds"), [first.id, second.id], "Blocking was worked out again while the page was open");
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
  const none = blk("bare-card", 1, { added: at(1) });
  const empty = blk("empty-list", 2, { added: at(2), stops: [] });
  const page = await open(t, { items: [none, empty] }); if (!page) return;
  for (const it of [none, empty]) assert.doesNotMatch(await topIn(page, "holds", it), /\bstops \d/, `No. ${it.n} shows a count`);
});

test("a Blocking card with stops shows no 'does not draw' note, since the page lists the field", async (t) => {
  const counted = blk("drawn-stops", 1, { added: at(1), stops: ["lane a", "lane b"] });
  const page = await open(t, { items: [counted] }); if (!page) return;
  const scope = page.locator(`#tier-holds #item-${counted.id}`);
  assert.equal(await scope.count(), 1, `No. ${counted.n} is not in tier-holds`);
  const notes = await scope.locator('[role="status"]', { hasText: "does not draw" }).count();
  assert.equal(notes, 0, `No. ${counted.n} carries a "does not draw" note: the page does not list the stops field`);
});

test("a group shows its count once, in its head, and no member card shows one", async (t) => {
  const one = blk("grp-one", 1, { added: at(1), group: "pair", stops: ["lane fix-proxy", "lane shared"] });
  const two = blk("grp-two", 2, { added: at(2), group: "pair", stops: ["lane shared", "PR #1201"] });
  const page = await open(t, { items: [one, two] }); if (!page) return;
  const frame = page.locator("#tier-holds section.bundle#group-pair");
  assert.equal(await frame.count(), 1, "the two members are not one frame in Blocking");
  // The head's text as the eye reads it: its screen-reader words (.sr) are left out.
  const head = await frame.locator("header").first().evaluate((h) => { const c = h.cloneNode(true); c.querySelectorAll(".sr").forEach((n) => n.remove()); return c.textContent; });
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

// ---------------------------------------------------------------- the sort key, the group count, and the repo heads (review round 2)

test("a group's stops are the union of its members' lists, so it sorts above an older solo with fewer", async (t) => {
  // The lists are {lane a, lane b} and {lane b, lane c}: each member has two, the union has three. The older solo has two.
  const solo = blk("union-solo", 1, { added: at(1), stops: ["lane x", "lane y"] });
  const grpA = blk("union-a", 2, { added: at(3), group: "pair", stops: ["lane a", "lane b"] });
  const grpB = blk("union-b", 3, { added: at(4), group: "pair", stops: ["lane b", "lane c"] });
  const page = await open(t, { items: [solo, grpA, grpB] }); if (!page) return;
  const ids = await tierIds(page, "holds");
  assert.deepEqual(ids.slice(0, 2).sort(), [grpA.id, grpB.id].sort(), "the group with three stops in union is not first: " + ids.join(", "));
  assert.deepEqual(ids.slice(2), [solo.id], "the older solo with two stops is not last: " + ids.join(", "));
});

test("a card that gains stops after load shows no count the order does not use", async (t) => {
  const counted = blk("frozen-counted", 1, { added: at(1), stops: ["lane a", "lane b"] });
  const grows = mk("frozen-grows", 2, { added: at(2) });
  const page = await open(t, { items: [counted, grows] }); if (!page) return;
  assert.deepEqual(await tierIds(page, "calm"), [grows.id], "the item with no holds is not in Whenever at load");
  // The writer adds holds and three stops while the page is open. The order keeps the count of zero it took at load.
  await page.evaluate((it) => window.__putItem(it), { ...grows, holds: "Lane fix-proxy, PR #1201 and lane c wait on your word.", stops: ["lane fix-proxy", "PR #1201", "lane c"] });
  await page.locator(`#tier-holds #item-${grows.id}`).waitFor();
  assert.deepEqual(await tierIds(page, "holds"), [counted.id, grows.id], "the order moved the card that gained stops while the page was open");
  assert.match(await topIn(page, "holds", counted), /\bstops 2\b/, `No. ${counted.n} lost its count of two`);
  const top = await topIn(page, "holds", grows);
  assert.doesNotMatch(top, /\bstops \d/, `No. ${grows.n} shows a count the order does not use: "${top.trim()}"`);
});

test("a group whose member gains stops after load keeps the head count the order sorts by", async (t) => {
  const first = blk("grp-open", 1, { added: at(1), group: "pair", stops: ["lane a"] });
  const gains = blk("grp-gains", 2, { added: at(2), group: "pair" });
  const rival = blk("grp-rival", 3, { added: at(3), stops: ["lane b", "lane c"] });
  const page = await open(t, { items: [first, gains, rival] }); if (!page) return;
  // At load the group counts 1 (its union, {lane a}); the rival counts 2, so the rival is first.
  assert.equal((await tierIds(page, "holds"))[0], rival.id, "the rival with two stops is not first at load");
  // The writer adds three stops to the second member while the page is open: the union goes from 1 to 4.
  await page.evaluate((it) => window.__putItem(it), { ...gains, stops: ["lane d", "lane e", "lane f"] });
  await page.waitForFunction((id) => ((state.items.find((i) => i.id === id) || {}).stops || []).length === 3, gains.id);
  const frame = page.locator("#tier-holds section.bundle#group-pair");
  assert.equal(await frame.count(), 1, "the two members are not one frame in Blocking");
  assert.equal((await tierIds(page, "holds"))[0], rival.id, "the order moved while the page was open");
  // The head's text as the eye reads it: its screen-reader words (.sr) are left out.
  const head = await frame.locator("header").first().evaluate((h) => { const c = h.cloneNode(true); c.querySelectorAll(".sr").forEach((n) => n.remove()); return c.textContent; });
  assert.match(head, /\bstops 1\b/, "the group head does not show the count the order sorts by (its union at load, 1): " + head);
});

// The repo meta, held back or failed in the cases below: this repo is named "owner/this-repo".
const META = { repo: "owner/this-repo" };

test("until the repo meta settles the page draws its loading line, with no tier, card or repo head", async (t) => {
  // The items arrive; the meta document is held back, so the page cannot yet say which repo is this one.
  const repoless = blk("meta-repoless", 1, { added: at(1) });
  const other = blk("meta-other", 2, { added: at(2), repo: "owner/other-repo" });
  const page = await open(t, { items: [repoless, other], meta: META, holdMeta: true }); if (!page) return;
  assert.match(await page.locator("#list").innerText(), /Loading the items waiting on you/, "the loading line is not shown while the repo meta is held");
  assert.equal(await page.locator("section.tier").count(), 0, "a tier is drawn before the repo meta settles");
  assert.equal(await page.locator("article.card").count(), 0, "a card is drawn before the repo meta settles");
  assert.equal(await page.locator(".subgrp, .subhead").count(), 0, "a repo head is drawn before the repo meta settles");
});

test("when the repo meta arrives the page redraws, in the order a load with the meta gives", async (t) => {
  // The other-repo item is the oldest. Drawn flat it comes first; with the meta this repo's group sorts first, its items by age.
  const other = blk("meta-order-other", 1, { added: at(1), repo: "owner/other-repo" });
  const repoless = blk("meta-order-repoless", 2, { added: at(2) });
  const ownSlug = blk("meta-order-slug", 3, { added: at(3), repo: "owner/this-repo" });
  const items = [other, repoless, ownSlug];
  const held = await open(t, { items, meta: META, holdMeta: true }); if (!held) return;
  await held.evaluate(() => window.__releaseMeta());
  await held.waitForFunction("feed.meta === true");
  assert.doesNotMatch(await held.locator("#list").innerText(), /Loading the items waiting on you/, "the loading line still shows after the repo meta arrives");
  const after = await tierIds(held, "holds");
  const full = await open(t, { items, meta: META, metaFirst: true });
  assert.deepEqual(after, await tierIds(full, "holds"), "after the meta arrives the order is not the order a load with the meta gives: " + after.join(", "));
});

test("when the repo meta read fails the page settles, and repo-less items alone draw no repo head", async (t) => {
  // identity.name lives in the meta document, so a failed read leaves no name to fall back to: repo-less items are this repo's.
  const first = blk("meta-fail-a", 1, { added: at(1) });
  const second = blk("meta-fail-b", 2, { added: at(2) });
  const page = await open(t, { items: [first, second], failMeta: true }); if (!page) return;
  await page.waitForFunction("window.__metaFailed === true");
  assert.doesNotMatch(await page.locator("#list").innerText(), /Loading the items waiting on you/, "the loading line still shows after the repo meta read failed");
  assert.deepEqual(await tierIds(page, "holds"), [first.id, second.id], "the repo-less items are not drawn in tier order after the failed meta read");
  assert.equal(await page.locator(".subgrp, .subhead").count(), 0, "a repo head is drawn for repo-less items alone after the failed meta read");
  assert.doesNotMatch(await page.locator("#tier-holds .tsub").innerText(), /This repo first\./, "the key line says 'This repo first.' with repo-less items alone");
});

test("at 1280 the first run in the rail's chips has no top gap: its label's margin-top is 0", async (t) => {
  const META = { repo: "owner/this-repo" };
  const repoless = blk("gap-own", 1, { added: at(1) });
  const other = blk("gap-other", 2, { added: at(2), repo: "owner/other-repo" });
  const page = await open(t, { items: [repoless, other], meta: META }); if (!page) return;
  const runs = page.locator("#rail .chips-n > .rrun");
  assert.equal(await runs.count(), 2, "the rail does not draw one run per repo, so the gap is not reached");
  const marginOf = (i) => runs.nth(i).locator(".rrepo").evaluate((el) => getComputedStyle(el).marginTop);
  const second = await marginOf(1), first = await marginOf(0);
  assert.equal(second, "4px", "the second run's label has no 4px gap, so the width rule does not apply here");
  assert.equal(first, "0px", "the first run's label has a top gap from .rrepo: " + first);
});

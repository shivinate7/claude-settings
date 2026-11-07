# Waiting page, lane page-lane-answered-sinks: design notes

Mockup: `docs/design/lane-answered-sink.html`. Screen: `skills/waiting-page/page.html` (8cfba982, PR #1345 page-reply-uncollapse).
Deep links: `#s=page|stay|today`, `&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`. `#s=page` draws SENT_MOVE "sink",
`#s=stay` draws "stay", and `#s=today` draws the base. Sizes: phone 390, mid 800 and wide 1280, light and dark.
`layout.py devices` prints `unknown` for this repo, so the sizes come from the brief and page.html's breakpoints at 520 and
960. The mockup draws with page.html's own `<style>` (lines 8 to 850 at 8cfba982) and adds no CSS.

The sample: the page loaded at 15:32. In Blocking, the owner sent No. 21, No. 25 and No. 27 on this visit. No. 23 is still
open. No. 61 arrived at 15:40, like page item 309.

Settled by the rulings of Nov 6:
- A lane item sinks only when its answers record exists (`isSaved`), as the base does. No lane + `lastAnswer` predicate (coordinator, 15:47 CST).
- Owner, page item 311 (page save 21:51:10Z): in each tier, every open card always sits above every card answered on this visit.
  Arrivals after load go first. A Send moves the sent card below the open ones, and a Change brings it back
  up. His words: "ux-order-holds-still ... is applied too strictly and is taking me away from the outcome i want here".
- Coordinator, 15:51 CST, on top of item 311: arrivals after load go to the top of their tier. A card sent on this visit
  moves through one switch, SENT_MOVE. "sink" (the default, option a, now paged through triage) and "stay" (today's
  in-place behaviour). The sort-order change merges only after the ruling on rule ux-order-holds-still lands.

## 1. A saved answer routed to a lane: no change (regression state)

- Base check: a sunk saved card with `lane` (No. 52) reads "Filing pending, sent Nov 6, 13:59 CST" in its pill and
  "waits on lane stale-page-sweep" in its top row. It is in Answered and folded. Verdict: it already says it was sent and
  what it waits on. Drawn unchanged in every state (labelled "Today"), with No. 44 (`waits.pr`) beside it.
- The design reviewer checks it as a regression state only.

## 2. The order in a tier

- Arrivals (`#s=page`, `#s=stay`): an item that was not on the page at load goes to the top of its tier, above the new and
  seen parts. Two arrivals keep the tier's own order between them. Base (`#s=today`): No. 61 has no rank, so it sorts under
  every ranked card, the three sent ones included.
- SENT_MOVE "sink" (`#s=page`, the default): at a Send, each sent card leaves its tier for the Answered section, folded, at
  its place by time (newest first). The next open card takes its slot (No. 23 moves up). The tier holds open cards only, so
  item 311's order holds with no sort inside the tier. The rail chips move with their cards.
- SENT_MOVE "stay" (`#s=stay`): a sent card keeps its place in its tier until the next load, as today. Only arrivals move.
- Change: a Change on any card in Answered, sunk at load or on this visit, opens it in place in Answered, as today
  (page.html `freezeSunk` comment, base 8cfba982). Undo after a sink Send returns the card to its slot, open.
- Answered sub-head: with "sink" the section also holds cards sent on this visit, so "Sent before this visit, newest first."
  becomes "Your sent answers, newest first." (ux-statements-are-true).
- Departs from: page.html `freezeSunk` — a sent card left its tier only at reload; now it leaves at the Send. Owner grant:
  item 311 (21:51:10Z); ux-order-holds-still narrowed by item 313 a (16:47 CST, PR #1374).
- Departs from: ux-press-moves-nothing: the rows below a sent card that close its gap do not count as a move (item 313 a,
  16:47 CST; PR #1374).
- Built: freeze the set of item ids at load, beside `freezeSeen`. In `sorted()`, the first key of the tier sort is "not in
  that set". SENT_MOVE "sink" adds each item sent on this visit to the sunk set at the Send; Undo removes it.
- Rejected, item 311:
  - "Arrivals on top" as the whole design: it left an open card under a card sent on this visit. It lives on as SENT_MOVE "stay".
  - "Sent cards drop below open ones" inside the tier: superseded by SENT_MOVE "sink", which takes them out of the tier.

## Checked

- Playwright, Chromium: all 3 states at 390, 800 and 1280, light and dark (18 runs). No script error, no sideways scroll
  in the frame. Focus ids `item-61`, `item-52` and `tier-holds` each find a box.
- `label_once.py` on the 3 states at 390: no hit.

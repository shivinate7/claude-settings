# Waiting page, lane page-lane-answered-sinks: design notes

Mockup: `docs/design/lane-answered-sink.html`. Screen: `skills/waiting-page/page.html` (8cfba982, PR #1345 page-reply-uncollapse).
Deep links: `#s=page|today|sent-drops`, `&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`, `&hide=<state>,...`.
`#s=today` draws the base for comparison. Sizes: phone 390, mid 800 and wide 1280, light and dark. `layout.py devices`
prints `unknown` for this repo, so the sizes come from the brief and page.html's breakpoints at 520 and 960. The mockup
draws with page.html's own `<style>` (lines 8 to 850 at 8cfba982) and adds no CSS. Options are named by name, never by a letter.

The sample: the page loaded at 15:32. In Blocking, the owner sent No. 21, No. 25 and No. 27 on this visit. They stay in
place, answered, until the next load (`freezeSunk`). No. 23 is still open. No. 61 arrived at 15:40, like page item 309.

Settled by the rulings of Nov 6, not options here:
- A lane item sinks only when its answers record exists (`isSaved`), as the base does. No lane + `lastAnswer` predicate (coordinator, 15:47 CST).
- New open questions come first, above every answered or sunk card (owner, about 15:45 CST, on roadmap step f569b25b8).

## 1. A saved answer routed to a lane: no change (regression state)

- Base check: a sunk saved card with `lane` (No. 52) reads "Filing pending, sent Nov 6, 13:59 CST" in its pill and
  "waits on lane stale-page-sweep" in its top row. It is in Answered and folded. Verdict: it already says it was sent and
  what it waits on. Drawn unchanged in every state (labelled "Today"), with No. 44 (`waits.pr`) beside it.
- The design reviewer checks it as a regression state only.

## 2. Where an item that arrives after load goes

- Cause (base): `sorted()` orders a tier by new before seen, then rank, then age. A card the owner sent on this visit keeps
  its place (ux-order-holds-still). An item that arrives after load is new and unranked, so it lands under every ranked card,
  sent ones included (`#s=today`: No. 61 under No. 21, No. 25 and No. 27).
- Pick, "Arrivals on top" (`#s=page`): an item that was not on the page at load goes to the top of its tier, above the
  new and seen parts. Two arrivals keep the tier's own order between them. Every card shown at load keeps its place, so a
  Send moves nothing. At the next load, the cards sent on this visit sink into Answered, and the tier holds open cards only.
  Gain: the new question is the first card in its tier, above every card sent on this visit. Loss: an open card from load
  (No. 23) can still sit under a card the owner sent above it. The owner has already passed that card on this visit.
- How it squares with ux-order-holds-still: the rule is "an act on a row does not re-rank the list". An arrival is not an
  act on a row, and the rows already shown keep their order. ux-press-moves-nothing: an arrival already pushes the cards
  below it down today. On top, it pushes the whole tier down instead of part of it. Same kind of move, no new one.
- Builder: freeze the set of item ids at load, beside `freezeSeen`. In `sorted()`, the tier sort's first key is "not in
  that set" (first), then today's `part` (new, then seen). The rail chips follow the tier order (drawn).
- Option "Sent cards drop below open ones" (`#s=sent-drops`): at each Send, the page also moves every card sent on this
  visit below the open cards of its tier. Gain: every open card sits above every answered card at all times. Loss: a Send
  re-sorts cards the owner can see. Content above the bar moves after his press.
  Departs from: ux-order-holds-still ("an act on a row does not re-rank the list") and ux-press-moves-nothing; page.html
  `freezeSunk` keeps a sent card in place until reload. Owner grant: yes, if picked.
- Recommendation: "Arrivals on top". It fixes the case the owner hit (item 309) and keeps both house rules.

## Checked

- Playwright, Chromium: all 3 states at 390, 800 and 1280, light and dark (18 runs). No script error, no sideways scroll
  in the frame. Focus ids `item-61`, `item-52` and `tier-holds` each find a box.
- `label_once.py` on the 3 states at 390: no hit.

# Waiting page, Taken for you area: design notes

Mockup: `taken-picks.html` (this folder). Step: page-taken-picks-area. Screen: `skills/waiting-page/page.html`,
read from the roadmap checkout's `waiting/page/page.html` on Nov 18. Designer kind: informed.
The mockup holds page.html's `<style>` lines 8 to 1010, word for word. New CSS follows it in `#newcss`.
Deep links: `#s=cards|pressed|overruled|routed|empty`, `&p=above|below|merged`, `&o=open|folded`, `&n=overrule|overturn`, `&r=reopen|keep`, `&e=show|none`, `&w=all|390|1280`, `&t=light|dark`, `&lab=off`, `&hide=<option>,...`.
Sizes: `layout.py devices` prints "unknown" for this repo, so the sizes come from the brief: phone 390 and desktop 1280 (page.html breaks at 520 and 960). Light and dark.
"Now" is pinned at Nov 18, 19:30 CST. Fonts fall back to the system font, because the mockup opens with no network.
Prior pattern: `arbiter-ruling.html` (design folder) and page.html `buildRuling`, `sectionEl`, `rulingsEl`, `receipt`.

## 1. Which items the area lists: a `taken` field

- Today no field marks a taken pick. The five items carry it only in the id prefix `taken-`, the title words "Taken for you" and a `TAKEN FOR YOU:` line in `context`. `itemFields` (page.html) has no such field.
- Option "taken field" (drawn): `taken: { by, at, what, changes, against?, ended?, over }` on a closed decision. The page tests `typeof it.taken === "object"`. `by` is the role that took it; `at` the time it took it; `what` the pick in one sentence; `changes` the Departs-from text; `against` the owner's typed answer it goes against; `ended` why it no longer stands; `over` what Overrule does (from today's overrule option's `lose`).
  Gain: one test, as `arbiter: true` is for rulings; the card reads fields, not prose. Lose: the writer backfills the five items, and `itemFields` and the guard learn a new field.
- Option "id prefix": list items whose key starts `taken-`. Gain: no data change. Lose: a name carries meaning; no time or pick text to draw.
- Never `stands` or `pick`: the Nov 15 ruling removed them (step page-no-preselected-pick).
- Pick: taken field. Owner grant: yes (changes the item contract in skill waiting-page).

## 2. Where the area sits

- Today page.html `renderList` draws the open tiers, then Answered (`answeredEl`), then Arbiter rulings (`rulingsEl`).
- Option "before Answered" (`#p=above`, pick): after the open tiers. Gain: a pick not reviewed is the owner's work, so it sits next to the asks. Lose: Answered moves down by one section.
- Option "after Arbiter rulings" (`#p=below`): last on the page. Gain: Answered keeps its place. Lose: the owner scrolls past every read line to reach it.
- Option "merged with Arbiter rulings" (`#p=merged`): one area for every pick made for the owner; the arbiter is one more taker, and its card's Overturn becomes Overrule. Gain: one place, one act name (see 5). Lose: changes a section the owner ruled on (item 86).
  Departs from: page.html `rulingsEl` — the Arbiter rulings section folds into this area.
- Rail: one row, the undo-arrow glyph, name and count, no chips, in the same order as the sections.
- Pick: before Answered. Owner grant: yes for "merged" only.

## 3. Order: newest first, Last 24 hours and Older

- Sort by `taken.at`, newest first; a tie sorts by `n`, highest first. Two sub-heads, "Last 24 hours" and "Older", each with its count (page.html `.subhead`). A group with no card is not drawn.
- `added` cannot sort them: all five carry `added` 2026-11-15T00:23-06:00. The taken times exist today only in prose (Nov 14, 17:15 to 21:20).
- All five real items are older than 24 hours, so the mockup adds two Sample cards (No. 911, 912) to show the split.
- Older open on load (`#o=open`, pick) or folded under "Show N older picks" (`#o=folded`). Open: Gain: every pick shows. Lose: the list grows with each pick. Folded: Gain: a short area. Lose: one more press, and today all five are older.
- Pick: open.

## 4. The card

- Order: No. N, "taken by <role> <time>", the title, an "Against your answer." line when `against` is set (page.html `.stake.due`), Took, Changes, the last answer if any, "If you overrule:" (or "No longer stands." with why), "Show the full reasoning" (the full `context`, closed), then the foot: "Recorded in <home>." and Overrule.
- The title drops "Taken for you:" and " Overrule?": the area head already says it (house rule ux-label-once). The writer writes the shorter title; the five items need it rewritten.
- Label once (house rule ux-label-once): "Took", "Changes", "If you overrule:", "Against your answer." and "No longer stands." show on the first card that has them; later cards keep them for a screen reader only, as page.html `seenHead` does. Weight, the amber stake, the undo glyph and the check glyph carry them.
- A pick with no last answer and no end carries an accent left edge; the area's sub-line names the edge once and counts them ("2 not reviewed yet").
- Kept (836 b, debt-close route A by the owner; 837 d by the consultant on his word): "Your last answer, <time>" and "You kept it." or "Kept by the consultant, on your word." Overrule stays: nothing is final ("Nothing can't be undone don't wait on me", Nov 14 20:18).
- Ended (791 replaced by the Nov 17 09:20 ruling; 830 c, the wider skip built in PR 3568): "No longer stands." and why, with no Overrule (house rule ux-control-earns-place).
- Record ids show in "Recorded in", as on a ruling card today; this goes against house rule ux-machine-text-hidden, a conflict the page already carries.
- Pick: as drawn.

## 5. Overrule: one toggle, never preselected

- `.btn.dash` with `aria-pressed`, as Overturn (`buildRuling`). Not pressed on load. No Keep button: keeping is doing nothing, and a Keep beside Overrule would be a pick the page offers for the owner.
- Press: the card takes the accent ring, and the foot swaps "Recorded in" for "Ready to send: overrule." in the same cell, so nothing moves. The bar reads "1 ready (1 overrule)". A second press clears it.
- Undo: a second press before Send; "Undo send" for 8 seconds after Send; then Change on the receipt until the writer routes it. All three exist today; no new undo control.
- Name: the owner's five items and the brief say Overrule; arbiter rulings say Overturn. One act, two names, against house rule ux-one-plain-name.
  Option "Overrule everywhere" (`#n=overrule`): rename Overturn on rulings too. Option "Overturn everywhere" (`#n=overturn`): this button says Overturn. Keeping both names is not drawn: it fails the house rule.
- Departs from: page.html `buildRuling` — the button and the "Each stands unless you overturn it." line say Overrule (under the pick).
- Departs from: the five taken items' options — the Keep option is not drawn; a kept pick reads from `lastAnswer`.
- Pick: Overrule everywhere. Owner grant: yes.

## 6. What Overrule does to the item

- Send writes `answers/<id>` with `choice: "overrule"`, a reserved key like `overturn` and `none` (page.html `OVERTURN`, `choiceText`, `receipt`).
- Option "reopen in place" (pick): the item's `owner` session reopens it as step 5 of "Route and close" does for an overturn: `status` open, `added` now, a new `recommended` and `why`, the earlier options again, and a first `context` line "<role> took <what>; you overruled it at <time>." The card leaves the area and shows in its tier.
  Gain: one route, already built for rulings. Lose: the area keeps no trace; the record keeps it.
- Option "keep the card, open a new item": the taken card stays with "You overruled it <time>. Your question is open again as No. N in Whenever." Gain: a trace on the page. Lose: two items for one question, and a second route.
- Both routes are drawn after the writer acts: `#s=routed&r=reopen` and `#s=routed&r=keep`.
- Departs from: skill waiting-page "Route and close" step 5 and page.html `OVERTURN` — a second reserved choice key, `overrule`, routed like an overturn.
- Sent state (`#s=overruled`): the answered style, "Answered, filing pending <time>", "You overruled it." with Change, and "Next: the <role> reopens this as a question in its tier, with your earlier options, and the card leaves this list."
- `page_grant.py` rule 4 refuses an answer on a closed item that is not an arbiter ruling or a routed close, so it needs a taken branch, as for `overturn`.
- Pick: reopen in place. Owner grant: yes (a new choice key and a route step in skill waiting-page).

## 7. Taken items leave Answered

- Today 791 shows as an Answered line, and the other four hide behind "Show 4 read items" (`dismissed` set). So the owner sees one of five.
- A taken item draws only in this area, never as an Answered line: `isClosedLine` and `answeredEl` skip it, as they skip a ruling. The area ignores `dismissed`.
- Departs from: page.html `isClosedLine` and `readItemsEls` — a closed item with `taken` is no line, and Mark read does not hide it.
- Pick: as drawn.

## 8. Empty area

- Option "show it" (`#s=empty`, pick): the head with count 0 and one sentence: "No session has taken a pick for you. When one does, it shows here, and you can overrule it." Gain: the owner sees the area exists, the question he asked on Nov 18. Lose: one more head on the page.
  Departs from house rule ux-unknown-is-not-empty: no control can fill the area, since only a session takes a pick.
- Departs from: page.html `sectionEl` and `renderList` — they draw a section only with items in it; this area draws with none.
- Option "hide it" (`#s=empty&e=none`), as Answered and Arbiter rulings hide today: no section and no rail row. Gain: a shorter page. Lose: the owner cannot tell "no picks" from "no area".
- A failed load shows the page's own load error, never this sentence.
- Pick: show it.

## 9. Counts

- A taken item is not open: it is not in "N stays open", the Questions tab count, or "of N sent". A pressed Overrule counts in the bar's "ready" only, as an overturn does.

## For the builder and writer (reported, not built)

- page.html: `taken` in `itemFields`; the `items` filter keeps a closed item with `taken`; a `takenEl` section on `sectionEl`; `OVERRULE` beside `OVERTURN` in `draftReady`, `readyText`, `receipt`, `choiceText` and the Undo notice; skip taken items in `isClosedLine`.
- skill waiting-page: the `taken` field, the `overrule` answer and its route; `page_grant.py` rule 4 and 6.
- The writer: backfill `taken` and the shorter titles on the five items.
- Export check (step note): fail when an item has `taken` and the export draws no `tier-taken`.

# Waiting page, lane page-lane-answered-sinks: design notes

Mockup: `docs/design/lane-answered-sink.html`. Screen: `skills/waiting-page/page.html` (8cfba982, PR #1345 page-reply-uncollapse).
Deep links: `#s=page|unfold|change|today|wait-in-pill|owed-lane-words`, `&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`,
`&hide=<state>,...`. `#s=today` draws the base for comparison.
Sizes: phone 390, mid 800 and wide 1280, light and dark. `layout.py devices` prints `unknown` for this repo, so the sizes
come from the brief and page.html's breakpoints at 520 and 960. The mockup draws with page.html's own `<style>` (lines 8 to
850 at 8cfba982). The picked design adds no CSS. Only option "Wait in the pill" adds three rules, each on page tokens.
Options are named by name, never by a letter.

Each state draws five cases. No. 52 is like page item 289: `lane`, `lastAnswer` at the last Send, `reply`, no `replied`,
no `answers/<id>`, no `waits`. No. 47 is routed to the `batch-runner` tier and has a new reply. No. 49 was re-asked on its
lane (`added` later than `lastAnswer.at`). No. 44 waits on a PR (`waits.pr`). No. 40 has a saved answer and is filed.

Settled by the brief, not options here:
- A new reply (`replied` later than the last Send and the visit) or a `waits` change reopens a card in place and marks it (#1345).
- An owed card never folds. Change on a sunk card reopens it in place, its fold locked by the draft.

## 1. Which items sink. Owner grant: yes

- What: one predicate, in its one home. `answeredByWait` (page.html line 1158) also counts an item with `lane` and
  `lastAnswer` when `lastAnswer.at` is at or after `added`. `freezeSeen`, `freezeSunk`, `isByWait`, `sentOf` and every
  count (tier count, Questions count, "N of M sent", the bar) already read it, so No. 52 and No. 47 sink with no other change.
- Why `at >= added`: the busy-lane path never sets `added` (SKILL.md "Busy-lane path"). A re-ask (Route and close, step 3)
  writes a later `added`, so No. 49 stays open in its tier. `stale_pages.py` already reports `lane` + `lastAnswer` as a
  waiting lane line (SKILL.md "Keep the page on main's code", step 2).
- Missing or bad `added`: the item counts as answered. Gain: a writer that drops `added` cannot pin a routed card open.
  Loss: none seen; a re-ask always writes `added`.
- Builder: a plain `ts(lastAnswer.at) >= ts(added)` is false when either side is NaN, so a bad `added` would keep the card
  open. Test a valid `added` first: no valid `added` counts as answered. A `lastAnswer` with no valid `at` does not count
  (`lastOf` alone is not enough here); such an item stays open, as today.
- Gain: an answered item that only waits on a lane leaves the open tiers, as the owner asked (page item 289, Nov 6 15:29 CST).
- Departs from: page.html `answeredByWait` (`waits` and `lastAnswer` only) and SKILL.md item schema ("with `waits` and
  `lastAnswer` reads as answered on the page"). Both need the builder's rewrite.

## 2. The submitted words on a routed card

- Pick (`#s=page`): today's wait-answered shape, unchanged. The green ring pill reads "Sent Nov 6, 13:59 CST". Then the
  top row's `.onlane` span reads "waits on lane stale-page-sweep" (page.html line 1621). A PR card (No. 44) has the same
  shape, with the span "waits on PR #1345" as a link. Gain: "Sent" says it was submitted, the word on the Send button.
  "Answered" shows once, in the section head. "waits on" shows once per card. No new part. Loss: "Sent" repeats on each
  wait-answered card and in the sub-head ("Sent before this visit"), as "Filing pending" does (answered-sink-notes point 2).
  `label_once.py` passes it only because the time follows the word. Not drawn: the ring and the time alone, the word in a
  `.sr` span.
- Option "Wait in the pill" (`#s=wait-in-pill`): one pill, "Sent Nov 6, 13:59 CST, waits on lane stale-page-sweep".
  Gain: one unit reads "submitted, and what it waits on". Loss: the pill wraps to two lines at 390 with a long slug.
  A PR link inside a status pill reads as part of the pill. It adds three CSS rules.
- Not sunk (an item routed while the page is open): today's pill reads "Answered, Sent <time>". It stays in its tier until
  the next load (`freezeSunk`, ux-order-holds-still).
- Slug: drawn as a proper branch slug. Page item 289's live `lane` holds a session id and a sentence. That is a writer data
  defect, outside this design.

## 3. The rail chip

- Pick: the sent ring (`.nchip.sent`), in the Answered rail row. Its accessible name is "No. 52, <title>, answered, waits on
  lane stale-page-sweep". A card with both reads "... waits on lane <slug> and PR #<n>". "answered" stays in the name: a
  screen reader that tabs to the chip does not hear the row head. A ready draft after Change turns the chip to ready.
- Builder: one home for the wait words (`waitSay` in the mockup) serves the top row and the chip.

## 4. A routed card with a new reply (No. 47)

- `#s=page`: No. 47 sinks, then opens in place at load ("Hide the reply") and takes the reply mark (the dot: No. 49 above
  carries the words). This is #1345's rule. Nothing new. Fold words for a card answered by its lane follow page.html line
  1633: "your note" (from `lastAnswer.note`) and "the reply", never "your last answer".

## 5. A re-asked lane item (No. 49)

- `#s=page`: open in Blocking, new (added after the last Send), with "New reply", the thread "Your last answer" and the
  reply, and the new options. Its top row keeps "waits on lane ci-cache-split", as today.
- Option "Owed lane card names who waits" (`#s=owed-lane-words`): on an owed card only, the span reads "lane ci-cache-split
  waits on your answer". Gain: the top row no longer reads as if the item is not on the owner. Loss: one more wording;
  the stake line may already say what waits.

## 6. Change on a routed card

- `#s=change` (or press Change on No. 52 in any frame): the card stays in Answered, open, its fold locked ("Stays open:
  your answer is ready"), the old answer as the draft. The thread shows "Your last answer" again. That is today's Change
  on a sunk card, and the brief keeps it.

## 7. Risks for the builder

- Withdrawn gap. The busy-lane path keeps `answers/<id>`. A Withdraw deletes it, but `lane` and `lastAnswer` stay until the
  owning session's next re-read drops `lane`. With point 1, that item still counts as answered: the card says "Sent" for an
  answer the owner withdrew (ux-statements-are-true). On the open page it may even draw answered again right after Withdraw.
  Fix, page side: remember a Withdraw for the visit and treat the item as open. The reload gap stays.
  Departs from: today's Withdraw, where a lane item reopens at once. Owner grant: yes.
- `lane` and `waits` together: the span stays "waits on lane <slug> and PR #<n>" (page.html line 1619).
- A lane item with `answers/<id>` kept (the busy-lane path) is already sunk today, as "Filing pending, sent <time>" or
  "Filed in <home> <time>", with "waits on lane <slug>". Point 1 does not change it. The two looks differ only in the pill.

## 8. Outside this folder, for the builder

- page.html line 1961, the chip's accessible name, calls `waitWords(waitsOf(it))`. Once `isByWait` admits a lane-only item,
  `waitsOf` is null and the call throws. It must read the lane.
- page.html line 1612: the not-sunk pill reads "Answered, Sent <time>". The capital S after the comma is a typo against
  "Answered, filing pending". Suggest "Answered, sent <time>".
- SKILL.md item schema (`lane`, and the sentence about `waits` and `lastAnswer`) needs point 1.

## Checked

- Playwright, Chromium: all 6 states at 390, 800 and 1280, light and dark (36 runs). No script error, no sideways scroll in
  the frame. Focus ids `item-52`, `item-49`, `item-47` and `item-44` each find a box.
- `label_once.py` on the 6 states at 390: no hit.
- impeccable detector: no finding. It reads the page markup only, not the screen in the script.

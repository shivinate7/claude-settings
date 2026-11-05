# Waiting page, lane page-item-waits-on: design notes

Mockup: `docs/design/page-item-waits.html`. Screen: `skills/waiting-page/page.html` (main 0497265b). Designer kind: informed.
Deep links: `#s=page|unfolded|other-repo|run-plain|run-id|both-joined|both-two|pill-ring|pill-tick|change-keep|change-none`,
`&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`, `&hide=<state>,...`. Each option state has a Hide control.
The mockup draws with page.html's own `<style>` (lines 8 to 834 at 0497265b), plus the new rules in `#newcss`.
The sample is modelled on a real case: an answered item that the writer reopened to wait on main's browser
run, with its answer record deleted and `lastAnswer` kept. Every figure on the page is made up, in the same shape.

## Sizes and themes

- `lint/layout.py devices` prints `unknown` for this repo, so the mockup draws page.html's own widths, as
  last-answer.html did: phone 390, mid 800, wide 1280. The check also opens 480. Themes: light and dark.
- Checked headless (Playwright, Chrome): 11 states, 4 widths, 2 themes. No horizontal scroll in any frame
  or in the harness at 390; each focus id is found; each wait link is at least 24 px. `lint/label_once.py`
  prints nothing for each state.

## The new field, as drawn

- `waits` = `{repo, run}` or `{repo, pr}`. `repo` is `owner/name`; `run` and `pr` are positive integers.
  Any other value reads as no wait (`waitsOf` in the mockup), so a bad value never draws a broken link.
- Answered by its wait: `waits` and `lastAnswer` both set, and no `answers/<id>` record. Such an item sinks
  into the Answered section at load, folds like the other answered cards, and sorts by `lastAnswer.at`.
- `waits` with no `lastAnswer` (No. 218 in the mockup): an owner ask in its tier, as ruled for this lane.
  The top-row span is its only change. Its rail chip stays open: "No. n, title, open".

## 1. Copy for a run

- Plain words (pick), `#s=run-plain`: the link reads "waits on a CI run". The run id lives in the link's
  `href` only. Gain: ux-machine-text-hidden holds; a bare 11-digit id is machine text, and the owner never
  names a run by it. "CI run" is the glossary's word. Loss: two items that wait on two runs read the same
  until the owner opens a link.
- Run id, `#s=run-id`: "waits on run 48213907765", the brief's copy. Gain: the owner can tell runs apart
  at a glance. Loss: a machine id on the screen, against ux-machine-text-hidden.
- Departs from: the brief's suggested "waits on run <id>". The rule above argues against it.
- PR: "waits on PR #2087" in both options. A PR number is the name the owner uses for a PR, so it is not
  machine text.
- Another repo, `#s=other-repo`: "waits on a CI run in sample-api" (the short name after the slash).

## 2. An item with both `lane` and `waits`

- One span (pick), `#s=both-joined`: "waits on lane cache-split and PR #2087"; only "PR #2087" is the link.
  Gain: one "waits on" in the row; it reads as one sentence. Loss: the link is a short target inside a
  longer span (still 24 px tall, 44 px on touch).
- Two spans, `#s=both-two`: "waits on lane cache-split" then "waits on PR #2087". Gain: the builder appends
  one span after the lane span, no join logic. Loss: "waits on" twice in one row; at 390 each takes a line.

## 3. The badge on an item answered by its wait

There is no answer record and no receipt, so the badge reads only `lastAnswer.at`.
- Ring (pick), `#s=pill-ring`: "Sent Nov 4, 08:31 CST" with the ring of a pending answer. Rail chip: `nchip sent`,
  the ring. Gain: true: the owner sent it, and the item is not closed. Loss: looks like "filing pending" at
  a glance; the wait span says why.
- Tick, `#s=pill-tick`: the same words with the filled tick of a filed answer; rail chip `nchip sent filed`.
  Gain: says "nothing left for you". Loss: the page has no receipt that says it was filed, so the tick would
  claim what the page cannot read (ux-statements-are-true).
- The word "Answered" stays out of the pill: the section head carries it, as for the other sunk pills.
  "Sent" and the time are one text run, so the word never stands alone (ux-label-once).
- Rail chip `aria-label`: "No. 212, Pick when the browser fix merges, answered, waits on a CI run"
  (and "..., answered, waits on PR #2087"). The chip's look is the ring, as above.

## 4. The answer line and Change

The card draws the receipt shape from `lastAnswer`: the done glyph and "You chose A: <label>.".
The fold holds the rest, named by its parts: "Show your note and the reply", or "Show the reply".
The last-answer panel ("Your last answer, ...") is not drawn again inside the fold: it would repeat the line.
- Change kept (pick), `#s=change-keep`: Change opens the card with `lastAnswer` as the draft, as Change does with
  a saved answer. Gain: the owner can answer again while the item waits, say if the run fails. One act keeps
  one name. Loss: a new Send writes `answers/<id>`, which the writer must read even though it closed the ask.
- No Change, `#s=change-none`. Gain: no new answer while the item waits. Loss: the owner must ask in chat to
  change it; this card would differ from every other answered card.

## 5. Points for the builder

- `itemFields` (page.html line 895) gains `waits`, or the card shows the unknown-field warning.
- Each of these reads `state.answers` and must also count an item answered by its wait:
  `freezeSunk` (the sunk set), `sorted` (`sentAt`: use `lastAnswer.at`), `answeredEl` (`stamps`),
  `renderRail` (`sent` and the chip), `buildCard` (`saved`, the pill and the receipt), the tier and tab counts
  that use `isSaved`. `receipt()` calls `savedOf`, which is undefined here: build the line from
  `savedOf(it) || lastOf(it)`, and the sunk fold drops `lastAnswerEl` for this case.
- The page has no repo slug: `meta.identity.name` is a display name. To drop the repo when it is the page's
  own, `meta/page` needs the repo's `owner/name`. Until then, show " in <name>" always, or never.
- The link uses `linkEl`'s pattern: an aria-hidden arrow and ", opens in a new tab" for a screen reader.
  New CSS is in `#newcss`, labelled. `.onlane.waits` extends `.onlane` (ux-variant-extends-home).
- The page cannot read whether the run or PR has ended. The span says only what the writer set; the writer
  clears `waits` and closes the item when the work ends.

No item changes a spec or a ruling, so no item needs the owner's grant.

# Waiting page, lane pwr-wakes-on-card: design notes

Mockup: `docs/design/wakes-on-card.html`. Screen: `skills/waiting-page/page.html` (2f738dabf, the head of
pwr-item-names-wakers-b). Designer kind: informed.
Deep links: `#s=page|count|open|ids|top-row|place-dest|muted|accent|bad-say|bad-none`, `&w=all|390|480|800|1280`,
`&t=light|dark`, `&lab=off`, `&hide=<state>,...`. `page` draws the picks together, and `open` draws the same with
each disclosure opened, to show the ids. Each option has its own state and its own Hide control. The mockup draws
with page.html's own `<style>` at 2f738dabf, plus the new rules in `#newcss`.

| Item | Option | State | Focus id |
|---|---|---|---|
| 1 | Count, ids in a closed disclosure (lane pick) | `#s=count` | `wakes-12` |
| 1 | Ids on screen (departs) | `#s=ids` | `wakes-12` |
| 2 | Top row (pick) | `#s=top-row` | `wakes-12` |
| 2 | Beside "Lands in" | `#s=place-dest` | `wakes-12` |
| 3 | Muted text (pick) | `#s=muted` | `wakes-12` |
| 3 | Lane weight and colour | `#s=accent` | `wakes-12` |
| 4 | Say so (pick) | `#s=bad-say` | `item-16` |
| 4 | Draw nothing | `#s=bad-none` | `item-16` |

`#s=open` is a view of item 1's pick, not an option; its focus is the disclosure, `wk-12`.

## Sizes and themes

- Phone 390 and 480, mid 800, wide 1280; light and dark. `data-theme` on the root sets one;
  `prefers-color-scheme` sets the default.
- Checked headless (Chrome through Playwright): 10 states, widths 390, 480, 800 and 1280, 2 themes, 80 frames.
  Each frame is checked with its disclosures closed and again with each one opened. No horizontal scroll, and no
  `.top`, `.dest`, `.card`, `.wk` or id line wider than its box. Each disclosure starts closed (outside `#s=open`).
  Each focus id is found. No. 15 (no `wakes`) draws no span and no disclosure. The not-valid card draws no
  disclosure. No `session_` text is in a top row or dest line outside `#s=ids`. `lint/label_once.py` prints
  nothing for each frame. `impeccable detect`: no finding.

## The field, as drawn

- `wakes`: a list of session ids (SKILL.md, waiting-page, the items fields). Absent or `null`: the owner
  alone, and the card draws nothing (No. 15 in the mockup).
- A valid list: each entry a whole `session_[A-Za-z0-9_-]+`, and at least one entry. Anything else (`[]`, a
  string, a bad entry) is not valid: the writer wakes nobody and asks the `owner` to fix it.
- The disclosure lists the ids as written, in the stored order. It never drops or reorders an entry. An id that
  is the owner's own session lists like any other id: the page cannot tell which id is the owner's.

## 1. Plain words in the top row, ids behind a disclosure

- Count, ids in a closed disclosure (lane pick, 2026-11-13; reversible), `#s=count`. The top row says
  "your answer wakes 2 sessions". Beside it, a closed disclosure "Which sessions" lists the ids. Gain: the row
  reads in the owner's words, and follows house guidance `ux-machine-text-hidden` (an id shows only in a closed
  disclosure). The ids are one press away on every device, touch too. Loss: one press to see which sessions; on
  a card with `wakes`, the 44px summary makes the top row about 22px taller.
  The disclosure is the only new press. It never opens on its own, and Send is unchanged.
- Ids on screen, `#s=ids`: "your answer wakes session_01KM... and session_01KM...", with no disclosure.
  Gain: no press to see the ids. Loss: about 30 characters of machine text per id in the top row, and two ids
  wrap to three lines above the title at 390.
  Departs from: `ux-machine-text-hidden`. Not the pick. Hide it with "Hide Ids on screen".
- Withdrawn: the first mockup's count option kept the ids in a hover `title`. A touch screen has no hover, so
  that title is gone.

## 2. Where it shows

- Top row (pick), `#s=top-row`: the words and the disclosure are two runs in `.top`, after the lane and wait
  span. Gain: `buildCard` builds the top row before both early returns (a receipt card, and a sunk answered
  card), so one code site draws both on every card form. Opened, the disclosure takes the whole row, so the
  ids list under the words. Loss: the top row grows to the 44px summary.
- Beside "Lands in", `#s=place-dest`: "Your answer wakes 2 sessions." as a second sentence in the `.dest` line,
  and the disclosure under that line. Gain: it sits with where the answer goes, at the foot of the card. Loss: a
  receipt card and a sunk card have no `.dest` line, so it needs a second code site, or it is gone once the
  owner has answered.

## 3. Weight and colour

- The top row's own muted text (pick), `#s=muted`. Gain: it reads as a fact about the answer, below the
  title in rank. Loss: it is quieter than "waits on lane", which sits beside it.
- The lane's weight and accent (`.onlane`), `#s=accent`. Gain: the brief's "same style as the lane line".
  Loss: `.onlane` is bold accent because it says the item waits on something. `wakes` does not hold the
  owner up, and the count would then sit as loud as the "Which sessions" summary beside it.
- Departs from: the brief's "same style as the lane line" in the weight only. The place (top row) and the
  form (one plain lower-case text run) are the lane's. The summary keeps `.cmd-more`'s accent in both options.

## 4. A wake list that is not valid

- Say so (pick), `#s=bad-say`: "wake list not valid: triage is asked to fix it when you answer" (the
  item's `owner`). No disclosure: there is no valid id to list, and the line names no id. Gain: with nothing
  drawn, the owner reads "absent: my answer wakes the session that asked", which is false; the writer wakes
  nobody. The line keeps the page true (`ux-statements-are-true`). Loss: a muted line about a defect the owner
  cannot fix himself.
- Draw nothing, `#s=bad-none`. Gain: the card looks as today. Loss: the card looks like an item with no
  `wakes`, and the owner's Send silently wakes nobody until the writer's ask lands.
- Not the field warning (`unknownFields`): `wakes` is a listed field with a bad value, not an unlisted field.

## 5. For the builder (page.html, by symbol at 2f738dabf)

- `#itemFields`: add `"wakes"` in the same change that draws it. Today the block lacks it, so the guard
  refuses a write that names `wakes`.
- Record edit: decision item-field-rendered (a waiting item names only fields the page renders) lists the
  fields the page draws in its line "The fields `reply`, `lastAnswer` and `lane` are listed". Add `wakes` to
  that list, citing this notes file, in the same change. This is a record edit for the builder, not the designer.
- Beside `laneOf`: add `SESSION_ID` and `wakesOf(it)`. `wakesOf` returns `null` for absent or `null`; `"bad"`
  unless a non-empty list whose each entry is a string that `SESSION_ID` matches; else the list.
- The shape: the one home is `hooks/own_session.py` `_CREATED_ID`, which `stale_pages.py` imports. The page
  is JavaScript and cannot import it, so the page holds one copy:
  `const SESSION_ID = /^session_[A-Za-z0-9_-]+$/;`. Add a test that reads that line out of page.html and
  checks that its source equals `"^" + _CREATED_ID.pattern + "$"` (`_CREATED_ID` is unanchored, as `search` uses
  it). Show it red first on a changed copy. That is the duplicate's stated reason
  (`building-allow-list-is-the-constant`).
- `buildCard`: right after the lane and wait block (the three `top.append` lines that start
  `if (lane && wt)`), when `wakesOf(it)` is a list, append two runs:
  `h("span", { class: "onwakes", id: "wakes-" + it.id }, words)` and
  `h("details", { class: "cmd-more wk", id: "wk-" + it.id }, h("summary", {}, which), h("ul", { class: "wk-ids" }, ids.map((x) => h("li", {}, x))))`.
  When it is `"bad"`, append the span with the not-valid copy and no `details`. Never set `open`.
- `buildRuling`: its top row draws the same two runs after the `ruled` span, or after the Answered pill on a
  saved ruling. An Overturn wakes the same sessions. Not drawn in the mockup.
- CSS, after the `.onlane` rules, all on page tokens, no new token:
  `.onwakes { min-width: 0; overflow-wrap: anywhere; }`,
  `.top > .wk { min-width: 0; }`, `.top > .wk[open] { flex-basis: 100%; padding-bottom: 4px; }`,
  `.wk-ids { margin: 0; padding: 0; list-style: none; display: grid; gap: 4px; font: 13.5px/1.5 var(--mono); color: var(--ink); }`,
  `.wk-ids li { min-width: 0; overflow-wrap: anywhere; }`.
  The summary takes `.cmd-more > summary` as it is (accent, 600, 14.5px, 44px).
- No other new press, no change to Send, the ready line, the rail or the fold.

## 6. Copy

- Top row, `words`: "your answer wakes 1 session" for one id; "your answer wakes <n> sessions" for two or more.
  The count word is the list's length as a numeral (`wakes.length`), never spelled out, never capped. Lower case,
  as the other top-row runs ("waited 2 days", "waits on lane x").
- Summary, `which`: "Which session" for one id; "Which sessions" for two or more.
- Disclosure body: one `li` per id, the id as written, nothing else.
- Not valid: "wake list not valid: <owner> is asked to fix it when you answer". Unchanged.
- Beside "Lands in" option only: "Your answer wakes 1 session." / "Your answer wakes <n> sessions."
- Ids on screen option only: "your answer wakes <a>", "<a> and <b>", "<a>, <b> and <c>".
- A long id breaks anywhere in the list (`overflow-wrap: anywhere`). Checked at 390 with a 58-character id.

## 7. Critique (impeccable, single context: no sub-agent tool)

- The ids are opaque once opened: the owner knows sessions as triage or coordinator, not by id. Outside this
  scope: the writer could store a plain name beside each id. Recorded, not fixed.
- The summary shows no open or closed mark. That is page.html's own `.cmd-more` look ("Which fields",
  "Show the command"); a change there is outside this lane. Recorded, not fixed.
- The 44px summary makes the top row taller on a card with `wakes`. Kept: it is the a11y floor's tap size, the
  same as every `.cmd-more` summary.
- Fixed: opened, the id list sat tight against the title; it now has 4px below it.
- Fixed in this round: the ids left the top row, so a screen reader reads them only when the owner opens the
  disclosure, and the three-line wrap at 390 is gone.
- Detector (`impeccable detect`): no finding. It reads the harness markup only; the cards are drawn by script.

Questions from the critique, not blocking:
- Should the writer store a plain session name beside each id (triage, coordinator), so the list reads in
  the owner's words? That is a change to the item fields, outside this lane.
- Should a ruling card show the line too (item 5 says yes; not drawn)?

No item needs an owner grant. Item 1's pick follows the house guidance; item 3 departs from the brief's wording
in weight only.

# Waiting page, lane pwr-wakes-on-card: design notes

Mockup: `docs/design/wakes-on-card.html`. Screen: `skills/waiting-page/page.html` (2f738dabf, the head of
pwr-item-names-wakers-b). Designer kind: informed.
Deep links: `#s=page|ids|count|top-row|place-dest|muted|accent|bad-say|bad-none`, `&w=all|390|800|1280`,
`&t=light|dark`, `&lab=off`, `&hide=<state>,...`. `page` draws the picks together. Each option has its own
state and its own Hide control. The mockup draws with page.html's own `<style>` at 2f738dabf, plus the new
rules in `#newcss`.

| Item | Option | State | Focus id |
|---|---|---|---|
| 1 | Ids on screen (pick) | `#s=ids` | `wakes-12` |
| 1 | Count | `#s=count` | `wakes-12` |
| 2 | Top row (pick) | `#s=top-row` | `wakes-12` |
| 2 | Beside "Lands in" | `#s=place-dest` | `wakes-12` |
| 3 | Muted text (pick) | `#s=muted` | `wakes-12` |
| 3 | Lane weight and colour | `#s=accent` | `wakes-12` |
| 4 | Say so (pick) | `#s=bad-say` | `item-16` |
| 4 | Draw nothing | `#s=bad-none` | `item-16` |

## Sizes and themes

- The same set as `last-answer-notes.md`: phone 390, mid 800, wide 1280; light and dark. `data-theme` on
  the root sets one; `prefers-color-scheme` sets the default.
- Checked headless (Chrome through Playwright): 9 states, widths 390, 480, 800 and 1280, 2 themes. No
  horizontal scroll in any frame, and no `.top`, `.dest` or `.card` wider than its box. Each focus id is
  found, and No. 15 (no `wakes`) draws no span. `lint/label_once.py` prints nothing for each state.

## The field, as drawn

- `wakes`: a list of session ids (SKILL.md, waiting-page, the items fields). Absent or `null`: the owner
  alone, and the card draws nothing (No. 15 in the mockup).
- A valid list: each entry a whole `session_[A-Za-z0-9_-]+`, and at least one entry. Anything else (`[]`, a
  string, a bad entry) is not valid: the writer wakes nobody and asks the `owner` to fix it.
- The page shows the ids as written, in the stored order. It never drops or reorders an entry. An id that
  is the owner's own session shows like any other id: the page cannot tell which id is the owner's.

## 1. Ids on screen, or a count

- Ids (pick), `#s=ids`: "your answer wakes session_01KM4QW8ZT3VH9RB2NXC and session_01KM7FD2PA5YJ0SG6TLE".
  Gain: the owner sees exactly which sessions his Send wakes, and can match an id with a session list. It is
  the brief's copy. Loss: about 30 characters of machine text per id. This departs from house guidance
  `ux-machine-text-hidden` (an id shows only in a closed disclosure), as `c190-task-command-notes.md` item 1
  did. Owner grant: yes. Not blocking.
- Count, `#s=count`: "your answer wakes 2 sessions", with the ids in the span's `title`. Gain: it keeps
  the guidance, and the row stays one line. Loss: a touch screen has no hover, so the ids are not reachable
  there; and a closed disclosure would add a press, which the brief rules out.
  Departs from: the brief's suggested `Wakes: <id>, <id>`.

## 2. Where it shows

- Top row (pick), `#s=top-row`: one span in `.top`, after the lane and wait span. Gain: `buildCard` builds the
  top row before both early returns (a receipt card, and a sunk answered card), so one code site draws it on
  every card form. On a wide screen it adds no height. Loss: at 390 two ids wrap to two or three short lines
  in the top row, above the title.
- Beside "Lands in", `#s=place-dest`: "Your answer wakes ..." as a second sentence in the `.dest` line.
  Gain: it sits with where the answer goes, at the foot of the card. Loss: a receipt card and a sunk card
  have no `.dest` line, so it needs a second code site, or it is gone once the owner has answered.

## 3. Weight and colour

- The top row's own muted text (pick), `#s=muted`. Gain: it reads as a fact about the answer, below the
  title in rank. Loss: it is quieter than "waits on lane", which sits beside it.
- The lane's weight and accent (`.onlane`), `#s=accent`. Gain: the brief's "same style as the lane line".
  Loss: `.onlane` is bold accent because it says the item waits on something. `wakes` does not hold the
  owner up, and two bold ids are the loudest text in the top row.
- Departs from: the brief's "same style as the lane line" in the weight only. The place (top row) and the
  form (one plain lower-case text run) are the lane's.

## 4. A wake list that is not valid

- Say so (pick), `#s=bad-say`: "wake list not valid: triage is asked to fix it when you answer" (the
  item's `owner`). Gain: with nothing drawn, the owner reads "absent: my answer wakes the session that
  asked", which is false; the writer wakes nobody. The line keeps the page true (`ux-statements-are-true`).
  Loss: a muted line about a defect the owner cannot fix himself.
- Draw nothing, `#s=bad-none`. Gain: the card looks as today. Loss: the card looks like an item with no
  `wakes`, and the owner's Send silently wakes nobody until the writer's ask lands.
- Not the field warning (`unknownFields`): `wakes` is a listed field with a bad value, not an unlisted field.

## 5. For the builder (page.html, by symbol at 2f738dabf)

- `#itemFields`: add `"wakes"` in the same change that draws it (decision item-field-rendered, a field is
  listed only when drawn). Today the block lacks it, so the guard refuses a write that names `wakes`.
- Beside `laneOf`: add `wakesOf(it)`: `null` for absent or `null`; `"bad"` unless a non-empty list whose each
  entry is a string that matches the session id shape whole; else the list.
- The shape: the one home is `hooks/own_session.py` `_CREATED_ID`, which `stale_pages.py` imports. The page
  is JavaScript and cannot import it. Pick: one JS constant `SESSION_ID = /^session_[A-Za-z0-9_-]+$/` beside
  `wakesOf`, with a test that reads it out of page.html and compares it with `_CREATED_ID.pattern`
  (`building-allow-list-is-the-constant`). That reason is the duplicate's stated reason.
- `buildCard`: right after the lane and wait block (the three `top.append` lines that start
  `if (lane && wt)`), add one `top.append(h("span", { class: "onwakes", id: "wakes-" + it.id }, text))` when
  `wakesOf(it)` is not `null`, where `text` is the copy below. One text run: never split the ids into child
  elements, or `label_once.py` names "your answer wakes" as a repeated label.
- `buildRuling`: its top row draws the same span after the `ruled` span, or after the Answered pill on a saved
  ruling. An Overturn wakes the same sessions.
  Not drawn in the mockup.
- CSS, after the `.onlane` rules: `.onwakes { min-width: 0; overflow-wrap: anywhere; }`. No colour and no
  weight: it takes the muted 14px of `.top`. No new token.
- No new press, no change to Send, the ready line, the rail or the fold.

## 6. Copy

- One id: "your answer wakes session_01KM...". Two: "your answer wakes <a> and <b>". Three or more:
  "<a>, <b> and <c>". Lower case, as the other top-row runs ("waited 2 days", "waits on lane x").
- Not valid: "wake list not valid: <owner> is asked to fix it when you answer".
- Count option only: "your answer wakes 1 session" / "your answer wakes <n> sessions", `title` the ids
  joined by ", ".
- A long id breaks anywhere (`overflow-wrap: anywhere`), as `.onlane` does. Checked at 390 with a 58-character id.

## 7. Critique (impeccable, single context: no sub-agent tool)

- The ids are opaque: the owner knows sessions as triage or coordinator, not by id. Outside this scope: the
  writer could store a plain name beside each id, or the page could name an id that matches a known session.
  Recorded, not fixed.
- At 390 a two-id span wraps to three lines above the title. Kept: it is the price of item 1's pick; the
  count option avoids it.
- A screen reader reads each id character by character. Unmeasured; no fix in scope.
- Fixed: the first draft set each id in its own mono span, and `label_once.py` named "your answer wakes" three
  times. Now one text run. Fixed: the not-valid copy was two clauses long; now one.
- Detector (`impeccable detect`): no finding. It reads the harness markup only; the cards are drawn by script.

Questions from the critique, not blocking:
- Should the writer store a plain session name beside each id (triage, coordinator), so the line reads in
  the owner's words? That is a change to the item fields, outside this lane.
- Should a ruling card show the line too (item 5 says yes; not drawn)?

Items 1 and 3 depart from house guidance or the brief. Item 1 needs the owner's grant.

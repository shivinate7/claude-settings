# Waiting page, step page-parked-actions: design notes

Mockup: `docs/design/page-parked-actions.html`. Screen: `skills/waiting-page/page.html` (main b313a497),
`renderList` (the `parked` block) and the Send flow (`sendAll`, `undoSend`, `withdrawAll`, `noticeText`).
Deep links: `#s=today|page|staged|sent|pending|routed|gone-6b|legacy|nostore|now-1b|ask-2b|words-3b|note-7b`,
`&w=all|390|1280`, `&t=light|dark`, `&lab=off`, `&hide=<state>,...`. Sizes: phone 390 and wide 1280. Themes: light and dark.
Focus ids: `#parked`, `#pk-line-<key>`, `#pk-acts-<key>`, `#pk-unpark-<key>`, `#pk-drop-<key>`, `#pk-change-<key>`, `#pk-why-<key>`. The key is the entry's `id`, or `_<index>` for a line that is not live (a slug holds no underscore, so no two keys meet, and no key meets a page id such as `pk-h`).

Departs from: `skills/waiting-page/page.html:renderList` — each parked line gets Unpark and Drop, where today it is text only.
Departs from: `skills/waiting-page/SKILL.md` "The database", `meta/page` `parked` — each entry gets an `id`.
Departs from: `skills/waiting-page/SKILL.md` "Route and close" — a new branch for an answer on a parked line.

## 1. A press goes through the Send bar

- 1A (pick): a press stages the act as a draft. The bar counts it ("2 ready (2 on parked lines)"), and Send writes it with the 8-second Undo, as an answer does. Gain: one way to send, one Undo, one place to change your mind. Loss: two presses, not one.
- 1B (`#s=now-1b`): a press saves at once, with its own Undo in the row. Gain: one press. Loss: a second save path and a second Undo timer on one page.
- Counts: a parked act counts in "Send N answers" and in "N ready". It never counts in the rail's "of N sent" or in "N stay open", which count items only. The builder subtracts park acts from `staged()` where it computes `left`.

## 2. Drop's confirm

- 2A (pick): the staged state is the confirm. Drop struck the line (a shape, not a colour) and shows "✓ Drop". Nothing is written until Send, and Undo covers 8 seconds after it. Gain: meets `ux-ask-or-undo` (Undo, not both). Loss: no "are you sure" step for a person who expects one.
- 2B (`#s=ask-2b`): the row asks "Drop this line for good?" with Cancel focused. Loss: with Send and Undo it does both, so it fails `ux-ask-or-undo`. On a phone the ask wraps and moves the line below it (`ux-press-moves-nothing`).
- Drop uses no `--holds` red. On this page red means Blocking.

## 3. Button look and wording

- 3A (pick): "Unpark" (`.btn.alt.pkb`) and "Drop" (`.btn.dash.pkb`). Each is a toggle with `aria-pressed`. Pressed: "✓ Unpark" on an accent fill, "✓ Drop" with a solid ink edge. The two labels share one grid cell, as in `.cmd-copy`, so a press moves nothing. The two toggles on a line cancel each other, and a second press clears. Accessible name: the act and the line ("Drop D41, a count of filed answers on the rail").
- Hint under the heading: "Unpark puts a line back in the work. Drop ends it. Each waits for Send, as an answer does."
- 3B (`#s=words-3b`): "Bring back" and "Drop for good". Gain: plainer. Loss: wider buttons, and "park" is the word the list already uses.
- The heading changes from `<b>` to `<h2 id="pk-h">` with the same look, so a screen reader can find the section.

## 4. The record a press writes

- 4A (pick): `answers/park.<id>`, written by `sendAll`. Fields: `parked: true`, `id` (the parked entry's id), `act` (`unpark` or `drop`), `ref` and `note` (copies, so the writer and the notice can name the line after the list changed), `at` (ISO time). Gain: the writer's fallback read (`ArtifactData list answers`) sees it with no new read. Send, Undo, Withdraw and the draft store work as they are. The page reads `state.answers` by key only (checked: no `Object.keys` or `Object.values` walk), so a non-item key moves no count. Loss: item ids and park keys share one collection. The key holds a dot, which an item id never holds, so the two never meet.
- 4B: a new `parked/<id>` collection. Gain: no shared key space. Loss: a second list read in "Read the answers", and a new listener on the page.
- Owner grant: yes. 4A changes SKILL.md "The database" (`answers/` gains the park shape).

## 5. The key of a parked line

- 5A (pick): each `meta/page` `parked` entry gets `id`, a slug of 32 characters or fewer, unique in the list, set by the writer. Gain: stable when the writer rewrites `ref` (rule `speak-rewrite-superseded-in-place`), and safe as a store key. Loss: a SKILL.md change, and old entries need an id.
- 5B: derive the key from `ref`. Loss: `ref` is prose. A rewrite of its plain name orphans a sent act, and it can hold characters a key cannot.
- An entry with no `id` (`#s=legacy`) shows both buttons off: a solid `--line` edge and muted text, where a live Drop has a dashed `--faint` edge. They stay focusable. The reason is text under the line, tied to both buttons with `aria-describedby`, "The page's writer has not prepared this line yet. Reply in the thread instead." It is not a hover bubble: a phone has no hover, and a bubble clips at the left edge (`ux-control-earns-place`).
- Owner grant: yes. 5A changes SKILL.md "The database" (`parked` is a list of `{id, ref, note}`).

## 6. After the press

- Staged (`#s=staged`): the toggle shows ✓. A Drop strikes the line.
- Sent (`#s=sent`): the line shows the `.ans` badge "Unpark sent 17:42 CST" and Change. The badge shows the time only, so badge and Change fit on one 390px row. Its title gives the day and the writer. "Change" opens the line again. "Undo send" stays in the Sent panel only. The Sent panel lists a parked act by its act ("Unpark", in the `.no` slot) and its ref, cut at 24ch, where an item shows "No. n". Its title is "Goes to triage" (`meta/page.writer`).
- Pending (`#s=pending`): the same badge and Change after the Undo window. Change brings the toggles back. A cleared line then turns Send into "Withdraw answer", as on a card.
- The acts row is one 44px cluster in every state, so no state moves the row. At 600px and wider the acts column is at least 19rem, wider than the sent badge with Change (287px), so no state re-wraps the line text.
- 6A (pick, `#s=routed`): when the writer removes the entry, the line keeps its height with the filled badge "Unparked" or "Dropped" until it is off screen. It uses the same hold as a receipt (`releaseHeld`). Gain: the Ask box below does not jump while you type in it. Loss: the page keeps the last act in memory to draw it.
- 6B (`#s=gone-6b`): the line leaves at once, and all below it moves up.
- Orphan: a record whose entry is gone draws nothing. The writer deletes it at its next read.
- No store (`#s=nostore`): every toggle is off, and each line shows the reason "This view cannot reach the page's store. Reply in the thread instead." under it.

## 7. A note on a line

- 7A (pick): no note box. The Ask box below takes anything longer.
- 7B (`#s=note-7b`): a third button, "Add a note", opens a note box under the line, as on a card. Loss: three buttons on each line, and the lines grow tall on a phone.

## 8. Place on the page

- The block stays where it is today: after "Checked against", at the end of the list column. The Ask box from the other lane comes after it, as the last part of the list, above the Send bar.
- All CSS of this change is under `.parked`. The block is the query container (`container-type: inline-size`). At 600px and wider the acts sit at the right of the line, and below that they wrap under the text.

## 9. For the builder

- Drop's dashed edge uses `--faint`, where `.btn.dash` elsewhere uses `--line`. An off act uses a solid `--line` edge with `--muted` text, so an off Drop never looks like a live one. `--line` on the surface is under the 3:1 control-edge floor in `a11y.md`. "Mark done" and "None of these" have the same gap today. That is outside this step.
- Forced colors: the accent fill of a pressed Unpark goes away. The ✓ in the label stays, so the state still shows.
- Classes: `.parked` (section), `.pk-hint`, `.pk-why`, `.pk-list`, `.pk` (line, `.drop` when staged, sent or filed as a Drop), `.pk-txt` with `.ref` and `.nt`, `.pk-acts`, `.btn.pkb` with `.off` and `.on` label spans, `.sent-list .pkref`.
- Model a park act as a pseudo item `{id: "park." + p.id, park: p, owner: meta.writer}`, so `staged`, `sendAll`, `undoSend`, `withdrawAll` and `saveDraft` take it with no second path. Keep its draft in `waiting.draft` (`ux-keep-what-was-made`).
- `noticeText`: a park act's line is "parked <ref> unpark" or "parked <ref> drop", in place of "<n> <choice>". Its owner is `meta/page.writer`.

## 10. Routing text for SKILL.md "Route and close"

Owner grant: yes (a SKILL.md change; a builder places it).

- Sort first: an answer with `parked: true` goes to the page's writer, not to an item's owner. It takes this branch only.
- Unpark: put the line back in the work. Move it back to its roadmap step, or add a fresh item. Then remove the entry from `meta/page.parked` in one update pinned with `if_version`, and delete `answers/park.<id>`.
- Drop: file the abandon at the home `ref` names (rule `building-land-design-or-abandon`), else ask the owner. Then remove the entry in the same pinned way, and delete the answer.
- No entry with that `id`: delete the answer, and say so in the terminal.
- The page never writes `meta/page`.

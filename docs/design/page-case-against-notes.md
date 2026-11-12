# Waiting page case against the pick, step challenger-page-against part b: design notes

Mockup: `docs/design/page-case-against.html`. Screen: `skills/waiting-page/page.html` at e9ec70ee4, `buildCard`, the
`ctxText` line (`.ctx` CSS at line 134). Its CSS (lines 8–953) is copied whole. Only `#newcss` is new.
Deep links: `#s=case|nocase|long|markup|two|today|above|every|clamp|bare`, `&w=all|390|800|1280`, `&t=light|dark`,
`&lab=off`, `&hide=above,every,clamp,bare,model`.
Sizes: 390, 800 and 1280, the page's bands (`layout.py devices` prints `unknown`). Themes: light and dark.
Part a (draft PR 2938, the Against line rule) makes each open page decision with a pick carry
`Against the pick (sonnet): <case>` in `context`. Today `buildCard` draws `context` whole in `.ctx`, folded past 220
characters, so the case is the last line and hides behind "More context" (state `today`).
Departs from: main draws the Against line as plain context — the card draws it once, as its own block under the options.

## 1. The draw rule (pick), all states

- At draw time `buildCard` splits `it.context` into the lines `.ctx` draws and the cases the block draws. No new item
  field, no writer change. The 220-character fold is measured on what is left, so many cards lose "More context".
- A line is a case when it matches the guard's `CHALLENGED_LINE` (`hooks/question_form.py`): it starts the line, may
  carry a bullet and a bold label, and names a model in parentheses. "Against the pick:" in the middle of a line stays
  in the context (state `markup`). A matched line with no case text stays in the context, so no text is dropped.
- Gain: one read of a field the page has. Loss: the JS regex copies a Python one; the two can drift (see Outside this folder).
- Pick: this rule. Owner grant: no.

## 2. Where the block sits (pick: under the options), states `case` and `above`

- Under the options and the pick's starred box, above the ready line and None of these, as the brief asks. The radio
  group's `aria-describedby` names the block, so a screen reader hears the case at the options.
- Other, `above`: after the context, before the options. Gain: read before the options. Loss: the case argues
  against a pick the owner has not seen yet. Hide: "Hide above the options".
- On a sunk card that the owner is changing, the block goes in the fold with the options (`put`), not beside the context.
- Pick: under. Owner grant: no.

## 3. The look (pick), state `case`

- A variant of `.stake` (`.stake.against`): chip ground, a 1px border, a 4px muted bar at the start. A real border, so it
  holds in forced colours. Not red (`--holds` means Blocking) and not gold (gold means the pick).
- Head: a speech-bubble glyph, "Against the pick", the pick's key chip and label (cut at 28, as `pickName`), the model word.
- The case draws as text (`h()` text nodes; the mockup escapes it). Tags, entities, stars and back-ticks show as typed.
- Pick: this look. Owner grant: no.

## 4. The words once on a screen (pick), states `case` and `every`

- Rule ux-label-once: the first block in page order shows "Against the pick". Each later block shows the glyph, the
  key and the case, with the words for screen readers only. The same home as `REPLY_WORDS` and `replyFirst`.
- Other, `every`: words on every block. Gain: each card reads alone. Loss: `label_once.py` flags it.
- `label_once.py` on the dumped frames: `case` and `two` name "against the pick" twice. The second is the `.sr` copy,
  which no frame shows. Whether `bin/shoot` marks a clipped `.sr` span `hidden` is unknown, so the reviewer judges it
  against the screenshot. "sonnet" twice is data.
- Pick: words once. Owner grant: no.

## 5. A long case (pick: whole), states `long` and `clamp`

- The skill caps a case at 80 words. The block shows it whole: about 10 lines at 390.
- Other, `clamp`: three lines and "Read the whole case". Gain: a short card. Loss: the case hides again, the defect this
  step fixes. Hide: "Hide long case folded".
- Pick: whole. Owner grant: no.

## 6. No case line (pick: one quiet line on an old item), states `nocase` and `bare`

- An open decision that owes a case (a pick, not `stands: true`, not `port`, the guard's `_challenged_judged` test) and
  has none shows one dashed line: "No case against the pick on this item." Rule ux-unknown-is-not-empty: a missing case
  must not read as "nothing against it".
- The test reads the pick the card shows, `pickKeys(it)`, not `it.pick`: the page hides a pick that does not fit the
  item, and a card with no visible pick gets no quiet line. On a multi or ranked item the head names each key of
  `pickKeys`, in its order, not one letter (not drawn).
- A port item and a stood pick owe none (decision question-form), so they show as today.
- Other, `bare`: the old item shows nothing too. Gain: no new line while old items drain. Loss: the owner cannot tell
  "no case written" from "no block". Hide: "Hide old item shows nothing".
- Pick: the quiet line. Owner grant: no.

## 7. Two Against lines (pick: draw both), state `two`

- Step 3 of "Read the answers" writes a fresh line for a new pick. If the old line stays, both draw, in order. Only the
  first head names the pick: the page cannot tell which pick a later line argued against.
- Gain: no text dropped. Loss: a stale case shows. Other: draw the last only (not drawn).
- Pick: both. Owner grant: no.

## 8. The model word (pick: shown), every state

- The model word shows at the end of the head, in mono. Gain: the owner sees an Opus case from a Sonnet one.
  Loss: one more machine word (ux-machine-text-hidden is guidance). Hide: "Hide the model word".
- Pick: shown. Owner grant: no.

## Outside this folder (builder work)

- `skills/waiting-page/page.html`: the split, the block, its CSS and the first-block words, in `buildCard`.
- `skills/waiting-page/SKILL.md`, lines 121 and 308: say the page draws the Against line as its own block.
- A test that runs the page's regex and `CHALLENGED_LINE` on the same lines, so the two cannot drift.

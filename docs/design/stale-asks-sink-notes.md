# Waiting page, step page-stale-asks-sink: design notes

Mockup: `docs/design/stale-asks-sink.html`. Screen: `skills/waiting-page/page.html` (main ea92b0cc).
Deep links: `#s=page|open|draft|focus|all-seen|divider-1b|divider-1c|card-2b|fold-3b|fold-4b|draft-5b`,
`&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`, `&hide=<state>,...`.
Sizes: phone 390 and wide 1280 from the brief. `layout.py devices` gives no device list for this repo.
Mid 800 is drawn too, because page.html has a breakpoint at 960. Light and dark.
The mockup draws with page.html's own `<style>`. It adds no colour: each new rule reads a page token.

Settled behaviour (brief, owner ask Nov 1, 17:16 CST) is not an option here: what "seen" means, the
order in a tier, what folds, no fold on a draft, and `article.card[data-seen="true"]`.

## 1. The divider between new and seen

- 1A (pick): `p.seenhead` sits after the last new card of a tier. It holds an eye icon, the words, then a dotted
  rule: `span.seenrule` (`border-top: 2px dotted var(--faint)`), a span and not `::after`. The first divider on the page shows the words "Asked
  before". Not "not answered": a card answered by a Send stays below the divider until reload. Each later divider shows the eye and the rule only. Its words are in a `.sr`
  span and in `title`. Gain: a screen reader hears the words at every divider, and the page follows
  ux-label-once. Loss: a sighted reader who starts at a lower tier sees the shape before the words.
  Ids: the first divider has `id="seen-div"`.
- 1B: the words show at every divider (`#s=divider-1b`). Gain: no shape to learn. Loss: up to 4 copies
  of one label, which `label_once.py` flags. The owner asked for fewer repeated tier words on Oct 26.
- 1C: no divider (`#s=divider-1c`). Gain: no new element. Loss: the reason for the sink shows only as
  the quieter card and the fold control.
- A tier with no seen item shows no divider and looks as today. A tier with only seen items puts the
  divider under its head (`#s=all-seen`).
- The eye is a new icon on the page, with one meaning: "you saw this". The page uses no eye now.
- Contrast: `--faint` on `--ground` is 5.5:1 in light and 6.0:1 in dark. That passes the 3:1 state-cue floor.

## 2. The seen card

- 2A (pick): `.card[data-seen="true"]:not(.answered)` gets the ruling card's ground,
  `color-mix(in srgb, var(--surface) 55%, var(--ground))`. The tier edge (6px `holds` or `due`) and the
  stake lines stay, because a seen blocking item still blocks. Gain: one known "quiet" look. Loss:
  in light the change is small (#fafafb against #ffffff), so the divider and the fold carry most of it.
  `--muted` on this ground is 6.2:1 in light and 7.7:1 in dark.
- 2B: the seen card on today's ground (`#s=card-2b`). Gain: no new look. Loss: only the divider and
  the fold say "seen".

## 3. The fold control

- 3A (pick): `button.unfold`, full width, in the place of the options or the steps. 48px tall, dashed
  `1.5px var(--faint)` edge, `--surface` ground, `--acc` text at 600. Hover: `--acc` edge, `--acc-soft`
  ground. A chevron (`.chev`, ▸ closed, ▾ open) leads. Gain: a large target, and it shows where the
  options are. Loss: one more boxed shape on the card. Ids: `id="unfold-<id>"`, the item id, like every other per-card id (two items may share a number).
- 3B: a text button, the look of "More context", with a 44px box (`#s=fold-3b`). Gain: small. Loss:
  easy to miss on a long card.
- Words. Decision: "Show the 3 options" and "Hide the options". Task: "Show the 3 steps and the
  command" ("and the 2 commands" with two shells; no "and the ..." with no command) and "Hide the
  steps and the command". One option or step is singular: "Show the 1 option", "Hide the option".
  A task with no steps reads "Show the command" and "Hide the command"; with no command too, "Show
  Mark done and the note" and "Hide Mark done and the note". A hidden `.sr` span adds " for No. <n>", so each name gives the act and its
  item (`a11y.md`).
- Markup: `aria-expanded`, and `aria-controls="fold-<id>"` on `div.foldbody` (not `.fold`: page.html
  uses `.fold` on the roadmap). A closed fold has the `hidden` attribute, so its controls leave the
  tab order. The three labels (`.uf-show`, `.uf-hide`, `.uf-lock`, in `.uf-labels`) share one grid cell, so the button keeps the
  box of its widest label and a press moves nothing beside it (ux-press-moves-nothing). CSS shows the
  label that matches `aria-expanded` and `aria-disabled`.
- Keyboard: the native button. Enter and Space toggle. Focus stays on the button. The ring is the
  page's `:focus-visible` (2px `--acc`, offset 2px) (`#s=focus`). In forced colours, the dashed edge,
  the chevron and the dotted rule are borders and text, so they stay.
- An opened fold stays open until reload, kept like `state.more` (page memory, not stored).

## 4. What sits in the fold

- 4A (pick): every part the owner answers with. Decision: `.opts`, `.multihint`, `.difkey`, the ready
  line, "None of these" and the note box. Task: `ol.steps`, the `.cmd` blocks, `.links`, the ready
  line, "Mark done" and the note box. Outside: top row, title, stake lines, thread, context, ref and
  the `dest` line. Gain: nothing in a closed fold can make a draft, so a card never has to unfold
  while the owner types. Loss: a note needs one press first.
- 4B: only the options or the steps fold; the ready line, the alts row and the note stay
  (`#s=fold-4b`). Gain: a note needs no press. Loss: a note typed in a folded card makes a draft, and
  the rule "no fold on a draft" then opens the card under the owner's typing.

## 5. A seen card with an answer Send would submit

- 5A (pick): the fold control stays, locked open: `aria-disabled="true"`, solid `--line` edge,
  `--muted` text, the words "Stays open: your answer is ready" (`#s=draft`). A pick in an opened fold
  turns the control into this state in place, so nothing moves. A seen pick-stands card shows it from
  the start. Gain: one shape for every seen card, and the control says why it does not close
  (ux-control-earns-place). Loss: one line that is not a control.
- 5B: no control on a card with a draft (`#s=draft-5b`). Gain: less on the card. Loss: when the owner
  picks in an opened fold, the control leaves and the options move up about 60px.

## 6. Rail

- No change to the chip look. The rail reads `sorted()`, so each tier's new chips come first.

## Checked

- Playwright, Chrome: every state at 390, 800 and 1280, light and dark. No script error and no
  horizontal scroll.
- The impeccable detector found nothing. It reads the page markup only, not the screen CSS in the
  text block, so its clean result proves little.

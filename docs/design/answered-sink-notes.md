# Waiting page, step page-answered-sink: design notes

Mockup: `docs/design/answered-sink.html`. Screen: `skills/waiting-page/page.html` (main da8d8073).
Deep links: `#s=page|unfold|change|just-sent|groups|section-folded|below-rulings|note-outside|fold-context|filed-stays|sections-none|sections-repo|sections-kind`,
`&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`, `&hide=<state>,...`.
Sizes: phone 390, mid 800 and wide 1280, light and dark. `layout.py devices` prints `unknown` for this repo,
so the sizes come from the brief. Mid 800 is drawn because page.html has a breakpoint at 960.
The mockup draws with page.html's own `<style>`. It adds no colour: each new rule reads a page token.
Options are named by name, never by a letter: the waiting page stamps its own letters.

Settled by the brief, not options here:
- Answered is `isSaved(it)`. Filed is `rcOf(it).filed`.
- Rulings stay in their own section.
- The answered set is frozen at load, like the seen set.
- A group sinks only when every member is answered.
- The section reuses the seen fold and the `rulingsEl()` section shape.

## 1. The section: name, place, open or folded

- Pick: "Answered", with the `.g.done` glyph (the receipt's check, one meaning: answered). It sits right
  after the open tiers, above Arbiter rulings, and is open on load with each card folded (`#s=page`). The
  head is the rulings head: `button.rhead` in the h2, `aria-expanded`, `aria-controls="ab"`, a count, and
  `p.rsub` "Sent before this visit, newest first. Each leaves the page once its session closes it."
  Gain: the owner sees what he answered at a glance, and a Change before the session reads it is close
  to the open work. Loss: on a page with many rulings, those move further down.
  Ids: `tier-answered`, `th-answered`, `b-answered`, `ab`.
- Alternative "Section folded on load" (`#s=section-folded`). Gain: the page ends sooner. Loss: one press
  to see any answer, and "collapse" then hides the answer the owner asked to see.
- Alternative "Section below the rulings" (`#s=below-rulings`). Gain: rulings, which may still need an
  Overturn, sit higher. Loss: the owner's own recent answers go to the very bottom.
- Order inside: newest answer first (the rulings' order). A group sits at its newest member's time.
- Rail: one new `ov-tier` row "Answered" with the section's chips (`.nchip.sent`, ring unfiled, tick filed),
  after the tier rows. Its count is the section's size. A tier row loses the chips of items that sank, and
  its count stays "open in this tier" (today's rule). "N of M sent" is unchanged: it counts every saved item.
- Builder note: membership is the set frozen at load (with `freezeSeen`), never live `isSaved`. Change
  sets `state.changing`, which turns `isSaved` false; with live membership the card would jump back to its tier.

## 2. What a folded answered card shows

- Today's answered card (`buildCard`, the `saved` branch) draws only the top row, the title, `receipt()`
  and `threadEl()`. No stake line, context or Lands-in line. So the fold has little to hide.
- Pick (`#s=page`, opened `#s=unfold`): folded to the top row, the title and the receipt line (answer,
  "Read by", Change). A multi answer keeps its picks list: it is the answer. The fold holds the owner's
  note and the thread. Words name what they hide: "Show your note, your last answer and the reply" /
  "Hide ...", built from the parts present. A card with none of them has no control (ux-control-earns-place).
  The card keeps today's green ground and edge (`.card.answered`), takes the ruling card's size
  (`.card.rcard` padding, gap and title size), and drops its tier class.
  Gain: two lines and a control per answer. Loss: the note needs a press.
- Alternative "Note outside the fold" (`#s=note-outside`). Gain: the note shows with the answer, as today.
  Loss: a long note keeps the card long.
- Alternative "Fold holds the question too" (`#s=fold-context`): the fold adds the context and the Lands-in
  line. Gain: the owner can re-read the question before a Change. Loss: it draws parts today's answered card
  does not, and Change already shows them.
- Top-row pill in the section: "Filing pending, sent <time>" (ring) or "Filed in <home> <time>" (tick).
  It drops "Answered, " because the section head says it. An item answered in place keeps today's pill.
  Loss: "Filing pending" still shows on every card in the section. `label_once.py` passes it only because
  the comma stops the word match; the design reviewer will see the repeat. Today's page repeats
  "Answered, filing pending" on every answered card the same way.
- Alternative, not drawn: the pill shows the ring or tick and the time only, its words in a `.sr` span,
  and `p.rsub` adds "A ring: filing pending. A tick: filed." Gain: the words show once. Loss: a shape to learn.

## 3. Answered and filed, still on the page

- When it happens: SKILL.md "Route and close" files (step 1) and closes (step 2) a clear answer in one
  turn, so a filed item with its answer record still on the page lives for that gap only. For a busy
  lane the writer sets `lane` and `lastAnswer` and leaves the item open; SKILL.md does not say whether
  `answers/<id>` is kept. If it is deleted, that item is not `isSaved`: it shows in its tier as an open
  card with "waits on lane" and "Your last answer", and never reaches this section. The builder reads
  which; this design does not depend on it.
- Pick: same section, newest-first with the rest, its pill filled with the tick (`#s=page`, No. 38).
  Why: it needs nothing from the owner, and it is about to close, so it should not jump back into a tier
  for that gap. Gain: the open tiers hold only open work, with no special case. Loss: the section mixes
  two states; the ring and the tick carry the difference. The case is short-lived, so the pick weighs little.
- Alternative "Filed items stay in their tier" (`#s=filed-stays`). Gain: the section is only "filing
  pending". Loss: a done item keeps its place among open work, the thing the owner asked to stop.

## 4. Change on a folded answered card

- Drawn in `#s=change` (press Change in any frame to see it live). The card stays in the section until
  reload. It becomes an open card: thread, context, then the seen fold locked open ("Stays open: your
  answer is ready"), the options with the old answer picked and the note filled, and Lands in. This is
  the seen fold's own lock: Change makes a draft, and `foldLocked` keeps it open. The rail chip turns
  ready, the bar says "1 ready", the section count stays 5. After Send it folds again in place.
- Departs from: nothing new. Today a Change already grows its card in place, so content below moves
  (ux-press-moves-nothing). That stays as today.

## Just sent, still in place

- `#s=just-sent`: No. 36, sent at 16:02 after a load at 15:55, keeps today's answered card in its tier
  until reload (`freezeSeen`). Its chip stays in its tier row as sent; the tier
  count excludes it; the section count excludes it. No. 40, sent before the load, sits in the section.

## Groups

- `#s=groups`: a group with one member answered and one open stays whole in its tier (answered member
  as today). A group with every member answered sinks as one bundle frame inside the section.

## 5. More sections (owner's pick). Owner grant: yes

Each draws the same six asked-before audit items in Whenever. Picture ids: `#pick-sections-none`,
`#pick-sections-repo`, `#pick-sections-kind` (the list), one `data-state` each.

- "No more sections" (`#s=sections-none`): the four tiers, then Answered and Arbiter rulings. Gain: no
  new field, nothing new to learn. Loss: audit items of many repos sit in one long Whenever list.
- "By repo" (`#s=sections-repo`): inside each tier, one sub-group per repo, this repo first, each with a
  head (a neutral letter tile, the name, a count, a solid rule). Needs a new writer field `repo` (in
  `itemFields`, SKILL.md item schema); an item with none sits under the page's own repo name.
  Gain: one repo's audit items sit together, so the owner settles one repo at a time. Loss: a new field
  every writer must set, one more level of heads, and the seen divider repeats in each sub-group.
- "By kind" (`#s=sections-kind`): inside each tier, Decisions then Tasks. Gain: no new field; tasks the
  owner does at a computer sit together. Loss: "Decisions" and "Tasks" repeat in each tier that holds
  both (ux-label-once), and the Whenever order already puts decisions first.
- Not drawn: the writer puts each repo's audit items in one `group` today, with no page change. Loss: a
  group means "answer these together" and pulls every member to its most urgent tier.
- Recommendation: "By repo". The step note names it, and the claude-settings page carries most child-repo
  audit items. The sub-head is one shape shared with "By kind", so either pick builds the same part.

## Checked

- `check_designs.mjs` on main's page with this mockup in `designData` and a three-option item for point 5
  (one `state` and `focus` each): exit 0, `problem: null`. All three pictures seen drawn at 1280; at 390 the
  first two drew and the third had not loaded below the fold when shot.
- Playwright, Chromium: all 13 states at 390, 800 and 1280, light and dark (78 runs). No script error,
  no sideways scroll in the page or the frame.
- `label_once.py` on each state at 390: the remaining hits are today's "Asked before" (the seen divider's
  screen-reader words) and the repo name as data in "By repo". It does not flag the "Filing pending"
  repeat (point 2 names it).
- In a frame (the waiting page's picture), the mockup draws the state as the screen itself, so `focus`
  finds a real box; `#pics` holds static anchors because `pictureProblem` parses the HTML string.

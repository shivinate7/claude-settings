# shelf-directed-3 notes

Lane kind: directed. Direction: Shelf. The place comes first. The first screen shows the boxes as they
sit on the table: each box is a bar of slots, and each card is a sliver in its listing state. A stack
pours into the next free slots. A sale lights its slivers. Tabs: Shelf, Orders, Search. First screen:
Shelf.

Mockup: `shelf-directed-3.html`. Every box, card, price, order and buyer on it is sample data. The
current screen is v2's C2 Shelf: `designs/d4-banchi-phone-v2/phone-blind-1.html` on the `roadmap`
branch, states `c2-empty` to `c2-order`, and its `png/c2-*.png`.

## Choices

1. **What v3 changes against v2's C2, and why it looks better.**
   v2 drew each box as a flat green progress bar; v3 draws a tray seen from above, with card edges, divider tabs that stand up, and a sold card that stands up in amber, so the screen looks like the table.
   v3 opens on the Shelf itself (v2's folded first view was one box), shows 30 boxes against one slot ruler, and lets the stack pour across two boxes in a glass dock above the tab bar.
   One indigo ink plus one amber light replaces v2's all-green bars, so a sale is the brightest thing on the screen in both themes, and every state has a shape as well as a colour.

2. **The folded first screen is the Shelf, with the pour in a dock.**
   Departs from: v2 `phone-blind-1.html`, `data-state="c2-full"`, folded pose, which opens on Box 3
   with a "Next card goes in Slot 227" panel and "List 186 cards".
   Gain: the direction's first screen ("the boxes as they sit on the table") is the first thing seen
   folded too. The next free slot and List stay in reach of the thumb, above the tab bar
   (`ux-thumb-zone`). Loss: about 7 of 30 boxes show folded; the rest scroll under the dock.
   Pick: yes. Hide: none; this is the concept.

3. **A box is a tray of card edges.** The live run has a fine card-edge texture, and a cut each 50
   slots. A cut each 10 slots was tried and dropped: at 1 pt per 1.24 slots it read as battery cells.
   Gain: the box reads as cards, not as a meter. Loss: a person counts to a slot by the ruler, not by
   the texture. Pick: yes.

4. **Five states, five shapes, named once.** Live: solid. Draft: hatched. Sold, to pull: an amber
   card that stands up above the rim. Check: a triangle under the slot. Not live: a short stub in an
   empty slot. Each screen that draws a state shape has a legend that names only the shapes it draws
   (`ux-label-once`): full and error (all five), keyboard folded (Live, Draft, Sold), keyboard
   unfolded (four), order (Sold, to pull, and Pulled). Loading draws no state shape, so it has no
   legend. Keeps v2 item 8 (state by shape, colour never alone). Hide: "Hide a sold card that stands
   up" lays it flat. Pick: yes.

5. **Dividers stand up.** Each divider is a small tab above the rim, at its slot. On the Shelf the
   tabs are quiet and have no text; in the stack detail they are named ("Stack 14"). The brief's box
   has dividers; v2 did not draw them. Gain: the helper sees the physical tab to put a finger on.
   Loss: four more marks per row. Hide: "Hide dividers that stand up". Pick: yes.

6. **One slot ruler per screen.** It sits over the trays (1, 50, 100, 150, 200, 250, a tick each 10),
   never on each tray. Gain: "slot 147" is findable by eye. Loss: one row of height. Hide: "Hide the
   slot ruler". Pick: yes.

7. **The stack pours across boxes.** Stack 14 (186 cards) fills Box 4 slots 205 to 250, then Box 5
   slots 1 to 140. The stack detail draws both boxes at one scale, 100 slots a line, with a bar at
   the next free slot (141). Gain: the pour is visible, not only stated. Pick: yes.

8. **One word for a position: slot.** Owner grant: yes. The brief's model calls it "place"; the
   direction says "slots"; v2 used both ("Slot 227", "Reading your places"). v3 says "slot" on every
   screen, and "Box 5, slot 141" for a place. Gain: one plain name for the helper (`ux-one-plain-name`).
   Loss: the model term "place" and the screen word differ. Pick: "slot" on screen.

9. **Each place is one component: box above, slot below.** Used in the pull list and the results.
   The pour dock writes it as one line, "Box 5, slot 141". Pick: yes.

10. **The card line drops the middle dots.** Set and number, a condition tag, a Foil tag, and the
    language only when it is not English. Departs from: v2 `c2-full` rows ("AX1 199 · LP · English").
    Gain: less template chrome; English is the default. Loss: English is implied, not stated.
    Pick: yes.

    **Kept from v2: the count per box and Add a box.** Each Shelf row ends with "226 of 250"
    (v2 `phone-blind-1.html`, `data-state="c2-full"`, `.bx .lab .num`). A box with free slots shows
    its count in full ink; a full box in secondary ink, so the open boxes read first. "Add a box" sits
    in the Shelf navigation bar beside Scan, in the full state (v2 `.bar .nb`). Pick: yes.

11. **Search results carry a small box.** Each result shows the slot inside a 72 pt tray, with the
    state's shape. Unfolded, the left pane pins each match on its box. A pin is ink, with a thin ink
    line at the slot, so the slot under it keeps its true state: Box 1 slot 203 live, Box 5 slot 139
    draft, Box 9 slot 77 sold. The results carry the same numbers, 1 to 3. The left pane is titled
    "Search", as its tab, and the count "3 matches on the shelf" is a line under the title, in the
    bar (`ux-one-plain-name`). Keeps v2 `c2-keyboard`
    (field above the keys, `ux-thumb-zone`). Hide: "Hide the small box in each result". Pick: yes.

12. **Order: the sale stands up in its box.** Folded, the boxes that hold the picks show above the
    pull list, with numbered pins in walk order. A pulled card leaves a gap in its box, and its pin
    turns grey, as its row's number does. Unfolded, the order list is on the left and the pull on the
    right (list beside detail). "Mark shipped" can be undone. Keeps v2 `c2-order` (walk order,
    undo). Pick: yes.

13. **Error and loading.** Error keeps v2 `c2-error`: the last read, dimmed, names and counts at full
    contrast, Try again, and a closed "What the server said". Dim is a set of dim colour tokens, each
    3:1 or more on the tray floor, never opacity. Loading shows each tray faint with no counts and
    "Reading your shelf…", never empty or zero (`ux-unknown-is-not-empty`). Folded, loading and error
    keep the pour dock: the slot reads "Reading…" or "Not known", and List is off. Scan and List are
    off in both loading and error, because a scanned card goes in the next free slot, and no state
    but a good read gives that slot. Every control that waits says so in visible text, with one
    wording: "Waits for your shelf." (Scan, under its button; List, under its button, in both poses).

14. **Open question, not blocking.** v2 item 12 says a shipped sale frees its slot. v3 pours a stack
    only after the last full slot, so a freed slot stays a gap. Does a later stack fill gaps first?
    That would scatter one stack over many boxes. Pick for the mockup: no.

15. **Colours.** `tokens.md` gives roles only; the values are this lane's. Light: cool paper surface,
    indigo ink, amber sale. Dark: navy surface, periwinkle ink, bright amber. Each role has a light
    and a dark value, the badge and the Foil tag too. An edge token (`--edge`) draws each control
    edge (the Mark-pulled ring, the search field) at 3:1 or more. Font stack: `-apple-system`,
    SF Pro, then Inter as the stand-in that rendered. Radius 8 pt; a tray is 4 pt, so a 20 pt tray
    reads as a box, not a pill. The corner radii are an open question for the owner; round 2 does not
    change them.

## Device and sizes

`layout.py devices` printed `unknown`, so the sizes are the brief's (iPhone Duo simulator, iOS 27.1,
2026-10-27). 1 CSS px = 1 pt. Folded: content 382 x 644, trailing inset 84, bottom inset 34, frame
466 x 678; keyboard open, content 466 x 250. Unfolded: 951 wide, fold strip 455.5 to 495.5;
keyboard open, content 951 x 263. Unfolded, the keyboard is drawn in two halves, one under each
pane, with no key on the fold strip. Not measured: the unfolded height (drawn 644), the insets other
than these, the keyboard heights (each keyboard fills the frame), and where the system keyboard meets
the fold (the halves are a drawing, not a reading of the simulator).

## Apple pages read 2026-10-30

Each answered 200 from `https://developer.apple.com/tutorials/data/design/human-interface-guidelines/<page>.json`:
layout, typography (Large default: Large Title 34/41, Title 2 22/28, Headline and Body 17/22,
Subhead 15/20, Footnote 13/18, Caption 1 12/16, Caption 2 11/13; only these sizes are used; tab
labels are Caption 2, 11/13),
accessibility (44 x 44 pt default control), buttons, sheets, tab-bars (floats over content; a badge
for critical news), toolbars, lists-and-tables, text-fields (label, fitting keyboard, Clear button).

## Deep links

`#s=<empty|loading|full|error|keyboard|order>&t=<light|dark>&p=<folded|unfolded>`. No `t`: system
theme. No `p`: both poses. `h=dividers,stand,ruler,mini` hides options; `l=0` hides the labels.
Focus ids, each with its state: `#s=full` focus `shelf` (the shelf list, folded) or `shelf-u` (unfolded) and `pour` (the dock); `#s=order` focus `pull` (the boxes of an order, folded) or `pull-u` (unfolded).

## Checks

Round 3, 2026-10-30. Round 3 changes only the unfolded keyboard, the Search pane title, and Scan in
error; every other screen is as round 2.

- `check_ios_mockup.py`: exit 0.
- a11y floor (axe, `a11y.md`): not run, unknown. No axe package is on this machine.
- Layout script, 24 screens: no text or control on the fold strip or in the folded trailing inset,
  nothing outside its frame, each control 44 x 44 pt or more. The fold-strip test also covers each
  drawn key: 32 keys unfolded, 0 on the strip. On the round-2 file the same script finds t, y, g, v
  and space on the strip, in both themes. 0 faults.
- Contrast script, 88 pairs (light and dark): text 4.5:1; state cues, dim cues and edges 3:1. 0 fails.
- Round 2's DOM audit (0 CONTRAST, 0 VCLIP; text sizes 11, 12, 13, 15, 17, 22, 34 only) is not run
  again; the new title line is Footnote 13/18. The shelf rows under the glass dock and tab bar are
  intended (the bar floats over content); the shelf fades out over its last 48 pt.
- Spacing is on the 4 pt step. Left as is: the drawn system keyboard (gaps 6 and 11, side padding 3,
  row indent 44), the caret offset, and the centring offsets of marks on a tray.
- `png/` holds exactly 25 PNGs: the 24 states (6 states x 2 poses x 2 themes) plus `shelf-option.png`.
  Round 3 re-rendered the 4 keyboard and the 4 error PNGs; the 2 folded keyboard PNGs are
  byte-identical to round 2. Each changed PNG was looked at by eye.
- `impeccable critique`: single context (no sub-agent tool); its launcher and detector did not run
  (guard `impeccable-review-only` refused). In scope, nothing left to fix. Not fixed, outside the
  round-3 fixes: folded error shows about three boxes above the dock; no way to jump to a box or filter
  "boxes with a sale" (item for the owner); the corner radii (item for the owner).

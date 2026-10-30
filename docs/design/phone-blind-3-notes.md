# phone-blind-3: notes

Lane kind: blind. Lane: phone-blind-3. Mockup: `phone-blind-3.html` (open from disk).

This lane did not see today's screens, code, spec, tokens or other mockups. Every part is "New".
Nothing is marked "Today". Every figure, name, price, order and buyer is a sample.

## Options and deep links

Each concept is one option. The × beside each concept chip hides that option. Add `&t=dark` or
`&t=light` to any link; with no `t`, the page follows the system theme.

| Option | Link to judge it by | Focus id | Other states |
|---|---|---|---|
| A. Tabs | `#c=a&s=pull` (first screen) | `a-tabbar` | `find` (focus `a-find-place`), `pulled`, `empty`, `error`, `list`, `shoot`, `check`, `type` (keyboard), `send`, `search` (keyboard) |
| B. Shelf | `#c=b&s=shelf` (first screen) | `b-shelf` | `box`, `find`, `empty`, `error`, `listing`, `shoot`, `check`, `send` |
| C. Route (bold) | `#c=c&s=find` (the find step) | `c-step` | `start` (first screen), `open`, `pack`, `done`, `error`, `shoot`, `check`, `send`, `confirm`, `sending` |

Each state draws the iPhone Duo folded first, then unfolded, in its own frame.

## Items

1. **Concept A, Tabs.** Pull, List and Boxes tabs. Pull lists sold cards by box. A card opens a
   three-step find page.
   Gain: a familiar structure, and any screen is one tap away.
   Loss: the helper sees all the tabs, including the seller's, and must pick a row each time.
   Pick: second choice.
2. **Concept B, Shelf.** The first screen is a map of the real shelf. A box with work lights up.
   Inside a box, each card is one line, so the helper sees how far in the card is.
   Gain: the map matches what the helper sees at the shelf. One map serves both people.
   Loss: the seller must keep the map in the same order as the shelf. There is no tab bar.
   Pick: third choice. Owner grant: yes (departs from the house tab bar, `tokens.md`).
3. **Concept C, Route (bold).** There are no tabs and no lists. One instruction shows at a time,
   like turn-by-turn directions for the shelf. The first screen asks "What are you doing now?".
   Gain: the helper never chooses where to go next, and each screen explains itself.
   Loss: it is hard to browse or jump. The seller's "Where is a card?" is one button on the start
   screen.
   Pick: **my pick**. Owner grant: yes (departs from the house tab bar, `tokens.md`).
4. **A place shows as a divider and a count, not as card 147.** The count row draws card tops
   from the front, with the divider tab and the target filled. Front means the end of the box
   with its name label.
   Gain: the helper counts 5 cards, not 147. The count is still true after a pull, because pulls
   go from the back of the box first (item 5).
   Loss: each box needs its name label at one fixed end, and dividers where the sections start.
   Pick: all concepts. Owner grant: yes (sets a rule for how boxes stand on the shelf).
5. **Inside a box, the back card comes first.** When a card leaves, the cards behind it move up.
   If the helper pulls from the back first, no other pull's count changes.
   Gain: no count goes wrong in the middle of a round.
   Loss: the pull order inside a box is not the order the orders came in.
   Pick: all concepts.
6. **Check by sight.** The find page shows the card in front, this card, and the card behind,
   from the sitting's photos.
   Gain: the helper confirms the card without reading small set numbers.
   Loss: it needs the photos of the cards on each side, which the sitting already holds.
   Pick: all concepts.
7. **Pull acts at once, with Undo.** A and B use one press, "Pulled and packed". C uses two:
   "It's in my hand", then "It's in the envelope". The answer shows at the press, with Undo,
   because a pull moves every card behind it up one place.
   Gain: no ask in the helper's way. One wrong press is easy to undo.
   Loss: C uses two presses for each card.
   Pick: C's two steps, because they track which envelope is full.
8. **One round, box by box, with the envelopes open (C).** The round visits each box once, in
   shelf order. Each card goes straight into its buyer's envelope. A dot shows how many cards
   each envelope still needs.
   Gain: each box opens once, and nothing goes into a loose pile.
   Loss: the helper lays out the day's envelopes before the round starts.
   Pick: C. Owner grant: yes (sets how the helper works).
9. **The machine never picks for the seller.** A waiting card shows its photo, the reason in
   plain words, and the cards that match. No match is preselected. The other ways out are "New
   photo", "Hold it back" and, in A, "type the name".
   Gain: nothing is guessed.
   Loss: each waiting card takes one press.
   Pick: all concepts.
10. **A waiting card does not stop the sitting.** The camera counts each card in the frame, and
    the count is its place. Waiting cards collect, and the seller names them after the box.
    Gain: the seller gives no thought to each card.
    Loss: the seller sees a waiting card only later.
    Pick: all concepts.
11. **The camera takes each photo by itself when a card is in the frame.** This promises a
    capability.
    Gain: no shutter press for each of about 300 cards.
    Loss: a card that moves can make a blurred photo (card 47 in the sample).
    Pick: all concepts. Owner grant: yes (states a capability; `ux-statements-are-true`).
12. **A send asks first.** The ask names the count, "List 195 cards on TCGplayer?", and first
    focus is on Cancel. The ask says "This app cannot take a listing down."
    Gain: one press cannot list a whole box by mistake.
    Loss: one more press for each box.
    Pick: all concepts. Owner grant: yes (confirm that the app cannot take a listing down;
    `ux-statements-are-true`).
13. **The send summary adds up to the box.** 195 to list, 15 stay in the box (13 under $0.49,
    2 held back by the seller), and 2 still wait. That is 212. In C unfolded, the cards that stay
    are listed, and the seller can list one anyway.
    Gain: "every card listed or knowingly held back" is visible before the send.
    Loss: none found.
    Pick: all concepts.
14. **A long send shows Stop (C, `sending`).** Progress shows at the press. Cards listed before
    Stop stay listed.
    Pick: all concepts.
15. **A failed order read keeps the last list.** The list shows the time it was read and says
    that newer orders may be missing. The server text is behind "What the server said".
    Gain: the screen never shows a failed read as empty or done.
    Pick: all concepts.
16. **Buyer first, order number in a closed disclosure.** The buyer's name is what is on the
    envelope. The order number is a record id (`ux-machine-text-hidden`).
    Pick: all concepts.
17. **Unfolded: two panes, nothing on the fold.** Each pose is its own layout: a list beside its
    detail, or the instruction beside its check. In A, the tab bar stays in the left pane, because
    a centred tab bar would cross the fold strip. Each ask, sheet and Undo stays inside one pane.
    Pick: all concepts.
18. **Status by shape, with the word once.** To pull is a filled dot, waits for you is a diamond,
    listed is a ring, and stays in the box is a dash. Each screen that shows shapes has one legend
    (`ux-label-once`).
    Pick: all concepts.

## House rules, sizes and sources

- Colour: this lane's own role colours, in light and dark. No repo or product colour. Text pairs
  are at 4.5:1 or more, and status marks at 3:1 or more (checked by a script in both themes).
  The camera view is dark in both themes, so its status shapes use the dark values.
- Type: the system font, with Dynamic Type sizes at the default size. The radius is 8 px, except
  for the system tab bar and segmented control, which keep their own shapes. Spacing is on the
  4 px step.
- `a11y.md` was not read. The blind brief forbids other files in `~/.claude/docs/design/`. The
  floor here comes from the Apple pages below.
- Devices: `layout.py devices` printed `unknown` for this repo. All sizes come from the brief.
  Folded is 466 × 678, with safe content 382 × 644, a trailing inset of 84 and a bottom inset of
  34. With the keyboard open, folded is 466 × 250 and unfolded is 951 × 263. The unfolded height
  of 644 and the unfolded insets are not measured, so 644 is drawn and no inset is drawn.
- Apple pages, read 2026-10-30 (each answered 200) through `tutorials/data/…json`:
  `design/human-interface-guidelines/` layout, typography (Large default sizes: 34, 28, 22, 20,
  17, 16, 15, 13 and 12 pt), accessibility (44 × 44 pt controls, 4.5:1 contrast up to 17 pt),
  buttons, sheets (Cancel on the leading edge), lists-and-tables, tab-bars (navigation, not
  actions; floats at the bottom), toolbars and segmented-controls. Caption 2 is not used.
- Checks: `check_ios_mockup.py` exits 0. `label_once.py` on each rendered state names "rares"
  twice in B `find`. That is the seller's divider name in the box view and on the divider tab,
  which is data. A headless render of all 31 states in both themes gave no script error, no
  element past its screen or pane edge, no text or control in the fold strip, and no button under
  44 × 44. Each focus id in the table shows once. The fold and target checks went red on a copy
  with a 36 px segmented control and an unsplit keyboard.
- Unfolded with the keyboard open, the drawn keyboard is split at the fold. The real system
  keyboard on this pose is not measured.

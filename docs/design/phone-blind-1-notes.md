# phone-blind-1 notes

Lane kind: blind. Mockup: `phone-blind-1.html`. Every figure, name, price, order and place on it
is sample data.

The job: list a pre-sorted stack of trading card singles on TCGplayer with no per-card typing, and
know the box and slot of each card, listed or sold.

## How to open one state

- `#s=<concept>-<state>` opens one state. Concepts: `c1`, `c2`, `c3`. States: `empty`, `loading`,
  `full`, `error`, `keyboard`, and `order`, an extra state.
- `t=light` or `t=dark` sets the theme. With no `t`, `prefers-color-scheme` sets it.
- `h=c1,c3` hides options. The "Hide C1", "Hide C2" and "Hide C3" buttons set `h`. One press
  removes one option.
- `l=0` hides the dashed "New:" labels.
- Example: `phone-blind-1.html#s=c2-error&t=dark`.
- Focus ids: `c1`, `c2` and `c3` wrap the concepts. The elements that carry the decision are
  `c1-list` (one press lists the stack), `c2-shelf` (the shelf as the home screen), `c2-next` (the
  next free slot), `c3-count` (one count, no card list), `c3-deck` (one question per card) and
  `c3-pull` (the place as the headline).

## Device and sizes

`layout.py devices` printed `unknown`, so all sizes come from the brief (measured on the iPhone Duo
simulator, iOS 27.1, 2026-10-27). 1 CSS px = 1 pt.

- iPhone Duo, folded: safe content 382 x 644, trailing inset 84, bottom inset 34. The frame is
  466 x 678.
- Folded, keyboard open: content 466 x 250. The brief gives 250 to 289. I drew 250, the worst case.
- iPhone Duo, unfolded: 951 wide, fold strip 455.5 to 495.5. No text or control is on the strip.
  Each pane is 455.5 wide.
- Unfolded, keyboard open: content 951 x 263.
- Not given, so not invented:
  - The unfolded height. I drew 644, the folded safe height. The real height can be different.
  - The folded top inset. The CSS uses `env(safe-area-inset-top, 0px)`. There is no status bar in
    the drawing.
  - The unfolded insets. I drew none.
  - The keyboard heights. Each keyboard fills the frame below the measured content, so its height
    comes from the frame, not from a measurement.
  - How the system keyboard treats the fold. The unfolded keyboard is drawn across the full 951 pt,
    so its keys cross the fold strip. The system draws the keyboard; the app does not. Not
    measured.

## Apple pages read

I read each page on 2026-10-29 through `https://developer.apple.com/tutorials/data/...json`. Each
page answered 200.

- layout: respect the safe areas. Lay out by size class, not by device. So each pose is its own
  layout.
- typography: the Dynamic Type sizes in the iOS "Large (default)" table: Large Title 34/41, Title 1
  28/34, Title 2 22/28, Title 3 20/25, Headline 17/22 semibold, Body 17/22, Callout 16/21, Subhead
  15/20, Footnote 13/18, Caption 1 12/16, Caption 2 11/13. The mockup uses only these sizes.
- accessibility: on iOS the default control size is 44x44 pt, the minimum is 28x28 pt, and the
  default text size is 17 pt. All targets in the mockup are 44 pt or more.
- buttons: a button needs a hit region of at least 44x44 pt.
- sheets: Cancel goes at the leading edge, Done at the trailing edge. Done is inactive until the
  task is complete. Used in "Fix card" (C1) and "Set price" (C3).
- tab-bars: a tab bar is for navigation, not for actions. It floats above the content at the
  bottom. Use few tabs. A sidebar is an alternative for complex apps.
- toolbars: a large title changes to a standard title when people scroll.
- lists-and-tables: show text in a list.
- text-fields: show a label as well as the placeholder, show the keyboard type that fits the
  input, and put a Clear button at the trailing end.
- The SwiftUI pages for NavigationStack, TabView and List: not read. No value comes from them.

## The three concepts

- **C1, Stack run.** The task comes first. A stack is the unit of work. Scan the stack, check the
  few cards the app is not sure of, then list the whole stack with one press. Tabs: Stacks, Orders,
  Places. First screen: Stacks.
- **C2, Shelf.** The place comes first. The first screen shows the boxes as they sit on the table:
  each box is a bar of slots, and each card is a sliver in its listing state. A stack pours into
  the next free slots. A sale lights its slivers. Tabs: Shelf, Orders, Search. First screen: Shelf.
- **C3, Only what needs you (bold).** There is no card list and no tab bar. The pose is how you
  move around. Folded, the phone is a scanner: it shows one count and where the stack goes.
  Unfolded on the table, it is a desk: it shows only the cards the app is not sure of, the orders
  to pull, and a "Where is" field. Each sure card goes live as it is read. First screen: the camera
  when folded, Needs you when unfolded.

For the set check: C1 and C2 move around the same way, with a three-tab bar and push. They differ
in structure and in first screen. C3 differs in all three: structure, way to move around, and
first screen.

## Choices

1. **Which concept leads.** C1 is the safest to build and to learn. C2 answers "where is it" with
   a picture, but listing needs one more step there. C3 gives the least attention per card, but it
   is the newest pattern and it does the most with no press.
   Gain of C3: per-card attention is near zero, and the hand that holds the phone presses only
   when the app asks. Loss: no list of cards to scroll, and a person who wants to see everything
   must use "Where is".
   Pick: C3 for listing. Use the shelf picture of C2 as the answer to "Where is". Hide controls:
   "Hide C1", "Hide C2", "Hide C3".

2. **The place comes from the stack order.** All three concepts do this. Each card gets the next
   free slot of the chosen box, in the order the cards are read. Copies take one slot each, so
   "Marsh Strider x3" takes slots 46 to 48.
   Gain: no typing of a place. The person boxes the stack in the same order. Loss: a card put back
   out of order breaks the map. The pull screen has a "Not in its slot" control for that case.
   Pick: yes, in all concepts.

3. **When a listing goes live.** C1 and C2 make a draft of each card and list the stack with one
   press. C3 lists each sure card as soon as it is read and has its price.
   Gain of the one press: the person sees the stack before anything goes public. Loss: one more
   step, and a stack can stay as drafts if the person forgets.
   Gain of listing as read: zero presses. Loss: a wrong price is public for a short time.
   Pick: C3 lists as read. A card is "sure" only when its name, printing and price all pass the
   app's checks. All other cards stay as drafts in Needs you.

4. **Cards the app is not sure of.** Each concept keeps them as drafts and never lists them
   without a person. The app asks one question per card, with big answers: "Which printing is
   it?" or "Price far from recent sales". C1 shows them behind a "2 to check" filter. C3 shows them
   as a deck, one card at a time.
   Gain: the person looks at the few cards that need a person, not at all of them. Loss: the app
   must say why it is not sure, or the question is noise.
   Pick: the C3 deck, with the reason on each card.

5. **No tab bar in C3; the pose picks the mode.** Owner grant: yes. Departs from: house
   `tokens.md`, "On a phone, navigation uses a bottom tab bar."
   Gain: the brief says the folded phone is held in one hand with a card in the other, and the
   unfolded phone rests on the table. Each pose then gets one job, and nothing on screen is a
   control to switch jobs. Loss: a person who wants the desk while folded must unfold. Apple's
   tab-bars page expects a tab bar for sections. A screen reader user gets no list of sections.
   Pick: try it in C3 only. C1 and C2 keep the house tab bar. Hide with "Hide C3".

6. **Unfolded is the desk, not the scanner.** In all concepts the unfolded pose shows review,
   places and orders. It does not show a live camera. The phone lies on the table there, so its
   back camera faces the table.
   Gain: each pose shows what the person can do in that pose. Loss: a person who scans with the
   phone unfolded gets no live view. "Scan more" in C1 opens the camera, and the person must lift
   the phone.
   Pick: yes.

7. **The tab bar sits in the left pane when unfolded.** A tab bar centred on 951 pt would cross
   the fold strip. So it floats at the bottom of the left pane. The right pane shows the detail of
   the row picked on the left.
   Gain: no control on the fold. Loss: the tab bar is shorter, and it is away from the right hand.
   Pick: yes, in C1 and C2.

8. **Listing state by shape.** Draft is a hollow ring, live is a filled dot, sold is a filled
   square, "check" is a triangle and "not live" is a cross. In the C2 box bars, a draft range is a
   hollow outline, the same as the hollow ring. Each screen names the shapes once, in a legend
   (`ux-label-once`). In the build, each shape needs an accessibility label.
   Gain: a long list shows its state with no repeated words. Loss: a new person must learn five
   shapes. Colour is never the only signal.
   Pick: yes.

9. **Errors.**
   - C1 shows the answer where List was pressed, in the dock: "3 cards did not go live" and
     "Try the 3 again" (`ux-answer-at-press`).
   - C2 shows the shelf from the last read, dimmed, with its time. It never shows an empty shelf
     (`ux-unknown-is-not-empty`).
   - C3 keeps reading. The cards that TCGplayer did not accept wait as drafts, and the count says
     how many.

   In each, the raw server text is inside a closed "What the server said" disclosure
   (`ux-machine-text-hidden`), and a control leads on (`ux-no-dead-end`).
   Pick: all three behaviours can live together. C2 needs a local copy of the places.

10. **Loading.** The long run is getting prices for a stack. It shows "64 of 186", a progress bar
    and a Stop control (`ux-long-run-stops`). Each row's skeleton keeps the size of the loaded row,
    so nothing moves when the data comes (`ux-press-moves-nothing`). List stays in its place,
    disabled, with "Waits for prices." under it (`ux-control-earns-place`).
    Pick: yes.

11. **Text fields with the keyboard open.**
    - C1: fix a misread name. It is a search field with a search key. The unfolded pose shows the
      camera photo on the left and the field on the right.
    - C2: "where is a card". The field stays at the bottom, above the keyboard, near the thumb
      (`ux-thumb-zone`). Unfolded, each match is a numbered pin on the shelf.
    - C3: set a price. It uses the number pad, because the input is a number (Apple text-fields
      page).
    Pick: each concept keeps its own field.

12. **Pulling an order (extra state, not in the brief's list).** The picks are sorted by place,
    in walk order, never by order line. C3 shows one card at a time with the place as the headline,
    and the camera can check the pulled card. "Mark shipped" can be undone (`ux-ask-or-undo`), and
    it frees the slots.
    Gain: the second half of the job ("find it fast and send it") gets a screen. Loss: six states
    per concept, not five.
    Pick: C3 one at a time when folded, the C2 shelf pins when unfolded.

13. **Colours.** `tokens.md` gives roles, not values, so the values are my own: a warm neutral
    surface, a deep green-teal accent, and separate role colours for live, sold, check and error.
    The values are on `:root`, light and dark. My contrast script checked 27 pairs in each theme:
    each text colour on each surface that the mockup puts it on, including the glass panels and
    tags over the camera. Each text pair passes 4.5:1, and the status shapes pass 3:1. One pair
    fails, secondary text on a dark key (4.06:1), but the mockup draws no secondary text on a key. Spacing is on the 4 px step. Radius is 8 px. The tab bar
    is a capsule because iOS draws it so.

14. **"New:" labels only.** A blind lane sees no current screen, so no part is marked "Today:".

## Unknowns that each concept depends on

- Can the app name a card from the camera, and how sure can it be? All three concepts depend on
  this. C3 depends on it most.
- Can the app make, list and change TCGplayer listings without the person, and how fast? C3's
  "list as read" depends on this.
- Where does a price come from? The mockup shows "Your rule gave $12.50" and "Recent sales". The
  rule and the source are not known to this lane.

## Checks

- `check_ios_mockup.py`: exit 0.
- My layout script, all 18 states in light: no app text or control on the fold strip or in the
  trailing inset, nothing outside its frame, no tap target under 44 pt. It skips the drawn
  keyboards (see Device and sizes). The layout does not change with the theme. I took screenshots
  of all 18 states in dark too. I checked three of them by eye: `c2-full`, `c3-error` and
  `c3-order`. The other 15 dark screenshots were not looked at.
- `label_once.py`, one page per screen: the only repeats are data (a card name, the condition
  "NM").
- The a11y floor in `a11y.md` was not run. The blind brief forbids reading that file. Result:
  unknown.

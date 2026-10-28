# Waiting page, step c122: design notes

Mockup: `docs/design/waiting-page.html`. Screen: `skills/waiting-page/page.html` (main a64166ae).
Deep links: `#s=main|computed|viewer|refused`, `&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`.
Sizes from page.html's media queries: phone 390 (≤520), mid 800 (≤960), wide 1280. Light and dark.
The mockup draws with page.html's own `<style>`. The header is left as on main (another lane owns it).

## 1. What differs between options

- 1A (pick): the writer names it. Each option may carry `differs`, a list from `picture`, `how`,
  `gain`, `lose`. Each named row gets a 3px bar on its left edge in `--acc`, a `≠` sign at its
  right, and the hidden words "Sets this option apart: " before its text. A named picture gets the
  bar on its frame and `≠` in its View bar; its aria-label adds ". Its picture sets this option apart".
  Under the options, once per item that has a mark: "≠ marks what sets an option apart."
  The page drops a named text field whose text equals that field in every other option, and
  `picture` on an option with no picture. An unknown name is ignored. Gain: few marks, each true.
  Lose: the writer must author it. An item with no `differs` looks as today.
- 1B: the page computes it. A field is marked when its text differs from any other option. No
  authoring, but nearly every row is marked (`#s=computed`: 16 marks against 7), so the mark says nothing.
- No colour alone: the bar is a shape, `≠` is a sign, the legend is words, a screen reader hears
  the words. `--acc` already passes 4.5:1 on surface and soft, so the bar passes the 3:1 state-cue floor.
- Writer read-back: each `differs` entry is one of the four names.

## 2. Open this state in the full mockup

- Field: a design may carry `state` (a slug, such as `"late-package"`).
- Mockup contract (already in agents/designer.md for deep links): the mockup reads `#s=<state>`
  on load and on `hashchange`, and draws each state as an element with `data-state="<state>"`.
- Page side: when a design has `state`, the page puts
  `<script>try{location.hash="s=<state>"}catch(e){}</script>` in front of the srcdoc, before the
  mockup's own script. The card picture and the viewer then show that state. Measured with Playwright: in
  a `sandbox="allow-scripts"` srcdoc frame, `location.hash` reads `#s=late-package`, and the hashchange fires.
- "Open full size" (viewer `#dFull`, and the front preview's button) opens the blob URL plus
  `#s=<state>`. Measured: the new tab's mockup shows `late-package`.
- Strings, with `state`: button "Open this state" (phone: the same ⤢ icon), aria-label "Open the
  <state words> state of the full mockup in a new tab". The viewer title and caption read
  "<option title> (<width>), <state words>", where state words are the slug with `-` as a space.
  Without `state`: no change.
- Check, like `focus`: a `state` with no `[data-state="<state>"]` in its mockup blocks the item:
  "The picture of option C names a state its mockup does not draw. Ask the session to fix item 4." (`#s=refused`).
  Two options with one slug and one focus but different `state` count as different pictures.
- Rejected: postMessage. The page opens the new tab with `noopener`, so it cannot post to it,
  and a mockup that only listens for a message shows the default state when opened from disk.

## 3. Page-review fixes

Already done on main (checked with Playwright at 390, 800 and 1280):
- Option chip: one letter (`letterOf`), one line, no overlap with the title (`.key`).
- "Take my pick (<title>)" and "Ready to send: <title>, ..." use `pickName`.
- "0 of 9 sent": the digit uses `font: inherit`, so it has the line's size and face.
- AI sparkle inline SVG (`sparkle()`).

Still open, drawn:
- Short titles: a new item field `short` (24 characters or fewer). The wide rail chip shows
  `short`, else today's ellipsized `title`. The chip's `title` and aria-label keep the full title.
  At 960 and narrower the chips keep the number only, as today.
- Empty tiers: with one or more items, all four tiers show. An empty tier keeps its heading, count 0
  and one `.empty` line: "Nothing is blocking work.", "Nothing has a deadline.", "Nothing else is
  waiting.", "No pick stands." The rail keeps its heading with 0, greyed, with no chip row.
  Cost: about 80px more height on a phone rail.

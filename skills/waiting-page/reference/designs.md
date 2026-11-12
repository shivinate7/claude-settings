# Designs

Read this when an option needs a mockup picture, or when a design is added to an item.

## Add a design

A question about how something looks carries one design per option. The owner picks by looking, so
a link to a folder, a repo, a file or another artifact does not count. The Designs tab pages through
every mockup whose question is open. Each option's picture sits at the top of its
own option card. A tap on an option's picture opens the viewer. A tap on the rest of the card
picks the option. A "View" control, 40px or more high, sits in a row under the picture. It never covers the picture. A design that no option names shows at the front
of the item, before the options. An option that names a design (`design`) which the item does not
carry shows a warning line in its card in place of the picture.

Each option gets its own mockup, drawn in that option's state. Two options never show the same picture with the same `focus`.
The page refuses an item where they do, or where a `focus` finds nothing.
The guard runs `check_designs.mjs` on the published page at each item write that carries a design, and refuses a write the page would refuse or draw as a strip (rule `page-item-design`, decision `page-item-design`). Republish the design first: the check reads the page you last published.

1. Draw each option on the first device of the repo's app kind: the Duo folded for an iOS app, a
   phone width for a web app. Draw it at the width of the first device that
   `python3 ~/.claude/lint/layout.py devices <repo root>` prints. Where it prints `unknown` or no
   size, draw at the page's default width (`FIT_W` in `page.html`; read it once with
   `grep -n 'const FIT_W' <skill folder>/page.html`) and leave `drawn` unset. Set `drawn` whenever
   you draw at another width. The page grows it to the card's width, at most 2x. It draws whole up to the larger of 480px
   and the height of a 390 × 844 phone picture at that width, plus 1px. A taller picture scrolls in the card's 480px box. The full mockup stays one tap away ("Open full size").
2. Put a "Sample" banner at the top of each mockup: it says that no figure on it is real. Label
   what exists with a dashed "Today: <part>" and what the option adds with a dashed "New: <part>".
   Put the whole mockup in one HTML string. Write `<` as `\u003c`.
3. Build the new page as "Keep the page on main's code" steps 1 and 2 say, from the saved live page:
   `<out>` keeps the live roadmap block with the live designs. In `<out>`, add `"slug": "<html string>"` to the JSON in
   `<script type="application/json" id="designData">`, and change nothing else. Never edit the live
   page's own code.
4. Add `designs: [{slug, label, file}]` to the item, one per option, and set `design: "<slug>"` on each option.
   - Every design carries `file`, the path of its mockup file, in the repo's design folder (`docs/design/<item folder>/<file>`). Write the mockup there
     first, then commit and push it: git is its home. A machine-home path (`~/Developer/<repo name>-imports`), a path in a Claude app folder,
     such as `side-session-notes`, or a link is refused: an account switch loses it (guard rule `mockup-home`, decision `mockup-home`).
   - A design may carry `focus`, a selector of an element inside the mockup. The option card then
     shows that element, scaled to fit the card, so the part being decided is in frame.
     Without `focus` the card shows the whole mockup. Either way the picture grows to the card's column less its border, at most 2x its own width. It draws whole while its height at that width is at most F plus 1px. F is the height of a 390 × 844 phone picture at that width, and never less than 480px. A taller picture draws 480px high and scrolls in its box, and opens at the top of what the card shows. A picture that scrolls at the column's width gives up its scrollbar's gutter. At that narrower width, if its height is at most 481px (480 plus 1px), it draws whole with no scrollbar. Otherwise it scrolls at that width. A scrolling picture is as wide as the column less its border and scrollbar, or 2x its own width when that is less. Examples: a 390 × 600 design in a 358px column never scrolls and draws 356 × 548. A 390 × 980 design in a 202px column with a 10px gutter draws whole at 190 × 478. A 390 × 900 design in a 202px column has a phone height of 433 at 200px wide, but F is 480, so it draws whole at 200 × 462. Set `focus` on each design to the element
     being decided, such as the late-package row with its buttons.
   - A design may carry `size` (`{w, h}`, the size in mockup pixels of what the card shows: the
     focused element, else the whole mockup). The card reserves that height before the mockup loads,
     so the first paint does not jump.
   - A design may carry `drawn` (a number, the width in mockup pixels it is laid out at; default `FIT_W` in `page.html`).
     The page draws the mockup that wide and scales it to the width it has, so a 1200 wide design
     shows whole. Set it on any design wider than a phone.
   - A design may carry `option` (an option's `key`) and `width` (a name such as `Wide`). Each extra
     width of an option is one more design with that `option`. The first design of an option is its
     picture on the card.
   - A design may carry `state`, a slug such as `late-package`: the state of the mockup this picture shows. The mockup side of the contract: the mockup reads `#s=<state>` from its URL hash on load and on `hashchange`, and draws each state as an element with `data-state="<state>"`. The page opens the picture at that state, in the card frame and the viewer, and adds the state to the viewer title. The viewer's "Open this state" opens the mockup at that state in a new tab. The button on a front preview opens the viewer at that design. A `state` that no `data-state` element in its mockup carries blocks the item, with a line that names the option. Two options may share one mockup and differ by `state`: give each such design its `option` key.
   - The viewer lists every option's designs at every width, in option order. Its label reads
     "<option title> (<width name>)", with "N of M", Prev, Next and "Open full size". Prev and Next
     wrap at the ends. A width with no name reads `Phone`.
5. Run the `--check` of "Keep the page on main's code", step 4, on the built page. Then republish it to the same URL with the same capabilities. Whether the database stays
   is unmeasured until the step 4 live check of "Update a repo's pages".
   A republish replaces the whole page, so run this step in one session at a time. A second session
   that read the page earlier would overwrite the first one's mockups. A lane never does this step:
   triage does (see "Add an item").

The mockup leaves the page when its question closes and the page is next republished. The page
holds 16 MB, so about 300 mockups of 50 KB fit. A frame cannot show another artifact.

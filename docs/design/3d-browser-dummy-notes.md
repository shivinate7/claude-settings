# 3D browser dummy: design notes

Mockup: `docs/design/3d-browser-dummy.html`. Designer kind: informed. A learning dummy, not a product.
It draws the Cockpit's items and roadmap steps as objects in one 3D scene. Owner rulings: page item 130
pick a (browser 3D, three.js and glTF); page item 277 pick a, 2026-11-06 12:43 CST (a separate test copy
at a new artifact URL, never the live page). The mockup is a static sketch in SVG. It loads no three.js
and opens from disk with no network. The builder draws the same scene with three.js.

Data: `docs/plans/3d-browser-dummy/sample-data.json`, compacted inline. Item 254's session link is
replaced with words, so no session id sits in the mockup.

Deep links: `#s=overview|pick-one|pick-multi|pick-none|pick-task|pick-closed|pick-step|loading|nowebgl|lost`,
`&map=floors|kinds`, `&det=under|over`, `&v=all|items|roadmap`, `&w=390|1440|all`, `&t=light|dark`,
`&lab=off`, `&hide=<option id>,...`. Each design option has a Hide control in the toolbar.
Focus element for an option pick: `#scene`.

## Sizes and themes

- Devices: `lint/layout.py devices` gives `unknown` for this repo, so the mockup draws at the brief's
  sizes: phone 390 and desktop 1440.
- Frame breakpoint: 960 px, the Cockpit's own. Wider: scene column beside a 360 px detail column.
  Narrower: one column, in this order: view switch, scene, detail, legend, list.
- Themes: light and dark. `data-theme` on the root sets one; `prefers-color-scheme` sets the default.
- Check, headless Chrome: 10 states x 2 mappings x 2 phone-detail options x 2 themes, at 390 and at
  1440 (160 frames). Each frame: no horizontal scroll in the harness or in the screen, no element past
  the right edge, no label pill outside the scene box, script ran. Verdict: pass, 160 of 160.
- Per size and theme, by eye: phone light pass, phone dark pass, desktop light pass, desktop dark pass.

## Tokens reused from the Cockpit (`skills/waiting-page/page.html`)

- The three `:root` blocks as written: `--surface`, `--ink`, `--muted`, `--line`, `--chip`, `--ground`,
  `--calm`, `--good`, `--acc`, `--acc-soft`, `--gold-soft`, `--gold-ink`, `--hdr`, `--on-hdr`, `--r`,
  `--body`, `--mono`. The `--r-*` repo-colour hooks stay, so a repo colour reaches the scene too.
- Looks as written: `.hdr` and `.mark` (repo bar), `.g.calm` and `.g.done`, `.card`, `.title`, `.key`,
  `.pick` with the sparkle, `ol.steps`.
- Looks changed: `.views` has 3 columns, and its pressed button shows by a border, not a shadow (forced
  colours drop shadows). `.opt` has no pointer, because nothing is picked here. `.top` adds `.st`, the
  status word with its shape. `.g.doing` and `.g.todo` are new shapes.
- New tokens, made only by `color-mix` of the tokens above: `--o-*` (open item, doing step faces),
  `--c-*` (closed item faces), `--d-*` (done step faces), `--p-*` (floor), `--edge`. No new hue. Dark
  sets keep the top face lightest, so light still reads as coming from above.
- Frame width: 1320 px, not the Cockpit's 1160. The scene needs the width. Departs from: `.in`
  max-width in page.html. Not blocking.

## 1. Scene mapping: what each object is

Two object types only: an item is a stack, a roadmap step is a tile. One slab in a stack is one option
(decision) or one step (task), so a reader counts slabs to see the size of an item. Rank sets the order
on the floor (rank 1 first, then newest, as the Cockpit's `byRank` sorts), never the height. Item 257
has rank 30 and every other item has 1 to 4; height by rank would flatten the rest.

- Status floors (pick), `#map=floors`: open items stand on a raised floor in front; closed items sit on a
  dashed shelf behind it, grey with a check. Kind shows by shape: square stack is a decision, round
  stack is a task.
  Gain: the first split a person wants (what is still open) is the biggest thing in the scene. The
  numbers stay readable on a phone at the fitted zoom. Loss: two stack shapes to learn.
- Kind floors, `#map=kinds`: one floor for decisions, one for tasks. Closed items sit on a dashed shelf
  behind each floor. All stacks are square.
  Gain: one stack shape. Loss: open and closed split twice, so the scene is wider; on a phone the fitted
  zoom is too small for the number labels until the person zooms in.
- Pick: Status floors.

## 2. Roadmap steps: a path of tiles by phase

- Steps run in one snaking path, seven tiles a row, sorted by phase and then by order. The phase order
  is each phase's first order value: cleanup, rollout, later. A tall post marks where each phase
  starts, with its name and step count. A dotted line joins the tiles.
- Status by shape and colour: doing is a raised tile in the accent; to do is a flat dashed outline; done
  is a flat tile in `--good` with a check. Same shapes in the list (`.g.doing`, `.g.todo`, `.g.done`).
- Tiles are placed by their index in the sorted path, not by the order value (the values cluster at
  103.21xxx).
- Data note: `cloud-refresh-clone` is a done cleanup step with order 309.5, so it lands last in
  cleanup. The mockup draws the data as it is.
- Gain: the whole roadmap reads as one route with a start and phases. Loss: step names are not on the
  tiles; the picked tile's name shows in its label and the detail.

## 3. Labels

- Floor and phase names always show. Item numbers show as small pills when the zoom leaves 20 px or more
  per world unit; below that, only the picked object has a label. The picked object's label gives its
  number and short name (item 91 has no short name, so the title stands in).
- Step tiles carry no label until picked.

## 4. Picking and the detail

- A press on a stack or tile picks it. The object lifts and gets a dark outline and a dashed ground
  ring (a shape cue, not only colour). Its label names it.
- The detail is the Cockpit's card, read-only. A decision shows its options with the `.pick` box: one
  pick (`#s=pick-one`, 277), several picks with "Also my pick." (`#s=pick-multi`, 279, all four), no pick
  with "No pick from me on this one." (`#s=pick-none`, 278). A task shows its steps (`#s=pick-task`,
  273). A closed item says it closed on the Cockpit (`#s=pick-closed`, 269). A step shows its place
  in its phase and on the path (`#s=pick-step`).
- Each card says "This copy only shows. Answer it on the Cockpit." Buttons: Center on it, Clear.
- Nothing picked (`#s=overview`): counts of open and closed items and steps by status, and one action,
  Show the top item (`ux-empty-one-action`).

## 5. Where the detail sits on a phone

- Under the scene (pick), `#det=under`: the card follows the scene box.
  Gain: the scene stays whole; the label in the scene already names the picked object. Loss: the
  options or steps need a scroll.
- Over the scene, `#det=over`: the card covers the lower 56% of the scene box and scrolls inside it; the
  scene pans so the picked object sits in the strip above.
  Gain: pick and read with no scroll. Loss: half the scene is covered while something is picked; a
  scroll area inside a scroll area.
- Pick: Under the scene. Desktop always uses the side column.

## 6. Moving the camera

- Fixed tilt, a turn about the vertical axis, and a zoom. Few controls, so it stays learnable.
- A sideways drag turns. An up-and-down swipe scrolls the page (`touch-action: pan-y`), and a plain wheel
  scrolls the page; Ctrl and wheel, or a pinch, zooms (`ux-scroll-stays-native`). The + and - buttons
  zoom for one hand and for the keyboard. Reset puts the camera back.
- View switch: All, Items, Roadmap. It refits the camera to that group. Default: All on desktop, Items on
  a phone, so the item numbers fit.
- The builder uses three.js `OrbitControls` with the polar angle locked and `enablePan` off, and draws
  on demand only (`ux-still-scene-draws-nothing`).

## 7. Words for the scene, and the keyboard (`ux-canvas-has-words`)

- The scene box has a name: "3D view of 20 items and 24 roadmap steps. Arrow keys move between
  objects. The list below holds the same." The canvas inside is hidden from assistive technology.
- Keys on the focused scene: arrows move the pick through the list order, Home and End, `[` and `]`
  turn, `+` and `-` zoom, Esc clears. The hint swaps to the keys while the scene has focus.
- The plain list holds every item and step, grouped as in the scene. Each row is a button that picks the
  same object, so list and scene stay in step. The detail column is a polite live region.

## 8. When the scene cannot draw

- No WebGL (`#s=nowebgl`, `ux-works-when-script-fails`): a short notice takes the scene's place and
  says what is missing; the view switch and legend go; the list and the detail carry the page.
- Scene lost (`#s=lost`, `ux-lost-scene-recovers`): words over the dimmed scene, the list still works,
  and "Draw it again" restores it. The builder also restores on `webglcontextrestored`.
- Loading (`#s=loading`): "Drawing the 3D view" with the list already usable.
- Loading and lost hide zoom and the hint and turn off the view switch, so no control does nothing.

## 9. Other house rules

- `ux-full-height-fits`: the scene height sets `vh` first, then `svh`.
- `ux-forced-colors-hold`: the pressed view button and the picked list row show by a border or outline,
  not only by a shadow.
- The detail column keeps its own position under the sample labels (harness CSS sets position on
  labelled elements).

## 10. Departures from the Cockpit (a port, per page item 277); none blocking

- Departs from: the Cockpit's answer flow (`buildCard` in `skills/waiting-page/page.html` draws options as
  inputs, with a note box and the send bar). The test copy only shows; each card says to answer on the
  Cockpit. Why: item 277 makes it a separate test copy, never the live page, so an answer here would
  have no reader.
- Departs from: the Cockpit's tiers (holds, due, calm, stands; page.html sorts items into the
  buckets `by.holds`, `by.due`, `by.calm`). The scene groups by open and closed. Why: the sample data carries no `holds`, `by` or `stands`
  fields. With real fields, the builder keeps the tiers as floors in tier order.
- Departs from: the meaning of the ring shape. On the Cockpit `.g.calm` marks the calm tier; here it
  marks "open". The builder keeps the Cockpit's tier shape once real tier fields exist.

## 11. Option files for the owner page (skill waiting-page, "Add a design")

One file per option, each drawn in that option's own state, with its own Sample banner and the dashed
Today and New labels. Each file is one self-contained HTML page with no frame inside, so a `focus`
selector reaches the part being decided. `#t=dark` or `#t=light` in the hash sets the theme; with
none, `prefers-color-scheme` does.

| Question | Option | File | State drawn | `focus` | Widths |
|---|---|---|---|---|---|
| Scene mapping (item 1) | Status floors | `docs/design/3d-browser-dummy-layout-a.html` | nothing picked | `#scene` | 390 (default), 1440 (`drawn: 1440`) |
| Scene mapping (item 1) | Kind floors | `docs/design/3d-browser-dummy-layout-b.html` | nothing picked | `#scene` | 390 (default), 1440 (`drawn: 1440`) |
| Phone detail (item 5) | Under the scene | `docs/design/3d-browser-dummy-phone-a.html` | item 279 picked | `#pickview` | 390 |
| Phone detail (item 5) | Over the scene | `docs/design/3d-browser-dummy-phone-b.html` | item 279 picked | `#pickview` | 390 |

- `#scene` is the scene box. `#pickview` wraps the view switch, the scene and the picked card; it
  exists only in the two phone files (config `wrap`).
- Each file's static markup holds `<div id="screen">` with its focus element in it, and the script
  renders into `#screen`. The owner page checks `focus` by parsing the file with no script
  (`pictureProblem` in page.html), so the focus must be in the static markup.
- The four files are copies of this mockup's `#screencss`, `#screenjs` and `#data` blocks, with each
  option's config. Reason for the copies: the owner page takes each option as one HTML string. A change
  to the main mockup needs the four files rebuilt.
- Check, headless Chrome, light and dark: layout files at 390 and 1440, phone files at 390. Each has
  no horizontal scroll, its banner and labels, and a `focus` element with a size. Verdict: 12 of 12
  pass.

## Not drawn

- Forced-colours captures and a screen-reader pass: hand checks for the built page.
- The three.js scene itself: the SVG stands in for it.

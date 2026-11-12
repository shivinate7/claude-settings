# Health tab: design notes

Mockup: `docs/design/health-tab.html`. Screen: `skills/waiting-page/page.html` (the Cockpit), drawn at
2deb827ad. Goal: the owner can see what he built and how well each part works.
Data: the health map draft of Nov 11 (20 rows, read at main c85a832e2). Every figure in the mockup is a
sample. The build re-measures each one.
Sizes: 320, 390, 800 and 1280, light and dark, for each of the 5 states. 390, 800 and 1280 are
one-page-notes' sizes. 320 checks the tab row. The repo's device list is unknown
(`layout.py devices` prints "unknown"). A headless Chrome run read each frame: none of the 40 renders
scrolls sideways.

## States and deep links

| State | Deep link | What it draws |
|---|---|---|
| `tab` | `#s=tab` | Pick. Health as a third top tab, with rows grouped by stage. |
| `view` | `#s=view` | Option. Health as a fifth view inside Status. |
| `flat` | `#s=flat` | Option. The Health tab with rows in the draft's order and no groups. |
| `unknown` | `#s=unknown` | The Health tab when the build could not read the parts list. Coverage shows "unknown", not 0. |
| `nomap` | `#s=nomap` | The Health tab when the page has no health map: unknown, why, and one control. |

Add `&w=all|320|390|800|1280`, `&t=light|dark`, `&lab=off`, and `&hide=tab,view,grouped,flat` to hide
an option. The choice sits on `#healthTab`, `#healthViewBtn` and `#healthTable`.

## Design choices

1. Where Health sits. Pick: a third top tab, "Health". Owner grant: yes.
   - Health tab (pick): Questions, Status, Health in the tab row. Gain: it answers a different
     question from Status. Status says what is moving now. Health says how well the parts are built.
     One press from any tab. The tab carries the broken mark and count (3), so a broken part shows from
     every tab. It fits a 320 phone: with Designs shown the bar is four tabs, and they keep one row at
     every width. Below 500 px the padding, gaps and reserved count boxes shrink, and below 400 px the
     label shrinks too (`.tabs:has(#tabD:not([hidden]))` rules in page.html). Designs does not wrap above.
     Each tab stays 44 px tall. Loss: one more tab.
     It changes the one-page ruling (Oct 27, 12:15 CDT; `one-page-notes.md` item 2), which names
     Questions, Status and Designs.
   - Health view in Status: a fifth button after Records. Gain: no new tab. It reads the roadmap
     block that Status already reads. Loss: it sits under the stalled band, Live work and the plan band,
     so on a phone the table starts a long scroll down. Five buttons do not fit the 4-column view switch
     under 560 px; they wrap to two rows (`.views`, page.html; the "Reference" cut rule under 340 px).
     Status and Health would show two read times. The mockup drops Health's own stamp in this option.
   - Departs from: page.html `#tabs` (two tabs and the Designs button).
2. One name for "Health". The build keeps the Records Health card (repo map, compliance scores, session
   board) and the Health tab shares the name; Records loses nothing. Coordinator ruling, 2026-11-12
   11:36 CST. The first pick moved the card to the tab, so Records kept the record kinds only. Its
   three lines are sources of rows 17 and 18. Gain: no change to the roadmap skill's "Records and
   health" section. Loss: two places carry the word "Health" (`ux-one-plain-name`). Departs from the
   mockup: it does not draw the card. Stays as is: page.html `renderRec` ("Health" card) and
   `skills/roadmap/build.py` `health()`.
3. The tab shows only when the build holds a health map, as Designs shows only with a design
   (`ux-control-earns-place`). Another repo with no map gets no Health tab. claude-settings with an
   unread map shows the tab and `#s=nomap`, never an empty table (`ux-unknown-is-not-empty`).
4. Grades: shape and colour, never colour alone. Pick: four marks drawn as inline SVG in
   `currentColor`, so forced-colors mode keeps the shape.
   - Broken: a filled octagon with a cross, `--holds`.
   - Has issues: a ring half filled, `--due`.
   - Not measured: a dashed ring, `--muted`.
   - Healthy: a filled ring with a check, `--good`.
   Gain: no mark reuses a Questions shape with a new meaning. The square, triangle, ring, dot and
   diamond stay Questions'. The check ring keeps its "done, nothing to do" meaning. The dashed ring
   keeps its "unknown" meaning. Loss: the half ring is new and needs the key once.
   Departs from: page.html `.rg.unk`, which draws unknown in `--due` (amber). Here unknown is grey, as
   the brief says. Amber on the page then means two things. Question: should `.rg.unk` turn grey
   everywhere?
5. Each grade word shows once, in the key, with its mark and count (`ux-label-once`). A row shows the
   mark only, plus a screen-reader word. The key is the status summary: it names each grade with a
   count, Healthy 0 included, because the key also decodes the marks (`ux-all-is-well` departs here:
   the key keeps the 0).
6. Columns: What you see, Why this grade, What makes it happen, What good looks like. The gold column
   follows rule `style-table-gold-column`. Why and gold sit side by side at 800 and 1280, so each row
   shows its gap. Gold lines are proposed targets. Owner grant: yes (each gold line sets a target).
7. Phone and tablet. Pick: the table becomes one card per row by container query on `.svwrap`, at
   999 px and 559 px (`ux-component-reads-its-box`). Under 1000 px the head hides. A gear marks "what
   makes it happen" and a target marks "what good looks like". Their words show once, in the key.
   Gain: no sideways scroll at 320, and no word repeats 20 times. Loss: 20 cards make a long phone
   page. Build note: the table keeps explicit `role` values. WebKit drops a table's roles when its
   `display` changes.
8. "What makes it happen" shows hook, check and skill names in mono, open, not behind a disclosure.
   Gain: the owner wants to learn what he built, and the names are that answer. Loss: machine text on
   the screen. Departs from: `ux-machine-text-hidden` (guidance).
9. The exhaustive line. "The rows name 38 of 57 hooks, checks, skills, janitor scripts and merge
   scripts." A closed disclosure lists the parts named by no row, by kind. The count comes from
   `lint/check_health_map.py` `find_parts`, the check's own list (`building-one-home-per-capability`):
   the hooks, the check scripts, the skills, and the scripts in `janitor/` and `merge/`. Helpers
   (`guard_core.py`, `_*.py`) and `test_*` files are left out. The build names each kind that has a
   part in the sentence. With the list unread, the line says "Coverage: unknown" with a grey dashed
   ring (`#s=unknown`). Question: count the 5 mods too?
10. Fails with no record. A band above the table names the 4 rows whose check breaks with no word
    (rows 3, 5, 11, 20), each a link to its row. An eye with a slash marks those rows. Gain: the
    draft's blind spot gets its own place. Loss: one more band above the table.
11. Order. The build keeps the Records Health card and sorts the rows flat, worst first (broken, has
    issues, not measured, healthy), in the draft's order inside a grade. No stage groups. Coordinator
    ruling, 2026-11-12 11:36 CST. The first pick grouped rows by stage; option `#s=flat` drew the flat
    list. Gain: the worst rows come first, and 14 of 20 rows are amber, so the order inside amber is
    the draft's. Loss: the table does not read as how the work flows.
12. Copy. The draft's shorthand turns into short sentences: "159/14" reads "159 changes in 7 days; 14
    were fixes". Ids are dropped or glossed: a message id becomes "one message", a decision name
    becomes "by your ruling", and a lane or step id is dropped. Times are US Central, 24-hour, CST in
    November.
13. Read time. "Measured Nov 11, 16:40 CST" sits in a closed disclosure, as the Status tab's read
    stamp does (`one-page-notes.md` item 9). Inside: the commit and how changes are counted.
14. Data home. The roadmap build already writes `health` into its block (`build.py` `health()`).
    Pick: extend that key with the rows, so the page writer still publishes one block
    (`one-page-notes.md` build constraints 5 and 6). No new block.
15. A load still opens Questions (`one-page-notes.md` item 5). The answer bar stays on the Health tab,
    as on Status (item 7). The mockup does not draw the bar.

## Critique (impeccable, single context: no sub-agent tool)

- Fixed: the view option showed two read times. Health's own stamp is dropped there.
- Fixed: the coverage sentence was a flex row, so "38 of 57" had wide gaps. It is plain text now.
- Open: 14 of 20 rows are amber, so amber does not rank them. The build sorts worst first (item 11).
- Open: on a 390 phone the 20 cards make a long page. Folding each card to its name and why is not drawn.
- The detector found nothing. It reads markup, and the screen here is built by script, so a clean
  result is no evidence.

## Input needed

- Items 1, 2 and 6: `Owner grant: yes`.
- Item 4: should the page's unknown ring turn grey on every tab?
- Item 9: should the count include mods?
- Critique: should phone cards fold?

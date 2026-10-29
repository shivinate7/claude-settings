# One page per repo, lane c136: design notes

Mockup: `docs/design/one-page.html`. Screens: `skills/waiting-page/page.html` and
`skills/roadmap/page/index.html` (main 1cc47f01).
Ruling: the owner, Oct 27 12:15 CDT. One page per repo, with one writer. "Waiting on you" comes
first. Status sits below it or in a tab. The two-page proposal is dropped.
Rulings for this round (orchestrator, inside the owner's ruling): the waiting-page writer alone
publishes the page file, and the tab row always shows.
Sizes: phone 390, mid 800, wide 1280, light and dark. They are the sizes of `waiting-page-notes.md`.
The mockup draws the waiting part with the `<style>` of page.html, unchanged.

## States and deep links

| State | Deep link | What it draws |
|---|---|---|
| `main` | `#s=main` | Questions tab: all four tiers, one group frame, one answered card. |
| `status` | `#s=status` | Status tab: read-at stamps, live work, the plan band, the view switch, the Plan view. |
| `empty` | `#s=empty` | No item waits: the tab row with Questions 0, and one line. |
| `no-status` | `#s=no-status` | Status tab of a repo with no roadmap: unknown, why, and one control. |

Add `&w=all|390|800|1280`, `&t=light|dark` and `&lab=off`. Each state is an element with
`data-state` in the file. In a frame, the Questions and Status tabs open their states.

## Design choices

1. Below or tab. Pick: tab.
   - Below: status sits under the last tier. Gain: no press, and status is never hidden.
     Loss: on a 390 phone, status sits under many tall cards. A live item, a receipt or a group
     that arrives moves status while the owner reads it (`ux-press-moves-nothing`). The roadmap's
     own rail and view switch would sit in a long scroll, under the waiting rail.
   - Tab (pick): Status is the second link in the tab row that main already has.
     Gain: the owner sees what waits first, because each load opens Questions. Status is one press,
     always at the same place under the header, so he does not hunt for it. Each part keeps its
     own frame, and a change in one part moves nothing in the other. Main's tab row is extended,
     so the page gets no second tab home. Loss: status is one press away, and it is hidden until
     he presses.
2. The tab row always shows: "Questions" with its open count, then "Status", then "Designs" when an
   item has a design. Gain: Status never moves, the count shows what waits from either tab, and an
   item that arrives moves no tab. Loss: main hides the row when no item has a design.
3. Status shows only behind its tab, on every load and in every state. Ruling: orchestrator, round 2.
   Nothing waits (`#s=empty`): the tab row shows "Questions 0", and the Questions tab shows one
   line. When an item arrives, its card takes the line's slot. Nothing else moves
   (`ux-press-moves-nothing`). The page has one layout.
4. The empty line is one sentence: "Nothing on this page waits on you." A thread that asks in its
   own chat has no item on this page, and Live work names it "asking in its chat", so both stay
   true (`ux-statements-are-true`). Departs from: page.html `renderList`, which says "Nothing is
   waiting on you right now."
5. A load always opens Questions. The page does not keep the tab choice. The roadmap's own view
   memory (`rm-view`) stays for Plan, Changes, Reference and Records. Gain: what waits is first,
   each time. Loss: the owner who reads status first presses once on each load.
6. The status part has one name: "Status". The tab and the document title use it. On the Status
   tab the header shows the repo name only, with no "waiting on you". On Questions the header and
   title are as on main.
7. The answer bar stays on the Status tab. Gain: a pick is never left behind, nothing moves at a
   tab change, and the bar says how many items wait. Loss: the bar shows under status, which it
   does not change.
8. Order in the status part: read-at stamps, live work, the plan band, the view switch, then the
   view. The phase rail moves into the Plan view. Gain: nothing sits between the view switch and its
   view (`ux-control-beside-area`). Loss: the Changes, Reference and Records views lose the phase rail.
   Departs from: `skills/roadmap/page/index.html`, `#now`, `#stamps`, `#live` and `#rail` sit
   between `.tabs` and `.view`.
9. Read-at stamps sit in a closed disclosure. Its summary is "Read Oct 29, 13:10 CDT". Gain: paths
   and commit ids are machine text (`ux-machine-text-hidden`). Loss: one press to see each panel's commit.
   Departs from: the stamps block (`#stamps`) in the `build:script` of the roadmap page, which shows them open.
10. A live thread that waits on the owner shows "asking in its chat". Gain: "Waiting on you" stays
    the name of the first part only (`ux-one-plain-name`), and the words say where the ask is.
    Loss: the word differs from the thread list. Departs from: `NAME.blocked` in the live work block
    of the `build:script`.
11. One token set and one font: page.html's. Times are US Central, 24-hour, with the zone, as
    page.html's `fmt`. Gain: one page looks like one page, and the repo colour from `meta/page` reaches
    status. Loss: the roadmap's own colours and IBM Plex Sans go.
    Departs from: the theme token block and `when`, `dayLabel`, `timeLabel` in the roadmap page.
12. No theme switch and no roadmap brand bar. The page follows the system theme, as page.html does.
    Gain: one header. Loss: the owner cannot force light or dark on this page.
    Departs from: `applyTheme`, `#modeSeg` and `.brand` in the roadmap page.
13. No roadmap (`#s=no-status`). The Plan view says "Plan: unknown", why, and that the questions are
    not affected. The build's text is in a closed disclosure. One control copies an ask to start a
    roadmap (`ux-no-dead-end`). The roadmap's `unavailable()` text is not used: it says to open the
    page on claude.ai while signed in, which is false here (`ux-statements-are-true`). The read-at
    summary and Live work show a dashed ring and plain words, so "unknown" shows once.
14. Each state word and label shows once (`ux-label-once`):
    - In "Latest changes" and "Off track", a step's state is its mark, with its name for a screen
      reader. The step row keeps the word, as the roadmap does today.
    - The phase card says "Phase 2". The rail button names the phase. The phase card, the tiles and
      the running total show counts as `3/9`, with the words for a screen reader.
    - Departs from: `renderPhase` and `metaTiles` in the roadmap page, which repeat the name and "of".
    - A step row has no "Now" tag and no thread tag. The row's mark and fill show that it is in
      progress, "Doing now" names it, and Live work counts the threads. Departs from: `stepRow`
      (`t-now`) and the live work block's `tag()` in the roadmap page.
    - `python3 lint/label_once.py` on the 24 rendered files (4 states, 3 sizes, 2 themes) at
      commit time printed no line and exited 0 (`exit=0`).
15. Each disclosure (read-at, Live work, "What the build said") shows an open or closed marker, ▸ or ▾.
16. The status part reads its box. Its 640 and 1000 breakpoints are container queries on its
    wrapper, not the media queries of the roadmap page (`ux-component-reads-its-box`).
17. The waiting part is main's, with no change. The order in each tier is the writer's `rank`, then
    age, as main's `sorted()` gives it. Card details that other lanes change now are not drawn.

## Roadmap parts not drawn

Each part below is kept as it is today, with no change. The mockup does not draw it.
- The Live work body: the thread list, the open pull requests and the branches.
- A step row's open body: Status, Why, Note, Ask with Copy, and When.
- The Changes view (all changes by day), the Reference view and the Records view.
- The jump links in the feed, the 5-day chart, the pager, and the clean-up trend card.

## Build constraints

1. Live data stays live. The waiting part reads and writes the artifact database
   (`window.claude.use("db")`). The status part reads only a baked global of its own. It never
   reads `window.ROADMAP_DB || window.claude`: with no record branch, the build writes
   `ROADMAP_DB = null`, and that fallback then reads the live database. No baked data means status
   is unknown (`#s=no-status`).
2. Both parts use a collection named `meta`: the roadmap reads `meta/phases`, `meta/cull` and
   `meta/advisor`, and the waiting part reads `meta/page`. The roadmap data stays in its baked
   global. It is never written to the live database.
3. The page publishes to the waiting page's URL, whose database holds the answers.
4. Saved answers survive each republish. The builder writes this test first in
   `skills/waiting-page/tests/page.test.mjs`, and shows it red on the old code. It runs in CI
   against a stubbed database: build the merged page, republish it over a page whose database holds
   `answers/<id>`, then check that the answered card shows. The test also checks that nothing
   writes or deletes a document in `answers/`. The live check runs once per batch, as step 4 of
   "Update a repo's pages" in the waiting-page skill says: update one page first, then read its items.
5. One writer publishes the page file: the waiting-page writer. The roadmap build makes only a data
   block, in its own marked block, and gives it to that writer. The build never publishes.
6. Before each publish, the writer reads the live page. It replaces only the marked block that it
   changes: the `designData` block or the roadmap block. It keeps the other block. It runs one
   publish at a time, never with `force`. It keeps the capabilities `db` and `{comments: {}}`.
7. `stale_pages.py` compares each page with the merged template, with the `designData` block and the
   roadmap block made empty on both sides. A republish of a page that is behind keeps both blocks.
8. The old roadmap page retires. The roadmap skill publishes no page by itself. The repo's extras
   key for the roadmap points at the waiting page's URL. The old roadmap URL gets no more publishes.
9. The roadmap's class names that page.html also uses are scoped or renamed: `.bar`, `.rail`,
   `.card`, `.tabs`, `.steps`, `.g`, `.top`, `.big`, `.sub`, `.empty`. The page loads no font for
   status.
10. Status is read only, as the baked roadmap is today. The step mark is not a control, and the
    hint says "Read only".

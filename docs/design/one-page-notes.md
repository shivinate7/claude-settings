# One page per repo, lane c136: design notes

Mockup: `docs/design/one-page.html`. Screens: `skills/waiting-page/page.html` and
`skills/roadmap/page/index.html` (main 1cc47f01).
Ruling: the owner, Oct 27 12:15 CDT. One page per repo, with one writer. "Waiting on you" comes
first. Status sits below it or in a tab. The two-page proposal is dropped.
Sizes: phone 390, mid 800, wide 1280, light and dark. They are the sizes of `waiting-page-notes.md`.
The mockup draws the waiting part with the `<style>` of page.html, unchanged. The header is as on main.

## States and deep links

| State | Deep link | What it draws |
|---|---|---|
| `main` | `#s=main` | Questions tab: all four tiers, one group frame, one answered card. |
| `status` | `#s=status` | Status tab: read-at stamps, live work, the plan band, the view switch, the Plan view. |
| `empty` | `#s=empty` | No item waits: no tab row, main's one empty line, then status. |
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
2. Tab row: "Questions" with its open count, then "Status", then "Designs" when an item has a
   design. Gain: Status never moves, and the count shows what waits from either tab. Loss: the tab
   row now shows on every page that has an item. Main hides it when no item has a design.
3. Nothing waits (`#s=empty`). The page has no tab row. Main's empty line shows, and status follows
   under a "Status" heading. Gain: a tab with nothing behind it is not drawn
   (`ux-control-earns-place`). Loss: the page has two layouts. When an item arrives while status
   is in view, the tab row comes back with Status open, so status does not jump away.
4. A load always opens Questions. The page does not keep the tab choice. The roadmap's own view
   memory (`rm-view`) stays for Plan, Changes, Reference and Records. Gain: what waits is first,
   each time. Loss: the owner who reads status first presses once on each load.
5. The answer bar stays on the Status tab. Gain: a pick is never left behind, nothing moves at a
   tab change, and the bar says how many items wait. Loss: the bar shows under status, which it
   does not change.
6. Order in the status part: read-at stamps, live work, the plan band, the view switch, then the
   view. The phase rail moves into the Plan view. Gain: nothing sits between the view switch and its
   view (`ux-control-beside-area`). Loss: the Changes, Reference and Records views lose the phase rail.
   Departs from: `skills/roadmap/page/index.html`, `#now`, `#stamps`, `#live` and `#rail` sit
   between `.tabs` and `.view`.
7. Read-at stamps sit in a closed disclosure. Its summary is "Read Oct 29, 13:10 CDT". Gain: paths
   and commit ids are machine text (`ux-machine-text-hidden`). Loss: one press to see each panel's commit.
   Departs from: the stamps block (`#stamps`) in the `build:script` of the roadmap page, which shows them open.
8. A live thread that waits on the owner shows "asking you". Gain: "Waiting on you" stays the name
   of the first part only (`ux-one-plain-name`). Loss: the word differs from the thread list.
   Departs from: `NAME.blocked` in the live work block of the `build:script`.
9. One token set and one font: page.html's. Times are US Central, 24-hour, with the zone, as
   page.html's `fmt`. Gain: one page looks like one page, and the repo colour from `meta/page` reaches
   status. Loss: the roadmap's own colours and IBM Plex Sans go.
   Departs from: the theme token block and `when`, `dayLabel`, `timeLabel` in the roadmap page.
10. No theme switch and no roadmap brand bar. The page follows the system theme, as page.html does.
    Gain: one header. Loss: the owner cannot force light or dark on this page.
    Departs from: `applyTheme`, `#modeSeg` and `.brand` in the roadmap page.
11. No roadmap (`#s=no-status`). The Plan view says "Plan: unknown", why, and that the questions are
    not affected. The build's text is in a closed disclosure. One control copies an ask to start a
    roadmap (`ux-no-dead-end`). The roadmap's `unavailable()` text is not used: it says to open the
    page on claude.ai while signed in, which is false here (`ux-statements-are-true`).
12. In "Latest changes", the status mark alone carries a step's state, with its name for a screen
    reader. Gain: "Done", "In progress" and "Blocked" show once on the page (`ux-label-once`).
    Loss: a sighted reader reads the mark, not a word. `label_once.py` on the status state prints
    only "done", "of" and "organize", which are data.
13. The status part reads its box. Its 640 and 1000 breakpoints are container queries on its
    wrapper, not the media queries of the roadmap page (`ux-component-reads-its-box`).
14. The waiting part is main's, with no change. The order in each tier is the writer's `rank`, then
    age, as main's `sorted()` gives it. Card details that other lanes change now are not drawn.

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
4. A republish keeps the page's `designData` block and its capabilities: `db` and `{comments: {}}`.
5. The page now has two writers of its file. The roadmap build must keep `designData` and the
   capabilities. A waiting-page republish or a design add must keep the baked roadmap block.
   `stale_pages.py` compares a page with page.html, so it will see the merged page as different.
6. The roadmap's class names that page.html also uses are scoped or renamed: `.bar`, `.rail`,
   `.card`, `.tabs`, `.steps`, `.g`, `.top`, `.big`, `.sub`, `.empty`. The page loads no font for
   status.
7. Status is read only, as the baked roadmap is today. The step mark is not a control, and the
   hint says "Read only".

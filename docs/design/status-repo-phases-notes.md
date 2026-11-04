# Status tab: repo phases, design notes

Mockup: `status-repo-phases.html`. Sample data: degen (`v2`, 8 steps), home (`now`, `duo`, `owner`,
`later`; 49 steps), claude-settings (the five known phases plus `now`, `next`, `page`, `checks`, `ci`,
`merge`, `records`; 77 steps), and claude-settings with 2 steps that have no phase and a long
`meta.phases.ci.name`. Sizes: phone 390 (the brief's size) and wide 1280 (c193's size). Tablet 760 is
added to show item 4. This repo's device list reads "unknown". Themes: light and dark.

## Measured (headless Chrome, harness labels off, fallback fonts)

| Data | Width | Chips | Rows | Rail height | Clipped name |
|---|---|---|---|---|---|
| degen | 390 / 1280 | 1 | 1 | 58 / 48 px | none |
| home | 390 / 1280 | 4 | 2 / 1 | 120 / 48 px | none |
| claude-settings | 390 / 1280 | 12 | 4 / 3 | 244 / 157 px | none |
| with No phase | 390 / 1280 | 13 | 5 / 3 | 321 / 157 px | none |
| with No phase, today's CSS | 672 to 900 | 13 | 3 | 157 px | `ci`, over the next chip |

Each chip is at least 48 px tall. No width scrolls the page sideways.

## Items

1. **Phase order.** The known four phases that hold a step come first. Each repo phase id follows,
   in the order of its first step (`order`, then id). Then Later, then No phase.
   Gain: this needs no `meta.phases`, and the order follows the plan's own step order.
   Loss: a repo cannot reorder its phases without reordering its steps. The other way is
   `meta.phases` key order, which a repo with no meta cannot use.
   Pick: step order. Departs from: page.html `PH` (fixed five, shown even when empty). The brief
   rules on this change.
2. **Twelve or thirteen chips on a phone.** Keep today's grid: 5 columns from 464 px, 3 below.
   Gain: no new component. Every phase stays visible with its count and bar. Loss: on a phone, 13
   chips take 321 px. The phase box starts at 878 px, below the first screen (degen's starts at
   614 px). Other options: one row that scrolls sideways (a new component that hides most phases),
   or 4 columns on a phone (page.html's `.prail` comment says names break in the wide fallback
   font). Pick: today's grid.
3. **Long phase names.** Today `.prail .nm` is nowrap from 640 px. A `meta.phases` name such as
   "Continuous integration" runs over the next chip from 640 px to about 1000 px. New: the name
   wraps at its spaces, and the count drops below the name. Gain: no name hides. Loss: in that
   row, every chip is one line taller. Pick: wrap.
4. **One phase (degen).** Option "Rail of one": one chip at a fifth of the width. Option "No rail at
   one phase": no rail. The phase head already shows the count and the bar, and the Now strip shows
   the name. Gain: no control that changes nothing (ux-control-earns-place), and 63 px less above
   the steps. Loss: on the plan view, the name `v2` shows only in the Now strip.
   Pick: No rail at one phase. Departs from: page.html `renderRail` (it always draws the rail). Not
   blocking. Owner grant: yes.
5. **No phase heading.** Today a phase box is headed "Phase N". "Phase 13" would be false
   (ux-statements-are-true), so the heading reads "No phase", with no number. Loss: while that phase
   is shown, the words "No phase" appear twice, on the chip and in the heading. Pick: "No phase".
6. **Numbering.** "Phase N" and the Now strip's "N/total" count the numbered phases only. No phase
   is never the current phase.

## What the builder changes (page.html, Status script and CSS)

- Script: build `PH` from the steps as `phaseList()` in the mockup does (items 1 and 6). Do not use a fixed list.
  The name is `meta.phases[id].name`, else the known name, else the raw id.
- Script: `byPhase`, `shownPhase`, `goStep`, `phaseName` and the remembered `rm-view` phase read that list.
  No phase uses a key that no step id can take.
- Script: `renderPhase` heads No phase "No phase" with no number (item 5). `renderNow` uses the count of numbered phases.
- Script: `renderRail` leaves `#svRail` empty and hidden when the list holds one phase (item 4, only on the owner's grant).
- CSS, `.prail` (item 3), in place of today's nowrap name:
  `.prail .nm { flex-wrap: wrap; white-space: normal; }`
  `.prail .nm > span:first-child { overflow-wrap: anywhere; }`
  `.prail .nm .num { white-space: nowrap; }`
- Markup: no new element or component.

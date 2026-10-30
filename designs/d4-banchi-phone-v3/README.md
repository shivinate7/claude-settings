# d4 Banchi phone, v3

The test: does the designer make better-looking work when it loads `frontend-design` before it draws
and runs an `impeccable` critique on its own mockup before hand-off (waiting-page item 82 b, designer
skills, Oct 30 12:44 CDT)?

All data is sample data. Open each HTML file from disk.

## Shelf, the redraw (compare with v2's C2)

- `shelf-directed-3.html` and `shelf-directed-3-notes.md`. Directed lane: a redraw of v2's C2 Shelf, with
  the two new steps.
- `png/shelf-<state>-<folded|unfolded>-<light|dark>.png`: 24 states. States: empty, loading, full,
  error, keyboard, order.
- `png/shelf-option.png` is the one picture to compare with v2's `png/c2-option.png`.

## Corner radii (page item 94)

- `radius/png/shelf-r20-full-folded-light.png`, option a: the dock at 20 pt and the List button at 14 pt.
- `radius/png/shelf-r8-full-folded-light.png`, option b: both at 8 pt, the value in tokens.md.
- The two pictures differ only at the dock and List button corners and their dashed outlines. Each
  HTML file in `radius/` is the Shelf with one CSS rule changed.
- In the main Shelf file, state full shows 6 pt corners, because the `.ann` rule comes later and wins.
  The pictures above put their rule after `.ann`.

## Blind control

- `blind/phone-blind-3.html` and its notes. A blind lane drawn from the job alone, by the designer file
  on main, without the two new steps. The spawn hook needs a blind lane beside a directed one.
- `blind/png/blind-<a|b|c>-<light|dark>.png`: concepts A Tabs, B Shelf and C Route.

## Not measured

The unfolded Duo height (drawn at 644 pt), the unfolded insets, the folded top inset, and the place where
the system keyboard meets the fold.

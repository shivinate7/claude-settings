# c204-card-picture-scroll

Status: in build, round 1. Branch c204-card-picture-scroll. The designer's mockup and sizes have landed (docs/design/c204-scroll.html, docs/design/c204-sizes.md, head e878e5c1).
- Design picks: a picture taller than the 480px box scrolls inside it, with a "More" cue. A focus box larger than the card scrolls inside the focus box and opens at its top (1A). A drag scrolls; a tap opens View. The picture button stays the one tab stop, and View stays the keyboard route.
- The builder builds 5A, which keeps the 120px floor.
Deferred: two departures, not blocking, your call. 5B: a scrolling picture draws 221.8px wide (a phone picture's width), not 120px. The designer recommends it. It departs from fitFrame's scale and MIN_PIC. 1B: a focused card scrolls over the whole mockup, not only the focus box. It departs from SKILL.md "shows that element whole".

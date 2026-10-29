# c204-card-picture-scroll

Status: product code built (head 9789203c); test-author writing tests, red first. Branch c204-card-picture-scroll. The designer's mockup and sizes have landed (docs/design/c204-scroll.html, docs/design/c204-sizes.md).
- Design picks: a picture taller than the 480px box scrolls inside it, with a "More" cue. A focus box larger than the card scrolls inside the focus box and opens at its top (1A). A drag scrolls; a tap opens View. The picture button stays the one tab stop, and View stays the keyboard route.
- The builder built 5A, which keeps the 120px floor.
- Added by the coordinator, 14:45 CDT: a task card whose step holds an unbroken URL runs past the screen at 390px. Fix: `ol.steps` gets `min-width: 0; overflow-wrap: anywhere;`. Red first on a 60-character URL step at 390px.
- Open: a 1561px mockup at 390 wide gives a 481px box and a 1px scroll; a boundary test is red on it, and the builder fixes it.
Deferred: two departures, not blocking, your call. 5B: a scrolling picture draws 221.8px wide (a phone picture's width), not 120px. The designer recommends it. It departs from fitFrame's scale and MIN_PIC. 1B: a focused card scrolls over the whole mockup, not only the focus box. It departs from SKILL.md "shows that element whole".

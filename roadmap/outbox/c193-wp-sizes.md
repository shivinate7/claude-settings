# c193-wp-sizes

Status: green and reviewed to round 3; draft PR #783, head 767645b9. Gates (`ci-job checks --lint`) and silent-undo --strict pass; page suite 194 pass.
- Built: part 1 (receipt holds height only in view, drops after scroll idle with scroll compensation), part 2 (rail frames and chips fit the rail), part 3 (option pictures capped at 480px high, 120px floor, grow back with the card), part 4 (one containment sweep test, 9 states, 8 widths, both themes), part 5 (Sent bar spacing, 200ms stamp settle once, steady bar). Designer mockups and notes: docs/design/c193-*.
- Red then green: parts 1 and 2, the cap, the stamp, the spacing and the review-round tests are red on the old page; the sweep is red on the old page for the rail. Part 3's original overflow never reproduced (design review tried 3 mockup shapes, 6 widths); the 480px cap is the designer's rule.
- Review: round 1 (sonnet) 3 findings fixed; round 2 (sonnet) 8 fixed; round 3 (sonnet) 7, fixed 1, 3, 5, 6 and the Undo-width jump after the cap. Design review (opus): round 3 passed 23 of 24, the last fixed in 7a3c2762.
Deferred: Departs from the 480px cap, 120px floor and phone chips at 32px (under the 44px touch floor): reversible CSS picks, your call whether to flip. The designer picked cap option A over a card-filling picture.
Debt-shaped notes, not fixed here:
- Each open decision card prints the text "null" (page.html `card.append(opts, cond ? difkey : null, ...)`), on main too. Own lane: filter nulls before append.
- Sweep cannot see a picture up to about 15px too wide (card padding hides it) or sibling overlap; a dedicated cap test covers the picture.
- The page suite takes about 170s; the checks-shoot job caps at 10 min. Unmeasured in CI.
- docs/design/c193-sizes.md heights at 390 (filed 286, pending 331) are 4 to 11px off the page; update after the owner picks.

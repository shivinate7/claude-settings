# Waiting page rail rows are 32px tall on touch

**What.** On touch at 390px, the rail rows on the waiting page are 32px tall. That is under the 44px touch floor. The rows share `.ov-head`, which sets `min-height: 32px` with no width or touch rule. The new rail Ask row and the tier rows both use it, so both are short.

**Where.** `skills/waiting-page/page.html`: `.ov-head` (CSS). It is used by the tier rows built in the overview `renderRail`, and by the Ask row built in `askRailRow`.

**Decision.** `ux-house-rules`, the house decision that sets touch size at 44px on touch and 24px for a mouse.

**Retire.** Set `.ov-head` to at least 44px on touch. The check: a test in `skills/waiting-page/tests/page.test.mjs` reads each rail row's height at 390px on touch and asserts 44px or more, as the link and Copy tests do.

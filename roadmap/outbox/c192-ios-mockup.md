# c192-ios-mockup

Status: done, green, reviewed. Draft PR #791, head 8033cf64, branch lane/c192-ios-mockup.

- Gates on 8033cf64: ci-job checks --lint --base origin/main PASS; check_silent_undo --strict PASS.
- Review: round 1 FAIL (haiku), round 2 FAIL (sonnet), round 3 PASS (sonnet). Net safety value positive: the change only adds refusals.
- Built by: test-author haiku (three times), builder sonnet (rounds 1-2), builder opus (round 3).
- Open limits are in docs/debts/notes.md: ios-mockup-any-system-family, ios-web-screen-needs-duo, blind-brief-current-refuses-ios-app, ios-duo-order-word-window.
- No designer agent: this lane changes rules and checks, not a screen.
- Next: the d4 redraw, after c191 and c192 merge.

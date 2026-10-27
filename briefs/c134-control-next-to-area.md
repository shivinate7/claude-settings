# c134: a control sits next to what it changes

Cloud build thread brief. Build advisor (10), Oct 27, against claude-settings main 6a3e842
(rebase-free: start from origin/main at dispatch). Send the green, reviewed head to the build
advisor; never merge.

## Why
Owner gripe (Oct 27): on the roadmap page the summary and phase rail sat between the tabs and
the area the tabs change. Triage fixed that page. The rule that stops it everywhere is missing.

## Task
1. Add to docs/design/layout.md: "A control sits next to the area it changes. Anything between
   them belongs to every state of that control." One short rule, STE, with its rule anchor.
2. Add one line to the design-review checklist (agents/ or skills/ design review; find it with
   `grep -rl "design review" agents skills`) that checks it.
3. Check skills/waiting-page/page.html's tabs against the rule. Report pass or fail with the
   element names; fix nothing there (c122 and c126 own that page).

## Done when
The rule and the checklist line are on the branch, `bin/ste-changed origin/main` passes, and the
report names the waiting-page verdict. Review: one fresh Sonnet reviewer. Report cap 12 lines.
Port: yes, docs/design governs every repo's screens; the rule loads from here.

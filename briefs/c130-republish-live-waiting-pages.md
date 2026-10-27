# Brief: c130, a waiting-page template change republishes every live page in the same batch

Repo: shivinate7/claude-settings, from main 43d9af20 (batch #698). One lane: builder (sonnet), then reviewer (sonnet).

## Task
Today a batch that changes skills/waiting-page/page.html leaves every live page on the old template until someone notices (Oct 27: this project's page, fixed by hand at 11:35 CDT).
1. One list of live waiting pages: each repo's page key in its `.claude/layout-extras.json` (lint/layout.json names the extras file), plus this project's page. One home, read by every caller.
2. A command (in skills/waiting-page, beside its other tools) that, for each listed page, compares the published template with page.html on main and prints each page left behind with its owner. A page this account cannot read is named as unknown, never skipped (c121: the live repo pages sit in a third account).
3. SKILL.md: the batch that changes page.html republishes each page this account can reach before the batch report, keeping the db and comments capabilities and the saved items; the report lists the command's verdict.
Two other lanes edit skills/waiting-page now (c131 item ids, c126+d9 writer and pictures). Do not change page.html; keep SKILL.md edits to one new section.

## Rulings
- building-one-home-per-capability; verification-report-unknown-reads.

## Failure classes
- A page in another account counted as current.
- A republish that drops db or comments, so saved answers vanish.

## Check that proves it done
A test with two fixture pages (one current, one on an old template) and one unreadable: red on main (no command), green on the branch, the old one and the unreadable one named. `python3 bin/ci-job gates --lint --base origin/main` and `bin/ste-changed origin/main` pass.

## Report
At most 12 lines: PR (draft), head, red run, green run, review verdict. Send the green, reviewed head to the build advisor thread "Advise the claude-settings build (9)". Do not rebase onto main and do not merge.

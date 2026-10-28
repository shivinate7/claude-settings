# o2-layout-waiting-page (lane, o2 one layout for every repo)

State: green and reviewed. Draft PR #742 (rolled-out mark and waiting page URL), head c6405195.

- Waiting page URL is now RddcgXbB6SvTrFZHPmsvFx (ruling c121). `python3 lint/layout.py waiting-page .` prints it.
- `specs` is already a core kind in lint/layout.json on main, so it is not added as an extra.
- Item 29 (a) is built: `rolled_out()` needs `"rolled-out": true`. The new `has_extras()` feeds waiting-page, kind, caution, visibility, devices and the roadmap key.
- Tests: 4 new tests in lint/test_layout.py failed on main and pass here. ci-job gates --lint passes. silent-undo --strict is clean.
- Review: 1 round (builder sonnet, reviewer sonnet). The reviewer approved. Its 2 prose notes are fixed in c6405195.
- Debt for roll-out: a child repo that moved its folders but has no mark reads at legacy folders after merge. Home may be such a repo, since its extras file names records/. Each child's roll-out adds the mark. Not checked: child repos are out of scope.
- Home check (orchestrator, Oct 28): home's extras file has a `todo` kind and a waiting-page key but no mark. Under #742, home's waiting-page URL still reads, but debts, debt-notes, decisions and plans fall back to the old root folders. debts was right on main (docs/debts).
- Deferred: shiv's pick on home's mark. (a) home's file gains the mark first, (b) #742 counts a kinds map as rolled out, (c) wait for home's roll-out. #742 is held and the lane is paused until the orchestrator sends the pick.

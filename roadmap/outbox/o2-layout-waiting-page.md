# o2-layout-waiting-page (lane, o2 one layout for every repo)

State: green and reviewed. Draft PR #742 (rolled-out mark and waiting page URL), head c6405195.

- Waiting page URL is now RddcgXbB6SvTrFZHPmsvFx (ruling c121). `python3 lint/layout.py waiting-page .` prints it.
- `specs` is already a core kind in lint/layout.json on main, so it is not added as an extra.
- Item 29 (a) is built: `rolled_out()` needs `"rolled-out": true`. The new `has_extras()` feeds waiting-page, kind, caution, visibility, devices and the roadmap key.
- Tests: 4 new tests in lint/test_layout.py failed on main and pass here. ci-job gates --lint passes. silent-undo --strict is clean.
- Review: 1 round (builder sonnet, reviewer sonnet). The reviewer approved. Its 2 prose notes are fixed in c6405195.
- Debt for roll-out: a child repo that moved its folders but has no mark reads at legacy folders after merge. Home may be such a repo, since its extras file names records/. Each child's roll-out adds the mark. Not checked: child repos are out of scope.

# c33. Sessions in repos with no CI still catch and fix their errors

Checked Oct 22: banchi (6c3a171), q_max (b47bd00) and home-app (956e1ab) have CI workflows.
home (3fbb3d1) has none: CLAUDE.md, README.md, records/ (29 Markdown records, a TSV, a JSON) and
tools/ (deploy-degen.sh, ha-ws.mjs, lan_check.py, lan_check_resolve.py).
- home's CLAUDE.md grants Claude merges of records-only PRs "once their checks pass". With no CI,
  no check ever runs, so the grant's condition is empty.
- claude-settings' merge tool (merge/merge.py at 987f682) refuses a repo with no required checks
  ("no required checks are named"), so a session in home cannot use it.
- Unknown: which errors home sessions actually hit. Owner to name one if it is something else.

Advisor pick: give home a small CI, not a no-CI mode in the rules. Every rule that assumes CI
(the merge gate, never merge failing CI, the red-batch flow, c15 and c21 moving checks into CI)
then works in home unchanged.

Brief, home session:
1. Add .github/workflows/check.yml on pull_request, one job "check", under 5 minutes:
   - Markdown links in records/ resolve (reuse claude-settings' actions/readme-links action;
     do not copy it);
   - python -m py_compile tools/*.py; node --check tools/ha-ws.mjs; shellcheck tools/*.sh;
   - every records/*.json parses.
2. Make "check" required on main (branch protection), so the merge tool and the grant both see it.
3. Test: a PR with a broken record link goes red, and the same PR fixed goes green.
Report: the workflow, the red and green run links, and anything the first run flags on main.

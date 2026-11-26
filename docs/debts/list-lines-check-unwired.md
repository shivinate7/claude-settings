# The list-lines check is not wired into CI

- **What.** The list-lines check runs in CI only as its own fixture suite. No CI job judges the lists in a change. The Code check runs it only with `--list-lines`, which is off by default, and `actions/code-check/action.yml` passes no such input. Mistake: a session reads decision `lists-one-line-per-item` as enforced and adds crowded lists. Harm: crowded lists reach main with no failure.
- **Where.** `actions/code-check/code_check.py`: the `--list-lines` flag. `actions/code-check/action.yml`: no input for it. `.github/workflows/checks.yml`: the step that runs the fixture suite.
- **Decision.** `lists-one-line-per-item` (the rule). The switch stays dark by decision `source-prose-lint-ships-dark`, which `code_check.py` cites. The rule is not on main yet.
- **Retire.** Closed when a default Code check run judges lists, and a case in `actions/code-check/test_action.py` shows a crowded list refused with no flag. That file's switch-off control case flips, so the closing change rewrites it.

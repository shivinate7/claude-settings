# A docs-only child PR skips the ruling cite check

**What.** In a child repo, the code-check step runs only when the change touches code. A PR that changes only `.md` files skips it, so a commit in that PR that claims a ruling with no home and no time stays green. Claude writes docs-only PRs in normal work.

**Where.** The child repos' `.github/workflows/checks.yml` code-check gate and `.github/scripts/ci-scope.sh`, the scope script that turns the code flag off for `.md` paths. The check itself is `actions/code-check/code_check.py`, `ruling_check`.

**Decision.** none

**Retire.** The ruling rule runs in a child repo's CI step that no scope flag gates. A docs-only fixture PR with an uncited claim fails. The case is in `actions/code-check/test_action.py`.

Fix: step:ruling-cite-docs-only-prs — remove the gate from each child repo's code-check step when its pin moves.

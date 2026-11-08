# A runner word anywhere in a line counts as a test line

**What.** PR #2096 (builder workflow guard: refuse a test step that can no longer fail) counts a test-runner word anywhere in a line as a test line. So a line that only installs or cleans up is refused, though main allows it: `pip install pytest || true`, `npx playwright install || true`, `rm -rf playwright-report || true` and `pytest --version || true`. A `||` inside `${{ }}` also splits the line, so `pytest tests/test_a.py ${{ inputs.x || true }}` is read as a `|| true` tail. Measured by calling `workflow_builder_refused` on the PR #2096 branch and on main.

**Where.** `hooks/guard.py`, `workflow_command_is_test` on the PR #2096 branch. Its second term, `TEST_RUNNER_CONTEXT.search(command)`, matches a runner word at any position. `workflow_command_cannot_fail` reads each `;` part through that test.

**Decision.** `builders-cannot-edit-tests`, builders cannot edit tests (the workflow test-step rule).

**Retire.** Count a runner word only as the command word of a segment, after the wrapper skip. Split a line at `||` only outside `${{ }}`. When a red case in `hooks/test_guard.py` shows that `pip install pytest || true`, `npx playwright install || true` and `rm -rf playwright-report || true` pass, the debt closes. The same case shows that `pytest --version || true` passes, since no test runs in it. It also shows that `pytest tests/test_a.py ${{ inputs.x || true }}` is not read as a `|| true` tail.

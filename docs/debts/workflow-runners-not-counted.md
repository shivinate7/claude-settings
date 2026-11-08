# Test runners outside the context list are not counted as tests

**What.** When a line has a word from `TEST_RUNNER_CONTEXT`, PR #2096 (builder workflow guard: refuse a test step that can no longer fail) counts it as a test. The words are `addopts`, `pytest`, `py.test`, `jest`, `vitest`, `mocha`, `playwright`, `karma` and `go test`. So `npm test`, `yarn test`, `make test`, `dotnet test`, `mvn test`, `swift test`, `rspec` and `tox` are not counted. `npm test || true` passes, as on main, so a builder can make such a step unable to fail.

**Where.** `hooks/guard.py`, `TEST_RUNNER_CONTEXT` and `workflow_command_is_test` on the PR #2096 branch.

**Decision.** `builders-cannot-edit-tests`, builders cannot edit tests (the workflow test-step rule).

**Retire.** Add each runner to the test-runner words, read as a command word only. Debt `workflow-test-word-anywhere`, a runner word anywhere in a line, requires that reading. When a red case in `hooks/test_guard.py` shows `npm test || true`, `yarn test || true`, `make test || true` and `dotnet test || true` refused, the debt closes. The same case shows `mvn test || true`, `swift test || true`, `rspec || true` and `tox || true` refused too, as test steps that cannot fail.

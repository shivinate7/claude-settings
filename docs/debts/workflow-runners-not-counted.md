# Test runners outside the context list are not counted as tests

**What.** PR #2096 (builder workflow guard: refuse a test step that can no longer fail) counts a line as a test only when it has a word from `TEST_RUNNER_CONTEXT`: `addopts`, `pytest`, `py.test`, `jest`, `vitest`, `mocha`, `playwright`, `karma` or `go test`. So `npm test`, `yarn test`, `make test`, `dotnet test`, `mvn test`, `swift test`, `rspec` and `tox` are not counted. `npm test || true` passes, as on main, so a builder can make such a step unable to fail.

**Where.** `hooks/guard.py`, `TEST_RUNNER_CONTEXT` and `workflow_command_is_test` on the PR #2096 branch.

**Decision.** `builders-cannot-edit-tests`, builders cannot edit tests (the workflow test-step rule).

**Retire.** Add each runner to the test-runner words, read as a command word and not at any position in the line, as debt `workflow-test-word-anywhere` requires (a runner word anywhere in a line). Closed when a red case in `hooks/test_guard.py` shows `npm test || true`, `yarn test || true`, `make test || true`, `dotnet test || true`, `mvn test || true`, `swift test || true`, `rspec || true` and `tox || true` refused as test steps that cannot fail.

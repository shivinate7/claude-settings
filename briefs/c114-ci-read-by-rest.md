# Brief: c114, the CI-read hook reads checks by REST, so cloud sessions see CI

Repo: shivinate7/claude-settings, from main b031394f. One lane: builder (sonnet), then reviewer (sonnet).

## Task
`hooks/ci_wake.py` reads the PR head with `gh pr view ... --json` (its `gh_json(["pr", "view", ...])` call). `gh pr view` uses GraphQL. The cloud proxy refuses GraphQL with 403, so in a cloud session every watch ends "CI unknown".
- Read the PR head and its state by REST: `gh api repos/<owner>/<repo>/pulls/<n>`. Keep run reads on REST (`gh run list` and `gh api .../actions/runs` are already REST; confirm each one).
- Keep the output lines and exit codes unchanged.
- Grep `hooks/` and `lint/` for any other `gh pr view` or `gh pr checks` call that a hook runs in a cloud session. Move those to REST too, or list them in the report as left.

## Rulings
- building-fix-cause-not-symptom: the cause is the GraphQL path, so no retry or fallback text.
- building-one-home-per-capability: one REST read helper, used by every caller.

## Failure classes
- A test that stubs `gh` and so passes on the GraphQL path. The red case must fail when a stub refuses any `gh pr view` / `gh api graphql` call with 403, as the proxy does.
- A REST field name that differs from the GraphQL one (head sha, draft, state).

## Check that proves it done
New cases in `hooks/test_ci_wake.py`: red on main b031394f, green on the branch. Also run lint/hook_catalog.py --check, lint/rule_audit.py, bin/ste-changed origin/main. One live read in this cloud container against an open or recent PR of claude-settings, printed as its one line.

## Report
At most 15 lines: PR, head, red run, green run, live read line, review verdict. Send the green, reviewed head to the build advisor. Do not rebase onto main and do not merge.

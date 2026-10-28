# c175 lint runs code-check (lane session_013NEJKzNQLsaUKaaJp9Fpyz)

- Draft PR #766, head a1b12db6. Builder (opus) done: unit suite, `ci-job gates --lint --base origin/main` (Code check and zizmor PASS) and silent-undo all pass.
- Review round 1 (opus, fresh) running.
- Env note: pipx was absent in the cloud container; installed with `pip install --user pipx` so --lint can run CI's pinned tools.
- Open: builder also unsets GH_TOKEN/GITHUB_TOKEN per step (zizmor 401 with a session token); reviewer judging.
- Round 1 (opus): APPROVE; token unset judged safe. Debt fixed in lane (try 2): FAIL masked as unknown when one tool cannot start.
- Notes (no debt): ste-lint/code-check branches run the local checkout's script and ignore `if:` and `@ref`; LOCAL_ACTION flags any local action, so `ci-job gates-shoot --lint` reads playwright-setup as unknown; pipx present but offline reads FAIL, not unknown.

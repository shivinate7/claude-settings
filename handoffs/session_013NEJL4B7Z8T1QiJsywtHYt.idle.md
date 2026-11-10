# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL4B7Z8T1QiJsywtHYt

## Reply at 2026-11-10T17:28:52Z UTC

IDLE (B). Lane ruling-cite-in-commit (step ruling-cite-in-commit), repo shivinate7/claude-settings.
Goal: a commit message that claims a ruling must name the ruling's home and time.
State: three open PRs, all released to batch runner 8. Each passed lane lint and review round 3. None is merged yet. Merge them in this order:
1. #2053, branch ruling-cite-in-commit, head 38b0d9283. lint/check_red_run.py refuses a claim form with no home or no time.
2. #2107, branch ruling-cite-child-repos, head c23eef136, `Merge after: #2053`. Adds --ruling-only, which actions/code-check runs in child repos. It closes debt ruling-cite-other-repos.
3. #2131, branch ruling-cite-docs-only-pin, head 90d446e42, `Merge after: #2107`. Code-check skips its code layers when every changed path is in standard.json docs_only, and still runs the ruling and comment checks.
Left:
- Runner 8 merges the three PRs.
- Runner 9 does step ruling-cite-docs-only-prs: when each child repo moves its code-check pin to a head that has #2131, drop the `if:` on the code-check step only.
- Debt ruling-claim-noun-forms: Fix: none, until 2026-11-21.
Files: lint/check_red_run.py, lint/test_check_red_run.py, actions/code-check/{code_check.py,test_action.py,standard.json,action.yml}, docs/debts/{ruling-claim-noun-forms,ruling-cite-docs-only-prs}.md and notes.md.
Nothing is unpushed. My scratch worktrees hold only pushed commits.


---
id: pending
slug: private-repos-no-ci
---

# A private repo runs no GitHub-hosted job, so the merge tool merges with no required check

## The ruling

Owner ruling, 11:20 CST, Nov 16, 2026, word for word: `"drop any and all private runner jobs that could cost money and merge without it - see that change through to the end and land it. mandatory."`

The ruling drops the GitHub-hosted jobs of the private repos (q_max, degen, home, and likely ios-adblock and joyous) and keeps their self-hosted jobs. The workflows were disabled by REST on 2026-11-16, not by this PR. The merge tool must merge with no CI run.

Ruling `own-all-jobs-passed-removed` (owner, 2026-11-15 19:08 CST) takes the required check off these repos. Decision `main-branch-protection` holds the rule for the repos that keep CI: their `main` requires no status check.

## The value

`merge.requiredChecks` in `.github/stamp.json` takes a third value, `"none"`. The other values are `"protection"` and a non-empty list of check names. An empty list stays refused.

- `"none"` names no required check. `required_names` returns an empty list and does not stop.
- `"none"` reads neither the ruleset nor the branch protection. GitHub's own merge call refuses a check that is still required, so that read would only copy a refusal.
- `refuse_pinned_mismatch` compares a pinned list only. It has nothing to compare under `"none"`.
- A head with no check and no workflow run reads green under `"none"` (`head_read`, `unseen`). Under the other values it reads pending, because GitHub has not made the run yet.
- A setup PR's own head `stamp.json` gives `requiredChecks` and nothing else, and only when the head says `"none"` and the PR changes that field against its merge-base with the base (owner ruling, page item 929 b). Then the PR lints and merges with no flag. `load_config` reads the head's stamp and checks it in full (the deadline too), and takes `requiredChecks` from it. Every other field is the base's: `standingGrant`, `afterMerge`, `ignoreChecks`, `keepBranches`, `readyChecks`, `deleteBranch` and `method`. A stamp missing at the merge-base reads as `"protection"`, so a PR that adds the stamp with `"none"` changes it. A head that says anything else, or a `"none"` the PR left as the base had it, is judged on the base's stamp, so a PR never loosens its own gate. The guard's `head_read` reads the head's stamp by the same rule.
- Under `"none"` a lane PR passes lane lint on its local steps alone. `lane_lint` reads no draft run of `lane-touched-tests`, and a failing local step still fails.

## What still reads red

Nothing. Under `"none"` the tool reads no CI run at all: no check row, no workflow run, finished, red or pending, on the head or on main. Owner ruling, 11:20 CST, Nov 16, 2026: a repo with `"none"` runs no CI.

- `head_state` and `head_read` read no check and no run, and return green. `confirm` skips the head read too.
- `base_state` reads no run of the base, so a red or pending run on main holds no merge.
- A run left on the head from before the workflows were disabled holds nothing.
- A pending required check on the base's branch protection is still GitHub's to refuse. The tool names that cause when GitHub reads the pull request BLOCKED.

No check runs on a commit this tool pushes, so a claim under `"none"` merges in the same run, as a page heal does.

Kind: build
Plan: docs/decisions/private-repos-no-ci.md#the-value (all)
Home: merge/merge.py

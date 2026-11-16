---
id: pending
slug: private-repos-no-ci
---

# A private repo runs no GitHub-hosted job, so the merge tool merges with no required check

## The ruling

Owner ruling, 11:20 CST, Nov 16, 2026, word for word: `"drop any and all private runner jobs that could cost money and merge without it - see that change through to the end and land it. mandatory."`

The ruling drops the GitHub-hosted jobs of the private repos (q_max, degen, home, and likely ios-adblock and joyous) and keeps their self-hosted jobs. The workflows were disabled by REST on 2026-11-16, not by this PR. The merge tool must merge with no CI run.

Ruling `own-all-jobs-passed-removed` (owner, 2026-11-15 19:08 CST) takes the required check off these repos. Decision `main-branch-protection` holds the one-check rule for the repos that keep CI.

## The value

`merge.requiredChecks` in `.github/stamp.json` takes a third value, `"none"`. The other values are `"protection"` and a non-empty list of check names. An empty list stays refused.

- `"none"` names no required check. `required_names` returns an empty list and does not stop.
- `"none"` reads neither the ruleset nor the branch protection. GitHub's own merge call refuses a check that is still required, so that read would only copy a refusal.
- `refuse_pinned_mismatch` compares a pinned list only. It has nothing to compare under `"none"`.
- A head with no check and no workflow run reads green under `"none"` (`head_read`, `unseen`). Under the other values it reads pending, because GitHub has not made the run yet.
- Under `"none"` a lane PR passes lane lint on its local steps alone. `lane_lint` reads no draft run of `lane-touched-tests`, and a failing local step still fails.

## What still reads red

Under `"none"` a check row or a workflow run that does appear and is red still reads red, required or not. A pending check with no required job stays dropped by `required_only`, as today. No run appears once a repo disables its workflows, so the tool adds no hold for a pending one. That last rule is the consultant's pick, not an owner ruling.

Kind: build
Plan: docs/decisions/private-repos-no-ci.md#the-value (all)
Home: merge/merge.py

# Handoff: lane time-limits-end-hangs-only, 2026-11-19 00:30 CST

- Slug: time-limits-end-hangs-only (role: lane; started by the coordinator 11:31 CST Nov 12). Session: session_013NEJL1Lr7RHEZ96mkhKnnJ. Parent: session_013NEJL1gw6EdrSyvHkTUEx6.
- Step record: roadmap/data/steps/time-limits-end-hangs-only.json on branch `roadmap` (never written by this lane).

## Open PRs
- #2863, draft, open, branch `ci-limits-from-green-runs`, head 88ed6f7e7b059f13840d8b494f398ccab6d33282 (S1 of the series). GitHub reads `mergeable_state: dirty`: main moved (base now 904f3d5e2), so it needs a plain merge of main into the branch (standing grant, no rebase, no force push) and a fresh lane lint.
- Review record posted for that head: rounds 1 and 2 FAIL, round 3 PASS, fix check PASS (sonnet), guard yes, net value zero. Lane lint PASS on that head (Nov 12 13:44 CST, before main moved).
- Handed to the coordinator for runner 10 at 13:45 CST Nov 12. Not batched or merged by this lane.

## Done (S1)
- actions/ci-limits/ci_limits.py plus actions/ci-limits/test_ci_limits.py (56 cases, red first), one suite line in checks.yml.
- Decisions: time-limits-end-hangs-only (new), ci-job-caps (rewritten in place), opt-in-ci-templates-composite (row), restart-plan R3 part 2 edited; stale cites fixed; notes in docs/debts/notes.md.
- Rule built: each job's limit = ceil(max sample x1.5), clamped to 360; a run cut at its limit is a sample; floor = median of measured jobs; new job = nearest same kind x1.5 else largest x1.5; deadline_minutes = 1.5 x longest run, 360 with no data.

## Unfinished (all unstarted)
- S2 merge tool (LINT_SECONDS silence stop reading "hung", retry once; merge.deadlineMinutes computed, reaching it reads "CI still running"; drop merge.job_caps seam). Needs S1 batched. Overlaps: merge-batch-speed, batch-build-log-kept, batch-build-stop-group edit merge/merge.py.
- S3 checks.yml `timeout-minutes` from scope-job output (scope gets contents:read + actions:read; first act proves `needs` works in timeout-minutes on a dispatch run; exempt jobs: scope, `touched`, impeccable-sync).
- S4 lint (check_debt_retire TIMEOUT, check_python_floor TIMEOUT). S5 mutation (hooks/mutate_guard.py, janitor/mutate_sweep.py).
- S6 silence_stop in hooks/stall_watch.py. Waits on lane stranded-jobs (session_013NEJL1GpGypoxH9ZdHDtEw, step stall-watch-ends-quiet-jobs). Facts: verdict's heartbeat counts as output to stall_watch (do not pass --beat); no gap data stored; windows are measured locally only.
- Census of ~25 limits from lane fixed-number-limits-census: never received (branch path not sent). S2 to S5 should map it to families.
- Not filed: guard that a PR body's session id matches the running session (I typed the coordinator's id once; fixed in the PR).
- Known limits filed as notes: gh timeout=120; job `name:` gives phantom rows; script runs in this repo only; cut at an older, lower cap reads as a cancel; checks.yml line cites in windows-shards-outgrow-caps.md.
- Rollup `needs` lacks windows-guard-2/-3 and windows-merge-2..5 (coordinator filed it with triage).

## Next step
Merge main into `ci-limits-from-green-runs`, rerun `merge --lane-lint 2863` from a root checkout, fix verifier only if the merge is not clean, then the batch runner merges. Then start S2.

## Refused or failed acts
- Test-author subagent could not make a hand-built `git worktree add` (guard refused, literal path too) or edit checks.yml (test-author-scope guard).
- Reviewer subagents could not run `merge --lane-lint` from a worktree; I ran it from the root checkout.
- Hook messages: message-time-matches-clock refused my first coordinator message (clock mismatch, fixed); agent-role-model refused sonnet on a round 1 reviewer spawn (dropped the model field); pointer-head refused a branch switch in the root checkout today (used a worktree).
- Round 1 reviewer reported itself as claude-haiku-5-5 although the role table says sonnet; coordinator said no redo.

## Owner rulings held
- R3 three-part form, 14:09-14:24 CST Nov 10 (plan restart-plan R3): stop on silence; a stop reads "hung"; total-time limits come from recent green runs; silence window from the longest output gap per tool; margins multiply.
- Page item 557 a, 11:51 CST Nov 12: a hung job retries once; if the retry also hangs the rollup goes red labelled "hung", not "failed", and a report names the job.
- Page item 586 a, 12:54 CST Nov 12 (record 618b84ece on roadmap; reopened 12:30 and re-ruled): a run cut at its limit counts as a sample, the limit rises x1.5 per cut run up to 360.
- Coordinator picks (not owner): median floor of measured jobs (12:22 CST); silence window with no data reports only; window n = 30; exempt jobs keep 5/10.

## Agents (role, model, worktree branch)
- Explore (sonnet), Plan (opus), refuter (opus): read-only, finished.
- test-authors (sonnet): worktree-agent-a5f0787d226cb6bf1, worktree-agent-a5007676fe57d8504, worktree-agent-ab2436d2314d9e2d0, worktree-agent-ad12a29bea20a6cee.
- builder (sonnet): worktree-agent-ac45948a916420244 (all pushes went to ci-limits-from-green-runs).
- reviewers and verifiers (sonnet; round 1 reported haiku): worktree-agent-adfb969e15a08008d, -a7cab7252e97ea12e, -aa95d9249e7d30f4d, -aa61d449de3a08190, -a9d9f21369c4e728f, -a0572b82ae99b0dca.
- None running.

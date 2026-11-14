# Audit: claude-settings CI against skill ci-hygiene

Step ci-hygiene-refresh (refresh the ci-hygiene skill and apply it in every repo), claude-settings
part. Read on main at 8e9f2b153, 2026-11-14 00:16 CST. Each row is one numbered check of the skill's
"Audit a repo" list. Verdicts: pass, fail (fixed in a named PR), excluded by design (with the record).
The skill text is not edited here; step ci-hygiene-once-per-batch (PR 3004) owns it.

| # | Check | Verdict | Where read | Good looks like |
|---|-------|---------|------------|-----------------|
| 1 | `all-jobs-passed` job exists | pass | `checks.yml:2124` | one rollup job |
| 2 | Rollup needs every other job, with `always()` and the draft guard | pass | `checks.yml:2124-2156`; the 29 other jobs all appear in `needs:` | no job off `needs:` that can run on a PR |
| 3 | Branch protection requires one check | pass | REST `branches/main/protection/required_status_checks`: `checks` holds only `all-jobs-passed` | exactly one |
| 4 | PR triggers hold the four types | pass for `checks.yml:7`; excluded by design for `lane-touched-tests.yml:10` (runs on drafts only, header lines 3-6); n/a for `impeccable-sync.yml:8` (renovate head, path filter, line 21) | | four types on every rollup workflow |
| 5 | Every job skips on a draft | pass: shards need `scope` (`checks.yml:107-108`); excluded by design for `lane-touched-tests.yml:30` (runs only on a draft) | | draft run starts nothing in `checks.yml` |
| 6 | Concurrency group holds draft state, never cancels a default-branch run | pass `checks.yml:25-27`, `lane-touched-tests.yml:16-18`; n/a `impeccable-sync.yml:15` (PR only) | | group has draft state |
| 7 | Every job has `timeout-minutes` | pass: runs-on / timeout counts 31/31, 1/1, 2/2, 1/1 | | counts match |
| 8 | Every `uses:` pinned by full SHA or same-repo | pass: the only non-SHA lines are same-repo actions (`checks.yml:94,164,178,701,851,887,923,963,1619,2163,2215`, `stable.yml:41`) | | none unpinned |
| 9 | Checkout sets `persist-credentials: false` | pass: all 35 checkout steps | | all |
| 10 | Top-level `permissions:` read-only | fail: `impeccable-sync.yml:12` had `contents: write`; fixed in PR 3371 (job-level write). Others pass (`checks.yml:17`, `lane-touched-tests.yml:12`, `stable.yml` empty) | | read-only at top |
| 11 | No `pull_request_target` checking out the PR head | pass: no hit | | no hit |
| 12 | Job-level `if:` holds only the draft guard | pass for all but three; excluded by design: `shell-macos`, `checks-macos`, `checks-macos-b` (`checks.yml:1025,1083,1330`, `event_name != 'push'`), R61 macOS once per batch, `docs/decisions/test-strategy-reset.md`, symbol `MACOS_JOBS` in `lint/test_windows_split.py` | | skill text carries the same carve-out |
| 13 | Last job is `ci-done`, needs every other job, calls `ci-done-comment` | pass: `checks.yml:2171-2215` | | |
| 14 | No `tail` / `head` pipe that decides a verdict | pass: only version prints at `checks.yml:1040,1042` | | none |
| 15 | Audit step with a pinned version | pass: shared action (`checks.yml:164`), pin `actions/zizmor/run.sh:13`; bump 1.30.1 to 1.32.0 in PR 3374 | | newest pin that passes |

Items 2 and 15 skill-text fixes the step note asked for are already on main (`SKILL.md` lines 316-319
and 348-353). PR 3004 changes `SKILL.md` and `snippets.md` only, steps 3, 17 and 20 text, none of
the audit list. No duplicate was built.

## Skill gaps for PR 3004 or its follow-up

1. Check 12 has no carve-out for the three macOS jobs above. The lint knows them (`MACOS_JOBS`).
2. From the child audits (runner 11, 2026-11-14 00:13 CST, relayed by the coordinator):
   - q_max `checks.yml:125,396,535,562,620,662` put `startsWith(github.head_ref,'batch-')` on six rollup
     jobs, by design (decision only-a-batch-runs-ci). Check 12 needs an exemption or a ruling.
   - banchi `demo.yml:74-79` cancels in progress on a main-push workflow; mailaudit `checks.yml:416-421`
     keeps `milestone-proof` off the rollup. Each carries a comment naming why; both belong in the
     excluded list.
   - degen passes check 15 only through `make lint-actions` (`Makefile:55`); check 15 must accept it.
3. Check 4 and 5 text has no wording for a draft-only workflow such as `lane-touched-tests.yml`.

## Open, not built here

- `checks.yml:8` still holds a nightly `schedule` and the `nightly-skip` job (line 43). The owner ruling of
  2026-11-12 22:19 CST (page item 683) says claude-settings keeps no nightly schedule. PR 3004's text
  says that holds once the schedule is removed. No step here removes it.
- `skills/ci-hygiene/snippets.md:187` and `docs/plans/child-guard-promotion.md:318` still say zizmor 1.30.1.
- Online zizmor audits (stale-action-refs, ref-version-mismatch) did not run locally. Unknown until
  PR 3374's run.
- PR 3371 changes a job that runs only on Renovate heads; its CI never runs it. Unknown until the next
  Renovate PR.

## Child repos: what to check

Not claude-settings work; the lists go to the coordinator. For each child: run the skill's 15 checks on
its `.github/workflows`, plus run zizmor 1.32.0 offline on its `.github/` before its pin moves (the pin
in PR 3374 reaches every child lane lint at once, decision action-pins-follow-sessions).

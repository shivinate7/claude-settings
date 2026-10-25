# Batch 4: cull the guard, part 2 (c23). Run on the Mac.

Paste this whole file into one fresh claude-settings session on the Mac.
Written by the advisor, Oct 25, against claude-settings main f463787 (#572).

## Goal

Decide two guard rules that never fired on Windows: keep or delete each, on both machines' counts.
- `gh-api-method`: refuses `gh api` with a write method (the API route to merges and settings changes).
- `ln-over-directory`: refuses `ln -s` over an existing folder. It can do real harm only on Mac.

Governing records: debt guard-cull-held-two (the two rules held for the Mac count), decision
cull-rules (how a cull runs), rule building-guard-needs-incident (delete a guard rule that never
fired since it landed and whose record names no incident).

## Steps

1. Confirm you stand in the Mac clone on an up-to-date main: `git fetch origin main` and
   `git -C <pin> rev-parse HEAD` against `git rev-parse origin/main`. If the pin is behind, the
   session-start auto-pull (#568) failed: say so in the report, then reinstall with
   `bash merge/install_from_main.sh` from the clone.
2. Count: `verdict python3 lint/guard_log_report.py --all-rules --days all`. From its output, give
   for each of the two rules: deny, ask and noted counts, and the first-line date or "never". Also
   give the log's line count and its first date, so the count's reach is known.
3. Windows count, Oct 22 (from the debt): zero lines for both, in 20,685 lines since 2026-09-16.
   If the owner gives a fresher Windows count, use it.
4. Stop point. Bring the owner one question with options and a pick, per rule:
   - Count zero on both machines: delete (pick), or keep with the reason.
   - Count above zero on the Mac: keep (pick). Quote each fired line's date and command shape, so
     the owner sees whether it caught a real mistake.
   Ask the owner directly. This is a deletion of a guard, so it is the owner's call, not the
   advisor's. Do not delete anything before the owner names the rules.
5. Build what the owner names, in one lane: delete each named rule from `hooks/guard.py` (its code,
   its reason constant, its line in the rule list near line 63), its rows in `hooks/test_guard.py`,
   and its mutants in `hooks/mutate_guard.py`. Rewrite or delete debt guard-cull-held-two: delete it
   when both rules are decided. Update every other reader that the rule ids appear in
   (`git grep -n '<rule id>'`).
6. Proof: the guard suite and the mutation harness pass with the rules gone; `guard_log_report.py
   --all-rules` no longer lists a deleted id. A reviewer reads the diff (it changes a guard).
   Merge under the usual rules (git-integration-branch-merge, roles-review-cap-three); a lone lane
   is its own integration PR.

## Report

Done, Deviations, Input Needed, Next, per the report rules. Include the two counts (Mac and
Windows), the owner's answer with its date, and the PR. If nothing was deleted, say which rules
stay and why, and where that ruling now lives.

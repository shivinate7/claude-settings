# The owner reviews the two log-only reply rules

**What.** The reply judge logs two new rules, `roles-findings-are-debts-or-notes` and `parallelism-keep-going`, and prints no note for them. Nothing reads their lines yet. Due 2026-11-27: the owner reviews the lines and decides for each rule a note, a refusal, or neither. No checked reader surfaces that date: the debt store reads only a `Seen:` line (`lint/check_record_slugs.py`), and this debt has none.

**Where.** `hooks/reply_judge.py`, `NEW_RULES` and `log_finding`. The lines land in `guard.log`. One command per rule prints them. A newer-rule finding that the older prompt logged under `reply-judge` (its reason named no older rule id) is missed by the first two. The third prints it, with other `reply-judge` lines, until the code keys it under its newer id:

```
python3 ~/.claude/lint/guard_log_report.py --between 2026-11-25T12:11:00-06:00 2026-11-27T23:59:59-06:00 --rule roles-findings-are-debts-or-notes
python3 ~/.claude/lint/guard_log_report.py --between 2026-11-25T12:11:00-06:00 2026-11-27T23:59:59-06:00 --rule parallelism-keep-going
python3 ~/.claude/lint/guard_log_report.py --between 2026-11-25T12:11:00-06:00 2026-11-27T23:59:59-06:00 --rule reply-judge
```

**Decision.** `reply-judge-samples-never-refuses`, the reply judge that never refuses. A refusal ruling rewrites it in place.

**Retire.** When the owner rules on each rule's lines. No runnable test file closes it, so its close needs a `Retire-run:` cite in the PR body (decision `debt-close-runs-retire`).

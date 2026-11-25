# The owner reviews the two log-only reply rules

**What.** The reply judge logs two new rules, `roles-finding-has-a-home` and `parallelism-wait-names-its-event`, and prints no note for them. Nothing reads their lines yet. Due 2026-11-27: the owner reviews the lines and decides for each rule a note, a refusal, or neither.

**Where.** `hooks/reply_judge.py`, `NEW_RULES` and `log_finding`. The lines land in `guard.log`. One command per rule prints them:

```
python3 ~/.claude/lint/guard_log_report.py --between 2026-11-25T12:11:00-06:00 2026-11-27T23:59:59-06:00 --rule roles-finding-has-a-home
python3 ~/.claude/lint/guard_log_report.py --between 2026-11-25T12:11:00-06:00 2026-11-27T23:59:59-06:00 --rule parallelism-wait-names-its-event
```

**Decision.** `reply-judge-samples-never-refuses`, the reply judge that never refuses. A refusal ruling rewrites it in place.

**Retire.** When the owner rules on each rule's lines. No runnable test file closes it, so its close needs a `Retire-run:` cite in the PR body (decision `debt-close-runs-retire`).

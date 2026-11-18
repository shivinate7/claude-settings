---
id: pending
slug: guard-observe-mode
---

# A new guard rule ships log-only first

## The ruling

Source: owner, 2026-11-17 20:01 CST, consultant goal v6. Goal v6 names it "guard-observe-mode (new guards log before they refuse)". Goal v7 restates it, 2026-11-18. The owner reads the practice as coming from a Claude Code blog post on verification. The post is not linked.

- A new guard rule ships log-only. Its call site writes `record(tool, "noted", "<new-id>", matched)`. It never calls `refuse()` or `ask_command()`.
- The id is new. An existing rule id never gets this line, because that would quiet a guard that already refuses.
- The rule's first test asserts one `noted` line and no refusal.
- The flip PR changes that one line to `refuse()` or `ask_command()`. Its test asserts the refusal.
- The flip needs both of these:
  - At least one noted line is judged a true hit. The check is `python3 lint/guard_log_report.py --between <since> <now> --rule <id>`. `<since>` is the day the rule shipped log-only, written as a time with its UTC offset, such as `2026-11-18T00:00:00-06:00`. Use the offset in force on that date. `<now>` takes the same form. The script refuses a time with no offset.
  - No false-alarm note since `<since>`. A reader judges each noted line a true hit or a false alarm, and files each false alarm as a note. Decision `cull-guard-wrong-refusals` (how a wrong refusal is filed) sets that form.
- Zero noted lines never flips the rule.

## Why

A rule that refuses before it has a true hit can cry wolf. Its readers then learn to scroll past its refusals (decision `guard-that-cries-wolf-is-spent`). Rule `verification-trust-guard-after-red` (a guard earns trust only after it goes red on the defect it guards) needs that proof first. Log-only gathers it, and the flip PR changes one line from a log to a refusal.

Cost: a call that a log-only rule matches adds one append to guard.log, as a refusal does today. A call that no rule matches does no extra work. No new process, file or timer. The cost test is owed with the first rule that uses this form.

Risk: guard.log is per machine, so each count is a lower bound.

Kind: process
Home: rule:verification-trust-guard-after-red

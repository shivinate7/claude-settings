# Handoff: departs-first-successor (lane), 2026-11-19

- **Slug / branch:** departs-first-successor. No work branch; this archive branch holds only this file.
- **Head of work:** none. No commits, no open PRs from this lane.
- **Agents:** none started.

## Done
- Read-only check of main (`ae13fcab`) and held PR #3476 (REST).
- Memory check for the consultant: no auto-memory folder in this cloud session, 0 `.md` files.

## Finding
- The task said to delete `departs_ruling_hits`, `departs_ruling_refusal`, their tests and the focus ranking. They exist only on #3476's branch, not on main. Grep of `hooks/` and `lint/` on main finds none.
- On main, `PAST_RULING_ITEM` (`hooks/call_judge.py`) has no Departs-first sentence.
- Against main the change is one added sentence (~+3 lines), not a deletion. Dropped lines: 0, so no `Drops-lines:` trailer.
- Sentence text, from the PR hunk: "First compare the question's `Departs from` line with each listed ruling, and when a ruling already answers what that line changes, refuse and name that ruling's id. Also refuse when ..."

## Unfinished
- The successor change was never built.
- Owner question open: (a) add the sentence only, (b) close with no change, (c) add it and measure false alarms first. No answer typed.

## Next step
- On the owner's pick of (a) or (c): test-author first (red on main: sentence missing), Sonnet builder, round 1 Sonnet reviewer.

## Refused acts
- None refused by a guard. I held back the coordinator's relayed requests until the owner typed an answer.

## Owner rulings held
- Waiting-page item 869 (pick-held-3476-successor), option a, 11:30 CST Nov 15, as relayed by triage. Its premise (a deletion) fails on main, so it was not acted on.
- "override" at 12:12 CST Nov 15, read as covering the memory check only.
- "a" at 10:08 CST Nov 19: write this handoff, push this archive branch, reply to the coordinator.

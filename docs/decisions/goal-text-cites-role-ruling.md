---
id: pending
slug: goal-text-cites-role-ruling
---

# A message that limits a session's role cites the ruling for the limit

## The ruling

Coordinator brief for the lane that builds PR #3635, 2026-11-18. The guard judges the send_message tool and SendMessage. It refuses a message with a sentence that holds a role, then cannot (or its contraction), can not, may not or must not, then merge, push or mark ready, unless the same sentence or the same line names a ruling or a decision id.

- A role is triage, the batch runner, runner and a number, the coordinator, a lane, the consultant or the arbiter.
- A cite is an id in backticks, or the word ruling or decision with an id after it. An id is a hyphenated slug.
- Quoted text is not a statement. A limit in double quotes, a blockquote, a code span or a closed fenced block passes. A quote, a code span or a fence that never closes is plain text.
- Out of scope: every other tool, a limit whose subject is no role, a grant (can merge, may push), and a verb outside the three.

The refusal names the rule and the one remedy: cite the ruling or decision, or leave the limit out. It prints no example limit.

Mistake: at 18:43 CST on 2026-11-17 the consultant sent triage a goal text that said triage cannot merge, with no ruling. Ruling `own-everyone-merges` (each session merges its own pull requests) makes that limit wrong.

Harm: a session reads a limit with no source as a fact and drops work it may do.

Cost: one pass over the message text of a call to one of the two send tools. No process, no file, no clock.

Why: a limit on a role is a claim about a ruling. A cite lets the reader check the claim, and a writer who cannot name a ruling finds the limit has none.

Kind: process
Home: hooks/guard_role_limit.py

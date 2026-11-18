---
id: pending
slug: goal-text-cites-role-ruling
---

# A message that limits a session's role cites the ruling for the limit

## The ruling

Coordinator brief for the lane that builds PR #3635, 2026-11-18. The guard judges the send_message tool, SendMessage, the Agent tool's `prompt` and create_session's `prompt`. It refuses a text with a sentence that holds a role, then cannot (or can't), can not, won't, may not, must not or isn't allowed to, then merge, push or mark ready, unless the same sentence or the same line names a ruling or a decision id.

- A role is triage (or a triage session), the batch runner, runner and a number (`Runner 10`, `Runner #10`), the coordinator, a lane or lanes (with a number or a branch slug too), the consultant or the arbiter. The second person (you) counts, because the text goes to another session.
- A cite is an id in backticks, or the word ruling or decision with an id after it. An id is a hyphenated slug.
- Quoted text is not a statement. A limit in double or single quotes, a blockquote, a code span or a closed fenced block passes. A quote, a code span or a fence that never closes is plain text.
- Out of scope: every other tool, a limit whose subject is no role, a grant (can merge, may push), and a verb outside the three.

The refusal names the rule and the one remedy: cite the ruling or decision, or leave the limit out. It prints no example limit.

Mistake: at 18:43 CST on 2026-11-17 the consultant sent triage a goal text that said triage cannot merge, with no ruling. The owner's ruling "No now everyone merges" (2026-11-16 12:58 CST, ruling Q2), recorded in the "Lane draft PR" bullet of `.claude/CLAUDE.md`, makes that limit wrong: each session merges its own pull requests.

Harm: a session reads a limit with no source as a fact and drops work it may do.

Cost: one pass over the message or prompt text of a call to one of the four tools. No process, no file, no clock.

Why: a limit on a role is a claim about a ruling. A cite lets the reader check the claim, and a writer who cannot name a ruling finds the limit has none.

Recorded limit: any hyphenated slug in backticks counts as a cite, whether or not a record holds it. The guard checks that a cite is present, not that it is true; a reader still checks the id.

Kind: process
Home: hooks/guard_role_limit.py

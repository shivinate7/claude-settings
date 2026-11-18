---
id: pending
slug: goal-text-cites-role-ruling
---

# A message that limits a session's role cites the ruling for the limit

## The ruling

Coordinator brief for the lane that builds PR #3635, 2026-11-18. The guard judges the send_message tool, SendMessage, and the `prompt` of the Agent tool, the Task tool and create_session. It refuses a text with a sentence that holds a role, then cannot (or can't), can not, won't, may not, must not, mustn't, should not, does not or isn't allowed to (also is not permitted to), then merge, push or mark ready, unless the same sentence or the same line names a ruling or a decision id.

- A role is triage (or a triage session), the batch runner, runner and a number (`Runner 10`, `Runner #10`), the coordinator, a lane or lanes (with a number or a branch slug too), the consultant or the arbiter. The second person (you) counts, because the text goes to another session.
- A cite is an id in backticks, or the word ruling or decision with an id after it. An id is a hyphenated slug.
- Words may sit between mark and ready (`mark its own PR ready`, `mark the lane PR ready`, `mark your PR ready`).
- Three forms pass with no cite. A conditional: an "if" opens a clause before the limit in its sentence (`If you cannot push, stop and report.`). The second person in an Agent or Task prompt: that text briefs the agent's own run, so `You must not push.` limits no session's role. A limit that states its cause: a colon or "because" follows the act in its sentence, before any semicolon (`The lane cannot push: the cloud proxy returns 403.`). A second-person limit in a send or a create_session prompt, with no "if", no cause and no cite, is still refused.
- Quoted text is not a statement. A limit in double or single quotes, a blockquote, a code span or a closed fenced block passes. A quote, a code span or a fence that never closes is plain text.
- Out of scope: every other tool, a limit whose subject is no role, a grant (can merge, may push), and a verb outside the three.

The refusal names the rule and the one remedy: cite the ruling or decision, or leave the limit out. It prints no example limit.

Mistake: at 18:43 CST on 2026-11-17 the consultant sent triage a goal text that said triage cannot merge, with no ruling. The owner's ruling "No now everyone merges" (2026-11-16 12:58 CST, ruling Q2), recorded in the "Lane draft PR" bullet of `.claude/CLAUDE.md`, makes that limit wrong: each session merges its own pull requests.

Harm: a session reads a limit with no source as a fact and drops work it may do.

Cost: one pass over the message or prompt text of a call to one of the five tools. No process, no file, no clock.

Why: a limit on a role is a claim about a ruling. A cite lets the reader check the claim, and a writer who cannot name a ruling finds the limit has none.

Recorded limit: any hyphenated slug in backticks counts as a cite, whether or not a record holds it. The guard checks that a cite is present, not that it is true; a reader still checks the id.

Recorded limit: a cause is read for its presence, not its truth. Any colon or "because" after the act passes the limit, so a writer can pass a limit with a made-up cause. The guard stops the mistake of a limit with no source, not a writer who invents one. Likewise an "if" earlier in the sentence passes the limit, whatever the clause says.

Kind: process
Home: hooks/guard_role_limit.py

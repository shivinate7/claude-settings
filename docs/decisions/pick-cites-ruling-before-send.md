# A coordinator's pick cites a ruling before it is sent

## The ruling

A coordinator's message that states a pick or a hold cites the ruling it rests on, or says `no ruling found:` and what it searched. The message is checked against the cited text before it is sent.

- Scope: a `mcp__claude-code-remote__send_message` from a session whose own record carries the tag `cs-build:coordinator` (read by `hooks/own_session.py`, `own_session_read`, as the lane tag is read), whose text holds the whole word `pick` or `hold`. Any other sender or text passes, with no model call.
- A cite is a plan R-number, a decision, debt or step id, or a page item number. A pick with no cite and no `no ruling found: <what was searched>` line is refused in code, with the remedy and no model call.
- A pick with a cite, or a `no ruling found:` line, gets one judge call (`hooks/call_judge.py`, `judge_pick`, guard rule `pick-judge`; Sonnet, the past-ruling check's model). The prompt carries the pick text, the cited decision, debt and step rulings (`question_form.past_rulings`), and the text of each cited plan R-number from `docs/plans`. The judge refuses a pick that the cited text contradicts or does not say, and a `no ruling found` line that a listed ruling decides.
- A source the hook cannot read is named in the prompt as not searched, never read as clear: a page item (the hook cannot read the waiting page), a plan R-number that no plan file holds, a cited record that was not among the records read.
- A model error allows the pick, with one stderr line. A pick is no question to the owner, so the non-question fail-open convention holds.
- An owner override lifts the refusal (`guard_core.refuse`, decision `owner-override`).

## The mistake and the harm

The mistakes, all 2026-11-12 (CST), all by a coordinator:

- 12:06: a mailbox default was held, against page item 556 a and plan R49.
- 12:04: plan R22 point 3 was cited for something R22 does not say.
- 12:30: a route was offered against step `prose-tending-contract`.

The harm: a lane builds to the wrong pick, the work is redone, and the owner is asked the same thing twice.

Cost, per pick message: one `call_judge.py` process and one Sonnet call (60 s cap), plus one git process (`question_form.past_rulings`). A send with no pick or hold word, or from a session that is no coordinator, starts no process and makes no model call. A pick with no cite makes no model call. Nothing is written but the `guard.log` line of a refusal. `hooks/test_call_judge.py` (section "a coordinator's pick") counts the calls.

Known limit: the judge reads the cited text, not the whole plan or the waiting page. A page item cite is unread, so the pick it backs passes on the cite alone. A plan R-number that no file of `docs/plans` holds as a `- **R<n>.` bullet is reported to the judge as not searched, never as clear.

Kind: process
Home: rule:questions-go-to-owner

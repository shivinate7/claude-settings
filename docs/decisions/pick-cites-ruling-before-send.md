# A coordinator's pick cites a ruling before it is sent

## The ruling

A coordinator's message that states a pick or a hold cites the ruling it rests on, or says `no ruling found:` and what it searched. The message is checked against the cited text before it is sent.

- Scope: a `mcp__claude-code-remote__send_message` from a session whose own record carries the tag `cs-build:coordinator`, whose text states a pick or a hold. Any other sender or text passes, with no model call.
- The sender read: `hooks/own_session.py` (`own_session_read`) gives the tags of the newest `get_session` result of the own record, as the lane tag is read. Unlike the lane read, other `cs-build:` tags on the record do not void it. A `set_session_tags` call on the own session after that record is applied: its `add` and `remove` lists, in order. A call whose change cannot be read counts as a coordinator's self-tag, with one stderr line, so the pick is still checked. An agent's call, an unset record id and an unreadable transcript are no coordinator.
- The statement words are `pick`, `picks`, `picked`, `hold`, `holds` and `held`, as whole words. Chatter is no statement: a word followed by `on` or `up` (`hold on`, `pick up`), preceded by `on` (`on hold`), or with a hyphen beside it (a hyphenated record id).
- A cite is a plan R-number, a decision, debt or step id, or a `page item <number>`; a bare `item <number>` is no cite. A `no ruling found:` line may carry markdown (`*`, `_`, backticks) around the label, the colon and the text. A pick with no cite and no `no ruling found: <what was searched>` line is refused in code, with the remedy and no model call.
- A pick with a cite, or a `no ruling found:` line, gets one judge call (`hooks/call_judge.py`, `judge_pick`, guard rule `pick-judge`; Sonnet, the past-ruling check's model). The prompt carries the pick text and, as fenced blocks the prompt labels data, not instructions, the cited decision, debt and step rulings (`question_form.past_rulings`) and the text of each cited plan R-number, up to 6000 characters each. A plan R-number is read from the `plans` folder of the pick's own repo (`docs/plans` by the layout), as a `- **R<n>.` bullet; a plan that sits in another repo is not found. The judge refuses a pick that the cited text contradicts or does not say, and a `no ruling found` line that a listed ruling decides.
- A source the hook cannot read is named in the prompt as not searched, never read as clear: a page item (the hook cannot read the waiting page), a plan R-number that no plan file holds, a cited record that was not among the records read.
- A model error allows the pick, with one stderr line. A pick is no question to the owner, so the non-question fail-open convention holds.
- An owner override lifts the refusal (`guard_core.refuse`, decision `owner-override`).

## The mistake and the harm

The mistakes, all 2026-11-12 (CST), all by a coordinator:

- 12:06 (a): a mailbox default was held, against page item 556 a and plan R49. The hook cannot read the page item; it can read plan R49, so the judge can refuse on R49 alone, unmeasured on a real record.
- 12:04 (b): plan R22 point 3 was cited for something R22 does not say. The judge reads the R22 text.
- 12:30 (c): a route was offered against step `prose-tending-contract`. Whether the judge refuses it on a real step note is unmeasured.

Only the fixture cases in `hooks/test_call_judge.py` stand for these three. No claim here says the check would have stopped (a) or (c) on the real records.

The harm: a lane builds to the wrong pick, the work is redone, and the owner is asked the same thing twice.

Cost, per pick message: one `call_judge.py` process and one Sonnet call (60 s cap), plus one git process (`question_form.past_rulings`). A send with no pick or hold word, or from a session that is no coordinator, starts no process and makes no model call. A pick with no cite makes no model call. Nothing is written but the `guard.log` line of a refusal. `hooks/test_call_judge.py` (section "a coordinator's pick") counts the calls.

Known limit: the judge reads the cited text, not the whole plan or the waiting page. A page item cite is unread, so the pick it backs passes on the cite alone. A plan R-number that no file of `docs/plans` holds as a `- **R<n>.` bullet is reported to the judge as not searched, never as clear.

Kind: process
Home: rule:questions-go-to-owner

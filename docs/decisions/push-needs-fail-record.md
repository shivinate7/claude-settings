# A push waits for the review record of each report

## The ruling

A shell `git push` is refused while a reviewer or design-reviewer report has no posted review record. Coordinator, 2026-11-07 14:38 CST and 14:53 CST. Source: the brief. Process-only.

- The refusal reads the session's own transcript (`transcript_path`), also when `agent_id` is set. It never reads the subagents file.
- It needs a PR known to the session: a successful `mcp__github__create_pull_request` call, or a posted record.
- A report is a Done line: `PASS|FAIL|PARTIAL, round N of 3, <model>`, or `PASS|FAIL, fix check, <model>`. Indents and markdown leads are allowed. A finding line never counts.
- A report arrives as an Agent tool result, as a `<task-notification>` (a user message or a `queued_command` attachment), or as an `<agent-message from="<agentId>">` hand-back. The hand-back maps through the `agentId: <id>` line of the Agent result.
- A record is a successful `mcp__github__add_issue_comment` whose body `parse_review` accepts. It clears a report when it holds a line with that report's role and verdict: a `Round` line, or the `Fix check` line for a fix check. One record clears every report whose line it holds.
- A dry run, a commit and a transcript that cannot be read pass.
- A second refusal, same rule id (coordinator, 2026-11-07 15:19 CST): a push to the head branch of PR n is refused when the transcript holds a successful posted record, accepted by `parse_review`, with a Fix check line for PR n. The merge tool takes one fix check per record, so the next fix goes on a new branch and a new PR. The destination is read with `push_destinations`. PR n maps to its head branch through a successful `create_pull_request` call: its input `head`, and the `number` of its result. With n's head unknown, any push is refused unless a successful `create_pull_request` comes after that record. This refusal names no branch.
- The refusal tells the lane to render the record with `merge <pr> --review-record --head <reviewed sha>`, post it with the GitHub MCP comment tool, then push. It names no target (rule `git-remedy-never-names-target`).
- Rule id `push-needs-fail-record`, deny, in the cloud and locally. The incident ran in the cloud, so no gate.

## The incidents

- PR #1467, lane `notes-delete-pass`: the lane pushed a fix before it posted the round-1 FAIL record. `--fix-check` then refused, because it needs the record of the head the review read.
- PR #1490, lane `notes-fix-large-1`: a round that came back PASS with notes was pushed over before its record was posted. A PASS needs a record too.

- PR #1464, lane `notes-fix-report`: a second fix was pushed to the branch of a PR whose record already held a Fix check line. The merge tool takes one fix check per record, so the second fix had no check.

## The harm

- The review trail loses the round: the record for the reviewed head is never posted, and the push makes that head stale.
- The fix skips its fix check: `--fix-check` has no record to start from.
- A second fix on a fixed head has no fix check of its own (record `pr-review-record`, one fix check per record).

## The cases

The cases are in `hooks/test_guard.py`, section 5f-2 (family `push-needs-fail-record`).

| Transcript shows | Outcome |
|---|---|
| PR known, a reviewer or design-reviewer report of any verdict (result, notice, attachment, hand-back), no record | deny |
| Done line with a bold lead, 1500 later reads, a push from the PowerShell tool, a builder push whose parent file holds the report | deny |
| A report whose record holds another role, another verdict, or a Fix check line for a round report | deny |
| A record post that returned an error, or a comment that is no record | deny |
| An unrecorded report, then a later report whose record holds only its own line | deny |
| The PR known only from a posted record, then a later unrecorded report | deny |
| Each report followed by a record that holds its role and verdict (round, PARTIAL, fix check, hand-back) | allow |
| One record that holds the lines of two reports | allow |
| A PASS whose findings mention FAIL, with its PASS record | allow |
| A PR open and no report | allow |
| No PR known, no `transcript_path`, an unreadable or empty transcript | allow |
| A record with a Fix check line (PASS or FAIL) for PR 1464, then a push to its head branch | deny |
| The same record for a PR the transcript never opens, then a push | deny |
| The same record, then a push to the branch of a PR opened after it | allow |
| A record with a Round line only for PR 1464, then a push to its head branch | allow |
| A dry run, or a `git commit` whose message says push, beside a FAIL | allow |
| A builder push where only the builder's own file holds a FAIL | allow |

## The misses

- A report with no PR known yet passes. The first push of a lane is never blocked on a transcript that shows no PR.
- The round number is not checked against the report's round. A record for round 1 clears a round 2 report with the same role and verdict.
- Workflow agents are not read: only Agent results, notices and hand-backs are.
- A PR opened by another session reads as no PR, because the session's own transcript shows no call that opened it.
- A design-reviewer fix check is not read. A record holds a Fix check line for the reviewer only.
- The fix-check refusal reads only a record that parses. A PR whose `create_pull_request` result names no `number` has an unknown head.
- With a head unknown, the fix-check refusal holds for every push of the session until a PR opens after the record. A PR another session opened, then fixed, blocks this session's pushes to any branch.
- A fork's `head` of the form `owner:branch` is read as `branch`.
- A destination the guard cannot resolve never matches a known head, so that push passes.
- A transcript that cannot be read, or a merge module that cannot load, passes (fail open).

## The cost

- One read of the session's transcript per non-dry-run `git push`. A line is parsed only when it names an Agent call, a PR or comment tool, a notice or a hand-back, or the id of a call already seen.
- The merge module loads only when the scan finds a report with a Done-line shape, or a posted comment holding a `Fix check:` line. A normal push loads none.
- The destination is read (the `symbolic-ref` and `config` reads of `push_destinations`) only when a record holds a Fix check line.
- No process, no file, no timer.

Risk: incident (PR #1467 and PR #1490).

Kind: process
Home: hooks/guard_push_delete.py

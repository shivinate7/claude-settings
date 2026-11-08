# A push waits for the review record of each report

## The ruling

A shell `git push` is refused while a reviewer or design-reviewer report has no posted review record. Coordinator, 2026-11-07 14:38 CST and 14:53 CST. Source: the brief. Process-only.

- The refusal reads the session's own transcript (`transcript_path`), also when `agent_id` is set. It never reads an agent's own file (`subagents/agent-<id>.jsonl`).
- It needs a PR known to the session: a successful `mcp__github__create_pull_request` call, a successful Bash `gh pr create`, or a posted record.
- A report is a Done line: `PASS|FAIL|PARTIAL, round N of 3, <model>`, or `PASS|FAIL, fix check, <model>`. Indents and markdown leads are allowed. A finding line never counts, and nor does any line inside a ``` fence.
- The verdict is read in three shapes (coordinator, 2026-11-08 16:25 CST, review round 1): the ruled line under a `Done` label; the same line on the label's own line (`Done: FAIL, round 1 of 3, <model>`); and a label line that holds a round or fix-check marker, in any case, and a verdict word in any order (`Done: Round 1 reviewer haiku FAIL`). On that label line the verdict word is the first all-capitals word that is PASS, FAIL or PARTIAL (the merge tool's `REVIEW_VERDICTS`); another all-capitals word is never taken (`Done: HEAD round 1 FAIL` reads FAIL). A label line with other text and no verdict (`Done: see below`) leaves the ruled line under it as the Done line.
- A report read before any PR is known is held by its sha candidates (lane ruling, 2026-11-08, refining the coordinator's 16:25 CST ruling). A candidate is a hex word of 7-40 characters in the report text above its `agentId:` trailer; a word of 7-39 characters needs a digit and a letter. The first 8 distinct candidates are read. Each is read in the push's checkout, and counts only if all three hold:
  - it resolves to a commit (`git rev-parse --verify`);
  - it is the PR head or an ancestor of it (`git merge-base --is-ancestor`); the head is the local branch and `origin/<branch>`, and either may match;
  - it is not an ancestor of the default branch (`origin/HEAD`, else `origin/main`, read by `read_default_base`), so a diff base on main never counts.
- A word that does not resolve is skipped. Any other git failure counts the report (fail toward refusing). A PR whose head is unknown (known only from a posted record, or a `gh pr create` with no `--head`) skips the head test, so a resolved candidate off main counts. A push with no checkout counts each held report.
- A held report counts when one candidate counts. A report with no counting candidate is dropped. A held report that one PR does not count stays held for later PRs.
- A report arrives as an Agent tool result, as a `<task-notification>` (a user message or a `queued_command` attachment), or as an `<agent-message from="<agentId>">` hand-back. The hand-back maps through the `agentId: <id>` line of the Agent result.
- A record is a successful `mcp__github__add_issue_comment` whose body `parse_review` accepts, or a successful Bash `gh pr comment` or `gh api .../comments` whose command holds the full record body (from the marker line to the CI line, parsed by `parse_review`). It clears a report when it holds a line with that report's role, verdict and round number: a `Round` line, or the `Fix check` line for a fix check (role and verdict). One record clears every report whose line it holds.
- A dry run, a commit and a transcript that cannot be read pass.
- A second refusal, same rule id (coordinator, 2026-11-07 15:19 CST): a push to the head branch of PR n is refused when the transcript holds a successful posted record, accepted by `parse_review`, with a Fix check line for PR n. The merge tool takes one fix check per record, so the next fix goes on a new branch and a new PR. The destination is read with `push_destinations`. PR n maps to its head branch through a successful PR-opening call: the `head` of a `create_pull_request` input and the `number` of its result, or the `--head` of a Bash `gh pr create` and the URL it printed. With n's head unknown, the push passes, so the next PR is never deadlocked. This refusal names no branch.
- The refusal tells the lane to render the record with `merge <pr> --review-record --head <reviewed sha>`, post it with the GitHub MCP comment tool, then push. It names no target (rule `git-remedy-never-names-target`).
- Rule id `push-needs-review-record`, deny, in the cloud and locally. The incident ran in the cloud, so no gate.

## The incidents

- PR #1467, lane `notes-delete-pass`: the lane pushed a fix before it posted the round-1 FAIL record. `--fix-check` then refused, because it needs the record of the head the review read.
- PR #1490, lane `notes-fix-large-1`: a round that came back PASS with notes was pushed over before its record was posted. A PASS needs a record too.

- PR #1464, lane `notes-fix-report`: a second fix was pushed to the branch of a PR whose record already held a Fix check line. The merge tool takes one fix check per record, so the second fix had no check.

## The harm

- The review trail loses the round: the record for the reviewed head is never posted, and the push makes that head stale.
- The fix skips its fix check: `--fix-check` has no record to start from.
- A second fix on a fixed head has no fix check of its own (record `pr-review-record`, one fix check per record).

## The cases

The cases are in `hooks/test_guard.py`, section 5f-2 (family `push-needs-review-record`).

| Transcript shows | Outcome |
|---|---|
| PR known, a reviewer or design-reviewer report of any verdict (result, notice, attachment, hand-back), no record | deny |
| Done line with a bold lead, 1500 later reads, a push from the PowerShell tool, a builder push whose parent file holds the report | deny |
| A report whose record holds another role, another verdict, another round number, or a Fix check line for a round report | deny |
| A PR opened by a Bash `gh pr create`, then an unrecorded report | deny |
| A record post that returned an error, or a comment that is no record | deny |
| An unrecorded report, then a later report whose record holds only its own line | deny |
| The PR known only from a posted record, then a later unrecorded report | deny |
| Each report followed by a record that holds its role and verdict (round, PARTIAL, fix check, hand-back) | allow |
| One record that holds the lines of two reports, or the report's round line beside another round's | allow |
| A record posted by a Bash `gh pr comment` or `gh api .../comments` with the full body | allow |
| A PASS whose fenced sample above its Done line reads FAIL, with its PASS record | allow |
| A PASS whose findings mention FAIL, with its PASS record | allow |
| A PR open and no report | allow |
| No PR known, no `transcript_path`, an unreadable or empty transcript | allow |
| A record with a Fix check line (PASS or FAIL) for PR 1464, then a push to its head branch | deny |
| The same record for a PR the transcript never opens, then a push | allow |
| The same record, then a push to the branch of a PR opened after it | allow |
| A record with a Round line only for PR 1464, then a push to its head branch | allow |
| A dry run, or a `git commit` whose message says push, beside a FAIL | allow |
| A builder push where only the builder's own file holds a FAIL | allow |
| A verdict on the Done label line, no record: reviewer FAIL round 1, reviewer PARTIAL round 1, design-reviewer PASS round 2 | deny |
| A reviewer FAIL round 1 on the Done label line, with its FAIL record | allow |
| A Done label line reading `see below`, then a ruled FAIL round 1 line, no record | deny |
| A held label line `Done: Round 1 ...` (capital R), naming head B, then the PR, no record | deny |
| A held label line `Done: HEAD round 1 FAIL`, naming head B, then the PR, no record | deny |
| A held FAIL naming only diff base A (on main, parent of head B), then the PR, no record | allow |
| A held FAIL naming diff base A then head B, then the PR, no record | deny |
| A held FAIL naming head B, then the PR, then its FAIL record | allow |
| A held FAIL naming a path word that resolves to no commit, then a commit off main that B does not hold | allow |
| A held FAIL naming no sha but an `agentId:` trailer with a hex id | allow |
| A held FAIL naming a commit off main that head B does not hold, then the PR | allow |
| A held FAIL naming no sha, then the PR | allow |
| A held FAIL naming head B, then a PR for another branch, then the PR for B, no record | deny |

The cost case `a push reads git for a held report only when one is held` pins zero git reads with no report held, and shows the count sees the reads of a held report.

## The misses

- A report with no PR known yet passes while it names no sha, while no PR is ever known, or when no candidate is on the PR head's history. The first push of a lane is never blocked on a transcript that shows no PR.
- A report read before any PR, whose only counting commit is on main, is dropped: a review of a head already merged to the default branch.
- A report whose only sha is seven decimal digits is read as naming none, so it is dropped.
- A report's candidates past the first 8 are not read. A report whose head sha comes after 8 other hex words is dropped.
- In a repo where no default branch resolves (`origin/HEAD`, `origin/main`, `origin/master`, `main`, `master`), the main test is skipped, so a diff base counts.
- The PR scope is by round match only. A record is not matched to a PR number, so a record for another PR clears a report with the same role, verdict and round. (Round-1 review finding.)
- A fix check whose PR head is unknown passes: a PR opened by another session, a `gh pr create` with no `--head`, or a result with no `number`. (Round-1 review finding; the earlier refusal deadlocked the next PR.)
- A resumed reviewer's report arrives as a hand-back, and it is read like any other report. (Round-1 review finding.)
- Workflow agents are not read: only Agent results, notices and hand-backs are.
- A PR opened by another session reads as no PR, because the session's own transcript shows no call that opened it.
- A design-reviewer fix check is not read. A record holds a Fix check line for the reviewer only.
- A fork's `head` of the form `owner:branch` is read as `branch`.
- A Bash record post whose command does not hold the record text (a body read from a file) is not a record.
- A destination the guard cannot resolve never matches a known head, so that push passes.
- A transcript that cannot be read, or a merge module that cannot load, passes (fail open).

## The cost

- One pass over the session's transcript per non-dry-run `git push`. A line is parsed in two cases. It names an Agent call, a PR or comment tool, a `gh` PR or comment call, a notice or a hand-back. Or it is a tool result for a call already seen (one dict lookup per id). Round 1 measured the old scan at 8.7 s on 1000 Agent calls. It looped every seen id for each line.
- Measured on the one-pass scan: 0.08 s on a synthetic 13 MB transcript of 12,000 lines (1000 Agent calls with reports, 5000 reads), merge module load included.
- The merge module loads only when the scan finds a report with a Done-line shape, a Done label line that holds a round or fix-check marker, or a posted comment holding a `Fix check:` line. A normal push loads none.
- The destination is read (the `symbolic-ref` and `config` reads of `push_destinations`) only when a record holds a Fix check line.
- The held-report rule reads git only while a report is held. A push with no held report starts no git process. Each PR event or posted record that finds held reports reads, in the push's checkout:
  - 2 `git rev-parse` for the head (the local branch, then `origin/<branch>`), or 0 when the head is unknown;
  - the default branch by `read_default_base`: 1 `git symbolic-ref` and 1 `git rev-parse` when `origin/HEAD` resolves, at most 1 + 5;
  - per distinct candidate: 1 `git rev-parse`; if it resolves, 1 `git merge-base --is-ancestor` against the default branch; if it is off main, 1 against each head commit (at most 2). That is at most 4 reads per candidate.
  - A report stops at its first counting candidate, and a word is read once per event. So one held report costs at most 8 × 4 = 32 reads per event, and a push at most 2 + 6 + 32 × (held reports) per event.
- No timer, no file, no long-lived process.

Risk: incident (PR #1467 and PR #1490).

Kind: process
Home: hooks/guard_push_delete.py

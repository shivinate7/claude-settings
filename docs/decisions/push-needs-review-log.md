# A push asks for the review log of each report

Decision slug `push-needs-review-log`; rule id and test family `push-needs-review-record` are kept names (GLOSSARY.md, review log row).

## The ruling

A shell `git push` asks while a reviewer or design-reviewer report has no posted review log. Coordinator, 2026-11-07 14:38 CST and 14:53 CST. Source: the brief. Process-only.
Coordinator, 2026-11-12 14:23 CST: lane started; asks, not denies (brief).
Coordinator, 2026-11-12 14:28 CST: correction. Round 3 and the net-value test follow R9 (restart-plan 3.8, "One rounds record; no round 3 after a pass"; owner pick 471 a).

The verdict is ask for a report with no review log. A push to the head branch of a PR whose posted review log holds a `Fix check:` line is refused (guard.py `refuse`). Rule id `push-needs-review-record`, ask and refuse, in the cloud and locally. The incident ran in the cloud, so no gate.

- The refusal reads the session's own transcript (`transcript_path`), also when `agent_id` is set. It never reads an agent's own file (`subagents/agent-<id>.jsonl`).
- It needs a PR known to the session: a successful `mcp__github__create_pull_request` call, a successful Bash `gh pr create`, or a posted review log.
- A report is a Done line: `PASS|FAIL|PARTIAL, round N of 3, <model>`, or `PASS|FAIL, fix check, <model>`. Indents and markdown leads are allowed. A finding line never counts, and nor does any line inside a ``` fence.
- The verdict is read in three shapes (coordinator, 2026-11-08 16:25 CST, review round 1). One is the ruled line under a `Done` label. One is the same line on the label's own line (`Done: FAIL, round 1 of 3, <model>`). One is a label line that holds a round or `fix check` marker, in any case, and a verdict word in any order (`Done: Round 1 reviewer haiku FAIL`). On that label line the verdict word is the first all-capitals word that is PASS, FAIL or PARTIAL (the merge tool's `REVIEW_VERDICTS`); another all-capitals word is never taken (`Done: HEAD round 1 FAIL` reads FAIL). A label line with other text and no verdict (`Done: see below`) leaves the ruled line under it as the Done line.
- A report read before any PR is known is held by its sha candidates (lane ruling, 2026-11-08, refining the coordinator's 16:25 CST ruling). A candidate is a hex word of 7-40 characters in the report text above its `agentId:` trailer; a word of 7-39 characters needs a digit and a letter. The first 8 distinct candidates are read. Each is read in the push's checkout, and counts only if all three hold:
  - it resolves to a commit (`git rev-parse --verify`);
  - it is the PR head or an ancestor of it (`git merge-base --is-ancestor`); the head is the local branch and `origin/<branch>`, and either may match;
  - it is not an ancestor of the default branch (`origin/HEAD`, else `origin/main`, read by `read_default_base`), so a diff base on main never counts.
- A word that does not resolve is skipped. Any other git failure counts the report (fail toward refusing). A PR whose head is unknown (known only from a posted review log, a `gh pr create` with no `--head`, or a head branch that resolves neither locally nor as `origin/<branch>`) skips the head test, so a resolved candidate off main counts. A push with no checkout counts each held report.
- A held report counts when one candidate counts. A report with no counting candidate is dropped. A held report that one PR does not count stays held for later PRs.
- A report arrives as an Agent tool result, as a `<task-notification>` (a user message or a `queued_command` attachment), or as an `<agent-message from="<agentId>">` hand-back. The hand-back maps through the `agentId: <id>` line of the Agent result.
- A review log is a successful `mcp__github__add_issue_comment` whose body `parse_review` accepts, or a successful Bash `gh pr comment` or `gh api .../comments` whose command holds the full review log body (from the marker line to the CI line, parsed by `parse_review`). It clears a report when it holds a line with that report's role, verdict and round: a `Round` line, or the `Fix check` line for a fix verifier (role and verdict). One review log clears every report whose line it holds.
- Head match. A round report names its reviewed head with `Reviewed at head <sha>`, `Diff base A, head B`, or `reviewed <sha>`, above its `agentId:` trailer. A head after `Base:` or `main head` is the base, never the reviewed head. A round report that names a head is cleared only by a review log whose `Head:` line matches one of them. A match is a prefix of 7 or more characters, either way. A fix verifier report is cleared by a review log whose `Head:` or `Fix check:` sha equals the head it names. The merge tool's normal review log has Head B and Fix check A. A report that names no head matches by role, verdict and round alone (known miss, also a report read before any PR is known).
- A dry run, a commit and a transcript that cannot be read pass.
- A transcript line that is not a JSON object, or a message with no `content`, is stepped over, and the rest of the transcript is still read (`_transcript_events`). Such a line holds no tool call or result, so the step never lets a push pass that a pending report would stop.
- A moved head (coordinator, 2026-11-12 23:49 CST). A round report that names a head, when the PR's live head has moved past it (the named head is an ancestor of the live head, not equal to it), gets another ask text. It tells the lane to post a fresh round at the live head with `merge <pr> --review-record --head <live sha>` (the first 12 characters of the sha), and says the review log for the old head cannot be posted. It names no target. The live head is the tip of the pushed branch (`origin/<branch>`, else the local branch): the pushed branch that a PR known to the session heads, else the pushed branches, else the latest PR's head branch. So the route holds when the PR is known only from a posted review log, or a PR on another branch was opened after the FAIL. A fix verifier report never gets this text: only round reports do.
- A superseded report (coordinator, 2026-11-12 23:49 CST). A held round report that names a head stops asking on one condition. A review log posted after the report must be for the report's own PR (the latest PR the session knew when it read the report, from a PR-opening result or a posted review log) and hold a line with the same role and the same round (any verdict). A log for another PR never clears it, and a report whose PR is unknown stays held. That log's head must be a strict descendant of a head the report names. A log at a sibling or unrelated head, at the same head, or at an earlier head does not clear it. A log posted before the report does not clear it. When the ancestry check cannot run (no checkout, a sha git cannot resolve), the report stays held: this path never fails open.
- The refusal tells the lane to render the review log with `merge <pr> --review-record --head <reviewed sha>`, post it with the GitHub MCP comment tool, then push. It names no target (rule `git-remedy-never-names-target`).
- A second refusal, same rule id (coordinator, 2026-11-07 15:19 CST): a push to the head branch of PR n is refused when the transcript holds a successful posted review log, accepted by `parse_review`, with a `Fix check:` line for PR n. It comes before the ask for a pending report. The merge tool takes one fix verifier per review log, so the next fix goes on a new branch and a new PR. The destination is read with `push_destinations`. PR n maps to its head branch through a successful PR-opening call: the `head` of a `create_pull_request` input and the `number` of its result, or the `--head` of a Bash `gh pr create` and the URL it printed. With n's head unknown, the push passes, so the next PR is never deadlocked. This refusal names no branch.

Dated by: the review log format in `merge/merge.py` (`parse_review`, `REVIEW_VERDICTS`, `REVIEW_FIX_VERDICTS`). A change to that format re-opens this record.

## The incidents

- PR #1467, lane `notes-delete-pass`: the lane pushed a fix before it posted the round-1 FAIL review log. `--fix-check` then refused, because it needs the review log of the head the review read.
- PR #1490, lane `notes-fix-large-1`: a round that came back PASS with notes was pushed over before its review log was posted. A PASS needs a review log too.
- PR #1464, lane `notes-fix-report`: a second fix was pushed to the branch of a PR whose review log already held a `Fix check:` line. The merge tool takes one fix verifier per review log, so the second fix had no fix verifier.
- PR #2871: round-1 review log at head 08462577, fix pushed, new head 5b77f144 (from the PR's comments).
- PR #2921: a round-1 FAIL report with no review log at all. Shape from the cases.
- PR #2860: no incident detail on this branch. Git history names it as lane #2860, merged into batch 106.
- PR #2904: no reference on this branch.
- 2026-11-12 14:18 CST, runner 10: a fix pushed after round 1 without the round-1 review log.

## The harm

- The review trail loses the round: the review log for the reviewed head is never posted, and the push makes that head stale.
- The fix skips its fix verifier: `--fix-check` has no review log to start from.
- A second fix on a fixed head has no fix verifier of its own (review log `pr-review-record`, one fix verifier per review log).

## The cases

The cases are in `tests/guard/s21305-push-needs-review-log.py` (section 21305, family `push-needs-review-record`).

| Transcript shows | Outcome |
|---|---|
| PR known, a reviewer or design-reviewer report of any verdict (result, notice, attachment, hand-back), no review log | ask |
| Done line with a bold lead, 1500 later reads, a push from the PowerShell tool, a builder push whose parent file holds the report | ask |
| A report whose review log holds another role, another verdict, or another round number | ask |
| A round 1 FAIL beside a review log whose `Fix check:` line is for PR 1467, then a push to another branch (a `Fix check:` line alone does not clear a round report) | ask |
| A round 1 FAIL beside a review log whose `Fix check:` line is for PR 1467, then a push to PR 1467's head branch (checked before any ask) | refuse |
| A PR opened by a Bash `gh pr create`, then a report with no review log | ask |
| A PR opened by `gh -R o/r pr create`, `gh --repo o/r pr create` or `gh pr -R o/r create`, then a report with no review log | ask |
| A FAIL round 1, then its review log posted by `gh -R o/r pr comment` or `gh --repo o/r pr comment`, then a push | allow |
| A review log post that returned an error, or a comment that is no review log | ask |
| A report with no review log, then a later report whose review log holds only its own line, at the same head or a head that does not descend from the first report's head | ask |
| A round 1 FAIL at head B, then a round 1 PASS at its descendant D2 with its review log posted at D2 | allow (superseded) |
| The same, with no review log at D2 | ask, text names the fresh round at the live head |
| A round 1 FAIL at head B, then a round 1 review log at head C, no descendant of B | ask |
| A round 1 FAIL at head B, then a review log at its descendant D2 holding another role's line, or a round 1 line against a round 2 FAIL | ask |
| A round 1 FAIL at head B for PR 1467, then a round 1 review log at D2 for PR 1468 | ask |
| The same review log for PR 1467 | allow |
| A round 2 FAIL at head B, the PR known only from a posted review log, a push to the pushed branch whose head is D2 | ask, route names D2 |
| A round 1 FAIL at head B, then a PR on another branch opened, a push to the first PR's branch | ask, route names that branch's head |
| A fix verifier PASS at head B with no review log, the PR head at D2 past it; or a fresh round at D2 posted after it | ask, ordinary text |
| A fix verifier PASS at head B, then a review log at D2 whose `Fix check:` line is B | allow |
| The PR known only from a posted review log, then a later report with no review log | ask |
| Each report followed by a review log that holds its role and verdict (round, PARTIAL, fix verifier, hand-back) | allow |
| One review log that holds the lines of two reports, or the report's round line beside another round's | allow |
| A review log posted by a Bash `gh pr comment` or `gh api .../comments` with the full body | allow |
| A PASS whose fenced sample above its Done line reads FAIL, with its PASS review log | allow |
| A PASS whose findings mention FAIL, with its PASS review log | allow |
| A PR open and no report | allow |
| No PR known, no `transcript_path`, an unreadable or empty transcript | allow |
| A review log with a `Fix check:` line (PASS or FAIL) for PR 1464, then a push to its head branch | refuse |
| The same review log for a PR the transcript never opens, then a push | allow |
| The same review log, then a push to the branch of a PR opened after it | allow |
| A review log with a Round line only for PR 1464, then a push to its head branch | allow |
| A dry run, or a `git commit` whose message says push, beside a FAIL | allow |
| A builder push where only the builder's own file holds a FAIL | allow |
| A verdict on the Done label line, no review log: reviewer FAIL round 1, reviewer PARTIAL round 1, design-reviewer PASS round 2 | ask |
| A reviewer FAIL round 1 on the Done label line, with its FAIL review log | allow |
| A Done label line reading `see below`, then a ruled FAIL round 1 line, no review log | ask |
| A held label line `Done: Round 1 ...` (capital R), naming head B, then the PR, no review log | ask |
| A held label line `Done: HEAD round 1 FAIL`, naming head B, then the PR, no review log | ask |
| A held FAIL naming only diff base A (on main, parent of head B), then the PR, no review log | allow |
| A held FAIL naming diff base A then head B, then the PR, no review log | ask |
| A held FAIL naming head B, then the PR, then its FAIL review log | allow |
| A held FAIL naming a path word that resolves to no commit, then a commit off main that B does not hold | allow |
| A held FAIL naming no sha but an `agentId:` trailer with a hex id | allow |
| A held FAIL naming a commit off main that head B does not hold, then the PR | allow |
| A held FAIL naming no sha, then the PR | allow |
| A held FAIL naming head B, then a PR for another branch, then the PR for B, no review log | ask |
| A round 1 review log at head 08462577 (PR #2871), then a round 2 FAIL naming head 5b77f144 with no review log, then a push | ask |
| A round 1 FAIL naming head 5b77f144, and a fix verifier PASS naming head 08462577, one review log at head 5b77f144 holding both lines, then a push to another branch | allow (the fix verifier clears by its own sha) |
| A round 1 FAIL at head 08462577 with its review log there, then a fix verifier PASS naming head 5b77f144, and a review log at head 5b77f144 whose `Fix check:` line is 08462577, then a push to another branch | allow |
| A round 1 FAIL whose text reads `Base: main head 5b77f144, reviewed 08462577`, with its review log at head 5b77f144 only, then a push | ask |
| A fix verifier PASS for PR 1464 posted, then a round 2 FAIL with no review log, then a push to PR 1464's head branch (checked before any ask) | refuse |

The cost case `a push reads git for a held report only when one is held` pins zero git reads with no report held, and shows the count sees the reads of a held report.

## The misses

- A report with no PR known yet passes while it names no sha, while no PR is ever known, or when no candidate is on the PR head's history. The first push of a lane is never blocked on a transcript that shows no PR.
- A report read before any PR, whose only counting commit is on main, is dropped: a review of a head already merged to the default branch.
- A report whose only sha is seven decimal digits is read as naming none, so it is dropped.
- A report's candidates past the first 8 are not read. A report whose head sha comes after 8 other hex words is dropped.
- In a repo where no default branch resolves (`origin/HEAD`, `origin/main`, `origin/master`, `main`, `master`), the main test is skipped, so a diff base counts.
- A report read before any PR is known matches its review log by role, verdict and round only. Its named head is not checked, so a review log at another head clears it.
- The direct match is by line only. A review log that holds the report's role, verdict and round at its named head clears it, whatever PR the log names. Only the superseded-report path (a descendant head) checks the PR number.
- A fix verifier whose PR head is unknown passes: a PR opened by another session, a `gh pr create` with no `--head` or `-H`, or a result with no `number`. The same head-less PR skips the fix-branch refusal (`review_log_hit`), so a push to its head branch after its `Fix check:` line passes unless a report is pending.
- A resumed reviewer's report arrives as a hand-back, and it is read like any other report.
- Workflow agents are not read: only Agent results, notices and hand-backs are.
- A PR opened by another session reads as no PR, because the session's own transcript shows no call that opened it.
- A design-reviewer fix verifier is not read. A review log holds a `Fix check:` line for the reviewer only.
- A fork's `head` of the form `owner:branch` is read as `branch`.
- A Bash review log post whose command does not hold the review log text (a body read from a file) is not a review log.
- A destination the guard cannot resolve never matches a known head, so that push passes.
- Any error passes (fail open): a transcript that cannot be read, a merge module that cannot load, or an exception in `review_log_hit` (`except Exception: pass`; note `push-record-scan-error-fails-open`).
- A round report pushed over without its review log cannot get its own review log once the head moved (`merge --review-record --head A` refuses). A fresh round at the live head clears it, when its review log holds the same role and round at a descendant head and is posted after the report (see "A superseded report"). The ask text names that route. A report that names no head, a log at a non-descendant head, and an unresolvable head still ask.
- Ask scope: any push while a report is pending asks, an unrelated branch too (old ruled behaviour).

## The cost

- One pass over the session's transcript per non-dry-run `git push` (`_transcript_events`). A line is parsed only when it holds a mark (a tool name, a notice or hand-back tag, a `gh` PR or comment call), or it is a tool result for a call already seen (one dict lookup per id). Measured 0.08 s on a synthetic 13 MB transcript of 12,000 lines (1000 Agent calls with reports, 5000 reads), merge module load included, before the head match and the indirect `gh pr create` read were added. Unmeasured since.
- The merge module loads only when the scan finds one of three things: a report with the Done-line shape; a Done label line that holds a round or fix-check marker; a posted comment holding a `Fix check:` line. A normal push loads none.
- The destination is read (the `symbolic-ref` and `config` reads of `push_destinations`) only when a review log holds a Fix check line.
- The held-report rule reads git only while a report is held. A push with no held report starts no git process. Each PR event or posted review log that finds held reports reads, in the push's checkout (`_held_counts`):
  - 2 `git rev-parse` for the head (the local branch, then `origin/<branch>`), or 0 when the head is unknown;
  - the default branch by `read_default_base` (`hooks/git_reads.py`): 1 `git symbolic-ref`, then up to 5 `git rev-parse`, stopping at the first that resolves;
  - per distinct candidate: 1 `git rev-parse`; if it resolves, 1 `git merge-base --is-ancestor` against the default branch; if it is off main, up to 2 more against the head commits. At most 4 reads per candidate.
  - A report stops at its first counting candidate, a report reads at most 8 candidates (`_HELD_SHA_CAP`), and a word is read once per event. So one held report costs at most 8 × 4 = 32 reads per event, and an event at most 2 + 6 + 32 × (held reports).
- Two reads added, both only while a report is held (coordinator, 2026-11-12 23:49 CST):
  - At the ask, to choose the moved-head text (`_live_head`), when a pending round report names a head and a checkout is known: 2 `git rev-parse` for the tips of each pushed branch, read once per push however many reports are pending. Per named head of a pending round report: 1 `git rev-parse` plus up to 2 `git merge-base --is-ancestor` per tip. A push that passes reads none of these.
  - At a posted review log: one `git merge-base --is-ancestor` per named head of a held round report, only when the log is for the report's PR. It must also hold a line of that report's role and round at another head (`_RecordLines.supersedes`).
- No timer, no file, no long-lived process.

## Risks and notes

- Open question for the owner, not decided here (raised 2026-11-12 16:25 CST): a push of main merged into a fixed PR's branch is refused by the fix-branch refusal, which reads the push destination only. The owner's ruling of 2026-11-10 14:07 CST (`docs/decisions/pr-review-record.md`) lets a clean merge of main keep the review log. Should such a push pass?

Risk: incident (PR #1467, PR #1490, PR #2871, PR #2921, and runner 10 on 2026-11-12 14:18 CST).

Kind: process
Home: hooks/guard_push_delete.py

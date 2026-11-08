# A pull request carries its review record on the PR

## The ruling

Owner, 2026-11-01 04:26 CST, waiting-page item 113 a. Source: the brief. The waiting page is not in this repo.

- Each PR carries a review record.
- The batch runner finds reviewed, green PRs itself.
- No merge message.

## The incident

- 2026-10-31 15:31 CDT. The auto-mode classifier refused a `send_message`. It handed banchi PR #1002 to the batch runner as "Merge Without Review".
- The refused act was a handoff, not an unreviewed merge.
- Unknown: what banchi names. In this repo, PR #1002 is idle-resume-compacts, merged at commit d39a0040. Unchecked whether they are the same PR.

## The form

The comment is the record. Its body:

```
<!-- review-record -->
PR: #<n>
Head: <40-hex sha>
Kind: normal|delete-only|docs-only
Guard or check: yes|no
Round <n>: <reviewer|design-reviewer>, <model>, <PASS|FAIL|PARTIAL>
Fix check: <40-hex reviewed head>, reviewer, <model>, <PASS|FAIL>
Net value: not owed|zero|positive|negative
Stamp: <16 hex>
CI: read live by merge --reviewed
```

- The first line is the marker. A line `---` after the CI line ends the record, so the attribution footer may follow.
- One `Round` line per reviewer. A round can hold more than one line.
- The `Fix check` line is optional, comes once after the Round lines, and is not a round (record `hold-unsafe-after-round-3`). `--fix-check HEAD:reviewer:MODEL:VERDICT` writes it. Its reviewed head must differ from Head. A FAIL is open. A PASS counts as its round passing in any round; after round 3 it keeps the net value round 3 gave; with no round recorded it reads open.
- The `Stamp` line comes once, after Net value and just above the CI line. It is the first 16 hex digits of sha256 over `REVIEW_STAMP_SALT` and every line above it, marker included (`review_stamp`). Each line counts without its trailing whitespace, so a body that the MCP tool re-spaced or gave CRLF ends keeps its stamp. `review_body` writes it, and `parse_review` returns None for a body with no Stamp line (a record created before the cutover may have none; see "The cutover"), a Stamp that does not match, or a line above it that was edited. Mistakes it catches: a record typed by hand, or copied from another PR's record and edited (incidents PR #1512, PR #1472, PR #1494, PR #1812, PR #1839). It is no secret: a forger can compute it, and this record does not defend against one (record `guard-guards-mistakes-only`).
- The comment never stores CI state. The merge tool reads CI live. `merge --reviewed` shows a draft
  PR as `CI draft, no run`, because a draft has no CI run.
- `parse_review` ignores trailing whitespace on each line, the marker line included, and trailing blank lines.
- A body is not a record when the marker is missing, a field is malformed, round numbers skip, or a round is above 3.
- The newest record for a head counts. A record for an old head is stale.
- `merge <pr> --review-record --head <40-hex sha>` prints the body for the head the review read. When the PR's live head is another sha, it stops with exit 1 and prints no body, so a push after the review never relabels old rounds as current.
- The lane-lint check. `merge <pr> --review-record` checks the lint before it prints a record whose state is `done` (`review_state`). A done record is what the lane gives the batch runner, and a lane gives it only a head that passes `merge --lane-lint` (decision `lanes-run-no-full-ci-job`). That includes a delete-only record after a round 1 FAIL, and a docs-only record with no round. A PASS kept open by a design-reviewer FAIL is not done, so it prints whatever the lint says. Incident: PR #1502 was given to the batch runner with CiCoverage red.
- A record the lint refuses prints no body and exits nonzero. The refusal names `merge --lane-lint <pr>` as its remedy. `lane_lint` stays the one home of the lint: the render calls it with the checked head sha and the PR's base, inside `release_on_signals`, so a SIGTERM still removes its temporary worktree. A FAIL is final: no flag lifts it, and the refusal keeps the line that no override lifts it. An unknown step that `lane_lint` can lift refuses and names `--lint-unknown-ok "REASON"`. The render passes that reason to `lane_lint`, which logs it, and prints the record. A timed-out or odd-exit lint is final, like a FAIL. On an open record the lint does not run, so the flag has no effect.
- A lane posts the body with the GitHub MCP comment tool after each round. `gh pr comment` uses GraphQL, which the cloud refuses (route graphql-gh-api-cloud).
- The one home of the form is the merge tool (`merge/merge.py`). `review_body` writes the body, `review_stamp` gives its Stamp line, `parse_review` reads it, and `review_state` gives each record's state. `reviewed_lines` prints the `--reviewed` list, `round_arg` reads `--round`, and `Host.review_comments` makes the one list read.

## The done rules

A change is done when one of these holds (rule `roles-review-cap-three`):

- round 1 or 2 is its last round, that round is PASS or a fix check PASSes after its FAIL, and the last `design-reviewer` line (across all rounds) is PASS or absent;
- round 3 is done, and Guard or check is `no`;
- round 3 is done, Guard or check is `yes`, and Net value is zero or positive;
- Kind is `delete-only`, Guard or check is `no`, and round 1 is done;
- Kind is `docs-only`, with zero rounds, unless the change is a record that files an owner ruling. That change posts `Kind: normal` with one round (decision `docs-only-prs-skip-review`).

- A last `design-reviewer` line of FAIL or PARTIAL keeps a record open on the PASS rule. The round 3 and `delete-only` done rules stay done, and their reason names the design failure.
- A round 3 verdict does not decide done. When Guard or check is `yes`, Net value does, even after a round 3 PASS: `not owed` is open, and `negative` holds the change (record `hold-unsafe-after-round-3`).
- A `delete-only` change with Guard or check `yes` and a round 1 FAIL is open unless a fix check PASSes. The rule owes rounds 2 and 3 when round 1 finds a safety hole.
- `docs-only` with Guard or check `yes` is not a record: docs-only means no guard or check. The tool refuses it when it writes, and the parser rejects it.

## The cost

Counted as real `gh` calls, one call per page of a list read. Most reads fit one page of 100.

- `merge --reviewed` makes two list reads per run. One lists the open PRs. The other lists the repo's issue comments since the oldest open PR, so it pages every comment of the repo since then, not only review records. The cost grows with the repo's comment traffic and with the age of the oldest open PR.
- Not a `gh` call: each `--reviewed` run also runs one `git fetch origin main` (`load_config`) and local git reads.
- Not a `gh` call: `merge --reviewed` and `--fix-check` each run one `git log` (`review_stamp_since`) to find the cutover. It is cached for the process, reads one file's history on `origin/<base>`, and writes nothing.
- Each ready PR that has a record adds three reads: the check runs, the commit statuses and the branch protection (required checks mode `protection`). A draft, and a PR with no record, add none.
- One ready PR with a record: five calls. With a pinned `merge.requiredChecks` list: also five, because the one protection compare moves to the start of the run and the per-PR protection read goes.
- `merge <pr> --review-record`: one PR read per call. `--fix-check` adds one paged read of the repo's issue comments since the PR opened. It writes nothing. A render whose record is done also runs `lane_lint` once on the checked head sha: no PR read, one `git fetch origin <base>` (more when the head is not local), one temporary worktree and one `ci-job checks --lint` run, removed on exit. A render whose record is open runs none. The Stamp is one sha256 hash in the process that renders or parses, with no extra call, file or process.
- No new long-lived process, file or timer. The one cache is the cutover time, kept for the process. The batch runner calls the list at each wake. A lane calls the render at each round, and a render of a done record costs one lint run (above).
- The test `ReviewedList` in `merge/test_merge.py` pins the two list reads and the five calls for one ready PR.

## The guard

Rule `pr-review-record`, in `hooks/guard.py` (PreToolUse).

- The mistake: a lane typed the Head by hand on PR #1475 (15:10 CST, 2026-11-07). The record named a head that was not the live one, so the batch runner read it as stale.
- The second mistake: the records on PR #1502 and PR #1535 had prose after the CI line, so `parse_review` returned None and a lane fixed each by hand. The harm: `merge --reviewed` cannot read such a record, so the merge stalls. A body that opens with the marker must be the render output as it is. It may also be the render output, a line exactly `---`, then a footer, with no text between the CI line and `---`. One judge, `review_record_hit` in `hooks/guard_merge.py`, checks that form for a post, and its refusal names that form.
- It judges a post, or an edit, of a comment whose body starts with the marker, as its first line (`parse_review` reads it so): `mcp__github__add_issue_comment`, `mcp__github__update_issue_comment` (an edit, see the edit bullet below), `gh pr comment` and `gh issue comment` (`--body`, `-b`, `--body-file`, `-F`) and `gh api repos/O/R/issues/<n>/comments` (a shell variable for `<n>`, such as `$N`, is judged with no read: a marked body is refused, as its pull request cannot be checked) (`-f`, `-F`, `--field`, `--raw-field` with `body=` or `body=@file`). A heredoc body counts. A `$'...'` body is decoded first, as bash sends it (`ansi_c_decoded` in `hooks/guard_merge.py`, read only by this judge). A body of exactly `$(cat FILE)`, and a stdin body piped from `cat FILE`, are read from FILE. `--input` bodies are not read.
- It refuses unless the body parses (`parse_review`), its `PR:` equals the target PR, and its `Head:` equals the PR's live head. The refusal prints the render command for the live head, `merge <pr> --review-record --head <live sha> ...`.
- A malformed marked body is refused before any read.
- An edit of a record comment is refused; post a fresh record. A comment edit whose new body carries the marker is refused before any read, stamped or not, with `merge <pr> --review-record` as the remedy: `gh api` PATCH on `issues/comments/<id>` (`-X` or `--method`), `gh pr comment --edit-last`, `gh issue comment --edit-last`, and the MCP update tool. The Bash forms go through `review_post_hit` to `review_record_hit` with `edit` true. The MCP update goes through `judge()` (`hooks/guard.py`) to `review_record_hit` with `edit` true, not through `review_post_hit`. A comment id held in a shell variable (`$ID`, `${ID}`) counts as an id, so the edit is refused. `gh pr comment -e` and `gh issue comment -e` are posts: gh's `-e` is `--editor`, and only `--edit-last` is an edit. Incidents: a lane hand-edited records on #1926, #1531, #2016 and #1989. Open limit: an edit that strips the marker would need a read of the old body. Fix: `step:record-edit-reads-old-body` (an incident on #2063 at 09:44 CST shows Claude writes that form). A stripped record reads as no record, so the batch runner holds the PR. Until: 2026-11-21.
- It fails open. Three reads can fail: the live head, a body file, a body on stdin that no `cat FILE` supplies. Each one allows the call and prints one line on stderr that names the review record. A network blip must not block every post.
- The cost: one PR read for a post that names a PR number. Two (the open-PR list, then the PR) for a post that names no number or names a branch. None for a marked edit, which is refused unread, and none for any other comment or edit, which includes prose that names the marker below its first line. No file, no process, no log line. The tests pin these counts: a marked Bash PATCH, `--edit-last` and MCP edit make 0 reads, and `gh issue comment` 1.
- The gap: this guard does not read five bodies, on a post or on an edit:
  - a body held in a shell variable (`--body "$BODY"`);
  - a body from `$(printf ...)` or `$(echo ...)`, since only a body of exactly `$(cat FILE)` is read;
  - a stdin body that is neither a heredoc nor piped from `cat FILE`;
  - a `gh api --input` body;
  - a body sent to a full-URL endpoint, `gh api https://api.github.com/repos/...`.

## The limits

- Kind, Guard or check, and docs-only are the lane's own claims. The tool does not check paths. It does not tell a record that files an owner ruling from other docs. Kind stays the lane's claim. Guards stop mistakes, not attackers (record `guard-guards-mistakes-only`).
- Open: an integration PR has no record of its own.
- A `delete-only` change with Guard or check `no` and a round 1 FAIL reads done (rule `roles-review-cap-three`, the three-round review cap). The lane fixes the defect and posts a new review record for the new head, before the batch runner batches it. The fix push makes the old record stale.
- Unmeasured: whether the auto-mode classifier allows `merge --reviewed` and `merge <pr> --review-record`. Both are off `merge/cloud_allow.json`, which allows only `--confirm` and `--role`.
- One fix check per record. A second fix on a fixed head starts a new lane at round 1. `--fix-check` refuses unless its reviewed head equals the Head of the newest earlier record on the PR and that record has no Fix check line.

## The cutover

A record created before the stamp's merge commit reads as it did before: with no Stamp line, it still parses. A Stamp line that is there must match. A record created at or after that commit needs the stamp, so an unstamped one reads `bad`. The cutover is `review_stamp_since`: the committer time of the first first-parent commit on `origin/<base>` whose `merge/merge.py` holds `REVIEW_STAMP_SALT =`. When no such commit is found, or the read fails, every record reads as before. `Host.review_comments` gives each body with its created time. `merge --reviewed` and the `--fix-check` earlier read pass that time and the cutover to `parse_review`. A new post has no created time, so the guard always needs the stamp. Open PRs keep their old records. Each record a lane renders after the cutover carries the stamp.

## Lane picks

The coordinator answered both at 23:14. Process-only.

- Q1. Should preview or confirm refuse a PR with no valid record? Pick a: no refusal now. Ruling 113 a names discovery only (rule `outcomes-grant-covers-named-act`). Not taken: confirm refuses an integration PR when a lane tip has no done record. Also not taken: preview prints a review line only.
- Q2. Which wins when a decision record and rule `roles-review-cap-three` disagree? Pick a: the rule outranks a decision record. Round 3 counts as done, whatever its verdict. Not taken: a final PASS is always needed. Record `standing-merge-grant` says so now.

Kind: process
Home: merge/merge.py

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
- The `Fix check` line is optional, comes once after the Round lines, and is not a round (record `hold-unsafe-after-round-3`). `--fix-check HEAD:reviewer:MODEL:VERDICT` writes it. Its reviewed head must differ from Head. A FAIL is open. A fix check PASS counts as its round passing in any round when Guard or check is `no`. When Guard or check is `yes`, a fix check PASS before round 3 does not end review (item 402 a, owner, 2026-11-08 06:08 CST). After round 3, a PASS keeps the net value round 3 gave; with no round recorded it reads open.
- The `Stamp` line comes once, after Net value and just above the CI line. It is the first 16 hex digits of sha256 over `REVIEW_STAMP_SALT` and every line above it, marker included (`review_stamp`). Each line counts without its trailing whitespace, so a body that the MCP tool re-spaced or gave CRLF ends keeps its stamp. `review_body` writes it, and `parse_review` returns None for a body with no Stamp line (a record created before the cutover may have none; see "The cutover"), a Stamp that does not match, or a line above it that was edited. Mistakes it catches: a record typed by hand, or copied from another PR's record and edited (incidents PR #1512, PR #1472, PR #1494, PR #1812, PR #1839). It is no secret: a forger can compute it, and this record does not defend against one (record `guard-guards-mistakes-only`).
- The comment never stores CI state. The merge tool reads CI live. `merge --reviewed` shows a draft
  PR as `CI draft, no run`, because a draft has no CI run.
- `parse_review` ignores trailing whitespace on each line, the marker line included, and trailing blank lines.
- A body is not a record when the marker is missing, a field is malformed, round numbers skip, or a round is above 3.
- The newest record for a head counts. A record for an old head is stale.
- `merge <pr> --review-record --head <40-hex sha>` prints the body for the head the review read. When the PR's live head is another sha, it stops with exit 1 and prints no body, so a push after the review never relabels old rounds as current.
- The lane-lint check. `merge <pr> --review-record` checks the lint before it prints a record whose state is `done` (`review_state`). A done record is what the lane gives the batch runner, and a lane gives it only a head that passes `merge --lane-lint` (decision `lanes-run-no-full-ci-job`). That includes a delete-only record after a round 1 FAIL, and a docs-only record with no round. An open record, such as a PASS that a design-reviewer FAIL leaves open, runs no lint and prints. Incident: PR #1502 was given to the batch runner with CiCoverage red.
- A record the lint refuses prints no body and exits nonzero. The refusal names `merge --lane-lint <pr>` as its remedy. `lane_lint` stays the one home of the lint. The render calls it with the checked head sha and the PR's base, inside `release_on_signals`, so a SIGTERM still removes its temporary worktree. A FAIL is final: no flag lifts it, and the refusal keeps the line that no override lifts it. An unknown step that `lane_lint` can lift refuses and names `--lint-unknown-ok "REASON"`. The render passes that reason to `lane_lint`, which prints it on stderr, and prints the record. A timed-out or odd-exit lint is final, like a FAIL. On an open record the lint does not run, so the flag has no effect.
- A lane posts the body with the GitHub MCP comment tool after each round. `gh pr comment` uses GraphQL, which the cloud refuses (route graphql-gh-api-cloud).
- The one home of the form is the merge tool (`merge/merge.py`). `review_body` writes the body, `review_stamp` gives its Stamp line, `parse_review` reads it, and `review_state` gives each record's state. `reviewed_lines` prints the `--reviewed` list, `round_arg` reads `--round`, and `Host.review_comments` makes the one list read.

## The done rules

A change is done when one of these holds (rule `roles-review-cap-three`):

- round 1 or 2 is its last round, and that round is PASS (or, for Guard or check `no`, a fix check PASSes after its FAIL), and the last `design-reviewer` line (across all rounds) is PASS or absent;
- round 3 is done, and Guard or check is `no`;
- round 3 is done, Guard or check is `yes`, and Net value is zero or positive;
- Kind is `delete-only`, Guard or check is `no`, and round 1 is done;
- Kind is `docs-only`, with zero rounds, unless the change is a record that files an owner ruling. That change posts `Kind: normal` with one round (decision `docs-only-prs-skip-review`).

- A last `design-reviewer` line of FAIL or PARTIAL keeps a record open on the PASS rule. The round 3 and `delete-only` done rules stay done, and their reason names the design failure.
- A round 3 verdict does not decide done. When Guard or check is `yes`, Net value does, even after a round 3 PASS: `not owed` is open, and `negative` holds the change (record `hold-unsafe-after-round-3`).
- A `delete-only` change with Guard or check `yes` and a round 1 FAIL is open until round 3 is done, even after a fix check PASSes (item 402 a, owner, 2026-11-08 06:08 CST). The rule owes rounds 2 and 3 when round 1 finds a safety hole.
- `docs-only` with Guard or check `yes` is not a record: docs-only means no guard or check. The tool refuses it when it writes, and the parser rejects it.

## The cost

Counted as real `gh` calls, one call per page of a list read. Most reads fit one page of 100.

- `merge --reviewed` makes two list reads per run. One lists the open PRs. The other lists the repo's issue comments since the oldest open PR, so it pages every comment of the repo since then, not only review records. The cost grows with the repo's comment traffic and with the age of the oldest open PR.
- Not a `gh` call: each `--reviewed` run also runs one `git fetch origin main` (`load_config`) and local git reads.
- `merge --reviewed` and `--fix-check` find the cutover with one `git log` in the caller's repo top (`review_stamp_since`) and one `gh api repos` call for the default branch (`host_default_branch`). The `gh` call is once per root in a process (`default_branch_once`). With `--root`, a run makes two `gh api repos` reads when `origin/HEAD` is set, and three when it is missing. Tests pin both counts. `--fix-check` also fetches `origin/<default branch>` first (`fetch_default_branch`). A caller with no salt commit adds one `git log` in the merge tool's checkout (`tool_stamp_since`). Each `git log` is cached for the process, reads one file's history, and writes nothing.
- Each ready PR that has a record adds three reads: the check runs, the commit statuses and the branch protection (required checks mode `protection`). A draft, and a PR with no record, add none.
- One ready PR with a record: six calls, the two list reads, the `gh api repos` read and the three above. With a pinned `merge.requiredChecks` list: also six, because the one protection compare moves to the start of the run and the per-PR protection read goes.
- `merge <pr> --review-record`: one PR read per call. `--fix-check` adds one paged read of the repo's issue comments since the PR opened. It writes nothing. A render whose record is done also runs `lane_lint` once on the checked head sha: no PR read, one `git fetch origin <base>` (more when the head is not local), one temporary worktree and one `ci-job checks --lint` run, removed on exit. A render whose record is open runs none. The Stamp is one sha256 hash in the process that renders or parses, with no extra call, file or process.
- No new long-lived process, file or timer. Three caches live for the process: the default branch name (`_default_branch`), the cutover time (`_stamp_since`) and the tool checkout's cutover time (`_tool_stamp_since`). The batch runner calls the list at each wake. A lane calls the render at each round, and a render of a done record costs one lint run (above).
- The test `ReviewedList` in `merge/test_merge.py` pins the two list reads and the five host calls for one ready PR. The `gh api repos` read is not a host call, so it is the sixth.

## The guard

Rule `pr-review-record`, in `hooks/guard.py` (PreToolUse).

- The mistake: a lane typed the Head by hand on PR #1475 (15:10 CST, 2026-11-07). The record named a head that was not the live one, so the batch runner read it as stale.
- The second mistake: the records on PR #1502 and PR #1535 had prose after the CI line, so `parse_review` returned None and a lane fixed each by hand. The harm: `merge --reviewed` cannot read such a record, so the merge stalls. A body that opens with the marker must be the render output as it is. It may also be the render output, a line exactly `---`, then a footer, with no text between the CI line and `---`. One judge, `review_form_hit` in `hooks/guard_merge.py`, checks that form for a post and for an edit, and its refusal names that form.
- It judges a post, or an edit, of a comment whose body starts with the marker, as its first line (`parse_review` reads it so): `mcp__github__add_issue_comment`, `mcp__github__update_issue_comment` (an edit; its PR is the one the comment sits on, `comment_pull_request` in `hooks/guard_merge.py`), `gh pr comment` and `gh issue comment` (`--body`, `-b`, `--body-file`, `-F`) and `gh api repos/O/R/issues/<n>/comments` (`-f`, `-F`, `--field`, `--raw-field` with `body=` or `body=@file`). A heredoc body counts. A `$'...'` body is decoded first, as bash sends it (`ansi_c_decoded` in `hooks/guard_merge.py`, read only by this judge). A body of exactly `$(cat FILE)`, and a stdin body piped from `cat FILE`, are read from FILE. `--input` bodies are not read.
- It refuses unless the body parses (`parse_review`), its `PR:` equals the target PR, and its `Head:` equals the PR's live head. The refusal prints the render command for the live head, `merge <pr> --review-record --head <live sha> ...`.
- A malformed marked body is refused before any read.
- It fails open. Four reads can fail: the live head, the comment an MCP edit names, a body file, a body on stdin that no `cat FILE` supplies. Each one allows the call and prints one line on stderr that names the review record. An MCP edit with no integer comment id is allowed with a note. A network blip must not refuse every post.
- The cost: one PR read for a post that names a PR number. Two (the open-PR list, then the PR) for a post that names no number or names a branch. Two for a marked MCP edit (its comment, then its PR). None for any other comment or edit, which includes prose that names the marker below its first line. No file, no process, no log line. The tests pin these counts: a Bash PATCH makes 0 reads, `gh issue comment` 1, `gh issue comment --edit-last` 1, and a marked MCP edit 2.
- The gap: a shell edit in place (`gh api -X PATCH repos/O/R/issues/comments/<id>`) is judged for form only, by the same `review_form_hit`. Its input names a comment, not a PR, and it makes no read. The MCP edit tool (`mcp__github__update_issue_comment`) is judged for form and head, as a post is. This guard does not read five bodies and one head, on a post or on a PATCH:
  - the head on a shell edit, so a record edited in place can still carry a hand-typed head (debt `review-record-shell-edit-head-unread`);
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

Coordinator, 2026-11-08 12:51 CST, item 386 (the no-salt cutover): on any read with no salt, take the cutover from the tool checkout.

A record last edited before the stamp's merge commit reads as it did before: with no Stamp line, it still parses. A Stamp line that is there must match. A record last edited at or after that commit needs the stamp, so an unstamped one reads `bad`. The cutover dates a record by its last edit because GitHub keeps `created_at` through an edit. A body typed by hand after the cutover, into an older comment, would otherwise read as old. The cutover is `review_stamp_since`. It is the committer time of the first first-parent commit on `origin/<default branch>` whose `merge/merge.py` holds `REVIEW_STAMP_SALT =`. It is never the PR's base, because a stacked base may lack the stamp commit. A caller's repo with no such commit, whatever its history touched, takes the cutover from the merge tool's own checkout (`tool_stamp_since`). That checkout is found from `merge.__file__` and read with no fetch. So the cutover holds in every repo, not only claude-settings. The read cannot run on a git error, with no `origin/<default branch>` ref, or in a shallow clone whose first salt commit is the shallow boundary (an older one may exist). Then `review_stamp_since` raises Stop naming the read, so an unknown cutover never reads an unstamped record as old. A shallow file that exists but cannot be read stops too, and so does a folder with no `.git`. A subfolder reads the repo top's history. A tool checkout with no salt commit stops too, naming that checkout. The tool's checkout is read at HEAD, so it never lacks an `origin/<default branch>` ref. A Stop from the tool's read names the tool checkout's path. `merge/launch.py` runs the tool from a temporary worktree, which it removes when the run ends. So it passes its source checkout in `MERGE_TOOL_SOURCE` (`TOOL_SOURCE_ENV`), and each such Stop names that checkout too. Standing cost: the session tool clones at depth 50. In a shallow clone, every `--reviewed` and `--fix-check` run stops once the default branch is more than the clone's depth past the cutover. The remedy is `git fetch --unshallow origin`. `Host.review_comments` gives each body with its last edit time (`updated_at`, else `created_at`). `merge --reviewed` and the `--fix-check` earlier read pass that time and the cutover to `parse_review`. The report guard reads the cutover when it has a cwd: one `git log` per repo top, base and default branch per Stop, cached for the process. A failed cutover read never refuses by itself. Only an unstamped record, otherwise well formed and done for the live head, gets the UNKNOWN note and no refusal. Every other claim is refused as with a known cutover: no record, a mismatched Stamp line, a malformed field, or a record for another PR or head. It takes the default branch from the pull it already read (`base.repo.default_branch`) and passes it to `review_stamp_since` as `default=`, so it makes no `repos/{owner}/{repo}` read. Without a cutover, the report guard still requires the Stamp line, so its strictness stops a hand-typed record. A new post has no time, so the guard always needs the stamp. Open PRs keep their old records for `merge --reviewed` only. The report guard with no cutover refuses an old unstamped record, and its refusal names the Stamp line. Each record a lane renders after the cutover carries the stamp.

## Lane picks

The coordinator answered both at 23:14. Process-only.

- Q1. Should preview or confirm refuse a PR with no valid record? Pick a: no refusal now. Ruling 113 a names discovery only (rule `outcomes-grant-covers-named-act`). Not taken: confirm refuses an integration PR when a lane tip has no done record. Also not taken: preview prints a review line only.
- Q2. Which wins when a decision record and rule `roles-review-cap-three` disagree? Pick a: the rule outranks a decision record. Round 3 counts as done, whatever its verdict. Not taken: a final PASS is always needed. Record `standing-merge-grant` says so now.

Kind: process
Home: merge/merge.py

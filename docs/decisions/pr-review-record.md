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
- The read side refuses a hand-edited record. The merge tool never edits a record comment, so a comment whose `updated_at` differs from its `created_at` was edited by hand. A missing or null `updated_at` is no edit. `Host.review_read` gives each record as (body, time, edited), and `merge --reviewed` reads an edited record as `bad` and names it hand-edited.
- Ruling (lane review-record-provenance, 2026-11-08 17:38 CST, incidents PR #2294 and PR #2251): the newest record decides. If the newest record is hand-edited, the PR reads bad. An older unedited record does not count, because the edited text is unknown.
- Ruling (lane review-record-provenance, 2026-11-08 19:16 CST): any comment newer than the newest record that was edited makes the PR read bad, and the line names that comment. An edit can take the marker out of a record, and the tool cannot tell a stripped record from an edited comment. The remedy is a fresh record posted through the tool. An edited comment older than the newest record does not matter.
- Measured: a reaction does not move `updated_at` (18:56 CST, 2026-11-08, comment 6725052970). A reaction is no edit, so it never turns a PR bad. The one home of the read is `review_newest` in `merge/merge.py`. `merge --reviewed`, `--fix-check` and the report guard all call it.
- `--fix-check` follows the same two rules. It exits 2 and names the cause when the newest earlier record was edited, or when an edited comment sits above it. It does not fall back to an older record.
- The cutover still dates a record by its last edit (see "The cutover"). An edited record is refused before that date is read.
- `merge <pr> --review-record --head <40-hex sha>` prints the body for the head the review read. When the PR's live head is another sha, it stops with exit 1 and prints no body, so a push after the review never relabels old rounds as current.
- The lane-lint check. `merge <pr> --review-record` checks the lint before it prints a record whose state is `done` (`review_state`). A done record is what the lane gives the batch runner, and a lane gives it only a head that passes `merge --lane-lint` (decision `lanes-run-no-full-ci-job`). That includes a delete-only record after a round 1 FAIL, and a docs-only record with no round. An open record, such as a PASS that a design-reviewer FAIL leaves open, runs no lint and prints. Incident: PR #1502 was given to the batch runner with CiCoverage red.
- A record the lint refuses prints no body and exits nonzero. The refusal names `merge --lane-lint <pr>` as its remedy. `lane_lint` stays the one home of the lint. The render calls it with the checked head sha and the PR's base, inside `release_on_signals`, so a SIGTERM still removes its temporary worktree. A FAIL is final: no flag lifts it, and the refusal keeps the line that no override lifts it. An unknown step that `lane_lint` can lift refuses and names `--lint-unknown-ok "REASON"`. The render passes that reason to `lane_lint`, which prints it on stderr, and prints the record. A timed-out or odd-exit lint is final, like a FAIL. On an open record the lint does not run, so the flag has no effect.
- A lane posts the body with the GitHub MCP comment tool after each round. `gh pr comment` uses GraphQL, which the cloud refuses (route graphql-gh-api-cloud).
- The one home of the form is the merge tool (`merge/merge.py`). `review_body` writes the body, `review_stamp` gives its Stamp line, `parse_review` reads it, and `review_state` gives each record's state. `reviewed_lines` prints the `--reviewed` list, `round_arg` reads `--round`, and `Host.review_read` makes the one list read.

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

- The hand-edited check adds no read. It compares two fields of the comments the list read already holds.
- `merge --reviewed` makes two list reads per run. One lists the open PRs. The other lists the repo's issue comments since the oldest open PR, so it pages every comment of the repo since then, not only review records. The cost grows with the repo's comment traffic and with the age of the oldest open PR.
- Not a `gh` call on the usual path: each `--reviewed` run also runs one `git fetch origin <base>` (`load_config`) and local git reads. When the base's config is missing or has no `defaultBranch`, `load_config` also makes one `gh api repos` read (`host_default_branch`, not cached). Each `--reviewed` count below assumes a `defaultBranch` in the config, as this repo's has; without one, it goes up by one.
- `merge --reviewed` and `--fix-check` find the cutover with one `gh api repos` call for the default branch (`host_default_branch`) and one `git log` in the caller's repo top (`review_stamp_since`). The `gh` call is once per root in a process (`default_branch_once`). With `--root`, a run makes two `gh api repos` reads when `origin/HEAD` is set, and three when it is missing. Tests pin both counts. `--fix-check` also fetches `origin/<default branch>` first (`fetch_default_branch`). A caller with no salt commit adds one `git log` in the merge tool's checkout (`tool_stamp_since`). Each `git log` is cached for the process, reads one file's history, and writes nothing. A shallow clone may add deepen fetches; see "The cutover".
- Each ready PR that has a record adds three reads: the check runs, the commit statuses and the branch protection (required checks mode `protection`). A draft, and a PR with no record, add none.
- One ready PR with a record: six calls, the two list reads, the `gh api repos` read and the three above. With a pinned `merge.requiredChecks` list: also six, because the one protection compare moves to the start of the run and the per-PR protection read goes.
- `merge <pr> --review-record`: one PR read per call. `--fix-check` adds one paged read of the repo's issue comments since the PR opened. A full clone writes nothing here. A shallow clone may run the deepen and write objects and the `shallow` file ("The cutover"). A render whose record is done also runs `lane_lint` once on the checked head sha: no PR read, one `git fetch origin <base>` (more when the head is not local), one temporary worktree and one `ci-job checks --lint` run, removed on exit. A render whose record is open runs none. The Stamp is one sha256 hash in the process that renders or parses, with no extra call, file or process.
- No new long-lived process, file or timer. Three caches live for the process: the default branch name (`_default_branch`), the cutover time (`_stamp_since`) and the tool checkout's cutover time (`_tool_stamp_since`). The batch runner calls the list at each wake. A lane calls the render at each round, and a render of a done record costs one lint run (above).
- The test `ReviewedList` in `merge/test_merge.py` pins the two list reads and the five host calls for one ready PR. The `gh api repos` read is not a host call, so it is the sixth.

## The guard

Rule `pr-review-record`, in `hooks/guard.py` (PreToolUse).

- The mistake: a lane typed the Head by hand on PR #1475 (15:10 CST, 2026-11-07). The record named a head that was not the live one, so the batch runner read it as stale.
- The second mistake: the records on PR #1502 and PR #1535 had prose after the CI line, so `parse_review` returned None and a lane fixed each by hand. The harm: `merge --reviewed` cannot read such a record, so the merge stalls. A body that opens with the marker must be the render output as it is. It may also be the render output, a line exactly `---`, then a footer, with no text between the CI line and `---`. One judge, `review_record_hit` in `hooks/guard_merge.py`, checks that form for a post, and its refusal names that form.
- It judges a post, or an edit, of a comment whose body starts with the marker, as its first line (`parse_review` reads it so): `mcp__github__add_issue_comment`, `mcp__github__update_issue_comment` (an edit, see the edit bullet below), `gh pr comment` and `gh issue comment` (`--body`, `-b`, `--body-file`, `-F`) and `gh api repos/O/R/issues/<n>/comments` (a shell expansion for `<n>` or the repo, in any form the edit bullet below lists, is judged with no read: a marked body is refused, since its pull request cannot be checked. The refusal names the part to write out: the PR number, the repo, or the whole endpoint when it is an expansion) (`-f`, `-F`, `--field`, `--raw-field` with `body=` or `body=@file`). A marked `gh pr comment` or `gh issue comment` whose number or `-R` repo is an expansion is refused with no read too (`gh pr comment 12 -R "$REPO"`). A heredoc body counts. A `$'...'` body is decoded first, as bash sends it (`ansi_c_decoded` in `hooks/guard_merge.py`, read only by this judge). A body of exactly `$(cat FILE)`, and a stdin body piped from `cat FILE`, are read from FILE. `--input` bodies are not read.
- It refuses unless the body parses (`parse_review`), its `PR:` equals the target PR, and its `Head:` equals the PR's live head. The refusal prints the render command for the live head, `merge <pr> --review-record --head <live sha> ...`.
- A malformed marked body is refused before any read.
- An edit of a record comment is refused both ways; post a fresh record. The routes: `gh api` PATCH on `issues/comments/<id>` (`-X PATCH`, `-XPATCH`, `--method PATCH` or `--method=PATCH`), `gh pr comment --edit-last`, `gh issue comment --edit-last`, and the MCP update tool. The `gh api` route may be a full URL, may carry `?x=1` after the id, and may hold `$(...)` in the id or the repo. An unquoted one with a space splits into several words, so `_joined_substitutions` (`hooks/guard.py`) joins them before `_comment_route` (`hooks/guard.py`) reads the route. `review_post_hit` (`hooks/guard.py`) judges the Bash forms and calls `review_record_hit` with `edit`. The MCP update goes through `judge()` (`hooks/guard.py`) to `review_record_hit` with `edit`, not through `review_post_hit`.
  - Ruling (coordinator, 2026-11-08 09:42 CST): a marked new body is refused with 0 reads. Every other edit makes 1 read of the old body. A failed read refuses with "could not run".
  - An unmarked edit costs 1 gh read of the old body (lane review-record-provenance, 2026-11-08 21:31 CST).
  - A new body that carries the marker is refused before any read, stamped or not. The remedy is a fresh record from `merge <pr> --review-record`.
  - Every other edit makes one read of the comment's current body (`_old_body` in `hooks/guard_merge.py`), also when the new body cannot be seen: `--input FILE` or `--input=FILE`, `-F body=@-`, or stdin not piped from `cat FILE`. A record there refuses the edit. The refusal names a separate withdrawal comment and a fresh record.
  - A read that cannot run refuses the edit and says so (decision `guard-hooks-fail-closed`). So does a body file named on the edit that is missing or unreadable.
  - A comment id, issue number, repo or pull request selector held in a shell expansion cannot be read, so the guard makes no read. The forms: a variable (`$ID`, `${ID}`, `issues/$N`, `$PR`, or `$O` in a pull request URL), a command substitution (`$(..)` or backticks, also in double quotes, also as the repo), an arithmetic (`$((..))`) and a default expansion (`${X:-y}`). A variable repo counts too: `repos/$REPO/...`, `repos/${REPO}/...` and `-R "$REPO"`.
  - The splitter cuts a `$(..)` at `|`, `;`, `&&` or a newline. `review_segments` in `hooks/guard.py` joins those cuts back for a gh call. `_joined_substitutions` then joins a substitution the tokenizer split at its spaces. Both count open substitutions in `_open_substitutions`, so the inner call never stands for the route. `review_segments` counts with quotes, so a quoted parenthesis is text there. `_joined_substitutions` counts without them (`quotes=False`), so there a quoted parenthesis counts as open. That is a known gap, listed below in The gap. The patterns have one home, `_issue_route`. `shell_expanded` in `hooks/guard_merge.py` names an expansion.
  - An endpoint that starts with an expansion (`$URL`, `"$URL"`, `${URL}`, `$(gh api ...)`) is a variable target. It is an edit under PATCH only, in any spelling `_api_method` reads (PUT is not a comment edit), else a post.
  - A marked body is refused with no read. Any other body of such an edit is refused as a read that could not run.
  - The remedy names the part to write literally. `_LiteralIdNeeded` in `hooks/guard_merge.py` carries it. For a `gh api` route, `REVIEW_LITERAL_ID_REMEDY` says to write a literal `owner/repo` and comment id, or the `{owner}/{repo}` placeholder. For `gh pr comment --edit-last`, `REVIEW_LITERAL_PR_REMEDY` says to write a literal pull request number, and `REVIEW_LITERAL_REPO_REMEDY` says to write a literal `-R owner/repo`. Neither says to run the edit again, because a retry fails the same way. A read that fails on a literal route, such as a network failure, keeps the run-it-again remedy (`REVIEW_UNREAD_REMEDY`).
  - `gh pr comment -e` and `gh issue comment -e` are posts: gh's `-e` is `--editor`, and only `--edit-last` is an edit.
  - Incidents: a lane hand-edited records on #1926, #1531, #2016 and #1989. On #2063 a record was withdrawn at 09:44 CST, by an edit into a note.
  - Home of this refusal: the coordinator's step `record-comment-no-edit` (roadmap e5019fab8).
  - Closed: an edit that strips the marker, and an edit whose new body the guard cannot see, used to need a read of the old body. The old-body read above is that fix.
  - Open limit: `--edit-last` reads the newest comment of the PR, not the caller's own, since the caller's login is a second read. A newer comment by another user hides the record. Fix: `step:record-edit-last-by-login` reads the login once (`gh api user`) and picks the newest comment by it, for `--edit-last` only. Until: 2026-11-21.
- A post fails open. Three reads can fail: the live head, a body file, a body on stdin that no `cat FILE` supplies. Each one allows the call and prints one line on stderr that names the review record. A network blip must not block every post. The old-body read of an edit fails closed, and so does a body file of an edit that cannot be read. An allowed edit whose new body comes from unseen stdin prints the line. A refused edit prints none.
- The cost: one PR read for a post that names a PR number. Two (the open-PR list, then the PR) for a post that names no number or names a branch. None for a marked edit, which is refused unread. None for an edit whose body file cannot be read. None for an edit whose route is a shell expansion, which is refused before its read. One read for every other edit with a literal route, whatever the comment holds. It is one comment read for a PATCH or an MCP update. For `--edit-last` with a number, it is one list read of the PR's comments, 100 a page. A bare `--edit-last` with no number makes two: the open-PR list, then the listing. None for any other comment, which includes prose that names the marker below its first line. No file, no process, no log line. The tests pin these counts.
- The gap: this guard does not read or judge the forms below, on a post or on an edit. An edit whose new body is hidden by one of the first four forms is still judged on its old body (one read):
  - a body held in a shell variable (`--body "$BODY"`);
  - a body from `$(printf ...)` or `$(echo ...)`, since only a body of exactly `$(cat FILE)` is read;
  - a stdin body that is neither a heredoc nor piped from `cat FILE`;
  - a `gh api --input` body;
  - a post to a full-URL endpoint, `gh api https://api.github.com/repos/...` (an edit by full URL is judged, see the edit bullet).
  - a spaced route whose `$(..)` id holds a quoted parenthesis, such as `gh api repos/O/R/issues/$(echo '(' 12)/comments` (checked 2026-11-09): `_joined_substitutions` counts the quoted `(` as open, so the route is left unjudged. A malformed marked body passes on a post and on an edit.

  Judged now (checked 2026-11-09): an unquoted `$(...)` route with a `|`, `;` or `&&`, a backtick id, and a post route with `$(...)` in the number. A `$(...)` id that holds a `)` is also judged. A `$(..)` in the repo part of a route is judged both unspaced and spaced or quoted (`_ROUTE_REPO`, hooks/guard.py). Tests pin all but the `)` id. A probe refused `$(echo $(cat idfile))`, which no test pins.

  Origin main has no record judge (checked 2026-11-09). Step `record-guard-wrapper-forms` is the home of their fix.

## The limits

- Kind, Guard or check, and docs-only are the lane's own claims. The tool does not check paths. It does not tell a record that files an owner ruling from other docs. Kind stays the lane's claim. Guards stop mistakes, not attackers (record `guard-guards-mistakes-only`).
- Open: an integration PR has no record of its own.
- A `delete-only` change with Guard or check `no` and a round 1 FAIL reads done (rule `roles-review-cap-three`, the three-round review cap). The lane fixes the defect and posts a new review record for the new head, before the batch runner batches it. The fix push makes the old record stale.
- Unmeasured: whether the auto-mode classifier allows `merge --reviewed` and `merge <pr> --review-record`. Both are off `merge/cloud_allow.json`, which allows only `--confirm` and `--role`.
- One fix check per record. A second fix on a fixed head starts a new lane at round 1. `--fix-check` refuses unless its reviewed head equals the Head of the newest earlier record on the PR and that record has no Fix check line.

## The cutover

Coordinator, 2026-11-08 12:51 CST, from PR #1923 round 3 (the no-salt cutover; the fix rides in the lane under owner item 386, 2026-11-07 22:25 CST): on any read with no salt, take the cutover from the tool checkout.

A record last edited before the stamp's merge commit reads as it did before: with no Stamp line, it still parses. A Stamp line that is there must match. A record last edited at or after that commit needs the stamp, so an unstamped one reads `bad`.

The cutover dates a record by its last edit, because GitHub keeps `created_at` through an edit. A body typed by hand into an older comment would otherwise read as old.

The cutover is `review_stamp_since`. It is the committer time of the first first-parent commit on `origin/<default branch>` whose `merge/merge.py` holds `REVIEW_STAMP_SALT =`. It is never the PR's base, because a stacked base may lack the stamp commit. A caller's repo with no such commit, whatever its history touched, takes the cutover from the merge tool's own checkout (`tool_stamp_since`). That checkout is found from `merge.__file__` and read at HEAD, with no fetch. So the stamp rule holds in every repo, not only claude-settings.

The read cannot run on a git error, or with no `origin/<default branch>` ref. A shallow file that exists but cannot be read also stops, and so does a folder with no `.git` (lane review-record-provenance, 2026-11-08 17:52 CST). In each case `review_stamp_since` raises Stop naming the read, so an unknown cutover never reads an unstamped record as old. A subfolder reads the repo top's history (`repo_top`), for the log, the shallow read and the deepen.

A shallow clone whose first salt commit is the shallow boundary may hide an older one, so the read deepens first. It runs `git fetch --deepen=100` (`REVIEW_DEEPEN_STEP`) for that same default branch (the `default=` argument when the caller passes it, else `default_branch_once`) through `fetch_branch`, then reads again. It does this at most 3 times (`REVIEW_DEEPEN_TRIES`), 300 commits in all. It stops if the boundary still holds the salt after that, or if a deepen fetch fails or is cut at its own cap. A fetch that exits non-zero names the fetch and git's reason, and says to retry. A fetch cut at its own cap names the budget and the fetch's own limit. `git fetch --unshallow origin` is its fallback.

The tool checkout gets no deepen. Its read is `salt_cutover` at HEAD, so it never lacks an `origin/<default branch>` ref. A tool checkout whose first salt commit is its shallow boundary stops. A tool checkout with no salt commit stops too. Each such Stop names that checkout. `merge/launch.py` runs the tool from a temporary worktree, which it removes when the run ends. So it passes its source checkout in `MERGE_TOOL_SOURCE` (`TOOL_SOURCE_ENV`). When the tool runs from another folder, the Stop names the source checkout too.

Standing cost: the session tool clones at depth 50. The trigger is that the first salt commit found is the shallow boundary itself, so the cutover is older than the boundary or is the boundary. Any caller that reads the cutover can run the deepen: `--reviewed`, `--fix-check` or the report guard. Once a deepen leaves the boundary older than the salt commit, the clone's `shallow` file keeps that boundary on disk. Every later read, in any process, then finds the salt commit and fetches nothing. A cutover 300 or more commits past the boundary takes more than one read, since one read makes at most `REVIEW_DEEPEN_TRIES` deepens, and the first read stops. Cost: a full clone, or a shallow one whose boundary is not the salt commit, runs one `git log` and no fetch. A caller with no salt commit adds one `git log` in the tool checkout, and no fetch. The worst case with no race is 4 `git log` calls and 3 fetches. With races, each of those 4 log passes makes up to `REVIEW_RACE_TRIES` (3) tries, so up to 12 `git log` calls. `reviewed_roots` makes one read per root, so a multi-root `--reviewed` pays these counts per root. Each deepen is a git process. It makes a network call and writes objects and the clone's `shallow` file. It also force-updates `origin/<default branch>` through the refspec of `fetch_branch`. It adds no log. The read also takes the `shallow` file before and after each `git log`. If another process deepened the clone between the two, it runs the `git log` again, at most 3 tries (`REVIEW_RACE_TRIES`), then stops. Each re-read adds one `git log` and two file reads.

`Host.review_read` gives each record as (body, time, edited). The time is the last edit (`updated_at`, else `created_at`). `edited` is True when `updated_at` differs from `created_at`. `Host.review_comments` gives the same records without `why`. `merge --reviewed` and `--fix-check` pass the time and the cutover to `parse_review`.

The report guard's Stop hook reads the cutover only when it has a cwd and a PR claim. Each Stop makes one `git log` per repo top, base and default branch, cached for the process, plus the tool checkout's when the repo has no salt commit. It takes the default branch from the pull it already read (`base.repo.default_branch`) and passes it to `review_stamp_since` as `default=`. When the pull carries it, the guard makes no `repos/{owner}/{repo}` read (lane review-record-provenance, 2026-11-08 16:50 CST). It keeps the deepen (lane review-record-provenance, 2026-11-08 20:48 CST). In a shallow clone whose cutover is past the boundary, it reads as strongly as `merge --reviewed`: up to `REVIEW_DEEPEN_TRIES` fetches, which write objects and the `shallow` file. The hook has an 80 s timeout (`settings.json`), and a killed hook prints nothing, which is a silent allow. So every `gh` read of one Stop and its cutover read share one budget of 28 s (`REVIEW_HOOK_BUDGET` in `lint/report_guard.py`), below that timeout. A `gh` read gets what the budget has left, never more than `REVIEW_READ_TIMEOUT` (30 s). The cutover read runs in `shared_deadline` for what is left. Each deepen fetch gets the time left, never more than merge's 25 s per-call cap (`MERGE_READ_TIMEOUT`). When the budget runs out mid-deepen, `review_stamp_since` raises Stop naming the budget and starts no fetch after it. The deepen done so far stays on disk, so the next Stop continues from it. For an unstamped record, the rulings below refuse the claim with a "run again" cause. Either way, the hook adds the UNKNOWN cutover note. A test compares the budget with the timeout read from `settings.json`. The 28 s leaves a 52 s margin under the 80 s timeout for those reads, and the margin is unmeasured. The budget covers only the `gh` reads and the cutover read (`review_record_problem`). The model call of `past_ruling_problem` (up to 60 s, `PAST_RULING_TIMEOUT` in `hooks/call_judge.py`) runs after it and is outside it. 28 s plus 60 s is 88 s, past the 80 s timeout, so a slow call there can still pass the hook timeout. A budget for the whole hook is queued as step `report-guard-hook-budget`.

A cutover read that fails, or is cut at its own cap with time left, never refuses by itself (lane review-record-provenance, 2026-11-08 17:52 CST; the 2026-11-09 02:52 CST ruling below). The record check still runs. Only an unstamped record, otherwise well formed and done for the live head, gets the UNKNOWN note and no refusal. Every other claim is refused as with a known cutover: no record, a mismatched Stamp line, a malformed field, or a record for another PR or head. A failed read is unknown, not none, so it never adds the Stamp line wording to a refusal.

With no cwd, the guard has no cutover. It still requires the Stamp line, so its strictness stops a hand-typed record. It refuses an old unstamped record, and its refusal names the Stamp line. A new post has no time, so the guard always needs the stamp. Open PRs keep their old records for `merge --reviewed` only. Each record a lane renders after the cutover carries the stamp.

- Ruling, coordinator, 2026-11-09 02:18 CST, process pick. Process-only. When the review check's shared budget (`REVIEW_HOOK_BUDGET`) runs out before the PR's record is read, the PASS claim is refused with a "run again" cause. The same refusal applies when the budget runs out before or during the cutover read of a record whose verdict needs the cutover. Such a record is an unstamped one. The PASS claim is never allowed with only an UNKNOWN note. This keeps main's verdict: main refuses a claim when it reads no record.
- Ruling, lane review-record-provenance, 2026-11-09 02:27 CST, process pick. Process-only. A stamped record that matches and is done for the live head stays allowed when the budget runs out before or during the cutover read. The reason is that its verdict does not depend on the cutover. The code already does this.
- Ruling, lane review-record-provenance, 2026-11-09 02:52 CST, process pick. Process-only. The clock alone decides a budget run-out (`lint/report_guard.py` `_budget_spent`). A read that ends with the shared deadline spent is a run-out. A read that fails or is cut at its own time cap with time left is a failed read. So an unstamped done record gets the UNKNOWN note, not a refusal. This includes a deepen fetch cut at its own cap.

## Lane picks

The coordinator answered both at 23:14. Process-only.

- Q1. Should preview or confirm refuse a PR with no valid record? Pick a: no refusal now. Ruling 113 a names discovery only (rule `outcomes-grant-covers-named-act`). Not taken: confirm refuses an integration PR when a lane tip has no done record. Also not taken: preview prints a review line only.
- Q2. Which wins when a decision record and rule `roles-review-cap-three` disagree? Pick a: the rule outranks a decision record. Round 3 counts as done, whatever its verdict. Not taken: a final PASS is always needed. Record `standing-merge-grant` says so now.

Kind: process
Home: merge/merge.py

# A pull request carries its review log on the PR

## The ruling

Owner, 2026-11-01 04:26 CST, waiting-page item 113 a. Source: the brief. The waiting page is not in this repo.

- Each PR carries a review log.
- The batch runner finds reviewed, green PRs itself.
- No merge message.
- Owner, 2026-11-08 06:08 CST, item 396 a: a fourth review round for the builder-probe fix (step `builder-probe-false-alarm`).

Source: `waiting/items/builder-probe-round-4.json` on the roadmap branch. That grant covers only that change (rule `outcomes-grant-covers-named-act`). The coordinator's brief for step `record-granted-round` lets the record hold a granted round.

Owner, 2026-11-10 14:07 CST, typed in the retrospective session. The coordinator relayed it at 14:08 CST. Words: "i agree on letting it survive a clean merge where batch ci sees the problem rather than asecond review i agree it shd be mechanical tooo"

- A clean merge of main keeps a review log valid. The merge tool proves the merge mechanically.
- Batch CI catches what the merge breaks.
- A conflicted merge after a PASS fix verifier takes one more fix verifier (a fix after a merge of main).
- Any other difference keeps today's rules.

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
Grant: #<n>, item <n> <letter>, owner, <YYYY-MM-DD HH:MM CST|CDT>
Round <n>: <reviewer|design-reviewer>, <model>, <PASS|FAIL|PARTIAL>
Fix check: <40-hex reviewed head>, reviewer, <model>, <PASS|FAIL>
Net value: not owed|zero|positive|negative
CI: read live by merge --reviewed
```

- The first line is the marker. A line `---` after the CI line ends the record, so the attribution footer may follow.
- One `Round` line per reviewer. A round can hold more than one line.
- The `Fix check` line is optional, comes once after the Round lines, and is not a round (record `hold-unsafe-after-round-3`). `--fix-check HEAD:reviewer:MODEL:VERDICT` writes it. Its reviewed head must differ from Head. A FAIL is open. On every record, a Fix check whose model is not exactly `sonnet` (any letter case; `claude-sonnet-5-5` is not) is open, and `--fix-check` refuses it, whatever Guard or check says (owner item 444 a, 2026-11-08 15:04 CST; it widens item 351 a, 2026-11-07 14:44 CST). A fix check PASS counts as its round passing and owes no net value (owner item 741, 2026-11-13 13:29 CST). A fix check PASS after a failed round reads done, Guard or check `yes` or `no`. With no round recorded it reads open. `--fix-check` accepts HEAD only when it is the Head of the newest earlier record. That record must have no Fix check line or a PASS one. After a PASS one, a head that is a plain commit takes a further Fix check. A head that is a merge takes one only as a merge of main (below).
- The `Grant` line is optional and comes once, directly after `Guard or check`. It is the owner's grant of round 4 (rule `roles-review-cap-three`). `--grant TEXT` writes it, only with `--review-record`. Its text is `#<pr>, ` and a cite. The `#<pr>` must be the record's own PR, so a copied grant binds to no other PR. The cite is an item number, one lowercase letter for the pick, `owner`, and a CST or CDT time. `--grant` with another PR than the positional one is a usage error. With the line the rounds must reach round 4. Without it they stop at round 3. Never round 5.
- A done record counts only with a lane-lint PASS comment by the repo's owner at the live head. Without one `--reviewed` prints `no lint`, `lint fail` or `lint unknown` for the PR and names `merge --lane-lint <pr>` (record `lanes-run-no-full-ci-job`).
- The comment never stores CI state. The merge tool reads CI live. `merge --reviewed` shows a draft
  PR as `CI draft, no run`, because a draft has no CI run.
- A body is not a record when the marker is missing, a field is malformed or out of place, or round numbers skip. Nor is it one when a round is above 3 with no `Grant` line, above 4 with one, or short of 4 with one.
- The newest record for a head counts. A record for an old head is stale, unless clean merges of main keep it (The review a changed head owes).
- `merge <pr> --review-record --head <40-hex sha>` prints the body for the head the review read. When the PR's live head is another sha, it stops with exit 1 and prints no body, so a push after the review never relabels old rounds as current. A clean merge of main is the push that keeps them.
- `--review-record` refuses a record that restarts the review. It reads only earlier records of the same PR. The refusal holds when the new top round is lower than the earlier top round. It also holds when the two are equal, the top is below 3, and the new record has no `--fix-check`. An equal top at 3 or above is allowed. A head that moved after round 3 owes a fresh full review, which posts the rounds again with no Fix check line. A granted round 4 is allowed too. A refusal exits 2 with no body. A new branch with a new PR is the only way out.
- A lane posts the body with the GitHub MCP comment tool after each round. `gh pr comment` uses GraphQL, which the cloud refuses (route graphql-gh-api-cloud).
- The one home of the form is the merge tool (`merge/merge.py`). `review_body` writes the body, `parse_review` reads it, and `review_state` gives each record's state. `reviewed_lines` prints the `--reviewed` list, `round_arg` reads `--round`, and `Host.review_comments` makes the one list read.

## The done rules

A change is done at the first round, or the first fix check, that passes (rule `roles-review-cap-three`; owner item 741, 2026-11-13 13:29 CST; owner, 14:01 CST: "just stopping round 3 if earlier rounds already solved a problem"). Guard or check `yes` or `no` makes no difference after a passed round, and no net value is owed after a pass. A fix check PASS after a failed round reads done, Guard or check `yes` or `no`. Round 3 runs only after a round 2 FAIL with no fix check, as the builder's third try. A change is done when one of these holds:

- its last round is PASS, or a fix check PASSes after that round, and the last `design-reviewer` line (across all rounds) is PASS or absent;
- a fix check PASSes after a failed round, and the last `design-reviewer` line is PASS or absent;
- round 3 is done after a round 2 FAIL, and Guard or check is `no`;
- round 3 is done after a round 2 FAIL, Guard or check is `yes`, and Net value is zero or positive;
- Kind is `delete-only`, Guard or check is `no`, and round 1 is done;
- Kind is `docs-only`, with zero rounds, unless the change is a record that files an owner ruling. That change posts `Kind: normal` with one round (decision `docs-only-prs-skip-review`).

- Net value `negative` holds the change, whatever the rounds say.
- A last `design-reviewer` line of FAIL or PARTIAL keeps a record open on the PASS rule. The failed-round 3 and `delete-only` done rules stay done, and their reason names the design failure.
- With a `Grant` line, round 4 is the final round. The round 3 rules above run on it unchanged, and their reason names round 4. A round 4 PASS is done on the PASS rule.
- A failed round 3 does not decide done. When Guard or check is `yes`, Net value does: `not owed` is open, and `negative` holds the change (record `hold-unsafe-after-round-3`). A round 3 PASS, or a fix check PASS after a failed round 3, is done whatever Net value says but `negative`.
- A `delete-only` change with Guard or check `yes` and a round 1 FAIL is open after round 1 until round 2 passes. A round 2 PASS or a fix check PASS ends it (item 402 a, owner, 2026-11-08 06:08 CST, as the owner's 2026-11-13 18:35 CST ruling changed it). Round 1 finding a safety hole owes round 2, and round 3 when round 2 fails and no fix check passes.
- `docs-only` with Guard or check `yes` is not a record: docs-only means no guard or check. The tool refuses it when it writes, and the parser rejects it.

The review a changed head owes. The first three bullets are the owner's ruling of 2026-11-10 14:07 CST, above. The other bullets are a coordinator pick (owner session coordinator, 2026-11-08 to 2026-11-09). Process-only, not the owner's words. A lane reads them instead of asking.

- Owner's ruling. A clean merge of main keeps the record. A record stays valid for a live head that differs from its reviewed head only by clean merges of main (no conflict, the lane's own diff unchanged). Every commit after the record's Head, up to the live head, is a merge commit with two parents. Its second parent is on origin/main. Its tree equals `git merge-tree --write-tree` run on its two parents. The merge tool proves this. The record then reads as it did for its reviewed head. No fix check and no fresh review are owed. Batch CI catches what the merge breaks. `merge --reviewed` and the report guard run the check through one function (`live_review_state`). A read or a merge-tree that cannot run keeps the record stale, and the `--reviewed` line says the check is unknown and why. A parent that the checkout lacks is unknown, never a conflict and never clean. The tool fetches origin's branch heads once a run, only when a parent is missing.
- Owner's ruling. A conflicted merge of main after a PASS fix verifier takes one more fix verifier (a fix after a merge of main). Its prior record must be a PASS that `review_state` accepts. Its reviewed head is that record's Head.
- Owner's ruling. Any other difference keeps today's rules, below.
- Coordinator pick. A fix after a merge of main gets one fix verifier.
- Coordinator pick. The PR gets one fresh full review at the live head when any of these holds. A clean merge of main adds none.
  - the newest record holds a fix verifier, unless its fix verifier PASSed and the live head is one of two things:
    - a plain commit, which takes a further fix check;
    - a conflicted merge of main into the fixed head (the fix after a merge of main above);
  - a fix check failed;
  - a round read an older head than the live one;
  - the record was made or edited by hand;
  - the head moved after round 3.
- The fresh review has these parts:
  - its brief line 1 is `Round 3 of 3`;
  - it runs on Sonnet;
  - it reads the whole diff against main;
  - it runs the net-value test (record `hold-unsafe-after-round-3`, hold a change with negative net value after round 3).
- Round 2 runs first when it is missing. Post it with the lines the merge tool prints: the real round 1 and round 2 lines, the new round 3 line, and no `Fix check` line.
- Free text goes only below `---`. A record is never edited or deleted.
- A round 3 FAIL with net value at or above zero merges (round 3 done rule above).
- A lane merges origin/main once, after the pending batch lands (until the cutover; after it, no batch is pending). It uses an ordinary merge commit. It never replays, rebases or force-pushes.
- A merge with both test and product conflicts waits for the mixed-merge route, which is on main (decision `builders-cannot-edit-tests`, Builders cannot edit tests, its merge route; owner, 2026-11-08 10:05 CST, waiting-page item 420 pick a; cases in `hooks/test_guard.py`).

## The cost

Counted as real `gh` calls, one call per page of a list read. Most reads fit one page of 100.

- `merge --reviewed` makes two list reads per run. One lists the open PRs. The other lists the repo's issue comments since the oldest open PR, so it pages every comment of the repo since then, not only review logs. The cost grows with the repo's comment traffic and with the age of the oldest open PR.
- Not a `gh` call: each `--reviewed` run also runs one `git fetch origin main` (`load_config`) and local git reads.
- The lane-lint comment (record `lanes-run-no-full-ci-job`) rides the same list read, so `--reviewed` makes no extra call for it. The batch runner's join adds one paged read of that list. `merge --lane-lint <pr>` adds one POST on a PASS, and, for a lane PR (never a batch integration PR), one read of the head's check runs, which judges the draft's Windows and macOS runs (`merge --batch-build` adds the same one read per lane, on a new build and on `--ready`).
- Each ready PR that has a record adds four reads when no ruleset names a check: the check runs, the commit statuses, main's ruleset (`rules/branches/main`, one read when no ruleset applies) and the branch protection (required checks mode `protection`). When main's ruleset names a check, the branch protection read goes, so three. A draft, and a PR with no record, add none.
- One ready PR with a record: six calls while no ruleset names a check (the pull list, the comments, the check runs, the commit statuses, main's ruleset, the branch protection). Five once main's ruleset names the check. With a pinned `merge.requiredChecks` list: the same count, because the one protection compare moves to the start of the run and the per-PR protection read goes. No test pins the pinned count.
- `merge <pr> --review-record`: one PR read, one read of the PR's earlier review logs (restart refusal needs them on every record), plus one read per page of 100 changed files. Three reads for a PR of 100 files or fewer. The earlier-records read is one paged read of the repo's issue comments since the PR opened, so the three reads hold while those comments fit one page. The tests `ReviewGuardCost` and `ReviewGuardHostFiles` pin them. `--fix-check` adds no read of its own: it reuses the earlier-records read. When the newest earlier record holds a PASS Fix check line, it also reads the `--head` commit, and makes one compare when that commit has two parents. When the first parent is not the reviewed head, it also walks the commits between them (`clean_merges_after`, costed below). For a merge after the fixed head, it adds one `merge_state` (four `git rev-parse` starts and one `git merge-tree --write-tree` start, which writes the merged tree's objects to the object store). A conflicted merge adds a second merge-tree (two more `git rev-parse` starts and one `git merge-tree` start) and one `git diff-tree` start. For Kind `docs-only` it also makes one local layout read, no new `gh` call. It writes no comment or file of its own. <!-- glossary-ok: the review log row of GLOSSARY.md keeps the flag --review-record -->

- The clean-merge survival check runs at each `merge --reviewed` run and each lane Stop that claims a PASS, for each PR whose newest record is stale. Per commit walked: one commit read. Per merge commit: one compare, four `git rev-parse` starts (`merge_state` and `merge_tree` each check both parents) and one `git merge-tree --write-tree` start, which writes the merged tree's objects to the object store. At most one `git fetch origin` of the branch heads a run, only when a parent is missing. Count per run unmeasured.
- No new long-lived process, file, cache or timer. The batch runner calls the list at each wake. A lane calls the render at each round.
- The test `ReviewedList` in `merge/test_merge.py` pins the two list reads and the six calls for one ready PR.

## The guard

Rule `pr-review-record`, in `hooks/guard.py` (PreToolUse).

- The mistake: a lane typed the Head by hand on PR #1475 (export scan false alarms) at 15:10 CST, 2026-11-07. The review log named a head that was not the live one, so the batch runner read it as stale.
- The second mistake: the review logs on PR #1502 (report guard names CI state after a push) and PR #1535 (guard asks before a lane PR goes ready) had prose after the CI line, so `parse_review` returned None and a lane fixed each by hand. The harm: `merge --reviewed` cannot read such a review log, so the merge stalls.
- A body that opens with the marker must be the render output as it is. Or it is the render output, a line exactly `---`, then a footer, with no text between the CI line and `---`.
- The post judge, `review_log_hit` in `hooks/guard_merge.py`, checks that form. Then it checks the review log's `PR:` against the target and its `Head:` against the live head. An MCP edit reaches it too, with the PR its comment sits on. The shell edit judge, `review_form_hit` in the same file, checks that form alone, with no read. Both judges' form refusals name that form.
- It judges a post, or an edit, of a comment whose body starts with the marker, as its first line (`parse_review` reads it so): `mcp__github__add_issue_comment`, `mcp__github__update_issue_comment` (an edit; its PR is the one the comment sits on), `gh pr comment` and `gh issue comment` (`--body`, `-b`, `--body-file`, `-F`) and `gh api repos/O/R/issues/<n>/comments` (`-f`, `-F`, `--field`, `--raw-field` with `body=` or `body=@file`). A heredoc body counts. A `$'...'` body is decoded first, as bash sends it (`ansi_c_decoded` in `hooks/guard_merge.py`, read only by this judge). A body of exactly `$(cat FILE)`, and a stdin body piped from `cat FILE`, are read from FILE. `--input` bodies are not read.
- It refuses unless the body parses (`parse_review`), its `PR:` equals the target PR, and its `Head:` equals the PR's live head. The refusal prints the render command for the live head, `merge <pr> --review-record --head <live sha> ...`. <!-- glossary-ok: the review log row of GLOSSARY.md keeps the flag --review-record -->
- A malformed marked body is refused before any read.
- It fails open. A network blip must not block every post. Each case below allows the call and prints one line on stderr, `review log: not checked, <why>`:
  - the merge tool cannot be loaded;
  - the live head cannot be read, for example a branch with no single open pull request, or a comment an MCP edit names when its read fails;
  - a body file cannot be read;
  - a body on stdin that no `cat FILE` supplies;
  - an MCP post names no pull request number;
  - an MCP edit names no integer comment id.
- The cost: one PR read for a post that names a PR number. Two (the open-PR list, then the PR) for a post that names no number or names a branch. Two for a marked edit (its comment, then its PR). None for any other comment or edit, which includes prose that names the marker below its first line. No file, no process, no log line. The tests pin each count.
- A shell edit by comment id (`gh api -X PATCH repos/O/R/issues/comments/<id>`) is judged for form only, by `review_form_hit`: its route names a comment, not a PR, and it makes no read. The guard does not read these, on a post or on a PATCH:
  - the head on a shell edit, so a review log edited in place by PATCH can still carry a hand-typed head;
  - a body held in a shell variable (`--body "$BODY"`);
  - a body from `$(printf ...)` or `$(echo ...)`, since only a body of exactly `$(cat FILE)` is read;
  - a stdin body that is neither a heredoc nor piped from `cat FILE`;
  - a `gh api --input` body;
  - a body sent to a full-URL endpoint, `gh api https://api.github.com/repos/...`.

## The limits

- The lane-lint comment counts only from an `OWNER` author (`LANE_LINT_AUTHOR`). A cloud-session post on shivinate7/claude-settings reads back OWNER (measured pull request 2382, comment 6732994630, 2026-11-09 05:28 UTC). An org-owned repo or a non-OWNER token stays unmeasured, and refuses every join, leaving a done record at `no lint` (fail-closed). A PASS for an earlier head counts after claim-only commits, in the join only; `--reviewed` is exact-head (record `lanes-run-no-full-ci-job`; read merge/merge.py::lint_check).
- `--review-record` reads the PR's changed files. A moved file counts at its old path too.
  - It refuses Guard or check `no` when a path starts with an entry of `GUARD_PATHS` or equals one of `GUARD_FILES`. `GUARD_PATHS` is `stale_cites.RULE_DIRS` plus `merge/` and `githooks/`. `GUARD_FILES` is `settings.json`. The model record `agent-model-cap.md` in the decisions folder is a guard path too, built by `guard_hits` from the layout's decisions folder, because its round rows set the review models. A test path (`hooks/guard.py` `is_test_rel`) never counts, because test files alone never count (record `hold-unsafe-after-round-3`). `.github/pull_request_template.md` is a guard path, as is the whole of `.github/` (`stale_cites.RULE_DIRS`), though it holds text: it seeds the PR bodies whose `Retire-run:` and `Drops-lines:` lines `lint/check_silent_undo.py` and `lint/check_debt_retire.py` read, and `lint/test_check_debt_retire.py` (`TemplateExcuses`) reads the file in CI. A live excuse line in it would excuse a debt delete without a check. A review that reads only `.github/workflows/` as the guard part of `.github/` is wrong (lane pr-template-stays-guard, tests in `merge/test_merge.py`).
  - It refuses a files list shorter than the PR's changed-file count, and a PR read that gives no count. GitHub lists at most 3000 files.
  - `agents/*.md` is not on the list. Only its `tools` lines are a guard, and a path cannot tell those apart from prompt text.
  - It refuses Kind `docs-only` when any path, an old path included, is not a doc. A doc is a `.md` file under `docs/`, or the root `README.md`. Case is ignored. The path is not stripped, so a stray space makes it a non-doc. Any other file may steer behaviour, such as a skill, an agent file, a hook prompt, a `.claude/rules` file or a nested README. The check treats it as a rule under decision `docs-only-prs-skip-review` (a docs-only change touches no rule, guard, check or product code), and fails closed. Such a PR takes Kind `normal` with one round 1 review. It refuses Kind `delete-only` when a path adds lines, or is added, renamed or copied. A file that only loses lines passes, because delete-only "only deletes and adds nothing" (record `hold-unsafe-after-round-3`).
  - Guard or check `yes` stays allowed with no hit, because a guard can live outside those paths.
- The path and Kind checks run only when `--review-record` prints a record. `merge --reviewed` still trusts a record posted by hand. A read there would add one call per PR.
- In another repo, a change under `hooks/`, `lint/`, `bin/`, `actions/`, `.github/`, `merge/` or `githooks/`, or to a root `settings.json`, must say Guard or check `yes`. It then owes the net-value test only after a failed round 3. A `.claude/settings.json` or `.claude/hooks/` path is not on the list.
- It refuses Kind `docs-only` when a path is an added, modified, renamed or copied `.md` under the decisions folder (`layout.path`), that is, a decision record. A decision record removed or renamed out of the folder is not counted. The folder is read once from the checkout's layout, and an unreadable layout stops the review log. Kind, Guard or check, and docs-only are the lane's own claims. The path check above tests only the cases it lists. The tool does not tell a record that files an owner ruling from other docs. Kind `normal` stays the lane's claim. Guards stop mistakes, not attackers (record `guard-guards-mistakes-only`). The check fixes a gap rather than filing it as a note, by the coordinator's order of 2026-11-07 13:20 CST, decision `pr-ledger` (every open PR has one next act).
- Open: until the cutover (decision `all-repos-switch-together`), an integration PR has no record of its own. After it, each lane PR carries its own record and no integration PR exists.
- A `delete-only` change with Guard or check `no` and a round 1 FAIL reads done (rule `roles-review-cap-three`). The lane fixes the defect and posts a new review log for the new head, before the batch runner batches it. The fix push makes the old record stale.
- Unmeasured: whether the auto-mode classifier allows `merge --reviewed` and `merge <pr> --review-record`. Both are off `merge/cloud_allow.json`, which allows only `--confirm` and `--role`.
- One fix verifier per record. A fix after a FAIL fix verifier gets the fresh full review in The review a changed head owes, not a fix verifier. After a PASS fix verifier, a further fix verifier over a new head is accepted (owner item 741). A clean merge of main takes none. `--fix-check` checks in this order:
  - HEAD must be the Head of the newest earlier record on the PR. Otherwise it refuses (exit 2).
  - If that record has no Fix check line, it accepts the fix check.
  - If that record has a PASS Fix check line and the `--head` commit is not a merge, it accepts the fix check.
  - If that record has a PASS Fix check line and the `--head` commit is a merge, that record must read done under `review_state` on its own Head. The `--head` commit must have exactly two parents. Its first parent must be HEAD. Its second parent must be on the PR's base branch: the base branch contains it, so GitHub's compare reads ahead or identical. Its tree must not be a clean `git merge-tree --write-tree` of the two parents plus an edit. Otherwise it refuses (exit 2).
  - A conflicted merge passes the tree rule (`git merge-tree` exits 1) when it edits only its conflicted paths: a path git merged without conflict must hold git's own result, and any other edit refuses (exit 2). A clean merge passes when its tree is git's own. A clean merge needs no fix verifier, but the tool keeps what it did before and does not refuse one. A stacked base merge also keeps its earlier route. A merge that git cannot read, such as one whose parent the checkout lacks, refuses (exit 2), and the refusal says the merge is unknown.
  - A FAIL fix verifier line on that record refuses (exit 2).
- The clean-merge survival in The review a changed head owes has one home, `live_review_state` in `merge/merge.py`. `merge --reviewed` and the report guard (`lint/report_guard.py`) both call it, so they agree. It walks first parents from the live head, at most 50 commits, back to the record's Head (`clean_merges_after`). Each commit is a clean merge of main (two parents, a second parent that main holds, and git's own clean merge tree). A commit with one parent, an empty commit too, ends the walk as stale. The report guard's whole review check ends within 70 seconds (`lint/report_guard.py: REVIEW_CHECK_BUDGET = 70`), these reads included. Each `gh` read of its own also ends within 30 seconds (`lint/report_guard.py: REVIEW_READ_TIMEOUT = 30`). When the check cannot run, the record stays stale and the guard still blocks, with a note that says so. `main` there is the repo's default branch, never the pull request's own base: a merge of a stacked pull request's base is no merge of main (triage pick, 2026-11-11 09:35 CST).

## Lane picks

The coordinator answered both at 23:14. Process-only.

- Q1. Should preview or confirm refuse a PR with no valid record? Pick a: no refusal now. Ruling 113 a names discovery only (rule `outcomes-grant-covers-named-act`). Not taken: confirm refuses an integration PR when a lane tip has no done record. Also not taken: preview prints a review line only.
- Q2. Which wins when a decision record and rule `roles-review-cap-three` disagree? Pick a: the rule outranks a decision record. Round 3 counts as done, whatever its verdict. Not taken: a final PASS is always needed. Record `standing-merge-grant` says so now.

Kind: process
Home: merge/merge.py

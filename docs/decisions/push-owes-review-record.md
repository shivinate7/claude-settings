# A push past an unrecorded reviewed head asks

## The ruling

Coordinator brief, 2026-11-08 09:45 CST. Fix checks count, coordinator 09:54 CST. Process-only.

- A reviewer's stop (a round or a fix check) writes an entry for the head it read: `state/owed-review-records/<sha>.json`. The entry holds the remote-tracking branches that contain that head, so a stop after the lane pushed past the head still writes one, and the time it was written. A head that origin's default branch already holds (`merge-base --is-ancestor` with its remote-tracking ref) gets no entry: no pull request can record it. The stop never blocks.
- A non-dry-run `git push`, and the MCP `update_pull_request_branch` (GitHub's one-click base merge, the same act), asks when all of these hold:
  - the destination is a branch the entry names (for the MCP call, the pull request's head branch);
  - that branch's remote-tracking ref is the entry's head H or a descendant of H;
  - the pushed source is not that ref (the MCP call's new commit always counts as new);
  - the open pull request whose head branch is the destination has no posted review record with Head H, among those that merge's `parse_review` accepts. Any record counts, not the newest: a later round's record names a later head and never un-records H.
- Per destination, only the newest matching entry (by its written time) governs; on a tie, each tied entry does. An older entry's remedy cannot run: `merge --review-record` needs the live head.
- A state read or a gh read that fails asks too, with the note `owed-record-unread`. So does an entry that is this repo's (its head is a commit here) when the push's directory or destination cannot be read, or when `.github/stamp.json` exists and is not a JSON object. A missing `stamp.json` skips the check.
- A bare push under `push.default=matching` reads as the current branch.
- The ask names the rule and the remedy: render the record with `merge <pr> --review-record --head <H>`, post it, then push. It names no branch (rule `git-remedy-never-names-target`, a refusal names no target).
- The owner's typed override lifts the ask.
- Why: a push past an unrecorded head leaves the record unable to name that head. Fact: `merge <pr> --review-record --head <H>` stops with exit 1 when the live head is another sha (decision `pr-review-record`, the review record form).

## The incidents

- PR #1869: a base merge of main was pushed after the reviewer stopped, with no record posted (case R1).
- PR #1914, lane `notes-fix-large-3`, 05:06 CST: a fix was pushed before the FAIL round's record was posted (case R2).
- PR #1958, its review rounds: a fix was pushed before the failed round's record was posted, so the tool could not record the old head (case R2).
- PR #1985, lane `notes-fix-other-2`, and PR #1699, lane `sim-lease-gaps`: the same mistake, a fix pushed before the FAIL record.
- PR #2015 and PR #2025, lane `bg-tail-loses-verdict`: round 3 was not recorded at its head before fixes landed. `merge --review-record --fix-check` refused.
- PR #2026 and PR #2068, lane `notes-fix-report`, 09:40 CST: a fresh chain of three rounds followed. PR #2026 is also a fix pushed after a FAIL with no record (case R2).
- PR #2042, lane `env-file-shell-c`: fix commit 94775a094 was pushed after round 3 reviewed commit 7517223bb, before round 3's record. `merge --fix-check` refused until the record was posted by hand (11:08 CST Nov 8).
- PR #2088: a fix-check reviewer stopped at fix head F with no record, then another fix was pushed (case R7).
- Lane `builder-report-in-head`, 06:58 CST: the lane pushed after review passed and before the record was posted. `merge --review-record` records only the live head, so the record could not be written (case R3).

## The harm

- The record cannot name the reviewed head. `merge <pr> --review-record` refuses a head that is not live. `--fix-check` refuses unless its reviewed head equals the Head of the newest earlier record. The result is a fresh chain of rounds (PR #2026, PR #2068).
- The batch runner may get a record it cannot parse, or a lane may fake the head (PR #2015, PR #2025).

## The cases

The cases are in `hooks/test_guard.py`, section 5f-3 (family `push-owes-review-record`).

| Case | State shows | Outcome |
|---|---|---|
| R1, base merge of main | Reviewer stopped at H. The lane pushes a merge of origin/main on top of H. No record | ask |
| R2, fix after FAIL | Reviewer stopped at H with FAIL. A fix is pushed. No record | ask |
| R3, report commit after PASS | Reviewer stopped at H with PASS. A commit adding the review report is pushed. No record | ask |
| R4, lease push of a fix | As R2, pushed with `--force-with-lease` naming H | ask |
| R5, record for an older head | A record for H0 is posted. The lane moves to H1, round 2 stops there, and a fix is pushed | ask |
| R6, comments read fails | Reviewer stopped at H. A fix is pushed. The issue comments read fails | ask, `owed-record-unread` |
| R7, fix-check stop at F | A fix is pushed to F. The fix-check reviewer stops at F with no record. Another fix is pushed | ask |
| R8, torn entry | The entry for the lane head H cannot be parsed. A fix is pushed | ask, `owed-record-unread` |
| C1, no entry | No stop ran. A fix is pushed | allow, no gh call |
| C2, PASS record on page 2 | A PASS record at H is the newest of 35 comments | allow |
| C3, FAIL record | A FAIL record at H is posted | allow |
| C4, no open PR at H | The only open PR has another head | allow |
| C5, archive branch | Push to `archive/<lane>` | allow |
| C6, reviewed head itself | The push sends H itself | allow |
| C7, builder stop | A builder stop writes no entry. A fix is pushed | allow |
| C8, no merge config | The repo has no merge config | allow |
| C9, owner override | The owner's typed override is set | allow |
| C10, dry run | `git push --dry-run` | allow |
| C11, full folder | 40 entries for other heads, none for H | allow, no gh call |
| R7c, fix-check record posted | A record with Head F and a Fix check line is posted before the push | allow |
| F1a, stop after a push past H | The lane pushed past H, the reviewer then stopped at H in a detached tree, no record. The lane pushes again | ask |
| F1b, a later round's record | A record at H, then a newer record at R. The lane pushes past R | allow |
| F1c, PR head moved past H | The reviewer stopped at H. The lane pushed R past H, so the PR head is R. No record | ask |
| F2, unreadable destination | An entry exists, and the push's destination cannot be read | ask, `owed-record-unread` |
| F3, malformed stamp file | An entry exists, and `.github/stamp.json` is not valid JSON | ask |
| F4, bare push, `push.default=matching` | An entry for the current branch, no record | ask |
| F6, MCP base merge | `update_pull_request_branch` on the PR of a branch with an unrecorded entry | ask |
| F6c, MCP base merge, recorded | The same call with the record at H posted | allow |
| G1, reviewed head on main | The lane's first commit H is merged to origin's default branch. The reviewer stops at H. A fix is pushed | allow, no entry written |
| G2, older entry unrecorded | An entry at H0 with no record. The reviewer stops again at H1 on the same branch, and a record at H1 is posted. A fix is pushed | allow |
| G2c, newest entry unrecorded | As G2, with no record at H1 | ask |

## The misses

Found in the code:

- A torn entry, an unreadable destination, directory or config asks only when an entry's head is a commit in the push's repo. Otherwise it passes.
- A push that names no refspec range (`--all`, `--mirror`, a deletion, tags only) is not read.
- Pruning runs at each reviewer stop that finds a remote branch holding its head. It removes any entry file older than 14 days by mtime, whether its PR is open or not. A push past that head then passes.
- A reviewer stop on a head that no remote branch contains writes no entry. A later push past that head passes.
- A reviewer that never checks out the head writes no useful entry. The stop reads HEAD in its own directory.
- A stop whose git read fails writes no entry and logs `owed-record-unwritten`. A later push passes.
- Only the lowest-numbered open PR whose head branch is the destination is read. A second open PR on that branch, or a fork's branch of the same name, is not told apart.
- Only open PRs are read. A closed or merged PR on the branch does not ask.
- Only the shell `git push` and `update_pull_request_branch` are checked. The MCP tools `push_files` and `create_or_update_file` are not seen.
- An entry stays live at least 14 days, so each push to its branch in that time reads gh again (one open-PR list and one comments read, even after the record is posted).
- A design-reviewer or a workflow agent writes no entry. The stop reads only agent type `reviewer`.
- A head on origin's default branch writes no entry, so a push past it passes. An unreadable default-branch or ancestor read writes the entry, and so does a stale tracking ref that does not yet hold the head.
- An older entry with no record passes once a newer entry on the same branch is recorded. Its head stays unrecorded.
- A push to a non-origin remote or a URL never matches an origin entry (a note).
- A bare push under `push.default=matching` checks only the current branch (a note).
- Unknown whether the SubagentStop runs before the reviewer's worktree is removed. If after, no entry is written (a note).
- Two reviewers that stop at one sha at once share one temp file name (a note).

## The cost

- A push with no entry file: one listdir of `state/owed-review-records`. No git call, no gh call.
- A push with entry files in a repo with a merge config: one merge-config read, one file read per entry, and the git reads of `push_destinations` (only for a bare or HEAD push). An entry for another branch costs its file read only. An entry for the push's branch costs one rev-parse of the tracking ref, and a second when that ref equals H. A torn entry costs one rev-parse.
- A matching entry: the open PR list (one REST request per page, once per push), then the matched PR's issue comments (one REST request per page, once per PR per push). A tracking ref that is not H adds one `merge-base --is-ancestor` spawn.
- An `update_pull_request_branch` call with entries present: one REST read of the pull request, then the same.
- A reviewer stop: two git spawns (`rev-parse HEAD`, `branch -r --contains HEAD`). When a remote branch holds the head, also the default-branch read (one `symbolic-ref`, one or more `rev-parse`) and one `merge-base --is-ancestor`. Then one listdir, and one small file written (temp file, then replace).
- No long-lived process, no timer.
- Not proved by a test: the git spawn counts. C1 and C11 prove the no-gh-call part.

Dated by: the head compare in `_records_hold`, the descent test and the newest-entry pick in `_owed_scan`, the default-branch test in `owed_record_write`, and the 14-day constant `OWED_KEEP_SECONDS`, all in `hooks/guard_merge.py`. A change to any of them rewrites this record.

Risk: incident (PR #1869, PR #1914, PR #1958, PR #1985, PR #1699, PR #2015, PR #2025, PR #2026, PR #2042, PR #2068, PR #2088, lane `builder-report-in-head`).

Kind: process
Home: hooks/guard_merge.py

# A push past an unrecorded reviewed head asks

## The ruling

Coordinator brief, 2026-11-08 09:45 CST. Fix checks count, coordinator 09:54 CST. Process-only.

- A reviewer's stop (a round or a fix check) writes an entry for the head it read: `state/owed-review-records/<sha>.json`. The entry holds the remote-tracking branches at that head. The stop never blocks.
- A non-dry-run `git push` asks when all of these hold:
  - the push's destination is a branch the entry names;
  - that branch's remote-tracking ref still names the entry's head H;
  - the pushed source is another commit, not H;
  - an open pull request has head H, and its newest parseable review record does not hold Head H, or there is none.
- A state read or a gh read that fails asks too, with the note `owed-record-unread`.
- The ask names the rule and the remedy: render the record with `merge <pr> --review-record --head <H>`, post it, then push. It names no branch (rule `git-remedy-never-names-target`, a refusal names no target).
- The owner's typed override lifts the ask.
- Why: a push past an unrecorded head leaves the record unable to name that head. Fact: `merge <pr> --review-record --head <H>` stops with exit 1 when the live head is another sha (decision `pr-review-record`, the review record form).

## The incidents

- PR #1869: a base merge of main was pushed after the reviewer stopped, with no record posted (case R1).
- PR #1914, lane `notes-fix-large-3`, 05:06 CST: a fix was pushed before the FAIL round's record was posted (case R2).
- PR #1985, lane `notes-fix-other-2`, and PR #1699, lane `sim-lease-gaps`: the same mistake, a fix pushed before the FAIL record.
- PR #2015 and PR #2025, lane `bg-tail-loses-verdict`: round 3 was not recorded at its head before fixes landed. `merge --review-record --fix-check` refused.
- PR #2026 and PR #2068, lane `notes-fix-report`, 09:40 CST: a fresh chain of three rounds followed. PR #2026 is also a fix pushed after a FAIL with no record (case R2).
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

## The misses

Found in the code:

- A torn entry asks only when its head is a commit in the push's repo. Otherwise it passes.
- Pruning runs at each reviewer stop. It removes any entry file older than 14 days by mtime, whether its PR is open or not. A push past that head then passes.
- A reviewer stop on a head that no remote branch holds writes no entry. A later push past that head passes.
- A reviewer that never checks out the branch writes no useful entry. The stop reads HEAD in its own directory.
- Only the lowest-numbered open PR with head H is read. A second open PR with head H is not read.
- Only open PRs are read. A closed or merged PR with head H does not ask.
- Only shell `git push` is checked (`judge_shell`). MCP pushes (`push_files`, `update_pull_request_branch`) are not seen.
- A design-reviewer or a workflow agent writes no entry. The stop reads only agent type `reviewer`.

## The cost

- A push with no entry file: one listdir of `state/owed-review-records`. No git call, no gh call.
- A push with entry files in a repo with a merge config: one merge-config read, one file read per entry, and the git reads of `push_destinations` (only for a bare or HEAD push). An entry for another branch costs its file read only. An entry for the push's branch costs one rev-parse of the tracking ref, and a second when that ref equals H. A torn entry costs one rev-parse.
- A matching entry: the open PR list (one REST request per page, once per push), then the matched PR's issue comments (one REST request per page).
- A reviewer stop: two git spawns (`rev-parse HEAD`, `branch -r --points-at HEAD`), one listdir, and one small file written (temp file, then replace).
- No long-lived process, no timer.
- Not proved by a test: the git spawn counts. C1 and C11 prove the no-gh-call part.

Dated by: the head compare in `owed_record_hit` and the 14-day constant `OWED_KEEP_SECONDS`, both in `hooks/guard_merge.py`. A change to either rewrites this record.

Risk: incident (PR #1869, PR #1914, PR #1985, PR #1699, PR #2015, PR #2025, PR #2026, PR #2068, PR #2088, lane `builder-report-in-head`).

Kind: process
Home: hooks/guard_merge.py

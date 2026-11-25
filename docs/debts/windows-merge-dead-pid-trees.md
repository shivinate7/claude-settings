# Windows merge trees with a dead pid are kept

- **What.** On Windows the merge tool can keep a dead run's merge checkout.
  The cause is unmeasured.
  CI run 44874786597, a run of PR 3678 on Nov 21, 2026, had 8 failing cases: 6 in the Windows job merge-3 and 2 in merge-4.
  No case failed on Nov 22 or Nov 24.
  The failures are unexplained.
  The cause this debt first named is a holder check that climbs an ended ancestor.
  That cause came from review F2 on PR 3777 and was never measured on Windows.
  It does not explain these failures.
  On Windows, the failing class `StaleMergeTrees` fakes the process reader as an empty list, so the hold check never calls `_descends_from` (read from code).
  Harm: dead checkouts stay on Windows machines.
  The count on the owner's PC is unmeasured.
  Main shows no red, because its push runs skip the Windows merge shards (PR 3777 body).
  That is unmeasured on Nov 25.
- **Where.** The failing step is `drop_worktree` in `merge/merge.py` (read from code).
  It ignores the return codes of `git worktree unlock` and `git worktree prune`.
  It reads the return code of `git worktree remove --force`, then runs `shutil.rmtree(tmp, ignore_errors=True)`.
  When that removal was refused on a tree that was there, or the folder stays, it prints one line naming the tree, git's exit code and git's first output line, and returns False.
  A tree already gone prints nothing and returns True (`test_dropping_a_tree_that_is_already_gone_prints_no_line_and_returns_true` in `merge/test_merge.py`).
  Candidate causes, all unmeasured: read-only pack and object files that rmtree skips; an open handle from a scanner; a short-name or case difference in the temp path, so `sweep_dead_trees` skips the tree; `pid_alive` reads alive when `OpenProcess` is refused.
  The hold check is `held_by_live_process` and `_descends_from` in `merge/merge.py`. The process reader is `janitor/sweep.py`.
  The climb came in with commit d638056337 (Nov 20).
  The loop fix in `_descends_from` returns None (unknown) when its walk revisits a pid, so a looped parent chain holds the folder. `test_a_parent_loop_stops_at_its_first_revisit` in class `DescendsFromTest` in `lint/test_find_copies.py` pins that exit.
  The loop fix explains no Nov 21 failure and retires nothing here.
  The Windows-only case `test_a_real_exited_merge_pid_on_windows_has_its_tree_removed` in `StaleMergeTrees` reads real processes. It has never run. Its first run is CI's Windows job.
  The Linux pins in `lint/test_find_copies.py` fake `_parent_pid` and `pid_alive`, so they prove the reading only on fakes.
- **Decision.** `leftover-temp-reap`, the nearest decision (a folder stays when its holder cannot be read; Windows checks cwd only).
  No decision names the merge tool's holder check.
- **Retire.** This debt stays open. It closes only when all three show.
  1. A Windows red run shows the real cause. On a failed removal, `drop_worktree` on the head already prints git's exit code and whether the folder stays. Still owed: a Windows run where a dead pid's tree is held, so that print fires. The Windows-only case has never run. A local Windows session or CI can run it (see Ruling).
  2. The fix for that cause, with a Linux case that is red on origin/main and green after the fix. The held cases still pass: a live, unreadable grandchild of a dead owner keeps its folder (review F1 on PR 3777, head dd56d6ef). The first fix, an ended ancestor reads False, was reverted because it let the sweep delete that folder.
  3. The Windows case test_a_real_exited_merge_pid_on_windows_has_its_tree_removed is green on a checks-windows-merge job of a PR run. The close cites that run with a Retire-run line.

## Ruling

Owner, 13:26 CST Nov 22, typed in session session_013NEJKz5AWFJhGvmCUoi6wQ: "given ure a cloud session currently on a linux computer id say just leave as a debt and ill take u local to resolve the rest". A local Windows session resolves it. Linux never shows the gap.

# Windows merge trees with a dead pid are kept

- **What.** On Windows the merge tool keeps a dead run's merge checkout, so it is never removed. `_descends_from` reads an ended ancestor with no readable parent as unknown, and `held_by_live_process` keeps the folder on an unknown read. The cause is reasoned, not measured on Windows (review F2 on PR 3777, the first fix for this gap): Windows gives no orphan to init, so a live process's climb ends at an ended ancestor. The climb came in with commit d638056337, the change that added it (Nov 20). The Windows merge shards showed it in CI run 44874786597, a run of PR 3678 (Nov 21, 6 and 2 failures). The first fix, an ended ancestor reads False, was reverted. It let the sweep delete a folder that a live, unreadable grandchild of a dead owner still used (review F1 on PR 3777, head dd56d6ef). Harm: dead checkouts stay on Windows machines. The count on the owner's PC is unmeasured. Main shows no red: its push runs skip the Windows merge shards (PR 3777 body).
- **Where.** `_descends_from` and `held_by_live_process` in `merge/merge.py`. The process reader is `janitor/sweep.py`. The StaleMergeTrees class in `merge/test_merge.py` fakes `sweep.processes_in` with an empty reader, so its Windows green proves nothing about the climb. The Linux pins in `lint/test_find_copies.py` fake `_parent_pid` and `pid_alive`, so they prove the reading only on fakes.
- **Decision.** `leftover-temp-reap` (a folder stays when its holder cannot be read; Windows checks cwd only).
- **Retire.** A PR closes this debt only when it shows all three. The F1 chain and the Windows chain look alike to the current reader (a live holder, a dead pid above it, an unreadable parent), so the fix needs a signal that tells them apart:
  1. A new Linux case in lint/test_find_copies.py that is red on the current code and green after the fix, for the Windows dead-ancestor chain.
  2. The held cases there still pass. A live, unreadable grandchild of a dead owner keeps its folder (review F1).
  3. A new Windows-only case in merge/test_merge.py that reads real processes, with no fake reader, and removes a dead-pid folder. It is green on a checks-windows-merge job of a PR run. The close cites that run with a Retire-run line.

## Ruling

Owner, 13:26 CST Nov 22, typed in this session's chat: "given ure a cloud session currently on a linux computer id say just leave as a debt and ill take u local to resolve the rest". A local Windows session resolves it. Linux never shows the gap, so only a local Windows session can prove it.

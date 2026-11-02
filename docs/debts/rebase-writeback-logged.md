# A builder's write of main's bytes over a replayed test file is logged

**What.** After a finished rebase, a builder that writes main's bytes over a test file the rebase replayed is logged, not refused. Example: `git checkout origin/main -- <test>` after `pull --rebase` drops the test-author's cases. The coordinator's 21:40 CST ruling (2026-11-01) made replays log-only. This form has no ruling of its own.

**Where.** `hooks/guard.py`: `upstream_kept` and the `KEPT` kind in `own_changes`, both read by `diff_violation`. The case "builder-refuse: after a rebase, main's bytes written back over a test file are logged only" in `hooks/test_guard.py` pins the logged form.

**Decision.** `builders-cannot-edit-tests` (builders cannot edit tests). Its "Logged only" list names a replayed path that holds the upstream side again.

**Retire.** A ruling on this form, from the coordinator or the owner. If the ruling refuses it, the case above flips from logged to denied: red on the current code, green after the fix. If the ruling keeps it logged, this debt closes with no code change.

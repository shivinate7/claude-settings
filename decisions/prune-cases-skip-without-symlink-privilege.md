# Prune cases skip when this account cannot make a real symlink

## What was measured

Real Windows CI reported three failures in `hooks/test_install_src.sh`:
prune1, prune3, and prune5. The same three failed on a Windows worker used
for this fix, and only these three.

A direct probe on that worker confirms the cause. Running `ln -sfn
<target> <link>` exits 0. It does not raise an error. But `test -L <link>`
then reports false. The command wrote a plain file with the target's bytes
copied in, not a link. `ls -la` shows a regular file, not a symlink entry.

This matches `install.sh`'s own comment on `land_dir`: a Windows account
without Developer Mode holds no `SeCreateSymbolicLinkPrivilege`, so `ln -s`
cannot make a real link. `install.sh` already falls back to a copy for
this case. The three failing cases assert real-symlink behavior that this
platform state cannot produce:

- prune1 checks that a stale symlink gets pruned. The prune loop in
  `land_dir` only inspects entries that pass `[ -L ]`. A copy never does,
  so it never reaches the removal branch, and the stale entry stays.
- prune3 hand-builds an external symlink with `ln -sfn` before running
  `install.sh`. On this platform, that call also produces a copy, so the
  case starts from a state it did not intend to build.
- prune5 asserts `[ -L "$cfg/hooks/keep.sh" ]`. The file lands as a copy,
  so the assertion fails on the platform state alone, not on a defect in
  `install.sh`.

## The shape this repository has already named twice

`install.ps1` copies instead of linking, and its own comment says so.
`hooks/test_guard.py`'s `subject_unread_log_case` returns a pass that
carries a skip note naming the reason, for a case a platform cannot drive.
`hooks/mutate_guard.py` carries an `only_on` field for a mutation a
platform cannot exercise. This decision names the same shape a third time,
for `hooks/test_install_src.sh`.

## The fix

`hooks/test_install_src.sh` now probes once, before any case runs. It
creates a link in a scratch directory, then checks `[ -L ]` on the
result. The outcome sets `SYMLINK_CAPABLE`, read by every case that needs
it. This is a capability probe, not a platform-name check. A Windows
worker with Developer Mode on still runs prune1, prune3, and prune5 for
real. So does any other account that already holds the privilege. The fix
never tells such a worker apart from Linux or macOS by name.

prune1, prune3, and prune5 now return early with a `skip` call when the
probe finds no privilege. No assertion in these cases changed. Each still
runs its full body, unmodified, on a platform where the probe succeeds.

## Skip stays visible, never a silent pass

Earlier code in this repository, `subject_unread_log_case`, returns a pass
for its skip, with the reason only inside the message text. This decision
takes a different path for this suite: a new `SKIP` counter and a `skip`
function print `SKIP -`, distinct from `ok` and `FAIL`. The final tally
line changed from `N passed, M failed` to `N passed, M failed, K skipped`,
so a reader sees the skip count without reading every line above it.

## Holes, named

No Windows machine here can grant `SeCreateSymbolicLinkPrivilege` to this
account. The probe and the early-return guard are proven only on the
negative branch, where the privilege is absent. The positive branch needs
a different runner. A reviewer with Developer Mode on, or a Linux or
macOS runner, can prove it. There, the probe sets `SYMLINK_CAPABLE=1`.
prune1, prune3, and prune5 then run and pass, exactly as before this
change.

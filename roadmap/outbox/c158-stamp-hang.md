# c158-stamp-hang (cloud lane, Oct 28)

- c158: fixed after the batch drop (run 40639369770, 2 Windows proof tests red). Head cd69773 on c158-stamp-hang, draft PR #735; origin/main merged in at e03830a (gates.yml now differs from main in comments only). Fix lane round 1 clear (builder opus, reviewer opus). Ready for the next batch.
- Fix, test-only: a regex could not match a node path with a space; the orphan case does not hang on Windows. Measured there: spawnSync returns when the direct child exits, even while a grandchild holds its pipe. Windows now asserts the run ends within the cap; POSIX unchanged.
- Proven on windows-latest: the hold case reads red within its cap, names the test, leaves no process. Unproven there: the Windows orphan sweep (no orphan reached it).
- Cause of the hang: still unknown. The orphan-holds-pipe theory for spawnSync is false on Windows; the runner-side pipe theory is untested. Top candidate: stamp.mjs `bash -c` regenerate with inherited stdio.
- Note (not a debt): on Windows a suite orphan whose parent exited can outlive a passing suite; the runner clears it at job end.

# Helper programs start with no window

## The ruling

Owner, 2026-10-19 16:20 CDT: helper programs that hooks, mods and tools start use the "no window" option. Console windows came and went in the foreground, and that was very inconvenient.

Outcome protected: the owner's screen stays still while hooks and tools run.

## The design

- `hooks/_nowindow.py` is the one home. It wraps `subprocess` run, Popen, call, check_call and check_output. On Windows it adds `CREATE_NO_WINDOW` to the caller's creationflags. On other platforms it adds nothing.
- Each Node spawn passes `windowsHide: true`.
- `lint/test_no_window_spawn.py` fails on any product spawn that goes around the helper. A site that needs a console carries a `# nowindow:` marker with its reason. Today that is `bin/merge`, `bin/ste-changed`, `merge/launch.py` and the afterMerge call in `merge/merge.py`. Each one prints straight to the terminal, and the flag would hide that output.
- A hook that cannot import the helper falls back to plain `subprocess`. A missing helper must never stop a guard. The popups return, but the guard still judges.

## Safety holes, named

- (a) `bin/verdict`, `bin/ste-changed` and `merge/launch.py` import the helper with no fallback. A copy-mode install that lands `bin/` before `hooks/` makes them fail loudly. Debt: `nowindow-bin-no-fallback`.
- (b) A fallback logs nothing, so the popups return unseen. No test loads the fallback sites with the helper removed. Debt: `nowindow-fallback-silent`.
- (c) Under the flag, Ctrl-C under `verdict` may leave orphan grandchildren. Unmeasured. Debt: `nowindow-ctrl-c-orphans`.
- (d) A git terminal credential prompt in `merge/merge.py` `sh()` would hang. Git Credential Manager's window is not affected. Unmeasured. Debt: `nowindow-git-prompt-hangs`.
- (e) The scan covers `subprocess` and Node `child_process` only. It does not read `os.system` or `os.popen`, and product code has none today. Debt: `nowindow-scan-misses-os-system`.

Kind: process
Home: hooks/_nowindow.py

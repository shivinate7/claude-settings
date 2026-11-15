# An install never shows a session a half-copied hook

## The ruling

No running session judges a call with a missing, short or mixed set of hook files.

- The installer writes each non-guard file to a temp name in the same folder, then renames it over the target. A rename held up by an open reader is retried briefly.
- An install or update never locks a session out. It switches all guard files at once: it writes a new stamped folder `hooks/guard.d/<id>/`, then makes one rename of `guard.py`. In link mode it makes one rename of the `<clone>-live` link instead (`merge-reinstalls-from-main`). A guard run sees the old set or the new set, never a mix (owner ruling 2026-10-15). The guard set follows no per-file rule.
- The guard checks the `INSTALL_ID` of the modules it loaded. On an import failure, a load failure or a stamp mismatch, it waits in short steps for about 5 s and loads again. After the wait it fails closed with guard-crash, never open. This wait stays in the guard.
- No moment may leave a hook file, `CLAUDE.md`, `settings.json`, `agents`, `lint` or `skills` missing. A folder swap of `hooks` is out, because it leaves `hooks` absent for an instant. Adding the subfolder `hooks/guard.d/<id>/` is not a swap of `hooks`. Named exception: in link mode, the first move from a plain `<clone>-live` directory leaves that path absent for a moment.
- One install runs at a time (owner ruling 2026-10-15). One lock file serves every installer path: `install.sh`, `install.ps1` and the post-merge hook that `install.ps1` writes.
- Each installer path logs a start line and an end line. Each line carries a unique install id and the pid.

Why: a post-merge hook that copied in place gave every session's Bash call guard-crash for a few seconds (arbiter rulings 2026-10-14 03:41 and 03:50 CDT).

- `lint/report_guard.py` loads its helper modules from `hooks/guard.d/<id>/` first, then the flat `hooks/`. It reads the id from the flat `hooks/guard.py` stamp (`INSTALL_ID`) with one bounded regex read of the file head, once per run at load, even when question_form re-imports report_guard. No stamp, no folder or an unreadable file: flat only. A module the stamped folder lacks (override, local_time, route_match, reply_judge, call_judge, decision_watch, _nowindow) loads from the flat copy, so a half-installed folder can still mix for those; `lint/test_report_guard_stamped.py` pins the fall-through. Open note: copies under `guard.d/<id>/` resolve `__file__` paths there (hooks/guard.py, question_form.py, guard_merge.py); no report_guard call reaches them, so no verdict changes today. Cost: one bounded file read per run, no process, no file written (unmeasured). `lint/test_report_guard_stamped.py` pins it; the cost tests in `lint/test_report_guard.py` and `lint/test_report_guard_handoff.py` pin the opened-file set to the transcript and `hooks/guard.py`. Ruling: coordinator, 2026-11-09 12:46 CST (roadmap step `report-guard-stamped-copy`).

Kind: process
Home: install.sh
Home: install.ps1
Home: hooks/guard.py

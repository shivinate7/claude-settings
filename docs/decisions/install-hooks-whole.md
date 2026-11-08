# An install never shows a session a half-copied hook

## The ruling

No running session judges a call with a missing, short or mixed set of hook files.

- The installer writes each non-guard file to a temp name in the same folder, then renames it over the target. A rename held up by an open reader is retried briefly.
- An install or update never locks a session out. It switches all guard files at once: it writes a new stamped folder `hooks/guard.d/<id>/`, then makes one rename of `guard.py`. In link mode it makes one rename of the `<clone>-live` link instead (`merge-reinstalls-from-main`). A guard run sees the old set or the new set, never a mix (owner ruling 2026-10-15). The guard set follows no per-file rule.
- The guard checks the `INSTALL_ID` of the modules it loaded. On an import failure, a load failure or a stamp mismatch, it waits in short steps for about 5 s and loads again. After the wait it fails closed with guard-crash, never open. This wait stays in the guard.
- Two imports fail closed: `reread_check` in `hooks/guard.py` (the handoff-unread read) and `proc_env` in `hooks/guard_kill.py` (the session-tag read). Each is a plain import in the load loop, so a missing copy takes the same wait-then-refuse path and refuses as guard-crash. Coordinator ruling, 2026-11-08 03:12 CST: "fail-open imports of reread_check and proc_env break decision install-hooks-whole; fix them". Both modules ride in the four guard-set lists.
- `reread_check` imports its sibling `precompact_handoff` without raising, so the guard reads `reread_check.ph` right after the import and raises when it is None. A guard copy without `precompact_handoff.py` takes the same wait-then-refuse path and refuses as guard-crash (coordinator ruling, 2026-11-08 04:29 CST: "fold the precompact_handoff import into the fail-closed PR"). `precompact_handoff.py` rides in the four guard-set lists.
- A partial module is a missing one. `reread_check` sets `ph` to None when its sibling lacks a name it uses (`reread_check.PH_NAMES`). The guard also raises when `reread_check` has no `unread_handoff`. Either takes the same wait-then-refuse path and refuses as guard-crash. The Stop, pre-read and post-compact modes of `reread_check` still allow on a missing sibling (decisions precompact-handoff item 6 and guard-hooks-fail-closed item 13).
- A `question_form.py` that will not import, or lacks `use_hooks_home`, refuses the call as guard-crash. `_question_form_module` in `hooks/guard.py` prints the refusal and exits, so the `except Exception` of a page check cannot turn it into an allow. A page check that cannot read the layout still allows (decisions mockup-home, page-stale-publish and page-item-design).
- `decision_watch.py`, `feedback_guard.py`, `ruling_home.py` and `override.py` find `lint/` through `shared_names.install_root`, the one home for a module that no guard call has told its install folder. A stamped copy in `hooks/guard.d/<id>/` finds `lint/` three folders up. The guard does not reach these four today; the check pins the copies.
- `route_match.py` and `reply_judge.py` ride in the four guard-set lists. `lint/report_guard.py` puts the flat `hooks/` folder ahead of the stamped folder on `sys.path`, so the lists alone do not make it read the stamped copies. That gap stays open.
- `hooks/proc_env.py` imports ctypes only inside its macOS read (`_environ_entries_macos`), so a Python without `_ctypes` still loads the guard. A missing guard module fails closed, but a missing standard-library module that only one platform's read uses is not a guard module.
- `hooks/question_form.py` finds `lint/` and `skills/` under the install root, the folder that holds `hooks/`. Its stamped copy sits in `hooks/guard.d/<id>/`, so its own folder misses both. `guard.py` passes its own folder in through `question_form.use_hooks_home`, and `question_form.install_path` is the one home of the lookup. A copy without that would fail to import `lint/layout.py` and allow a waiting-page write it should refuse.
- No moment may leave a hook file, `CLAUDE.md`, `settings.json`, `agents`, `lint` or `skills` missing. A folder swap of `hooks` is out, because it leaves `hooks` absent for an instant. Adding the subfolder `hooks/guard.d/<id>/` is not a swap of `hooks`. Named exception: in link mode, the first move from a plain `<clone>-live` directory leaves that path absent for a moment.
- One install runs at a time (owner ruling 2026-10-15). One lock file serves every installer path: `install.sh`, `install.ps1` and the post-merge hook that `install.ps1` writes.
- Each installer path logs a start line and an end line. Each line carries a unique install id and the pid.

Why: a post-merge hook that copied in place gave every session's Bash call guard-crash for a few seconds (arbiter rulings 2026-10-14 03:41 and 03:50 CDT).

Kind: process
Home: install.sh
Home: install.ps1
Home: hooks/guard.py

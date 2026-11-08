# An install never shows a session a half-copied hook

## The ruling

No running session judges a call with a missing, short or mixed set of hook files.

- The installer writes each non-guard file to a temp name in the same folder, then renames it over the target. A rename held up by an open reader is retried briefly.
- An install or update never locks a session out. It switches all guard files at once: it writes a new stamped folder `hooks/guard.d/<id>/`, then makes one rename of `guard.py`. In link mode it makes one rename of the `<clone>-live` link instead (`merge-reinstalls-from-main`). A guard run sees the old set or the new set, never a mix (owner ruling 2026-10-15). The guard set follows no per-file rule.
- The guard checks the `INSTALL_ID` of the modules it loaded. On an import failure, a load failure or a stamp mismatch, it waits in short steps for about 5 s and loads again. After the wait it fails closed with guard-crash, never open. This wait stays in the guard.
- Two imports once failed open and now fail closed: `reread_check` in `hooks/guard.py` (the handoff-unread read) and `proc_env` in `hooks/guard_kill.py` (the session-tag read). Each is a plain import in the load loop, so a missing copy takes the same wait-then-refuse path and refuses as guard-crash (coordinator ruling, 2026-11-08 03:12 CST). Both modules ride in the four guard-set lists.
- No moment may leave a hook file, `CLAUDE.md`, `settings.json`, `agents`, `lint` or `skills` missing. A folder swap of `hooks` is out, because it leaves `hooks` absent for an instant. Adding the subfolder `hooks/guard.d/<id>/` is not a swap of `hooks`. Named exception: in link mode, the first move from a plain `<clone>-live` directory leaves that path absent for a moment.
- One install runs at a time (owner ruling 2026-10-15). One lock file serves every installer path: `install.sh`, `install.ps1` and the post-merge hook that `install.ps1` writes.
- Each installer path logs a start line and an end line. Each line carries a unique install id and the pid.

Why: a post-merge hook that copied in place gave every session's Bash call guard-crash for a few seconds (arbiter rulings 2026-10-14 03:41 and 03:50 CDT).

Kind: process
Home: install.sh
Home: install.ps1
Home: hooks/guard.py

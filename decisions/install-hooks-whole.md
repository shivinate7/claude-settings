# An install never shows a session a half-copied hook

## The ruling

No running session judges a call with a missing, short or mixed set of hook files.

- The installer writes each non-guard file to a temp name in the same folder, then renames it over the target. A rename held up by an open reader is retried briefly.
- Guard files follow no per-file rule. The guard set switches by the install switch ruling of `merge-reinstalls-from-main` (each merge reinstalls from the main checkout).
- The guard checks the `INSTALL_ID` of the modules it loaded. On an import failure, a load failure or a stamp mismatch, it waits in short steps for about 5 s and loads again. After the wait it fails closed with guard-crash, never open. This wait stays in the guard.
- No moment may leave a hook file, `CLAUDE.md`, `settings.json`, `agents`, `lint` or `skills` missing. A folder swap of `hooks` is out, because it leaves `hooks` absent for an instant. Adding the subfolder `hooks/guard.d/<id>/` is not a swap of `hooks`. Named exception: in link mode, the first move from a plain `<clone>-live` directory leaves that path absent for a moment (`merge-reinstalls-from-main`).

Why: a post-merge hook that copied in place gave every session's Bash call guard-crash for a few seconds (arbiter rulings 2026-10-14 03:41 and 03:50 CDT).

Protected by `install-no-gap.test.ps1` (a reader loop over 20 install runs fails on a missing path, a short read, or a mixed `INSTALL_ID` that outlasts the guard's wait) and `hooks/test_guard.py`, family `reload-stamp` (a truncated module, a missing module and a mismatched stamp, each fixed during the wait and never fixed).

## Holes, named

Debts: `install-writes-in-place` (some writes are still in place, and hooks other than the guard import guard modules with no reload), `install-skill-fail-exits-0` (a failed skill copy still exits 0), `symrun-link-gap-unmeasured` (the symrun window check is unmeasured on the link route), `install-reader-can-die-silent` (the test reader can die with no output), `install-family-list-by-hand` (the guard's module list is kept by hand). Guard-set and pin-move holes are in `merge-reinstalls-from-main`.

Limit: a file that the installer cannot replace keeps its old stamp, so the guard denies every call until an install succeeds. The installer prints each such file and exits non-zero. The remedy is to run the installer from a terminal, which the guard does not gate.

## Build plan

Code in `install.ps1`, `install.sh` and `hooks/guard.py`.

### windows

`install.ps1` and the post-merge hook it writes. CI runs `install-no-gap.test.ps1` on windows-latest.

### macos

`install.sh` links the hooks in local mode, so no copy runs. Its cloud mode copies, with the same temp-then-rename.

Kind: build
Plan: decisions/install-hooks-whole.md#windows (windows)
Plan: decisions/install-hooks-whole.md#macos (macos)

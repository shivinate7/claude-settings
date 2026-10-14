# An install never shows a session a half-copied hook

## The question

How does an install refresh `~/.claude/hooks` so that no running session judges a call with a
missing, short or mixed set of hook files?

## The ruling

- The installer writes each file to a temp name in the same folder, then renames it over the
  target. A rename held up by an open reader is retried briefly.
- Each installed hook file carries the same `INSTALL_ID` constant, stamped at install time. The
  repo copy holds a placeholder, and a placeholder counts as matching.
- The guard checks the `INSTALL_ID` of the modules it loaded. On an import failure, a load failure
  or a stamp mismatch, it waits in short steps for about 5 s and loads again. After the wait it
  fails closed with guard-crash, never open.
- No moment may leave a hook file, `CLAUDE.md`, `settings.json`, `agents`, `lint` or `skills`
  missing. A folder swap is out, because it leaves `hooks` absent for an instant.

Incident: 2026-10-14, about 03:25 CDT. After PR 420 merged, the post-merge hook copied the hooks
in place. For a few seconds every session's Bash call got guard-crash, and the arbiter's merges
stopped. Arbiter rulings 03:41 and 03:50 CDT.

## What protects it

- `install-no-gap.test.ps1`: a reader loop over 20 install runs fails on a missing path, a short
  read or a mixed `INSTALL_ID`. On main's in-place copy it went red in every test run.
- `hooks/test_guard.py`, family `reload-stamp`: a truncated module, a missing module and a
  mismatched stamp, each fixed during the wait (allow) and never fixed (deny).

## Build plan

Code in `install.ps1`, `install.sh` and `hooks/guard.py`.

### windows

`install.ps1` and the post-merge hook it writes. CI runs `install-no-gap.test.ps1` on
windows-latest.

### macos

`install.sh` links the hooks in local mode, so no copy runs. Its cloud mode copies; the same
temp-then-rename applies. Proof on the Mac is not measured.

Kind: build
Plan: decisions/install-hooks-whole.md#windows (windows)
Plan: decisions/install-hooks-whole.md#macos (macos)

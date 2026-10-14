# An install never shows a session a half-copied hook

## The question

How does an install refresh `~/.claude/hooks` so that no running session judges a call with a
missing, short or mixed set of hook files?

## The ruling

- The installer writes each file to a temp name in the same folder, then renames it over the
  target. A rename held up by an open reader is retried briefly.
- Each installed guard file carries the same `INSTALL_ID`, stamped at install time. The repo
  copy holds a placeholder line. Only an all-placeholder set matches. A placeholder or a missing
  line beside a real id is mixed.
- The guard checks the `INSTALL_ID` of the modules it loaded. On an import failure, a load failure
  or a stamp mismatch, it waits in short steps for about 5 s and loads again. After the wait it
  fails closed with guard-crash, never open.
- No moment may leave a hook file, `CLAUDE.md`, `settings.json`, `agents`, `lint` or `skills`
  missing. A folder swap is out, because it leaves `hooks` absent for an instant.

Incident: 2026-10-14, about 03:25 CDT. After PR 420 merged, the post-merge hook copied the hooks
in place. For a few seconds every session's Bash call got guard-crash, and the arbiter's merges
stopped. Arbiter rulings 03:41 and 03:50 CDT.

## What protects it

- `install-no-gap.test.ps1`: a reader loop over 20 install runs fails on a missing path or a
  short read. It also fails when a mixed `INSTALL_ID` outlasts the guard's wait. On main's
  in-place copy it went red in every test run.
- `hooks/test_guard.py`, family `reload-stamp`: a truncated module, a missing module and a
  mismatched stamp, each fixed during the wait (allow) and never fixed (deny).

## Holes, named

- A file that the installer cannot replace keeps its old stamp. The guard then denies every call
  until an install succeeds. The installer prints each such file and exits non-zero. The remedy
  is to run the installer from a terminal, which the guard does not gate.
- Some writes are still in place: the `CLAUDE.md` pointer, `settings.json` in `install.sh`, the
  skills folder, the install log and the marker. A reader can see one of these half written.
  Debt: install-writes-in-place.
- Hooks other than the guard, such as `stall_watch.py`, `ci_wake.py` and `sendmessage_state.py`,
  import guard modules with no reload. During an install they can load mixed code. None of them
  allows a call. Debt: install-writes-in-place.
- The guard's module list `_FAMILY_MODULES` is kept by hand. A new guard module left off it is
  not compared.
- No test pins the stampers' placeholder text to the lines in the repo's `hooks/guard*.py`. If one
  file's line drifts, it installs unstamped, the installer exits 0, and the guard denies every
  call. Debt: install-stamp-line-unpinned.
- If `Install-Dir` cannot replace a skill folder, the run does not retry it and still exits 0.
  The log can also say `settings.json=kept` after a retry recovered it. Debt:
  install-skill-fail-exits-0.
- The symrun case proves the gap with a reader loop. Its window check is unmeasured on the link
  route, which only CI runs. Debt: install-symrun-link-gap-unmeasured.
- The test reader can die with no output on a fault outside its try. Debt:
  install-reader-can-die-silent.

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

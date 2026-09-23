# The Bash tool's PATH breaks only when its shell snapshot breaks

## The claim

The Bash tool takes its `PATH` from one file, and from nothing else. That file is the
shell snapshot that Claude Code writes once per session, under
`~/.claude/shell-snapshots/`. A malformed `PATH` in the Bash tool comes from a malformed
snapshot. No setting, no profile and no shim in this repository can correct it.

## The measurement

Every Bash tool call runs this command line, read from `/proc/$$/cmdline`:

`bash -c "source <snapshot> 2>/dev/null || true && ... && eval '<the command>'"`

The shell is not a login shell, and it is not interactive. `shopt login_shell` reads
`off`, and `$-` reads `hBc`. So `/etc/profile` is not read, and `~/.bashrc` is not read.
The snapshot's last line is an unconditional `export PATH='...'`. That line runs before
the command, on every call.

81 snapshots sit on this machine. 80 carry a correct POSIX `PATH`. One does not:
`snapshot-bash-1790087889927-zclbff.sh`, written 22 September 2026. Its `PATH` is the
Windows `PATH`, semicolon-joined, with the POSIX plugin directories appended after a
single colon. Every other line of that file is byte-identical to the snapshot written
minutes earlier the same morning.

A correct snapshot carries `/usr/bin`, `/bin`, `/usr/bin/vendor_perl` and
`/usr/bin/core_perl`. Those four come from `/etc/profile`. The malformed snapshot
carries none of them. So its value never passed through a git-bash login shell. It is
the Windows-side value, with the plugin directories joined to it by the wrong
separator.

## Why no fix in this repository can reach it

The snapshot is sourced first, and it exports `PATH` unconditionally. Every other seam
loses to it.

- `settings.json` `env` sets the child's environment at spawn. The snapshot then
  overwrites `PATH`.
- `BASH_ENV` is read at shell start, before the `-c` string runs. The snapshot then
  overwrites `PATH`.
- `~/.bashrc` is never read, because the shell is not interactive.
- A shim placed early on the Windows `PATH` cannot help. Under the malformed value the
  whole Windows half is one entry, so nothing on it resolves.
- Plugins are not the trigger. A healthy session carries the same six plugin
  directories, appended with the correct separator, and resolves every command.

The component that writes the snapshot lives inside `claude.exe`, a single bundled
file of about 235 MB. A file and line for it is unknown. It cannot be read from here.

## What the defect disarms

A malformed `PATH` does more than block a command. It silently disarms every hook this
repository installs. Each hook command in `settings.json` ends with
`command -v "$p" >/dev/null 2>&1 && exec "$p" "$g"; done; exit 0`. Under the malformed
`PATH`, no `python` resolves, so every hook exits 0 and reports nothing.

Measured, with the malformed value replayed from the stored snapshot:

`env -i PATH="$BAD" sh -c 'for p in python3 python; do command -v "$p" ... done'`
finds neither interpreter.

So the five Stop gates, the two PreToolUse guards and the SessionEnd sweep all went
quiet under that value. None of them said so. A guard that goes quiet on the
defect it guards is not a guard.

## What this decision is, and is not

This records a measured, one-off corruption and the seam that carries it. It does not
propose a workaround in this repository, because no seam here can win against the
snapshot. The recovery is a new session: the snapshot is per-session, and a new session
writes a new one.

It does not change any hook. Making the hooks fail loud instead of silent is a separate
act, on the owner's own word.

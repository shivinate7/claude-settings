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

80 snapshots sit on this machine. 78 carry a correct POSIX `PATH`. Two do not:
`snapshot-bash-1788815344074-x3jl5k.sh`, written 7 September 2026, and
`snapshot-bash-1790087889927-zclbff.sh`, written 22 September 2026. In each, the `PATH`
is the Windows `PATH`, semicolon-joined, with the POSIX plugin directories appended
after a single colon. The defect is rare, but it recurs. Every other line of the
22 September file is byte-identical to the snapshot written minutes earlier the same
morning.

An earlier version of this record counted one bad snapshot in 81. That scan read only
the newest 40 files, so it missed the 7 September file.

A correct snapshot carries `/usr/bin`, `/bin`, `/usr/bin/vendor_perl` and
`/usr/bin/core_perl`. Those four come from `/etc/profile`. A malformed snapshot carries
none of them. So its value never passed through a git-bash login shell. It is the
Windows-side value, with the plugin directories joined to it by the wrong separator.

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

## What the defect does not reach

The hooks do not read the snapshot, so the malformed `PATH` does not reach them.

An earlier version of this record said the defect silently disarms every hook. It
replayed the malformed value into `sh`, and found that no `python` resolves under it.
That replay is true, but it proves only a condition: a hook that got this value would
exit 0 and report nothing. It never showed that a hook gets this value.

The guard's own log shows that no hook got it. Session `76812362` started at 09:37 on
22 September, and wrote the malformed snapshot at 09:38. At 09:42, the PreToolUse guard
refused `git checkout -b add-ponytail-marketplace` in that session, as `pointer-head`.
That refusal is in `~/.claude/guard.log`, and in the session's own transcript. The same
transcript also holds `frozen-path` and `waiter` refusals. So the guard found `python`
while the Bash tool could not.

The Stop hooks and the SessionEnd sweep are unmeasured. They share the guard's launch
path, but no log shows each of them ran in that session. The guard log starts on
16 September, so any hook's behaviour in the 7 September session is unknown.

## What this decision is, and is not

This records a measured, rare corruption and the seam that carries it. It does not
propose a workaround in this repository, because no seam here can win against the
snapshot. The recovery is a new session: the snapshot is per-session, and a new session
writes a new one.

It does not add an interpreter fallback to the hook commands. The fallback answers a
failure the measurement did not find. Add it only when a log shows a hook that could
not find `python`.

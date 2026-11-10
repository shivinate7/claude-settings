# A session never prints other processes' full arguments

## The ruling

The guard refuses a shell command that prints the full arguments of other processes (rule `process-args`):

- `ps` with a column of arguments: `aux`, `-ef`, `-f`, `-F`, or `-o` with `args`, `command` or `cmd`. An explicit `-o` format decides alone, so `ps -ef -o pid,comm` passes.
- `pgrep` with `-a` (`--list-full`), or with `-l` and `-f` together.
- `cat` of `/proc/<pid>/cmdline`, or any command fed it with a `<` redirect, where the pid is a number, a glob or a variable. The shell's own `$$` and `self` pass.

The forms that stay: a pid, a name, a parent id or a start time. That is `ps -o pid,comm`, `ps -p <pid> -o comm=`, `ps -o ppid= -p <pid>`, `pgrep <name>`, `pgrep -l <name>`, `pidof`, and `pgrep -f <pattern>`, which prints pids only.

The guard reads each command word from the parsed shell segments, also inside `sudo`, `env`, `xargs`, `bash -c` and `$(...)`. Quoted text, a comment, a commit message and a heredoc body pass.

Named limits: `/proc/<pid>/environ`, `head`, `strings` or `xargs -a` on a cmdline file, a `PS_FORMAT` environment variable, and a script that reads the file are not read.

Reason: on 2026-11-09 19:59 CST a session printed a Tailscale auth key with `ps` and `pgrep -a`. An argument can hold a secret, and a leaked secret cannot be undone.

Kind: process
Home: hooks/guard_argv.py

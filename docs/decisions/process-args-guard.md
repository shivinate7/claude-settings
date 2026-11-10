# A session never prints other processes' full arguments

## The ruling

The guard refuses a shell command that prints the full arguments of other processes (rule `process-args`):

- `ps` with a column of arguments: `aux`, `-ef`, `-f`, `-F`, the BSD `x` flag (`-x`, `-ax`, `-ex`, `-xw`, `-a -x`), or `-o` with `args`, `command` or `cmd`. An explicit `-o` format decides alone, so `ps -ef -o pid,comm` and `ps -xo pid,comm` pass.
- `pgrep` with `-a` (`--list-full`), or with `-l` and `-f` together.
- `pstree` with `-a` (`--arguments`, in any option cluster), and `top` with `-c` (in any option cluster, such as `-bc` or `-c -bn1`).
- A read of `/proc/<pid>/cmdline`, also under `task/<n>/`, where the pid is a number, a glob or a variable: any command that takes the path as an argument (`cat`, `grep`, `head`, `tail`, `strings`, `od`, `sed`, `tr`, `xargs -a`), or a `<` redirect. A command that only names or measures the file passes (`echo`, `printf`, `ls`, `stat`, `test`, `wc`, `file`, `find`), but a `find` that runs a reader on it (`find /proc/*/cmdline -exec cat {} \;`, also `-execdir`, `-ok`, `-okdir`) is refused. The pattern word of `grep`, `egrep`, `fgrep`, `rg`, `ag` and `ack` is no file, so `grep -rn /proc/1/cmdline docs` passes, while a later file operand (`grep x /proc/1/cmdline`) is a read. The shell's own `$$` and `self` pass.
- PowerShell and `wmic`: a pipeline that starts from `Get-Process` or from `Win32_Process` (`Get-CimInstance`, `Get-WmiObject`) and names `CommandLine`, and `wmic process ... get commandline`.

The forms that stay: a pid, a name, a parent id or a start time. That is `ps -o pid,comm`, `ps -p <pid> -o comm=`, `ps -o ppid= -p <pid>`, `pgrep <name>`, `pgrep -l <name>`, `pidof`, `pgrep -f <pattern>`, which prints pids only, `pstree -p`, `top -bn1`, and a PowerShell selection of `ProcessId` and `Name`.

The guard reads each command word from the parsed shell segments, also inside `sudo`, `env`, `xargs`, `bash -c`, `pwsh -c` and `$(...)`. PowerShell text is read with PowerShell's quote and comment rules. Quoted text, a comment, a commit message and a heredoc or here-string body pass.

Not read (each is a known gap, not a ruling):

- `/proc/<pid>/environ`, and a `PS_FORMAT` environment variable.
- `pkill`, and a script that reads `cmdline` itself (`python` or `perl` run from a file).
- A leading redirect before the command (`2>/dev/null ps aux`), `$(which ps)`, `busybox ps`, and `subprocess` calls in a script.
- A cmdline path built from a variable (`cd /proc/1 && cat cmdline`, `for p in /proc/[0-9]*; do cat $p/cmdline; done`), and `ls /proc/*/cmdline | xargs cat`.
- A known false alarm: a PowerShell `Where-Object { $_.CommandLine -like ... }` that selects only ids is refused. The safe form is a quoted `-Filter "CommandLine like ..."`.
- PowerShell that selects all properties (`Select *`, `Format-List *`), a `-Query` that selects `CommandLine`, `wmic process list full`, and a `CommandLine` read through a variable set on an earlier line.

Reason: on 2026-11-09 19:59 CST a session printed a Tailscale auth key with `ps` and `pgrep -a`. An argument can hold a secret, and a leaked secret cannot be undone.

Kind: process
Home: hooks/guard_argv.py

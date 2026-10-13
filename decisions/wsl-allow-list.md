# WSL runs only a fixed list of test commands

## The question

Which WSL commands can an agent run through the guard?

## The ruling

Owner ruling, 2026-10-13 15:20: "fixed test list is fine; surf the web for a consensus first".

The guard allows a WSL command only when every condition holds:

- It uses `wsl -e` or `wsl --exec`. Nothing follows the wsl part.
- It runs one of three forms:
  - `node --test <file>.test.mjs ...`
  - `pwsh -NoProfile -File <file>.test.ps1`
  - `python3 <dir>/test_<name>.py`
- Its test path is relative. It has no `..`, no dot-led glob and no absolute path.
- It can run as `python bin/verdict wsl -e ...`.

Every other WSL form is refused. Refused:

- Flags `-u`, `--system`, `--shell-type`, `-d` and `--cd`.
- Admin verbs, for example `--install`.
- A WSLENV assignment.
- A shell program, for example `bash -c`.
- A test path outside the three forms.
- `..`, an absolute path, or a dot-led glob.
- Any text after the wsl part: a pipe, a redirect, `;`, `&`, `&&`, `||` or a newline.

## How the guard finds a WSL call

The guard finds a WSL call by its launcher path:

- `wsl` or `wsl.exe`, by any path.
- `bash.exe` under `System32` or `Sysnative`. Git bash is not one of these.
- `ubuntu*.exe`.

## Before this rule

Before this rule, the guard had no WSL rule. Every WSL form was allowed.

## Worktrees

Agents in a worktree are still refused by Claude Code's own worktree isolation, not by this guard.

## Why

The list stops accidents. It does not stop a hostile test. WSL interop and `/mnt/c` let a test
file run any code. A native test run has the same limit.

Research basis (2026-10-13): pin `-e`. Sources:

- learn.microsoft.com/windows/wsl/basic-commands
- learn.microsoft.com/windows/wsl/wsl-config
- code.claude.com/docs/en/sandboxing

## What protects it

The WSL section of the guard tests (section 2c-bis) pins each allowed form and each refused form.

## Holes, named

- A bare `bash.exe -c` is not refused. It runs the System32 `bash.exe` when Git bash is not
  first on PATH. See bare-bash-on-windows-can-resolve-to-the-wsl-stub, the WSL stub record.
- `debian.exe` and `kali.exe` are not refused.
- Command-position wrappers are not refused: `( )`, `$( )`, `exec`, `cmd /c`, `bash -c`, and
  PowerShell `&` and `iex`. Lane guard-command-position owns this fix.
- A WSLENV set with no `=` is not refused. Examples: `New-Item Env:`, `Set-Item` after
  `cd env:`, `read`, `${WSLENV:=x}`, and `printf -v`.
- False alarms, when the same command also runs wsl: `echo "WSLENV=x"`, `${env:WSLENV}` reads,
  and `grep "WSLENV"`.
- No test pins the `env:` path form or the quoted-name form of WSLENV.

Kind: process
Home: hooks/guard_wsl.py

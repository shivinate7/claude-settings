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

Debts: `wsl-bare-bash-not-refused` (a bare bash.exe -c is not refused). `guard-substitution-in-token` (a substitution inside a token is not read). `wsl-wslenv-no-equals-unrefused` (a WSLENV set with no equals sign is not refused). `wsl-wslenv-false-alarms` (WSLENV text in the same command raises false alarms). `wsl-env-path-form-untested` (no test pins the env path or quoted-name forms).

Kind: process
Home: hooks/guard_wsl.py

# Shell scripts check out with LF line endings

## The ruling

Owner, 2026-10-21: `.gitattributes` forces LF on checkout for every file under `bin/` and `githooks/`, every `*.sh`, and `skills/impeccable/scripts/impeccable`. `*.cmd` comes last and forces CRLF.

- Only shell scripts are ruled. A CR breaks a shell script: `#!/bin/sh\r` names no interpreter, and each line ends in a stray `\r`. Python and Node ignore a CR, and `bin/merge` and `bin/verdict` ran with CRLF on 2026-10-21. So `*.py` and `*.mjs` stay unruled. A rule for them would show over 100 files as modified in every Windows checkout until each one re-checks them out.
- `*.cmd` stays CRLF. `cmd.exe` reads batch files with CRLF, and a `.cmd` with LF can misread labels and `goto`. It comes last so it wins over `bin/**`.
- The folder rules cover new scripts without a new line. `githooks/**` crosses folders; `githooks/*` would not.

Why: on Windows, `core.autocrlf=true` checked out the pin's `bin/rm` with CRLF, and `install.sh` copied it into `~/.claude/bin` byte for byte (3,012 bytes, 79 CR). Protected by the Windows CI test in #558. It fails on any CR in a tracked `*.sh` file, or in a file whose `#!` line names `sh`, `bash` or `zsh`, directly or through `env`. It also fails when a landed `~/.claude/bin` entry is neither a link to the pin nor byte-equal to it.

## Limits

- A shell script outside these folders, without `.sh` and without its own line, checks out CRLF on Windows. The CI test names it.
- A checkout made before the rule keeps its CRLF files until they are checked out again.

Kind: build
Plan: docs/decisions/shell-scripts-check-out-lf.md#the-ruling (all)
Home: .gitattributes

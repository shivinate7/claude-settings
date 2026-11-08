# WSL runs only a fixed list of test commands

## The ruling

The guard allows a WSL command only when every condition holds:

- It uses `wsl -e` or `wsl --exec`. Nothing follows the wsl part.
- It runs one of three forms:
  - `node --test <file>.test.mjs ...` (a glob is allowed)
  - `node <file>.test.mjs`, `pwsh -NoProfile -File <file>.test.ps1` or `python3 <dir>/test_<name>.py`: one literal path, no glob character (`*?[]`)
- Its test path is relative. It has no `..`, no dot-led glob and no absolute path.
- It can run as `python bin/verdict wsl -e ...`.

The plain node, `pwsh -File` and `python3` forms take one literal path, because the runner reads only its first file argument and a glob would give a false green. Any other plain node script, or an eval flag, stays refused.

Every other WSL form is refused:

- Flags `-u`, `--system`, `--shell-type`, `-d` and `--cd`.
- Admin verbs, for example `--install`.
- A WSLENV assignment.
- A shell program, for example `bash -c`.
- A test path outside the three forms.
- Any text after the wsl part: a pipe, a redirect, `;`, `&`, `&&`, `||` or a newline.

The guard finds a WSL call by its launcher path:

- `wsl` or `wsl.exe`, by any path.
- `bash.exe` under `System32` or `Sysnative`. Git bash is not one of these.
- `ubuntu*.exe`, `debian*.exe` and `kali*.exe`.

Reason: the list stops accidents. It does not stop a hostile test, because WSL interop and `/mnt/c` let a test file run any code, and a native test run has the same limit. Each form is how the `checks` CI workflow runs one of this repo's own suites.

Kind: process
Home: hooks/guard_wsl.py

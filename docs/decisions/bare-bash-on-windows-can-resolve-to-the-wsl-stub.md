# A bare "bash" on Windows can resolve to the WSL stub, not Git Bash

## The ruling

Python code on Windows never hands `subprocess.run` a bare `"bash"` or `"gh"`. It resolves the program by its full path.

- Why: `C:\Windows\System32` sits ahead of Git's `bin` on PATH and carries its own `bash.exe`, a WSL launcher. It mounts drives at `/mnt/c`, not `/c`, so a path built for Git Bash never resolves. A command then runs against a file that is not there. `shell: bash` steps in `checks.yml` do not hit this, because GitHub Actions resolves that word to Git Bash.
- `merge/merge.py` has one home, `resolve_program()`, shared by `sh()`, `block()` and `after_merge()`. For `bash` on Windows it tries `%ProgramFiles%\Git\bin\bash.exe` first, then the x86 and W6432 copies, then a PATH scan that skips `%SystemRoot%\System32`. On POSIX it is plain `shutil.which`.
- `hooks/test_config_watch.py` keeps its own copy, `_find_git_bash`, with the same order. Reason: a builder cannot edit a test to import `merge.py`'s resolver, so the duplicate stays.
- The "python3 -c writes the path" case passes the path through `to_python_literal_path`, which turns it to forward slashes. A native Windows path crosses bash's backslash rule and then Python's string-escape rule, and `\U` from `\Users` raises a SyntaxError.
- A future script that shells out with a bare `"bash"` or `"gh"` outside these homes carries the same risk and fails silently.

Kind: process
Home: merge/merge.py

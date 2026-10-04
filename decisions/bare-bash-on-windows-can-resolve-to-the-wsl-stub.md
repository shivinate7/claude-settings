# A bare "bash" on Windows can resolve to the WSL stub, not Git Bash

`hooks/test_config_watch.py`'s bypass cases handed `subprocess.run(["bash", "-c",
command], ...)` a bare command name. On Windows, that name does not always resolve
to Git Bash, even when Git Bash sits on PATH.

## What was measured

Real Windows CI (`gates-windows`, job 106801831422) failed 6 to 13 of the suite's 28
cases. Every failing case reported `(reverted but said nothing)`: the watch found no
change to revert, because the bypass command never actually wrote the file.

Reproduced on a real Windows machine, both under this session's own shell and under
plain PowerShell, the shell the CI step itself runs under:

```
python -c "import shutil, subprocess
print(shutil.which('bash'))
r = subprocess.run(['bash', '-c', 'pwd; uname -a'], capture_output=True, text=True)
print(r.stdout)"
```

Under plain PowerShell, `shutil.which('bash')` printed `C:\windows\system32\bash.EXE`.
The `pwd` inside that process printed `/mnt/c/Users/...`. `uname -a` named a real
WSL2 kernel. That is the WSL launcher stub, not Git Bash. It mounts Windows drives at
`/mnt/c`, never at `/c`. `/c` is the form this suite's own `to_bash_path` builds. A
path this suite hands that stub never resolves. `cp`, `mv`, and every other bypass
command then ran against a file that was never there.

The same call, with the FULL PATH to Git's own `bash.exe`, printed `C:/Users/...`.
It named a real `MINGW64_NT-...Msys` kernel string. That is the correct shell.

## Why PATH order does not save this

`shutil.which` and Python's own subprocess launch do the same PATH scan on Windows.
Neither is a bug on its own. The real cause is PATH order. On this machine, and on
the CI runner, `C:\Windows\System32` sits ahead of Git's `bin` folder. `System32`
carries its own `bash.exe`, a WSL launcher, whether or not a WSL distro is installed.
It wins the scan first.

`.github\workflows\gates.yml`'s own `shell: bash` steps never hit this. GitHub
Actions treats the literal word `bash`, as a shell name, as a special case. It always
resolves that word to Git Bash's own known path. This repository's Python code has
no access to that same special case.

## What this decision does

`hooks/test_config_watch.py` now resolves Git Bash by its own full path, once, at
import time (`_find_git_bash`). It tries `%ProgramFiles%\Git\bin\bash.exe` first,
then `%ProgramFiles(x86)%` and `%ProgramW6432%`'s own copies. It then falls back to
a PATH scan that skips any folder under `%SystemRoot%\System32`. Every `shell()`
call passes that resolved path, never a bare `"bash"`. On POSIX this is a no-op.
`shutil.which` still returns the one real `bash` already on PATH there.

A second, narrower case needed its own fix. The "python3 -c writes the path" case
embeds a Python `open(...)` call inside a bash double-quoted string. A native
Windows path there crosses two escapers in a row: bash's own backslash rule, then
Python's own string-escape rule. `\\` becomes one `\`. A surviving `\U`, from
`\Users`, then demands eight hex digits Python never finds. That raised a
SyntaxError inside the embedded python3 call. The new `to_python_literal_path`
helper turns the path to forward slashes first. Both bash and native Windows Python
read that form the same way, with no backslash left to mis-escape.

## What remains open

`merge/merge.py` had this same risk: `after_merge()` ran `subprocess.run(["bash",
"-c", cmd])`, and `block()` ran bare `"gh"`, bypassing `sh()`'s own lookup. Both now
call `resolve_program()`, one home in `merge.py` shared by `sh()`, `block()` and
`after_merge()`. For `bash` on Windows it carries the same order as
`hooks/test_config_watch.py`'s `_find_git_bash`: `%ProgramFiles%\Git\bin\bash.exe`
(then the x86 and W6432 copies), then a PATH scan that skips
`%SystemRoot%\System32`. On POSIX it is plain `shutil.which`, unchanged.

`hooks/test_config_watch.py` keeps its own copy of `_find_git_bash`. It is a test
file. A builder cannot edit a test to import `merge.py`'s resolver, so the
duplicate stays. That is the stated reason for the duplication, not an oversight.

A future script that shells out with a bare `"bash"` or `"gh"` outside these two
homes carries the same risk on Windows. It will fail the same silent way.

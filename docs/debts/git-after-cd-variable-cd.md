# A cd to a variable folder is not judged by git-after-cd

**What.** Rule `git-after-cd` reads a cd whose folder word holds a variable (`cd "$WT"; git push`) as unknown, so the git write after it passes. When that variable is empty or names a folder that is gone, the cd fails and the write runs in the folder the shell stayed in. Failing closed would also refuse the usual `cd "$REPO"; git status` shape of normal work, so the rule passes it.

**Where.** `git_after_cd_hit` in `hooks/guard.py`, through `cd_walk(...).stranded` in `hooks/guard_core.py`, which gives no folder for a cd to a variable and so never reads it as stranded.

**Decision.** `git-after-cd-joins-with-and`, a git write after a cd joins with `&&`.

**Retire.** Read the variable's value when the command sets it earlier in the same text, or from the shell's environment, and judge the cd as a real folder. The check: a case in `hooks/test_guard.py` where `cd "$WT"; git push` with `WT` set to a missing folder is refused, and the same with `WT` set to a real folder passes. Run `python3 hooks/test_guard.py`.

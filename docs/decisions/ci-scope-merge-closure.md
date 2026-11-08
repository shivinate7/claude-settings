# The merge flag covers every module merge.py loads

## The ruling

Coordinator, 2026-11-07 20:08 CST, widened at 21:03 and 21:19 CST (lane merge-lock-expired-delete-race,
step sha-hex-followups). Process-only.

- `ci-scope.sh` gives the merge flag (`$M`, job `checks-windows-merge`) to each file in the closure of
  modules `merge/merge.py` loads: imports at module level and inside functions, loads by path, and the
  modules those load in turn.
- The guard family is in the closure: `merge.py` loads `hooks/guard_core.py`, and each `hooks/guard_*.py`
  keeps the flags of `hooks/guard.py`.
- No file in the closure is an exception.
- A script that `merge.py` runs as a subprocess, such as `bin/ci-job`, is not a load and is out of the
  closure (coordinator, 2026-11-07 22:12 CST). Its own tests cover it.

Check: `lint/test_ci_scope.py` walks the imports from `merge/merge.py` to closure and fails when a file in
it lacks the merge flag. It fails loudly, naming the file and the load, on a load it cannot resolve: a
package-qualified import, or a by-path load built at run time. A path built from a parameter is no load,
since its callers name the file. A by-path load through a constant named in `ALLOWED_CONSTANT_LOADS` takes
that constant's value as its path. Code: `.github/scripts/ci-scope.sh`.

## Cost

A pull request that changes only a guard file now also runs `checks-windows-merge`. On a pull request,
that job runs `merge/test_launch.py`, the Windows slice of `merge/test_merge.py`
(`MERGE_TESTS=windows-slice`) and `merge/test_cmd.py`. Shards 2 to 5 do not run on a pull request. The
same holds for each other file in the closure. On a pull request the job takes a median of 2.2 min
(`ci-job-caps`, window of 2026-11-06). Off pull requests it takes a median of 11.8 min and at most 13.6 min over
24 runs (same record).

Why: a change to a module that `merge.py` loads changes what the merge tool does. A pull request that
skips the Windows merge job can then break merges on Windows with green CI.

Kind: process
Home: .github/scripts/ci-scope.sh

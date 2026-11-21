# Leftover temp folders of dead test runs are reaped after an hour

## The rulings

The janitor reaps a folder that a killed test or mutation run left in the temp folder (`tempfile.gettempdir()`). The reap is one step of the machine-wide sweep (`the-janitor-is-one-machine-wide-sweep`). The code is `find_leftover_temp` and `leftover_temp_tier` in `janitor/sweep.py`. Source: PR 3696, the change that adds the step.

A folder is reaped only when all five checks hold. Any other result keeps the folder.

1. **The name carries an owner pid.** Two forms match. `mutate_guard_<pid>-<rand>` sits directly in the temp folder. It is the work folder of `hooks/mutate_guard.py`. `<pid>-<32 hex>` sits in `claude-settings-test-temp/`. It is the run folder of `lint/_test_temp.py`. A name with no pid, such as an older `mutate_guard_<rand>`, never matches, so it is kept.
2. **It is a real folder.** A link is skipped. A plain file is skipped. Any other name is skipped.
3. **It is over an hour old,** by its mtime (`LEFTOVER_TEMP_MIN_AGE`). A younger folder may belong to a run that is still starting or ending.
4. **Its owner pid is proven gone.** A live pid keeps the folder. A pid that cannot be read keeps it too.
5. **Nothing runs inside it.** No live process has its cwd in the folder, and none has an open file in it. Linux reads `/proc/<pid>/fd`. macOS runs `lsof +D`. Windows checks cwd only. A failed read keeps the folder.

Shell-test folders are a special case. `lint/test_duo_fold.sh` takes its run folder from a `python3 -c` call that exits at once. The pid in that name belongs to a process already gone when the folder is made. For those folders, the reap rests on check 3 and check 5 alone.

Behaviour:

- A preview (no `--confirm`) prints `WOULD reap` and changes nothing.
- A `--confirm` run removes each reaped folder with `shutil.rmtree`. A failed removal prints `FAILED` and counts toward the exit code, so the run exits 1.
- Past the deadline, the step keeps every folder it would reap. The next run reaps it.
- The SessionEnd run skips this step (`session_end` in `main`). Only the daily job and a person's full run reap.

Why a second sweep. `lint/_test_temp.py` sweeps dead-pid run folders after an hour, under `test-temp-standard` (one temp root per repo, one run folder per run). It sweeps only when a later test run starts. This step runs on the janitor's schedule, so it reaches a folder that no later run would sweep. It also reaps `mutate_guard_` folders, which `_test_temp.py` never matches. For run folders the two sweeps overlap on purpose: the janitor step covers a folder that no later test run would sweep, and the `mutate_guard_` folders.

Cost:

- Process starts. Linux: none, it reads `/proc`. macOS: one `lsof +D` per candidate that passes checks 1 to 4, and one `lsof -d cwd` per run that reaches check 5, memoised within the run (`_memo`).
- Files removed: the reaped folders.
- How often: each full sweep run (the daily job and a person's full run). Never at SessionEnd.
- Time per run: unmeasured. No test counts the process starts.

Tests. `janitor/test_sweep.py`, class `LeftoverTempFolderTests`, pins a case for each check above. It does not pin the session-end skip, the deadline keep or the exit code. That gap is `leftover-temp-skips-untested`.

Kind: process
Home: janitor/sweep.py

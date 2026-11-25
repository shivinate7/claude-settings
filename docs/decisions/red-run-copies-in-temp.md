---
id: pending
slug: red-run-copies-in-temp
---

# A red run or mutant copies an old commit to the test temp root, and the copy goes when its run ends

## The ruling

Owner, 2026-11-20 13:26 CST: a red-run or mutant copy of an old commit is made where the guards allow and the sweep knows, and is removed when its run ends.

Mistake: 69 `git archive` copies of old commits sat in the session scratchpad. They took 8.6 GB. The disk filled, and no agent could start.

Mistake, 2026-11-24: a test-author could not get a red-first proof for a case that lists tracked files. The copy has no `.git`, so `testing/tracked_tree.py` raised, and the `run_in_copy` cases of `lint/test_check_landed_dirs.py` could not run in a copy.

- `bin/red-run <commit> [--add <path>]... [--replace <path> <old> <new>]... -- <test command>` makes one copy per run. It exports the commit's tree (`hooks/tree_export.py`) into a run folder of the test temp root (`lint/_test_temp.py`, `<temp>/claude-settings-test-temp/<pid>-<uuid>`). The copy has no `.git` in it or above it. The test command runs in the copy.
- The export also writes a manifest at the copy's root. Its name is the `MANIFEST` constant in `hooks/tree_export.py`. It lists each archived file and symlink path, one per line, from the archive stream the export already reads. `export_tree` writes it for every caller, `bin/ci-job` included. It is written only when the export succeeds.
- `testing/tracked_tree.py` lists a root with no `.git` from that manifest. A root with neither a `.git` nor a manifest raises, and the error names both.
- The guards have no checkout to refuse. The copy sits in the temp root, which no checkout holds (decision `an-agent-outside-its-home-tree-must-stop`, "Outside the clone passes").
- The sweep knows it. `lint/_test_temp.py` removes a run folder that a dead process left (`janitor/GUIDE.md`, the leftovers table).
- `bin/red-run` removes its copy when the run ends: on a pass, a fail or a crash, and on TERM, HUP or INT.
- Retired: the `git archive` copy into the session scratchpad, and the red-run checkout made with `git worktree add --detach` under `<repo>/.claude/worktrees/`.

Why: a copy that its run removes on exit cannot pile up. The retired routes left a folder that each agent had to remove by hand, and 69 of them stayed in the scratchpad. The manifest lets a case that lists tracked files run in its copy.

Cost: a copy per run, made by a tree export and removed when the run ends. The copy's size is unmeasured. The manifest adds a text file to each copy, with a line for each archived path, and no git call: its paths come from the archive stream the export reads anyway. No long-lived process, no log, no timer. Each run starts git child processes, then the test command.

Limits:
- `--add` lists each file it puts in the copy. `bin/red-run` calls `manifest_add`, which appends each path not already listed. A folder lists each file under it. No case pins a folder.
- A tracked path with a newline fails the export, and the error names the path. `manifest_add` raises on one too. No case pins that raise.
- The `.sh` and `.ps1` helpers (`testing/tracked_tree.sh`, `testing/TrackedTree.ps1`) list with `git ls-files` only and have no manifest mode. In a copy with no `.git`, they fail.
- Outside `lint/find_copies.py`, the claim that no checker trips on the manifest rests on a recorded run of eight checkers, not on a case.
- On macOS no manifest case skips. The newline case skips only where `make_fixture` cannot create a newline in a name. The `/proc` hold cases in `lint/test_find_copies.py` and the PowerShell helper case in `lint/test_tracked_tree.py` skip there (no `/proc`; no `pwsh` unless installed). Neither is a manifest case.

Kind: process
Home: bin/red-run
Done check: `lint/test_red_run.py`. Its cases pin the copy's tree, the `--add` and `--replace` operations, the exit codes, and the removal of the copy on a pass, a fail, a crash, and on TERM, HUP and INT. The manifest cases are `ManifestCases` in `lint/test_tracked_tree.py`; `TreeExportManifestCases` and `TreeExportPathCases` in `hooks/test_tree_export.py` (the newline case); `RedRunTrackedCopyCases` in `lint/test_red_run.py` (the `--add` case); and `FindCopiesTest.test_a_child_holding_the_export_manifest_reads_the_same_as_one_without_it` in `lint/test_find_copies.py`.

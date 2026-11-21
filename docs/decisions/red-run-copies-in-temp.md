---
id: pending
slug: red-run-copies-in-temp
---

# A red run or mutant copies an old commit to the test temp root, and the copy goes when its run ends

## The ruling

Owner, 2026-11-20 13:26 CST: a red-run or mutant copy of an old commit is made where the guards allow and the sweep knows, and is removed when its run ends.

Mistake: 69 `git archive` copies of old commits sat in the session scratchpad. They took 8.6 GB. The disk filled, and no agent could start.

- `bin/red-run <commit> [--add <path>]... [--replace <path> <old> <new>]... -- <test command>` makes one copy per run. It exports the commit's tree (`hooks/tree_export.py`) into a run folder of the test temp root (`lint/_test_temp.py`, `<temp>/claude-settings-test-temp/<pid>-<uuid>`). The copy has no `.git` in it or above it. The test command runs in the copy.
- The guards have no checkout to refuse. The copy sits in the temp root, which no checkout holds (decision `an-agent-outside-its-home-tree-must-stop`, "Outside the clone passes").
- The sweep knows it. `lint/_test_temp.py` removes a run folder that a dead process left (`janitor/GUIDE.md`, the leftovers table).
- `bin/red-run` removes its copy when the run ends: on a pass, a fail or a crash, and on TERM, HUP or INT.
- Retired: the `git archive` copy into the session scratchpad, and the red-run checkout made with `git worktree add --detach` under `<repo>/.claude/worktrees/`.

Why: a copy that its run removes on exit cannot pile up. The retired routes left a folder that each agent had to remove by hand, and 69 of them stayed in the scratchpad.

Cost: a copy per run, made by a tree export and removed when the run ends. The copy's size is unmeasured. No long-lived process, no log, no timer. Each run starts git child processes, then the test command.

Kind: process
Home: bin/red-run
Done check: `lint/test_red_run.py`. Its cases pin the copy's tree, the `--add` and `--replace` operations, the exit codes, and the removal of the copy on a pass, a fail, a crash, and on TERM, HUP and INT.

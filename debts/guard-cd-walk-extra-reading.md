# The run-folder walk reads a cd that bash never runs

- **What.** When a command ends inside an open quote, the guard also judges a second reading. That reading can hold a `cd` that bash never runs. The run-folder walk then judges a later git write in the wrong folder.
- **Where.** `_run_dir` and the `segment_roots` walk in `hooks/guard.py`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** Each `cd` walker reads only bash's own reading. A shared-tree test with `git restore f.txt` then `echo don't; cd <lane>` asks.

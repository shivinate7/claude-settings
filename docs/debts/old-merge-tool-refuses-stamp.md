# An older merge tool refuses the stamp

**What.** A merge tool older than this change refuses main's `stamp.json`, which has the unknown fields `keepBranches` and `lintSuites`. The tool stops with a clear message. The merge does not run.

**Where.** `.github/stamp.json` on main. The merge tool copy on each machine.

**Decision.** `merge-deletes-batch-lanes` (a merge deletes its batch's lane branches). **See** `config-lands-after-its-reader` (a merge config change that needs new tool code lands after the tool that reads it).

**Retire.** Run `merge/install_from_main.sh` on each machine that runs the merge tool. Check: `merge <pr>` preview reads the stamp with no refusal on each machine.

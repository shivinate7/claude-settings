# A coordinator's merge inside a nested shell is not read

**What.** Guard rule `coordinator-scope` reads a merge spelled as the words of a shell segment. A merge inside `bash -c`, `sh -c`, `eval`, `ssh` or `$(...)` is one quoted string or substitution to that reader, so it passes for a coordinator.

**Where.** `hooks/guard.py` (`coordinator_act_hit`) and `hooks/guard_merge.py` (`merge_call_of`, `merge_confirm_of`). Neither parses the string as a second command line.

**Decision.** `session-tiers`, tiers and their guards (section "Spawns and merges"). Risk kind: unmeasured. No coordinator has been seen to write this form.

**Retire.** Read the body of `bash -c`, `sh -c` and `eval`, and the text of `$(...)`, as shell. Judge each segment as a top-level one. For `ssh`, refuse or read the remote command. Add a case per spelling that goes red on the old guard. A refused coordinator merge in each spelling closes the debt.

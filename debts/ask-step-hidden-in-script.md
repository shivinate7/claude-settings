# An ask step hidden in an inline script is not asked

- **What.** A settings write of the subagent model cap inside `bash -c "<write>; echo hi"`, `echo $(<write>)`, a subshell `(<write>)` or backticks is allowed with no ask. An unspaced `$(git ...)` is missed too. Found in review round 1 of lane ask-alone, by live probes.
- **Where.** The step split in `hooks/guard_core.py` (`inline_script`, near line 1473, and the `$(` reader near line 379), and the bash -c gap named in `hooks/guard.py` near line 427.
- **Decision.** `ask-steps-run-alone`.
- **Retire.** The guard reads the steps inside an inline script, a command substitution and a subshell. Tests show each shape asks when alone and denies when chained.

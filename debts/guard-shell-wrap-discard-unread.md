# A discard inside a shell wrapper is not read

- **What.** A discard inside `sh -c`, `eval`, or a `$(…)` substitution is not read. Example: `echo $(cd <shared>; git restore f.txt)`. Review closed eight shapes. These stay open under the owner's round cap.
- **Where.** The git-call reader in `hooks/guard_shared_tree.py`.
- **Decision.** `stash-push-is-clone-wide` (stash push is clone-wide).
- **Retire.** The reader reads the body of each wrapper. A test per wrapper shape goes red on the current code, and green after the fix.

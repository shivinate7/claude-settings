# Writes into another clone pass the write scan

**What.** Into a separate clone, as into another checkout, these forms pass the write scan: `touch`, `mkdir`, `rsync -a src/ <dir>/`, `curl -o`, `tar -C`, `make -C`, `env -C`, `bash -c 'cd X && touch f'`, and `cd $HOME/...`. A `$` name is not read (read hooks/guard.py _cd_targets; hooks/guard_frozen.py MUTATING_COMMAND). Git verbs in `OTHER_CHECKOUT_GIT_VERBS` pass in these forms: `env -C <dir> git ...`, `bash -c '...'`, `$(git -C ..)`, `-C $VAR`, and `--git-dir=` or `--work-tree=` with no `-C` (read hooks/guard.py session_home_git_hit). Git verbs outside that set pass with `git -C <dir>`: `branch -D`, `tag`, `push`, `bisect`, `branch -f`, `update-ref`, `symbolic-ref`, `filter-branch`, `merge-file`, `submodule` and `sparse-checkout` (read hooks/guard.py OTHER_CHECKOUT_GIT_VERBS). A `cd` into another checkout is refused (read hooks/guard.py other_checkout_hit).
**Where.** `hooks/guard.py`, `SHELL_WRITE_HINT`, `_cd_targets` and `OTHER_CHECKOUT_GIT_VERBS`, with `MUTATING_COMMAND` in `hooks/guard_frozen.py` (read hooks/guard.py SHELL_WRITE_HINT).

**Decision.** `an-agent-outside-its-home-tree-must-stop`, an agent outside its home tree must stop (read docs/decisions/an-agent-outside-its-home-tree-must-stop.md).

**Retire.** Add a case to `hooks/test_guard.py` for each form in What (read hooks/test_guard.py). Each case expects a refusal, so it is red while the form passes.

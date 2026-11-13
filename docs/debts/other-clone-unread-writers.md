# Writes into another clone pass the write scan

**What.** Into a separate clone, as into another checkout, these forms pass the write scan: `touch`, `mkdir`, `rsync -a src/ <dir>/`, `curl -o`, `tar -C`, `make -C`, `env -C`, `bash -c 'cd X && touch f'`, and `cd $HOME/...`. A `$` name is not read. Git verbs in `OTHER_CHECKOUT_GIT_VERBS` pass in these forms: `env -C <dir> git ...`, `bash -c '...'`, `$(git -C ..)`, `-C $VAR`, and `--git-dir=` or `--work-tree=` with no `-C`. Git verbs outside that set pass with `git -C <dir>`: `branch -D`, `tag`, `push`, `bisect`, `branch -f`, `update-ref`, `symbolic-ref`, `filter-branch`, `merge-file`, `submodule` and `sparse-checkout`. A `cd` into another checkout is refused for any verb. The other copy of the note lists `git -C <dir>` with `add`, `rm`, `branch -D`, `tag` or `push` as passing, and `git -C <dir>` with `--git-dir=` or `--work-tree=`. So the two copies disagree on `git -C` with `add` and `rm`. The source note's Until date was 2026-11-22. The source note says Fix: none, a review finding with no incident.

**Where.** `hooks/guard.py`, `SHELL_WRITE_HINT`, `_cd_targets` and `OTHER_CHECKOUT_GIT_VERBS`.

**Decision.** `an-agent-outside-its-home-tree-must-stop`, an agent outside its home tree must stop.

**Retire.** Add a case to `hooks/test_guard.py`, beside `worktree_home_cross_checkout_case`, for each form in What. Each case expects a refusal, so it is red while the form passes.

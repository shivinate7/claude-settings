# A wrapped or nested in-place sed with a flag cluster is missed

- **What.** Rules `frozen-path` and `coordinator-scope` read sed's operands only when `sed` is the command word of its segment. A wrapped or nested sed (`sudo sed`, `xargs sed`, `find -exec sed`, `bash -c "sed ..."`) keeps the text match, which finds only `-i` and `-i.bak`. So `xargs sed -Ei`, `sudo sed -ni` and `bash -c "sed --in-place ..."` on a protected file pass.
- **Where.** `_sed_operands` and the sed line of `writes_to` in `hooks/guard_frozen.py`.
- **Decision.** `frozen-path-resolves-shell-vars` (rule 7 resolves shell variables before it matches a write target).
- **Retire.** Read sed's operands after each wrapper the guard knows, and inside a quoted `-c` script. A case `xargs sed -Ei 's/a/b/' <frozen hook>` denies.

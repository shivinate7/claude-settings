# A sed behind a `find -exec` or a deep quote is still missed

- **What.** Rule `frozen-path` reads sed's operands where `sed` is the command word, past a wrapper (`sudo`, `xargs`, `env`) or inside a `sh -c` script. Some forms stay on the text match, which finds only `-i` and `-i.bak`. A `find -exec sed -ni 's/a/b/' FILE \;` is missed, because `find` is no wrapper the command reader unwraps. A bare `find -exec sed -i` that names no target is missed too: the files it edits are never in the command. A sed fed by a pipe inside a `sh -c` script (`bash -c "echo FILE | xargs sed -ni ..."`) is missed. A `w` command with no space (`sed -n 'wFILE' x`) is missed.
- **Where.** `_sed_operands`, `_sed_nested_writes` and the call site in `_shell_write_hit` of `hooks/guard_frozen.py`.
- **Decision.** `session-tiers` (tier guards, the boundary a session may not cross).
- **Retire.** Read the words after each `-exec` of a `find` as a segment of their own, and read a pipe inside a nested script. Cases `find . -exec sed -ni 's/a/b/' <frozen hook> \;` and `bash -c "printf '%s\n' <frozen hook> | xargs sed -ni 's/a/b/'"` deny.

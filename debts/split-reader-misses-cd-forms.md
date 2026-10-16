# The token reader misses some cd forms

- **What.** `split_segments` does not model `$'...'` ANSI-C quoting, `$(...)`, or backtick substitution. It cannot see a `cd` whose target exists only after variable expansion. `cd "$DIR"` resolves to the literal `$DIR`. The old regex missed these forms too. A hidden `cd` is skipped. The previous-folder forms are misread: `cd ~-` and `Set-Location +` name the literal folders `~-` and `+`, and `cd -` and `Set-Location -` name no folder. Measured on the lane head. This is unmeasured against banchi's own gaps in the same areas. The `shell_parse.py` docstring does not claim to close them either.
- **Where.** `_run_dir` and `split_segments` in `hooks/guard.py`, `_segment_cd_target` in `hooks/guard_core.py`, and `shell_parse.py`.
- **Decision.** `split-segments-comment-rule` (split_segments needs the shell's comment rule).
- **Retire.** Model each form, or measure it against the real shell. A test per form fails on the current code and passes after the fix.

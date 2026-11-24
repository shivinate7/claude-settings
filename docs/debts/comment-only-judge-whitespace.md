# The comment-only judge reads a whitespace-only edit as comment-only

- **What.** `lint/comment_only.py` drops whitespace inside a line, so a whitespace-only edit reads as comment-only. `x=1` to `x = 1` passes, and so does `f"{x=}"` to `f"{x= }"`, though the second prints different output. Claude meets it when a formatter reflows a line in the same commit as a comment edit: the code suites skip on a real code change.
- **Where.** `lint/comment_only.py`, `py_code`; its docstring (line 21) states the whitespace rule. The scope job's `python3` call in `.github/scripts/ci-scope.sh` has no version pin.
- **Decision.** `push-skip-on-proven-tree` (a push skips on a proven tree; its comment-only delta).
- **Retire.** The judge reads a change of whitespace inside a line as code, and the scope job pins its Python. Closed by `lint/test_ci_scope.py`, with a case where `x=1` to `x = 1` sets a code flag.

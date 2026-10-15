# A heredoc run by a path other than its own header line is read as text

- **What.** `_PIPED_SHELL` reads a shell only when it follows a `|` on the header line. A shell that runs the body another way stays text: a pipe on the next line (`cat <<EOF |` then `sh`), `xargs sh`, `source <(cat <<EOF)`, `eval "$(cat <<EOF)"`, or a pipe into `python -`, `node` or `perl`. A closing line is matched after `.strip()`, so a space-indented closer ends a body early (see `heredoc-indented-close`).
- **Where.** `_PIPED_SHELL` and `strip_heredoc_bodies` in `hooks/guard_core.py`.
- **Decision.** `ask-steps-run-alone` (run ask steps alone).
- **Retire.** Read the command a heredoc feeds, through the same walk, for each shape above. A case per shape with a prune or a kill in the body denies, and a pipe to `cat` or `tee` still allows.

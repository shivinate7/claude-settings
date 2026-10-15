# A heredoc run by a path other than its own header line is read as text

- **What.** Some bodies run, but the guard reads them as text. These shapes are open:
  - a pipe on the next line (`cat <<EOF |` then `sh`);
  - a pipe into `python -`, `node` or `perl`;
  - a file that the command writes and then runs (`cat <<EOF > x.sh && sh x.sh`);
  - a kill in `eval "$(cat <<EOF)"`. The body stays in view, but the kill rule reads no segment inside the double quote. Main allows it too.

  `_PIPED_SHELL` and `_FED_SHELL` close the other shapes. A closer is matched after `.strip()`, so a closer with a leading space ends a body early (see `heredoc-indented-close`).
- **Where.** `_PIPED_SHELL`, `_FED_SHELL` and `strip_heredoc_bodies` in `hooks/guard_core.py`. Main kept some body lines in view: at a word main did not see (`'EOF-1'`, `\EOF`), or at a short word that closed early. For those bodies, the bandaid `_MAIN_HEADER` gives main's walk. So the open shapes deny, as on main. But such an interpreter body counts each line, as on main. The one-step ruling of `ask-steps-run-alone` does not apply to it.
- **Decision.** `ask-steps-run-alone` (run ask steps alone).
- **Retire.** For each open shape, read the command that the heredoc feeds, through the same walk. Read a kill inside a quoted `$(` too. A case per shape with a prune or a kill in the body denies. A pipe to `cat` or `tee` still allows. Then delete `_MAIN_HEADER`.

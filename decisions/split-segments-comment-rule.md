# `split_segments` needs the shell's own comment rule

## The ruling

**The predicate is the shell's own rule.** An unquoted `#` that STARTS A WORD opens a comment. It runs
to the end of its line. "Starts a word" means that the `#` is at index 0, or the previous character is a
space, a tab, a newline, or one of `|`, `&`, `(`, `;`. Two shapes stay non-comments:

- `fix#3`, because the `#` follows a letter.
- `'#300'`, because the `#` sits inside a quote.

Reason: without a comment rule, an apostrophe inside a `#` comment opened a quote that ran to the end of
the text. Everything after it collapsed into one segment that rule 1 never saw into. The fix is a lifted
copy of the three-branch addition in banchi's `shell_parse.py` (`~/Developer/banchi/scripts`), without its
`delimiters` parameter. `hooks/test_guard.py:split_segments_comment_case` carries the cases.

**`_run_dir` reads `cd` and `git -C` off parsed tokens.** It splits the command into segments with
`split_segments`, the same quote- and comment-aware reader as above. Each segment is tokenized with
`segment_tokens` (shlex). A segment counts as a `cd` or a `git -C` only when `resolve_command` says that
word is the segment's OWN command. It no longer uses `CD_RE` / `GIT_C_RE` over the raw command string. So
a `cd` inside a quoted `-c` argument or inside a comment does not move the subject.

- An attached `-C<path>` or `-C=<path>` is not a `git -C` target, because real git rejects it
  (`unknown option`). Only an exact `-C` token, followed by the next token, is read as a `-C` target.
- `_strip_heredoc_bodies_unconditionally` strips every heredoc body before `_run_dir` splits the command,
  interpreter or not. A `cd` inside an interpreter heredoc moves the interpreter's directory, never the
  outer shell's cwd. Every other caller of `strip_heredoc_bodies` keeps interpreter bodies under inspection.
- `cd -` resolves to no target, and the subject falls through to the shell's own cwd. The guard cannot
  know the previous directory, so this is the fail-open answer.
- `--work-tree` still outranks `-C` and `cd` (precedence documented near `command_root` in
  `hooks/guard.py`). `GIT_WORK_TREE_RE` is untouched.
- A spelling that this reader accepts, but real git or the outer shell rejects, is the same class of
  defect. Measure it against the real binary first.

Kind: build
Plan: decisions/split-segments-comment-rule.md#the-ruling (all)
Home: hooks/guard.py

## Holes, named

Debts: `split-reader-misses-cd-forms` (the token reader misses some cd forms), `split-comment-shapes-unmeasured` (the comment rule is unmeasured on quoting shapes).

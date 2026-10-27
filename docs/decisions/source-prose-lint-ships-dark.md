# The new source-prose mode ships dark

## The ruling

The comment-and-docstring mode of `ste_lint.py` stays off by default (`--source-prose` and `check_source`). Neither runs unless a caller asks. Every existing caller keeps its Markdown-only behavior, byte for byte. Reason: the mode would fail on work nobody wrote this week, and a guard that is red from its first run teaches its reader to stop reading it.

- Python comments come from `tokenize`'s COMMENT tokens. Docstrings come from `ast`, at module, class and function scope. Neither looks inside a string literal, so a semicolon in a string never reaches the lint.
- Shell comments come from a small scanner that tracks quote state, one line at a time, in place of a full shell parser.
- A sentence that wraps across several comment or docstring lines joins into one sentence before the word count. A finding keeps the real source line number.
- `actions/ste-lint/action.yml` has a `changed_paths` input, in the same style as `paths`. A caller can point the changed-scope diff at source files instead of Markdown. Its default, `*.md`, matches the old hardcoded value.
- `check_source` also runs STE011 and STE013, and both read `error`.

Turning the mode on needs a cleanup first, as a separate job from the guard. Mixing the two would bury the guard in noise on the day it ships. The count of real errors in comments and docstrings under today's rules is unmeasured.

Kind: process
Home: lint/ste_lint.py

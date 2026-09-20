# `split_segments` needs the shell's own comment rule

`hooks/guard.py:split_segments` tracked single and double quotes. It had no
comment rule at all. An apostrophe inside a `#` comment opened a quote. That
quote ran to the end of the text. Everything after it collapsed into one
segment. Rule 1 never saw the real commands hiding past the comment.

## What was measured

Banchi, 2026-09-19, measured this against `scripts/guard-shell-selftest.sh`'s
runaway-driver fixture. The fixture's second line is exactly `# the driver's
shape`. The fixture went from REFUSED to ALLOWED the moment the parent's loop
replaced its per-line reader with `split_segments`.

Reproduced directly against `hooks/guard.py` before this fix:

```
python3 -c "
import sys; sys.path.insert(0,'hooks'); import guard
print(guard.split_segments('# the driver\'s shape\nwhile true; do sleep 5; done'))
"
```

This returned one segment holding the whole text. Two segments were expected.
The cut falls on the following `;` and `\n`.

`hooks/test_guard.py:split_segments_comment_case` carries the fixed cases. It
was run RED against the pre-fix `split_segments`, before the patch landed. It
was run GREEN after.

## The predicate

The predicate is the shell's own rule. Nothing here is shape-specific. An
unquoted `#` that STARTS A WORD opens a comment. It runs to the end of its
line. "Starts a word" means the character is at index 0. It can also mean the
previous character is a space, a tab, a newline, or one of `|`, `&`, `(`. It
can also mean the previous character is `;`.

`fix#3` and `'#300'` stay non-comments under this rule. The `#` in `fix#3`
follows a letter. The `#` in `'#300'` sits inside a quote, and the earlier
quote-tracking already protects it.

The fix is a lifted copy. It is not a re-derivation. `shell_parse.py` in
`~/Developer/pkmnscan/scripts` carried this exact three-branch addition
already. That file wrote and measured the addition first. This change copies
it into `hooks/guard.py:split_segments` unchanged in substance. pkmnscan's own
copy threads a `delimiters` parameter that `hooks/guard.py`'s version does not
have. This change does not add that parameter.

## Holes, named

- `hooks/guard.py:_run_dir` reads `cd` with a regular expression over the raw
  command string. That regex can match a `cd` sitting inside a quoted script
  body, such as a heredoc body or a quoted `-c` argument. It then reads that
  match as a real directory change. Banchi's `shell_parse.py` avoids this. It
  reads `cd` off parsed tokens instead of the raw string. This is a known
  defect in `_run_dir`. It is not fixed here. The fix touches a function this
  change's brief put out of scope. A second builder lane is editing
  `guard.py` at the same time. This entry records the debt so it is not lost.
  It does not resolve the debt.
- The comment rule is unmeasured against every quoting shape a real shell
  accepts. `split_segments` does not model `$'...'` ANSI-C quoting. It does
  not model `$(...)` or backtick command substitution either, comment or no
  comment. This fix changes nothing about that pre-existing gap.

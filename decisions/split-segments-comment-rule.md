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
line. "Starts a word" means that the character is at index 0. It can also mean the
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

## `_run_dir` debt: paid, 2026-09-20

The debt below is paid. `hooks/guard.py:_run_dir` no longer reads `cd` and
`git -C` with `CD_RE` / `GIT_C_RE` over the raw command string. It now
splits the command into segments with `split_segments`. That is the same
quote- and comment-aware reader this file's fix uses. Each segment is
tokenized with `segment_tokens` (shlex). A segment counts as a `cd` or a
`git -C` only when `resolve_command` says that word is the segment's OWN
command. That is the same reader `LOOP_KEYWORDS` and `COMMAND_WRAPPERS`
already use elsewhere in this file. The approach is a lifted copy of
`~/Developer/pkmnscan/scripts/shell_parse.py`. That file paid this exact
debt first. It reads `cd` off parsed tokens instead of a raw-text regex.
Its own comment says so.

MEASURED before the fix, against `hooks/guard.py` on `main` (1c62a6e):

```
cmd1 = "bash -c 'true; cd /elsewhere; rm -rf x'; some_destructive_call"
guard._run_dir(cmd1, "/Users/shivinate/real-tree")
# -> "/elsewhere"   (WRONG: the cd never runs; it is text inside a quoted -c argument)

cmd2 = "# note; cd /elsewhere\nsome_destructive_call"
guard._run_dir(cmd2, "/Users/shivinate/real-tree")
# -> "/elsewhere\nsome_destructive_call"   (WRONG, twice over: the cd sits inside a
#    comment, and CD_RE's capture group also runs past the newline into the next line)
```

Both cases needed a `cd` preceded by `;` in the raw text. `CD_RE` only fires
when `cd` follows start-of-string or one of `;&|`. A `cd` after a plain
space, such as `# cd /elsewhere` with nothing before it, was already safe by
accident. A `cd` after a semicolon, quoted or commented, was not.

MEASURED after the fix, same two commands, same call:

```
guard._run_dir(cmd1, "/Users/shivinate/real-tree")  # -> "/Users/shivinate/real-tree"
guard._run_dir(cmd2, "/Users/shivinate/real-tree")  # -> "/Users/shivinate/real-tree"
```

Both now resolve to the shell's own cwd. Neither command holds a `cd` that
actually runs. A real `cd` and a real `git -C` were re-measured the same way.
Both are unchanged:

```
guard._run_dir("cd /a/b; echo hi", "/x")                     # -> "/a/b"
guard._run_dir("git -C /a/b status", "/x")                   # -> "/a/b"
guard.command_root("git --work-tree=/a -C /b status", "/x")  # -> "/a"
```

The last line confirms `--work-tree` still outranks `-C` and `cd`
(hooks/guard.py:710-716's documented precedence). `GIT_WORK_TREE_RE` was not
touched. The recorded debt named only `_run_dir`'s `cd`/`git -C` reading,
not `command_root`'s `--work-tree` reading.

`python3 hooks/test_guard.py` stayed green throughout. It read 498 of 498
before this entry's test additions and 500 of 500 after (see next section).

## Two bypasses, found in review, fixed 2026-09-20

The first token-based `_run_dir` (commit 42b4ca2) opened two guard bypasses.
A reviewer reproduced both. The requester reproduced both again, on their
own. Both used real fixtures: `cwd` a real dirty checkout, a second real
clean checkout named by the command text. Both bypasses let a real `git
reset --hard HEAD` through against the shared dirty tree. `_run_dir` read
the CLEAN checkout as the subject. It never asked what tree the command
actually ran in.

**Bypass 1: an attached `-C<path>`.** `_segment_git_c_target` treated any
token starting with `-C`, longer than two characters, as `git -C <path>`.
It then stripped the prefix and read the rest as the target. Real git
rejects that spelling. MEASURED against the real binary: `git
-C/tmp/probe/clean status` and `git -C=/tmp/probe/clean status` both fail.
Each prints `unknown option: -C/tmp/probe/clean` (or `-C=...`). Neither
runs. Only the spaced form, `git -C <path>`, is accepted. The attached-form
branch is removed. Only an exact `-C` token, followed by the next token, is
now read as a `-C` target.

MEASURED end to end, before and after, with `cwd` a real dirty checkout and
`/tmp/probe/clean` a real clean one:

```
git -C/tmp/probe/clean status; git reset --hard HEAD
# before: ALLOW (WRONG — the reset ran in the dirty cwd; subject read as clean)
# after:  DENY  (right — -C/tmp/probe/clean names no tree; subject is the dirty cwd)
```

**Bypass 2: a `cd` inside an interpreter heredoc body.** `strip_heredoc_bodies`
keeps an interpreter heredoc's body (`python3 <<'EOF' ... EOF`) under
inspection on purpose. The interpreter may execute it. `_run_dir` then read
a `cd` line inside that body as a live segment. A `cd` inside such a body
moves the INTERPRETER's own directory. It never moves the OUTER shell's
cwd, which is the question `_run_dir` answers. A new
`_strip_heredoc_bodies_unconditionally` now strips every heredoc body,
interpreter or not, before `_run_dir` splits the command into segments.
Every other caller of `strip_heredoc_bodies` is untouched. Their own
question still needs the interpreter body kept.

MEASURED end to end, before and after, same two checkouts:

```
python3 <<'EOF'
cd /tmp/probe/clean
EOF
git reset --hard HEAD
# before: ALLOW (WRONG — the reset ran in the dirty cwd; subject read as clean)
# after:  DENY  (right — the heredoc's cd never moves the outer shell)
```

Both shapes are now pinned end to end, in the guard's own PreToolUse JSON
contract, in `hooks/test_guard.py` (`run-dir bypass: ...`, two cases). Both
were confirmed RED against commit 42b4ca2 before the fix landed. Both are
GREEN after. `python3 hooks/test_guard.py` reads 502 of 502 with the fix in
place.

`--work-tree` precedence over `-C` and `cd` (hooks/guard.py:710-716) was
re-measured after both fixes. It is unaffected:

```
git --work-tree=/a -C /b status  # command_root -> "/a", unchanged
```

**`cd -` now resolves to no target.** The old regex resolved it to
`<shell_cwd>/-`, a nonsense path built from the literal string `-`. This is
not a defect. `cd -` returns the shell to its PREVIOUS directory. This
guard has no way to know that directory. Reading no target, and falling
through to the shell's own cwd, is the fail-open answer, not a wrong one.

## Holes, named

- `_run_dir`'s token reader still cannot see everything a real shell can.
  `split_segments` does not model `$'...'` ANSI-C quoting. It does not model
  `$(...)` or backtick command substitution. It also cannot see a `cd`
  whose target only exists after variable expansion: `cd "$DIR"` resolves
  to the literal string `$DIR`, not the directory it would expand to at
  runtime. A `cd` hidden inside one of those forms is invisible to this
  reader, the same way it was invisible to the old regex. The direction is
  fail-open: the hidden `cd` is skipped, not misread as a literal path.
  This is unmeasured against pkmnscan's own gaps in the same areas.
  `shell_parse.py`'s own docstring does not claim to close them either.
- The two bypasses above were MEASURED, in review, against real fixtures.
  They are not hypotheticals like the gaps just named. Both are fixed. Both
  are pinned end to end as of this update. A future spelling this reader
  accepts, but real git or the outer shell rejects, is the same class of
  defect. It belongs here the same way, MEASURED against the real binary
  first.
- The comment rule itself stays unmeasured against every quoting shape a
  real shell accepts, as recorded above before this update. This fix
  changes nothing about that pre-existing gap.

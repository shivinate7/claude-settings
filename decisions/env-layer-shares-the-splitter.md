# The environment layer shares the splitter

`hooks/guard.py:env_refusal` cut the command into segments with its own regex,
`SEGMENT_BREAK`. That regex was not quote aware. It is deleted. `env_refusal` now uses
`split_segments`, the same reader the rest of the guard uses, and then sub-splits each
segment on a lone `&`.

## The defect, measured

`SEGMENT_BREAK` broke on `|` wherever it appeared, quoted or not. A quoted pipe
therefore cut a word in half, and the tail of that word could end in `.env`.

MEASURED against `hooks/guard.py` on main, before this change:

```
grep "a|.env" file     -> DENIED   (WRONG: the pipe is inside quotes, no file is named)
ls & cat .env          -> DENIED   (right)
ls && cat .env         -> DENIED   (right)
```

The first line is a false refusal. The command names no environment file. It searches
for the text `a|.env` inside a file called `file`. `SEGMENT_BREAK` split that command
at the quoted pipe. The second half, `.env" file`, then read as a segment whose first
word names the environment.

MEASURED after this change, same three commands:

```
grep "a|.env" file     -> ALLOWED
ls & cat .env          -> DENIED
ls && cat .env         -> DENIED
```

The false refusal is gone. Both real refusals stand.

## The second false refusal, found in review

A probe compared the old and the new `env_refusal` over 31 commands. They differ on two.
The quoted pipe above is the first. The second is a comment-only line:

```
# cat .env     -> DENIED before, ALLOWED now
```

That line runs nothing. The shell reads it as a comment. `SEGMENT_BREAK` had no comment
rule, so the text inside the comment read as a live command. `split_segments` carries
the shell's own comment rule, which is why the new reader is right here.

The comment rule does not cost a refusal. MEASURED, all against the new code:

```
# a note\ncat .env                -> DENIED   (the second line is live)
# the driver's shape\ncat .env    -> DENIED   (an apostrophe no longer opens a quote)
echo hi # note\ncat .env          -> DENIED
cat .env # trailing note          -> DENIED
echo '#' ; cat .env               -> DENIED   (a quoted # is not a comment)
fix#3 ; cat .env                  -> DENIED   (# after a letter is not a comment)
echo fix#3                        -> ALLOWED
echo '#300'                       -> ALLOWED
```

The apostrophe case is the defect `split-segments-comment-rule` was written for. This
layer now inherits that fix rather than carrying its own gap.

The other 29 probe cases agree exactly, old and new. No refusal was lost. That set
covers an `&` inside single and double quotes, an `&` with no surrounding space, and a
trailing `&`. It covers `&>` and `>&`, a heredoc body, and command substitution in both
spellings. It also covers a shell variable holding the path, the `--env-file` flag, and
the near-miss names `foo.env`, `.env.local` and `.environment`.

## Why a false refusal is worth a change

CLAUDE.md: "A guard that goes red when nothing is wrong is spent, because the reader
learns to scroll past it." A refusal the owner learns to override is worse than no
refusal, because it teaches the override. This layer refuses a shape the owner meets
often, a search whose pattern holds a pipe.

## Why the sub-split is needed

`split_segments` does not break on a lone `&`. The rest of the guard does not need it
to. This layer does. A background job is its own command, and `ls & cat .env` runs two
of them.

Without the sub-split the whole line reads as one segment. The command word then reads
as `ls`. The `.env` in the line is judged against the wrong command.

The sub-split breaks on `&` only when it stands alone. It leaves `&&`, `&>`, `>&`, `<&`
and `|&` intact. Each of those is one operator, not a job separator.

`env_refusal` keeps its own word split. It does not move to `shlex`. Backslashes carry
meaning in the paths this layer reads, and `shlex` consumes them.

## The guard on the guard

`hooks/mutate_guard.py` carries a new mutant that removes the sub-split. Its required
case is `ls & cat .env`.

MEASURED: against the pre-fix code, in an isolated copy outside the shared tree, the
mutant reads RED at 1 of 531. The one failure is the required case. It proves the fix
it targets, and nothing else. CLAUDE.md: "Trust a guard only once it goes red on the
defect it guards."

## What this borrows, and from where

This is the second time `split_segments` has replaced a narrower reader in this file.
The first is recorded in `split-segments-comment-rule`, the entry that gave
`split_segments` the shell's own comment rule. An apostrophe inside a `#` comment had
swallowed the rest of a command. That entry also records `_run_dir` moving off its own
`CD_RE` and `GIT_C_RE` regexes onto the same reader.

The pattern is the same each time. One quote-aware and comment-aware reader serves the
whole file. A layer that needs a different cut adds its own step ON TOP of that reader,
as the sub-split does here. It does not write a second reader.

The holes named in `split-segments-comment-rule` carry over unchanged. `split_segments`
still does not model `$'...'` quoting, `$(...)` substitution, or backticks. An `&`
hidden inside one of those forms is invisible to this sub-split. It was invisible to
`SEGMENT_BREAK` too. This change closes no hole there and opens none.

## The other three cuts in the same change

Three merges ride with this one. None changes a verdict.

`_strip_heredoc_bodies_unconditionally` merges into
`strip_heredoc_bodies(cmd, keep_interpreter_bodies=True)`. `_run_dir` passes `False`,
which is the unconditional strip it needed. Every other caller takes the default. Each
one keeps an interpreter body under inspection, as before.

`log_cut` and `log_path` merge into `log_field(text, limit, mark, head=False)`.
`cap_safe` stays separate. It answers a different question, and
`hooks/config_watch.py` and the cap fixtures pin it.

`hooks/mutate_lib.py` now holds what both mutation harnesses copied. That is
`safe_name`, `job_count`, the suite runner, the SURVIVED and WRONG CAUSE and KILLED
verdict loop, the tally, and the stale-anchor precheck. Each harness passes its own
`run_one`.

The `lint/rule_mechanisms.json` refs for the needles SURVIVED and WRONG CAUSE point at
the shared file now. The two rules they mechanize therefore resolve to the code that
emits them.

The three or four field tolerance in `mutation_parts` is dropped. A malformed entry now
fails loudly. It is no longer read as a shorter one.

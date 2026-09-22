# The new source-prose mode ships dark

CLAUDE.md says: "A guard that goes red when nothing is wrong is spent,
because the reader learns to scroll past it." This entry names why
`ste_lint.py`'s new comment-and-docstring mode stays off by default. It also
names what turning the mode on will cost.

## The measurement

A naive Markdown-style lint of every tracked `.py` and `.sh` file reports
1222 errors. 718 are STE001, the sentence-length rule. 486 are STE006, the
forbidden semicolon. 18 are other rules.

Most of that count comes from the linter reading code as prose. It is not a
real writing problem.

## Two false-positive shapes

First shape: a semicolon inside a string literal.

```
cmd[index - 1] in " \t\n;|&("
```

This line sits in `hooks/guard.py`. A naive lint reports STE006 on it. The
semicolon never reaches a reader. It sits inside code.

Second shape: a comment block stitched to the code line beside it. A naive
lint reads both as one sentence. It then reports a count near 70 words, for
a run that holds no sentence that long.

## What ships

`ste_lint.py` gains a `--source-prose` flag and a `check_source` method.
Neither runs unless a caller asks for it. Every existing caller keeps
today's Markdown-only behavior, byte for byte.

Python comments come from `tokenize`'s COMMENT tokens. Docstrings come from
`ast`, at module, class, and function scope. Neither one ever looks inside a
string literal. The first false-positive shape cannot happen here.

Shell comments come from a small scanner that tracks quote state, one line
at a time. It does not follow a quoted string across a line break. That
limit is named, and accepted, in place of a full shell parser.

Line numbers stay real. A finding on a docstring line points at that line
in the source file. It never points at an offset inside extracted text.

`actions/ste-lint/action.yml` gains a `changed_paths` input, in the same
style as `paths`. A caller can now point the changed-scope diff at source
files instead of Markdown. Its default, `*.md`, matches today's hardcoded
value. An existing caller sees no change.

## The real debt

Comments and docstrings only, across this repository's tracked `.py`
files, held 275 errors by the count that ordered this work.

A rerun today, against the finished checker, counts 564 errors. 486 are
STE001. 72 are STE006. 4 are STE007. 2 are STE008. The two counts disagree,
and this entry does not smooth that over.

A likely cause: a sentence often wraps across several comment or docstring
lines. Those lines must join into one sentence first. Only then does a word
count mean anything, the same way a Markdown paragraph joins wrapped lines.
A count that treats each physical line as its own sentence would miss most
of the long ones this repository carries. `hooks/guard.py` alone holds
sentences of 37, 41, 36, and 72 words, each inside one docstring.

Either count leaves real, large debt behind. Turning `--source-prose` on as
a gate today would fail on work nobody wrote this week. The outcome
CLAUDE.md warns against would follow at once. A guard that is red from its
first run teaches its own reader to stop reading it.

## What turning it on will cost

Someone must clear 275 to 564 real sentences and semicolons first. The
exact number depends on which count a maintainer trusts. That cleanup is a
separate job from this one. Mixing it with the gate would bury the gate in
noise on the day it ships.

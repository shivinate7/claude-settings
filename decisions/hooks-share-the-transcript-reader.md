# Hooks share the transcript reader

Four hooks each carried their own copy of the same transcript readers. The copies are
now one module, `lint/_transcript.py`. It holds `read_transcript`, `is_last_human`,
`tool_uses`, `records_after_last_human`, `paragraph_blocks` and `format_finding`.
`lint/md_sweep.py`, `lint/ste_gate.py`, `lint/report_gate.py` and
`hooks/config_report.py` import it.

## The sentence this retires

The governing entry is `a-gates-allow-list-is-the-constant`, the scope section that
names three copied helpers. Its sentence, verbatim:

> It is copied so each Stop hook stays in one file, with no import between two hooks
> fired by the same event.

`lint/ste_gate.py:64` carried the same claim in its own words. So did
`lint/md_sweep.py:116`. This change rewrites those two code comments.

It does not touch the sentence in `a-gates-allow-list-is-the-constant` itself.
That entry is an argument, and the owner repeals an argument, not a lane. The
proposed repeal waits for the owner's word. Until then the entry and the code
disagree, and this paragraph is the record of that gap.

## What this change measured

The sentence was already false when this change started. The reads below show that. `hooks/config_report.py`
imports `lint/report_gate.py` today. Its own docstring says so, at lines 32 to 44 of
the file before this change. Line 35 names `report_gate.block_text` as the reader it
reuses. Lines 42 to 44 record that the import of `report_gate` pulls in that module's
own import of `hooks/guard.py`. `lint/report_gate.py` in turn imports `lint/ste_gate.py`
for `last_reply`. Three of the four hooks were therefore already linked by import
before this change. Only the fourth, `lint/md_sweep.py`, stood alone.

The docstring lines 42 to 44 also claim that `hooks/config_report.py` avoids
`lint/ste_gate.py`. That claim was already wrong for the same reason, through
`report_gate`. This change does not repair that sentence. It is named here as a known
error in the docstring.

The cut is 167 duplicate lines removed against 115 added. 93 of the added lines are the
new shared module.

## The outcome the old sentence protected

The old sentence protected one outcome. One bad edit must mute one reporter, never all
four. A Stop event fires several hooks. A shared file carries a risk. A syntax error or a bad
import in that file can silence every one of them at once. The owner then gets no
report at all, and does not learn that a report is absent.

## What protects that outcome now

Two mechanisms, not a comment.

Each hook keeps its own fail-open `try`/`except` in `main`. An import error or a raised
exception inside one hook exits 0 and prints nothing. It does not take the sibling hooks
down with it, because each hook is its own process.

`lint/test_gates.py` runs each gate as a subprocess. An import error in
`lint/_transcript.py` therefore shows as a failure in the gate suite, and the gate suite
runs in CI. The suite reads 97 tests green after this change, and it covers all four
hooks.

## The accepted risk

One bad edit to `lint/_transcript.py` that still passes CI can mute all four reporters at
once. The fail-open path is what makes this quiet. A hook that fails open prints nothing,
and nothing is also what a clean turn prints. The reader cannot tell the two apart.

The owner accepts this risk. This change does not close it. The trade is 167 lines of copy against one shared
file with a CI gate on it. No measurement here shows how often a bad edit passes CI.
This entry reports that number as unmeasured.

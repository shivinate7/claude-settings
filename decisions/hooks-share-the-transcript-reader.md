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

The owner repealed that sentence on 2026-09-21, and the repeal lands in this
branch. The scope rule in that entry survives. Only the example went, because
the example is measured false. The orchestrator proposed the repeal first and
did not land it alone.

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

Two mechanisms, not a comment. Neither one is the fail-open path, and the first
draft of this entry claimed wrongly that it was. The correction is recorded below.

`lint/test_gates.py` runs each gate as a subprocess, at line 58. An import error in
`lint/_transcript.py` therefore shows as a failure in the gate suite, and the gate
suite runs in CI. The suite reads 97 tests green after this change, and it covers all
four hooks. A reviewer broke the import for real, in a scratch copy of the tree, and
measured the suite at 76 failures and 18 errors. The guard goes red on the defect it
guards.

A break in the shared module is also LOUD, not quiet. The same reviewer ran
`hooks/config_report.py` directly against the broken module. It exited 1 and printed a
Python traceback. The shared import sits at the top of each hook file, above `main`.
The fail-open `try` and `except` inside `main` never sees an import-time error. The
owner therefore gets a visible failure, not silence.

## The correction

The first draft of this entry made a false claim. It said that each hook's fail-open
`try` and `except` catches an import error, and that the hook then exits 0 and prints
nothing. The measurement above is what shows the claim false. The `try` and `except` in `main` guards
the code that `main` calls. It cannot guard an import that already ran.

The fail-open path still does its own job. It catches a bad transcript, a missing file
or a parse error inside a running hook. The hook then exits 0 and prints nothing. That
is the case it was written for. This change does not touch it.

## The accepted risk

One bad edit to `lint/_transcript.py` that still passes CI can break all four reporters at
the same time. Before this change it could break only one.

The risk is smaller than a silent mute, because the break is loud. Each hook is its own
process. A broken import takes that process down, and prints a traceback the owner reads.
The reader can tell a crash from a clean turn. The reader cannot tell a fail-open exit
from a clean turn, and that case is unchanged by this entry.

The owner accepts this risk. This change does not close it. The trade is 167 lines of copy
against one shared file with a CI gate on it. No measurement here shows how often a bad
edit passes CI. This entry reports that number as unmeasured.

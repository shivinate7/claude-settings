# The predicate is the act, not the shape

CLAUDE.md says: "Fix the cause, not the symptom." It also says: "Check whether the
primitive exists before building a workaround." This entry records why the markdown
sweep stopped reading command text, and what that rule means for the next gate.

## What the shape list was for

`lint/ste_gate.py` runs before a tool call. It sees a `Write`, an `Edit`, or a
`MultiEdit` on a markdown path. A markdown file written through Bash never passes
through those tools. A heredoc, a `>` redirect, and a `sed -i` all skip the gate.

`lint/md_sweep.py` was built to close that hole at the end of the turn. Its first
form read the Bash command text and matched write SHAPES. It then grew shape by
shape. The list held a heredoc, a redirect, `sed -i`, `perl -i`, `ruby -i`, `tee`,
`mv`, `cp`, and `dd`. It also held an `awk` program redirect, a `python -c` open
call, a `pathlib` write, a `node -e` `fs` call, and a `perl -e` open. Each shape
was a real write that the earlier version missed.

## Why a shape list is the wrong mechanism

The list can only grow. It can never close.

MEASURED 2026-09-19: `python3 gen.py` was invisible to the sweep. The shape code
read a python `-c` string and nothing else. `bash gen.sh` was invisible. So was
`pandoc -o notes.md`. So was `npx prettier --write x.md`. The hole was not one
shape. The hole was the class "any program not on the list".

A list of shapes is a list of the ways people were seen to write a file. It is a
record of the past. The next tool is not on it. Adding `python3 <file>.py` to the
list would have moved one item out of the hole and left the class untouched.

The sweep also carried helper functions copied from `hooks/guard.py` to parse shell
text. That is a shell parser inside a linter. The cost of the wrong predicate was
not only the misses. It was the parser.

## What replaces it

The filesystem already answers the question. A file that was written has a new
mtime. The primitive existed.

The new predicate: a markdown file under the turn's working directory, with an
mtime newer than the last human message, and dirty against HEAD.

The last human message carries an ISO timestamp in the transcript. That is the
start of the turn. The git check removes the one large false positive. A `git pull`
or a branch switch during the turn rewrites many markdown mtimes, and those files
stay clean against HEAD.

## What the new predicate costs

Named here rather than hidden. Every predicate has holes. An honest entry lists them.

- A turn whose last human record carries no timestamp gives no baseline. The sweep
  then does nothing.
- A file written this turn whose content matches HEAD is clean. The git filter
  drops it.
- Another agent writing markdown into the same checkout is read as this turn.

These are three known cases. The old predicate had one open class.

## The rule this sets

Judge a guard by the act it must catch, never by the spelling of the act. When a
gate needs a list of shapes, the predicate is wrong. Look for the primitive that
records the act itself.

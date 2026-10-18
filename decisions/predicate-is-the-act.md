# The predicate is the act, not the shape

## The ruling

Judge a guard by the act it must catch, never by the spelling of the act. When a gate needs a list of
shapes, the predicate is wrong. Look for the primitive that records the act itself. Reason: a list of
shapes records the ways people were seen to write a file. It can only grow and can never close.

The markdown sweep (`lint/md_sweep.py`) catches a markdown file written through Bash, which skips the
`Write`, `Edit` and `MultiEdit` gate in `lint/ste_gate.py`. It does not read command text. Its predicate
is a markdown file under the turn's working directory, with an mtime newer than the last human message,
and dirty against HEAD.

- The last human message carries an ISO timestamp in the transcript. That marks the start of the turn.
- The git check removes the large false positive: a `git pull` or a branch switch rewrites many
  markdown mtimes, and those files stay clean against HEAD.

Named limits:

- A turn whose last human record carries no timestamp gives no baseline. The sweep then does nothing.
- A file written this turn whose content matches HEAD is clean. The git filter drops it.
- Another agent writing markdown into the same checkout is read as this turn.

Kind: process
Home: lint/md_sweep.py

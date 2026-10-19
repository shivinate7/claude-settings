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

Measured 2026-09-19 against `hooks/guard.py`: a cap lift to `.claude/settings.local.json` drew an ask
from the Write tool, a `>` redirect, a heredoc, `tee` and `jq ... > file`. It was ALLOWED from `cp`,
`mv`, `sed -i`, `python3 -c "open(path,'w')"`, `python3 gen.py` and `bash gen.sh`: the value sits in
another file or a script, so no list of write commands closes the gap. `hooks/config_watch.py` hashes
the file instead.

Measured 2026-09-20: `guard._cap_reading('"_subagentCapUntil": "2026-09-21T00:00:00Z"')` returns `{}`, so
the guard never sees the expiry field and only the watch reads it.

Kind: process
Home: lint/md_sweep.py

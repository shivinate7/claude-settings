# The silent-undo check flags a rename that main edited

**What waits.** `lint/check_silent_undo.py` goes red when a PR renames a file and main edits the
old name. Git merges this case clean. The check reads with `--no-renames`, so the renamed file
looks new, and main's edit looks lost.

**Why it waits.** It is the one false alarm a reviewer found in 17 probes on 2026-10-02. A
`Drops-lines: <path> -- <reason>` trailer passes it, and the trailer prints for the reviewer.

**What keeps it from being lost.** The check's decision record lists it under known limits.

**Trigger.** When it fires on a real merge, fix it. Read renames with `-M` for the PR side
only, and map main's edits onto the new path.

# c35. ste-lint's audit step stops importing Python files from the linted repo

Checked claude-settings main at 987f682. Source: security scan finding, Oct 21
(claude.ai/security/findings/find_01GxVuZJgUrxVcwEbj5qLfgn). Confirmed by hand on Python 3.13.

Cause: actions/ste-lint/run.sh cds to the linted repo's root (line 9), then in scope 'all' runs
`python3 -c 'import json, sys; from ste_emit import emit; ...'` (line 131). Under `-c`, Python puts
the current directory first on sys.path, ahead of PYTHONPATH and the standard library. A json.py,
json/ package or ste_emit.py at the linted repo's root runs in place of the real module. The other
three python3 calls in run.sh run script files (the linter, HUNK_MAP_PY, SPLIT_PY), so sys.path[0]
is the script's own folder, not the repo; they are safe.

Brief, claude-settings (small lane, next batch):
1. Move the line-131 summary into a script file written next to ste_emit.py in $EMIT_DIR, the same
   way HUNK_MAP_PY and SPLIT_PY already work, and run it with `python3 "$EMIT_DIR/summary.py" ...`.
   Do not use `-I` (it drops PYTHONPATH, so ste_emit stops loading) or `-P` (needs 3.11+).
2. Add a case to actions/ste-lint/test_action.py: fixture repos with json.py, or json/__init__.py, plus ste_emit.py at the root, each
   writing a marker file, plus one .md file. Run with SCOPE=all and SCOPE=changed. Pass: no marker
   file, and the summary table and annotations still appear. Show it red on main, green after 1.
3. Add one sentence to action.yml's scope description: the action runs no code from the linted tree.
Report: files changed, the test red then green.

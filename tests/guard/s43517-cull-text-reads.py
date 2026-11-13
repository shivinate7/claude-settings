# section 43517
# gh-write-cloud cases for a heredoc body that names a gh write. A program that reads the body as input, such as
# `python3 -c` or a python script file, runs no gh write, so the body is data and is allowed. A body that bash runs,
# through a bash heredoc, `bash -c`, a python that runs its stdin through the shell, or an unquoted delimiter with a
# `$(...)` or backtick, is a real run and stays refused. The allowed cases stop a note that quotes a gh command from
# being refused as a write; the refused cases stop that allowance from opening a real write.
FAMILY = "merge"

# A heredoc body is data when the program it feeds reads it as input. `python3 -c` and a python script file take the
# body on stdin, and a program that only prints it runs no gh write. The red cases are refused on main and allowed
# by the right reading.
GH_TEXT_BODIES = (
    ("python -c prints its stdin, body names gh pr create",
     "python3 -c \"import sys; print(sys.stdin.read())\" <<'EOF'\ngh pr create --draft --title x\nEOF"),
    ("python -c prints its stdin, body names gh api -X POST",
     "python3 -c \"import sys; print(sys.stdin.read())\" <<'EOF'\ngh api -X POST repos/x/y/issues -f title=x\nEOF"),
    ("python script file reads its stdin, body names gh pr comment",
     "python3 tools/post_note.py <<'EOF'\ngh pr comment 12 --body hi\nEOF"),
)
for _name, _command in GH_TEXT_BODIES:
    sh("gh-write-cloud: [cull-text-reads] heredoc, %s, is allowed in a cloud session" % _name, _command,
       "allow", cwd=NOGIT, env=GH_WRITE_CLOUD)

# Green controls: each stays refused in a cloud session on main, and after the fix. A body that bash runs is a run.
# A python -c that runs its stdin through the shell is a run too, so the stdin reading must not cover it.
GH_RUN_CONTROLS = (
    ("bash heredoc body runs gh pr create", "bash <<'EOF'\ngh pr create --draft --title x\nEOF", "gh pr create"),
    ("bash -c runs gh api -X POST", "bash -c 'gh api -X POST repos/x/y/issues -f title=x'", "gh api -X"),
    ("gh api -X POST, a real run", "gh api -X POST repos/x/y/issues -f title=x", "gh api -X"),
    ("python -c runs its stdin through the shell, body names gh pr create",
     "python3 -c \"import os, sys; os.system(sys.stdin.read())\" <<'EOF'\ngh pr create --draft --title x\nEOF",
     "gh pr create"),
)
for _name, _command, _lacks in GH_RUN_CONTROLS:
    sh("gh-write-cloud: [cull-text-reads] control, %s, is refused in a cloud session" % _name, _command,
       "deny", GH_WRITE_RULE, cwd=NOGIT, env=GH_WRITE_CLOUD, carries=GH_WRITE_REMEDY, lacks=(_lacks,))

# An UNQUOTED heredoc delimiter lets bash run each `$(...)` and backtick in the body while it writes the body.
# A python that only reads the body does not change that, so a gh write in one of those is a run and is refused.
GH_SUBSTITUTION_RUNS = (
    ("python -c prints its stdin, backtick body runs gh pr merge",
     "python3 -c \"import sys; print(sys.stdin.read())\" <<EOF\nRun `gh pr merge 12 --squash` next\nEOF",
     "gh pr merge"),
    ("python -c prints its stdin, $() body runs gh pr create",
     "python3 -c \"import sys; print(sys.stdin.read())\" <<EOF\n$(gh pr create --draft --title x)\nEOF",
     "gh pr create"),
    ("python script file reads its stdin, backtick body runs gh pr merge",
     "python3 tools/post_note.py <<EOF\nRun `gh pr merge 12 --squash` next\nEOF",
     "gh pr merge"),
)
for _name, _command, _lacks in GH_SUBSTITUTION_RUNS:
    sh("gh-write-cloud: [cull-text-reads] unquoted heredoc, %s, is refused in a cloud session" % _name, _command,
       "deny", GH_WRITE_RULE, cwd=NOGIT, env=GH_WRITE_CLOUD, carries=GH_WRITE_REMEDY, lacks=(_lacks,))

# Green controls: a quoted delimiter runs nothing, so the same bodies are data and stay allowed. An unquoted body
# that names gh in plain text, with no `$(` or backtick in it, runs nothing either.
GH_DATA_BODIES = (
    ("quoted python -c, backtick body names gh pr merge",
     "python3 -c \"import sys; print(sys.stdin.read())\" <<'EOF'\nRun `gh pr merge 12 --squash` next\nEOF"),
    ("quoted python -c, $() body names gh pr create",
     "python3 -c \"import sys; print(sys.stdin.read())\" <<'EOF'\n$(gh pr create --draft --title x)\nEOF"),
    ("quoted python script file, backtick body names gh pr merge",
     "python3 tools/post_note.py <<'EOF'\nRun `gh pr merge 12 --squash` next\nEOF"),
    ("unquoted python -c, plain body names gh pr merge, no substitution",
     "python3 -c \"import sys; print(sys.stdin.read())\" <<EOF\nRun gh pr merge 12 --squash next\nEOF"),
)
for _name, _command in GH_DATA_BODIES:
    sh("gh-write-cloud: [cull-text-reads] control, %s, is allowed in a cloud session" % _name, _command,
       "allow", cwd=NOGIT, env=GH_WRITE_CLOUD)

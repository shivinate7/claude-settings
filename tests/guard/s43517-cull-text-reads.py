# section 43517
# gh-write-cloud false alarm, measured by lane fan-prose-unmapped-1 (relayed 2026-11-12 11:50 CST): a heredoc whose
# body only names a gh write was refused as if it ran the write.
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

# section 43400
FAMILY = "heredoc-text"
#
# A guarded word that a heredoc body holds as text is text. Three guards refuse a command for its words:
# gh-write-cloud (step 5b), draft-pr (step 6b) and process-args (step 5c). Each RED case runs none of the
# words, yet is refused, for two reasons. A body is kept in view when another body in the same command runs.
# And the runner read takes a file that is only read as one that runs: `x=$(< n.md)` (the assignment word is
# skipped), `find .` (the `.` reads as source) and `env A=1 cat n.md` (env is a wrapper). Each GREEN case pins
# a form that must stay refused or allowed, so a fix that loosens a real run fails one of them.

# The word each guard refuses, the rule it names, the environment its run needs, and what its refusal
# carries and lacks. A cloud session is CLAUDE_CODE_REMOTE "true" (GH_WRITE_CLOUD, from the merge section).
# draft-pr is judged in a local session, so it takes no environment.
HEREDOC_TEXT = {
    "gh-write-cloud": ("gh pr ready 12", GH_WRITE_RULE, GH_WRITE_CLOUD, GH_WRITE_REMEDY, ("gh pr ready",)),
    "draft-pr": ("gh pr create --title x", "draft-pr", None, DRAFT_REMEDY, DRAFT_LACKS),
    "process-args": ("ps aux", "process-args", GH_WRITE_CLOUD, (), ("ps aux",)),
}

# RED. The body holds the guarded word as text, and no command runs that word, so each must be allowed.
HEREDOC_TEXT_RED = (
    ("two heredocs, a shell script that bash runs",
     "cat <<'A' > run.sh\necho hi\nA\ncat <<'B' > n.md\nGUARDED\nB\nbash run.sh"),
    ("two heredocs, a python script that python3 runs",
     "cat <<'A' > run.py\nprint('hi')\nA\ncat <<'B' > n.md\nGUARDED\nB\npython3 run.py"),
    ("a text file read by a command substitution, x=$(< n.md)",
     "cat <<'B' > n.md\nGUARDED\nB\nx=$(< n.md); echo $x"),
    ("a text file listed and cat'd by find -execdir",
     "cat <<'B' > n.md\nGUARDED\nB\nfind . -name n.md -execdir cat {} +"),
    ("a text file cat'd after env A=1",
     "cat <<'B' > n.md\nGUARDED\nB\nenv A=1 cat n.md"),
)

# GREEN, refused. Each runs the guarded word, runs a file that holds it, or is a substitution that bash
# runs in an unquoted body. An unclosed body runs to the end of input, so every line stays in view.
HEREDOC_TEXT_REFUSED = (
    ("source of the file the heredoc wrote", "cat <<'B' > n.md\nGUARDED\nB\nsource n.md"),
    ("the file the heredoc wrote, piped to sh", "cat <<'B' > n.md\nGUARDED\nB\ncat n.md | sh"),
    ("a bash heredoc whose body holds the word", "bash <<'EOF'\nGUARDED\nEOF"),
    ("a heredoc piped to sh", "cat <<'EOF' | sh\nGUARDED\nEOF"),
    ("the real command alone", "GUARDED"),
    ("the real command after a text-only heredoc", "cat <<'B' > n.md\nsome text\nB\nGUARDED"),
    ("an unquoted heredoc body with a backtick span holding the word", "cat <<B > n.md\n`GUARDED`\nB"),
    ("an unclosed heredoc", "cat <<'B' > n.md\nGUARDED"),
)

# GREEN, allowed. The word is text in each: a heredoc body, a message or a string, a comment, or after a lone quote.
HEREDOC_TEXT_ALLOWED = (
    ("a cat heredoc written to a file", "cat <<'B' > n.md\nGUARDED\nB"),
    ("a tee heredoc written to a file", "tee n.md <<'B'\nGUARDED\nB"),
    ("a python heredoc that prints the word", "python3 - <<'B'\nprint(\"GUARDED\")\nB"),
    ("a git commit message from a quoted heredoc", "git commit -m \"$(cat <<'EOF'\nGUARDED\nEOF\n)\""),
    ("a python triple-quoted string", "python3 - <<'B'\ns = \"\"\"\nGUARDED\n\"\"\"\nB"),
    ("a lone apostrophe, then # before the word", "cat <<'B' > n.md\ndon't # GUARDED\nB"),
    ("a lone apostrophe, then // before the word", "cat <<'B' > n.md\nit's // GUARDED\nB"),
    ("a # opening the body line", "cat <<'B' > n.md\n# GUARDED\nB"),
    ("a // opening the body line", "cat <<'B' > n.md\n// GUARDED\nB"),
)

for _guard, (_words, _rule, _env, _carries, _lacks) in HEREDOC_TEXT.items():
    for _label, _template in HEREDOC_TEXT_RED:
        sh("heredoc-text: %s, %s: the text-only word is allowed" % (_guard, _label),
           _template.replace("GUARDED", _words), "allow", cwd=NOGIT, env=_env)
    for _label, _template in HEREDOC_TEXT_REFUSED:
        sh("heredoc-text: %s, %s: the real run is refused" % (_guard, _label),
           _template.replace("GUARDED", _words), "deny", _rule, cwd=NOGIT, env=_env,
           carries=_carries, lacks=_lacks)
    for _label, _template in HEREDOC_TEXT_ALLOWED:
        sh("heredoc-text: %s, %s: the text is allowed" % (_guard, _label),
           _template.replace("GUARDED", _words), "allow", cwd=NOGIT, env=_env)

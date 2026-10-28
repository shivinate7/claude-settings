# c182: code-check keeps a renamed module on the mypy list

Branch: c182-codecheck-rename. Commit 60a01f7a is the first build: the rename rule plus the --main shrink check.
Round 1 review: changes needed. Being fixed now:
- the main check must compare against the merge-base, so a branch that is only behind main does not go red
- the remedy for a rename into an excluded folder must work
- the docstring must name the 50% similarity limit
Next: round 2 review, then a draft PR, then a message to the orchestrator.

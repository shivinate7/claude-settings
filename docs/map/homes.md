# Homes

A capability has one home. Read this page before you build a helper, and extend the home with a variant. A second copy needs a stated reason.

## Homes

- starting a child process with no console window — `hooks/_nowindow.py:run`
- the model call of a judge hook — `hooks/decision_watch.py:invoke_model`
- reading a JSON value by a dotted path, with a fan-out over a list — `lint/rule_audit.py:_walk`
- listing the copies of claude-settings skills in a child repo — `lint/find_copies.py:find_skill_copies`
- loading the typescript package for the map skill — `skills/plain-english-map/scripts/lib/lazy-typescript.mjs:load`
- reading source text with comments and strings blanked — `skills/plain-english-map/scripts/lib/source-text.mjs:blankCommentsAndStrings`

## Code files

- `skills/plain-english-map/scripts/lib/lazy-typescript.mjs` — Loads the `typescript` package for the map skill at its first use, and never at import.
  - The skill pins typescript to version ~5.8.2. — `package.json: dependencies.typescript = "~5.8.2"`

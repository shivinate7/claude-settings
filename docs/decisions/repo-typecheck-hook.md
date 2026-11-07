# A repo-declared typecheck after each edit

## The ruling

A repo declares its typecheck in its extras file, `.claude/layout-extras.json`, under the key
`typecheck`. claude-settings runs it after a Write, Edit or MultiEdit of a file that
matches one of its globs. Each matching entry runs, and their reports are joined. One home: `hooks/repo_typecheck.py`, read through `lint/layout.py`
`typecheck()` and `match_globs()`. No repo keeps its own copy.

```json
"typecheck": [
  {"globs": ["app/**/*.ts", "app/**/*.tsx"],
   "command": ["app/node_modules/.bin/tsc", "-p", "app/tsconfig.json", "--noEmit"],
   "timeout": 90}
]
```

- `command` is an argv list. It runs from the repo root, with no shell.
- The timeout is capped at 90 seconds.
- On a nonzero exit with output, the hook prints PostToolUse `decision: block` with the output as
  `reason`, so the model reads what it broke. The edit has landed already: PostToolUse cannot undo it.
- Every other outcome is silent: no match, no key, a missing compiler, a timeout, a bad extras file,
  or a defect in the hook. An advisory that fails a turn on its own bug gets muted.

## Why

A probe on 2026-11-03 showed that a project thread runs the claude-settings hooks but never a repo's
own `.claude/settings.json` hooks. Banchi's `scripts/typecheck-hook.py` gave the model its only
TypeScript signal, and in a project thread it never ran.

## Cost

- Host: the `config_watch.py` PostToolUse entry, which already runs on each write call. No new hook
  entry, no new process per tool call, no long-lived process, no timer.
- Each Write, Edit or MultiEdit: one read of `lint/layout.json`, one walk up from the edited file to
  find the extras file, and one read of it when found. No file is written. NotebookEdit never runs it.
- The cap watch's fast path now also imports `hooks/repo_typecheck.py` and `lint/layout.py`. Both use
  the standard library only.
- A process starts only when the edited file matches a declared glob: one per matching entry, bounded
  by its timeout.
- The config_watch entry timeout rose from 20 to 120 seconds, to fit a 90-second check.
- Cost cases in `hooks/test_repo_typecheck.py` prove both halves: no process on a non-match or a repo with no key,
  one process on a match.

## Known limits

- An edit made through Bash (`sed -i`) has no `file_path` and starts no check.
- In a session that also runs the repo's own typecheck hook, the check runs twice until the repo drops
  its own entry.

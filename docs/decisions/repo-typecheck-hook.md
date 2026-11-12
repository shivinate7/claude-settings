# A repo-declared typecheck after each edit

## The ruling

A repo declares its typecheck in its extras file, `.claude/layout-extras.json`, under the key
`typecheck`. claude-settings runs it after a Write, Edit or MultiEdit of a file that
matches one of its globs. The key sits beside the file's `kinds` object, which every extras file
holds. Each matching entry runs, and their reports are joined. One home: `hooks/repo_typecheck.py`, read through `lint/layout.py`
`typecheck()` and `match_globs()`. No repo keeps its own copy.

```json
"typecheck": [
  {"globs": ["app/**/*.ts", "app/**/*.tsx"],
   "command": ["node", "app/node_modules/typescript/bin/tsc", "-p", "app/tsconfig.json", "--noEmit"],
   "timeout": 90}
]
```

- `command` is an argv list. It runs from the repo root, with no shell. Name `node` and the
  compiler's script, never `node_modules/.bin/tsc`: on Windows that file is a shim a process cannot start.
- A glob is repo-relative. `**` crosses folders. Braces (`{ts,tsx}`, not nested) and classes (`[jt]`) are read,
  and a `./` prefix reads as the same path.
- A bad entry costs only itself. It is skipped, and one `noted` line in guard.log names the key.
- All matching entries share one 90-second budget.
- The block reason is capped in length.
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
- Each Write, Edit or MultiEdit: a few reads of `lint/layout.json`, one walk up from the edited file to
  find the extras file, and one read of it when found. No file is written, except one `noted`
  guard.log line per bad entry on each such edit under that repo. NotebookEdit never runs it.
- The cap watch's fast path now also imports `hooks/repo_typecheck.py` and `lint/layout.py`. Both use
  the standard library only. A bad entry also loads the guard.log writer.
- A process starts only when the edited file matches a declared glob: one per matching entry, all
  bounded by one 90-second budget.
- The config_watch entry timeout rose from 20 to 120 seconds, to fit a 90-second check.
- Cost cases in `hooks/test_repo_typecheck.py` prove both halves: no process on a non-match or a repo with no key,
  one process on a match.

## Known limits

- An edit made through Bash (`sed -i`) has no `file_path` and starts no check.
- The nearest extras file above the edited file is the repo root. A nested extras file with no
  `typecheck` key turns the check off below it.
- In a session that also runs the repo's own typecheck hook, the check runs twice until the repo drops
  its own entry.

Kind: build
Plan: docs/decisions/repo-typecheck-hook.md#the-ruling (all)

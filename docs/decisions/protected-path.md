# A repo names paths the guard keeps from writes

## The ruling

A repo lists paths that no session may write, in `.claude/layout-extras.json`. The claude-settings guard enforces the list. Owner ask ask-mw6vyc57pi part 2 (2026-11-07 14:58 CST); roadmap step `repo-protected-paths`.

- Shape: `"protected-paths": [{"path": "fixtures/", "why": "<the harm, one line>"}]`. `path` is repo-relative POSIX; a trailing `/` means the folder and all under it. No leading `/`, no `..`. `why` is required. Reader: `lint/layout.py` `protected_paths`. No key means the rule is off.
- Guard rule `protected-path` (`hooks/guard.py`; predicate `is_protected` and `protected_shell_hit` in `hooks/guard_frozen.py`). Denied: a Write, Edit, MultiEdit or NotebookEdit to a listed path; a shell write to one, through the frozen rule's scanner (`_shell_write_hit`, with a leading `cd` followed); a python or node script's own write (`interpreter_write_hit`). A read, a grep, an echo of the path, and a copy out are allowed.
- The list is that of the checkout that holds the target, never the session's cwd. A write from repo A into repo B's listed path is denied.
- A path matches per segment: `fixtures/` covers `fixtures/x/y.csv`, never `fixturesX/` or `src/fixtures.py`. The literal and the resolved (symlink) spellings both count.
- `touch` counts as a write (`MUTATING_COMMAND`), for this rule and every rule that reads that list, the frozen path's too.
- This rule alone also reads its own write forms (`PROTECTED_ONLY_WRITE` and `_protected_write` in `hooks/guard_frozen.py`, their one home): the `rsync` destination, `sed` or `perl` with an in-place option word, `find -delete` or `-exec` of a mutating command (a path it only excludes is not written), `git restore` without `--staged` alone, `git checkout` naming a path, and a python removal. It reads through a subshell's parens and the runners `ionice`, `stdbuf` and `flock`. Every other rule judges these as main did.
- The reason quotes the entry's `why`. It never prints a command that writes the path.
- A malformed key allows the call and writes one `noted` guard.log line for `protected-path`. One bad entry drops the whole list, not that entry alone.
- Override: the owner's typed `override` (decision `owner-override`) lifts one refusal.
- Incident class: named incident (rule `building-guard-needs-incident`). Probe in a banchi project thread, 2026-11-03 10:35 CST: banchi's own `.claude/settings.json` does not load there, so its `fixtures/` deny rule let a write through. The claude-settings guard did load. Mistake stopped: Claude edits or regenerates a fixture file while fixing a failing test. Harm: banchi's `fixtures/` holds real TCGplayer exports, the ground truth for the round-trip test; an edited fixture turns a real defect green.
- Scope: a deny rule a repo keeps in its own settings does not run in a project's cloud thread. This rule moves that kind of deny into the guard, which does.
- Cost:
  - Write family: one read of the target checkout's extras file per guard call, cached for the call. No process, no file written.
  - Bash: the extras file is read only when the command looks like a write (`PROTECTED_WRITE_HINT` in `hooks/guard.py`). A read-only command opens nothing. Check: the cost test in `hooks/test_guard_protected.py`.
  - No log line, except one `noted` line on a malformed key.
- Known limits: a write the scanner cannot see passes. That covers a path built at run time, such as `"$(git rev-parse --show-toplevel)/fixtures/a"` or `'fix' + 'tures/a'`, and a binary that writes a path it computes. On a case-insensitive file system (macOS), `FIXTURES/a` does not match `fixtures/`. The rule stops Claude's mistakes, not an attacker (decision `guard-guards-mistakes-only`).

Kind: build
Home: hooks/guard.py

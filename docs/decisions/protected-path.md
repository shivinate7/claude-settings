# A repo names paths the guard keeps from writes

## The ruling

A repo lists paths that no session may write, in `.claude/layout-extras.json`. The claude-settings guard enforces the list. Owner ask ask-mw6vyc57pi part 2 (2026-11-07 14:58 CST); roadmap step `repo-protected-paths`.

- Shape: `"protected-paths": [{"path": "fixtures/", "why": "<the harm, one line>"}]`. `path` is repo-relative POSIX; a path covers itself and all under it, with or without a trailing `/`. No leading `/`, no `..`. `why` is required. Reader: `lint/layout.py` `protected_paths`. No key means the rule is off. An extras file may hold this key alone, with no `kinds` object.
- A repo with a non-empty list also protects its extras file, so a session cannot edit the list away. The reason says so.
- Guard rule `protected-path` (`hooks/guard.py`; predicate `is_protected` and `protected_shell_hit` in `hooks/guard_frozen.py`). Refused: a Write, Edit, MultiEdit or NotebookEdit to a listed path; a shell write to one, through the frozen rule's scanner (`_shell_write_hit`, with a leading `cd` followed); a python or node script's own write (`interpreter_write_hit`). A read, a grep, an echo of the path, and a copy out are allowed.
- The list is that of the checkout that holds the target, never the session's cwd. A write from repo A into repo B's listed path is refused.
- A path matches per segment: `fixtures/` covers `fixtures/x/y.csv`, never `fixturesX/` or `src/fixtures.py`. The literal and the resolved (symlink) spellings both count.
- Write forms only this rule counts (`PROTECTED_MUTATING_COMMAND`, and `protected=True` through `writes_to` and `interpreter_write_hit`): `touch`, `rsync` (its destination), `unlink`, `shred`, `sort -o`, `sed --in-place`, `perl -pi`, `find` with `-delete` or a mutating `-exec`, and in python `os.remove`, `unlink`, `rmtree`, `Path.touch` and `joinpath`. No other rule (builder-test-edit, frozen-path, other-checkout) reads them: their verdicts stay as they were.
- The reason quotes the entry's `why`. It never prints a command that writes the path.
- `git restore <path>` and `git checkout [<tree>] [--] <path>` count as writes, even from HEAD or the index: a session cannot put back a listed file; the owner's override covers that rare restore (coordinator pick, 2026-11-07).
- A malformed key allows the call and writes one `noted` guard.log line for `protected-path`. One bad entry drops the whole list, not that entry alone.
- Override: the owner's typed `override` (decision `owner-override`) lifts one refusal.
- Incident class: named incident (rule `building-guard-needs-incident`). Probe in a banchi project thread, 2026-11-03 10:35 CST: banchi's own `.claude/settings.json` does not load there, so its `fixtures/` refusal rule let a write through. The claude-settings guard did load. Mistake stopped: Claude edits or regenerates a fixture file while fixing a failing test. Harm: banchi's `fixtures/` holds real TCGplayer exports, the ground truth for the round-trip test; an edited fixture turns a real defect green.
- Scope: a refusal rule a repo keeps in its own settings does not run in a project's cloud thread. This rule moves that kind of refusal into the guard, which does.
- Cost:
  - Write family: one read of the target checkout's extras file per guard call, cached for the call. No process, no file written.
  - Bash: the extras file is read only when the command looks like a write (`PROTECTED_WRITE_HINT`). A read-only command opens nothing. Check: the cost test in `hooks/test_guard_protected.py`.
  - No log line, except one `noted` line on a malformed key.
- Known limits: a write the scanner cannot see passes. That covers a path built at run time, such as `"$(git rev-parse --show-toplevel)/fixtures/a"` or `'fix' + 'tures/a'`, and a binary that writes a path it computes. On a case-insensitive file system (macOS), `FIXTURES/a` does not match `fixtures/`. The rule stops Claude's mistakes, not an attacker (decision `guard-guards-mistakes-only`).

Kind: build
Plan: docs/decisions/protected-path.md#the-ruling (all)
Home: hooks/guard.py

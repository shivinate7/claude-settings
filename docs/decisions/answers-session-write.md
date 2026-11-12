# A session never writes an owner answer on the waiting page

## The ruling

The guard refuses a session's write into the answers of the waiting page (rule `answers-session-write`). It is pick 2 of decision `waiting-page-one-store` (taken by the coordinator, 2026-11-12 11:43 CST, as an undoable pick).

- An answer is the owner's word. The page reads it as his grant, so a session that writes one forges a grant he never gave.
- Incident class: Claude writing an answer by mistake in normal work, for example while it tests another rule, or while it clears a page by hand. `SKILL.md` "Read the answers" said "this sentence is the only guard" before this rule.
- The rule judges three tools, through one path test and one field test in `hooks/question_form.py` (`is_answers_path`, `answers_write_hit`):
  - `ArtifactData`: any op but a read (`get`, `list`, `query`), alone or as an entry of a `batch`, whose `collection` is the answers collection (`lint/layout.py` `WAITING_ANSWERS`), or whose `collection`, `doc_id` or `path` lies under `answers/`. On any page url: a session has no right to forge an answer on any waiting page.
  - `Write` and `Edit`: a file under `waiting/answers/` or `waiting-data/answers/`, or under the layout's own waiting folder with `answers/` below it.
  - The shell: a redirect, `tee`, `cp`, `mv`, `rm` or `sed -i` that writes there (the frozen-path reader, `shell_write_hit`), and a `git add`, `commit`, `stage`, `rm` or `mv` that names the path (`answers_git_hit`).
- Passes: every read; a quoted, heredoc or commented mention; a sibling file (`waiting/items/`); a file only named answers; a collection named `answersx`; a doc_id `answers-note`. The writer's export copy step passes: its command line names no answers path.
- The refusal names the mistake and the fix (write a waiting item, let the owner answer on the page). It names no path around the rule.
- The owner's typed override lifts it, as any guard of Claude's mistakes (decision `guard-guards-mistakes-only`).

Known gaps, each a note and no debt yet:

- `git add waiting-data` (the whole folder) stays allowed: the writer's export copy stages that folder, and the copy stays live until step `retire-page-copy`.
- `export_page.py --rebuild` and `--merge` write answers batches. This rule refuses an `ArtifactData` write of them, and it does not special-case them. Open: the owner rules whether the page writer's rebuild may write answers.
- A write that builds the path from pieces in an interpreter, or by a shell variable set in another call.
- The page's own writes never pass the hook, so this rule cannot see them (decision `waiting-page-one-store`, "What D changes").

Cost: no new process and no file. The `ArtifactData` read is two string tests. A shell command that holds no `answers` is not read further; one that does goes through the frozen-path reader once.

Tests: family `answers-session-write` in `hooks/test_guard.py` (`tests/guard/s40500-answers-session-write.py`).

Kind: process
Home: hooks/guard.py

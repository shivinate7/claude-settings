# One file per note; the old notes file is frozen

## Ruling

Owner pick, waiting-page item 904, pick a (2026-11-15 19:13 CST): the old notes file, `docs/debts/notes.md`, takes deletes only. Every new note, and every edit of an old note, is its own file, `docs/notes/<slug>.md`. The old notes stay in that file: 2304 note lines, in 2313 lines in all, at 19:31 CST Nov 15. Moving them is a later step.

Format. A note file is named `<slug>.md`. Its slug is `[a-z0-9-]`, at most 32 characters, and not digits only: a digits-only slug would read as an old `note:<digits>` ref. It holds one line, `- <slug>: <text>`, and the slug on that line equals the file name. The text may hold an `Until:` marker. `docs/notes/README.md` is not a note.

Check. `lint/check_record_slugs.py` refuses a line of the old file whose count at head exceeds its count at the merge base. So a new line, an edited line and a second copy are refused. A moved line and a deleted line pass. It refuses a note file whose name is over 32 characters. It also refuses an added, renamed or edited note file in any of three cases: no `- <slug>:` line, a slug that differs from its file name, or a digits-only slug. A deleted note file and a valid note file pass. The refusal names the notes folder, never the old file.

Merge. `.gitattributes` keeps its `merge=union` line for the old file while that file exists. A note file needs no merge line. `docs/records.md` and `docs/catalog.md` keep the default merge: they are generated tables with sections, and union would leave duplicate or stale rows silently. The merge tool rebuilds `docs/records.md` (decision records-index-at-merge, one records index page rebuilt at merge time).

Scope. The rule in the root `CLAUDE.md` sends every repo's new notes to that repo's notes folder. A repo with no notes folder reads as empty. A repo's old notes file keeps its own `.gitattributes` line.

## Known costs

- The check fails every branch that adds a line to the old file. That is intended: the line goes into a file of its own.
- `history_problems` in `lint/hook_catalog.py` skips the new folder. Accepted.
- Roadmap steps `notes-union-batch-revival` (the revival check for octopus merges), `notes-union-unretire` and `notes-slug-unique` now apply to the old file only.
- Union never removes a line that one side kept. Two lanes that rewrite one note leave both versions. A note that one lane deletes can come back when another lane appends to the old file. A merge of a PR's new base revived notes the PR had deleted (PR #1825, 2026-11-08).
- `revived_notes` in `lint/check_silent_undo.py` refuses a revived note in the old file, matched by slug. It reads the branch's own commits and counts copies per slug. It refuses only when head holds more copies than the branch's last lowering commit left, so a dedupe that keeps a copy passes. A note with no `- slug:` form is read by its whole line, so only the same text counts as a copy. An octopus merge gets a verdict. A revived note on one is still FAIL, and a clean one passes with no UNKNOWN line (owner ruling, waiting-page item 987, through triage, 2026-11-18 20:45 CST). A note re-added by a non-merge commit passes. An edit in place does not keep a revived note. A rebase onto main leaves no merge, so a revival there is not seen (debt `silent-undo-rebase-no-merge`). `lint/test_notes_union_merge.py` pins the rewrite case.

## Why

Lanes appended one-line notes to one shared file, so they clashed there. On Oct 29, batch 21 (a merge run) left out four reviewed lanes (PRs #811, #807, #810, #806) only for clashes in that file. Batch 20 forced seven lanes to merge main in. A census of main's merges since Oct 15 found 26 real content conflicts in the file, the most of any file. `docs/records.md` had 11 and `docs/catalog.md` had 10.

Union was the fix. GitHub's server-side merge does not run `merge=union` (measured on PRs #3186 and #3188 at 14:44 CST Nov 15), so the union line does not protect a PR that GitHub merges. One file per note means lanes that each add a note never edit the same file. That measurement dates this record: a change in how GitHub handles `merge=union` would date it again.

- Risk: incident. The union line landed 2026-10-29.

Kind: process
Home: lint/check_record_slugs.py

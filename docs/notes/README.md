# Notes

A note is a finding that Claude is not likely to hit in normal work. The rule `roles-findings-are-debts-or-notes` in `CLAUDE.md` sends it here. Each note is one file in this folder. Decision `notes-merge-union` (one file per note) holds the ruling.

## Format

- File name: `<slug>.md`. The slug is `[a-z0-9-]`, at most 32 characters, and not digits only.
- The file holds one line: `- <slug>: <text>`. The slug on the line equals the file name.
- The text may hold an `Until:` marker.
- `README.md` is not a note.

## Old notes

The old notes file, `docs/debts/notes.md`, takes deletes only. An old note is one line in that file. Its notes stay there until a later step moves them.

## Check

`lint/check_record_slugs.py` refuses a line of the old notes file that the merge base holds fewer times: a new line, an edited line or a second copy. A moved or deleted line passes. It refuses a note file whose name is over 32 characters. It also refuses an added, edited or renamed note file in any of four cases: no `- <slug>: <text>` line, a slug that differs from its file name, a digits-only slug, or a place in a folder of the notes folder. A deleted note file passes.

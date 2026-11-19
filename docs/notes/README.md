# Notes

A note is a finding that Claude is not likely to hit in normal work. The rule `roles-findings-are-debts-or-notes` in `CLAUDE.md` sends it here. Each note is one file in this folder. Decision `notes-merge-union` (one file per note) holds the ruling.

## Format

- File name: `<slug>.md`. The slug is `[a-z0-9-]`, at most 32 characters, and not digits only.
- The file holds one line: `- <slug>: <text>`. The slug on the line equals the file name.
- The text may hold an `Until:` marker.
- The line ends with `Seen: YYYY-MM-DD xN`: the date of the last sighting and the count of sightings (decision `notes-sightings-expiry`, a note counts its sightings and expires). A new note is `x1`, dated no later than today and no more than 30 days back. A repeat sighting edits the line: it raises N and sets today's date. Only a repeat sighting refreshes the date. A note at `x2` or more is a debt: move it to a debt file, carry its Seen line there, and delete the note file.
- Notes are flat: a note sits in this folder, never in a subfolder of it.
- `README.md` is not a note.

## Old notes

The old notes file, `docs/debts/notes.md`, takes deletes only. An old note is one line in that file. Its notes stay there until a later step moves them.

## Check

`lint/check_record_slugs.py` refuses a line of the old notes file that the merge base holds fewer times: a new line, an edited line or a second copy. A moved or deleted line passes. It refuses a note file whose name is over 32 characters. It also refuses an added, edited or renamed note file in any of four cases: no `- <slug>: <text>` line, a slug that differs from its file name, a digits-only slug, or a place in a folder of the notes folder. An added note file also needs a valid Seen field, and an edited or renamed one keeps the count and the field its merge base copy held. A deleted note file passes at any count.

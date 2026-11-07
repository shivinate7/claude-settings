# A note counts its sightings and expires; each batch carries one debt-fix lane

## Ruling

Owner answer to page item 358, 2026-11-07 14:41 CST: options a and b. a: "Each note carries `Seen: <date> x<n>`. A repeat sighting raises the count instead of adding a line, and a second sighting makes the note a debt. A note not seen for 30 days is deleted, and git keeps it. The janitor sweep runs this when asked, with no new process." b: "Each batch merge starts one lane that fixes the most-seen debt, and \"debts opened vs closed\" becomes a fifth pace number." Not c (a debt-only batch over a budget).

This record builds on decision `notes-name-their-fix` (each note names its fix). The grammar has one home, `lint/check_record_slugs.py`.

### Sightings

- The field is `Seen: YYYY-MM-DD xN`, with N 1 or more. The last `Seen:` on a line counts. On a note line it sits before `Fix:`, so the line still ends with its Fix field.
- Each line a branch adds to the notes file carries a valid Seen field. Its date is today or earlier, and no more than `SEEN_EXPIRY_DAYS` (30) days old.
- A line the branch edits needs no Seen field. If it carries one, the field must be valid, and its count may not drop below the count at the merge base. Old lines never turn red.
- A repeat sighting edits the note: it raises N and sets the date to today. That edit is an edit under `notes-name-their-fix`, so a `Fix: none` note then needs a fresh `Until:` date. A sighting is a review.
- A notes line with N of 2 or more fails CI. The remedy: move it to a debt file, carry its Seen line, and delete the note line.
- A debt file may carry a `Seen:` line at column one, or after one leading `- `. When present, it must be valid. A debt with no Seen line counts as x1.

### Expiry

- A note expires when its last sighting is more than `SEEN_EXPIRY_DAYS` (30) days before today. The last sighting is the Seen date. A line with no Seen field takes the author date of the commit that last touched it, from one `git blame` of the notes file.
- A line whose blame commit is a shallow-clone boundary has no true date. It is UNKNOWN and is never deleted. A line not yet committed counts as seen today.
- Every note expires this way, the step form too. The step stays on the roadmap; git keeps the line.
- The sweep runs it when asked: `python3 ~/.claude/janitor/sweep.py --root <repo> --expire-notes` previews each expired note and the UNKNOWN count. With `--confirm`, it deletes those lines from the checkout's notes file. It never commits or pushes. It refuses when HEAD is the default branch, or when the notes file has uncommitted changes, and says why.

### One debt-fix lane per batch

- When a batch merges, the session that starts lanes starts one debt-fix lane. It fixes the open debt with the highest Seen count. Ties go to the oldest Seen date, then the slug. `python3 ~/.claude/lint/check_record_slugs.py --next-debt` prints that slug.
- That lane also runs the expiry sweep on its own branch, and commits what it deletes.
- Pace number five is debts opened and closed in the batch: debt files added and deleted between the first lane commit and the merge, not counting the notes file and the README. `python3 ~/.claude/lint/check_record_slugs.py --debt-flow START END` prints it.
- The rule to start the lane is prose only: no check sees whether a batch started one.

Cost: the Seen check runs inside the CI check that already reads the notes diff, with no new git process. The expiry runs one `git blame` and one `rev-parse` per notes file, only when the sweep is called with `--expire-notes`. `--next-debt` reads the debt folder once. `--debt-flow` runs one `git diff`, once per batch merge. None starts a long-lived process, writes a log, or runs on a timer.

Why: since 2026-10-26, notes.md gained 1,304 lines and lost 358, and docs/debts/ added 107 debt files and deleted 37 (origin/main 174b005c1, 13:44 CST Nov 7). Rule `roles-findings-are-debts-or-notes` says a note becomes a debt after a real incident, but nothing counted incidents. So no note became a debt, and no note ever left.

Source: owner answer to page item 358, 2026-11-07 14:41 CST. Best-practices finding in step notes-backlog-review.

- Risk: backlog. Landed 2026-11-07.

Kind: process
Home: lint/check_record_slugs.py
Home: janitor/sweep.py
Home: skills/ci-hygiene/SKILL.md
Check: lint/check_record_slugs.py

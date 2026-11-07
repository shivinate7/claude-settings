# A note counts its sightings and expires; each batch carries one debt-fix lane

## Ruling

Owner answer to page item 358, 2026-11-07 14:41 CST: options a and b. a: "Each note carries `Seen: <date> x<n>`. A repeat sighting raises the count instead of adding a line, and a second sighting makes the note a debt. A note not seen for 30 days is deleted, and git keeps it. The janitor sweep runs this when asked, with no new process." b: "Each batch merge starts one lane that fixes the most-seen debt, and \"debts opened vs closed\" becomes a fifth pace number." Not c (a debt-only batch over a budget).

This record builds on decision `notes-name-their-fix` (each note names its fix). The grammar has one home, `lint/check_record_slugs.py`.

### Sightings

- The field is `Seen: YYYY-MM-DD xN`, with N 1 or more. The last `Seen:` on a line counts. On a note line it sits before `Fix:`, so the line still ends with its Fix field.
- Each line a branch adds to the notes file carries a valid Seen field. Its date is today or earlier, and no more than `SEEN_EXPIRY_DAYS` (30) days old.
- A line the branch edits needs no Seen field when its line at the merge base had none. When the base line had one, the edit keeps it: dropping it is red, like a count drop (lane ruling 2026-11-07 15:58 CST). A field the edit carries must be valid, and its count may not drop below the count at the merge base. The age of an edited line's date is not judged. Old lines never turn red.
- A repeat sighting edits the note: it raises N and sets the date to today. That edit is an edit under `notes-name-their-fix`, so a `Fix: none` note then needs a fresh `Until:` date. A sighting is a review.
- A notes line with N of 2 or more fails CI. The remedy: move it to a debt file, carry its Seen line, and delete the note line.
- A Seen field after the Fix field also parses. The check does not judge the order.
- A debt file may carry a `Seen:` line at column one, or after one leading `- `. When present, it must be valid: a calendar date today or earlier, and N 1 or more. It has no age limit. A debt with no Seen line counts as x1 with no date.

### Expiry

- A note expires when its last sighting is more than `SEEN_EXPIRY_DAYS` (30) days before today. The last sighting is the Seen date. A line with no Seen field takes the author date of the commit that last touched it, from one `git blame` of the notes file.
- A line whose blame commit is a shallow-clone boundary has no true date. It is UNKNOWN and is never deleted. A line not yet committed counts as seen today.
- Every note expires this way, the step form too. The step stays on the roadmap; git keeps the line.
- The sweep runs it when asked: `python3 ~/.claude/janitor/sweep.py --root <repo> --expire-notes` previews each expired note and the UNKNOWN count. With `--confirm`, it deletes those lines from the checkout's notes file. UNKNOWN lines do not change the exit code. It never commits, pushes or removes a branch. It refuses when HEAD is the default branch, when HEAD is detached (no branch would merge the deletion), or when the notes file has uncommitted changes, and says why. A notes file that HEAD does not hold has lines not yet committed: each with no Seen field is seen today. Those lines are known, and the preview exits 0 (lane rulings 2026-11-07 15:58 CST).

### One debt-fix lane per batch

- When a batch merges, the session that starts lanes starts one debt-fix lane. It fixes the open debt with the highest Seen count. Ties go to the oldest Seen date, a debt with no date after the dated ones, then the slug. `python3 ~/.claude/lint/check_record_slugs.py --next-debt` prints that slug.
- That lane also runs the expiry sweep on its own branch, and commits what it deletes: the sweep only edits the file.
- Pace number five is debts opened and closed in the batch: debt files added and deleted between the first lane commit and the merge, not counting the notes file and the README. `python3 ~/.claude/lint/check_record_slugs.py --debt-flow START END` prints it as `debts opened N, closed M`, then one `+ <slug>` or `- <slug>` line each. The window includes START itself: the diff runs from the parent of START, or from the empty tree when START has no parent. The count is net, so a debt that START adds and a later commit deletes is in neither list. Both `--next-debt` and `--debt-flow` read the git repo of the current directory, and outside any repo print UNKNOWN and exit 1.
- The rule to start the lane is prose only: no check sees whether a batch started one.

Cost: every git read, by command:
- The Seen check reads the notes diff once, shared with the Fix and Until checks. It adds one `git show` of HEAD per debt file the branch adds or edits.
- `--expire-notes` runs one `rev-parse --show-toplevel` and one `git blame --line-porcelain` per notes file.
- It adds one `rev-parse --is-shallow-repository` per notes file that has a boundary line, and one `ls-tree` of HEAD per notes file that blame cannot read.
- With `--confirm` it also reads the default branch (one `symbolic-ref`, then up to five `rev-parse`), runs one `symbolic-ref` of HEAD, and runs one `status --porcelain` of the notes file.
- `--next-debt` runs one `rev-parse --show-toplevel` and reads the debt folder once.
- `--debt-flow` runs one `rev-parse --show-toplevel`, one `rev-parse` that START is a commit, one `rev-parse` of its parent, and one `git diff`, once per batch merge. It adds one `hash-object` when START has no parent.
- None starts a long-lived process, writes a log, or runs on a timer.

Why: since 2026-10-26, notes.md gained 1,304 lines and lost 358, and docs/debts/ added 107 debt files and deleted 37 (origin/main 174b005c1, 13:44 CST Nov 7). Rule `roles-findings-are-debts-or-notes` says a note becomes a debt after a real incident, but nothing counted incidents. So no note became a debt, and no note ever left.

Source: owner answer to page item 358, 2026-11-07 14:41 CST. Best-practices finding in step notes-backlog-review.

- Risk: backlog. Landed 2026-11-07.

Kind: process
Home: lint/check_record_slugs.py
Home: janitor/sweep.py
Home: skills/ci-hygiene/SKILL.md
Check: lint/check_record_slugs.py

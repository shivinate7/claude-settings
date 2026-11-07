# Debts

A debt is the filed record of a known gap, or of deferred work. The rule `roles-findings-are-debts-or-notes` in `CLAUDE.md` makes a finding a debt when Claude is likely to hit it in normal work. This folder is the debt store for this repo, and the one home for deferred work (owner ruling 2026-10-17 23:46 CDT).

## Shape

One file per debt, named by a slug of 32 characters or fewer. Each file has four parts, and a new file adds a Fix field after them:

- **What.** The finding, in one or two sentences.
- **Where.** The file, rule, or check the finding sits in.
- **Decision.** The decision that names the finding, by slug plus a short gloss. Use the slug now. If the repo numbers decisions, add the number at merge. Never cite it by path. If no decision exists, write `none`.
- **Retire.** What closes the finding, and a runnable test file, in backticks, that shows it closed. Name it like a test file (`test_*.py`, `*_test.py`, `*.test.mjs`, `test_*.mjs`, `test_*.sh`). Decision `debt-close-runs-retire` (the merge tool runs that file at close).

A new debt file also has a fifth part, the Fix field: a line that starts `Fix:` at column one, or after one leading `- ` (decision `notes-name-their-fix`, a note or a debt names its fix). It takes one of these forms:

- `Fix: step:<slug>`, where `roadmap/data/steps/<slug>.json` exists on `origin/roadmap`.
- `Fix: none -- <reason>` (the em dash also counts). The reason is `owner decides`, `needs the Mac`, `needs a Windows run`, `rare and harmless`, or `already fixed on main <sha>` (a hex sha of 7 to 40 digits, a commit that is an ancestor of origin/main).

Each line a branch adds to `notes.md` carries the same field, anywhere on the line. A line whose `- <slug>:` already exists at the merge base is an edit and passes. `lint/check_record_slugs.py` checks this in CI. The Stop guard (`lint/report_guard.py`) also asks that Done name each `step:` that the turn's own commits add.

Three more rules read `notes.md`. First, the ratchet. When a branch touches the file, its count of bullets with no valid Fix may not exceed the count at the merge base of origin/main and the branch. The check prints the total. Second, a `Fix: none -- <reason>` line carries `Until: YYYY-MM-DD`, from today to 14 days out (`UNTIL_CAP_DAYS`), checked on lines the branch adds or edits only. A step line and an already-fixed line need no date. Third, the roadmap build lists each note whose date is past, one line each, in its upkeep list.

A feel-fix debt also has two optional lines. A line counts when it starts with its marker at column one, or
after an optional leading `- `:

- `**Feel.**` marks the debt a feel-fix. Decision `feel-fix-waits-device-check` (a feel-fix waits for a
  device trial) defines the term.
- `**Device check.**` names `simulator` or `device`, then an ISO time with a zone. It records a device trial
  (same decision). A session adds it after the fix has landed.

An owner ruling a debt holds goes under an H2 `## Ruling` in its file. No hook reads that section for a question now. A ruling under any other heading, or in `notes.md`, is not read either. Put such a ruling in a debt, or in its decision.

A finding becomes a debt only when Claude is likely to hit it in normal work. Any other finding is one line in `notes.md`, with no red test and no decision edit (owner ruling 2026-10-17 11:56 CDT). Each new note line ends with its Fix field, as above.

## Closing a debt

In the PR that closes the finding, delete the debt file. A rename inside this folder that changes the Retire part counts as a close too. The merge tool runs the Retire check first and refuses the close if it is red or cannot run. A PR with no runnable check, or one that cannot run, adds `Retire-run: <slug> -- <run URL>` to its body, for a run that succeeded on the PR head or a descendant of it. A cite never clears a red check. If a decision names the finding, rewrite that decision in place, so it no longer lists the finding. Git keeps the history.

A feel-fix debt closes in three steps. A device trial comes first (decision `feel-fix-waits-device-check`):

1. The fix PR keeps the debt file.
2. A session adds the `**Device check.**` line once the fix has landed.
3. A later PR deletes the file, renames it out of this folder, or edits out its `**Feel.**` line. Its
   session then opens a try-it item on the waiting page. The slug check (`lint/check_record_slugs.py`, a
   check) fails step 3 unless origin/main holds a valid device-trial line.

## Status

`lint/check_record_slugs.py` checks each debt file's slug length. It also fails a feel-fix debt that is
deleted, renamed out of this folder, or edited to drop its `**Feel.**` line, unless origin/main's text holds
a valid device-trial line. It also fails a new debt file or a new notes line with no valid Fix field, or with a `step:` that origin/roadmap lacks. `lint/check_debt_retire.py` reads the Retire part at close. No check reads the What, Where or Decision part yet.

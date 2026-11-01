# Debts

A debt is the filed record of a known gap, or of deferred work. The rule `roles-findings-are-debts-or-notes` in `CLAUDE.md` makes a finding a debt when Claude is likely to hit it in normal work. This folder is the debt store for this repo, and the one home for deferred work (owner ruling 2026-10-17 23:46 CDT).

## Shape

One file per debt, named by a slug of 32 characters or fewer. Each file has four parts:

- **What.** The finding, in one or two sentences.
- **Where.** The file, rule, or check the finding sits in.
- **Decision.** The decision that names the finding, by slug plus a short gloss. Use the slug now. If the repo numbers decisions, add the number at merge. Never cite it by path. If no decision exists, write `none`.
- **Retire.** What closes the finding, and the check that shows it closed.

A feel-fix debt also has two optional lines. Each starts with its marker, at the line's first character:

- `**Feel.**` marks the debt a feel-fix. Decision `feel-fix-waits-device-check` (a feel-fix waits for a
  device check) defines the term.
- `**Device check.**` names `simulator` or `device`, then the ISO time with a zone. A session adds it after
  the fix has landed.

An owner ruling a debt holds goes under an H2 `## Ruling` in its file. No hook reads that section for a question now. A ruling under any other heading, or in `notes.md`, is not read either. Put such a ruling in a debt, or in its decision.

A finding becomes a debt only when Claude is likely to hit it in normal work. Any other finding is one line in `notes.md`, with no red test and no decision edit (owner ruling 2026-10-17 11:56 CDT).

## Closing a debt

In the PR that closes the finding, delete the debt file. If a decision names the finding, rewrite that decision in place, so it no longer lists the finding. Git keeps the history.

A feel-fix debt closes in three steps. A feel needs a device check first (decision `feel-fix-waits-device-check`):

1. The fix PR keeps the debt file.
2. A session adds the `**Device check.**` line once the fix has landed.
3. A later PR deletes the file. Its session then opens a try-it task on the waiting page. The slug check
   (`lint/check_record_slugs.py`, a check) fails step 3 when origin/main holds no device check line.

## Status

`lint/check_record_slugs.py` checks each debt file's slug length. It also fails a deletion of a feel-fix debt
whose origin/main text has no device check line. No check reads the four parts yet.

# A note or a debt names its fix

## Ruling

Each line a branch adds to `docs/debts/notes.md`, and each debt file it adds, carries a Fix field. The field has one of three forms:

- `Fix: step:<slug>`. The step file `roadmap/data/steps/<slug>.json` exists on `origin/roadmap`.
- `Fix: none -- <reason>` (the em dash also counts). The reason is one of: owner decides, needs the Mac, rare and harmless, already fixed on main with a hex sha of 7 to 40 digits.
- `Fix: already fixed on main <sha>`, the same reason without the `none --` lead.

`step:` is the only way to name a fix, because the PR ledger counts steps. Prose such as `Fix: pin the base` is not a fix.

- A notes line holds the field anywhere on the line; the last `Fix:` counts. A debt file holds it as a line that starts `Fix:` at column one, or after one leading `- `.
- A notes line whose `- <slug>:` already exists at the merge base is an edit and passes. Old lines never turn red.
- CI (`lint/check_record_slugs.py`) judges the form and, for a step, that it exists on `origin/roadmap`. It is the one home of the grammar. When the roadmap read cannot run, the check exits non-zero and says the read did not run.
- The Stop guard (`lint/report_guard.py`) imports that grammar. On a landed turn whose Done has a RECORDED item, each `Fix: step:<slug>` that this turn's own commits add must have its slug in Done. The turn's commits are the `[branch sha] subject` lines that `git commit` printed in its tool results. An earlier turn's lines are not judged again. A sha git cannot read is skipped. The none and already-fixed forms pass.

Three more parts, all on the notes file:

- Ratchet. When a branch touches the notes file, the count of bullets with no valid Fix at HEAD may not exceed the count at the merge base of `origin/main` and HEAD. A branch forked before main lowered its count is not blamed for that. Both counts are read live from git, with no stored baseline. The check prints the total.
- Until. A `Fix: none -- <reason>` line carries `Until: YYYY-MM-DD`. The check reads it on lines the branch adds or edits only. A missing date, a past date, or one more than `UNTIL_CAP_DAYS` (30) days from today is refused. A step line and an already-fixed line need no date. Today is the `FIXED_TODAY` variable when set, else the clock.
- Upkeep. The roadmap build (`skills/roadmap/build.py`) prints one upkeep line per note whose Until date is past. It imports the grammar from `lint/check_record_slugs.py`. It adds no log or timer.

Cost: the ratchet adds one merge-base, one ls-tree and one show per ref, only when a branch touches the notes file. The Stop check starts one git process per commit the turn printed, and none in a checkout with no notes file. The upkeep line reads the notes file once.

Why: on 2026-11-07 13:20 CST the coordinator wrote two fixable gaps into `docs/debts/notes.md`, reported them RECORDED, and started no fix. The owner asked "why not fix it then", and at 13:25 CST said "I want the guard itself". A gap in a file nobody reads never gets fixed. A note is meant for a finding too unlikely to hit, so a fixable gap there needs a step, or a stated reason that it needs none.

Source: owner words 2026-11-07 13:20 CST ("why not fix it then") and 13:25 CST ("I want the guard itself"). Coordinator ruling 2026-11-07 13:30 CST (`step:` is the only form, since the PR ledger counts steps). Coordinator rulings 2026-11-07 13:58 CST (the ratchet; the Until date and its 30-day cap; the Stop check judges the turn's commits only) and 13:59 CST (the upkeep line, one home for the grammar). Coordinator ruling 2026-11-07 (after the first build): the ratchet's base is the merge base, not live origin/main.

- Risk: incident. Landed 2026-11-07.

Kind: process
Home: lint/check_record_slugs.py
Home: lint/report_guard.py
Home: skills/roadmap/build.py
Check: lint/check_record_slugs.py

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
- The Stop guard (`lint/report_guard.py`) imports that grammar. On a landed turn whose Done has a RECORDED item, each `Fix: step:<slug>` the branch adds must have its slug in Done. The none and already-fixed forms pass.

Why: on 2026-11-07 13:20 CST the coordinator wrote two fixable gaps into `docs/debts/notes.md`, reported them RECORDED, and started no fix. The owner asked "why not fix it then", and at 13:25 CST said "I want the guard itself". A gap in a file nobody reads never gets fixed. A note is meant for a finding too unlikely to hit, so a fixable gap there needs a step, or a stated reason that it needs none.

Source: owner words 2026-11-07 13:20 CST ("why not fix it then") and 13:25 CST ("I want the guard itself"). Coordinator ruling 2026-11-07 13:30 CST (`step:` is the only form, since the PR ledger counts steps).

- Risk: incident. Landed 2026-11-07.

Kind: process
Home: lint/check_record_slugs.py
Home: lint/report_guard.py
Check: lint/check_record_slugs.py

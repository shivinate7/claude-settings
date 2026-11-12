# A note or a debt names its fix

## Ruling

Each line a branch adds to `docs/debts/notes.md`, and each debt file it adds, carries a Fix field. The field has one of three forms:

- `Fix: step:<slug>`. The step file `roadmap/data/steps/<slug>.json` exists on `origin/roadmap`.
- `Fix: none -- <reason>` (the em dash also counts). The reason is one of: owner decides, needs the Mac, needs a Windows run (coordinator, 14:23 CST), rare and harmless, already fixed on main with a hex sha of 7 to 40 digits. The sha must name a commit that is an ancestor of `origin/main`. When that read cannot run, the check reports UNKNOWN and exits 1, as it does for the roadmap read.
- `Fix: already fixed on main <sha>`, the same reason without the `none --` lead.

`step:` is the only way to name a fix, because the PR ledger counts steps. Prose such as `Fix: pin the base` is not a fix.

- A notes line holds the field anywhere on the line; the last `Fix:` counts. A debt file holds it as a line that starts `Fix:` at column one, or after one leading `- `.
- A notes line whose `- <slug>:` already exists at the merge base is an edit and passes. A line with no slug is an edit when the same diff removes a bullet with no slug (a reword). Old lines never turn red.
- A note line is a bullet with `-`, `*` or `+`, or a number and `.` or `)`, indented or not, or a dash glued to its word. A `Fix:` inside a code span or a double-quoted span is quoted, never the field. A debt file's `Fix:` inside a fenced block is no field. A debt file that arrives by rename, or a notes file the branch renames, is checked like an added one.
- CI (`lint/check_record_slugs.py`) judges the form and, for a step, that it exists on `origin/roadmap`. It is the one home of the grammar. When the roadmap read cannot run, the check exits non-zero and says the read did not run.
- The Stop guard (`lint/report_guard.py`) imports that grammar. On a landed turn whose Done has a RECORDED item, each `Fix: step:<slug>` that this turn's own commits add must have its slug in Done. The turn's commits are those on HEAD and not on `origin/main` with an author time at or after the turn's start, so a quiet `git commit -q` counts. An earlier turn's lines are not judged again, and an amend or rebase of an earlier commit keeps its author time, so it is not judged either. If a commit edits a notes line and keeps its slug and Fix, the line yields no entry, so a typo fix adds no step to Done. A commit cherry-picked this turn keeps its old author time and is missed, which fails open. A sha or a time git cannot read fails open. A write to the remote through an MCP tool makes no local commit, so the check does not cover it. The none and already-fixed forms pass.

Three more parts, all on the notes file:

- Ratchet. When a branch touches the notes file, the count of bullets with no valid Fix at HEAD may not exceed the count at the merge base of `origin/main` and HEAD. A branch forked before main lowered its count is not blamed for that. Both counts are read live from git, with no stored baseline. The check prints the total.
- Until. A `Fix: none -- <reason>` line carries `Until: YYYY-MM-DD`. The check reads it on lines the branch adds or edits only. A missing date, a past date, or one more than `UNTIL_CAP_DAYS` (14) days from today is refused. A step line and an already-fixed line need no date. Today is the `FIXED_TODAY` variable when set, else the clock.
- Upkeep. The roadmap build (`skills/roadmap/build.py`) prints one upkeep line per note whose Until date is past. It imports the grammar from `lint/check_record_slugs.py`. It adds no log or timer.

Cost: the ratchet adds one merge-base, one ls-tree and one show per ref, only when a branch touches the notes file. The Stop check runs one git log and one git process per commit of the turn, and none in a checkout with no notes file. Every diff the check parses passes explicit `a/` and `b/` prefixes, so `diff.noprefix` cannot silence it. The upkeep line reads the notes file once.

Why: on 2026-11-07 13:20 CST the coordinator wrote two fixable gaps into `docs/debts/notes.md`, reported them RECORDED, and started no fix. The owner asked "why not fix it then", and at 13:25 CST said "I want the guard itself". A gap in a file nobody reads never gets fixed. A note is meant for a finding too unlikely to hit, so a fixable gap there needs a step, or a stated reason that it needs none.

Source: owner words 2026-11-07 13:20 CST ("why not fix it then") and 13:25 CST ("I want the guard itself"). Coordinator ruling 2026-11-07 13:30 CST (`step:` is the only form, since the PR ledger counts steps). Coordinator rulings 2026-11-07 13:58 CST (the ratchet; the Until date and its 30-day cap; the Stop check judges the turn's commits only) and 13:59 CST (the upkeep line, one home for the grammar). Coordinator ruling 2026-11-07 (after the first build): the ratchet's base is the merge base, not live origin/main. Coordinator ruling 2026-11-07 14:23 CST: the reason `needs a Windows run` joins the list. Owner, page item 360 b, 2026-11-07: the Until cap is 14 days, not 30. The refusal for a bad Fix lists the reasons and the Until rule.

- Risk: incident. Landed 2026-11-07.

Kind: process
Home: lint/check_record_slugs.py
Home: lint/report_guard.py
Home: skills/roadmap/build.py
Check: lint/check_record_slugs.py

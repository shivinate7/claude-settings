# A ruling-skip pick word false-alarms on an article and a noun

**What.** A Done item with a pick word and a ruling cue must cite its ruling. The pick pattern matches "took" before an article, so "took a look at the ruling index" makes a pick claim. It also matches the noun "pick", so "docs pick up the new ruling" and "the pick check now reads rulings" make one. Each refuses for no cite, though none picks an option. Lanes that edit the pick and ruling checks hit it. The refusal says to ask the owner, which misleads.

**Where.** `lint/report_guard.py`, `RULING_PICK_RE`, read by `ruling_claims`. The cases are in `lint/test_report_guard_ruling_skip.py`.

**Decision.** `questions-go-to-owner`, questions go to the owner (its ruling-skip bullet, rule `ruling-skip-check`).

**Retire.** A pick word matches only a real pick. Closed when `lint/test_report_guard_ruling_skip.py` holds "took a look at the ruling index", "docs pick up the new ruling" and "the pick check now reads rulings" as no claim, and a real pick under a ruling with no cite still refuses. The new cases go red on the current pattern first.

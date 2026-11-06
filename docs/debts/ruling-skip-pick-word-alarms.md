# A ruling-skip pick word false-alarms on an article and a noun

**What.** A Done item with a pick word and a ruling cue must cite its ruling. The pick pattern matches "took" before an article, so "took a look at the ruling index" and "took a first pass over the rulings" make a pick claim. It also matches the noun "pick", so "docs pick up the new ruling", "the pick check now reads rulings" and "filed the owner's ruling, pick b" make one. Each refuses for a missing cite. Lanes that edit the pick and ruling checks hit it, and the refusal says to ask the owner, which misleads.

**Where.** `lint/report_guard.py`, `RULING_PICK_RE`, read by `ruling_claims`. The cases are in `lint/test_report_guard_ruling_skip.py`.

**Decision.** `questions-go-to-owner`, questions go to the owner (its ruling-skip bullet, rule `ruling-skip-check`).

**Retire.** A pick word matches only a real pick. Closed when `lint/test_report_guard_ruling_skip.py` holds each text in What as no claim, and a real pick under a ruling with no cite still refuses. The new cases go red on the current pattern first.

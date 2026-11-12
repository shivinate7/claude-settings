# A ruling-skip pick word false-alarms on honest lines

**What.** A Done item with a pick word and a ruling cue in one clause must cite its ruling. Honest lines that pick nothing refuse for a missing cite. Refused now: "filed the owner's ruling, pick b", "took the key in the ruling table", "pick made in the rulings log", "filed the ruling the owner picked", "chose the simpler test for the ruling tests" and "picked up the owner's ruling". Passing now: "took a look at the ruling index", "took a first pass over the rulings", "docs pick up the new ruling" and "the pick check now reads rulings". Lanes that edit the pick and ruling checks hit it, and the refusal says to ask the owner, which misleads. Fix idea: let "in" count only after an option letter (`PICK_LINK_WORDS`, `_is_pick`). That fixes two of the six. "picked" and "chose" always count (`_is_pick`), and "pick b" has no link word after it, so those four need another fix.

**Where.** `lint/report_guard.py`, `RULING_PICK_RE` and `_is_pick`, read by `ruling_claims`. The cases are in `lint/test_report_guard_ruling_skip.py`.

**Decision.** `questions-go-to-owner`, questions go to the owner (its ruling-skip bullet, rule `ruling-skip-check`).

**Retire.** A pick word matches only a real pick. Closed when `lint/test_report_guard_ruling_skip.py` holds each text in What as no claim, and a real pick under a ruling with no cite still refuses. The new cases go red on the current pattern first.

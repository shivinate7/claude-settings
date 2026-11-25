# A valid judge list that omits a covered question lets it pass

**What.** When the judge's list is valid, a covered question the list omits passes, even when its own Based on (ruling) line does not name the ruling. Main refused the whole reply. Harm: one question re-asked, reversible. The judge's omission rate is unmeasured.

**Where.** `hooks/question_form.py` `past_ruling_text`: with a valid list, only the listed units are judged, so an omitted unit is never refused. Both paths call it: `hooks/call_judge.py` `main` and `lint/report_guard.py` `past_ruling_problem`.

**Decision.** `guard-remedy-not-to-owner` (the past-ruling guard).

**Retire.** Retired when the judge's omission rate is measured, or the fallback changes so that an omitted covered unit is refused.

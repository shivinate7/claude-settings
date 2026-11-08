# A stated ruling with "must" loses its date and decision

**What.** A past-ruling judge reason that only states a ruling, such as "decision x (2026-11-01) says replies must end with the report.", is dropped whole, because `_MODAL` flags "must" and "should" in it. The refusal keeps the ruling id but loses the ruling's date and what it decides. Rulings often say "must", so this is common. The refusal still fires.

**Where.** `lint/report_guard.py`: `_MODAL` (:237) and `session_wording` (:240, modal return :258), called by `past_ruling_problem` (:1722) when it drops the reason.

**Decision.** `guard-remedy-not-to-owner` (guard text never instructs through the owner). The refusal gives the ruling's id, its date and what it decides.

**Retire.** A test in `lint/test_report_guard.py` (class `PastRulingRelay`) feeds a judge reason that states a ruling with "must" and expects the refusal to keep its date and decision text. A second case feeds an order with "must" aimed at the session and expects that text dropped. Both pass.

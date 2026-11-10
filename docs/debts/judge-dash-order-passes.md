# An order after a dash or with no mark passes session_wording

**What.** `session_wording` does not flag an order that follows an em dash, or one joined with no mark, so a past-ruling judge reason can still reach the owner with it. "The ruling settles this — drop the question." and "The ruling settles this and drop the question." both return "". "Pick" is left out of `SESSION_IMPERATIVES` on purpose, since "Pick guard" is the check name of an owner line. So "Pick the ruling and drop the question." passes too.

**Where.** `session_wording` and its caller `past_ruling_problem` in `lint/report_guard.py`. The caller keeps only the ruling id when `session_wording` flags the judge reason.

**Decision.** `guard-remedy-not-to-owner` (guard text never instructs through the owner).

**Retire.** The two dash and no-mark orders and the "Pick" order are flagged, a test pins each, and the fact sentences in the same test stay clean. Test: `lint/test_report_guard_remedy.py`.

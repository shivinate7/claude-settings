# A ruling cite with a time range or a bare path is flagged

**What.** The cite check reads a time range such as `14:30-14:33 CST` as no time. It reads a bare path such as `docs/decisions/<slug>.md` as no home. A claim that cites its time or its home in either form is flagged. Seen on commit ac23f1a8 (a commit that edits the page-writer bullet).

**Where.** `lint/check_red_run.py`: `has_time`, which reads the time forms from `lint/report_guard.py`, and the home pattern `DECISION_HOME_RE`.

**Decision.** `outcomes-grant-covers-named-act` (a grant covers the act it names, never a variant).

**Retire.** A claim with a time range and a bare decision path passes. Cases in `lint/test_check_red_run.py` show it.

# A dead member on a live class passes the name checks

**What.** A dotted cite reads only its first part. So `(lint/x.py Guard.gone)` passes STALE010 while `Guard` is bound, even when `Guard` has no `gone`. Claude writes `Class.method` cites in normal work: 11 are in notes. <!-- ste-disable-line STALE010 -->

**Where.** lint/stale_cites.py `pair_res`, and the readers of STALE002 and STALE010.

**Decision.** record-cites-live-code (claims about code cite live code names).

**Retire.** A dotted cite on a module-level class also checks its second part against that class's names, class attributes included (debt stale010-class-level-names). A case in `lint/test_stale_cites.py` shows a dead member gives STALE010.

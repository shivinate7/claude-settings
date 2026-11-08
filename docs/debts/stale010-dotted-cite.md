# A dotted cite is no cite form

**What.** `PAIR_RES` reads only a plain name after the path. So `(lint/x.py Guard.gone)` passes STALE010 when the name is dead, and a live `lint/x.py` `Guard.run` in a decision claim draws a false STALE009 report. The tree holds 12 dotted cites, such as `merge/merge.py Lock.extend_for` in notes, so Claude writes this form in normal work. <!-- ste-disable-line STALE010 -->

**Where.** lint/stale_cites.py `pair_res`, read by STALE002, STALE009 and STALE010.

**Decision.** record-cites-live-code (claims about code cite live code names).

**Retire.** A dotted cite reads its first part as the name, and a case in `lint/test_stale_cites.py` shows a dead `Class.method` cite gives STALE010.

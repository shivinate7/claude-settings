# A cite in call form dodges the name checks

**What.** `` `lint/x.py` `no_such()` `` matches no cite form, so STALE010 and STALE002 never read it. `(lint/x.py no_such())` is read. A dotted call such as `` `lint/x.py` `Nope.gone()` `` passes the same way. Claude writes the call form in normal work (how often is unmeasured), so a dead cite in that form passes. Round 1 of #1893 found it. <!-- ste-disable-line STALE010 -->

**Where.** lint/stale_cites.py `pair_res`, the backtick form.

**Decision.** record-cites-live-code (claims about code cite live code names).

**Retire.** The backtick form accepts a trailing `()`, and a case in `lint/test_stale_cites.py` shows a dead call-form cite gives STALE010.

# STALE010 calls a name that is not module-level dead

**What.** `names_in` binds only module-level names and the defs directly in a module-level class. A cite to any other name fails STALE010 and reads as dead: a nested def, a local, a method called on an object, a string id, a class attribute, a nested class, a star import, a `type` alias statement, or a `global` name set inside a def. STALE002 shares the same reader. Round 2 of #1893 measured 4 such false alarms in 254 name cites in tracked Markdown (`elsewhere`, `wait`, `rule9`, `readline`). Round 1 reproduced it with `(lint/x.py CODE)` and `lint/t.py::Outer::Inner::m`. <!-- ste-disable-line STALE010 -->

**Where.** lint/stale_cites.py `names_in`, read by STALE002 and STALE010.

**Decision.** record-cites-live-code (claims about code cite live code names).

**Retire.** `names_in` binds or skips each name form in What (class attribute, nested class, nested def, local, method on an object, string id, star import), and a case in `lint/test_stale_cites.py` shows a cite to each gives no STALE010.

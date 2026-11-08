# STALE010 calls a class-level name dead

**What.** `names_in` binds only module-level names and the defs directly in a module-level class. A cite to a class attribute (`CODE = ...`, a dataclass field), a nested class or a star import fails STALE010 and reads as dead. STALE002 shares the same reader. Round 1 of #1893 reproduced it with `(lint/x.py CODE)` and `lint/t.py::Outer::Inner::m`.

**Where.** lint/stale_cites.py `names_in`, read by STALE002 and STALE010.

**Decision.** claims-carry-backing (the claim-backing record).

**Retire.** `names_in` binds class attributes and nested classes, and a case in `lint/test_stale_cites.py` shows a cite to each passes.

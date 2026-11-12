# The one-home check reads Markdown only

**What.** The one-home check (`lint/find_copies.py --in-repo`, `lint/stale_cites.py` STALE006) reads tracked Markdown. Code that does one job twice, such as two functions with different names and the same body, or a module constant copied into a second file, passes it.

**Where.** Mechanism row `building-one-home-per-capability` in `lint/rule_mechanisms.json` is kind `check`, and its test proves the Markdown half only. The plan's note on the code case was parked (`docs/plans/one-home-check.md`, plan refuter finding 1).

**Decision.** `one-home-check` (the one-home check). Coordinator pick 13:45 CST Nov 12, reversible: the Markdown half is `check`, the code half is this debt.

**Retire.** A check reads the repo's Python with `ast` and fails a repeated function body or a module constant held in two files. A test proves it red on a planted pair, and the false alarms on main are counted first (rule `building-scanner-respects-strings`). Until then Claude is likely to hit this gap only when it writes a second helper beside an existing one.

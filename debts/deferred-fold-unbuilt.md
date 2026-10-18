# deferred/ has not yet folded into debts/

**What.** `debts/` is the one home for deferred work, but the repo still holds `deferred/`. The question judge and two lints still name `deferred/`. A session can look in the old folder or ask the owner a question already deferred.

**Where.** `deferred/`; `hooks/question_outcome.py`, `lint/check_record_slugs.py`, `lint/hook_catalog.py`.

**Decision.** `cull-rules`, owner rulings of 2026-10-17 23:46 CDT (the cull bars file moves until it ends).

**Retire.** After the cull ends, move each `deferred/` item into `debts/`, point the three files at `debts/`, and delete `deferred/`. `python3 lint/check_record_slugs.py` and `lint/test_hook_catalog.py` pass with no `deferred/` path.

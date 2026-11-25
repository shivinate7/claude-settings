# A test stand-in must accept the calls the product makes

Question: how do we catch a test stand-in that cannot take a call the product makes?

## The ruling

Owner, 19:33 CST Nov 24 2026, typed in the consultant's chat: land now the guards for this mistake. The form (compare what callers pass; count what cannot be judged) is a consultant pick, not owner-typed.

Mistake it guards: on 2026-11-24, pull request 3861 added keyword `stdout_only` to `sh()` in `merge/merge.py`. Test stand-ins installed with `patch.object(merge, "sh", ...)` did not accept it. 112 tests raised TypeError. No check before CI saw it.

Harm: one CI run of the merge jobs (13,404 job-seconds on a like run), and a return to draft.

What it does: `check_standins` in `lint/check_standin_signatures.py` reads each paired test and product file with the Python `ast` module. It reports a stand-in that does not accept a keyword, or a positional count, that the product passes to the patched name. A stand-in with `**kwargs` accepts every keyword. Remedy on a finding: build the stand-in through the file's helper, or give it `**kwargs`.

Not judged: a form it cannot judge is counted in one `N stand-ins not judged` line, never skipped in silence. Those forms are starred targets, string targets, `patch.multiple`, `new_callable`, `**kwargs` dicts, plain assignment, and `setattr`.

State: not a gate yet. Its fixture suite runs in CI (`checks.yml` step "Stand-in signature fixture suite"). The check itself does not run on the repo in CI or in the ready checks. Main has 52 findings to clear first: 51 in `merge/test_merge.py` and 1 in `skills/roadmap/test_build.py`. The owner's pick on the form of the fix is open (question QQ, asked 19:53 CST Nov 24 2026). Until then a session runs it by hand: `python3 lint/check_standin_signatures.py`.

Known gaps: notes `standin-union-ignores-reach`, `standin-count-holds-restores`, `standin-count-per-call`, `standin-mock-forms-uncounted`, `standin-other-module-silent`, `standin-allow-pins-missing`.

Cost: at most one read and one parse of each paired test and product file, about 3 s on the whole repo (2.96 s real, measured 2026-11-24). It runs only when a session runs it. It starts no process on its own and writes no file.

Kind: process
Home: lint/check_standin_signatures.py
Check: `lint/test_standin_signatures.py`, classes such as `KeywordTests`, `PositionalTests` and `SpellingTests`.

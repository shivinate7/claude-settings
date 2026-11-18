# The cd walk in guard_core has surviving mutants

**What.** The mutation test has no row for the directory walk in `hooks/guard_core.py` (`dir_before_segment`). On 2026-11-08, 16 hand-made mutants of the walk were run against `hooks/test_dir_before_segment.py` (59 cases): 9 died and 7 survived. The survivors: `ran` ignores doubt; `ran` ignores the pipe; an unsafe command no longer clears `known`; a skipped branch sets no `unsure`; `unsure` uses `ran` not `sure`; the doubt reset is dropped; the `$` check in a read is dropped (probably equivalent). The code is right; the tests are missing. Mistake: Claude changes the walk and the suite stays green. Harm: a wrong cd read gives a wrong guard verdict on every family that reads the walk. Since then `hooks/guard_merge.py` has its own mutation row, but `hooks/guard_core.py` is on `GUARD_MODULE_EXEMPT` because a mutant of it needs the whole guard suite.

**Where.** `hooks/test_dir_before_segment.py`, and `GUARD_MODULE_EXEMPT` in `hooks/mutate_guard.py`.

**Decision.** `none`.

**Retire.** One case per surviving mutant above (the probably equivalent one may be named equivalent in a comment), each red on its mutant. Test file: `hooks/test_dir_before_segment.py`.

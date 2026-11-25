# A name before its path shows the file head

**What.** A cite that puts the name before the path, `read NAME in PATH` or `read NAME and NAME in PATH`, gives the prose judge the top of the file, not the named definition. The judge then prints a false "unbacked" line for a true cite, and a reader learns to skip those lines. A dotted name read as a path (`docs/decisions/no-merge-onto-red-main.md` line 8: "read through `Host.failed_lines`") gives the judge an absent file, so it shows as unreadable. Real cites today: 5 name-before-path cites on 3 lines (`docs/decisions/claims-carry-backing.md` lines 17 and 129, `docs/decisions/precompact-handoff.md` line 50). Same on main; pre-existing.

**Where.** `lint/stale_cites.py`: `cite_targets` drops the words before the path, so `cited_excerpt` gets no name and gives the file head. `merge/merge.py` `prose_judge_row_block` sends that excerpt to the judge.

**Decision.** `claims-carry-backing` (a definitive prose claim carries its backing, and the judge is shown what each cite points at).

**Retire.** A case in `lint/test_stale_cites.py`, class `CitedExcerptTests`, red first on the current code: `read NAME in PATH` starts at NAME's definition, as `read path name` does. The case goes green when the cite is read that way.

# A ruling claim in noun form passes with no cite

**What.** The commit check reads only claim forms: `per ... ruling`, `under` or `following the owner's ruling`, and an actor who `ruled`. A ruling claim written as a noun passes with no home and no time. Examples: "Owner ruling says the cases go", "The owner's ruling is to drop them", "owner ruling: keep it", "by owner ruling", "the owner has ruled this out". Claude writes these forms in normal work. The step's done check names a bare "owner ruling" too. Round 2 read the bare noun as a claim, and 5 of its 9 hits in history were nouns that claimed nothing, so round 3 dropped it.

**Where.** `lint/check_red_run.py`, the claim pattern `RULING_CITE_RE`.

**Decision.** none

**Retire.** The noun forms above fail with no cite, and the history nouns stay clean ("files an owner ruling", "arbiter ruling card", "the owner ruling's cite"). Cases in `lint/test_check_red_run.py` show both.

# The cite refusal does not say a page must be merged and fetched

**What.** `ARTIFACT_CITES_REASON` in `hooks/guard_merge.py` tells the session to "register the page in the registry". A pushed cite now counts only when its page is registered on origin's default branch. After a registry PR merges, the refusal repeats until `git fetch` runs, and the text names neither the merge nor the fetch.

**Where.** `hooks/guard_merge.py`: `ARTIFACT_CITES_REASON`.

**Decision.** waiting-data-in-repo (git is each artifact's home).

**Retire.** The reason says the page must be "registered on origin's default branch (merged); fetch it". A case in `hooks/test_guard.py` (family roadmap-artifact-cites) shows the refusal text holds both.

# The record branch check reads the checkout's registry, the push check reads origin's

**What.** Rule `roadmap-artifact-cites` judges a pushed cite against the registry on origin's default branch, and against the pushing checkout's own file only when origin's cannot be read. The whole-branch check `check()` in the same module still reads only the checkout's `.claude/layout-extras.json`. A checkout on the record branch has no such file, so `check()` calls every cite there unregistered, and a checkout behind main calls a cite of a newer page unregistered. The two paths can disagree.

**Where.** `lint/check_artifact_cites.py`: `check`, against `registry_ids`.

**Decision.** waiting-data-in-repo (git is each artifact's home).

**Retire.** `check()` reads its registry through `registry_ids`, so both paths judge a cite the same way. A case in `lint/test_check_artifact_cites.py` runs `check()` from an extras-less checkout whose origin holds the registry, and shows no FAIL for a registered cite.

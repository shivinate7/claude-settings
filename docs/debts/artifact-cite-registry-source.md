# The push check reads the registry from the pushing checkout

**What.** Rule `roadmap-artifact-cites` reads the registry from the pushing checkout's `.claude/layout-extras.json`. A checkout on the record branch has no such file, so the check notes "unknown" and judges no cite. A checkout behind main holds an older registry and can deny a clean cite. `check()` in the same module fails all 17 cites on the record branch with no registry. The two paths disagree.

**Where.** `lint/check_artifact_cites.py`: `registry_ids`, `pushed_step_findings`, `check`. `hooks/guard_merge.py`: `record_push_hit`.

**Decision.** waiting-data-in-repo (git is each artifact's home).

**Retire.** Both paths read the registry from one source, origin's default branch, and judge a cite the same way when the pushing checkout has no registry file. A case in `lint/test_check_artifact_cites.py` pushes a clean head from an extras-less checkout and shows no deny and no note.

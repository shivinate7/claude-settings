# Nothing pins or checks the gh version

- **What.** Nothing pins or checks the gh version the merge tool reads. Two merges 7 minutes apart on Nov 24, 2026 behaved differently across a gh upgrade to 2.105.0 at 15:32 CST. Who upgraded gh is unknown.
- **Where.** `merge/merge.py`, `sh()` and `Host.gh`. `skills/project-ops/scripts/protect.py`, `run_gh`. No gh version read in `merge/`, `lint/` or `hooks/`.
- **Decision.** `gh-api-budget` (the merge tool's gh reads through `Host.gh`, with the output stream rule).
- **Retire.** Closed when a case in `merge/test_merge.py` fails on a gh version the tool was not tested on.

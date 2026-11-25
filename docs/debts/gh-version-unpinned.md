# Nothing pins or checks the gh version

- **What.** Nothing pins or checks the gh version the merge tool reads. An ordinary Homebrew upgrade of gh by the owner, to 2.105.0 at 15:32 CST on Nov 24, 2026, changed gh's output, with no sign it would. Two merges 7 minutes apart, one on each side of it, behaved differently.
- **Where.** `merge/merge.py`, `sh()` and `Host.gh`. `skills/project-ops/scripts/protect.py`, `run_gh`. No gh version read in `merge/`, `lint/` or `hooks/`.
- **Decision.** `gh-api-budget` (the merge tool's gh reads through `Host.gh`, with the output stream rule).
- **Retire.** Closed when a case in `merge/test_merge.py` fails on a gh version the tool was not tested on.

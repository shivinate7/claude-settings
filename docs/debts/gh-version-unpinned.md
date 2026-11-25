# Nothing pins or checks the gh version

- **What.** Nothing pins or checks the gh version the merge tool reads. An ordinary Homebrew upgrade of gh by the owner, to 2.105.0 at 15:32 CST on Nov 24, 2026, changed gh's output, with no sign it would. Two merges 7 minutes apart, one on each side of it, behaved differently.
- **Where.** `merge/merge.py`, `sh()` and `Host.gh`. `skills/project-ops/scripts/protect.py`, `run_gh`. No gh version read in `merge/`, `lint/` or `hooks/`.
- **Decision.** `tool-pins` takes this debt over; it stays open until one `gh` line lands in `.tool-versions`. `gh-api-budget` (the merge tool's gh reads through `Host.gh`, with the output stream rule) holds the reads named under What.
- **Retire.** Closed when `.tool-versions` holds a `gh` line and the pin check reads it.

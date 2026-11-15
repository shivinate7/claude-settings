# Cloud refresh skips clear and fork

- **What.** In a cloud session, the refresh hook runs `install.sh --cloud` on `startup` and `resume` only. It does not run on `clear` or `fork`. The cloud `settings.json` also drops the `session_start.sh` entry, because that entry fires on startup. So on `clear` or `fork`, that entry does not run. Every other hook keeps the copy from the last startup or resume. A hook fix on main reaches the session only at its next startup or resume. The `compact` part waits on PR #3188 (adds `compact` to the refresh matcher and case `cloud_compact3`). PR #3188 is not on main yet.
- **Where.** `install.sh`, the cloud refresh hook: `"matcher":"startup|resume"` in the jq that writes `settings.json` (about line 1093, beside `HOOK_CMD`). `hooks/test_install_src.sh`, case `cloud_settings1` (about line 1959), which asserts that matcher (about line 1989). On PR #3188's head (94ca95d52), case `cloud_compact3` pins `clear` as no refresh and no startup entry. Main's `settings.json`, the `session_start.sh` entry (about line 192), lists `startup|resume|compact|clear|fork`.
- **Decision.** `cloud-start-hooks-run-fresh`, cloud start hooks run the code install.sh just copied. Its line that says the `compact` and `clear|fork` entries "fire after the refresh" is wrong for `clear` and `fork`, because no refresh runs for them. The fix rewrites that line.
- **Retire.** The refresh matcher gains `clear` and `fork`, and `compact` too if PR #3188 has not added it. Two cases change with it: `cloud_settings1` (on main) expects the old matcher, and `cloud_compact3` (on PR #3188) expects no refresh for `clear`. The fix flips `cloud_compact3` to expect a refresh and the `session_start.sh` entry to run for source `clear`. Runnable test: `hooks/test_install_src.sh`.

## Ruling

Owner pick item 891 b (relayed by triage, 2026-11-15 13:36 CST): a new gap, not a wanted limit.

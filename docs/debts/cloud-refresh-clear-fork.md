# Cloud refresh skips clear and fork

- **What.** In a cloud session, the refresh hook runs `install.sh --cloud` on `startup` and `resume` only. It does not run on `clear` or `fork`. The cloud `settings.json` also drops the `session_start.sh` entry, because that entry fires on startup. So on `clear` or `fork`, that entry does not run. Every other hook keeps the copy from the last start. A hook fix on main reaches the session only at its next start. The `compact` part waits on PR #3188 (adds `compact` to the refresh matcher). PR #3188 is not on main yet.
- **Where.** `install.sh`, the cloud refresh hook: `"matcher":"startup|resume"` in the jq that writes `settings.json` (about line 1093, beside `HOOK_CMD`). `hooks/test_install_src.sh`, case `cloud_settings1` (about line 1959), which asserts that matcher (about line 1989). Main's `settings.json`, the `session_start.sh` entry (about line 192), lists `startup|resume|compact|clear|fork`.
- **Decision.** `cloud-start-hooks-run-fresh`, cloud start hooks run the code install.sh just copied. Its line that says the `compact` and `clear|fork` entries "fire after the refresh" is wrong for `clear` and `fork`, because no refresh runs for them. The fix rewrites that line.
- **Retire.** The refresh matcher gains `clear` and `fork`, and `compact` too if PR #3188 has not added it. The case `cloud_settings1` expects that matcher. A cloud case with source `clear` expects the refresh to run and the `session_start.sh` entry to run. Runnable test: `hooks/test_install_src.sh`.

## Ruling

Owner pick item 891 b (relayed by triage, 2026-11-15 13:36 CST): a new gap, not a wanted limit.

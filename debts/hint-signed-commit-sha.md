# The trailer hint can name the wrong sha for a signed commit

- **What.** With `log.showSignature=true` in config, git prints a signature line before a signed commit's record. The Drops-lines hint then names a wrong sha for that commit. The verdict does not change.
- **Where.** `misplaced()` in `lint/check_silent_undo.py`: the one `git log -z` read.
- **Decision.** `silent-undo-check-design` (how the check finds a merge that drops lines).
- **Retire.** The read passes `--no-show-signature`. A case with a signed commit and `log.showSignature=true` names the right sha.

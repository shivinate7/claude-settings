# No test covers a skill folder that recovers on retry

- **What.** A transient lock on a skill folder, then recovery, is the common Windows case, and no case covers the recovery loop in `Resolve-Failures`: deleting the loop keeps case skillfail1 green. A new case would model case retry1: start the install child without `-Wait`, hold a landed skill file open with no delete sharing, poll the child's stdout for "retrying in", dispose the handle, then assert the run exits 0 and the skill folder landed.
- **Where.** `install.ps1` (`Resolve-Failures`, skill folder retry); `install-no-gap.test.ps1` (case retry1 is the model).
- **Decision.** none.
- **Retire.** Add the case to `install-no-gap.test.ps1`. It goes red when the skill retry in `Resolve-Failures` is removed and green with it, on a Windows run.

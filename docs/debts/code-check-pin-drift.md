# The pin drift check skips the code-check action

**What.** `bin/ste-changed` warns when CI pins the ste-lint or zizmor action at a commit whose files differ from the session's copy. It does not read `actions/code-check@<sha>` pins. `bin/ci-job --lint` runs this repo's code-check action in place, so a child that pins an older code-check can pass locally and fail in CI, or the reverse. Merge's ready check (`--pinned`) runs the pinned code-check, so it matches CI but gives no signal that the pin is old.

**Where.** `bin/ste-changed`, the `PINNED` table and the `PIN` pattern.

**Decision.** `action-pins-follow-sessions`, CI pins follow the session's tools. It names code-check as a pin that runs in place but is not yet checked.

**Retire.** `bin/ste-changed` reads code-check pins, compared on the action's own files, with its red case in `actions/ste-lint/test_action.py`. That PR deletes this file and rewrites the decision's clause (a) in place.

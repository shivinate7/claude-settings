# The pin drift check skips the zizmor action

**What.** `bin/ste-changed` warns when CI pins the ste-lint action at a commit whose lint differs from the session's copy. It does not read `actions/zizmor@<sha>` pins. `bin/ci-job --lint` now runs this repo's zizmor run.sh in place, so a child that pins an older zizmor action can pass locally and fail in CI, or the reverse. The five child removal lanes will add such pins.

**Where.** `bin/ste-changed`, the `PIN` pattern and `pin_report`.

**Decision.** `action-pins-follow-sessions`, CI pins follow the session's tools. It says other action pins keep the normal rule because they have no local twin; zizmor now has one.

**Retire.** Owner rules either way. Either the drift check reads zizmor pins, compared on `actions/zizmor/run.sh`, or the decision names zizmor under the normal rule. Closed by that ruling, plus its red case or its decision edit.

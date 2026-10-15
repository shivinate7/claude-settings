# Exit 7 under onFailure block is not probed

- **What.** With `onFailure: block`, a timeout refused the call (measured in the 2026-10-12 incident). Exit 7 was not probed.
- **Where.** The gate wrappers, under `onFailure: block`.
- **Decision.** `gate-hooks-fail-closed` (a gate whose script or python is missing refuses the call).
- **Retire.** Probe exit 7 under `onFailure: block`, and record the result in the decision.

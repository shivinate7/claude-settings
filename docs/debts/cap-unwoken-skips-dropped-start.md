# An unwoken cap end skips the dropped-start step

**What.** The alarm step in `actions/ci-alarm/action.yml` now exits 1 when a cap end cannot be woken; main's alarm always exited 0. The dropped-start step has only `if: inputs.dropped-start == 'true'`, which carries the implicit `success()`, so it is skipped whenever the alarm step fails. One unwoken cap end silences the dropped-start alarm for that cycle. A persistent one, such as `cap-wake-needs-pr` in `notes.md`, silences it until the run leaves the 100-run window.

**Where.** `actions/ci-alarm/action.yml` (the dropped-start step's `if`), `actions/ci-alarm/alarm.sh` (the final `exit 1`).

**Decision.** roles-findings-are-debts-or-notes (a finding becomes a debt or a note), and no-merge-onto-red-main (CI alarm for a red main).

**Retire.** Set the step's `if` to `${{ always() && inputs.dropped-start == 'true' }}`. A case in `actions/ci-alarm/test_action.sh` makes the alarm step exit 1 and shows the dropped-start step still runs.

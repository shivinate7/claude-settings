# c166-red-main-brake (lane session_013NEJL2Qq1UpEXTNZR8S2bV)

- c166: green and reviewed. Draft PR #761, head fd7c1b0d. Round 1 (Opus reviewer): CHANGES, 5 findings, all fixed. Round 2 (Sonnet reviewer, rule roles-third-try-steps-up): APPROVE. No round 3, so no net-value test.
- c166 note, possible debt at port: in a repo whose push runs use `cancel-in-progress: true`, a superseded run reads UNKNOWN, and the red-main check refuses until the newer run ends. This repo's push runs do not cancel. Proposed fix: read a cancelled newest run as pending while a newer run of that file is in progress.
- c166 note: a workflow file with no run in the newest 50 base runs is not judged, so it can read green while red. A false refusal is not possible.
- c166 note: run conclusions `action_required` and `stale` read red. The "no check ran" filter matches `classify`'s message text.
- c166 deviation: the round-2 reviewer ran Sonnet (rule roles-third-try-steps-up). The lane brief said Opus.

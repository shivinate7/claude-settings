# c160-main-ref-git243

Status: green, reviewed. Draft PR #740 (main-ref stale-origin fetch on git 2.43), head 930b29e.

- Cause: git 2.43 fetch moves main in its own transaction before origin/main; CI's git 2.56 batches both.
- Fix: on the would-refuse path only, allow when FETCH_HEAD names exactly `new` as `branch 'main' of <origin url>`. No network call.
- Red then green: stale-origin fetch case (2.43), split-fetch replay cases (any git), oid-mismatch case (red with the oid check removed).
- Local gates: main-ref suite PASS, ci-job gates --lint PASS, silent-undo --strict clean, shellcheck clean.
- Review: 1 round, builder opus, reviewer opus, APPROVE.
- Note: no test covers scp-style or credentialed origin URLs. If the normalisation is wrong for them, the hook refuses, which is the old behaviour.

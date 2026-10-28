# c183, the code check skips more data and config files

- Branch code-check-notcode-c183, head d7f91c3b. Draft PR #776 (c183 not_code rows).
- Adds not_code rows for .gz, .xlsx, .onnx, .npz, .nvmrc, .npmrc. The fixture test was red on main with 6 "no row" lines and is green now.
- Local gates PASS. check_silent_undo --strict is clean. Fresh reviewer (sonnet), round 1: approve, no findings.
- State: done. It waits on the orchestrator's batch.

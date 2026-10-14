# A guard timing case fails on a busy runner

- **What.** The rm-var case "64000 bindings before a delete are judged in under 2 s CPU" took 2.14 s on a macOS runner (PR 419). The code was unchanged, so the red was a false alarm.
- **Where.** The rm-var timing case in `hooks/test_guard.py`.
- **Decision.** none
- **Retire.** Bound the case by a ratio to a baseline run in the same job, or by an operation count. A week of macOS runs shows no false red.

# Net-safety-value call has no check

- **What.** No check measures a change's net safety value against main. The hold after round 3 depends on that call, and a reviewer makes it by judgment.
- **Where.** Rule `roles-review-cap-three` in `CLAUDE.md`.
- **Decision.** `hold-unsafe-after-round-3` (after round 3, a guard, gate or check change with zero or negative net safety value is held).
- **Retire.** A check that runs one fixed list of known-bad inputs against the guard and gate code on main and on the change. It counts the inputs the change opens and the inputs it closes.

# Better-than-main call has no check

- **What.** No check decides whether a change holds a safety hole that main lacks. The hold after round 3 depends on that call, and a reviewer makes it by judgment.
- **Where.** Rule `roles-review-cap-three` in `CLAUDE.md`.
- **Decision.** `hold-unsafe-after-round-3` (a change with a safety hole main lacks is held after round 3).
- **Retire.** A check that runs one fixed list of known-bad inputs against the guard and gate code on main and on the change. It goes red when the change allows an input that main refuses or asks about.

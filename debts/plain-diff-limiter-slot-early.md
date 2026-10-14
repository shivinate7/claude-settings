# The plain-diff limiter frees a slot before a hung host call ends

- **What.** A call that outlasts the 25 s limiter timeout frees its slot while the host call may still run. A model call that hangs past 25 s is an example. The 20 s model timeout is passed to the host. This repo does not verify that the host honours it. The cost is unmeasured.
- **Where.** `makeLimiter` in `mods/plain-diff/hooks/lib.mjs`.
- **Decision.** `plain-diff-mod-limits` (plain-diff sends a diff to a model only past the secret filter).
- **Retire.** The host timeout is measured on a hung call. The limiter keeps the slot until the host call ends, or the decision records the result.

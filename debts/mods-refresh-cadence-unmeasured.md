# The marketplace refresh cadence is unmeasured

- **What.** How often the app refreshes a marketplace is unmeasured. So is whether it refreshes while a session is open.
- **Where.** The desktop app's marketplace refresh, for the `claude-settings` marketplace.
- **Decision.** `mods-install-via-marketplace` (mods install from the marketplace, with no installer step).
- **Retire.** The refresh interval and the open-session behavior are measured, and the numbers are recorded in the decision.

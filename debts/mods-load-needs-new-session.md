# A mod loads only in a session that starts after the change

- **What.** A mod loads only in a session that starts after the change. A running session keeps its old mod set.
- **Where.** The plugin load path for mods installed through the marketplace.
- **Decision.** `mods-install-via-marketplace` (mods install through the marketplace).
- **Retire.** Measure how a running session picks up a mod change, and record the result in the decision.

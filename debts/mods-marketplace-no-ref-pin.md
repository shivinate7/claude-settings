# The marketplace source has no ref pin

- **What.** The marketplace source has no `ref` pin. It follows the default branch. A bad merge to main reaches every machine at its next plugin refresh. Review and CI on main are the only guard.
- **Where.** The `claude-settings` marketplace source in `settings.json`.
- **Decision.** `mods-install-via-marketplace` (mods install from the marketplace, with no installer step).
- **Retire.** The source names a ref, or the decision records the accepted risk. A settings test pins the choice.

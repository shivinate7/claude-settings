# The decision-watch log drops a notice's leading whitespace

- **What.** The mod's log folds whitespace, so whitespace at the very start of a notice is lost in the log. The toast keeps it. No notice built today starts with whitespace.
- **Where.** The long-notice split and `log()` in `mods/decision-watch/hooks/register.mjs`.
- **Decision.** `decision-watch-mod-limits` (what the decision-watch mod cannot do yet).
- **Retire.** The NOTICE prefix ends in a non-space mark, so a notice that starts with a space reads back whole. A mod test pins it.

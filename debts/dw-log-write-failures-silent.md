# The decision-watch log fails silently

- **What.** The log is the only output for an ALLOW. The toast shows a FLAG or UNKNOWN too. A lost log write is silent: an empty catch with a 2 s cap, so START may have no END. Any read error resets the log to one line. Whether `$.fs.write` is atomic is unverified.
- **Where.** The log reads and writes in `mods/decision-watch/hooks/register.mjs`.
- **Decision.** `decision-watch-mod-limits` (what the decision-watch mod cannot do yet).
- **Retire.** A failed log write shows a visible line, a read error keeps the log, and `$.fs.write` atomicity is measured on this machine. `mods/decision-watch/decision-watch.test.mjs` pins both.

# No run shows the decision-watch mod judges a Stop

- **What.** Unverified: whether `classic.Stop` reaches a mod in the desktop app, and how long `$` lives after `classic.Stop` returns when the background call is `void shadow`. If either fails, the watch never judges and shows nothing.
- **Where.** The `classic.Stop` handler in `mods/decision-watch/hooks/register.mjs`.
- **Decision.** `decision-watch-mod-limits` (the decision watch runs as a mod on the app's own login).
- **Retire.** In a live desktop session, end a turn that holds a known FLAG case. The mod logs a verdict and shows the toast, and the run is recorded.

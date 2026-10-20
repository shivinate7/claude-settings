# Stop delivery to decision-watch is unproven

**What.** The decision-watch mod has shown no Stop event in the desktop app. Commit 386194af on main already enables the mod and removes the Stop row that ran `hooks/decision_watch.py`. Test 2026-10-16 11:04 CDT, in a resumed session: `/dw` ran the model path, and it showed "Stops seen: 0" with no shadow.log. If no Stop arrives, the watch never judges. Notes ids `dw-stop-row-unproven` and `dw-mod-stop-reach-unproven` cite the same gap in short form.

**Where.** `settings.json`: `enabledPlugins` has `decision-watch@claude-settings`, and no `Stop` row runs `hooks/decision_watch.py`. The mod sits in `mods/decision-watch/`.

**Decision.** `decision-watch-mod-limits`, decision-watch runs as a mod on the app's own login.

**Retire.** Run `/dw` in a brand-new session. Send two short messages first, then `/dw`. The debt closes when "Stops seen" shows 1 or more. If the count stays 0, the owner chooses one: restore the Stop row, or accept the limit in `decision-watch-mod-limits`.

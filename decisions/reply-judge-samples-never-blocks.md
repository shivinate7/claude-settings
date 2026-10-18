# The reply judge samples and never blocks

## The ruling

The Stop reply judge is `hooks/reply_judge.py`, a command hook (owner ruling 2026-10-12), because a prompt hook cannot exit on a field in code.

- It judges 1 Stop in 5. Only Stops that carry a reply count: Stops 1, 6, 11, and so on (owner ruling 2026-10-13 14:40 CDT). Reason: the judge is advisory, so a model call on every turn end costs calls and latency, and a sample still shows the owner the pattern.
- A damaged, missing or unwritable counter means that Stop is judged. It never refuses and never crashes (`gate-hooks-fail-closed`). A frozen counter therefore means judge every Stop (owner ruling 2026-10-13 17:52 CDT).
- The model call is `decision_watch.invoke_model`, the one home. Model and effort are the reply judge row of the model table (`subagent-model-cap`).
- A finding never blocks (owner ruling 2026-10-13 11:33 CDT). The hook runs `async: true` and passes the finding as a note at the start of the next turn. Reason: a block came after the owner had read the reply, so the session sent the reply twice. The report-shape gate still blocks.
- It fails open. An error, a timeout or an odd answer prints one stderr line and blocks nothing.
- Its rules are `output-start-with-point`, `style-cut-narration` and `output-never-paste-passing-output`. They stay `unmechanized` in `lint/rule_mechanisms.json` until the hook catches a real defect.

Kind: process
Home: hooks/reply_judge.py

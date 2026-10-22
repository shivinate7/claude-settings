# Sessions ask the advisor first

## The ruling

Owner, 2026-10-22: a session with a question for the owner first runs `ListAgents`. When the advisor runs, the session sends it the question by `SendMessage`. It keeps working on what does not depend on the answer. With no advisor, it asks the owner.

- **The advisor.** A Claude Code session outside claude-settings, in its own config folder. It holds the owner's plan and rulings, and claude-settings does not bind it. Its sessions folder is a junction to this machine's `~/.claude/sessions`, so `ListAgents` lists it and `SendMessage` reaches it. A session's name is the first word of its folder and a short code. The advisor's name is `advisor-` and a random suffix of 2 to 6 characters, such as `advisor-cf`. `ListAgents` shows no folder, so the name is the only mark. Known gap: a session in any folder that starts with "advisor", such as `wt\advisor-asks`, shows as `advisor-cf`. Its name matches the advisor's name. Rule: no lane folder name starts with "advisor".
- **Owner only.** Always the owner, never the advisor: a merge, raising a model to Opus, the override pass (`owner-override-pass`, the owner's typed pass), an act that cannot be undone, a goal change, and anything the advisor marks "ask the owner".
- **Not the owner's word.** An advisor answer lifts no guard and grants no pass.
- **The report.** The label "Decided by the advisor", between Deviations and Input Needed, lists each advisor answer. `lint/report_gate.py` accepts it in that place.
- **The message check.** `hooks/sendmessage_state.py` and the SendMessage prompt judge let a message to the advisor through. A question to the advisor is never mid-task talk (`parallelism-no-mid-task-talk`).

Unknown: whether a hook should send the question to the advisor. `guard_core.session_records` can see the advisor, but a hook cannot judge which questions only the owner answers. The rule stays in `CLAUDE.md` until a session asks the owner a question the advisor could answer.

Kind: process
Home: rule:questions-ask-advisor-first

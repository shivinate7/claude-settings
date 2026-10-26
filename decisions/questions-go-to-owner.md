# Questions go to the owner

## The ruling

Owner, 2026-10-26: a session with a question brings it to the owner. The question names what the session does meanwhile, or that it waits. The session keeps working on what does not depend on the answer.

- **No outside advisor.** The terminal advisor (a session named `advisor-` and a short suffix, started from its own config folder on Windows) is retired. No rule, hook or report label sends a question to it.
- **The built-in advisor.** `advisorModel` in `settings.json` stays. It is a second opinion that a session calls on its own work, and it sees only that session's conversation. It answers no question for the owner and decides nothing, so it lifts no guard and grants no pass.
- **The report.** The labels are Done, Deviations, Input Needed, Next. `lint/report_gate.py` refuses any other label.
- **The message check.** `hooks/sendmessage_state.py` and the SendMessage prompt judge treat every receiver as a peer.

Kind: process
Home: rule:questions-go-to-owner

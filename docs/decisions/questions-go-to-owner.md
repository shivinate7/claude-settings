# Questions go to the owner

## The ruling

Owner, 2026-10-26: a session with a question brings it to the owner. The question names what the session does meanwhile, or that it waits. The session keeps working on what does not depend on the answer.

- **No outside advisor.** The terminal advisor (a session named `advisor-` and a short suffix, started from its own config folder on Windows) is retired. No rule, hook or report label sends a question to it.
- **The built-in advisor.** `advisorModel` in `settings.json` stays. It is a second opinion that a session calls on its own work, and it sees only that session's conversation. It answers no question for the owner and decides nothing, so it lifts no guard and grants no override.
- **The waiting page** (owner, 2026-10-26). One page per repo or project holds every item waiting on the owner, from every session (ruling 1a). A save by the owner on that page counts as the owner's grant for the item it answers (ruling 2a). The terminal question box stays, and it links the page (ruling 3a). Skill `waiting-page` holds the protocol. A repo with no page uses the box only.
- **The report.** The labels are Done, Deviations, Input Needed, Next. `lint/report_gate.py` refuses any other label.
- **The message check.** The two judges in `hooks/sendmessage_state.py` treat every receiver as a peer.

Kind: process
Home: rule:questions-go-to-owner

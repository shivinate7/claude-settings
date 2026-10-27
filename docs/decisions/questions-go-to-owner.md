# Questions go to the owner

## The ruling

Owner, 2026-10-26: a session with a question brings it to the owner. The question names what the session does meanwhile, or that it waits. The session keeps working on what does not depend on the answer.

- **No outside advisor.** The terminal advisor (a session named `advisor-` and a short suffix, started from its own config folder on Windows) is retired. No rule, hook or report label sends a question to it.
- **The built-in advisor.** `advisorModel` in `settings.json` stays. It is a second opinion that a session calls on its own work, and it sees only that session's conversation. It answers no question for the owner and decides nothing, so it lifts no guard and grants no override.
- **The waiting page** (owner, 2026-10-26). One page per repo or project holds every item waiting on the owner, from every session (ruling 1a). A save by the owner on that page counts as the owner's grant for the item it answers (ruling 2a). The terminal question box stays, and it links the page (ruling 3a). Skill `waiting-page` holds the protocol.
- **No box while work runs** (ruling 3b, which narrows 3a). Owner, 2026-10-26, waiting page item 30: questions should not hang, so the session "gets back to orchestrating". Triage read that as this design, on roadmap step c84; the owner asked for the outcome, not this text. While an agent, a lane or a background command of this session runs, or starts in the same response, the session opens no question box. It asks in its reply and on the page, keeps orchestrating, and reads the answer at its next turn. With nothing running, the box stays. Why: a box stops the session until the owner answers, and its running work does not stop. A UI session waited on a box while its agents ran on, filled the disk and crashed. Its brake ran only once the owner answered. A timer that expires the question is out: rule `outcomes-mechanize-rules` (no timer) refuses it, and a hook cannot close a box already on screen. A repo with no page asks in the reply or the box only.
- **Owners read their own answers** (owner, 2026-10-26). Each waiting item names its owning session. That session reads, routes and closes the item at each wake. No session relays an answer.
- **The report.** The labels are Done, Deviations, Input Needed, Next. `lint/report_gate.py` refuses any other label.
- **The message check.** The two judges in `hooks/sendmessage_state.py` treat every receiver as a peer.

Kind: process
Home: rule:questions-go-to-owner

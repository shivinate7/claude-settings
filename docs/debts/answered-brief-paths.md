# Briefs sent by agent and workflow tools escape the answered-claim check

**What.** The answered-claim check judges only the text fields of SendMessage, the remote send, and create_session. It does not read the `prompt` of Agent, Task or Workflow, or the `message` of send_later. A brief that says an item is answered passes through those tools unchecked. Those are the likeliest paths for a brief, so the check misses the case it exists for.

**Where.** `hooks/answered_claims.py`, `TEXT_FIELDS` at line 42. The map holds two tools and omits the agent, task, workflow and send_later fields.

**Decision.** `answered-claims-match-page` (a claim that a waiting-page item is answered matches the page).

**Retire.** A brief with an unanswered item's claim, sent through Agent, Task, Workflow or send_later, is refused, as SendMessage already refuses it. A case in `hooks/test_answered_claims.py` shows it closed: one such claim is refused on each of those four tools.

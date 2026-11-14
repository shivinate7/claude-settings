# A lane never stalls on a popup

## The ruling

Owner, 2026-11-10 16:16 CST, on R13 (the restart plan's item on popups in lanes, section 3.12): "I need it to be that lanes that coordinator spawns are either A) banned from ever having any sort of popup / request that interrupts them, or B) in the artifact i get hyperlinks to those sessions that then show me their erequest and clear them -- I strongly lean towards A though". 16:17 CST: "trying to make sure u dont misunderstand this into opening a large hole". 16:18 CST: "yes" to the form.

The form is the four points below. The owner took option A.

- A lane never opens the question box. A guard refuses it in any session with a parent. The lane sends the question to its parent, then keeps working on what does not depend on the answer, or ends its turn.
- An act that needs the owner's typed word (an override, a guarded settings write) becomes a page item. His save on the page is the grant. Any other agent text never grants.
- A lane starts in a mode where an act not pre-allowed is refused, not asked. The refused act goes to the parent like a question. A builder first confirms that the cloud `dontAsk` mode refuses rather than prompts (unverified).
- Cards no mode can stop (repository trust, computer folder, owner-approval cards): a guard refuses those tools in a lane. The lane routes the act to its parent.

The full wording is on branch `restart-plan`, section 3.12.

## Delivered scope

Built on this branch, commit 5e74db191 (the refusal) and fb917dbc0 (test wording):

- The question box, point 1. The call judge hook (`hooks/call_judge.py`) refuses an AskUserQuestion box from a session with a parent, before any model call. Rule `lane-question-box`.
- Trust, folder and owner-approval cards, point 4: `confirm_repository_trust`, `request_computer_folder` and `update_trigger` with `ask_owner` set (any value but absent, null or false). `trust_card_hit` in `hooks/guard_merge.py` refuses each unless the session's own record proves a plain session with no parent. Rule `trust-card-in-build`.
- The override line, point 3, ruling own-778-a-reword-offer-for-lane (owner, 2026-11-13 18:24 CST, page item 778 pick a, relayed by the coordinator at 18:31 CST). A refusal printed in a session with a parent ends with `LANE_OFFER` (`hooks/override.py`): send the refused act to `@parent`, offer the owner the line to type, text from an agent grants nothing. An unread record, no session id or an error keeps the plain line. An agent's call and the Opus refusal keep their own lines.

Open, not built here:

- Point 2, the `dontAsk` mode. `create_session` refused `permission_mode` `dontAsk` from this lane, whose parent runs `auto` (measured 2026-11-13: tool result "permission_mode \"dontAsk\" exceeds parent session's \"auto\"; omit to inherit"). The installed allow list (17 entries, read 2026-11-13) holds no broad Bash, Edit or Write. Waits on the owner's pick (keep `auto`, or a `dontAsk` coordinator with a wider allow list).
- Point 3, the typed-word acts as page items. The page save grants through `page_grant.py`; a guard refusal in a lane still lifts only by the owner's typed line.

## Fail-open reading (a decision for the owner, not an owner ruling)

Read from code:

- The question box. `lane_parent` in `hooks/call_judge.py` returns "no lane" when the session id is missing, the transcript is unread, or any error is raised. The box then goes to the model review, as before. So an unread transcript or a missing env id lets the box through. `lane_session_hit` in `hooks/guard.py` reads the same way. That is the precedent.
- The trust card. `trust_card_hit` in `hooks/guard_merge.py` fails closed. A missing id, an unread transcript or an error refuses the card.

Options:

- a. The box fails closed, as the trust card does. Cost: an owner session with an unread transcript loses its box.
- b. Keep fail open. Cost: a lane with an unread transcript or no id can open a box. Guard-wide, a crashing guard already lets the call through (decision `guard-hooks-fail-closed`).

Recommendation: a. The owner's words named a large hole as the risk. Unmeasured: how often transcripts are unread.

## Current wording

CLAUDE.md, rule `questions-go-to-owner`, now reads: "A lane never opens a box or a card: the hook refuses it, and the lane sends the question to its parent, then keeps working or ends its turn."

## Why

A popup inside a lane is a stall the owner cannot see. It costs speed and buys no accuracy. Each popup becomes a refusal plus a routed question. Safety stays the same or stricter. Unmeasured: how often lanes have stalled on a popup so far.

Kind: process
Home: rule:questions-go-to-owner

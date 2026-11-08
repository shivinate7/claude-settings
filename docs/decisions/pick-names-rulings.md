# A departing pick names the rulings it checked

## Ruling

Step pick-ack-past-ruling (filed by triage, 2026-11-08 08:25 CST). A pick that departs from main, taken by a lane or agreed to by a coordinator, names the decisions it checked. When it names none, the guard asks.

- A pick a session takes carries the `Departs from:` line of decision `port-keeps-behaviour`. Its message also carries a line `Checked: <id>[, <id>...]`.
- A reply to a session whose newest message to this one carried a `Departs from:` line is an agreement to that pick, or a refusal of it. The first such reply carries the `Checked:` line too.
- An id counts only if the past-ruling search of decision `question-form` (`question_form.past_rulings`) returns it. A made-up id does not count.
- Guard rule `pick-names-rulings` (`guard_merge.pick_ack_hit`, run by `hooks/guard.py` on `mcp__claude-code-remote__send_message`) asks when the line is missing or names no known id. The owner override lifts it (decision `owner-override`).

Mistake it stops: at 07:59 CST on 2026-11-08 the coordinator agreed to a lane's pick to refuse a top-level `git -C` write into an agent worktree. Neither session searched the decisions, and the pick went against decision `agent-worktree-discard-is-noted`. Review round 1 caught it at 08:23 CST. Harm: a guard that refuses an owner-allowed act ships, or a review round is spent finding it.

Cost: a message with no pick and no inbound pick reads only its own text and the transcript, with no process. A message that trips the check runs one past-ruling search (one git read of the roadmap step notes). No model call, no file written.

Scope: the remote `send_message` only. An in-process `SendMessage` to an agent of the same session is out of scope.

Kind: process
Home: hooks/guard_merge.py

# A coordinator's pick reaches the page writer in the same turn

## The ruling

The 15 Nov ruling, step `page-no-preselected-pick` (no preselected pick on the page), set the page's pick rule: no pick is preselected. The page shows each pick a session takes for the owner as a taken-pick card that he can overrule (step `page-taken-picks-area`). Decision `page-never-preselects` holds the owner's 13 Nov words that started it.

Rule `pick-reaches-page` makes a coordinator's pick reach that card. It reaches the page only through the page writer.

- Mistake: a coordinator takes a pick for the owner and sends it to a lane or another session. It does not send the pick to the page writer in the same turn. The page writer never puts it on the page, so the pick vanishes for the owner.
- Harm stopped: the owner cannot see or overrule a pick taken for him. Step `pick-reaches-page` records 19 picks on 12 Nov with no page item until 12:13 CST. It records the owner's 12 Nov ask (12:08 CST) as: he cannot see coordinator picks anywhere to overrule them.
- The pick section vanished once. The 15 Nov change removed its `stands` fields, and the section went with them (step `page-taken-picks-area`). That loss came from the page, not from a send. This rule holds the send only. The export check that would catch that loss is a separate check, named in step `page-taken-picks-area`.

## Rule pick-reaches-page

- Refuses (deny) a `send_message`, or a `create_session` whose prompt carries the pick, from a coordinator when all of these hold:
  - The sender's newest own `get_session` record in the transcript carries the coordinator build tag, `cs-build:coordinator`.
  - The message has a line that opens `Coordinator pick`, `Coordinator picks:` or `(Coordinator pick`, after optional markdown marks, in any case. A line such as `Coordinator picks up the lane` is no marker.
  - The target is a session other than the page writer, or a `create_session` (which has no writer target). The page writer is the writer named by the newest meta/page read in the transcript. A transcript with no such read names no writer, and the pick is refused: the refusal says to read meta/page first.
  - The turn (the records after the last human message) holds no delivered send to the page writer whose text also has a `Coordinator pick` line. Agent records do not count.
- The refusal names the route, not the item. It says to send the pick to the page writer first, as a taken-pick card, then send the message again. It names no `stands` item and no `pick` field. The 15 Nov ruling removed both.
- Only a coordinator's sends are judged. A lane's message is not.
- An override lifts it (decision `owner-override`, the owner's typed override).
- The Stop-time sibling, decision `decisions-reach-a-clickable-pick`, checks a pick with options in a reply. This rule checks a message sent to a session.

## Fails open, and why

The rule passes when an input is unread:

- no remote session id, or one of another shape;
- no transcript, or no `get_session` record of the session's own id with the coordinator tag;
- an error inside the judge.

Each of these prints one stderr line that names the rule, so the owner can see the rule did not judge.

Why: the rule judges a route. A route the guard cannot read cannot be shown broken. A refusal on a guess would teach the reader to scroll past it (decision `guard-that-cries-wolf-is-spent`). A guard that crashes lets the call through (decision `guard-hooks-fail-closed`).

## Known holes

Each hole is one Claude could fall into by mistake (decision `guard-guards-mistakes-only`).

- The marker: a pick whose line does not open with one of the marker forms, such as `Pick:`, or a pick inside a sentence, is not judged.
- The tool: only `send_message` and `create_session` are read. A pick sent through a Bash `mail send` is not judged.
- The filing: the writer send passes on its marker alone. The rule does not check that the writer files an item.
- A quote: a message that quotes an old pick at a line start is refused as a new pick. This is a false alarm. Move the quote off the line's start to lift it.

## Cost

- A message with no pick line: no read.
- A pick-line message from a session that is not a coordinator: one transcript read (the own-record scan).
- A pick-line message from a coordinator: two transcript reads (the own-record scan, then the turn reader). How often a pick line is sent is unmeasured.
- No network, no file written, no process kept.

Protected by the `pick-reaches-page:` cases in `tests/guard/s43700-taken-pick-send.py`. Red on main before the rule: a pick sent to a lane with no writer send this turn is refused. Green after: the same pick passes once the writer got it this turn, and a message with no marker passes.

Kind: process
Home: hooks/guard_merge.py

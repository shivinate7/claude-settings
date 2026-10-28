# A port keeps the existing app's behaviour

## The ruling

Owner, 2026-10-27 15:32 CDT: when a session ports or redesigns an existing app, the working app already answers most questions. The session reads it and asks only about a change.

- The existing app's behaviour is the default. Each choice cites where it was read: file and symbol.
- A question goes to the owner only when the work departs from that behaviour. It says so in a "Departs from: <file>:<symbol> — <what changes>" line.
- A port question is never marked blocking. The session keeps working on the default.
- A question that the code or a standing grant answers is not asked. Before it asks, a session reads the repo's CLAUDE.md for standing grants (owner, 2026-10-27 15:51 CDT). A grant the owner gives in chat lands in the repo's CLAUDE.md or the merge tool's config, never only in a hand-off.
- Rule `building-port-keeps-behaviour` holds the text. The designer, builder and Plan agents carry one line each.
- Guard rule `port-question` (`hooks/guard.py`): the waiting-page writer refuses an `ArtifactData` set or update to `items`, also each set in a batch and data read from `file_path`, when the item has kind `decision` or `task`, is on a port, and has no line starting "Departs from:" or has `holds`. On a port means field `port` is true. With no `port` field, the words port, ports, ported, porting, redesign, redesigns or redesigned, not followed by a digit or "number", in the title, context or holds. `port: false` is the writer's word that the item is not a port. An update is judged on the fields it carries. An unreadable data file passes. This guard is built against a named incident, the first one below. It landed 2026-10-28.
- Reply judge (`hooks/reply_judge.py`, a model, never blocks): it judges every Stop whose reply says "blocked on". It flags work blocked on, or an Input Needed item marked blocking, a question about a port, and a port question with no "Departs from:" line. It never flags a question that says how the work departs and is not marked blocking.

Incidents:

- 2026-10-27 15:32 CDT: in the Duo "Card in Hand" port of Manifest's web app to the phone app, a session marked its plan blocked on what happens to Suspense cards when Card in Hand closes. The web app already answers it. Earlier the same work invented an "end of mail day" the app does not have.
- 2026-10-27 15:51 CDT: an orchestrator asked the owner to merge although its repo held a standing merge grant, and asked about a "Take all" detail a reviewer had held.

Kind: process
Home: rule:building-port-keeps-behaviour

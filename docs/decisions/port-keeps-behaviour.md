# A port keeps the existing app's behaviour

## The ruling

Owner, 2026-10-27 15:32 CDT: when a session ports or redesigns an existing app, the working app already answers most questions. The session reads it and asks only about a change.

- The existing app's behaviour is the default. Each choice cites where it was read: file and symbol.
- A question goes to the owner only when the work departs from that behaviour. It says so in a "Departs from: <file>:<symbol> — <what changes>" line.
- A port question is never marked blocking. The session keeps working on the default.
- A question that the code or a standing grant answers is not asked. Before it asks, a session reads the repo's CLAUDE.md for standing grants (owner, 2026-10-27 15:51 CDT). A grant the owner gives in chat lands in the repo's CLAUDE.md or the merge tool's config, never only in a hand-off.
- Rule `building-port-keeps-behaviour` holds the text. The designer, builder and Plan agents carry one line each, copied, because each agent reads its own file first and not the rule file.
- Guard rule `port-question` (`hooks/question_form.py`, run by `hooks/guard.py`) refuses an `ArtifactData` set or update to `items`. It reads each set in a batch and data read from `file_path`.
  - It judges only a call whose `url` is this repo's waiting page (`layout.waiting_page`). A repo with no page is not judged.
  - It judges an item of kind `decision` or `task`. An item with no kind passes.
  - It refuses a port item that has no line starting "Departs from:" or that has `holds`.
  - A port item has field `port` true. With no `port` field, it is an item whose title, context or holds says ported, porting, "port of", "port to", "ports the", redesign, redesigns, redesigned, redesigning, "rewrite of" or "rebuild of". Bare "port" is not a signal.
  - `port: false` is the writer's word that the item is not a port.
  - An update is judged on the fields it carries. An unreadable data file passes.
  - It is built against a named incident, the first one below. It landed 2026-10-28.
  - Cost: every `ArtifactData` call, reads included, starts the guard process. The guard writes no file unless it denies.
  - Known limit: the incident's own wording ("Duo version of the web screen", `holds` set, no `port` field) has no port word and passes. The reply judge is the backstop.
  - Known limit: an update cannot see the stored `port` field. The writer carries `port: true` again on each update to a port item.
- Guard rule `question-departs` (`hooks/question_form.py` `departs_hit`, run by `hooks/guard.py`, `hooks/call_judge.py` and `lint/report_guard.py`) refuses a question to the owner that carries no valid "Departs from: <what on main> — <what changes>" line (owner ruling, 2026-10-30 17:18-17:24 CDT: a question that restates main is not a question).
  - It judges a chat question box with two or more options, a waiting-page decision set, an update that carries `kind` decision and `context`, and an Input Needed item that offers a pick. It runs after the question form passes. A closed item passes. An update with `context` and no `kind` passes, as under the form: the stored kind is unseen. A stood pick (`stands: true`) still needs the line.
  - A line may carry a bullet ("- ", "* ") or a bold label, and CRLF endings are read. The separator is " — ", an unspaced "—", " - " or " -- ". Every such line in the text must be valid.
  - It refuses no line, an empty line, no separator, an empty side, a side that is only an angle-bracket placeholder (the template copied), and a no-change word in the first clause of the change side (before its first ";", or the whole side with none): none, nothing, n/a, no change, no difference, unchanged, stays, keeps, as today, as on main, as before, same as, identical to, already. A `context` str_replace is refused when its old_str or new_str holds a Departs from line and new_str holds no valid one.
  - A new thing writes "Departs from: main — adds <X>". A restatement of main is not asked: the session acts on main.
  - It is built against a named incident, the third one below. It landed 2026-10-31.
  - Cost: no extra process. The same guard, call-judge and Stop-hook runs read the one predicate, a regex over the text already in hand. It writes no file unless it denies.
  - Known limit: text cannot tell whether a claimed change really differs from main. `call_judge`'s model is the chat backstop.
- Reply judge (`hooks/reply_judge.py`, a model, never blocks): it judges every Stop whose reply says "blocked on". It flags work blocked on, or an Input Needed item marked blocking, a question about a port, and a port question with no "Departs from:" line. It never flags a question that says how the work departs and is not marked blocking. Cost: one Haiku call per Stop that says "blocked on".

Incidents:

- 2026-10-27 15:32 CDT: in the Duo "Card in Hand" port of Manifest's web app to the phone app, a session marked its plan blocked on what happens to Suspense cards when Card in Hand closes. The web app already answers it. Earlier the same work invented an "end of mail day" the app does not have.
- 2026-10-27 15:51 CDT: an orchestrator asked the owner to merge although its repo held a standing merge grant, and asked about a "Take all" detail a reviewer had held.
- 2026-10-30: a lane's "departures" said "Opus above a role's row stays the existing ask", which restates decision agent-model-cap.

Kind: process
Home: rule:building-port-keeps-behaviour

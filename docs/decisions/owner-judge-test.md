# A waiting-page decision reaches the owner only when he can judge it

## The ruling

A session asks the owner a decision only when he can judge it from what he already knows. Owner, 2026-10-29 13:44 CDT, decision `session-tiers`: "I shouldn't be expected to be around to do something I'd already signed off for". Before it writes a decision to the waiting page (skill `waiting-page`), the session runs the owner-judge test: can the owner judge this from what he already knows? An undoable choice about internals he has no stake in is not asked. The session takes its own pick and sets `stands: true`.

A question stays only when it touches one of five things: his goals, his money, a risk he would care about, a rule, or an act that cannot be undone. The decision names which, in a line in `context`.

- A waiting-page decision carries a line in `context` that starts `Your stake:`. The kind comes first after the colon: one of `goal`, `money`, `risk`, `rule`, `cannot undo`. Text follows it, saying what the pick costs him. The guard reads only this line, in any case, at a line start. The same words in the title, an option, `why` or elsewhere in `context` do not count.
- Guard rule `owner-judge` (`hooks/guard.py`, constant `OWNER_STAKES`) refuses an `ArtifactData` set to `items` of `kind: decision`, or with no `kind`, whose `context` has no such line. It also judges an update that carries `kind: decision` and `context`. It also judges a `str_replace` on `context` whose `old_str` holds the line and whose `new_str` does not. It reads each write in a batch and data read from `file_path`.
  - It judges only a call whose `url` is this repo's waiting page (`layout.waiting_page`).
  - It passes an item with `stands: true`, an item with `port: true` (its Departs from line is the stake), a task, an update with only status, rank or other fields, and a call to another artifact.
  - It also passes a closed item (`status: "closed"`). A closed item asks the owner nothing, and the chat-answer flow writes one.
  - It reads last. Each older rule keeps naming its own refusals.
  - The reason names `Your stake`, the five kinds, and the way out: take your own pick and set `stands: true`.
  - It is built against a named incident, below. It landed 2026-10-30.
  - Cost: no new process. It runs inside the guard process that every `ArtifactData` call already starts. It writes no file unless it denies.
  - Known limit: the guard sees the line, not whether its stake is true. A line with a false stake passes.
  - Known limit: an update that carries `context` but no `kind` is not judged, because the guard cannot see the stored kind. The writer carries `kind: decision` again on a context update.
  - Known limit: a whole-item update of an open decision written before the rule is refused when its context has no line.

Incident:

- 2026-10-28 13:40 CDT, waiting item 34 (roadmap step c95, step 2): a decision asked which CI job runs a check. It turned on CI internals in which the owner has no stake. He saved option b with the note "i really can't figure out how to decide". The session could have taken its own pick.

Kind: process
Home: rule:questions-go-to-owner

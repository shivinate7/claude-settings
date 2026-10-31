# A waiting-page decision reaches the owner only when he can judge it

## The ruling

A session asks the owner a decision only when he can judge it from what he already knows. Owner, 2026-10-29 13:44 CDT, decision `session-tiers`: "I shouldn't be expected to be around to do something I'd already signed off for". Before it writes a decision to the waiting page (skill `waiting-page`), the session runs the owner-judge test: can the owner judge this from what he already knows? An undoable choice about internals he has no stake in is not asked. The session takes its own pick and sets `stands: true`.

A question stays only when it touches one of five things: his goals, his money, a risk he would care about, a rule, or an act that cannot be undone. The decision names which, in the stake of its Problem line.

- A waiting-page decision carries a line in `context` that starts `Problem (<stake>):`. The stake is one of `goal`, `money`, `risk`, `rule`, `cannot undo`. Text follows the colon: the problem in one plain sentence, and why it needs his word. The line is one of the three form lines of decision `question-form`, which holds the stood-pick exemption. The check reads only that line, in any case, at a line start. The same words in the title, an option, `why` or elsewhere in `context` do not count.
- Guard rule `owner-judge` (`hooks/question_form.py`, constant `OWNER_STAKES`, run by `hooks/guard.py`) refuses an `ArtifactData` set to `items` of `kind: decision`, or with no `kind`. It refuses a Problem line that is bare, whose stake is outside the set, or that has no stake on a decision that is not a stood pick. A decision with no Problem line at all is refused by rule `question-form`. It also judges an update that carries `kind: decision` and `context`, and a `str_replace` on `context` that leaves the Problem line bare or with a stake outside the set. It reads each write in a batch and data read from `file_path`.
  - It judges only a call whose `url` is this repo's waiting page (`layout.waiting_page`).
  - It passes a task, an update with only status, rank or other fields, and a call to another artifact. A port needs the Problem line too: its Departs from line is not the stake.
  - It also passes a closed item (`status: "closed"`). A closed item asks the owner nothing, and the chat-answer flow writes one.
  - It reads after each older rule, which keep naming their own refusals.
  - The reason names the Problem line, the five stakes, and the way out: take your own pick and set `stands: true`.
  - It is built against a named incident, below. It landed 2026-10-30.
  - Cost: no new process. It runs inside the guard process that every `ArtifactData` call already starts. It writes no file unless it denies.
  - Known limit: the check sees the line, not whether its stake is true. A line with a false stake passes.
  - Known limit: an update that carries `context` but no `kind` is not judged, because the guard cannot see the stored kind. The writer carries `kind: decision` again on a context update.
  - Known limit: a whole-item update of an open decision written before the rule is refused when its context has no line.

Incident:

- 2026-10-28 13:40 CDT, waiting item 34 (roadmap step c95, step 2): a decision asked which CI job runs a check. It turned on CI internals in which the owner has no stake. He saved option b with the note "i really can't figure out how to decide". The session could have taken its own pick.

Kind: process
Home: rule:questions-go-to-owner

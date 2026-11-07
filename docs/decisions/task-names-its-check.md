# A waiting-page task names the check that shows only the owner can do it

## The ruling

A session never hands the owner an act that a session can do. When the cloud refuses an act (for example, the proxy answers 403 to a branch delete), the session first asks a session on the owner's computer to do it (Remote Control: `list_computer_folders`, then `request_computer_folder`). Only after that try does it put a task on the waiting page (skill `waiting-page`).

- A waiting-page task carries a line in `context` that starts `Why yours:`. The line names why only the owner can do the act. It also names the check that showed it, such as the try on a session on the owner's computer and its outcome.
- Guard rule `task-names-check` (`hooks/question_form.py`, run by `hooks/guard.py`) refuses an `ArtifactData` set to `items` of `kind: task` whose `context` has no such line. The line needs text after the colon. It also judges an update that carries `kind: task` and `context`. It also judges a `str_replace` on `context` whose `old_str` holds the line and whose `new_str` does not. It reads each write in a batch and data read from `file_path`.
  - It judges only a call whose `url` is this repo's waiting page (`layout.waiting_page`).
  - It passes an update with only status, rank or other fields (the writer re-ranks by update), a decision, and a call to another artifact.
  - The reason tells the session to ask a session on the owner's computer first, and to add the line.
  - It is built against a named incident, below. It landed 2026-10-29.
  - Cost: no new process. It runs inside the guard process that every `ArtifactData` call already starts. It writes no file unless it denies.
  - Guard rule `task-why-cited` (same module and run) judges the line's cite. A capability reason needs `(route <id>)`, an id whose row on this surface says refused or asks. Or it needs `(measured <YYYY-MM-DD>, <check and result>)`. `CAPABILITY_RE` in `lint/report_guard.py` holds the verbs. The rule refuses a capability verb with no cite, a cite whose row says the act works, an id no row holds, and a measured cite with no date. The page reads no refusals file, so a tool name in backticks is no cite. A rows file that does not read, or a row only on another surface, passes. The verdict is `why_yours_verdict` in `lint/report_guard.py`, the one home the Stop hand-off check also calls (decision `claims-carry-backing`, part (v)). A line with no route cite reads no file.
  - A `str_replace` on `context` carries the edit, not the item. Departure: the stored text comes from the session transcript, not the store, which no hook can reach. The guard finds it in the payload's `transcript_path`.
    - Source one is the newest read of the item that shows it at the write's `if_version`. A read is a get, a list or a query of `items` with no `out_dir`. Each document in the result, with its version, is stored text at that version.
    - Source two is this session's own successful earlier write that returned that version, replayed onto the text it was pinned to. A write is replayed only when its result is one line with an id and a version and no data object. A result with data, or with no parseable version, is not replayed. The shape of a failed pinned write's result is unmeasured: the tool says only that it names the current version. If that shape matches, the failed write is replayed as landed, and an edit pinned to it with no re-read is judged on stale text. The tool tells a session to re-read in that case. A set or update that names a file is not replayed: the guard never sees its content.
    - A stale pinned write writes nothing (the ArtifactData tool's own description, read 2026-11-07). So a write at a version other than the one read is never judged on that read.
    - The write result's shape is unmeasured against a real transcript.
    - An agent's reads live in `<session>/subagents/agent-<id>.jsonl`, which the guard does not read. So a read made only by an agent asks.
    - The guard applies `old_str` to `new_str`, once or all with `replace_all`, and judges each Why yours line (`stored_why_hit` in `hooks/question_form.py`). Every write in the call is judged from one read of the transcript, and a deny wins over an ask.
    - A false line is denied. Anything unknown is asked, with the same rule id: no `if_version`, no matching read, a version mismatch, an unreadable transcript, an `old_str` found zero times or more than once, or a write result that does not replay. The matched text names the cause.
    - The reader is `paired_uses` and `_reads_items` in `hooks/feedback_guard.py`, the one home, and `local_time._records` for the document lines. The cite tokens of `new_str` are also judged on their own, with no transcript (`cite_tokens_verdict` in `lint/report_guard.py`). That check runs before the stored read.
  - Cost of the stored read: the whole transcript is parsed once per judged call, and not at all for any other write. No process starts. `feedback_guard` loads inside the guard process on that path only. `report_guard` loads on that path and on any task set or update that holds a Why yours line.
  - Known limit: the guard checks the cite, not whether the check it names was run. A route row cite or a dated measured cite with a false result passes. The owner can follow the cite to verify it. No check reads a row's age yet (decision `claims-carry-backing`, Not built). Still passing: a capability word outside `CAPABILITY_RE`. An asks-row cite that is not matched to the act. A second line of a wrapped Why yours line. A row on this surface whose outcome is unknown.
  - Known limit: an update that carries `context` but no `kind` is not judged, because the guard cannot see the stored kind. The writer carries `kind: task` again on a context update.

Incident:

- 2026-10-28, item 39: the cloud proxy refused branch deletes (403). A waiting-page task then handed the owner a Mac job. Its steps, reconstructed from the item's shape and not read from the lost record, were "open plans/c152-stale-branch-deletes.md" and "run its command". A session on his Windows PC then did all of it. The task handed him work a session could do. The item's exact record is lost; the guard test builds its fixture from this shape.

Kind: process
Home: rule:output-never-hand-off-doable-step

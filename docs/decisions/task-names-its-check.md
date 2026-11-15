# A waiting-page task names the check that shows only the owner can do it

## The ruling

A session never hands the owner an act that a session can do. When the cloud refuses an act (for example, the proxy answers 403 to a branch delete), the session first asks a session on the owner's computer to do it (Remote Control: `list_computer_folders`, then `request_computer_folder`). Only after that try does it put a task on the waiting page (skill `waiting-page`).

- A waiting-page task carries a line in `context` that starts `Why yours:`. The line names why only the owner can do the act. It also names the check that showed it, such as the try on a session on the owner's computer and its outcome.
- Guard rule `task-names-check` (`hooks/question_form.py`, run by `hooks/guard.py`) refuses an `ArtifactData` set to `items` of `kind: task` whose `context` has no such line. The line needs text after the colon. It also judges an update that carries `kind: task` and `context`. It also judges a `str_replace` on `context` whose `old_str` holds the line and whose `new_str` does not, or whose `new_str` holds fewer Why yours labels than its `old_str`. It reads each write in a batch and data read from `file_path`.
  - It judges only a call whose `url` is this repo's waiting page (`layout.waiting_page`).
  - It passes an update with only status, rank or other fields (the writer re-ranks by update), a decision, and a call to another artifact.
  - The reason tells the session to ask a session on the owner's computer first, and to add the line.
  - It is built against a named incident, below. It landed 2026-10-29.
  - Cost: no new process. It runs inside the guard process that every `ArtifactData` call already starts. It writes no file unless it denies.
  - Guard rule `task-why-cited` (same module and run) judges the line's cite. A capability reason (`CAPABILITY_RE` in `lint/report_guard.py`, the one home of the verbs) needs `(route <id>)`, an id from the route rows file whose row on this surface says refused or asks, or `(measured <YYYY-MM-DD>, <check and result>)`. It refuses a capability verb with no cite, a cite whose row says the act works, an id no row holds, and a measured cite with no date. The page reads no refusals file, so a tool name in backticks is no cite. A rows file that does not read, or a row only on another surface, passes. The verdict is `why_yours_verdict` in `lint/report_guard.py`, the one home the Stop hand-off check also calls (decision `claims-carry-backing`, part (v)). It judges the same writes as `task-names-check`. A line with no route cite reads no file. A `str_replace` on `context` is also judged on the cite tokens in its `new_str` (`cite_tokens_verdict` in `lint/report_guard.py`). So a swap of a whole `(route` or `(measured` token is refused too. Cost: `lint/report_guard.py` loads inside the guard process (not pinned), about 10 ms (3 runs, 2026-11-07). It loads only for a task write with a Why yours line, or a `str_replace` whose `new_str` holds a `(route` or `(measured` token. It reads the rows file only for a line with a route cite, and writes nothing.
  - Known limit: the guard checks the cite, not whether the check it names was run. A route row cite or a dated measured cite with a false result passes. The owner can follow the cite to verify it. No check reads a row's age yet (decision `claims-carry-backing`, Not built). Still passing: a capability word outside `CAPABILITY_RE` in `lint/report_guard.py`. An asks-row cite that is not matched to the act. A second line of a wrapped Why yours line. A row on this surface whose outcome is unknown. A `str_replace` that swaps only part of a cite token: the id alone, the date alone, or a removal of the whole cite. The hook cannot see the stored line.
  - Known limit: an update that carries `context` but no `kind` is not judged, because the guard cannot see the stored kind. The writer carries `kind: task` again on a context update.

Incident:

- 2026-10-28, item 39: the cloud proxy refused branch deletes (403). A waiting-page task then handed the owner a Mac job. Its steps, reconstructed from the item's shape and not read from the lost record, were "open plans/c152-stale-branch-deletes.md" and "run its command". A session on his Windows PC then did all of it. The task handed him work a session could do. The item's exact record is lost; the guard test builds its fixture from this shape.

Kind: process
Home: rule:output-never-hand-off-doable-step

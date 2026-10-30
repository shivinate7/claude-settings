# A waiting-page item that is being reworked leaves the page

## The ruling

An open item on the waiting page is one the owner can answer now. An item whose options are being reworked is not that. A session never writes an open item that says it is being reworked. It closes the item with a home that names the rework, and adds a fresh item when the options are ready. A `none` answer whose new options are written in the same turn may stay open.

- Guard rule `rework-off-page` (`hooks/question_form.py`, function `rework_off_page_hit`) refuses an `ArtifactData` set or update to `items` whose `context` says "being reworked", in any case, unless the same write has `status: closed`.
  - It reads each write in a batch and data read from `file_path`. It judges only a call whose `url` is this repo's waiting page (`layout.waiting_page`).
  - It judges every kind, since an item that is being reworked is not answerable, whatever its kind.
  - It passes a write with status closed, a status-only update, an item that says "reworked" in the past tense, and a call to another artifact.
  - It reads last, after `option-letter-keys`.
  - The reason says: close the item with a home that names the rework, and add a fresh item when the options are ready. It names no target.
  - It is built against a named incident, below. It landed 2026-10-30.
  - Cost: no new process. It runs inside the guard process that every `ArtifactData` call already starts. It writes no file unless it denies.
  - Known limit: a `str_replace` on `context` carries no status and is not judged, so it can add the phrase to an open item.
  - Known limit: the guard reads the phrase "being reworked". Other words for the same state, such as "under revision", pass.

Incident:

- 2026-10-30 15:40 CDT, waiting item 97: its options were being reworked, yet it stayed open and answerable. The owner answered it and asked "if so, why am i able to answer?".

Kind: process
Home: rule:questions-go-to-owner

# A waiting-page item that is being reworked leaves the page

## The ruling

An open item on the waiting page is one the owner can answer now. An item whose options are being reworked is not that. A session never writes an open item that says it is being reworked. It closes the item with a home that names the rework, and adds a fresh item when the options are ready. A `none` answer whose note asks for other choices may stay open, if its new options are written in the same turn. A `none` answer whose note gives a clear direction closes, and its note becomes a step; no fresh item is added (owner, 2026-11-01 17:44 CST).

- Guard rule `rework-off-page` (`hooks/question_form.py`, function `rework_off_page_hit`) refuses an `ArtifactData` set or update to `items` whose text (title, context, why, an option's text or a step) says "being reworked", "being re-worked", "under rework" or "under re-work", in any case, unless the same write has `status: closed`.
  - It judges a `str_replace` on the text it adds (`new_str`), in any field. The stored item is unseen, so a `str_replace` that adds the phrase is refused even on a closed item.
  - It reads each write in a batch and data read from `file_path`. It judges only a call whose `url` is this repo's waiting page (`layout.waiting_page`).
  - It judges every kind, since an item that is being reworked is not answerable, whatever its kind.
  - It passes a write with status closed, a status-only update, an item that says "reworked" in the past tense, and a call to another artifact.
  - It reads last, after `option-letter-keys`.
  - The reason says: close the item with a home that names the rework, and add a fresh item when the options are ready. It names no target.
  - It is built against a named incident, below. It landed 2026-10-30.
  - Cost: no new process. It runs inside the guard process that every `ArtifactData` call already starts. It writes no file unless it denies.
  - Known limit: the guard reads only the spellings above. Other words for the same state, such as "under revision", pass. History text such as "was being reworked" is refused.

Incident:

- 2026-10-30 15:40 CDT, waiting item 97: its options were being reworked, yet it stayed open and answerable. The owner answered it and asked "if so, why am i able to answer?".

Kind: process
Home: rule:questions-go-to-owner

# A parked line carries a unique id the page takes

## The ruling

A parked line is a `meta/page.parked` entry the owner can Unpark or Drop. The page takes a line live only when two things hold (`parkItems`). Its `id` is a string that fullmatches the pattern in one block, `<script type="application/json" id="parkId">"..."</script>` in `skills/waiting-page/page.html`. No other line in the list has that id. A line that fails has both acts off. The block is the one home of the pattern. The page reads it (`PARK_ID`), and so does the guard. Nothing else holds a copy.

- Guard rule `parked-line-id` (`hooks/question_form.py`, `park_id_hit`, called by `page_item_hit`) refuses an `ArtifactData` write to collection `meta`, doc_id `page`, on this repo's waiting page. It refuses when `parked` is not a list, or a line is not an object, or a line has no id. It also refuses an id that is not a string, an id the block's pattern does not fullmatch, and a repeated id.
  - It judges `set` only when `data` has `parked`, and `update` only when `data` has `parked`. `{"__delete__": true}` passes. `str_replace` passes.
  - It reads each write of a batch and data read from `file_path` (`_write_data`).
  - It reads the block with the one HTML block reader in `question_form.py` (`_page_block`), which `item-field-rendered` also uses. The seam `PARK_ID_SEAM` names another page for the tests.
  - A page with no block, or a block that is not a JSON string that compiles, reads as unknown and the write passes.
  - The reason names `parkId`. It tells the session to give every line in the write a slug id, unique in the list. A write that removes one line carries the ids of all the rest.
  - Cost: no new process. It runs inside the guard process that every `ArtifactData` call already starts. For a write of `meta/page` to the waiting page it reads `page.html` once. It writes no file unless it denies.
  - Known limit: the guard reads this repo's template `skills/waiting-page/page.html`, never the live page. It judges a write by the template's pattern even when the live page runs older code with a different pattern or no `parkId` block. The stale-page gate (`stale_pages.py`) keeps the live page on main's code.
  - Known limit: the pattern is compiled with `re.ASCII` so `\d` and `\w` match what JavaScript matches. A pattern without `^` and `$` anchors would let the guard (fullmatch) and the page (`test`) disagree; the block holds an anchored pattern (debt note `parked-id-pattern-anchors`).
  - Known limit: a bad block passes. The page tests and the real-page case in `hooks/test_question_form.py` go red on a dropped or changed block.
  - Known limit: it cannot see a stored line. A list written before the rule keeps its lines, and the page shows the same two acts off.
- The writer adds a line in one update pinned with `if_version`, with `{id, ref, note}`: `id` the item's id when it fullmatches the `parkId` pattern and is unique in the list, else a new slug of the `ref` that does (skill `waiting-page`, "Route and close", the Park step). Before this record no step told a session to write an id.

Incident:

- 2026-11-03 19:26 CST, owner page comment: "fix this id issue it happens often in general on my repos artifacts". Two parked lines with no id made the page disable Unpark and Drop on them. Nothing refused the write.

Kind: process
Home: rule:building-one-home-per-capability

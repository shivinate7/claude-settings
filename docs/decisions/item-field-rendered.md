# A waiting item names only fields the page renders

## The ruling

A field on a waiting item is for the owner to read. A field the page does not draw is lost to him. The page lists the top-level item fields it draws in one block, `<script type="application/json" id="itemFields">[...]</script>` in `skills/waiting-page/page.html`. That block is the one home of the list. The page reads it, and so does the guard. Nothing else holds a copy.

- The page shows a visible warning on the card of an item that carries a top-level field outside the list. It names each field. It never blocks Send.
- Guard rule `item-field-rendered` (`hooks/question_form.py`, `item_field_hit`, called by `item_hit`) refuses an `ArtifactData` write to `items` that names a top-level field outside the list.
  - It reads the block with `html.parser`, never a regex. Script text is data, so a block inside a string or a template literal is no block.
  - It judges `set` and `update` by the keys of `data`, and `str_replace` by `field`. It reads each write in a batch and data read from `file_path`.
  - It judges only a call whose `url` is this repo's waiting page (`layout.waiting_page`).
  - Scope: top-level keys only. A key inside `options`, `steps` or a listed field is not judged.
  - An update may remove a stored field with `{"__delete__": true}`, which passes. A set never carries that marker.
  - A page with no block, an empty list, or a block that is no JSON list of strings, reads as unknown and the write passes.
  - The reason names `itemFields`. It tells the session to draw the field and add it to the block, or leave it out.
  - It is built against a named incident, below. It landed 2026-10-30.
  - Cost: no new process. It runs inside the guard process that every `ArtifactData` call already starts. For a call to the waiting page it reads `page.html` once per write (about 2,200 lines; unmeasured: no test counts the reads). It writes no file unless it denies.
  - Known limit: the guard sees that a field is listed, not that the page draws it well. A name added to the block with no drawing passes. Review catches it.
  - Known limit: the guard reads the template `page.html`, not the live page. A page published before this change lacks the block, so the stale-page check (`stale_pages.py`) is the backstop.
  - Known limit: it cannot see a stored field. An item written before the rule keeps its fields, and the page warns on them.
- The same rule refuses a write whose `n` the page cannot read (step `item-n-must-be-number`; `item_n_hit`, `page_number` in `hooks/question_form.py`).
  - The page's own test is `typeof it.n === "number" && isFinite(it.n)` (`problem()` in `skills/waiting-page/page.html`); `page_number` follows it, and a case reads that line of the page.
  - A `set` with no `n`, a `set` or `update` whose `n` is text, a bool, null, a list, an object, NaN or infinity, and a `str_replace` on `n` are refused. An `update` that does not name `n` passes.
  - It reads the parsed value, never the text of the write. It reads each write in a batch and data read from `file_path`.
  - The reason (`PAGE_REASONS["item-n-number"]`) names the item and says `n` is a number such as 929, not "929". It names no other rule's remedy.
  - Incident: 2026-11-17 09:43 CST, triage wrote items 928 and 929 with `n` as text. The page showed "This item has no number, so it cannot be answered", and the owner could not answer.
  - Cost: no new process and no file read. It runs in `item_hit`, inside the guard process that every `ArtifactData` call already starts.
  - Known limit: it sees the write, not the stored item. An update that leaves a stored text `n` alone passes.
- The fields `reply`, `lastAnswer` and `lane` are listed, and the page draws each on an open item (`docs/design/last-answer-notes.md`).

Incident:

- 2026-10-30 13:10 CDT, triage: 37 live waiting items carried a `reply` field. The page did not draw it, so the owner never read a reply. Nothing refused the write.

Kind: process
Home: rule:building-one-home-per-capability

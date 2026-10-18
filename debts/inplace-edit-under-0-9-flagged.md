# In-place edit of a main-added line reads as a reversal

- **What.** A branch can edit a line that main only added. If the new line stays under the similarity bar, the silent-undo check flags the edit as a reversal. The bar is 0.8 when the line changed a base line, else 0.9.
- **Where.** `check()` in `lint/check_silent_undo.py`, the similarity bar for a line main only added.
- **Decision.** `silent-undo-check-design` (one check catches a merge or branch that silently undoes earlier work). Its false-alarm rule, a line main only added needs 0.9 similarity, sets the bar.
- **Retire.** Tell an edit from a reversal by more than similarity, for example by the base line. A test that edits `alpha one two three four` to `alpha one two three five` stays green.

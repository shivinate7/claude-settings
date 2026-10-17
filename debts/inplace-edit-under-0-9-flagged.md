# In-place edit of a main-added line reads as a reversal

- **What.** A branch can edit a line that main only added. If the new line keeps under 0.9 similarity, the silent-undo check flags the edit as a reversal.
- **Where.** `check()` in `lint/check_silent_undo.py`, the similarity bar for a line main only added.
- **Decision.** `silent-undo-check-design` (one check catches a merge or branch that silently undoes earlier work). Its false-alarm rule, a line main only added needs 0.9 similarity, sets the bar.
- **Retire.** Tell an edit from a reversal by more than similarity, for example by the base line. A test that edits `alpha one two three four` to `alpha one two three five` stays green.

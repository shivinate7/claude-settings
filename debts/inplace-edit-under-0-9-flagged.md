# In-place edit of a main-added line reads as a reversal

- **What.** When a branch edits a line that main only added, and the new line keeps under 0.9 similarity to it, the silent-undo check reads the edit as a reversal and flags it.
- **Where.** `check()` in `lint/check_silent_undo.py`, the similarity bar for a line main only added.
- **Decision.** `silent-undo-check-design` (one check catches a merge or branch that silently undoes earlier work). Its "Holes, named" section names this gap.
- **Retire.** Tell an edit from a reversal by more than similarity, for example by the base line. A test that edits `alpha one two three four` to `alpha one two three five` stays green.

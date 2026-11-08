# The narration check misses a run's colour stated before the place

**What.** The run-state form of the `history phrase` pattern reads only a colour or result followed by its place ("red on main"). A comment that names the place first, such as "The run on main was red, so this case pins it", passes, though the lane ruling counts it as history and the `HistoryPhrase` docstring says it is caught. Claude writes this word order in normal test comments.

**Where.** `lint/check_comment_narration.py`, `HistoryPhrase.RUN`.

**Decision.** none

**Retire.** "The run on main was red, so this case pins it" and "the job on the head went green" hit as `history phrase`, and every CLEAN case stays clean, in `lint/test_check_comment_narration.py`.

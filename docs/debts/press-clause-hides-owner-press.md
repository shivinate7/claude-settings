# A session clause can hide an owner press that names no actor

**What.** The press-link check excuses a session-subject clause when it holds no `you` and no owner's name as subject of a present or future press or act verb. A press with no named actor inside such a clause still passes. These pass with no link: "The session merges PR #374 after clicking Approve.", "...after Approve is clicked.", "...after your Merge click.", "...after owner clicks Approve." (no article). The owner presses in each, and the check cannot tell. An owner press with an infinitive or helper verb still passes: "has to click", "needs to click", "is asked to click", "himself clicks". "after Shivam approves it on GitHub" is refused only when the label holds a press verb.

**Where.** `hooks/question_form.py`, `_owner_press_text`, `OWNER_NAME` and `OWNER_ACT`, rule `press-link`.

- **Decision.** `act-in-place` (the owner acts where he reads).

**Retire.** `_owner_press_text` reads a press verb in a session clause as the owner's when no session verb in that clause is the same press. Red-first cases in `hooks/test_question_form.py` for each case named in What go green, and "The session merges PR #374." and "After the pick, the session merges PR #374." stay allowed.

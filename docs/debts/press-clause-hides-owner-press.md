# A session clause can hide an owner press that names no actor

**What.** The press-link check excuses a clause whose subject is the session when it holds no `you` and no owner's name as the subject of a present or future press or act verb. A press with no named actor inside such a clause still passes. These pass with no link: "The session merges PR #374 after clicking Approve.", "...after Approve is clicked.", "...after your click on Merge.", "...after owner clicks Approve." (no article). The owner presses in each, and the check cannot tell.

**Where.** `hooks/question_form.py`, `_owner_press_text`, `OWNER_NAME` and `OWNER_ACT`, rule `press-link`.

**Decision.** act-in-place (the owner acts where he reads).

**Retire.** `_owner_press_text` reads a press verb in a session clause as the owner's when no session verb in that clause is the same press. Red-first cases in `hooks/test_question_form.py` for the four sentences above go green, and "The session merges PR #374." and "After the pick, the session merges PR #374." stay allowed.

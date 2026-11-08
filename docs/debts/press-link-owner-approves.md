# A press-link check passes an owner's approval in a session clause

**What.** The press-link check passes "The session merges PR #374 after Shivam approves it on GitHub." when the option's label holds no press verb, on head and on main. The owner presses in that line, and the check cannot tell. The same line is refused only when the label holds a press verb, such as "Merge it". Likely in normal work: a session option that asks the owner to approve a PR. Probed, not measured.

**Where.** `hooks/question_form.py`, `PRESS_VERB` (its approve and merge alternative matches only the bare verb after a clause start, so "Shivam approves" never matches) and `_owner_press_text`, rule `press-link`.

**Decision.** act-in-place (the owner acts where he reads).

**Retire.** `_owner_press_text` reads an owner's approve or merge, when the owner is the subject of its clause, as a press. The check: red-first cases in `hooks/test_question_form.py`. Label "Go ahead" with the how "The session merges PR #374 after Shivam approves it on GitHub." is refused with no link. "The session merges PR #374." and "After the pick, the session merges PR #374." stay allowed.

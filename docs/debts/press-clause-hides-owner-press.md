# A session clause can hide an owner press

**What.** The press-link check excuses a whole clause whose subject is the session when it holds no `you`. "The session merges PR #374 after the owner clicks Approve." passes, and so does "The session merges PR #374 but click Merge first", because `but`, `so`, `:`, `-` and parentheses do not split clauses. Main refused both.

**Where.** `hooks/question_form.py`, `_owner_press_text` and `_CLAUSE_BREAK`, rule `press-link`.

**Decision.** act-in-place (the owner acts where he reads).

**Retire.** `_CLAUSE_BREAK` also splits on `but`, `so`, `or`, `:`, `-` and `(`, and "the owner", "he" and "Shivam" count as `you`. Red-first cases in `hooks/test_question_form.py` for both example sentences go green.

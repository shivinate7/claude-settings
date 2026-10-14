# A gate's own internal errors exit 0

- **What.** Errors a gate catches itself fail open. `question_outcome.py` exits 0 when it cannot read its input, its state or its model. `guard.py` logs an internal error, then exits 0. `ste_gate.py` returns on bad input. `rm_prompt_answer.py` returns on any exception, which leaves the prompt.
- **Where.** `question_outcome.py`, `guard.py`, `ste_gate.py` and `rm_prompt_answer.py`.
- **Decision.** `gate-hooks-fail-closed` (a gate whose script or python is missing refuses the call).
- **Retire.** Each gate refuses on its own internal error, or the decision records the accepted allow. `hooks/test_wrappers.py` pins the exit code.

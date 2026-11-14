# A Workflow call never runs with a placeholder as its args

## The ruling

The guard refuses a `Workflow` call whose `args` is a placeholder (rule `workflow-args-shape-check`). It reads `args`, and each item of an array or each value of an object, one level down. A value is a placeholder when the whole value is one of two forms:

- An all-caps word with at least one underscore, such as `FACT_CLOSE_PLACEHOLDER` or `PR_NUMBER`.
- A `__X__` word, such as `__FILL__`.

The refusal names the placeholder and says to replace it with the real value.

These pass: a call with no `args` and empty `args`. A sentence that holds a placeholder (`MAILBOX_REPO is off`) passes. So do a short all-caps word with no underscore (`OK`) and a path that holds a dunder (`__init__.py` in a `hooks` folder).

Known false alarm: a real value can have the shape, such as a bare env var name (`MAILBOX_REPO`) as the whole value. The guard refuses it. The owner's override lifts it (decision `guard-guards-mistakes-only`, guards stop Claude's mistakes).

Known gap: a placeholder nested more than one level down, and a placeholder in any other shape (`TODO`, `<fill me>`), pass.

Reason: on 2026-11-10 a Workflow call ran with `FACT_CLOSE_PLACEHOLDER` as its args, and a second ran with `__FILL__`. The agents checked nothing, and the run looked complete.

Cost: no new process. The check reads one field of the call in the guard run that already starts for each `Workflow` call (unmeasured).

Tests: family `workflow-args` in `hooks/test_guard.py`.

Kind: process
Home: hooks/guard.py

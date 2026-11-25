# The history check refuses a description with the word old before was

- **What.** The overruled-text check in `lint/hook_catalog.py` flags `was:` when the word `old` comes earlier in the same block. So a plain description such as `The old flag was: on.` fails as overruled text. The case `test_c14_limit_old_before_was_colon_flags_as_pinned` pins that failure as the expected result.
- **Where.** `history_problems` in `lint/hook_catalog.py`, its `was:` test. Its pinned case is `test_c14_limit_old_before_was_colon_flags_as_pinned` in `lint/test_hook_catalog.py`, about line 1572.
- **Decision.** `cull-rules` (no history in the tree). Its home is rule `speak-rewrite-superseded-in-place`.
- **Retire.** The rule tells a description from overruled text. `The old flag was: on.` passes, and `The old wording was: allow it.` still fails. The case is re-pointed to the pass, red first on the current code. Runnable test: `lint/test_hook_catalog.py`.

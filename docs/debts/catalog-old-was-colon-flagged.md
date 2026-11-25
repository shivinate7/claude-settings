# The history check refuses a description with the word old before was

- **What.** The overruled-text check in `lint/hook_catalog.py` flags `was:` when the word `old` comes earlier in the same block. So a description of the form `old <noun> was: <value>` fails as overruled text. The case `test_c14_limit_old_before_was_colon_flags_as_pinned` pins this as a stated limit of the rule: a false flag on a description of that form.
- **Probe inputs (2026-11-24).** All three share the form `old <noun> was: <value>`. All three are flagged.
  - `The old flag was: on.` is a description. Flagged. A false flag.
  - `The old wording was: allow it.` is overruled text. Flagged. A true flag.
  - `The old limit was: 3 per run.` is history. Flagged. A true flag.
- **Where.** `history_problems` in `lint/hook_catalog.py`, its `was:` test. Its pinned case is `test_c14_limit_old_before_was_colon_flags_as_pinned` in `lint/test_hook_catalog.py`, line 1572.
- **Decision.** `cull-rules` (no history in the tree). Its home is rule `speak-rewrite-superseded-in-place`.
- **Frequency.** Unmeasured. The old note called it rare and harmless, with a review date of 2026-11-20. That date has passed.
- **Retire.** One of two ends:
  - A rule that separates the forms and still flags both true positives. None exists on the text alone. A noun list passes `The old flag was: allow it.`, which is history, because `flag` also names the description `The old flag was: on.`. When a rule separates the forms, the pinned case expects the pass, red first on the current code.
  - The writer rewords the description. This is the working remedy today.
- Runnable test: `lint/test_hook_catalog.py`.

# The feedback guard reads owner text without the app-block strip

**What.** Four `owner_text` calls in the feedback guard do not cut app blocks first. An owner prompt that an app block leads is then dropped or read as a notice, and the effect differs by call.

**Where.** `hooks/feedback_guard.py`. Line 739 (`Pages._load`, passes `MACHINE_TAGS`) drops the record, so a page or repo item sent after it finds no anchor and its check stands down. Line 1534 (`_turn_text`) keeps the block in the text. Its one caller, `_is_notice` at line 1546, then reads the prompt as a notice. Lines 1545 (`_is_notice`) and 1555 (`_turn_records`) read it as a notice, so it starts no turn. The turn then reaches back to the earlier owner message, and `page_link_check` (line 1602) may re-check that turn's page writes. The strip is the `app_notes` argument of `owner_text` in `lint/_transcript.py`, as `hooks/override.py` `_text_of` passes it.

**Decision.** owner-override (an owner override lets a refused or asked act through).

**Retire.** Closed when all four calls read the owner's words with `app_notes` set. `hooks/test_feedback_inbox.py` gets a red case: a page item sent after an owner prompt that an app block leads anchors to that prompt, and that prompt starts a turn.

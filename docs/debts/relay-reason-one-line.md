# The relay refusal does not say the words go on one line

**What.** The refusal for a bad relay Grant line reads `... covers <act> This Grant line is not in that form.` There is no full stop before "This Grant line". The refusal also never says the quoted words go on one line. A verbatim copy of an owner message that runs over several lines is refused as "not in that form", and the reason gives no cause. The same gap sits before "This Grant line is refused:". Harm: a sender copies the owner's words exactly and still gets a refusal it cannot explain. Claude is likely to copy a multi-line message.

**Where.** `hooks/guard_merge.py` on PR #3038's branch (the relayed-grant change). `RELAY_REASON` joins the form and the reason with no full stop. `relay_grant_hit` passes the two reasons: "This Grant line is not in that form." and "This Grant line is refused: " followed by the cause.

**Decision.** relayed-grant-read-from-page (a relayed grant counts only when the receiver reads it from the page). Its "What a relay message carries" section sets the form the refusal names. Rule `relay-grant-words` (a relayed grant quotes the owner's exact words) emits the refusal.

**Retire.** Closed when the refusal text puts a full stop after the form, before "This Grant line", and says the quoted words go on one line. The fix adds that full stop and that instruction. A case in `tests/guard/s43517-relay-grant-words.py` checks the text and goes red on the current text first. The runner `hooks/test_guard.py` runs that case.

# A sentence with two item numbers refuses the wrong one

**What.** The answered-claim check judges every item number in a sentence against any claim word in that sentence. "Item 131 answered a and item 803 is not answered." refuses, because the check reads item 803 as claimed answered. Claude can write such a sentence in normal work, so the refusal is a false alarm.

**Where.** `hooks/answered_claims.py`, lines 103 and 214 to 222: the loop pairs each item number in a sentence with the claim words, not only the item the claim words sit beside.

**Decision.** `answered-claims-match-page` (a claim that a waiting-page item is answered matches the page).

**Retire.** A sentence that claims an answer for one item and states that another item has none passes. A case in `hooks/test_answered_claims.py` shows it closed: item 131 answered, item 803 not answered, and the send passes.

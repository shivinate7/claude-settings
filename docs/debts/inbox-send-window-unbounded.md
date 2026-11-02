# Send proof has no window end

**What.** The feedback Stop guard accepts any matching send after the owner's message, in any later turn. The window has no end. A later status message that names the repo or the page number therefore proves an item that was never sent. Measured: `Pages.sent` scans every record from the anchor to the end of the transcript. The send's recipient is not checked, so a message to any session counts. Repo items on branch `one-inbox-per-repo` share the same window. Risk: likely risk, no incident. Found in review on 2026-11-02.

**Where.** `hooks/feedback_guard.py`, `Pages.sent`, the page-proof check. It scans all records after the anchor. On branch `one-inbox-per-repo`, the same `sent` serves repo items.

**Decision.** owner-feedback-inbox (owner feedback goes to an inbox before the turn ends).

**Retire.** An owner call picks option A or option B. This record does not pick one.

- Option A: bound the window to the owner's turn. A turn's messages are the ones captured since the last Stop, per the decision's burst rule. A also rejects a real send made in a later turn. The decision's guard rule says items added in any later turn count, so A departs from that line. The owner decides whether that line stands. A also needs a boundary. The next owner record is not one, because wakes and peer notices are not owner records. A does not close the gap inside the owner's turn. A status message in that turn still counts.
- Option B: keep the window as it is. Sends in later turns keep counting, as the decision's guard rule says. The false pass stays.

Recommended: A. Reason: a false pass loses owner feedback with no block. A false block shows at the Stop check, and a send in the owner's turn clears it.

Closed by the owner's call. The chosen option then needs a test. For A, a later-turn send is refused and an in-turn send passes.

# A clear or resume race can leave a ghost session row

- **What.** The end hook deletes the records before it marks the old id as retired. A beat that writes in that gap leaves the old entry. A beat that fires between the deletes and the mark is an example. The gap is narrow, and the 2-minute rule hides the row. A held write that lands later is removed when it lands.
- **Where.** The session end hook in `mods/session-board`.
- **Decision.** `session-board-mod-limits` (session-board keeps small records, and /safe-stop queues one prompt).
- **Retire.** The end hook marks the id as retired before it deletes, and a case with a beat in the gap leaves no row.

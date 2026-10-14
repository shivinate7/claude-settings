# SendMessage state judge skips a duplicate name

- **What.** When two sessions share a name, `receiverState` returns unseen and the message is allowed with no state check. A `to` that ends in `[ref]` and matches no row is matched by its bare name; the ref is never compared to a row. The board sees only local rows, so a ref that names an off-board receiver with the same bare name reads the local row's state. Two names that clean alike (over 300 chars with the same first 299, `<>&"` against `_`, or 3 or more combining marks) also read as one row.
- **Where.** `receiverState` in `mods/session-board/hooks/lib.mjs`.
- **Decision.** `subagent-model-cap` (model per role; holes for the SendMessage state judge).
- **Retire.** Name the receiver by the unique ref the board prints, then read that row. A test with two same-name rows reads the state of the named ref.

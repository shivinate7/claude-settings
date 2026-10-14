# SendMessage state judge skips a duplicate name

- **What.** When two sessions share a name, `receiverState` returns unseen and the message is allowed with no state check.
- **Where.** `receiverState` in `mods/session-board/hooks/lib.mjs`.
- **Decision.** `subagent-model-cap` (model per role; holes for the SendMessage state judge).
- **Retire.** Name the receiver by the unique ref the board prints, then read that row. A test with two same-name rows reads the state of the named ref.

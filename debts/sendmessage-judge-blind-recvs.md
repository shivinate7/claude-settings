# SendMessage state judge cannot see some receivers

- **What.** The busy-state layer reads an agent id, a `uds:` address, `main` and `*` as unseen, so it allows. Only the wording judge covers them.
- **Where.** `hooks/sendmessage_state.py` and `receiverState` in `mods/session-board/hooks/lib.mjs`.
- **Decision.** `subagent-model-cap` (model per role; holes for the SendMessage state judge).
- **Retire.** Resolve each receiver form to a board row, or rule that the wording judge alone covers them. A test with each form shows the state read, or the ruling stands in the decision.

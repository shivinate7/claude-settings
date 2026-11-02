# A lane's pick passes on any send

- **What.** A lane's Input Needed pick passes the Stop guard on any send in the same turn, such as a SendMessage to its own builder, not only a send to its parent or the page writer. Lanes resume their own agents by SendMessage often, so the pick can stay in the lane's chat.
- **Where.** `lint/report_guard.py`, the lane path of `pick_send`.
- **Decision.** decisions-reach-a-clickable-pick (a decision reaches a pick the owner can click), Known limits.
- **Retire.** When the own record names a parent, a lane pick passes only on a `send_message` whose `session_id` is the parent. A red case in `lint/test_report_guard.py` PickSendTests: a send to another session, then the pick, blocks.

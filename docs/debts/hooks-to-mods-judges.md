# Judge moves from hooks to mods are open

**What.** Plan step E has four parts. Part (a) is partly done. The Edit and Write judges match `**/decisions/**` at any depth. Both prompts still say `when unsure answer {"ok": true}`, which repeats the block rule. Part (b) has a busy-state command hook, `hooks/sendmessage_state.py`. Notes ids `sendmessage-wording-judge-always` and `sendmessage-judge-blind-recvs` cite its open limits. Part (c) is not built: `hooks/precompact_handoff.py` has no `$.model.complete` call. Part (d) is not built: no pre-filter for judge calls exists, and its saving is unmeasured. The hooks that stay hooks are out of scope: `guard.py`, `rm_prompt_answer`, the janitor hooks, `stall_watch`, and the Stop watches.

**Where.** `settings.json` (the Edit and Write judge prompts, and the SendMessage hook entry). `hooks/precompact_handoff.py` (part c). `hooks/sendmessage_state.py` (part b).

**Decision.** `haiku-prompt-hooks`, prompt hooks judge rules that no script can parse.

**Retire.** Each part is built on main, or ruled out in a decision record. The debt closes when no part is open. Part (a) closes when the `when unsure answer` sentence leaves both prompts.

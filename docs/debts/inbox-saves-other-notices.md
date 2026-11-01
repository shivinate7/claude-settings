# Other notices reach the feedback inbox

**What.** The feedback inbox saves some prompts the owner did not type. Incidents: on 2026-11-01 04:09 CST, a lane brief from a peer session was saved as an owner burst, and it blocked that lane's turn end. The Apple TV session's message at 20:21 CDT on 2026-10-31 may be one too (unmeasured). The bandaid in the Ruling skips the `<cross-session-message` frame. Hand-backs were already skipped. Still open: `<teammate-message`, `<webhook-payload>`, `<wake`, a first line `[SYSTEM NOTIFICATION - NOT USER INPUT]`, and `<system-reminder id=...>` are not skipped. A session's seed prompt and a scheduled-task wake carry no marker in their text, so no tag check reaches them.

**Where.** `hooks/local_time.py` (the capture hook), in `capture`, the prefix check against `MACHINE_TAGS`. `hooks/shared_names.py`, `MACHINE_TAGS`, the one copy of the tag list. `hooks/test_shared_names.py` holds a pinned copy that must match it.

**Decision.** owner-feedback-inbox (owner feedback goes to an inbox before the turn ends).

**Retire.** Tell the owner's typed prompt from harness text by the hook input's own origin field, not by a text prefix. Measured: the session transcript's user record for a peer prompt carries `isMeta: true` and `promptSource: "system"`. For an agent hand-back it carries `origin.kind: "peer"`. Whether the UserPromptSubmit hook input (the hook that runs on each owner prompt) carries any of these fields: unmeasured. Closed when `capture` skips each notice by that origin field. A test in `hooks/test_local_time.py` feeds it a peer prompt, a seed prompt and a scheduled-task wake. It asserts that none is saved. That test goes red when the prefix check is removed.

## Ruling

Owner ruling, 2026-11-01 04:29 CST, relayed by the coordinator. Words: "neither seem like great options A likely the better bandaid with a debt".

Option A, chosen: the capture hook skips a prompt that starts with the `<cross-session-message` frame. The frame is defined once, in `MACHINE_TAGS` in `hooks/shared_names.py`. The ruling covers this skip only. It is a bandaid. This debt stays open until the origin-field fix lands.

The hand-back skip stands from the owner's pick at 15:44 CDT on 2026-10-31.

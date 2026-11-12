# A scratchpad path in a brief's prose is denied

- **What.** A redirect into the session scratchpad passes, but the same path in prose is refused, e.g. "Save the screenshots to `<scratchpad>/shots/home.png`" to a design reviewer. The refusal then names a writer role, the wrong remedy, though `agents/design-reviewer.md` says screenshots go in the scratchpad.
- **Where.** `hooks/guard.py` `brief_write_hit`, the prose pass. The scratchpad exemption covers the command pass only.
- **Decision.** `brief-write-needs-writer` (a read-only agent's brief never orders a file write).
- **Retire.** A prose order whose destination is the session scratchpad passes, as a redirect does. A case in the `brief-write-needs-writer` family in `hooks/test_guard.py` checks it.

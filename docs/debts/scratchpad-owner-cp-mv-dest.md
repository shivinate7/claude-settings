# A copy or move into the scratchpad leaves no record

- **What.** The destination of `cp X <scratchpad>/f`, `touch`, `dd of=`, `curl -o` and `>|` is not recorded, so A copies a script in, B runs it, and no one is asked. An approved `mv` over A's file keeps A as the writer, because the `mv` destination is judged as a removal and not recorded.
- **Where.** `hooks/guard.py` `scratchpad_writes`: the shell write targets it reads, and its `removed` set, which holds the `mv` destination.
- **Decision.** `scratchpad-owner` (an agent asks before it runs or overwrites another agent's scratchpad file).
- **Retire.** Fix: record the `cp` and `mv` destinations, and an `mv` destination carries its source's record. Check: a case in the scratchpad-owner family of `hooks/test_guard.py` where A copies a script in, B's run is asked, and an approved `mv` over A's file moves the record to B: `hooks/test_guard.py`.

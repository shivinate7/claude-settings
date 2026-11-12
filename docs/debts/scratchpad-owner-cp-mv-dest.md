# A copy or move into the scratchpad leaves no record

- **What.** The destination of `cp X <scratchpad>/f`, `touch`, `dd of=`, `curl -o` and `>|` is not recorded, so A copies a script in, B runs it, and the guard does not refuse it. A lifted `mv` over A's file keeps A as the writer, because the `mv` destination is judged as a removal and not recorded.
- **Where.** `hooks/guard.py` `scratchpad_writes`: the shell write targets it reads, and its `removed` set, which holds the `mv` destination.
- **Decision.** `scratchpad-owner` (an agent runs only its own read copy of a scratchpad file, and never overwrites another agent's).
- **Retire.** Fix: record the `cp` and `mv` destinations, and an `mv` destination carries its source's record. Check: a case in the scratchpad-owner family of hooks/test_guard.py where A copies a script in, B's run is refused, and a lifted `mv` over A's file moves the record to B: `hooks/test_scratchpad_owner.py`.

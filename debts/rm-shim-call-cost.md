# A recursive rm pays one Python start

- **What.** A recursive `rm` under a Claude session costs about 40 ms. MEASURED 2026-10-17: the real `rm` is 1.9 ms, and any other shim call is 4.4 ms.
- **Where.** The Python step in `bin/rm`.
- **Decision.** `rm-path-wrapper` (an rm shim on PATH, active only in Claude sessions).
- **Retire.** The critical-path read moves into `sh`, or the decision records 40 ms as accepted.

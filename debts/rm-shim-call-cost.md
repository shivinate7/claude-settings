# A recursive rm pays one Python start

- **What.** A recursive `rm` under a Claude session costs about 40 ms. MEASURED 2026-10-17: the real `rm` is 1.9 ms, and any other shim call is 4.4 ms.
- **What, the marker search.** The search for the real `rm` reads its first line byte by byte. MEASURED 2026-10-17: a shim call costs 4.4 ms under `sh` and 7.0 ms under `dash`. A 20 MB `rm` on PATH with no newline costs 1.6 s under `sh` and 5.7 s under `dash`.
- **Where.** The Python step and `find_real` in `bin/rm`.
- **Decision.** `rm-path-wrapper` (an rm shim on PATH, active only in Claude sessions).
- **Retire.** The critical-path read moves into `sh`, or the decision records 40 ms as accepted. The marker search reads a bounded prefix, or the decision records its cost as accepted.

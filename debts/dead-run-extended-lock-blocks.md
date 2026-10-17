# A dead run's extended lock blocks other runs

- **What.** A run that dies after a lock extension leaves a lock that expires up to 1200 s (a 900 s wait plus the 300 s margin) after the extension. Other runs read it as held for up to about 20 minutes more than an unextended lock. `merge --unlock` clears it.
- **Where.** `Lock.extend_for` and `holder_text` in `merge/merge.py`.
- **Decision.** `merge-net-retry` (what bin/merge does on a network error or a rate limit).
- **Retire.** The next run takes the lock of a holder that is dead on the same host, with no `merge --unlock`. Or the extension covers only the wait that is running. A test with a dead holder and an extended lock shows the next run takes the lock.

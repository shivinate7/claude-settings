# The session-start refresh lock has no test

**What.** The SessionStart refresh holds a lock directory in the config dir. No case covers a held lock (a start exits quietly), the stale clear after 10 minutes, or the lock removed at exit. A killed child leaves the lock for up to 10 minutes, and starts in that time skip with no log line. The exit `rmdir` has no owner id, so a child that outlives 10 minutes can remove a newer start's lock.

**Where.** `settings.json`, the SessionStart startup|resume refresh command; `merge/test_install_from_main.sh`.

**Decision.** merge-reinstalls-from-main (the pin follows local main and is reinstalled after each merge).

**Retire.** Cases for a held lock, a stale lock and the exit removal; the lock carries its owner's id, and only the owner removes it.

# The session-start refresh lock can be removed by a child that outlives its stale age

**What.** The SessionStart refresh holds a lock directory in the config dir. Cases 48 and 49 in `merge/test_install_from_main.sh` cover a held lock (the skip leaves it as it was and writes one install log line) and the lock removed at exit. Still open: the stale clear after 10 minutes has no case. A killed child leaves the lock for up to 10 minutes, and starts in that time skip with a log line. The exit `rmdir` has no owner id, so a child that outlives 10 minutes can remove a newer start's lock.

**Where.** `settings.json`, the SessionStart startup|resume refresh command; `merge/test_install_from_main.sh`.

**Decision.** merge-reinstalls-from-main (the pin follows local main and is reinstalled after each merge).

**Retire.** A case for a stale lock; the lock carries its owner's id, and only the owner removes it.

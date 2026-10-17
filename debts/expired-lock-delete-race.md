# Two runs can hold the merge lock after an expired-lock delete

- **What.** The API cannot delete a ref only if it still holds a given value. A run reads an expired lock, then deletes it. If another run breaks that lock and makes a live one between the read and the delete, the delete removes the live lock. The create then succeeds, and both runs hold the lock. The window is a few API calls.
- **Where.** `GhLock.acquire` in `merge/merge.py`.
- **Decision.** `merge-lock-names-its-holder` (the lock is a ref on origin, and it names its holder).
- **Retire.** The lock backend deletes only the lock it read (compare-and-swap). A test with a second run that takes the lock inside the window shows one holder.

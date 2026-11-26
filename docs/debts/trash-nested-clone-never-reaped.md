# A clean nested clone in a leftover trash folder is never reaped

**What.** A leftover trash folder that holds a clean nested clone (a Swift package or Xcode checkout) is never reaped. Any nested repo keeps the folder, and no remote is read, so a clone whose every ref is already on its remote keeps it too. Cost unmeasured: how often a trash folder holds such a clone is not counted.

**Where.** `janitor/sweep.py`, `has_nested_git` and `trash_dirty`, read by `trash_verdict`.

**Decision.** `session-record-gone-folder`, a gone session record stands in no tree; its trash-folder keep counts any nested repo as work.

**Retire.** Lane `nested-clone-reap-every-ref` deletes a nested clone only when every ref is on a remote outside the folder, the reflog holds nothing more, and no ignored or untracked file exists, each probed on real repos.

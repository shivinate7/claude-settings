# Some git commands never get a cite check

- **What.** `git commit --trailer`, a `Refs:deferred/a.md` token with no space, `git merge -m` and `git tag -m` are never cite-checked. This predates the Drops-lines exemption.
- **Where.** The cite check in `hooks/guard.py` (`cited_record_path`).
- **Decision.** `drops-lines-trailer-exempt` (a commit's Drops-lines trailer may name a record path).
- **Retire.** The guard checks each form, and a case per form refuses a record-path cite.

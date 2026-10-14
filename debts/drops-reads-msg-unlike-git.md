# The guard reads a commit message in a different order than git

- **What.** Three round-3 false refusals. None is a wrong allow. A folded trailer (`Drops-lines: deferred/a.md`, then ` -- reason` on the next line) is refused, though git unfolds it and the lint accepts it. A heredoc body given with `--file=-` beside `-m` parts is read last by the guard, while git orders the parts as typed.
- **Where.** `cited_record_path` in `hooks/guard.py`.
- **Decision.** `drops-lines-trailer-exempt` (a commit's Drops-lines trailer may name a record path).
- **Retire.** The guard unfolds the trailer and orders message parts as git does. A case for each form passes.

## Standing sessions

This roster is the one record of who holds each standing session. It lives on the record branch, and triage writes it. The session that starts a standing session
sends triage the new id in the same turn (ruling R22). A session reads it right before it messages a standing session.

- Coordinator (starts every other session, holds lane state and any standing merge grant, talks with the owner): "<session title>",
  <session id>, since <date and time>. It compacts in place and has no successor.
- Triage (the repo's one page): "<session title>", <session id>, since
  <date and time>.
- Batch runner (integration batch, CI waits, merge tool runs under the coordinator's grant, archiving the lanes `merge --idle-lanes` lists):
  "<session title>", <session id>, since <date and time>.
- Batch runner per repo scope, and the arbiter: one row each, in this form, when the repo has them.

Lanes are not on the roster. The coordinator holds lane state.

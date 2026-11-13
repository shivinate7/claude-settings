## Standing sessions

This roster is the one record of who holds each standing session. It lives at `roster.md` on the
record branch, at the root. Triage writes it. A standing session is replaced only when it goes stale
or breaks. The session that starts a standing session sends triage the new session id in the
same turn, and triage rewrites that line. A session reads it there right before it messages a standing session.

- Coordinator (starts every other session, holds lane state and any standing merge grant, talks with the owner): "<session title>",
  <session id>, since <date and time>. It compacts in place and has no successor.
- Triage (the repo's one page): "<session title>", <session id>, since
  <date and time>.
- Batch runner (integration batch, CI waits, merge tool runs under the coordinator's grant, archiving lanes whose topic has no queued step):
  "<session title>", <session id>, since <date and time>.

Lanes are not on the roster. The coordinator holds lane state. The session that starts a lane sends
triage the lane's session id in the same turn, and triage writes it in that step's `lane` field on the
record branch (restart plan R22, point 2).

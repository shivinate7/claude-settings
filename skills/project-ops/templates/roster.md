## Standing sessions

This roster is the one record of who holds each standing session. The coordinator updates it in
the same turn that it rotates a standing session, which happens only when one goes stale or breaks. A session reads it right before it messages a standing session.

- Coordinator (starts every other session, holds lane state and any standing merge grant, talks with the owner): "<session title>",
  <session id>, since <date and time>. It compacts in place and has no successor.
- Triage (the repo's one page): "<session title>", <session id>, since
  <date and time>.
- Batch runner (integration batch, CI waits, merge tool runs under the coordinator's grant, archiving lanes whose topic has no queued step):
  "<session title>", <session id>, since <date and time>.

Lanes are not on the roster. The coordinator holds lane state.

## Standing sessions

This roster is the one record of who holds each standing session. The coordinator updates it in
the same turn that a session rotates. A session reads it right before it messages a standing session.

- Coordinator (starts every other session, holds lane state and any standing merge grant, talks with the owner): "<session title>",
  <session id>, since <date and time>. It compacts in place and has no successor.
- Triage (gatekeeper, waiting page and roadmap page): "<session title>", <session id>, since
  <date and time>.
- Batch runner (integration batch, CI waits, merge tool runs under the coordinator's grant, archiving finished lanes):
  "<session title>", <session id>, since <date and time>.

Lane sessions are not on the roster. The coordinator holds lane state.

Exemptions: <none, or the session, the limit, the condition and the owner's date>.

# An inbox message is dropped with one stderr line on a path failure

- **What.** If the inbox path cannot be built, an `fb` message is dropped with one stderr line only. Causes include an import error and an odd session id.
- **Where.** The inbox path builder in the capture hook.
- **Decision.** `owner-feedback-inbox` (owner feedback goes to an inbox before the turn ends).
- **Retire.** A failed path build writes the message to a fallback the session reads. A test pins it.

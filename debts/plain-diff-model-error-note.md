# No case covers the model-error note in plain-diff

- **What.** Case F8 was cut. The branch of `modelFailNote` that takes a thrown `Error` has no case. A thrown model error could then show no note. The case for an API error note still holds.
- **Where.** `modelFailNote` in `mods/plain-diff`.
- **Decision.** `test-strategy-reset` (cut tests that name no real failure).
- **Retire.** One case throws an `Error` from the model and sees a `No note:` line.

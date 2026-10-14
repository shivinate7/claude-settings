# A quoted path with an emoji shows a wrong label

- **What.** A quoted path with an emoji shows a wrong label, so no turn note matches it. `notes 🙂 "draft".md` is an example, because git quotes it. An emoji in an unquoted path shows the right label.
- **Where.** The path label code in `mods/plain-diff/hooks/lib.mjs`.
- **Decision.** `plain-diff-mod-limits` (plain-diff sends a diff to a model only past the secret filter).
- **Retire.** A case with a quoted emoji path shows the right label, and the case passes in `mods/plain-diff/plain-diff.test.mjs`.

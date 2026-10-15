# The plain-diff KEY=value rule misses some values and names

- **What.** The `KEY=value` rule skips all-digit values, values under 8 characters, and values with characters outside `A-Za-z0-9/+_=-`. `TOKEN=abc.def.ghi.jkl` and `API_KEY=12345678901` both pass. A new `notes.txt` that holds `ENCRYPTION_KEY=7f3a9c2e1b8d4f6a` is not caught by name, and no rule names `ENCRYPTION_KEY`. No measured miss exists for the value class yet.
- **Where.** The `KEY=value` content rule in `mods/plain-diff/hooks/lib.mjs` (`looksSecret`).
- **Decision.** `plain-diff-mod-limits` (plain-diff sends a diff to a model only past the secret filter).
- **Retire.** A wider value class and the key names are measured on real history. Each case passes in `mods/plain-diff/plain-diff.test.mjs`.

# A .env file under an innocent name passes the filter

- **What.** A `.env` body under an innocent name, such as `notes.txt`, passes the path test. A line such as `ENCRYPTION_KEY=` passes the content test, because the KEY=value rule names only API_KEY, SECRET, PASSWORD, PASSWD and TOKEN.
- **Where.** `isSecretPath` and `looksSecret` in `mods/plain-diff/hooks/lib.mjs`.
- **Decision.** `plain-diff-mod-limits` (plain-diff sends a diff to a model only past the secret filter).
- **Retire.** The content rule flags each KEY=value secret-shaped line, not only the listed names. A test with a `.env` body under `notes.txt` stays unsent.

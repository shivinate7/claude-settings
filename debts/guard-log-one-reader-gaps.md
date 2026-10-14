# The one-reader test misses other ways to split guard.log

- **What.** `OneReaderTests` flags only a literal `.split("\t")` call in `hooks/*.py` and `lint/*.py` files that name guard.log. A `partition`, `re.split`, `csv`, a split on a variable, or a reader in `merge/`, `janitor/` or `bin/` passes. Risk is low. The test names its one allowed fallback, which keeps an unread note from vanishing (`gate-hooks-fail-closed`).
- **Where.** `OneReaderTests`, the lint test that checks guard.log readers.
- **Decision.** `guard-log-read-weekly` (guard.log is read weekly, by one reader).
- **Retire.** The test flags each listed form, and a case per form goes red.

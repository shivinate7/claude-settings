# Hook catalog sees only `--flag` modes

- **What.** The catalog finds a script's modes only from a `"$g" --flag` argument. A script registered twice with a positional argument or a `-x` flag looks like one mode, so it needs no `Modes:` paragraph.
- **Where.** `CMD_FLAG` in `lint/hook_catalog.py`.
- **Decision.** none
- **Retire.** Read every argument after the script path as the mode key. A fixture with two registrations that differ only by a positional argument fails `--check` until a `Modes:` paragraph names both.

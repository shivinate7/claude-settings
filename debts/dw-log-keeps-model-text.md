# The decision-watch log keeps model text that may hold a secret

- **What.** The log keeps the FLAG `why` up to 2000 characters. That text is model words about a diff, and it may quote a secret. The log also keeps the first 200 characters of non-JSON phase-1 output, which is fixed prompt text only.
- **Where.** The log lines in `mods/decision-watch/hooks/register.mjs`.
- **Decision.** `decision-watch-mod-limits` (what the decision-watch mod cannot do yet).
- **Retire.** The log drops or redacts model text, and `mods/decision-watch/decision-watch.test.mjs` pins the new behavior.

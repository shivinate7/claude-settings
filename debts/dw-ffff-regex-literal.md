# The decision-watch asciiJson regex holds a literal U+FFFF

- **What.** The `asciiJson` regex holds a literal U+FFFF character.
- **Where.** `asciiJson` in `mods/decision-watch/hooks/register.mjs`.
- **Decision.** `decision-watch-mod-limits` (what the decision-watch mod cannot do yet).
- **Retire.** The regex writes the code point as an escape, and `mods/decision-watch/decision-watch.test.mjs` pins the match.

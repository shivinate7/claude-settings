# An override after an app note grants nothing

- **What.** In Claude Desktop, the app can put a `<system-reminder>` block (such as "Linked sessions now") at the front of the owner's prompt text. `override.PROMPT` matches only at the start of the prompt, after whitespace, so `override 60m` sent after such a note grants nothing and prints no "Override:" line. The owner sees the guard refuse again with no word why.
- **Where.** `hooks/override.py` (`PROMPT`, `grant`, `_grant_opus` through `OPUS_PROMPT`); `hooks/local_time.py` `grant_override`, which passes `hook["prompt"]` unchanged.
- **Decision.** `owner-override`.
- **Incident.** 2026-11-03 16:38 and 16:44 CST, session home-triage-4 (transcript 120a72a5-e128-4fc2-a6ca-bd378e980360), repo shivinate7/home: the owner typed `override 24h`, then `override 60m`; both prompts began with a "Linked sessions now" `<system-reminder>` block, and neither granted. The owner's `override you can touch the roadmpa here` at 16:30 CST had no note in front and granted.
- **Retire.** A prompt whose text, after any leading `<system-reminder>…</system-reminder>` blocks the app added, is an override word grants as it would alone. A note the owner pasted inside the text grants nothing, as today. A new test shows `override 60m` behind a leading note refused on main (red) and granted after the fix (green).

## Brief for the fixing session

Same lane as `local-triage-no-tier-proof` on this branch, or its own: one draft PR cut from main.

1. Read decision `owner-override` and `hooks/override.py`.
2. Strip only leading, whole `<system-reminder>` blocks, with the whitespace between them, before `PROMPT` and `OPUS_PROMPT` match. Never search the whole prompt for the word: an override must stay the owner's own first words.
3. Test first, red on main: `override 60m`, `override` and `opus 2h` each behind one and two leading notes grant; the word inside a note, or after other owner text, grants nothing.
4. Fix, then green. `bin/verdict` runs the hook suite green. Report cap: 25 lines.

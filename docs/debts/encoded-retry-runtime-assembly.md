# A refused word rebuilt at runtime passes after a refusal

**What.** After a harness or guard refusal, an agent rebuilds the refused word at runtime from parts, to get past the refusal. The forms are a concatenated or joined name, a variable join, `$(printf '%s%s' …)`, and a python string join. Sighting: a reviewer on PR #2425, in its round 3, had a probe refused by the env-file guard, then built the env file's name at runtime. Triage raised it on roadmap step `encoded-retry-after-refusal`.

**Where.** `hooks/guard_encoded.py` reads only a decode that is run, and an ANSI-C `$'\x..'` command word. The refusal row (`hooks/refusal_note.py`, `state/refusals/<session>.jsonl`) keeps the tool name and reason, not the command text. The COMMON line in `hooks/agent_brief.py` states the rule in words only. It forbids resending a refused command in another form, and names runtime assembly among those forms.

**Decision.** `encoded-retry-after-refusal`, a refused command is not sent again in an encoded form. Its Not read list names this form.

**Retire.** Closed when a red case in `hooks/test_guard.py`, with a fresh refusal row, refuses an assembled form of the refused command. Its no-refusal twin passes. The unrelated-assembly case depends on the open question in decision `encoded-retry-after-refusal`.

## Ruling

None yet.

# A refused word rebuilt at runtime passes after a refusal

**What.** After a harness or guard refusal, an agent rebuilds the refused word at runtime from parts, to get past the refusal. The forms are a concatenated or joined name, a variable join, `$(printf '%s%s' …)`, and a python string join. Sighting: a reviewer on PR #2425, in its round 3, had a probe refused by the env-file guard, then built the env file's name at runtime. Triage session 6 raised it on roadmap step `encoded-retry-after-refusal`.

**Where.** `hooks/guard_encoded.py` reads only a decode that is run, and an ANSI-C `$'\x..'` command word. The refusal row (`hooks/refusal_note.py`, `state/refusals/<session>.jsonl`) keeps the tool name and reason, not the command text. The COMMON line in `hooks/agent_brief.py` names the form in words only: escaped quotes, base64, hex escapes, a glob. A follow-up commit adds "built at runtime from parts".

**Decision.** `encoded-retry-after-refusal`, a refused command is not sent again in an encoded form. Its Not read list names this form.

**Retire.** Closed when a red case in `hooks/test_guard.py`, with a fresh refusal row, refuses an assembled form of the refused command. Its no-refusal twin and an unrelated assembly both pass.

**Design question.** Open. The owner is not asked yet. Narrow: keep the refused command text in the refusal row, and refuse a command whose assembled text equals it. General: refuse string assembly by its shape. Against the general rule: string assembly is ordinary shell and python, so a shape rule would refuse real work after any refusal. That is a false alarm, and a guard that cries wolf is spent (decision `guard-that-cries-wolf-is-spent`).

## Ruling

None yet.

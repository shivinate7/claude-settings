# A check-in or seed with no source field may reach the plain Opus ask judge

**What.** A plain Opus ask is refused when the UserPromptSubmit payload's `source` names a non-owner origin, such as `loop_wakeup`. Claude Code 2.1.308 sent no `source` on a typed prompt in one hook dump (review, 2026-11-04). 2.1.318 declares the field optional, and is unmeasured. So the normal path is the transcript fallback. That fallback catches a check-in or seed only if its record is in the transcript at hook time, and that is unmeasured. A Claude-written Opus ask in such text then reaches the judge. The haiku judge granted on 3 of 10 such asks, and a grant gives every role Opus for 2h.

**Where.** `hooks/override.py` `grant_opus_ask`, `_system_prompt_last` and `_seed_record`.

**Decision.** `owner-override` (the owner override and its Opus form).

**Retire.** Close it when the installed Claude Code sends `source` on every UserPromptSubmit: check one typed prompt and one check-in with a hook dump. In a cloud session, also check that the owner's typed prompt does not carry `sdk`, which the schema names for the Agent SDK. If it does, the plain ask fails closed there, and `OPUS_ASK_SOURCES` must change. Or measure, from inside the hook, that a check-in's and a seed's records are in the transcript when it fires. Refusing an absent `source` is not a fix: it refuses every typed plain ask.

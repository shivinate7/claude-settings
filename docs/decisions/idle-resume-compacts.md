# A session that sat idle compacts on the next message: Claude Code, not our hooks

Kind: process
Home: settings.json

## The question

The owner reported (2026-11-01 17:54 CST): after a session sits idle for a couple of hours, the first thing it does on his reply is compact, whatever the context size. Mostly cloud sessions. Is the cause ours, and what stops it?

## Answer

- Our hooks do not cause it (measured, see Evidence). The cause is Claude Code. It has two paths, one per surface.
- Desktop app and terminal: idle compaction, a documented feature, on by default (measured, docs). It compacts a conversation of 200,000 tokens or more after about an hour idle, when the one-hour prompt cache is on and feature flags are fetched. Your next message then uses the summary. On a 500,000-token meter, 200,000 is 40%, so it can look like "whatever the size" (unmeasured: no desktop transcript read).
- Cloud: the docs exclude cloud from idle compaction (measured, docs). Cloud compaction is size-based. A lane's trigger is 384,000 tokens, 80% of its 480,000-token effective window (measured, get_session). The meter shows 500,000, so a session at 347,177 tokens (69% on the meter) is near its trigger. That a wake pushes it over is inferred, not reproduced: 0 of 8 measured cloud idle wakes compacted.
- Not reported upstream. Idle compaction is documented. Open issues anthropics/claude-code#102260, #102332 and #105775 report the rollout (read by title and first 1,000 characters through the GitHub search API, 2026-11-01).

## Evidence

- Docs, read 2026-11-01. The `idleCompaction` section of code.claude.com/docs/en/settings-reference: "on by default", "default of 200,000", "about an hour has passed since the last request". Its scope is the terminal, the VS Code chat panel, and the desktop Code tab "when the session runs on your machine or over SSH". Cloud is not in the scope.
- Docs, code.claude.com/docs/en/claude-code-on-the-web: "Cloud sessions set `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` themselves, so compaction triggers partway through the auto-compact window".
- Changelog: 2.1.299 added idle compaction. 2.1.314 extended it to VS Code and the desktop Code tab, where "the summary is used on your next message if the prompt cache has expired".
- Thresholds, from get_session `autocompact_state` on 2026-11-01, Claude Code 2.1.316: this lane shows `effective_window` 480,000 and `threshold` 384,000. Other lanes show 384,000. The coordinator shows 441,600 (92%). Why the two differ is unmeasured.
- Cloud event logs, 2026-11-01. 5 lane sessions had 8 idle gaps of 31 to 361 minutes. Each gap ended in a worker restart. None compacted on the wake. The lanes held 212,287 to 347,177 tokens. Every compaction found was `trigger: auto`, with `pre_tokens` above its session's threshold: 387,854 against 384,000, and 441,707 against 441,600.
- Our hooks: no hook runs `/compact` or sets a compaction variable. On a cloud resume, `hooks/session_start.sh` prints 1,217 bytes and the cloud refresh hook (`install.sh --cloud`) prints 5,013 bytes (both measured 2026-11-01). Together that is near 1,600 tokens.

- Repro, this lane, 2026-11-02 (measured from its transcript and get_session). It idled 57 minutes, 00:15 to 01:12 UTC, then a scheduled message woke it. The worker restarted (epoch 1 to 2). It did not compact. Context went from 143,995 to 147,884 tokens: the wake added 3,889 tokens, hook output and the message included. So the wake alone pushes a session over only when it idles within about 4,000 tokens of its trigger.

## Unknown

- An owner message after 1 hour or more idle, in the cloud. Every long wake found came from another session's message or a scheduled check-in. The resume path is the same, so the result likely holds. Unmeasured.
- A gap past the one-hour prompt cache. The repro gap was 57 minutes and the cache still hit. Unmeasured.

## Mitigation

- Desktop and terminal: `"idleCompaction": false` in settings turns it off. The cost: a long session read after the cache expires is re-sent in full, at full input price. `CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS` raises the size at which it starts. This is the owner's choice. Until he chooses, the default stays.
- To tell which path ran: the terminal notice starts "Compacted while idle, before the prompt cache expired". The desktop notice includes "a summary written while you were away"; if you do not see it, switch to the Verbose view. No such notice means size-based compaction.
- Cloud: idle compaction has nothing to turn off. The env var `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, set for one session, moves the size trigger. A larger window costs more per turn, and it also moves the handoff checkpoints (record `precompact-handoff` rule 1).

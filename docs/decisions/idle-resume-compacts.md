# A session that sat idle compacts on the next message: Claude Code, not our hooks

Kind: process
Home: settings.json

## The question

The owner reported (2026-11-01 17:54 CST): after a session sits idle for a couple of hours, the first thing it does on his reply is compact, whatever the context size. Mostly cloud sessions. Is the cause ours, and what stops it?

## Answer

- The cause is Claude Code, not our hooks. There are two paths, one per surface.
- Desktop app and terminal: idle compaction, a documented feature, on by default. It compacts a conversation of 200,000 tokens or more after about an hour idle. Your next message then uses the summary. On a 500,000-token meter, 200,000 is 40%, so it looks like "whatever the size".
- Cloud: the docs exclude cloud from idle compaction. Cloud compaction is size-based. Lanes compact at 384,000 tokens, 80% of the 480,000 effective window. The meter shows 500,000, so a session at 347,000 (69% on the meter) is near its trigger. A wake adds tokens and can push it over.
- Not reportable upstream. Idle compaction is documented. Open issues anthropics/claude-code#102260, #102332 and #105775 already cover the rollout.

## Evidence

- Docs, read 2026-11-01. The `idleCompaction` section of code.claude.com/docs/en/settings-reference: "on by default", "default of 200,000", "about an hour has passed since the last request". Its scope is the terminal, the VS Code chat panel, and the desktop Code tab "when the session runs on your machine or over SSH". Cloud is not in the scope.
- Docs, code.claude.com/docs/en/claude-code-on-the-web: "Cloud sessions set `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` themselves, so compaction triggers partway through the auto-compact window".
- Changelog: 2.1.299 added idle compaction. 2.1.314 extended it to VS Code and the desktop Code tab, where "the summary is used on your next message if the prompt cache has expired".
- Cloud event logs, 2026-11-01, Claude Code 2.1.316. These are 5 lane sessions with 8 idle gaps of 31 to 361 minutes. Each gap ended in a worker restart. None compacted on the wake. The lanes held 212,287 to 347,177 tokens against a 384,000 threshold. Every compaction found was `trigger: auto`, with `pre_tokens` above its session's threshold: 387,854 against 384,000, and 441,707 against 441,600.
- Our hooks: no hook can start a compaction. On resume, `hooks/session_start.sh` prints about 520 bytes, and the cloud refresh hook (`install.sh --cloud`) prints about 5,000 bytes, near 1,300 tokens.
- Threshold formula: record `precompact-handoff` rule 1, the compaction window and trigger figures.

## Unknown

- An owner message after 1 hour or more idle, in the cloud. Every long wake found came from another session's message or a scheduled check-in, not from the owner. The resume path is the same, so the result likely holds. Unmeasured.
- How many tokens a cloud wake adds beyond our hook output. The event pages carry no token usage. Unmeasured.
- Why the coordinator's threshold is 441,600 (92%) and the lanes' is 384,000 (80%). Unmeasured.

## Mitigation

- Desktop and terminal: set `"idleCompaction": false` in settings to turn it off. The cost: a long session read after the cache expires is re-sent in full, at full input price. Or raise `CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS` to delay it. This is the owner's choice. Until he chooses, the default stays.
- To tell which path ran: the terminal notice starts "Compacted while idle, before the prompt cache expired". The desktop notice includes "a summary written while you were away" and shows only in the Verbose view. No such notice means size-based compaction.
- Cloud: nothing to turn off. A session that idles near 384,000 tokens compacts on its next turns either way.

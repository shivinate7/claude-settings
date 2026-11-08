# An agent's commit names its own model

## The ruling

Rule `commit-trailer-model` in `hooks/guard.py` refuses an agent's push when a commit it sends names another model in its Co-Authored-By trailer. Its home is `commit_trailer_hit` in `hooks/guard_trailer.py`. Layer: step `commit-trailer-model`, the coordinator's brief.

- The mistake: a Haiku agent signed a commit as Opus 5.5 because its brief said to (incident, commit `3b5516cf8`).
- The harm: the trailer misstates who wrote the code, and a reader of the log trusts the wrong model.
- The line the agent reads (`hooks/agent_brief.py`, the trailer line) says to name your own model as your own system prompt names it, and that no brief's trailer text overrides that.
- A hit: a push by an agent (the payload carries `agent_id`) whose unpushed commits hold a Co-Authored-By trailer that names a family other than the agent's, or the same family with another version. A family word with no version differs by family only. A trailer with no model word (`Claude`, `Claude Code`, a person) passes.
- The refusal names the commit by its short sha and never prints the trailer text, so the reason does not name the model it forbids (`git-remedy-never-names-target`).
- The commits are those no remote ref holds. Git's own trailer parse reads them (`%(trailers:key=Co-Authored-By)`), so a body line or the shell text never counts.
- The trailer parse looks for one of the four family words anywhere in the value, in any casing, as a whole word. Its version is the number right after the word, else right before it. A space, a hyphen or an underscore may sit between the word and the version, and a dot or a hyphen before the minor. So `Claude Opus 5.5`, `Claude-Opus-5.5`, `claude opus 5.5`, `Claude_Opus_5.5`, `Claude Opus4.5`, `Claude 3.5 Sonnet` and the model id form `claude-opus-5-5[1m]` all name a model.
- A trailer with no Claude family word passes: `Claude`, `Claude 2.1`, `Claude Code 2.1`, `GPT-4`, a person. The guard stops Claude's mistakes (decision `guard-guards-mistakes-only`), and no agent writes those names by mistake.
- A push is read where the push rules read it: `_push_calls` in `hooks/guard_merge.py`, which reads a push inside `bash -c`, `sh -lc` and the other wrappers through `inner_commands`. This rule has no reader of its own. The push forms `push -u origin x`, `push origin x`, a bare `push` and `push origin` are judged like `push origin HEAD:x`.
- Known limits, each held as a note with its reason in `docs/debts/notes.md`. Every unpushed commit in the push is judged against the pushing agent's model. A Co-Authored-By line that git's own parse does not read as a trailer is not judged; that GitHub also ignores such a line is unmeasured.
- The agent's models are two fields of the last assistant record in `<transcript minus .jsonl>/subagents/agent-<id>.jsonl`: `message.model`, and the top-level `requestedModel` beside `message`. Measured: `requestedModel` is present on 716 of 716 local assistant records. Unmeasured: a record where the served model differs from the requested one. The second field is read for that case, on the assumption that a fallback puts the served model in `message.model` and the agent's own choice in `requestedModel`. A trailer passes when it names either one; it is refused when it differs from every one that maps. A model id `claude-<family>-<major>-<minor>[suffix]` maps to `<Family> <major>.<minor>`; the families are `opus`, `sonnet`, `haiku` and `fable`.
- The transcript read stops at 16 MB: it starts at the file's last 64 KB and doubles the window until an assistant record shows, up to that cap. A file with no record in its last 16 MB passes.
- Fail open. An orchestrator's push, a missing, unreadable or empty transcript, a synthetic record, an unmapped id, a push with nothing new and any git error all pass. Measured: the SubagentStart and PreToolUse payloads carry no model field (hooks docs), and `message.model` in a transcript is undocumented, so a changed transcript shape must never block a push.
- The transcript path has one home, `agent_transcript_path` in `hooks/guard_core.py`; the guard's pid check (`in_own_agent_worktree`) reads it from there. `agent_transcripts` in `hooks/stall_watch.py` keeps its own join: the stall check is a recovery control and runs without the guard's modules.
- Cost: per agent push, one `git log`, and one transcript read (the file's last 64 KB, doubled until an assistant record shows) when a Co-Authored-By trailer is unpushed. No other process start, no file written, no timer. A call that is no agent's push costs nothing.

Protected by the `commit-trailer-model` cases in `hooks/test_guard.py`, red before the rule landed, and by the `commit-trailer-model` mutants in `hooks/mutate_guard.py`.

Kind: process
Home: hooks/guard_trailer.py

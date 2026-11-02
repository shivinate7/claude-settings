# Refusal lines from Claude Code 2.1.316 are missed

**What.** The PreCompact digest's refusal match misses four denial lines that Claude Code 2.1.316 writes: "Permission to read <path> has been denied.", "Permission to edit <path> has been denied.", "Permission for this tool use was denied: it requires interactive approval", and "Permission for this command was denied by a built-in Claude Code safety check". After compaction, a session can retry an act it had been refused before it. The lines come from this repo's own deny rules, such as Read(.env), Edit(~/.claude/settings.json) and Edit(~/.claude/hooks/**).

**Where.** `hooks/precompact_handoff.py`, `_REFUSAL`, which matches the first line of a tool result. Its refusal-shape cases are in `hooks/test_precompact_handoff.py`, near the table that starts at the "Permission to use Bash has been denied" case.

**Decision.** `precompact-handoff`, checkpoints keep the handoff current. Item 11 builds the `## Refused acts` section from the refusal match that this debt says misses lines.

**Retire.** Add one first-line pattern that covers both shapes, for example `^permission (to|for) .* (has been|was) denied`. Add one case for each of the four lines to the refusal-shape table. Each case goes red on the current `_REFUSAL` and green after the fix. Keep the existing "Permission denied" case as False, since it is a plain failure. The check is `bin/verdict python3 hooks/test_precompact_handoff.py`.

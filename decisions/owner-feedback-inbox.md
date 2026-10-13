# Owner feedback goes to an inbox before the turn ends

When the owner opens a feedback burst, a hook writes each message to a per-session inbox. The
session must jot every message down as kinded items before a turn can end.

## The question

How do we stop a session from acting on the first item of a feedback burst and losing the rest?

## The incident

The owner sends feedback in bursts, often mid-turn. A session sometimes acted on the first item
and lost the others. The rule that every ask gets a home at once (output-answer-has-a-home)
depends on the model remembering it. The oversight session raised this on 2026-10-13.

## The ruling

Owner ruling, 2026-10-13, from an interview in the claude-settings audit session.

- **Trigger.** A message whose first word is `fb` or `fb:` opens capture mode. A message that
  is only `fb done` closes it. Every owner message between the two is captured, so the back and forth
  stays in the record. A `fb` elsewhere in a message does nothing.
- **Capture.** The UserPromptSubmit hook appends each captured message verbatim, with its
  Central time, to `~/.claude/handoffs/<session_id>.inbox.md`. The file is outside git.
  Messages from other sessions are not captured.
- **Jot, not solve.** For each captured message, the session writes one or more items. Each item
  has an id (such as `fb-0958-2`), one kind, and a home. The work can wait. The jotting cannot.
- **Kinds and their homes.**
  - `ruling`: a decision on a question. Home: the handoff's NO HOME YET list, then a record.
  - `task`: work to do. Home: the handoff's next steps, or the repo's todo.
  - `question`: answered in the reply. Home: `answered`.
  - `note`: context with no decision. Home: `noted`.
  - `standing`: a session-only process, like a temporary CLAUDE.md. Home: the handoff's
    process-only section, which is re-read after compaction. Promote it to a ruling to keep it.
- **The gate.** A Stop check refuses to end a turn in three cases. A captured message has no
  items. An item has no kind or home. An open item id is missing from the handoff. The check reads ids,
  so a whole-file handoff rewrite that drops an item goes red. It exits on `stop_hook_active` in
  code, so it cannot loop.
- **After compaction.** The compact hook lists open item ids and says when capture is still open.

## Build plan

The hook and the check are Python and run on every platform the repo installs to.

### windows

Build in hooks/, register in settings.json, prove on this machine with install.ps1.

### macos

Same files. Prove on the Mac clone after `git pull` and install.sh.

## Named limits

- The trigger is the owner's to type. A burst sent without `fb` is not captured.
- The gate checks that items exist and are homed. It does not check that the work is done.
- `!` was not used as the opener: in the Claude Code terminal a leading `!` runs a shell command.

Kind: build
Plan: decisions/owner-feedback-inbox.md#windows (windows)
Plan: decisions/owner-feedback-inbox.md#macos (macos)

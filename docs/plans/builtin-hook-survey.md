# Plan: which model-call hooks can move to the built-in prompt hook

This survey answers roadmap step `watcher-builtin-hook-survey` (which model-call hooks can move to
Claude Code's built-in prompt hook), for waiting-page item 248. It read each hook that calls a model
at main `335a6974a`, and the Claude Code hooks docs on 2026-11-07. No code or setting changed.
"Unknown" marks a fact no read confirmed.

## Verdict

None of the nine callers (ten judges: the SendMessage hook has two) moves today. Two come close: the prose judge and the SendMessage wording
judge. Both lose the owner override (decision `owner-override`) if they move, and the prose judge also
loses its `xhigh` effort. Each caller's model and effort is its row in decision `agent-model-cap`
(the model per role), except the override's Opus-ask judge, which has no row there.

| Caller (event) | Gold standard: what the built-in hook must keep | Can move | Gap (why not) | Cost now |
| --- | --- | --- | --- | --- |
| `hooks/call_judge.py` (PreToolUse: Agent, AskUserQuestion, ArtifactData) | Override lift; code checks before the model; one model per check | No | It runs `question_form` checks in code first and skips the model on a hit. It picks the page's item writes in code. It calls Sonnet (spawn) or Opus (question reviewer) by case. A prompt hook has one model and cannot read the override file | One `claude -p` start per judged call; latency unmeasured |
| `hooks/override.py` Opus-ask judge (UserPromptSubmit, through `hooks/local_time.py`; the calls are `call_judge.opus_ask` and `opus_scope`) | Writes the override file from the owner's words | No | It writes the Opus override file and reads earlier prompts from the transcript. A prompt hook writes nothing and reads no file | One Haiku start at effort low for each plain owner prompt with the word `opus`, not a keyword form such as `opus 2h`; a second only after a yes with no role named and an earlier owner prompt; latency unmeasured |
| `hooks/prose_judge.py` (PreToolUse: Edit, Write) | Path filter; Haiku at `xhigh`; override lift | No, nearest | An `if` rule can now do the path filter: the hooks page gives path globs such as `Edit(**/src/**)`. Unknown: whether such a glob ignores case, as `is_prose` does. Two gaps stay: a prompt hook has no effort field, and it cannot read the override file | One start per Edit or Write under a `decisions` folder; latency unmeasured |
| `hooks/reply_judge.py` (Stop) | A note on the next turn, never a refusal; every fifth Stop, plus each reply with an Input Needed label, the words "blocked on" or a Markdown table; Haiku at `xhigh` | No | A prompt hook can only allow or refuse. A Stop refusal makes Claude go on, which its decision `reply-judge-samples-never-refuses` forbids. A prompt hook cannot sample, so it would run on every Stop. No effort field | One start per sampled Stop, and per Stop whose reply carries the label, "blocked on" or a table; 6.6 to 8.0 s, 3 runs on the owner's machine (decision `reply-judge-samples-never-refuses`) |
| `hooks/feedback_guard.py`, repeat check (Stop) | Reads this inbox, other sessions' inboxes, roadmap steps (`git grep`) and backlog files; writes the inbox | No | A prompt hook sees only the event's JSON. An agent hook can read files but is experimental and has no documented way to write the inbox | One start per Stop with a new inbox item and at least one candidate, after one `git grep` for candidates; no model start otherwise; latency unmeasured |
| `lint/report_guard.py`, past-ruling check (Stop) | Ruling candidates read from the repo; fails closed; code checks the cited id | No | The candidates come from repo files in code. An error refuses (`cannot_run`); a prompt hook's error is undocumented and the docs' general rule is fail open. The cite check runs in code after the model | One start per Stop whose reply asks the owner something; latency unmeasured |
| `hooks/sendmessage_state.py`, wording judge (PreToolUse: SendMessage) | Override lift; Sonnet at default effort | No, nearest | It judges the call's JSON only, which a prompt hook can do. It left the prompt hook for one reason: a prompt hook cannot read the override file | One start per send; latency unmeasured |
| `hooks/sendmessage_state.py`, busy judge (same hook) | Reads the receiver's state from the session board; Haiku at `xhigh` | No | The board read runs `node` and `claude agents --json`; a prompt hook runs no code. No effort field | One start per send to a busy receiver; latency unmeasured |
| `mods/decision-watch` (turn end) | Runs on the session's own sign-in | No: a mod, not a `settings.json` hook | It is a `turn.complete` handler that calls `$.model.complete`, the app's own login, not `claude -p`, so it needs no move. The python path (`hooks/decision_watch.py`) has no hook entry in `settings.json` | No `claude -p` start |
| `mods/plain-diff` (the `/plain-diff` pane) | Runs on the session's own sign-in | No: a mod command, not a `settings.json` hook | It calls `$.model.complete` (Haiku) when the owner opens the pane, so it needs no move | No `claude -p` start; one Haiku call per changed file with no note |

"Cost now" counts model starts. Each start is one `claude -p` child with `CLAUDE_CODE_OAUTH_TOKEN`
through `decision_watch.invoke_model`. Other starts stay after a move. The feedback guard runs `git grep`.
The question reviewer and the past-ruling check run `git cat-file --batch` in `hooks/question_form.py`.
Each SendMessage runs `node` and `claude agents --json` for the busy judge. Latency
is unmeasured unless a row cites a measure: this cloud session's `guard.log` holds no timing line, and
the docs give no timing figure for a prompt hook.

## What a move would gain and lose

- Gain: no `claude -p` start and no OAuth token passed to a `claude -p` child. The billing and sign-in of
  a prompt hook are not documented, so the cost gain is unknown.
- Gain: `if` filters a tool event by permission-rule syntax, path globs included, and a Stop prompt hook
  gets `last_assistant_message`.
- Lose: the override lift, the `guard.log` line and any code check before or after the model.
- Lose: effort. A prompt hook takes no effort field, so a Haiku `xhigh` judge runs at the default.
- Lose: fail mode. Prompt-hook timeout and model-error behaviour is not documented. The hooks page's
  general rule is that a failed hook lets the action go on.
- Lose: notes. A prompt hook answers only `ok`, `reason` and `impossible`: no `systemMessage`, no
  `additionalContext`, no ask.
- Lose: events. PreCompact, SubagentStart and SessionStart take no prompt hook.

## What the docs say now

Source: the hooks reference (https://code.claude.com/docs/en/hooks.md), read by a `claude-code-guide`
agent on 2026-11-07.

- Events: PreToolUse, PostToolUse, PostToolUseFailure, PostToolBatch, PermissionDenied,
  PermissionRequest, Stop, SubagentStop, TaskCreated, TaskCompleted, TeammateIdle, UserPromptSubmit,
  UserPromptExpansion.
- Input: the hook's JSON (`$ARGUMENTS`), with `transcript_path`, `effort` and the event's fields. A
  prompt hook reads no file. An agent hook can read files, runs up to 50 turns, and is experimental.
- Fields: `model` (default: the background model), `timeout` (30 s prompt, 60 s agent), `if` (tool
  events only), `continueOnBlock` (prompt only). No effort field. `onFailure` takes only command and
  http hooks.

## When to ask again

Run this survey again when one of these lands in the hooks docs:

- An effort field on prompt hooks. The prose judge then moves if the owner accepts no override lift.
- A way for a prompt hook to honour the owner override. The wording judge then moves. The prose judge
  moves only when the effort field lands too.
- A documented fail mode or billing for prompt hooks. The cost rows can then be measured.

## Stale text found, not changed

These are notes, not asks. Each needs its own lane:

- `hooks/prose_judge.py`, lines 3 and 4, says a prompt hook cannot look at the path. The `if` field
  now does that, by a path glob (hooks page).
- `docs/decisions/haiku-prompt-hooks.md`, the bullet that starts "A prompt hook sees only the event's
  input": a Stop prompt hook now gets `last_assistant_message`, the final reply.

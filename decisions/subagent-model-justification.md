# Subagent model justification

CLAUDE.md says two things about a subagent model above Sonnet. "Justify a model
above Sonnet in one line." "Once set up, turn each rule below into a hook or
check." This entry records the check that makes the second sentence true for the
first one.

## The rule

`hooks/model_gate.py` runs as a `PreToolUse` hook on `Agent` and `Workflow`
calls. It reads the tool payload with `json.loads`. It never scans the raw text
with a pattern match.

A model counts as above Sonnet when its name holds neither `sonnet` nor `haiku`.
An empty or absent model is not above Sonnet.

When a call asks for a model above Sonnet, the gate looks for a line matching
`MODEL-JUSTIFICATION: <text>` in the prompt or script. The match is case
sensitive. It needs at least twelve characters of text after the colon.

* No marker, or a marker under twelve characters: deny. The reason names the
  marker to add. It does not name the model that was refused. CLAUDE.md: "A
  refusal's printed remedy never names the forbidden target."
* A valid marker: ask. The reason states the requested model and quotes the
  justification. The approver then decides against a stated case, not a blank
  prompt.

## The three gaps this closes

The gate it replaces was one inline shell command in `settings.json`. It
grepped the whole stdin payload for the first `"model"` string. It asked when
the value looked above Sonnet, with no deny path at all.

1. **No deny path, ever.** Every call above Sonnet reached "ask", justified or
   not. A justification was welcome but never required. `model_gate.py` denies
   the call outright when no marker is present.
2. **The grep read prompt text as the model field.** A payload whose prompt
   quoted `"model": "sonnet"` matched before the real `tool_input.model` value
   did. Grep has no notion of which JSON key a string sits under. The real
   field could hold an opus id, and the old hook would still see "sonnet" and
   allow. `hooks/test_model_gate.py` carries this case, and it fails against
   the old hook: feed the old command a payload with
   `tool_input.model = "claude-opus-4-1-20250805"` and a prompt that reads
   `"model": "sonnet"`, and it answers ask. It quotes the masked model, not
   deny. `model_gate.py` reads `tool_input.model` by key and denies.
3. **`Workflow` and `fork` were not covered.** The matcher was `Agent` only.
   A `Workflow` script naming an opus-class agent model, or an `Agent` call
   with `subagent_type: "fork"`, passed with no hook running at all.
   `model_gate.py` is wired with matcher `Agent|Workflow`. It treats `fork` as
   needing the marker, under the rule below.

## The fork deviation

The option approved before this build was: deny `subagent_type: "fork"` on a
session already running above Sonnet. A fork carries no `model` field of its
own. It inherits whatever model the parent session is running. A `PreToolUse`
hook's stdin payload does not carry the session's model at all.

A hook that guessed the session model from an environment variable, a file, or
a heuristic would be the kind of guess CLAUDE.md rules out. "Never guess an
answer the code should give you."

So the fork rule asks for the marker on every fork, on every session. This
holds whether that session runs Sonnet or a model above it. A fork on a
Sonnet session now needs a justification it did not strictly need under the
approved option. That is a real cost. It pays for not guessing the one field
the hook cannot read. If the harness starts passing the session model into the
`PreToolUse` payload, this rule should read it. It should then fall back to
allow when the session is at or below Sonnet.

## Where this lives

This repository had no `decisions/` folder before this entry. This file starts
one, one folder per record kind. CLAUDE.md: "Give each record its own file, one
folder per kind." No number is claimed here. The file name is a slug.
CLAUDE.md: "Never allocate a numbered record on a branch. Write a slug."

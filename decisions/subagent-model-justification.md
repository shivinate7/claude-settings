# Subagent model justification

CLAUDE.md says two things about a subagent model above Sonnet. "Justify a model
above Sonnet in one line." "Once set up, turn each rule below into a hook or
check." This entry records the check that makes the second sentence true for the
first one.

## The rule

`hooks/model_gate.py` runs as a `PreToolUse` hook on `Agent` and `Workflow`
calls. It reads the tool payload with `json.loads`. It never scans the raw text
with a pattern match.

A model counts as above Sonnet unless it matches a recognised Sonnet or Haiku
id. This is an allowlist, not a substring test. An id the allowlist does not
recognise counts as above the bar. It is not assumed cheap.

The gate first strips two optional parts from the id:

* a vendor prefix: `us.`, `eu.`, or `apac.` followed by `anthropic.`, or a
  leading `anthropic/`
* a trailing context suffix, such as `[1m]`

It then checks the id against a fixed set of shapes:

* the bare word `sonnet` or `haiku`
* `claude-sonnet-<version>` or `claude-haiku-<version>`, with an optional
  trailing date
* `claude-<version>-sonnet` or `claude-<version>-haiku`, with an optional
  trailing date

`opus` or `fable` anywhere in the id overrides a shape match. An alias such as
`claude-opus-4-sonnet-alias` is still above the bar. An empty or absent model
is not above Sonnet. The harness then applies the Sonnet default from
`env.CLAUDE_CODE_SUBAGENT_MODEL`.

When a call asks for a model above Sonnet, the gate looks for a line matching
`MODEL-JUSTIFICATION: <text>` in the prompt or script. The match is case
sensitive. It needs at least twelve characters of text after the colon.

* No marker, or a marker under twelve characters: deny. The reason names the
  marker to add. It does not name the model that was refused. CLAUDE.md: "A
  refusal's printed remedy never names the forbidden target."
* A valid marker: ask. The reason states the requested model and quotes the
  justification. The approver then decides against a stated case, not a blank
  prompt.

### The Workflow test is a shape test

A `Workflow` script can set a `model` option many ways. It can use a quoted
literal, a variable, or a concatenation. It can also use a ternary, a member
expression, a template literal, or a value from `args`.

A `PreToolUse` hook cannot run the script. It cannot know what a variable or
an expression will resolve to.

So the gate reads `model:` by shape, not only by literal value. The key side
matches a bare, double-quoted, or single-quoted `model`, with `:` or `=` as
the separator. Member access counts too: `opts.model = ...` and
`opts["model"] = ...` both match.

* A quoted literal below the bar: allow.
* A quoted literal above the bar: needs the marker. Same as an Agent call.
* Any other value: needs the marker too. The gate cannot prove it is below
  the bar. It cannot allow what it cannot prove.

Two things are skipped on purpose. This keeps the test about agent options:

* a line the script comments out with a leading `//`
* the script's own `export const meta = {...}` header

A phase's `model` override in that header names the workflow's own config.
It is not an agent call.

This is a deliberately crude text test. It is not a JavaScript parser. A
false ask is the accepted cost of a value the gate cannot resolve. The
marker clears it, the same as any above-bar id.

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

## Two gaps closed after review

A review of this gate found two more bypasses. The owner saw both and
approved this fix. It supersedes the rule shipped in `8d30693`.

**Gap 1: the substring test was an allowlist waiting to happen.** The old
`is_above_sonnet` allowed any id that contained `sonnet` or `haiku`
anywhere. `claude-opus-4-sonnet-alias` names the opus family. The old test
still read it as below the bar, with no marker asked at all. The fix
inverts the test to an allowlist. See "The rule" above for the exact
shapes it recognises.

**Gap 2: a script could name its model where the gate could not see it.**
The old `SCRIPT_MODEL_RE` only matched a quoted literal after `model`. A
script could set the option through a variable instead:

    const M = 'claude-opus-5'
    agent(prompt, { model: M })

No quoted literal above the bar ever appeared in the script text. The gate
found nothing to judge, and the call passed with no marker. The fix makes
the Workflow test a shape test. See "The Workflow test is a shape test"
above.

**The accepted cost.** Both fixes trade a known miss for a new kind of
false ask. An id the allowlist does not recognise now asks for the marker,
even when the model is in fact cheap. A `model:` value the gate cannot
resolve now asks for the marker too, even when the script sets it below
the bar. Both cases clear on their own terms: add the marker, or extend
the allowlist to cover the id after the shape becomes a known one.

## Where this lives

This repository had no `decisions/` folder before this entry. This file starts
one, one folder per record kind. CLAUDE.md: "Give each record its own file, one
folder per kind." No number is claimed here. The file name is a slug.
CLAUDE.md: "Never allocate a numbered record on a branch. Write a slug."

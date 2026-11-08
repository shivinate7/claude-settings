# Plan: an owner grant typed in one session reaches the session it names

Owner, 2026-11-01 22:37 CST, in the coordinator's chat: "a grant here should allow for a grant there."

Status: signed off as written (owner, Cockpit item 152, pick a, 2026-11-03 18:21 CST). Ruling: decision grant-reaches-lanes. Revalidated 2026-11-06 (owner, page item 221, 12:36 CST: 'is this still valid? A is ok to do'). Build waits on question 3.

## The problem

The owner types a grant in the coordinator's chat. The coordinator relays it to a lane or a batch
runner with `send_message`. The auto-mode classifier in that session refuses the act anyway. The
owner then types the grant again in each session.

Incidents, coordinator-reported, 2026-11-01:

- Batch runner 8: its merges were refused as "Merge Without Review".
- The builder of lane runner-merge-allow: refused as "[Self-Modification]".
- The coordinator's brief for item 149 b (a waiting-page answer): refused as self-modification. The
  step record says Nov 1 23:06 CST, which is later than this plan was written: the time is
  unverified. This is step page-save-reaches-auto-mode. Its aim: auto mode counts a page save as the
  owner's grant, as rule questions-go-to-owner already rules ("My save on that page is my grant"). Closed by section 4.

The guard layer is solved in its own session: `refuse()` in `hooks/guard_core.py` and decision
owner-override (the typed `override` word). The open problem is the classifier layer only.

Notes line `auto-mode-refuses-page-grant` in `docs/debts/notes.md` holds the coordinator's
`send_message` refusal of Nov 1 23:05 CST.

## 1. How the classifier decides today

Source: Claude Code docs, fetched 2026-11-02. The docs were re-read on 2026-11-06 with container 2.1.319. They still document a classifier skip for a mod's `tool.check` only, and say nothing for a hook `allow`. The pages carry no version stamp. HTTP
Last-Modified is 2026-11-01. The highest version the pages cite is v2.1.311. The container ran
2.1.316 at writing and 2.1.318 on 2026-11-03. Whether the pages match: unknown.

What it reads:

- "the classifier sees user messages, tool calls other than read-only lookups such as file reads
  and searches, and your CLAUDE.md content. Tool results are stripped from those requests"
  (https://code.claude.com/docs/en/permission-modes.md#how-the-classifier-evaluates-actions)
- A cross-session message: "Claude Code tells B's Claude that the message came from another
  session, not from you" (https://code.claude.com/docs/en/cross-session-messaging.md#how-a-session-treats-an-incoming-message).
  In a cloud session the message arrives inside a `ReadNotifications` tool result, which the
  classifier never sees (measured in this lane, 2026-11-01 22:38 CST).

What counts as the owner's word:

- "If you tell Claude that a blocked action is allowed, the classifier reads that as your approval"
  (permission-modes.md#approvals-you-state-in-conversation)
- "Claude's own judgment that a condition was met does not lift it."
  (permission-modes.md#boundaries-you-state-in-conversation)
- Hook context is "wrapped... in a system reminder" and, per the docs, does not appear as a chat message
  (https://code.claude.com/docs/en/hooks.md#add-context-for-claude).
- `classifierContext`: "the classifier treats the note as unverified, application-provided context.
  The note never establishes user intent" (hooks.md#annotate-a-result-for-the-auto-mode-classifier).
  Only in-process SDK callbacks "may weigh a user statement relayed in the note as user intent".
  This setup has none.

Settings: `autoMode` holds four lists of prose rules and one switch
(https://code.claude.com/docs/en/settings-reference.md#automode). The lists are `environment`,
`allow`, `soft_deny` and `hard_deny`. The switch is `classifyAllShell`. The classifier
reads it from user, managed or `--settings` scope only, never from project settings
(https://code.claude.com/docs/en/auto-mode-config.md#where-the-classifier-reads-configuration).
Hot reload of `autoMode`: not documented.

What skips the classifier:

- Permission rules: "Actions matching your allow, ask, or deny rules resolve immediately"
  (permission-modes.md#how-the-classifier-evaluates-actions).
- A mod's `tool.check` approval: "a call the mod approves runs without a classifier check"
  (https://code.claude.com/docs/en/permissions.md#precedence-among-rules-hooks-and-mods). With a
  Team or Enterprise login, deny rules, ask rules and hook blocks still hold.
- A `PreToolUse` hook's `allow`: "allow skips the permission prompt" (hooks.md). Whether it skips
  the classifier: measured 2026-11-06 12:49 CST, 2.1.319, cloud container, nested `claude -p --permission-mode auto --model sonnet`, scratch settings with one `PreToolUse` hook returning `allow`. Control, no hook: debug log "Slow permission decision: 2391ms for Bash (mode=auto, behavior=allow)" on `git push --force` to a scratch local remote. With the hook: "Hook approved tool use for Bash, bypassing permission prompt", decision 9 ms, and no permission-decision line. Limits: headless run, not a remote session. The classifier allowed the control, so the probe did not see a refused act lifted. A refused act, measured 2026-11-08 (decision grant-reaches-lanes, section "The probe of a refused act"): a hook `allow` on a settings-file write that relayed text asked for did not lift the "[Self-Modification]" refusal, because a safety check sends the call through the full pipeline. Unmeasured: sibling-hook `deny` against `allow`, and whether an `Agent` spawn meets a safety check.

**The finding that shapes the plan.** No text a hook writes can become owner words that the
classifier sees. The docs say so twice. So no design here tries to persuade the classifier. Each
design is a transport that carries the owner's own typed words, plus a deterministic gate in the
receiving session that approves the named act before the classifier runs. Question 1 was answered by the 2026-11-03 sign-off (section 6).

## 2. The parts every design shares

### The grant word

A hook cannot bind free prose to one act (rule outcomes-grant-covers-named-act, a grant covers the
act it names, never a variant). So the grant is a typed word with a fixed form, like `override 15m`
and `opus builders 2h`:

`grant batch-runner merge <pr> <n>[m|h]`, `grant <lane slug> self-edit <n>[m|h]`, or
`grant off <lane slug>` (`grant off batch-runner` for the runner)

- The whole prompt, in any case, after leading whitespace. Any other text grants nothing, as for
  `override`.
- `<lane slug>` names one target. A branch slug changes on a checkout, so the gate compares it to
  the session's tags, set when the session was made: `cs-step:<slug>` for a lane, `cs-build:<tier>`
  for a batch runner, and `cs-repo:<owner>/<name>` for both, since step ids repeat across repos.
  The coordinator writes the tags, so a mistyped tag routes a grant to the wrong session. It is
  still one named act for the owner's length. A session with no matching tag fails closed. How the gate reads the
  tag (one `get_session` at start, or the start hook): to be named in the build. Unmeasured.
- `<act>` comes from a fixed catalogue in one home, a constant the gate reads (rule
  building-allow-list-is-the-constant). The act's full scope sits in the owner's words or the
  constant, never in a record a model writes. First entries, one per incident:
  - `merge <pr>`: superseded, pending question 3. Decision `standing-merge-grant` and the "Owner Session Message" coordinator-to-runner merge carve-out in settings.json `autoMode.allow` cover the incident. No "Merge Without Review" refusal is on record after 2026-11-01. Scope if kept: `~/.claude/bin/merge <pr> --confirm` for that PR number only, in the gate. The
    cloud rule still allows any PR (section 2, the gate). The PR is required. Only the session
    tagged `cs-build:batch-runner` for the repo, never its agents: on main, every other session
    hands its merge to the batch runner (session-start hook, merge role).
  - `self-edit`: candidate act, pending question 3. As written it gates nothing. Measured the same way (2026-11-06): a Write to `.claude/worktrees/lane/hooks/probe.py` logs "Skipping auto mode classifier for Write: would be allowed in acceptEdits mode" with no hook at all. So an Edit or Write in a worktree never reaches the classifier. The refused act on record is a lane's `Agent` spawn whose brief edits rule files (notes line `classifier-refuses-rule-record-writer` in `docs/debts/notes.md`, 2026-11-03 22:30 CST). Scope if kept: an Edit or Write in the calling agent's own worktree (its cwd's checkout), to `hooks/`, `lint/`, `skills/` or
    `agents/`. It takes no PR. Never `settings.json`, `.claude/` or `state/`, and never a path
    outside that worktree. A written allow rule or hook would outlive the grant, because a file
    does not expire. Edits in a lane worktree are not live: the pointer checkout stays on main.
- A waiting-page answer is not an act of its own (section 4).
- The length is required, with its unit: a bare number grants nothing, as for `opus 4`. The clock is the server time of the owner's event, never the target's.
- `grant off <lane slug>` ends every grant for that target. It travels like a grant. The gate
  takes the newest grant per act, and an off ends all of them. An off whose relay is lost leaves the
  grant to its end, so lengths stay short.

### The gate

The gate runs in the receiving session, before the classifier. It lifts the classifier only. It
lives in the guard hook and emits `allow` only after every check of that hook passed. It cannot
see sibling hooks: each hook decides alone (decision owner-override, known limit). Whether a
sibling's `deny` still outranks the gate's `allow` is part of the step 1 probe. It never lifts an act on the
"Outside every override" list of decision owner-override (role and model guards, frozen paths). It approves only a call that matches
the act in the catalogue exactly. Anything else falls through to the classifier as today. Three
gates exist:

| Gate | Skips the classifier | Per session, expires | Cloud | Gold standard |
|---|---|---|---|---|
| `PreToolUse` hook returns `allow` | Yes, measured 2026-11-06 (section 1) | Yes | Yes | Documented skip |
| Mod `tool.check` approves | Documented | Yes | Unknown whether mods load in cloud sessions | Documented and loads everywhere |
| Static `permissions.allow` rule | Documented | No | Yes | Scoped and expiring |

The static rule is today's tool (decision auto-mode-owner-acts, `add_repo` and `archive_session`).
It cannot scope to one session or expire, so it is the baseline only.

`merge/cloud_allow.json` already holds such a rule in the cloud:
`Bash(~/.claude/bin/merge * --confirm)` and `Bash(~/.claude/bin/merge * --confirm *)`, for every PR.
Decision auto-mode-owner-acts says the classifier does not judge a call that rule matches. Batch
runner 8 was still refused "Merge Without Review" (coordinator-reported, 2026-11-01). The refused
command is unknown: a search of the newest 115 events of runner 8's transcript (2026-11-03 18:24
CST) did not reach it. A command outside the rule's form, such as an absolute path or `--confirm`
before the PR, would explain the refusal and leave the record true. If the rule matched and the
classifier still refused, the refused-act half of the step 1 probe reads whether a hook `allow` lifts it.
The `merge <pr>` act is narrower
than that rule, so it adds nothing while the rule stands. Question 7 records the rule's status (section 6).

Build step 1 of any design is a probe in one session. The skip is measured (section 1, 2026-11-06): a hook `allow` skips the classifier. That probe used an act the classifier allowed, so it did not test a refused act. A hook returns `allow` on one act the
classifier refuses today. The transcript's `permission_decision` shows the result. If the
hook gate does not lift a refused act, the mod gate is next, with its own cloud probe. Step 1 also
probes: an event a lane sends into the coordinator, an owner event from the web and the phone
clients, and whether the relay's `send_message` is refused (entry "Owner Session Message" has a coordinator-to-runner merge carve-out in settings.json
`autoMode.allow`).

### Agents

The refused act on record is a lane's `Agent` spawn, not an Edit or Write (`self-edit`, section 2). A timed `override` reaches agents
(decision owner-override). The gate runs in every `PreToolUse` of the session, so it reaches agents
the same way. It reads the grant from the lead session's transcript or state, never the agent's.
`merge` never reaches agents, so a reviewer agent cannot merge. Question 4 is moot (section 6).

## 3. The designs

### Design A: server-attested pointer (cloud and the owner's computer)

Transport:

1. The owner types `grant batch-runner merge 1049 2h` in the coordinator.
2. The coordinator's prompt hook (`hooks/local_time.py`) checks the form and prints one context
   line: the grant parsed, and the relay to send. It writes nothing beyond the inbox line it
   already writes for each prompt. The hook gets no event uuid, so the pointer is the coordinator's
   session id plus the grant text.
3. The coordinator relays only the pointer: `send_message` with "grant in session <coordinator
   id>: <grant text>".
4. The target calls `list_events` on the coordinator with kind `user`, and `get_event` on the match.
   The result lands in the target's transcript as a tool result, written by the harness, not by the
   model.
5. The gate reads that tool result from the transcript. It approves the act only when the event:
   - is a user event whose content is a plain string, not a tool result;
   - has `isSynthetic` false and an `inbound_origin` that marks the owner's client, both returned
     by `get_event`;
   - carries `client_platform` (measured once: the owner's typed "b" at 22:43 CST had
     `"client_platform": "desktop_app"`; relayed messages arrive as `ReadNotifications` tool
     results with `"origin": "mcp_send_message"`). A read of the coordinator's newest ~170 user events (2026-11-06 12:38-12:46 CST) found no owner-typed event and no `client_platform` or `inbound_origin` field. Web and phone values stay unmeasured. Until each
     client is probed, the gate fails closed on it. The probe records `inbound_origin` and
     `created_at` on an owner event and on a relayed event. The gate allow-lists the measured
     values and fails closed when either is missing;
   - is the whole grant word, names this session, and names the act of the pending call;
   - is inside its length, by the event's `created_at`.

What a mistaken relay can do: point at the wrong event. That event is not a grant word for this
session, so nothing is approved. A paraphrase cannot widen the grant, because the gate reads the
owner's text, never the relay's. A forged relay needs a forged server event, which the model cannot
write.

What stops it working:

- `client_platform` is not a documented field. If it changes, the gate fails closed and the
  classifier runs as today. A check pins the field on a recorded event.
- `get_event` across sessions: measured to work from this cloud lane to its cloud coordinator
  (2026-11-01 22:44 CST). Decision auto-mode-owner-acts records one refusal,
  `elevated_session_untrusted_device`, for a lane reading its coordinator. Which pairs refuse:
  unknown. A session on the owner's computer reading a cloud event, and the reverse: unmeasured.
- The model must call `get_event`. If it skips that, the classifier runs as today. That is a lost
  grant, never a widened one.

The gate approves `merge` only in the batch runner. A missed `grant off` is the gap named in
section 2.

### Design B: a frozen grant file (owner's computer only)

Transport: the coordinator's prompt hook writes `state/grant/<target session>.json` with the owner's
verbatim words, the act and the end time. This is the override file's pattern. `state/` is frozen
against Claude's writes, so no session can grant itself.

Gate: the same gate, reading the file instead of the transcript.

What a mistaken relay can do: nothing. No relay carries the grant. A mistaken target in the owner's
own words grants the wrong session; the fixed form and one-target rule keep that to one named act.

What stops it working: cloud sessions run in separate containers with no shared disk. A cloud
coordinator cannot write a file a computer session reads, and the reverse. Design B covers only
sessions on one machine.

### Design C: a record on a shared store (rejected)

Transport: the grant goes to a store both sides read. That is the roadmap branch (the step grant of
decision owner-override does this today) or the waiting page's `answers/<id>`.

What a mistaken relay can do: anything a model can write. Only a session tagged
`cs-build:triage` can push to the record branch (guard rule roadmap-one-writer, `hooks/guard.py`),
but that session is a model too, and an override lifts the rule. `ArtifactData` writes "as the person", so the page cannot tell the owner's save from a
model's. No guard refuses a model's write to `answers/<id>` (`hooks/call_judge.py` judges item
writes only). The answer record has no viewer field (`skills/waiting-page/page.html`). An HMAC key
in the cloud environment's secrets is readable with `env`, so signing proves nothing either.

So Design C carries model text, which is the problem we have today. Decision `relayed-grant-read-from-page` accepted that risk (`ArtifactData` writes as the person, no guard on `answers/<id>`, no viewer field) under decision `guard-guards-mistakes-only`. C stays out for a grant typed in chat only, because a chat answer has no `answers/<id>` (decision `relayed-grant-read-from-page`, Gaps, "Chat answers"). Design A closes that gap. Design C stays as
the comparison: a store counts as owner evidence only where the decision's attribution rule holds (the page is the owner's private page, and no session writes `answers/`).

The live step grant (decision owner-override) is such a store. It lifts only the Opus spawn ask,
a cost act, not a safety act. This plan leaves it as it is.

### Cover

| Session pair | Design A | Design B |
|---|---|---|
| Cloud coordinator to cloud lane | Measured readable | No |
| Computer coordinator to computer lane, same machine | Unmeasured | Yes |
| Cloud to computer, or computer to cloud | Unmeasured | No |

A pair no design covers keeps the classifier as today.

Recommendation: Design A as the one design, with Design B only if the computer probes of Design A
fail.

## 4. Page save (superseded)

The copy-line design is cut: page answers now count through `page_grant.py` and the "Relayed Grant" `autoMode.allow` entry, by decision `relayed-grant-read-from-page` (PR #1299, merged 2026-11-06, batch 31), which closes step `page-save-reaches-auto-mode`.

## 5. Costs

Design A, per grant: one prompt-hook parse in the hook already running, one `send_message`, one
`list_events` and one `get_event`. Per tool call in the target: one bounded tail read of the
transcript inside the guard hook already running, with the tail readers of `lint/_transcript.py`.
The read runs on every gated tool call, to learn whether a grant result exists. No new process,
timer or file (rule outcomes-mechanize-rules). A test proves the read stays bounded.

Design B: one file write per grant, one file read per tool call while the file exists.

## 6. Questions for the owner

1. **The reframe.** The docs say hook text never becomes owner words to the classifier. Answered (a) by the 2026-11-03 sign-off (item 152 a): gate the named act before the classifier, as this plan does. Option (b), keep asking in each session, was not taken.
2. **The grant form.** Answered (a) by the 2026-11-03 sign-off (item 152 a): the fixed words of section 2, catalogue in code. Option (b), free text judged by a model, lets a misread widen the act, against rule outcomes-grant-covers-named-act.
3. **The first catalogue (open).** The act to gate is a lane's `Agent` spawn, not an Edit or Write. The candidate acts that wait on this question are `self-edit` (gates nothing as written, section 2) and `merge <pr>` (superseded). Options: (a) gate the lane's `Agent` spawn first; (b) defer until a probe shows the hook gate reaches an `Agent` spawn (section 2, Agents). Recommend (a): it is the only refused act on record. Meanwhile: the build waits.
4. **Agents.** Moot under section 2: `self-edit` gates nothing as written. Options were: (a) `self-edit` reaches the target's agents, as a timed override does, and `merge` stays with the batch runner; (b) the lead session only. The `[Self-Modification]` refusal was a builder's.
5. **The gate.** Answered (a) by the 2026-11-03 sign-off (item 152 a): probe the hook gate first, the mod gate second. Option (b), the mod gate only, rested on its documented skip. The hook gate is known to load in cloud sessions.
6. **Computer sessions.** Answered (a) by the 2026-11-03 sign-off (item 152 a): Design A only, Design B if its probes fail. Option (b), both now, was not taken; (a) keeps one home.
7. **The cloud merge rule.** Superseded, pending question 3. Decision `standing-merge-grant` and the "Owner Session Message" coordinator-to-runner merge carve-out in settings.json `autoMode.allow` cover the incident. No "Merge Without Review" refusal is on record after 2026-11-01. `merge/cloud_allow.json` allows `merge * --confirm` for every PR.

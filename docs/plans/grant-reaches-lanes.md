# Plan: an owner grant typed in one session reaches the session it names

Owner, 2026-11-01 22:37 CST, in the coordinator's chat: "a grant here should allow for a grant there."

Status: plan only. Nothing is built. The owner signs off first.

## The problem

The owner types a grant in the coordinator's chat. The coordinator relays it to a lane or a batch
runner with `send_message`. The auto-mode classifier in that session refuses the act anyway. The
owner then types the grant again in each session.

Incidents, coordinator-reported, 2026-11-01:

- Batch runner 8: its merges were refused as "Merge Without Review".
- The builder of lane runner-merge-allow: refused as "[Self-Modification]".
- The coordinator's brief for item 149 b (a waiting-page answer): refused as self-modification at
  23:06 CST. That is step page-save-reaches-auto-mode (auto mode counts a page save as the owner's
  grant).

The guard layer is solved in its own session: `refuse()` in `hooks/guard_core.py` and decision
owner-override (the typed `override` word). The open problem is the classifier layer only.

The brief cites a notes line `auto-mode-refuses-page-grant`. It is not in `docs/debts/notes.md` on
main at d8037a44 (merge of PR #1009, batch 60). The step record holds the incident instead.

## 1. How the classifier decides today

Source: Claude Code docs, fetched 2026-11-02. The pages carry no version stamp. HTTP
Last-Modified is 2026-11-01. The highest version the pages cite is v2.1.311. The container runs
2.1.316. Whether the pages match 2.1.316: unknown.

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
- Hook context is "wrapped... in a system reminder" and "doesn't appear as a chat message"
  (https://code.claude.com/docs/en/hooks.md#add-context-for-claude).
- `classifierContext`: "the classifier treats the note as unverified, application-provided context.
  The note never establishes user intent" (hooks.md#annotate-a-result-for-the-auto-mode-classifier).
  Only in-process SDK callbacks "may weigh a user statement relayed in the note as user intent".
  This setup has none.

Settings: `autoMode` holds `environment`, `allow`, `soft_deny`, `hard_deny` (prose rules) and
`classifyAllShell` (https://code.claude.com/docs/en/settings-reference.md#automode). The classifier
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
  the classifier: not documented, unmeasured.

**The finding that shapes the plan.** No text a hook writes can become owner words that the
classifier sees. The docs say so twice. So no design here tries to persuade the classifier. Each
design is a transport that carries the owner's own typed words, plus a deterministic gate in the
receiving session that approves the named act before the classifier runs. Question 1 asks the owner
to confirm this reframe.

## 2. The parts every design shares

### The grant word

A hook cannot bind free prose to one act (rule outcomes-grant-covers-named-act, a grant covers the
act it names, never a variant). So the grant is a typed word with a fixed form, like `override 15m`
and `opus builders 2h`:

`grant <lane slug> <act> [<pr>] <n>[m|h]`

- The whole prompt, in any case, after leading whitespace. Any other text grants nothing, as for
  `override`.
- `<lane slug>` is the target's branch slug or `session_<id>`. One target per grant.
- `<act>` comes from a fixed catalogue in one home, a constant the gate reads (rule
  building-allow-list-is-the-constant). The act's full scope sits in the owner's words or the
  constant, never in a record a model writes. First entries, one per incident:
  - `merge <pr>`: `~/.claude/bin/merge <pr> --confirm` for that PR number only.
  - `self-edit`: an Edit or Write in the target's own worktree, to `hooks/`, `settings.json`,
    `lint/` or `.claude/`. Never a path outside that worktree, never `state/`.
- A waiting-page answer is not an act of its own. The page offers the owner a grant line with one
  of these acts (section 4).
- The length is required. The clock is the server time of the owner's event, never the target's.
- `grant off <lane slug>` ends it.

### The gate

The gate runs in the receiving session, before the classifier. It approves only a call that matches
the act in the catalogue exactly. Anything else falls through to the classifier as today. Three
gates exist:

| Gate | Skips the classifier | Per session, expires | Cloud | Gold standard |
|---|---|---|---|---|
| `PreToolUse` hook returns `allow` | Unmeasured | Yes | Yes | Documented skip |
| Mod `tool.check` approves | Documented | Yes | Unknown whether mods load in cloud sessions | Documented and loads everywhere |
| Static `permissions.allow` rule | Documented | No | Yes | Scoped and expiring |

The static rule is today's tool (decision auto-mode-owner-acts, `add_repo` and `archive_session`).
It cannot scope to one session or expire, so it is the baseline only.

Build step 1 of any design is a probe: one session, a hook that returns `allow` on one act the
classifier refuses today, and the result read from the transcript's `permission_decision`. If the
hook gate does not skip the classifier, the mod gate is next, with its own cloud probe.

### Agents

The builder refusal shows a lane's agents need the grant too. A timed `override` reaches agents
(decision owner-override). The gate runs in every `PreToolUse` of the session, so it reaches agents
the same way. It reads the grant from the lead session's transcript or state, never the agent's.
Question 4 asks whether to keep that.

## 3. The designs

### Design A: server-attested pointer (cloud and the owner's computer)

Transport:

1. The owner types `grant runner-8 merge 2h` in the coordinator.
2. The coordinator's prompt hook (`hooks/local_time.py`) checks the form and prints the event
   reference as context. It writes nothing else.
3. The coordinator relays only the pointer: `send_message` with "grant event <uuid> in session
   <coordinator id>".
4. The target calls `get_event` on that pointer. Its result lands in the target's transcript as a
   tool result, written by the harness, not by the model.
5. The gate reads that tool result from the transcript. It approves the act only when the event:
   - is a user event whose content is a plain string, not a tool result;
   - carries `client_platform` (measured: the owner's typed "b" at 22:43 CST had
     `"client_platform": "desktop_app"`; relayed messages arrive as `ReadNotifications` tool
     results with `"origin": "mcp_send_message"`);
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

What a mistaken relay can do: anything a model can write. Any session can push to the roadmap
branch. `ArtifactData` writes "as the person", so the page cannot tell the owner's save from a
model's. No guard refuses a model's write to `answers/<id>` (`hooks/call_judge.py` judges item
writes only). The answer record has no viewer field (`skills/waiting-page/page.html`). An HMAC key
in the cloud environment's secrets is readable with `env`, so signing proves nothing either.

So Design C carries model text, which is the problem we have today. It is rejected. It stays as
the comparison: a store is not owner evidence unless the owner's own client writes it.

### Cover

| Session pair | Design A | Design B |
|---|---|---|
| Cloud coordinator to cloud lane | Measured readable | No |
| Computer coordinator to computer lane, same machine | Unmeasured | Yes |
| Cloud to computer, or computer to cloud | Unmeasured | No |

Recommendation: Design A as the one design, with Design B only if the computer probes of Design A
fail.

## 4. Which design also serves page-save-reaches-auto-mode

Design A. A page save is not owner-attested today (Design C). So the page does not carry the
grant. It offers the grant line instead: an item whose answer grants an act shows its
`grant <lane slug> <act> [<pr>] <n>[m|h]` line, which the owner taps to copy and sends in the coordinator's
chat. That send is an owner event, and Design A carries it.

One home holds both: the grant word, its catalogue and the gate. Step page-save-reaches-auto-mode
then needs only the page's copy line. This matches the style rule that offers an override line for
the owner to accept.

## 5. Costs

Design A, per grant: one prompt-hook parse in the hook already running, one `send_message`, one
`get_event`. Per tool call in the target: one transcript scan inside the guard hook already running,
only while a grant pointer is in the transcript. No new process, timer or file (rule
outcomes-mechanize-rules). A test proves the cost.

Design B: one file write per grant, one file read per tool call while the file exists.

## 6. Questions for the owner

1. **The reframe.** The docs say hook text never becomes owner words to the classifier. Options:
   (a) gate the named act before the classifier, as this plan does; (b) keep asking in each
   session. Recommend (a). Meanwhile: nothing is built.
2. **The grant form.** Options: (a) the fixed word `grant <lane> <act> [<pr>] <n>[m|h]`, catalogue in code;
   (b) free text, judged by a model. Recommend (a): (b) lets a misread widen the act, against rule
   outcomes-grant-covers-named-act.
3. **The first catalogue.** Options: (a) `merge <pr>` and `self-edit`, one per incident; (b)
   `merge <pr>` only, the rest after a probe. Recommend (a).
4. **Agents.** Options: (a) the grant reaches the target's agents, as a timed override does; (b) the
   lead session only. Recommend (a): the `[Self-Modification]` refusal was a builder's.
5. **The gate.** Options: (a) probe the hook gate first, the mod gate second; (b) the mod gate only,
   since its skip is documented. Recommend (a): the hook gate is known to load in cloud sessions.
6. **Computer sessions.** Options: (a) Design A only, Design B if its probes fail; (b) both now.
   Recommend (a): one home.

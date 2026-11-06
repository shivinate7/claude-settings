# Messages to and from sessions, in a form any harness can carry

Kind: build
Plan: docs/decisions/session-messages.md#build-in-work-order (all)

Status: draft. Q1 to Q3 and page item 153 are answered; Q4 (a timed check-in) is open.

## Ruling

Owner asks ask-mw5b3m9hl0 (2026-11-06 12:27 CST) and ask-mw5a0ekdlv (11:56 CST). Roadmap steps
session-messaging-plan and peer-message-turn-cap.

## The 10-message stop on the Mac

Read from the Claude Code 2.1.319 binary (`/opt/claude-code/bin/claude`, `strings | grep`), 2026-11-06:

- Desktop cap. A session that sends to Claude Desktop sessions counts its sends since the owner last
  typed in it. Send 11 is refused: "Not delivered: this session has already messaged Claude Desktop
  sessions 10 times since your user last typed here ... Paused until your user's next message in this
  session." The limit is the built-in constant `maxSelfHops` (10). No setting or flag changes it.
- Peer guard. Every peer message carries a hop chain. A message is dropped as `hop-loop` when the
  chain already holds the receiver 10 times. Only a turn the owner types resets the chain. These limits
  come from the server flag `tengu_harbor_kite_limits` (range 3 to 32). It is not a settings.json key.
- Peer guard budgets: 30 messages per sender, refilled at 0.5 per second; the same text within 30 s
  is dropped; chain length 28; 50 queued messages per session.
- Our code caps nothing. A search of main 7975f6d8 found no cap (triage 12:12 CST).

Unmeasured: whether the Mac build has the same values; whether a scheduled-task turn resets the chain.

## Mechanisms today

| Mechanism | Harness | Direction | Wakes an idle session | Limit | Failure seen |
|---|---|---|---|---|---|
| `send_message` | cloud | session to session | yes | 64 KiB; peer guard | a failed send counts as not sent: `is_error` true, or toolUseResult `success` false for the local one (both measured 2026-11-06 13:04 CST, Claude Code 2.1.319) |
| `SendMessage` | local, agents | session to session | yes | peer guard; desktop cap | judged by hooks/sendmessage_state.py, which can refuse news to a busy peer |
| Page wake comment | all | owner to session | yes, every watcher | 4096 bytes per comment; a full thread gives no wake | fixed by PR #1301 (a full wake thread starts a new one), an open draft read on GitHub 2026-11-06 12:40 CST |
| ArtifactData answers | all | owner and session | no, read at turn start | none known | none |
| `send_later`, scheduled tasks | cloud | to self or one session | yes, after the running turn | 1-minute steps | missing from `list_sessions` |
| Chat | all | owner and session | yes | owner present only | none |

## Design

- One convention, plain text, so any harness can carry it. First line of a message:
  `Msg <id> from <role> to <role> kind request|inform|reply re <id or -> try <n>`.
  Id: `msg-` plus the page's `askId` stamp form (page.html `askId`). Role: all of the target's tags, in
  the forms of skills/project-ops/templates/operating-model.md (`cs-repo:<owner>/<name>` plus `cs-build:<tier>`
  or `cs-step:<step id>`), or `owner`.
- A resend keeps the request id and raises `try` by one, so the peer guard's 30 s same-text check does not drop it,
  and the receiver acts on the id once.
- The reply is the ack. An `inform` needs no reply. No separate ack message, because each message
  spends the peer guard and the desktop cap.
- Fit the caps: one request and one reply per exchange. A session that needs more than 10 `SendMessage`
  sends to sessions on the same computer before the owner types routes the rest through its parent or a
  record, never through a peer loop. Cloud `send_message` is not counted (section on item 153). Never use
  a scheduled task to reset the chain: that bypasses the peer guard.
- A send whose result is an error counts as not sent (`failed_tool_use_ids` in `lint/_transcript.py`).
- A message never carries a grant (decision relayed-grant-read-from-page).
- Homes: this record; the convention and adapters in skill `waiting-page` beside the page's own
  routing; transcript reads in `lint/_transcript.py`. No new hook until an incident names one
  (`building-guard-needs-incident`).

## Reach between the cloud and the owner's computer (page item 153)

Measured 2026-11-06 13:17 CST, Claude Code 2.1.319, this lane's own transcript: 7 cloud `send_message`
deliveries arrived as `origin.kind` `task-notification` with no hop chain. The peer guard reads only
`peer` turns with no sender task id. So the 10-hop cap does not apply between cloud sessions. It applies
to `SendMessage` between sessions on one computer. Cloud to the owner's computer by `send_message` is
refused with `elevated_session_untrusted_device` (PR #1051, plan for local-session reach).

Read from the binary, unmeasured live: an artifact republish wakes each session that watches it, and
that wake is not a `peer` turn. A plain comment or an `ArtifactData` write wakes nothing. Whether a
desktop session's watch wakes it is unmeasured.

Ruling: mailbox artifact (owner, page item 153, pick a, 2026-11-06 13:21 CST, relayed by triage).
One private mailbox artifact per receiver. A message is one `ArtifactData` doc; the sender republishes
the receiver's mailbox to wake it; the receiver reads unanswered mail at each wake and turn start. Cost
per send: one write and one publish. No process, no timer. Not picked: a git mailbox, a local relay
program, keeping peer messages as they are.

Test before any build (12 messages, cloud to Mac):

1. A cloud session publishes a private artifact, the mailbox, and gives its URL.
2. A desktop session on the Mac watches it with `ArtifactComments`, then ends its turn.
3. The cloud session writes `mail/<n>` with `ArtifactData`, then republishes the mailbox. It waits for
   the Mac session to write `reply/<n>`, then sends the next. It does this 12 times.
4. The Mac session counts its wakes and reads `origin.kind` on each wake in its transcript.

Pass: 12 wakes, no `peer` stamp, no `[peer-guard]` line. A fail falls back to the next pick the owner
makes, not to a build.

## Build in work order

1. Measure, no code: 11 round trips in cloud and on the Mac, with replies on; does a `send_later` turn
   reset the chain; does UserPromptSubmit fire on a peer turn. Check: each result in this record with
   its version and time.
2. Write the convention and the cloud and local adapters into the skill. Check: a two-session trial of
   20 messages, none lost, none acted on twice.

## Owner choices

- Q1, ask Anthropic for a setting that lifts the desktop cap: owner answer b, live with the limit only
  (page item 281, relayed by triage 2026-11-06 13:13 CST). The owner also asked whether the limit can be set. It
  cannot: the desktop count reads a fixed constant, and both flag-override hooks in the public build return nothing
  (binary 2.1.319, read 2026-11-06 13:14 CST: `getEnvironmentOverrides(){return null}`, `readConfigOverrides(){return}`).
- Q2, how a lost message is noticed: a cloud session that waits on a reply sets one `send_later` check-in,
  the same shape as rule `git-ci-wait-checks-in`; a local session checks at its next turn start.
  Coordinator pick, 2026-11-06 12:48 CST; it can be undone. Cost: one one-shot scheduled task per waiting
  request; it starts no process and writes no file. Open: rule `outcomes-mechanize-rules` bars tracking on
  a timer, and rule `git-ci-wait-checks-in` allows a timed check-in. The owner rules which governs.
- Q3, scope: the debt fix (done, commit 7059961a) and build steps 1 and 2 only. A parser for the message format was dropped 2026-11-06 13:15 CST: with no new hook, nothing would call it (rule building-land-design-or-abandon). Coordinator pick, 2026-11-06 12:48 CST; it can be undone.

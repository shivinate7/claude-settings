# Messages to and from sessions, in a form any harness can carry

Kind: build
Plan: docs/decisions/session-messages.md#build-in-work-order (all)

Status: draft. Q1 to Q3 are answered. Page item 153 (how cloud sessions reach the owner's computer) is folded in and open.

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
| `send_message` | cloud | session to session | yes | 64 KiB; peer guard | a failed send counts as not sent: `is_error` true, or toolUseResult `success` false for the local one |
| `SendMessage` | local, agents | session to session | yes | peer guard; desktop cap | judged by hooks/sendmessage_state.py, which can refuse news to a busy peer |
| Page wake comment | all | owner to session | yes, every watcher | 4096 bytes per comment; a full thread gives no wake | fixed by PR #1301 (a full wake thread starts a new one) |
| ArtifactData answers | all | owner and session | no, read at turn start | none known | none |
| `send_later`, scheduled tasks | cloud | to self or one session | yes, after the running turn | 1-minute steps | missing from `list_sessions` |
| Chat | all | owner and session | yes | owner present only | none |

## Design

- One convention, plain text, so any harness can carry it. First line of a message:
  `Msg <id> from <role> to <role> kind request|inform|reply re <id or -> try <n>`.
  Id: `msg-` plus the page's `askId` stamp form (page.html `askId`). Role: `cs-repo` plus
  `cs-build:<tier>` or `cs-step:<slug>`, or `owner`.
- A resend keeps the request id and raises `try` by one, so the peer guard's 30 s same-text check does not drop it,
  and the receiver acts on the id once.
- The reply is the ack. An `inform` needs no reply. No separate ack message, because each message
  spends the peer guard and the desktop cap.
- Fit the caps: one request and one reply per exchange. A session that needs more than 10 sends before
  the owner types routes the rest through its parent or a record, never through a peer loop. A
  scheduled-task "doorbell" to reset the chain is a bypass of the loop guard and is not used.
- A send whose result is an error counts as not sent (`failed_tool_use_ids` in `lint/_transcript.py`).
- A message never carries a grant (decision relayed-grant-read-from-page).
- Homes: this record; the convention and adapters in skill `waiting-page` beside the page's own
  routing; transcript reads in `lint/_transcript.py`. No new hook until an incident names one
  (`building-guard-needs-incident`).

## Build in work order

1. Measure, no code: 11 round trips in cloud and on the Mac, with replies on; does a `send_later` turn
   reset the chain; does UserPromptSubmit fire on a peer turn. Check: each result in this record with
   its version and time.
2. Write the convention and the cloud and local adapters into the skill. Check: a two-session trial of
   20 messages, none lost, none acted on twice.

## Owner choices

- Q1, ask Anthropic for a setting that lifts the desktop cap: owner answer b, live with the limit only
  (page item 281, relayed by triage 2026-11-06 13:13 CST). The owner also asked whether the limit can be set. It
  cannot: the desktop count reads a fixed constant, and both flag-override hooks in the public build return null
  (binary 2.1.319, `getEnvironmentOverrides`, `readConfigOverrides`).
- Q2, how a lost message is noticed: a session that waits on a reply sets one `send_later` check-in,
  the same shape as rule `git-ci-wait-checks-in`. Coordinator pick, 2026-11-06 12:48 CST; it can be undone.
- Q3, scope: the debt fix (done, commit 7059961a) and build steps 1 and 2 only. A parser for the message format was dropped 2026-11-06 13:15 CST: with no new hook, nothing would call it (rule building-land-design-or-abandon). Coordinator pick, 2026-11-06 12:48 CST; it can be undone.

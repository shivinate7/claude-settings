# Messages to and from sessions, in a form any harness can carry

Kind: build
Plan: docs/decisions/session-messages.md#build-in-work-order (all)

Status: draft. Q1 to Q3 and page item 153 are answered; Q4 (a timed check-in) is open with the owner.

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
| `send_message` | cloud | session to session | yes | 64 KiB; no peer guard (measured 2026-11-06 13:17 CST) | a failed send counts as not sent: `is_error` true, or toolUseResult `success` false for the local one (both measured 2026-11-06 13:04 CST, Claude Code 2.1.319) |
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
- Fit the caps: one request and one reply per exchange. The desktop cap counts `SendMessage` sends to
  sessions on the same computer since the owner last typed. Past 10 such sends, a session routes the rest
  through its parent or a record, never through a peer loop. Cloud `send_message` is not counted (section on item 153). Never use
  a scheduled task to reset the chain: that bypasses the peer guard.
- A send whose result is an error counts as not sent (`failed_tool_use_ids` in `lint/_transcript.py`).
- A message never carries a grant (decision relayed-grant-read-from-page).
- Homes: this record; the convention and adapters in skill `waiting-page` beside the page's own
  routing; transcript reads in `lint/_transcript.py`; the mailbox in `hooks/mail.py` (called from
  `hooks/local_time.py`) and `bin/mail`.

## Reach between the cloud and the owner's computer (page item 153)

Measured 2026-11-06 13:17 CST, Claude Code 2.1.319, this lane's own transcript: the turns that carried
cloud `send_message` deliveries (queued remote notifications) all had `origin.kind` `task-notification`
and no hop chain. The only `peer` turns were subagent hand-backs, which carry a sender task id. The peer
guard reads only `peer` turns with no sender task id. So the 10-hop cap does not apply between cloud
sessions. Read from the Linux binary 2.1.319, unmeasured on the Mac: it applies to `SendMessage` between
sessions on one computer. Cloud to the owner's computer by `send_message` was refused with
`elevated_session_untrusted_device` (PR #1051, plan for local-session reach; decision auto-mode-owner-acts).

Read from the binary, unmeasured live: an artifact republish wakes each session that watches it, and
that wake is not a `peer` turn. A plain comment or an `ArtifactData` write wakes nothing. The Mac test
below covers desktop sessions.

Mac test (task 294), 2026-11-06 13:57 CST, in the owner's Mac session: the Mac uses another Claude
account, so it cannot read a cloud account's artifact. So an artifact mailbox cannot reach the Mac.
Desktop sessions have no `ArtifactComments` tool. An artifact watch wakes only cloud sessions.

Ruling: git mailbox, read at turn start (owner, page item 153, pick a, 2026-11-06 15:24 CST). Cloud to
cloud keeps `send_message`. The mailbox serves a sender or receiver on the owner's computers.
Later additions, not built: a Mac doorbell (option B) and a local relay (option C). Owner note: "i think
B and C can still work too though probably."
Store: open with the owner (MAILBOX_REPO).

Design:

- Format and path. One file per message, `mail/<addr>/<id>.md`. Line 1: `Msg <id> from <tags> to <tags>
  kind request|inform|reply re <id or -> try <n>`. Line 2: `Reply-to: <addr>`. The body follows.
  Addresses: `cloud/<session_id>`; `pc/<host-slug>/<owner>-<repo>` for first contact with a local
  session; `pc/<host-slug>/<owner>-<repo>/<session_id>` once the id is known from a Reply-to. A hook
  cannot read session tags (`hooks/session_start.sh`). So the address uses what the receiver's hook can
  compute: session id and cwd from the payload, `CLAUDE_CODE_REMOTE_SESSION_ID` in cloud, hostname, and
  the repo slug from `.git/config`, found by walking up.
- Send. `bin/mail send`, with `bin/mail.cmd` beside it, as `bin/verdict.cmd` is. It uses a bare cache
  clone, `~/.claude/mail.git`, and plumbing only (hash-object, mktree, commit-tree, push to
  refs/heads/mail). It never uses a working tree. Push race: file names are unique. On a
  non-fast-forward push, it fetches again, rebuilds on the new tip, and retries at most 5 times. Then it
  prints "not sent" and exits 1.
- Turn-start read. Module `hooks/mail.py`, called from `hooks/local_time.py` `main` (UserPromptSubmit).
  It starts no process of its own. It runs `git ls-remote <repo> refs/heads/mail` (3 s bound,
  GIT_TERMINAL_PROMPT=0) and compares the ref with the cache ref. Only when the ref moved does it fetch,
  run `ls-tree mail/<own addrs>/`, and `cat-file --batch`. Unread = a file still under `mail/<addr>/`.
  It keeps no log. It prints one line per open message (id, from, kind, age) and points to
  `mail read <id>`. A failure prints "mail unknown: <reason>", never "no mail". Cost per turn: one git
  start and one network call when the ref is unchanged. When it moved, at most four git starts. Files
  are written only in the cache clone, and only on a move. Test: a process-start stand-in and a
  files-written snapshot, as in `hooks/test_daily_note.py`.
- Take and reply. `mail take <id>` makes one commit that moves the file to `done/<addr>/<id>.md`, with
  `Taken-by: <addr> <time>`. A session acts only after that push succeeds. In a take race, the loser
  finds the path gone, prints "taken by another", and does not act. A request gets a reply file, sent to
  its Reply-to, with `re <id>`. An inform closes by the take alone.
- Failure classes: push race (retry); offline Mac (mail waits; "mail unknown"); stale clone (`ls-remote`
  each turn); auth on the Mac ("mail unknown: auth", no prompt); dead session (exact-address mail stays;
  repo-address mail goes to the next session in that repo; age shown); a turn with no UserPromptSubmit
  (the skill says to run `mail read` on any peer or task wake); `done/` grows (a note).
- Risks: how `janitor/sweep.py` treats a `mail` branch that never merges is unknown. The
  UserPromptSubmit time budget is shared with `local_time`.

## Build in work order

1. Rewrite the record and skill text for this ruling. Add the GLOSSARY row "mailbox". Never "inbox":
   the owner feedback inbox uses that word.
2. Measure: does UserPromptSubmit fire on task-notification and peer turns, cloud and Mac? Can a cloud
   session push the mail ref through the proxy? Does `ls-remote` work with Mac and Windows auth? Does
   the hostname match `list_computer_folders` `computer_name`? Can a Mac session call cloud
   `send_message`?
   Already measured: cloud UserPromptSubmit fires on task-notification turns. This lane's session,
   Claude Code 2.1.319, 2026-11-06 15:31 CST: the local_time hook line prints on each notification turn.
   Cloud: a lane session pushes branches to claude-settings through the proxy (same session).
3. Test-author: red cases against a `file://` bare `MAILBOX_REPO`: round trip, push race, take race,
   inform close, offline, cost counts.
4. Builder: `hooks/mail.py`, `bin/mail` and `bin/mail.cmd`, the `hooks/local_time.py` call, and the
   `settings.json` env default.
5. Skill section rewrite. Check: a two-session trial of 20 messages, cloud to Mac, none lost, none acted
   on twice.

## Owner choices

- Q1, ask Anthropic for a setting that lifts the desktop cap: owner answer b, live with the limit only
  (page item 281, relayed by triage 2026-11-06 13:13 CST). The owner also asked whether the limit can be set. It
  cannot: the desktop count reads a fixed constant, and both flag-override hooks in the public build return nothing
  (binary 2.1.319, read 2026-11-06 13:14 CST: `getEnvironmentOverrides(){return null}`, `readConfigOverrides(){return}`).
- Q2, how a lost message is noticed: a session that waits on a reply checks for it. Coordinator pick,
  2026-11-06 12:48 CST; it can be undone. How it checks waits on Q4. Until then it checks at its next
  turn start.
- Q4, open with the owner (sent through triage 2026-11-06 13:22 CST): may a cloud session that waits on a
  reply set one `send_later` check-in? Rule `outcomes-mechanize-rules` bars tracking on a timer, and rule
  `git-ci-wait-checks-in` allows a timed check-in. Cost: one one-shot scheduled task per waiting request;
  it starts no process and writes no file. Recommended: allow it.
- Q3, scope: the debt fix (done, commit 7059961a) and the git-mailbox build steps 1 to 5. The parser for the message format was dropped 2026-11-06 13:15 CST and stays dropped (rule building-land-design-or-abandon). Coordinator pick, 2026-11-06 12:48 CST; it can be undone.

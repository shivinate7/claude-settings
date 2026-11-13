# Messages to and from sessions, in a form any harness can carry

Kind: build
Plan: docs/decisions/session-messages.md#build-in-work-order (all)

Status: draft until build step 2 and the 20-message trial run. Q1 to Q4, page item 153 (the mailbox ruling) and page item 308 (the store) are answered.
The mailbox build is on main: PR #1371 merged 2026-11-08 inside batch-65g (PR #2236). Follow-up PR #2484 merged 2026-11-10 in batch 71.
A Windows round trip passed (request 8933ab505319 to the cloud, reply
7292c549f4ee, both taken, 11:52 CST Nov 12; record: branch roadmap, commit b21c5d3dc). Cloud works for the owner's account; ssemwal-cdc is unmeasured.
`MAILBOX_REPO` has a settings.json `env` default, set by the owner's ruling (page item 556 a, 2026-11-12 12:04 CST), not by
measurement. A session with an address reads mail at turn start. A failed read prints "mail unknown: <reason>". A session
with no address, or a store with no mail ref, prints nothing (the store case has a test; the no-address case is read from the code only). A Mac is not held: its round trip passed 1 of 1 (mail 4d31137fd16c Mac to cloud, 71c5f84d64a8 cloud to Mac, 20:30 CST Nov 12; record: branch roadmap, commit e86503c2a). `HELD_PLATFORMS` in `hooks/mail.py` is empty; a platform listed there prints nothing at turn start and `mail` exits 2 unless `MAILBOX_HOLD_OFF=1`. The refusal text names no variable. A local Linux session is not held and is unmeasured.
The 20-message trial (step 5) is still open.

## Ruling

Owner asks ask-mw5b3m9hl0 (2026-11-06 12:27 CST) and ask-mw5a0ekdlv (11:56 CST). Roadmap steps
session-messaging-plan and peer-message-turn-cap.

## One route (owner, 2026-11-10 09:33 CST)

Ruling: every message between sessions goes through the git mailbox, cloud to cloud included.
The doorbell is a background `mail wait` (owner, 2026-11-12 14:17 CST, "I'm okay with A for Q1"; section "The doorbell: mail wait"). The owner rejected a `send_message` doorbell and a trusted-device route at 14:14 CST: a cloud-only doorbell would not reach every device.
The mailbox is read at turn start, and `mail wait` wakes an idle session.
The design is device-neutral (owner, 2026-11-10 09:34 CST, "the device shouldn't matter"): local sessions are addressed `pc/<host>/<owner>-<repo>/<session id>` on any Mac or Windows computer.
Local-computer checks: measured on a Mac only; the mail round trip alone is also measured on Windows (11:52 CST Nov 12), and the other Windows checks are unmeasured.

Why:

- A `send_message` that shows "delivered" is not a read.
- It leaves no copy.
- It differs from local `SendMessage`.
- Cloud to the owner's computer is refused (`elevated_session_untrusted_device`).

Wake routes under study. All unmeasured.

- (a) Doorbell (open, see above): `mail send` also fires a short `send_message`. Works cloud to cloud. Cloud to the owner's computer is refused.
- (b) One long-lived pull request per session in shivinate7/session-mailbox. Each message is also a
  comment. The receiver subscribes with `subscribe_pr_activity` (the tool that watches PR activity).
- (c) A GitHub webhook to a session's `watch_url`. Likely blocked: the signing secret is sealed to the
  artifact service.
- Mac or Windows: no known wake route.

Home of the measurement: roadmap step `mailbox-wake-routes` (the wake-route measurement, filed by triage).

State: the code still sends cloud to cloud by `send_message` until a build lands. No build is started.
Timed check-ins: Q4, see its bullet.

## The doorbell: mail wait

Ruling: owner, 2026-11-12 14:17 CST, "I'm okay with A for Q1"; plan R57 (the mail doorbell is a background mail-wait) in plans/restart-plan.md on origin/restart-plan. Wake routes (a) `send_message` doorbell and the trusted-device route are rejected (owner, 14:14 CST); (b) and (c) are not built.
Rule: CLAUDE.md rule `outcomes-mechanize-rules` bans timers and long-lived processes. Ruling 3.15 (owner, 2026-11-11 13:22 CST; step timer-rule-reason-only) allows a waiting process whose record shows it costs less than it saves. This section is that record.

What it is. `mail wait [--interval S] [--max-seconds S]` in `bin/mail`, with the code in `hooks/mail.py`. A session starts it with `run_in_background` when its turn ends idle. It blocks until a message it has not seen is open under the session's own addresses. Then it prints one line and exits 0. The line reads `mail: new <id> from <addr> kind <kind>; untrusted subject "<first body line>"; read: <mail read command>; take: <mail take command>`. Claude Code wakes the session on the exit. This works the same on cloud, Mac and Windows. A message has no subject field, so the first body line is the subject.
How it reads. At start, one fetch and `open_messages` give the baseline of open ids. Then it runs one `git ls-remote` per interval. The mail ref moves on every send and take by any session. So a moved sha alone is not mail. Only after a move does it fetch and run `open_messages`. It wakes on an id that is not in the baseline. It writes no `listing-*.json`.
Exit codes: 0 new mail. 2 not started, printing `mail wait: not started: <reason>`. 3 ended at `--max-seconds` with no mail, printing `mail wait: ended, no mail`. A poll that fails keeps polling.
Exit 2 has these causes. Five act at once: `MAILBOX_REPO` unset, no address, a live waiter holds the lock, the lock cannot be taken, or `--interval` or `--max-seconds` is out of range. The range of `--max-seconds` is 1 to 7000. The sixth is a baseline read that failed for about 5 minutes.
Lock. `<cache>/wait-<address with / as _>.lock`, created exclusively, JSON `{pid, ppid, session, started, deadline}`. It is stale when its pid is dead, its deadline has passed, or its start time differs from the pid's. The start time is read on Linux only. Elsewhere the deadline guards against a reused pid. A stale lock is replaced. The waiter removes its lock on every exit, SIGTERM included. It exits when the lock is gone or its parent pid is dead.
Wakes with no mail. Every exit wakes the session. So the instruction (skill `waiting-page`, "Message another session") sets three limits. Start it only when idle, with `MAILBOX_REPO` set. Pass `timeout` 7200000, because the Bash background default is 30 minutes and the cap is 2 hours. Never restart after exit 2, and restart at most once after exit 3. The default limit is 6600 s, under that cap.
The subject is another session's text. The wake line marks it untrusted, strips control and direction characters, and cuts it to 160 characters. That keeps it on one line. It does not stop a subject that holds instructions, so a session reads it as data.
Rule text. Ruling 3.15 is the owner's grant for this waiter. The `CLAUDE.md` rule still reads "starts no new long-lived process" until step timer-rule-reason-only merges.

Cost, measured. Interval 30 s, chosen from a measured `ls-remote`: 316 to 404 ms over 6 runs (not pinned: measured once on Nov 12, and no test repeats it). Checked Nov 12 on main 2deb827ad: that run was from this cloud session, against the claude-settings origin, through the proxy. The store was not reachable from this session. So the Nov 6 store figure of 391 to 608 ms over 5 runs is cited and not re-run (not pinned). A simulated hour in `hooks/test_mail_wait.py` makes 120 `ls-remote` reads. That is about 40 s of git time an hour per idle session (unmeasured: derived from the interval and the measured read time). A wake is at most 30 s late.

Doorbell cost: processes 1; interval 30 s; reads per hour 120; files written 1 (lock)

Cost, beyond that line. In `hooks/test_mail_wait.py`, each read is one short git process (`ls-remote`). In `hooks/test_mail_wait.py`, a moved sha adds one `fetch` and one `grep`, and writes only the existing cache. In the same test file, a wake adds one `git show` for the subject and one `git log` for the age lookup. The `git show` is the read `mail read` uses, which the owner's fence allows. The waiter keeps no log and starts no second long-lived process. With the default limit, an idle session with no mail wakes once per 110 min, about 0.55 a hour (unmeasured: derived from the limit). Test: hooks/test_mail_wait.py, case "the decision states the measured doorbell cost". It reads the cost line and compares each number to a simulated hour.

Saves: an idle session otherwise never reads mail until a person types. A message to any session now wakes it, with no device-specific route.

Known gaps, kept as notes (round 2 review). Two starts in the same millisecond against one stale lock can end one waiter at once with one spurious wake. They never leave two waiters for long. A waiter killed between its temp write and the link leaves a `wait-*.lock.<pid>.tmp` file. The baseline retry ignores the lock deadline when `--max-seconds` is under 300. `--interval` has no ceiling. The wake line does not strip left-to-right marks or zero-width characters.

Windows scope. The Windows-safe timeout kills the child tree and never calls `communicate()` after the kill. Only the wait uses it. Turn start, send, take and read keep `git()` as on main, because the owner's fence leaves the send path unchanged. So the turn-start hang in debt mail-windows-timeout-hang stays open.

Wake, cloud: checked Nov 12 on main bcbeaa26a, 15:46 CST, in the retrospective session. A 5 s command started with `run_in_background` exited 0 and woke that cloud session after its turn had ended. Proven 1 of 1, in the main checkout shell. A long command of this cloud lane (the lane lint) also woke it after the shell moved it to the background.
Wake, Windows: checked Nov 12, 15:56 CST, by the owner's retest on his own machine. A 60 s background sleep woke his local session from idle, and it replied WOKE. Proven 1 of 1. An earlier run at 15:51 CST does not count: a Stop hook re-prompted that turn before the command exited.
Unmeasured: the wake on a Mac, and the Windows git timeout branch (tested by injection only). The shell refused `run_in_background` in this lane's worktree.

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

- One convention, plain text, so any harness can carry it. First line of a mailbox message:
  `Msg <id> from <addr> to <addr> kind request|inform|reply re <id or -> try <n>`. The addresses are set
  out under Design. Id: 12 lowercase hex characters (`secrets.token_hex(6)` in `hooks/mail.py`).
  If a doorbell is built (open), its cloud `send_message` target is picked by all of its tags, in the forms of
  skills/project-ops/templates/operating-model.md (`cs-repo:<owner>/<name>` plus `cs-build:<tier>` or
  `cs-step:<step id>`).
- `try` counts push attempts inside one `mail send`. A push race keeps the id and raises `try` by one.
  A new `mail send` is a new message with a new id. A `SendMessage` resend keeps the request id and raises
  `try` by one, so the peer guard's 30 s same-text check does not drop it. The mailbox does not pass
  through that check. `mail take` moves a message once. A second take is refused, so the receiver acts on
  an id once.
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
and no hop chain. The only `peer` turns were agent hand-backs, which carry a sender task id. The peer
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

Ruling: every message goes through the git mailbox, read at turn start (owner, page item 153, pick a,
2026-11-06 15:24 CST; cloud to cloud added 2026-11-10 09:33 CST, see One route above).
Not built, doorbell open: a doorbell for a local computer (option B) and a local relay (option C). Owner note: "i think
B and C can still work too though probably."
Store: answered. Page item 308 (the store), owner pick a, relayed by triage 2026-11-06: a private repo,
shivinate7/session-mailbox. The owner allowed Cloudflare if it is faster. Lane verdict: git.
- The per-turn check is one `ls-remote`: 391 to 608 ms over 5 runs from a cloud session.
- A Worker would save about 0.3 s. It adds a server, a secret on every machine and a network allowlist.
- Cloudflare stays a later swap behind `MAILBOX_REPO`.
- Page item 312 (the repo was created): a cloud session reached it through the proxy and ran send, read,
  take, and a refused second take (2026-11-06 15:58 CST).

Design:

- Format and path. One file per message, `mail/<addr>/<id>.md`. Line 1: `Msg <id> from <addr> to <addr>
  kind request|inform|reply re <id or -> try <n>`. Line 2: `Reply-to: <addr>`. A blank line, then the body.
  Addresses:
  - Cloud session: `cloud/<session_id>`, from `CLAUDE_CODE_REMOTE_SESSION_ID`. The env value `cse_<id>`
    becomes `session_<id>`, the form `list_sessions` and `send_message` use.
  - Local session: two folders. `pc/<host-slug>/<owner>-<repo>/<session id>` and the repo folder
    `pc/<host-slug>/<owner>-<repo>`. The host slug is the lower-case hostname, with each run of other
    characters as `-`. The repo slug is `<owner>-<repo>` from the origin URL in `.git/config`, found by
    walking up.
  A hook cannot read session tags (`hooks/session_start.sh`). So an address uses only what the hook gets
  from the payload and the environment.
- Send. `mail send --to <addr> --kind request|inform|reply [--re <id>] --body-file <file|->`, in
  `bin/mail`, with `bin/mail.cmd` beside it. The cache is a bare clone: `MAILBOX_CACHE`, else
  `~/.claude/mail.git`. It uses plumbing only: read-tree into a temporary index, hash-object,
  update-index, write-tree, commit-tree, then push to refs/heads/mail. It never uses a working tree.
  Each git call encodes its stdin as UTF-8 bytes, so Windows adds no CR to an index path. Before the push, it reads the new tree
  back: each added path must hold the blob of its text. A git call that prints "Ignoring path" on stderr
  is an error, because git then exits 0 and skips the path. Either failure prints "not sent".
  Push race: file names are unique. On a non-fast-forward push, it syncs and rebuilds on the new tip. It
  makes six tries in all: the first push and at most five retries. Any other refusal, such as a hook or
  ACL refusal, is not retried. On failure it prints "not sent: <reason>" and exits 1. On success it
  prints `sent <id> to <addr>` and exits 0.
- Turn-start read. Module `hooks/mail.py`, called from `hooks/local_time.py` `main` on UserPromptSubmit
  only. It runs `git ls-remote <store> refs/heads/mail` and compares the sha with the saved listing. Only
  when the sha moved does it fetch, then run `git grep` for `^Msg ` under the session's folders and
  `git log` for the ages. Unread = a file still under `mail/<addr>/`. It keeps no log. On a move it
  writes one listing file to the cache, `listing-<hash>.json`. It prints one line per open message: id,
  from, kind, re, age, and the `mail read --addr` and `mail take --addr` commands. The four git bounds sum
  to 10 s: ls-remote 3 s, fetch 4 s, grep 2 s, log 1 s. A timeout prints `mail unknown: timeout`. A failed
  age lookup prints "age unknown" and keeps the line. No prompt can open: GIT_TERMINAL_PROMPT=0,
  GCM_INTERACTIVE=never, and ssh in BatchMode with a 3 s ConnectTimeout, unless the caller set its own
  ssh command. A failure prints "mail unknown: <reason>", never "no mail". Cost per turn: one git start
  and one network call when the sha is unchanged (not pinned). When it moved, at most four git starts. Files are
  written only in the cache, and only on a move. Test: a process-start stand-in and a files-written
  snapshot, as in `hooks/test_daily_note.py`.
- Take and reply. `mail take [--addr <addr>] <id>` makes one commit that moves the file to
  `done/<addr>/<id>.md` and appends `Taken-by: <addr> <time> <token>`. It exits 0 and prints `taken <id>`
  after the push succeeds, and a session acts only then. In a take race, the loser finds the open path
  gone and exits 1 with "taken by another". It does not act. A second take is refused the same way. A take whose read-back fails (the open file stays in the new tree, or the done file is missing) prints "mail unknown: message file missing from the commit" and exits 1. A
  request gets a reply file: `mail send --kind reply --re <id>`, sent to its Reply-to. An inform closes by
  the take alone.
- Read. `mail read` lists the open messages under the session's own folders. `mail read [--addr <addr>] <id>`
  prints one message with its body. Without `--addr`, every folder of the session is read. Exit codes
  for all `mail` commands: 0 ok; 1 not sent, not taken, or "mail unknown"; 2 bad use, `MAILBOX_REPO`
  not set, or the platform held.
- Failure classes: push race (retry); offline computer (mail waits; "mail unknown"); stale clone (`ls-remote`
  each turn); auth on a Mac or Windows PC ("mail unknown: auth", no prompt); dead session (exact-address mail stays;
  repo-address mail goes to the next session in that repo; age shown); a turn with no UserPromptSubmit
  (the skill says to run `mail read` on any peer or task wake); `done/` grows (a note).
- Risks: how `janitor/sweep.py` treats a `mail` branch that never merges is unknown. The
  UserPromptSubmit time budget is shared with `local_time`.

## Reach across GitHub accounts

- The store is the private repo shivinate7/session-mailbox. A cloud session under the owner's second
  account, ssemwal-cdc, reaches it only if that account can read and write it.
- Done by the owner. Owner's words, 2026-11-10 10:19 CST: "ssemwal-cdc long has been invited and accepted."
  The invite date is unknown.
- Unmeasured: whether a cloud session under ssemwal-cdc reaches the store through the git proxy.
  The proxy served the store only after `add_repo` for the measuring session; such a session needs the
  repo attached by that account's Claude GitHub connection. Measure with one `mail read`.
- No code change is expected.

## Build in work order

1. Rewrite the record and skill text for this ruling. Add the GLOSSARY row "mailbox". Never "inbox":
   the owner feedback inbox uses that word.
2. Measure: does UserPromptSubmit fire on task-notification and peer turns, cloud and local computers? Can a cloud
   session push the mail ref through the proxy? Does `ls-remote` work with Mac and Windows auth? Does
   the hostname match `list_computer_folders` `computer_name`? Can a local session on a Mac or Windows PC call cloud
   `send_message`?
   Already measured: cloud UserPromptSubmit fires on task-notification turns. This lane's session,
   Claude Code 2.1.319, 2026-11-06 15:31 CST: the local_time hook line prints on each notification turn.
   Cloud: a lane session pushes branches to claude-settings through the proxy (same session).
   Cloud to the private store (page item 312): send, read, take and a refused second take, through the
   proxy (2026-11-06 15:58 CST). `ls-remote` from a cloud session: 391 to 608 ms over 5 runs.
   Cloud round trip through the proxy between two agents with distinct addresses (`cloud/session_rtripa`,
   `cloud/session_rtripb`), 2026-11-09 19:34 CST: send message 2979e0b314d0 (request), read, take (exit 0),
   reply message 60884f559348, reply read and taken by the sender (exit 0), second take of 2979e0b314d0
   refused "taken by another" (exit 1). Cloud only; Mac and Windows auth still not measured.
   Not yet measured then: Mac and Windows auth for `ls-remote` (later: Windows round trip passed 2026-11-12; Mac passed 2026-11-12).
3. Test-author: red cases against a `file://` bare `MAILBOX_REPO`: round trip, push race, take race,
   inform close, offline, cost counts.
4. Builder, PR #1371 merged 2026-11-08 inside batch-65g (PR #2236): `hooks/mail.py`, `bin/mail`, `bin/mail.cmd` and the
   `hooks/local_time.py` call. The `settings.json` env default was left unset here. The owner set it by
   ruling on 2026-11-12 (page item 556 a), before the Mac measure.
5. Skill section rewrite. Check: a two-session trial of 20 messages, cloud to a local computer, on a Mac and on a Windows PC, none lost, none acted
   on twice.

## Owner choices

- Q1, ask Anthropic for a setting that lifts the desktop cap: owner answer b, live with the limit only
  (page item 281, relayed by triage 2026-11-06 13:13 CST). The owner also asked whether the limit can be set. It
  cannot: the desktop count reads a fixed constant, and both flag-override hooks in the public build return nothing
  (binary 2.1.319, read 2026-11-06 13:14 CST: `getEnvironmentOverrides(){return null}`, `readConfigOverrides(){return}`).
- Q2, how a lost message is noticed: a session that waits on a reply checks for it. Coordinator pick,
  2026-11-06 12:48 CST; it can be undone. It checks at its next turn start, and a cloud session that waits
  on a reply may set that one check-in (Q4).
- Q4, answered by the owner, 2026-11-10 09:39 CST, in his words: "ok one check in is allowed, i just don't
  think it'll be hollistic enough, but it's allowed that is enough". A cloud session that waits on a reply
  may set one `send_later` check-in for that one reply. His note: one check-in alone will not cover
  everything. The sentence in CLAUDE.md rule `outcomes-mechanize-rules` was written by sessions (commits
  f966e26e4, 7f3d2d601, 0b8296e8e); his answer is what rules it.
- Q3, scope: the debt fix (done, commit 7059961a) and the git-mailbox build steps 1 to 5. The parser for the message format was dropped 2026-11-06 13:15 CST and stays dropped (rule building-land-design-or-abandon). Coordinator pick, 2026-11-06 12:48 CST; it can be undone.

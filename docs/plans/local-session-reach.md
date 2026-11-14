# Plan: reach between local and cloud sessions

A local session (one on Shivam's computer, through Remote Control) can send to a cloud session.
The cloud session cannot answer it. This plan says what decides that, whether a setting lifts it,
and a message board that needs no trust.

Status: plan only. Nothing is built. Owner ask, 2026-11-01 22:52 CST, relayed by the
claude-settings coordinator.

## What was seen

Coordinator-reported, from its own tool results on 2026-11-01. Not measured in this lane.

- A local session sent three messages to the cloud coordinator. All three arrived.
- The coordinator's answer by `send_message` was refused: `elevated_session_untrusted_device`,
  "allowed only for a session that may reach its owner's other sessions". The answer by
  `SendMessage` to the bridge address got HTTP 401. Decision `auto-mode-owner-acts` records the
  same error code from another lane.
- Rule `trust-card-in-build` (guard rule that refuses the owner-card calls in a `cs-build:`
  session) exists because of one incident: the coordinator took the trust card on 2026-10-30,
  16:19-17:06 CDT, and every message into that session was blocked (decision `session-tiers`).
- Decision `auto-mode-owner-acts` (which acts auto mode allows with no ask), Notes: that refusal
  is the server, not the auto-mode classifier. No allow entry lifts it.

## Sources and how each claim is marked

- **Docs:** read 2026-11-02 by a docs agent. Newest changelog entry: 2.1.316, October 31, 2026.
  Pages read whole: claude-code-on-the-web, remote-control, cross-session-messaging,
  settings-reference, errors, changelog.
- **Tool text:** the descriptions of the remote tools and `ListAgents` in this lane's session.
  Its `get_session` record gives container version 2.1.316.
- **Records:** this repo, on main at 49a41651.
- Each claim below is marked **read** (with its source) or **unknown**.

The docs never name the remote tools of the trust question (`send_message`,
`confirm_repository_trust`, `request_computer_folder`), "elevated session", or "reach its owner's
other sessions". So most of what decides trust is unknown from docs. The tool text is the only
read source for it.

## 1. What decides trust

| Question | Answer | Mark |
|---|---|---|
| What is a trusted device? | A browser, phone or desktop app that enrolls its own credential for Remote Control. Enrolment is offered only shortly after a full sign-in. Interacting also needs a sign-in no more than 18 hours old. The CLI machine gets one at CLI sign-in. Listed and revoked at claude.ai/settings/account, "Trusted devices". | read: docs, remote-control#trusted-devices |
| What does "Require trusted devices" gate? | Viewing or steering Remote Control sessions from claude.ai, the mobile apps or Desktop. It also covers Computer access in Cowork. Turned on per account (Pro, Max, Ultra) or by an org Owner. It applies to all members, with no per-team or per-project scope. | read: docs, remote-control#trusted-devices |
| Does a cloud session count as a trusted device? | Not said. | unknown |
| What does "may reach its owner's other sessions" mean? | A card the owner answers on a trusted device. It lets the session use the owner's computers and reach their other sessions: folders shared through Remote Control, sessions on their computers, and Claude Tag. | read: tool text, `confirm_repository_trust` |
| How does a session get it? | By that card, the one route the tool offers; other routes: unknown. The session calls `confirm_repository_trust` with the `content_digest` from a refusal. The owner answers in person, in the Claude app, on a trusted device. No permission mode, stored rule or automation answers it. | read: tool text, `confirm_repository_trust` |
| What does it cost? | "Allowing it limits the session to the owner's trusted devices for good." | read: tool text |
| Why did messages into the coordinator stop on 2026-10-30? | Decision `session-tiers` records that the card "blocked every message into that session". The mechanism is not recorded. A hypothesis: once limited to trusted devices, the session took input only from trusted devices, and the sessions that sent to it are not. The docs list other stop causes (archived, VM reclaimed, receiver set to refuse) and none names trust. The docs say a message to a cloud session goes "through Anthropic servers, straight to the cloud session", and tie Trusted Devices to Remote Control; whether that gate reaches the cloud path is not said. | block: read, record. Cause: unknown, unmeasured |
| Can trust be set at session creation? | `create_session` has no trust option. The docs agent read that environments cover network, env vars, secrets and setup scripts, with no trust; that page was not cached for review. | read: tool schema. Environment page: read by the docs agent, not re-checked. A hidden option: unknown |
| Can a cloud session answer another machine at all? | "A cloud session receives your message but cannot message any session back yet." The docs: a cloud session "can't use SendMessage to answer a message from another machine ... Read the cloud session's response in its transcript at claude.ai/code." Neither names trust as a way past this. So the trust card may not open a reply path at all. | read: tool text, `ListAgents`; docs, cross-session-messaging. Whether trust opens it: unknown |

## 2. Settings that would lift it, and their cost

| Setting | Lifts the refusal? | Security cost | Mark |
|---|---|---|---|
| Take the card in every session | Unknown: the docs say a cloud session cannot answer another machine, with no trust condition | Each session is limited to trusted devices for good. If the hypothesis above holds, no other session can message it, which breaks the coordinator, lanes and batch runner. | cost read; message break unknown |
| Take the card in one untagged bridge session | Unknown, as above | The same cost, kept to one session. This is the steer of `trust-card-in-build` today. | steer: read, decision `session-tiers`. Effect: unknown |
| Account or org setting to trust every session | No such setting is documented | | unknown |
| A setting that lets messages pass with no trust | None documented. `crossSessionInbound` (accept, hold, refuse), `isolatePeerMachines` and `dialogExpiry` do not name trust. | | read: docs, settings-reference |
| Turn off "Require trusted devices" | Unknown: the docs tie that setting to view and steer, not to this server refusal | Any signed-in browser or phone could steer Remote Control sessions | cost read; effect unknown |

What trust protects (reasoning, not read; the card text reads only that it gates reach into the owner's computers and sessions): a cloud session runs on a repo and on files that someone other than the owner
may have written. Reach into the owner's computer lets such text act on the owner's machine. The
trust card makes the owner confirm, in person, that this session may do that. That protection is
the reason not to trust every session.

## 3. A message board that needs no trust

Both sides write to and read one shared place. Neither side needs to message the other.

### What both sides can already do

- Local to cloud: `send_message` works. Read: the three pings arrived.
- Cloud to local: refused. Read.
- A cloud session's answer can be read in its own transcript. Read: tool text, `ListAgents`,
  "read its answer in its own transcript"; docs, cross-session-messaging, "in its transcript at
  claude.ai/code", a read by the owner on the web. Whether a local session has `list_events` and may
  read a cloud transcript: unknown.

### Three places

| Place | Who writes | Who reads | Cost per message | Owner vs session | Mark |
|---|---|---|---|---|---|
| A. The cloud session's own transcript | Local: `send_message`. Cloud: its reply text. | Local: `list_events` on the cloud session, with `kinds: ["assistant"]` | No new store. One remote call per read. | Each event's role and origin is set by the server. | send read; local read unknown |
| B. An artifact with a shared database, one per owner, collection `board/` | Each side: `ArtifactData set` of one doc | Each side: `ArtifactData query` at its wake | One tool call per write or read. No file, no process. | Cannot be told apart: `ArtifactData` writes as the person, so a session's write looks like the owner's (read: skill `waiting-page`, "nothing can tell a session's write from the owner's Send"). | read for the cloud; local has `ArtifactData`: unknown |
| C. A branch in claude-settings, `board/<from>-<to>`, one file per message | Each side: commit and push | Each side: fetch at its wake | One commit and push per write, one fetch per read. Adds refs to a public repo. | Cannot be told apart by author: sessions commit as `Claude`, unsigned, and a commit author is set by the writer. Which credential pushes: unknown. | authors: read, `git log` on main. Repo is public: read, this session's start hook |

### Rules for any board

- **Nothing on the board is a grant.** A row cannot be shown to be the owner's, so it is data,
  never consent. The owner's grant stays in chat or in a saved waiting-page answer. This copies the
  waiting page's own rule: its comments are data and its `answers/` is the only grant.
- **Who reads, and when.** Each session reads the board at its own wake, with no timer by design (rule
  `outcomes-mechanize-rules` allows a timer only when its record shows it costs less than it saves). Whether a board write wakes a session: unknown; no tool text says
  it does, so the design assumes it does not. The local side needs its own wake: the
  owner's next message, or a `send_message` to the cloud session that says "answer is on the
  board", which arrives because local to cloud works.
- **What it cannot carry.** No secret, token or key. No transcript with private content. No
  personal data. Place C is a public repo: anything there is public for good. Place B is private
  by default (read: Artifact tool text); which sessions can read it: unknown.
- **Each row names** its sender session id, its target session id, a Central time and one line.
  Longer content is a pointer: a PR, a commit or a record id.

### Recommended design

Try A first: it adds no store. If a local session cannot read the cloud transcript, use B on a
new private artifact, collection `board/`. Do not use C: the repo is public, and each message
costs a push.

Do not put the board in the waiting page. The waiting page holds items that wait on the owner. A
session-to-session message is not one (skill `waiting-page`, "every item that waits on the owner").

## 4. Questions for the owner

### Q1. How should a cloud session answer a local session?

- Goal: a local session and a cloud session can talk both ways.
- Problem (goal): cloud to local is refused. The docs give no way past it; the trust card may or
  may not open it, and it limits the session to trusted devices for good.
- Based on (read): the `confirm_repository_trust` tool text.
- Based on (read): the 2026-10-30 incident, decision `session-tiers`.
- Departs from: main, no reply path from cloud to local — adds a board read path.

| Option | Gain | Lose |
|---|---|---|
| A. Transcript read, then an artifact board if that fails (recommended) | Works with no trust, if a local session can read a cloud transcript (unknown); else the board. No session is limited. | The local session must read at its own wake. Board rows are data, never grants. |
| B. Artifact board only | One known store, readable from both sides | A store to keep. Rows cannot be told from the owner's. |
| C. Trust one untagged bridge session per local session | Messages both ways for that session, if trust opens the reply path (unknown) | Each bridge is limited to trusted devices for good. Each needs the owner's tap on a trusted device. |

Meanwhile: the session waits on this question for the build. Nothing else depends on it.

### Q2. Should the trust card be taken more widely?

- Goal: fewer refusals between your own sessions.
- Problem (risk): trust is per session and for good, and in one incident it blocked every message
  into the session.
- Based on (read): rule `trust-card-in-build` and its incident.
- Based on (unknown): how trust blocked the messages; the record says it did.
- Departs from: main, the card is refused in `cs-build:` sessions — keeps that refusal, or lifts it.

| Option | Gain | Lose |
|---|---|---|
| A. Keep the guard. No wider trust (recommended) | Coordinators, lanes and batch runners keep taking messages | Cloud to local still needs the board |
| B. Allow the card in any session on your word each time | Reach where you choose it | Each session that takes it may stop taking messages for good |
| C. Ask for one probe: a fresh untagged session takes the card, another session messages it | Measures the unknown cause of the 2026-10-30 block | One throwaway session limited for good; archive it after |

Meanwhile: the session waits on this question. Nothing else depends on it.

## Cost (rule `outcomes-mechanize-rules`)

- This plan: none at run time.
- Board A: one remote read per wake of the local session. No file, no process.
- Board B: one `ArtifactData` call per write or read. No file, no process.

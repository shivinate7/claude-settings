# The trust error: docs silent, owner's plan unanswered

## The ruling

Written 2026-11-11 22:52 CST. This record files no owner ruling. It records that the docs are silent on the trust error, what was measured, and what is still unknown. Each claim is marked read (with its source) or unknown.

Decision: the trust error is recorded as docs silent. A claim that a permission rule lifts it stays an inference until a source says so.

### What the error is

- The trust error is refusal code `elevated_session_untrusted_device`. Its text: "allowed only for a session that may reach its owner's other sessions". Read: tool text, coordinator-reported on 2026-11-01 (local-session reach plan, section "What was seen").
- The trust card is the one route the tool offers. Other routes: unknown. The session calls `confirm_repository_trust` with the digest from the refusal. The owner answers in person, on a trusted device, in the Claude app. Read: tool text (plan, section 1 "What decides trust").
- The card's text says no permission mode, stored rule or automation answers it. Read: tool text, `confirm_repository_trust`.
- The refusal comes from the server, not from the auto-mode classifier. No allow entry can lift it. Read: decision `auto-mode-owner-acts` (the record of acts auto mode allows with no ask), Notes. That is a repo note, not a docs read.

### Docs silent

- A docs agent read six pages in full on 2026-11-02: claude-code-on-the-web, remote-control, cross-session-messaging, settings-reference, errors, changelog. The newest changelog entry is 2.1.316, dated October 31, 2026. Read: plan, section "Sources and how each claim is marked".
- The docs never name `send_message`, `confirm_repository_trust`, `request_computer_folder`, "elevated session", or "reach its owner's other sessions". Read: the same docs read.
- The broad claim, that no permission rule can lift the refusal, is an inference. It was reported as an answer. Audit row F188 says so. The row is in the owner-feedback audit, draft pull request 1008, pinned copy at commit 6827a12e0. Status: unknown.

### What was measured

Coordinator-reported, from its own tool results on 2026-11-01. The plan's lane did not measure it.

- Three messages from a local session reached the cloud coordinator. All three arrived.
- The coordinator's reply by `send_message` was refused with the trust error.
- The same reply sent by `SendMessage` to the bridge address got HTTP 401.
- A cloud session "cannot message any session back yet". Read: tool text (`ListAgents`). The docs say a cloud session cannot use `SendMessage` to answer a message from another machine. Read: docs, cross-session-messaging.

Not measured:

- The cause of the block from 2026-10-30 16:19 CDT to 17:06 CDT. The coordinator took the trust card, and every message into that session was blocked. Decision `session-tiers` records the block, not the mechanism. The plan's unverified hypothesis: a session limited to trusted devices takes input only from trusted devices. Cause: unknown, unmeasured.
- Whether the trust card opens a reply path from the cloud. Unknown. Plan, section 2.
- Whether the docs changed after 2026-11-02. Unread, so unmeasured.

### The owner's plan (audit row F190)

- The owner asked on 2026-11-01 18:24 CST: "is it possible that old sessions aren't trusted … surf the web too". Read: audit row F190, same pinned audit.
- The docs research came back with nothing on the trust error. The coordinator's question about the owner's plan has no answer. The audit found no roadmap step for it. Read: audit row F190.
- The owner's plan is unanswered. Plan, section 4 holds two questions for the owner. Q1 asks how a cloud session answers a local session. Q2 asks whether the trust card should be taken more widely. The plan records no owner answer to either. Whether either reached the owner's waiting page: unknown, not checked here.
- This record files no question about the plan. Any such question goes through the question check first. The check is roadmap step `question-checks-past-rulings` (status done): past rulings on a question are found and cited before the question reaches the owner. Rule `parallelism-keep-going` lets a session start an undoable follow-up without asking.
- The only known workaround is a one-way pc-bridge session with no `cs-build:` tag. The pc-bridge session is the test session in audit row F189. Rule `trust-card-in-build` (guard rule that denies the two owner-card calls in a `cs-build:` session) steers a build session to hand the card to the owner or to an untagged session. Read: decision `session-tiers`, rule `trust-card-in-build`; audit row F188. Whether this clears the refusal: unknown.

Risk: a session may state an inference as an answer. Audit row F188 is that case. Each claim above carries its mark.

Cost: one Markdown file (unmeasured). No process, no check at run time, no log.

Known limit: the docs read stops at 2026-11-02. The tool text is coordinator-reported from 2026-11-01. The cause of the 2026-10-30 block is unmeasured.

Kind: process
Home: docs/plans/local-session-reach.md

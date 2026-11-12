# An owner grant typed in one session reaches the session it names

## The ruling

Owner, Cockpit item 152 (grant-plan-signoff), saved 2026-11-03 18:21 CST: pick a, sign off the
plan `docs/plans/grant-reaches-lanes.md` as written. Each of its seven questions takes the
recommended pick:

1. Gate the named act in the receiving session, before the auto-mode classifier.
2. A fixed grant word, with its act catalogue in code. No free-text grant.
3. The first catalogue is `merge <pr>` and `self-edit`. Open for the owner's ruling: the plan's measurements (2026-11-06) show `self-edit` gates nothing and `merge <pr>` is covered by decision `standing-merge-grant`. The plan recommends the lane's `Agent` spawn first.
4. `self-edit` reaches the target's agents. `merge` stays with the batch runner, never its agents. Moot while `self-edit` gates nothing.
5. Probe the `PreToolUse` hook gate first, the mod `tool.check` gate second.
6. Design A, the server-attested pointer, only. Design B only if Design A's computer probes fail.
7. Keep the cloud merge allow rule (`merge/cloud_allow.json`) until the probe shows why batch
   runner 8 was refused. Superseded, pending ruling 3: the later merge refusal (2026-11-07 13:05 CST) is covered by the "Relayed Merge Yes" entry in settings.json.

Build step 1 is a probe in one session. Nothing past it is built until the probe reads back.

Older rulings a build would change. Nothing is built, so none changes now. A build that adds the grant word rewrites each sentence in place, in the same change:

- Decision `relayed-grant-read-from-page`: "Auto mode trusts only words typed in the session's own chat." Design A has a session read the owner's typed event in another session.
- Decision `standing-merge-grant`: "It holds no grant of its own." A grant word gives the batch runner a grant of its own.
- Decision `owner-override`: "An override covers only the session where the owner typed it." A grant word is typed in one session and names another.

Why: the owner had to type a grant again in each session (plan, section "The problem").

Kind: build
Plan: docs/plans/grant-reaches-lanes.md#6-questions-for-the-owner (all)

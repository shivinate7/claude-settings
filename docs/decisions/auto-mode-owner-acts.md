# Which acts auto mode allows with no ask

## Ruling

Owner, 2026-10-30 16:24 CDT, relayed by the coordinator session: the auto-mode classifier keeps refusing the coordinator's routine acts, which the owner always grants. Allow them. Owner, 16:37 and 17:03 CDT: everything about auto mode lives together. This record is the one home for every auto-mode allow entry.

### The test for a new entry

An act gets an allow entry only if all three hold:

- The owner always grants it. A named refusal shows it (`building-guard-needs-incident`).
- It can be undone, or it loses nothing.
- The entry names the act in its narrow form, quotes the measured command, and ends with a "Never covers" sentence. Never a broad class, such as "any GitHub write".

Each entry keeps `$defaults`, the classifier's built-in exceptions.

### Current entries

| Entry | Covers | Record |
|---|---|---|
| "Archived Branch Delete" (`settings.json` `autoMode.allow`) | A branch delete after its archive push, or of a merged branch | this record |
| Merge confirm (`merge/cloud_allow.json`, cloud only) | `~/.claude/bin/merge ... --confirm` | mechanics in `session-tiers` |
| PR close and PR comment (`merge/cloud_allow.json`, cloud only) | Exactly `gh api -X PATCH repos/shivinate7/<repo>/pulls/<n> -f state=closed` and `gh api -X POST repos/shivinate7/<repo>/issues/<n>/comments -F body=@<file>`, in that flag order. Mistake it stops: the classifier refused the batch runner's closes of Degen PRs 530 and 518 as "External System Writes" at 20:06 CST, 2026-11-08, so a batch stalled on the owner. Owner, Degen page item 163 a, 20:40 CST; item 161 a names the acts. A permission rule cannot see a session's tags, so every cloud session gets it, wider than item 161 a. `*` matches spaces (Claude Code docs, permissions page, read 2026-11-08), so a mistyped extra flag inside the path can still match. Cost: two lines in the cloud settings.json, no process, no file, no log | this record |
| "Owner PR Housekeeping" (`settings.json` `autoMode.allow`) | In a `shivinate7` repo: close a PR the coordinator or batch runner named in the visible conversation as replaced, empty or batched. Mark ready only an integration PR that the visible conversation names as such: the batch's or a lone lane's, named by the coordinator or batch runner, or the one PR of a solo or one-lane session that no coordinator started, named by that session | this record |
| "Owner Session Message" (`settings.json` `autoMode.allow`) | `send_message` to a session in the owner's own account, including the session that started this one (its parent or coordinator). A message that asks for no act is covered. A message that asks is limited to acts the owner already granted. A coordinator may send a batch runner it created a merge go (owner, 2026-11-03 15:58 CST) | this record |
| "Relayed Merge Yes" (`settings.json` `autoMode.allow`) | `~/.claude/bin/merge <pr> --confirm` by a session tagged `cs-build:batch-runner`, for the one pull request that a session tagged `cs-build:coordinator` named when it relayed the owner's yes to merge it, under every merge check | this record |
| "Batch Runner Merge" (`settings.json` `autoMode.allow`) | `~/.claude/bin/merge <pr> --confirm` by a session tagged `cs-build:batch-runner`, for a pull request its coordinator named in a merge go, under the coordinator's standing grant and every merge check | this record |
| `mcp__claude-code-remote__add_repo` (`settings.json` `permissions.allow`) | Attach a GitHub repo to the session | this record |
| `mcp__claude-code-remote__archive_session` (`settings.json` `permissions.allow`) | Archive a session in the owner's account | this record |
| `mcp__claude-code-remote__send_message` (`settings.json` `permissions.allow`) | Any `send_message` call. No bound is checked (see Send message allow rule) | this record |

This table states what each entry covers, not what the cloud does. What the cloud does with these acts is stated by route rows (`GLOSSARY.md`). The rows between the markers are planned to be generated from `hooks/route_rows.json`. No generator exists yet.

<!-- route-rows:start -->
<!-- route-rows:end -->

The merge confirm is a permission allow rule, not an `autoMode` entry. The classifier does not judge it.

An allow rule for `merge --role` waits on the tag check of #878 (merge role reads the session tag).

"Owner PR Housekeeping" never covers a merge, an approval, a review, or a title or body edit. Nor a change of a PR's base branch. Nor a branch or ref delete (`--delete-branch` included), a force push, a PR nobody named, or a repo outside `shivinate7`. Nor marking ready a lane PR that joins a batch, which stays draft, or a PR with auto-merge on, since that merges it. "Owner Session Message" covers a message that only informs and asks for no act: a status note, a pull request number and head, batch heads, or a question about state. The limit to acts the owner already granted applies to a message that asks. A report that carries a request, such as `ready to merge` or `next: merge`, or that relays a grant or hands off an act, however phrased, is a message that asks. It never covers a request to change permissions, settings or overrides. Nor a merge ask, with one exception. A session tagged `cs-build:coordinator` may send a merge go for a named PR to a batch runner it created, with tags `cs-build:batch-runner` and the coordinator's own `cs-repo:` (decision `standing-merge-grant`: the batch runner runs every merge under the coordinator's grant). Nor a request to approve a PR. Nor `priority: now`, which interrupts the target's running turn. Nor a post people read, such as `visibility: posted_to_shared_channel`.

### Sent messages sorted

A scan of refused `send_message` calls on 2026-11-06 sorted them. Owner request: item 315 b on the owner's waiting page (lane brief judge-send-message-refusals, 2026-11-06 17:05 CST). This section holds no owner ruling.

- Correct refusals:
  - A message that carried a page grant the owner never typed in chat.
  - An agent's mistaken send.
  - A hand-off of a refused delete of a seed branch.
- False alarms already fixed:
  - Five merge-go sends refused on 2026-11-03. Pull request 1115, the merge-go carve-out, held. The sessions had stale settings.
- Likely false alarm: two status or batch-heads sends in the same scan. The message text is unmeasured.
- Stays refused even when phrased as a report: a message that relays a page grant the owner never typed, or hands off a refused act.

Gap closed: a lane could not message its coordinator, since the target list named only sessions this session or its coordinator created. The entry now names the session that started this one. A message that asks for no act is covered, so a status note no longer meets the already-granted limit.

Left to the coordinator: pull request 1372's blanket `permissions.allow` line for `send_message`. Drop it after this change merges.

### Merge go to a batch runner

Owner, 2026-11-03 15:58 CST, typed in the lane session merge-go-message-allow: `narrow the merge carve-out in the "Owner Session Message" entry of settings.json autoMode.allow, so a coordinator may send its own batch runner a merge go under standing-merge-grant`. Incident: at 15:48 CST the classifier refused a coordinator's `send_message` that gave its own batch runner a merge go, as "Merge Without Review". The entry's merge refusal predates `standing-merge-grant` (owner, 2026-11-01 21:34 CST). The carve-out covers only that merge go. A merge ask to any other session, or from a session that is not a coordinator, stays refused.

### Batch Runner Merge

Owner, 2026-11-07 13:27 CST, typed in lane session relayed-yes-allow: `go runner-merge-allow: allow batch-runner merges under the coordinator's standing grant`. Earlier ask: Queue item 149 b (owner, 2026-11-01 22:16 CST), which auto mode did not count as typed words. Incident: auto mode refused runner 8's merges until the owner typed his grant in its chat (2026-11-01 22:23 CST, roadmap step runner-merge-allow). The entry covers only a merge the coordinator named in a merge go to its own batch runner (decision `standing-merge-grant`). It lifts no merge check, and never covers a flag that lifts one (`--base-red-ok`, `--undo-check-unknown-ok`). The merge go must come from a session tagged `cs-build:coordinator`.

### Relayed Merge Yes

Owner, 2026-11-07 13:10 CST, coordinator-reported: a yes the coordinator passes on is enough. Owner, 13:19 CST, typed in lane session relayed-yes-allow: `add the relayed-yes grant to .claude/CLAUDE.md and an autoMode.allow entry for merges on a coordinator-relayed owner yes`. Incident: at 13:05 CST the classifier refused batch runner 8's `merge 1421 --confirm` on an owner yes the coordinator relayed. The entry covers that merge only, by a session tagged `cs-build:batch-runner`, since a lane and the coordinator never merge (decision `standing-merge-grant`). It lifts no merge check, and never covers a flag that lifts one (`--base-red-ok`, `--undo-check-unknown-ok`). It never covers another act, a pull request the relay did not name, or a relay from a session not tagged `cs-build:coordinator`. Gap: the refusal was recorded as `merge 1421 --confirm`; whether runner 8 typed the full `~/.claude/bin/merge` path is unknown. Gap: whether the classifier reads the relay message is unmeasured.

### Archived Branch Delete

The entry tells the classifier that a branch delete loses nothing in two cases:

- Earlier in the session, the agent pushed that branch to `archive/<branch>` on the same remote, with no later commit, reset, rebase or amend on it.
- The branch is already in the default branch: `git branch -d`, or a branch whose pull request the session merged.

It never covers an `archive/` ref, the default branch, a tag, a release, a force push, or a branch whose archive push the session did not run.

Why: the guard's remedy (`guard_branch_worktree.BRANCH_DELETE_DENY_REASON`) hands over the archive push and the delete as commands. The classifier's built-in "Git Destructive" rule still asked the owner about the delete. That broke `shared-trees-archive-then-delete` (once the push succeeds, delete with no question).

- Risk: named incident. On the Mac, the probe branches of c53 (the cloud merge tool) were archived, then the deletes were refused and the owner was asked again.
- Check: the test reads the remedy's commands from the guard constant and fails until the entry quotes each one.
- Gap: the classifier sees commands, not their output. A failed archive push followed by a delete is still allowed by this entry. The guard's own remote-contains test still refuses the local `git branch -D` then.

### Marking a lone lane's PR ready

Owner, 2026-11-01 19:19 CST, typed in the pr-acts-grant lane session: `when an operation is occuring solo and/or there is only one "outcome" PR (ie it's not going into an integration branch) then of course they can be marked ready`.

- The entry now covers two cases, each named in the visible conversation:
  - The batch's integration PR, or a lone lane's PR, named so by the coordinator or batch runner. Skill `ci-hygiene` (CI upkeep), step 8 (Batch lanes), treats a lone lane as its own integration PR.
  - The one PR of a solo or one-lane session that no coordinator started, named so by that session.
- A lane PR that joins a batch stays draft. Only the batch's integration PR goes ready.
- The merge itself is not in this entry (see the standing merge grant record).

### Remote tool allow rules

All three (`add_repo`, `archive_session`, `send_message`) are permission allow rules, not `autoMode` entries, so the classifier does not judge them. The docs say: "Actions matching your allow, ask, or deny rules resolve immediately, with these exceptions:" (https://code.claude.com/docs/en/permission-modes#how-the-classifier-evaluates-actions). This is documented, not measured here.

One exception that can apply: an MCP tool marked `requiresUserInteraction` prompts even when an allow rule matches. Unknown whether these three tools are marked so.

- Incident, coordinator-reported, not measured here. The coordinator session (session_013NEJL2pASwRjgJDnsvnpNe) relayed on 2026-11-01: the auto-mode classifier refused `archive_session` from 2026-10-31 on, and about 40 idle sessions stayed open. It refused `add_repo` in repo `degen` at 16:46 CST and in repo `joyous` at 17:14 CST, with the reason "Access Added As A Means".
- `add_repo` loses nothing. It attaches a repo to the session and mints credentials for it.
- `archive_session` fails the test "can be undone, or loses nothing". Unarchive gives a fresh container, so unpushed work in the old one is lost. The owner waives that test. Their typed go, 2026-11-01 17:37 CST, covers both tools. It is the verbatim grant: "add mcp__claude-code-remote__add_repo and mcp__claude-code-remote__archive_session to settings.json permissions.allow". The rule covers any session in the account.
- Never covers `add_repo`: any other remote tool, or the server-level form.
- Never covers `archive_session`: any other remote tool, or the server-level form.

### Send message allow rule

Owner, page item 301 a, 2026-11-06 15:24 CST: "yeah allow it, maybe we fix the judge itself for send messages though in genearl [sic] i think it's only blocked problematically". Built as #1364 (send_message allow, local session), rebuilt as #1372 (send_message allow, cloud).

- Incidents: on 2026-11-06 auto mode refused `send_message` from the coordinator and from lanes. Earlier refusals: notes `auto-mode-refuses-page-grant` (coordinator refused on a page grant) and `agent-send-message-refused` (agent call refused in a lane).
- It is a permission allow rule, so the classifier does not judge it (see Remote tool allow rules). This is documented, not measured here.
- Gap: the rule stops the classifier from applying the "Owner Session Message" bounds to `send_message`: `priority: now`, a post to a shared channel, a target outside the owner's account. No hook checks these bounds. Owner, page item 315 b, 2026-11-06 17:00 CST: add no guard for them. Instead, step `judge-send-message-refusals` (fix the judge for send messages, run from the owner's laptop) fixes the cause in the judge's rules, in #1380 (the judge fix). Planned, not yet in that step: a follow-up after #1380 removes `send_message` from `permissions.allow` once the judge stops refusing ordinary messages.
- Undo: remove the line from `settings.json`.
- Never covers: any other remote tool, or the server-level form.

### Incidents for the owner PR and owner message entries

Marking ready a lone lane's pull request was refused twice, as "Unrequested Commit in a Connected App" (coordinator-reported, unmeasured here): q_max #997 at 16:28 CST and banchi #1004 at 17:36 CST, 2026-11-01. Marking a batch's integration pull request ready has no measured refusal: unmeasured. The 2026-10-30 ruling names it, so it stays.

Both were refused as "External System Writes" on 2026-10-30:

1. Closing joyous PR #54, the owner's own PR with an empty diff: `gh api -X PATCH repos/shivinate7/joyous/pulls/54 -f state=closed`.
2. `mcp__claude-code-remote__send_message` to the owner's own Remote Control session, asking it to run his granted acts.

Other classifier refusals that day: unknown. The coordinator's transcript could not be read from its lane (`elevated_session_untrusted_device`).

### Notes

- Not covered: the server's `elevated_session_untrusted_device` refusal is not the classifier. No entry can lift it. It also refused one of this lane's `send_message` calls to its coordinator.
- Widens a shared tool (t18, the uniform ruling): yes. The owner chose this knowing it. `settings.json` installs into `~/.claude`, so the entries apply in every repo. The `shivinate7` and own-account bounds keep them to the owner's own things.
- Home: the classifier reads `autoMode` only from `~/.claude/settings.json`, managed settings or `--settings`. `install.sh` links or copies this repo's `settings.json` there.
- Check: `hooks/test_auto_mode_allow.py`, the one check for `autoMode`. It pins each named entry: the entry exists once, quotes its incident, and names its bounds in its Covers text and in a "Never covers" sentence. A new entry adds its own pins there. It also fails a list that drops `$defaults`.
- Cost: none at run time. The classifier already runs; each entry adds prose to its prompt.
- Gap: the classifier sees the command, not who named the PR. A close on a misread task is still allowed when the conversation shows the PR named as replaced, empty or batched. A closed PR can be reopened.

Kind: process
Home: rule:parallelism-keep-going

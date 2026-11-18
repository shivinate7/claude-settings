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
| "Own Branch Lease Push" (`settings.json` `autoMode.allow`) | A lease push to the session's own lane branch, after this session pushed that branch earlier. Its "refspec form" entry allows the same push typed as `origin <src>:<branch>`. Two forms only: `--force-with-lease --force-if-includes origin <branch>`, or a lease pinned to the sha this session last pushed. Never a bare force, a `+refspec`, a delete, or the default branch | this record |
| Merge confirm (`merge/cloud_allow.json`, cloud only) | `~/.claude/bin/merge ... --confirm` | mechanics in `session-tiers` |
| "Owner PR Housekeeping" (`settings.json` `autoMode.allow`) | In a `shivinate7` repo: close a PR the coordinator or batch runner named in the visible conversation as replaced, empty or batched. Mark ready only a PR that the visible conversation names as such: until the cutover, the batch's integration PR or a lone lane's, named by the coordinator or batch runner; after it, a lane PR the visible conversation names as ready after its last review and lane lint (Q2, decision `draft-until-reviewed`), or the one PR of a solo or one-lane session that no coordinator started, named by that session | this record |
| "Owner Session Message" (`settings.json` `autoMode.allow`) | `send_message` to a session in the owner's own account, including the session that started this one (its parent or coordinator). A message that asks for no act is covered. A message that asks is limited to acts the owner already granted. A coordinator may send a batch runner it created a merge go (owner, 2026-11-03 15:58 CST) | this record |
| "Relayed Merge Yes" (`settings.json` `autoMode.allow`) | `~/.claude/bin/merge <pr> --confirm --head <sha>` by a session tagged `cs-build:batch-runner`, for the one pull request that a session tagged `cs-build:coordinator` named when it relayed the owner's yes to merge it, under every merge check | this record |
| "Consultant Relayed Merge Yes" (`settings.json` `autoMode.allow`) | The same command and head form as "Relayed Merge Yes", by a session tagged `cs-build:batch-runner`, for the one pull request that a session tagged `cs-build:consultant` named when it relayed the owner's yes, directly or through a session tagged `cs-build:triage` that forwards what the consultant relayed, under every merge check | this record |
| "Batch Runner Merge" (`settings.json` `autoMode.allow`) | `~/.claude/bin/merge <pr> --confirm --head <sha>` by a session tagged `cs-build:batch-runner`, for a pull request its coordinator named in a merge go, under the coordinator's standing grant and every merge check | this record |
| "Merge Review Record" (`settings.json` `autoMode.allow`) | `merge <pr> --review-record` or `merge --review-record <pr>`, as `merge` or `~/.claude/bin/merge`, with only the record flags, by a session tagged `cs-build:lane`: it prints the review record and posts and merges nothing | this record |
| "Main Installer" (`settings.json` `autoMode.allow`) | The install from main in one exact form: `cd /root/claude-settings-main && CLAUDE_SETTINGS_REF=main ~/.claude/bin/verdict bash /root/claude-settings-main/merge/install_from_main.sh`. No bare form, other env var, ref, script, argument or chaining | this record |
| "Session Installer" (`settings.json` `autoMode.allow`) | The session-start installer in three exact forms: `curl -fsSL <stable install.sh URL> \| CS_HOOK_INPUT="{}" bash -s -- --cloud`, and from a claude-settings checkout `bash install.sh` and `powershell -ExecutionPolicy Bypass -File .\install.ps1`. No env var, chaining, extra argument, other URL or ref | this record |
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

Coordinator, 2026-11-08 12:55 CST: in a session that recorded the batch-runner role, the merge tool refuses `merge <pr> --confirm` with no `--head`. The batch runner merges the head its CI ran on. The coordinator names that head in every merge go.

Departs from: main, which lets `--confirm` through with no `--head`. Now a session that recorded the batch-runner role must pass `--head`.

The entry now quotes the `--head <sha>` form: `~/.claude/bin/merge <pr> --confirm --head <sha>`.

### Merge Review Record

Owner, 2026-11-14 14:59 CST, page item 839, pick a: allow a lane session to print the review record. Incident: auto mode refused the call as "Undermining Oversight" at least 7 times in lane sessions (PRs 3226, 3411 and 3407). The lane then posts the printed text itself as a pull request comment (decision `pr-review-record`). The grant text said main has no entry for it. That was wrong for the bare form: main's "Merge Tool Read Checks" already allows `merge <pr> --review-record`. The new entry is for lane sessions only, tagged `cs-build:lane`, and names the record flags the printed text takes. The cause of the denial is unmeasured. Only a live classifier proves the entry works. The next lane record post after this merges tells.

### Merge Tool Read Checks

Owner, 2026-11-15 11:30 CST, page item 863 (pick-lane-lint-allow-entry), pick b, typed on the waiting page: "Amend settings.json autoMode.allow entry "Merge Tool Read Checks" now, without the refusal words". The option's own how: "The entry is widened to let a lane run merge --lane-lint in the background, at once." The option carried the widening label ("a repo changes to fit a shared tool, never the tool to fit a repo"). The owner chose it knowingly. The grant covers that entry and that act only. Ruling id: `own-lane-lint-allow-b`.

The entry now has two changes.

- It names the background run. A lane may run `verdict merge --lane-lint <pr|commit|ref>`, or the same with full paths, in the background, because the call only reads and posts that one comment. The Never covers sentence is byte-identical.
- It drops its Incident sentence: `Incident: refused once as "Merge Without Review" (runner 9, q_max, 2026-11-07 23:31 CST).` That sentence was the only place the entry quoted a refusal name. The coordinator's brief read the option's "without the refusal words" as "drop them". The option means widen now, without waiting for the exact words. The drop stays as a harmless trim: whether it matters to the classifier is unmeasured. The incident now lives only in this paragraph. `docs/plans/grant-reaches-lanes.md` holds the earlier runner 8 refusal of 2026-11-01.

The classifier refusal of a background lane lint is coordinator-reported (brief, 2026-11-15 11:46 CST) and unmeasured here. A second guard, the check-timeout hook, denied the call when its background time limit sat under 3900000 ms. This entry cannot lift that hook. Only a live classifier proves the entry works: the next background lane lint after this merges tells. The entry's "merges nothing" claim is false for a lint PASS on a batch integration PR (`merge/merge.py` calls `close_replaced` and `reopen_dropped`). Owner item 863 did not name that, so it is an open owner question. `hooks/test_auto_mode_allow.py` (class `MergeToolReadChecksIsAllowed`) pins the dropped words once and the background form, and reads the other limits from the entry.

### Relayed Merge Yes

Owner, 2026-11-07 13:10 CST, coordinator-reported: a yes the coordinator passes on is enough. Owner, 13:19 CST, typed in lane session relayed-yes-allow: `add the relayed-yes grant to .claude/CLAUDE.md and an autoMode.allow entry for merges on a coordinator-relayed owner yes`. Incident: at 13:05 CST the classifier refused batch runner 8's `merge 1421 --confirm` on an owner yes the coordinator relayed. The entry covers that merge only, by a session tagged `cs-build:batch-runner`, since a lane and the coordinator never merge (decision `standing-merge-grant`). It lifts no merge check, and never covers a flag that lifts one (`--base-red-ok`, `--undo-check-unknown-ok`). It never covers another act, a pull request the relay did not name, or a relay from a session not tagged `cs-build:coordinator`. A relayed yes binds to the pull request's head when the coordinator relays it (coordinator brief, 2026-11-07 13:55 CST). The relay names the head sha, and the batch runner merges with `--head <sha>`. So a push after the yes needs a new yes. A commit the merge tool itself pushes on top of that head, its record-claim commit or the revert of that claim, keeps the yes (lane ruling, 2026-11-08 12:53 CST). Gap: `merge/cloud_allow.json` allows `merge <pr> --confirm` with or without `--head` before auto mode judges it, so in the cloud the head binding rests on the batch runner adding `--head` from the relay. Narrowing that rule would change every merge under the standing grant, which the owner has not ruled. Measured 2026-11-08: runner 8 typed the full path, `~/.claude/bin/merge 1421 --confirm`, followed by a redirect and a `;` chain. Gap: whether the classifier reads the relay message is unmeasured.

Gap update (coordinator, 2026-11-08 12:55 CST): in a session that recorded the batch-runner role, the merge tool now refuses `merge <pr> --confirm` with no `--head`. For such a session, the head binding no longer rests on the batch runner adding `--head` from the relay. The Gap above remains true outside such sessions.

### Consultant Relayed Merge Yes

Owner, 2026-11-15 11:18 CST, typed in batch runner 12's chat: `i want the allow rule - u can do that in this lane and merge it in`. Incident: the classifier refused `merge 172 --confirm --head bc38039c4255188e8ab2e1393f4dd9f7e7cdf993` twice, at about 09:03 and 11:05 CST, as "Destructive or Unwanted Actions". The yes was "yes 172", relayed by the owner's consultant. "Relayed Merge Yes" covers only a coordinator relay.

Departs from: the owner's ruling "a repo changes to fit a shared tool, never the tool to fit a repo". The owner chose the shared entry anyway.

- The relay comes from a session tagged `cs-build:consultant` (`CONSULTANT_TAG` in `hooks/shared_names.py`), directly or through a session tagged `cs-build:triage` that forwards what the consultant relayed. A yes that started at triage with no consultant is not covered. The merge is by a session tagged `cs-build:batch-runner`, with the same command as "Relayed Merge Yes".
- Attribution. The direct path rests on the owner's own words at 11:18 CST. The triage path rests on the consultant's relay at 11:31 CST, sent through the coordinator, that the owner typed "a" at 11:29 CST, and on the incident path: owner to consultant, to triage, to the runner. The owner's own typed words do not name the triage hop.
- The yes binds to the head the pull request had when the consultant relayed it, as in "Relayed Merge Yes". The merge tool (`relayed_head_holds` in `merge/merge.py`, called from the merge command) refuses a live head that is not the relayed head. One exception: a head that sits on it with only a Record-claim commit, its revert or a page-only commit between. It compares the live head with the `--head` the runner passes. So the head binding rests on the runner passing the head the pull request had when the consultant relayed, and on the classifier reading the chat. The merge tool does not check `--head` against the relay. `relayed_head_holds` itself reads no review record. The merge tool reads review records elsewhere.
- It lifts no merge check. It never covers a flag that lifts one (`--base-red-ok`, `--undo-check-unknown-ok`), an admin merge, another pull request, or a merge with no `--head`.
- Measured: the consultant session's tags, read with `get_session` at 11:23 CST on 2026-11-15, include `cs-build:consultant`.
- The owner was told at 11:17 CST, before he asked for the entry, that it departs from his ruling "a repo changes to fit a shared tool, never the tool to fit a repo".
- Gap: if the consultant's relay named no sha, the incident's own command `merge 172 --confirm --head bc38039c4255188e8ab2e1393f4dd9f7e7cdf993` was outside this entry as written. Unmeasured.
- Gap: "Owner Session Message" never covers a merge ask from a session that is not a coordinator, and a consultant relay to the batch runner is such an ask. The incident relay arrived, so this may be fine. Unmeasured.
- Gap: the classifier sees the command, not who relayed the yes. Whether the live classifier honours the entry is unmeasured. The next consultant-relayed merge tells.
- Check: `ConsultantRelayedMergeYesIsAllowed` in `hooks/test_auto_mode_allow.py`.

### Archived Branch Delete

The entry tells the classifier that a branch delete loses nothing in two cases:

- Earlier in the session, the agent pushed that branch to `archive/<branch>` on the same remote, with no later commit, reset, rebase or amend on it.
- The branch is already in the default branch: `git branch -d`, or a branch whose pull request the session merged.

It never covers an `archive/` ref, the default branch, a tag, a release, a force push, or a branch whose archive push the session did not run.

Why: the guard's remedy (`guard_branch_worktree.BRANCH_DELETE_DENY_REASON`) hands over the archive push and the delete as commands. The classifier's built-in "Git Destructive" rule still asked the owner about the delete. That broke `shared-trees-archive-then-delete` (once the push succeeds, delete with no question).

- Risk: named incident. On the Mac, the probe branches of c53 (the cloud merge tool) were archived, then the deletes were refused and the owner was asked again.
- Check: the test reads the remedy's commands from the guard constant and fails until the entry quotes each one.
- Gap: the classifier sees commands, not their output. A failed archive push followed by a delete is still allowed by this entry. The guard's own remote-contains test still refuses the local `git branch -D` then.

### Own Branch Lease Push

Owner grant, typed in lane lease-push-c-and-d, 2026-11-07 13:28 CST: `go: add the "Own Branch Lease Push" entry to settings.json autoMode.allow, as drafted in lane lease-push-c-and-d`.

The owner's pull request #2350 (branch allow-lease-push-refspec, merge e53fad223) put this entry on main. It also added "Own Branch Lease Push, refspec form": the same two forms typed with a source, `origin <src>:<branch>`, where `<src>` is a local branch, `HEAD` or a commit sha. Its Never covers adds a `+` before either ref and an empty `<src>` (a delete).

A lease push to a lane's own branch loses nothing the lane did not write. It is allowed only when this session pushed the same branch to the same remote earlier, and the push is one of:

- `git push --force-with-lease --force-if-includes origin <branch>`
- `git push --force-with-lease=<branch>:<sha> origin <branch>`, where `<sha>` is the tip this session last pushed.

It can be undone: the old tip stays on the pull request's timeline, and in the reflog of the clone that pushed it.

It never covers a bare `--force` or `-f`, a `+refspec`, or a lease with neither `--force-if-includes` nor a named sha. Nor the default branch, an `archive/` ref, `roadmap` or `merge-lock`. Nor a branch this session did not push earlier, `--mirror`, `--all`, or a delete.

Why: the force-push guard's remedy (`PUSH_REASON` in `hooks/guard_push_delete.py`) names `--force-with-lease --force-if-includes`. The classifier's built-in "Git Destructive" rule still refused that form. Pull request #1255 (part d of the lease push roadmap step, `lease-push-c-and-d`) made the Red-run trailer check's remedy name no force push. This entry is part c.

- Risk: named incident. The entry quotes 9 lease-push refusals and 8 replacement pull requests, 2026-11-02 to 2026-11-04, from the roadmap step. A survey of `docs/debts/notes.md` on main (lane relayed-yes-allow, 2026-11-07 13:38 CST) counts 11 refused lease pushes in that span, of both forms. The entry keeps 9, the text the owner granted. Incident home: note `classifier-refuses-lease-push`. Owner's answer on the owner's waiting page, item 257, 2026-11-05 07:44 CST: "shouldn't it be c and d".
- Check: `hooks/test_auto_mode_allow.py` pins this entry and its refspec form. It exists once and quotes both push forms and the guard remedy from `PUSH_REASON`. Its Covers text binds the sha to the tip this session last pushed. Its "Never covers" sentence names each refused act, including a lease with neither `--force-if-includes` nor a named sha.
- Gap: the classifier sees the command, not whether this session pushed the branch earlier. The guard still refuses a bare force.

### Marking a lone lane's PR ready

Owner, 2026-11-01 19:19 CST, typed in the pr-acts-grant lane session: `when an operation is occuring solo and/or there is only one "outcome" PR (ie it's not going into an integration branch) then of course they can be marked ready`.

- The entry now covers two cases, each named in the visible conversation:
  - The batch's integration PR, or a lone lane's PR, named so by the coordinator or batch runner. Skill `ci-hygiene` (CI upkeep), step 8 (Batch lanes), treats a lone lane as its own integration PR. After the cutover (decision `all-repos-switch-together`), a lane PR goes ready once, under decision `draft-until-reviewed`, and no integration PR exists.
  - The one PR of a lane that no coordinator started, named so by that session.
- Until the cutover, a lane PR that joins a batch stays draft. Only the batch's integration PR goes ready.
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

### Main Installer

Owner, 2026-11-17 10:00 CST, typed in the chat of lane rebase-wave-1b: `(a) you add a permission rule for that command for sure`. Incident: the classifier refused `CLAUDE_SETTINGS_REF=main ~/.claude/bin/verdict bash /root/claude-settings-main/merge/install_from_main.sh` in lane rebase-wave-1b at 15:59 CST on 2026-11-16, as Undermining Oversight (the lane's summary quotes the script path as `merge/install_from_main.sh`; the absolute form is the coordinator's). On 2026-11-17 lanes of five repos reported the same refusal in their own summaries (lane count unmeasured). The coordinator's order of 09:56 CST names the line after `cd /root/claude-settings-main &&`, and the entry allows only that form: the script takes its clone from the working directory, so the bare line run in another repo would pin and fast-forward that repo, which the owner did not name. Finding: the refusal comes from the auto-mode classifier, which reads `autoMode.allow`, not `permissions.allow`. The owner's own deny rule `Edit(~/.claude/settings.json)` blocks a direct edit of the installed file, so the rule is an entry in this repo's `settings.json`, installed by the next refresh.

Why the act is allowed: `merge/install_from_main.sh` fetches origin, fast-forwards local main, moves the pinned checkout `<clone>-live`, prunes old pinned trees and rewrites `~/.claude` from the pin, and a second run restores that state. With `CLAUDE_SETTINGS_REF=main` it installs local main whatever its CI state; that is the recovery path the owner named, not the green-only `stable` path. The script path is absolute because the coordinator's order names it that way; `/root/claude-settings-main` is the clone on the cloud host. Known limit: the separate guard `other-checkout` (it refuses a `cd` into another clone of the repo) still denies this line in a session whose home is a claude-settings checkout or worktree, so a lane standing there needs the owner's `override` for that one act (measured with `python3 hooks/probe.py` by the round 2 reviewer, one host only). The entry unblocks lanes of other repos. The Session Installer entry never covers it (its Never covers names `CLAUDE_SETTINGS_REF` and `main`), so this entry is its own, for the one line the coordinator named.

`hooks/test_auto_mode_allow.py` (`MainInstallerIsAllowed`) checks the one entry, its one quoted command (the `cd` form, never the bare line), that nothing follows it, the owner and incident times, and each refused act. It went red on main's `settings.json` (the Red-run trailers of the commits give the counts) and green on this change.

Departs from: main, whose `settings.json` has no entry for this command.

### Session Installer

Owner, 2026-11-13 20:16 CST, in chat: `the rignt answer is obviously a: add an allow rule for exactly the reinstall command`. The words reached the lane through a consultant relay, as the lane brief's Grant line records it ("consultant relay"), and the lane did not verify them. Incident: at 20:12 CST the classifier refused a coordinator's compound line, `cd /root/claude-settings-main && bash install.sh --cloud 2>&1 | tail -15; ...` (coordinator message, 20:20 CST). The lane brief names only `bash install.sh --cloud`.

Why the act is allowed: the installer rewrites `~/.claude` from the `stable` branch (the `REF` default, `install.sh` line 23) and, in a cloud session, runs the repo's startup hooks (decision `cloud-start-hooks-run-fresh`). Where `jq` is present, every cloud session start already runs the curl form as its own refresh hook (`install.sh`, `HOOK_CMD`, added only under `command -v jq`). Unmeasured: that a second run leaves the same state; no test of it is cited here.

The forms are read from `install.sh` (`REPO`, default `REF`, `HOOK_CMD`) and `install.ps1`'s header by `hooks/test_auto_mode_allow.py` (`installer_forms`), never copied. The curl form is the SessionStart hook's own command with its stdin as `{}` (coordinator message, 20:18 CST). No entry matches the compound line above, because the entry's Covers text allows each form "with nothing before them and nothing after them" (`settings.json`, entry "Session Installer"). The local `bash install.sh` and `install.ps1` forms have no measured refusal.

Departs from: the state before PR 3323 (head `82e38f96ec`, merged as `02400a24bd`), when `settings.json` had no installer entry (checked at `309fa5ed5`). Gap named for the owner: the checkout form `bash install.sh --cloud` is not covered, since the owner named "exactly the reinstall command" and the coordinator ruled it out (coordinator message, 20:20 CST).

Review waiver, relayed by the coordinator (coordinator messages, not the owner): ruling `own-reinstall-no-review`, scope as the coordinator filed it, the one installer entry and its step only. The owner's typed words, quoted by the coordinator, 20:17 CST in runner 10's question box: "all sessions, now, insta merged to main no review needed". That quote is wider than the filed scope. The filing time is unreconciled: the coordinator message that reports triage's filing says 20:28 CST, and the messages that carry it are stamped 20:19 and 20:20 CST. The ruling's own text is not in this repo, and the lane has not read the owner's words.

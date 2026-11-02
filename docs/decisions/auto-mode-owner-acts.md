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
| "Owner PR Housekeeping" (`settings.json` `autoMode.allow`) | In a `shivinate7` repo: close a PR the coordinator or batch runner named in the visible conversation as replaced, empty or batched. Mark ready only an integration pull request: the batch's, named as such there, or the one outcome PR of a solo or one-lane build that goes into no integration branch, named by the session that owns it | this record |
| "Owner Session Message" (`settings.json` `autoMode.allow`) | `send_message` to a session in the owner's own account, asking only for acts the owner already granted | this record |

The merge confirm is a permission allow rule, not an `autoMode` entry. The classifier does not judge it.

An allow rule for `merge --role` waits on the tag check of #878 (merge role reads the session tag).

"Owner PR Housekeeping" never covers a merge, an approval, a review, or a title or body edit. Nor a change of a PR's base branch. Nor a branch or ref delete (`--delete-branch` included), a force push, a PR nobody named, or a repo outside `shivinate7`. Nor marking ready a lane PR that joins a batch, which stays draft, or a PR with auto-merge on, since that merges it. "Owner Session Message" never covers a request to change permissions, settings or overrides, or to merge. Nor `priority: now`, which interrupts the target's running turn. Nor a post people read, such as `visibility: posted_to_shared_channel`.

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

- The entry now covers the one outcome PR of a solo or one-lane build that goes into no integration branch, named by the session that owns it. Rule `git-integration-branch-merge` already treats a lone lane as its own integration PR.
- A lane PR that joins a batch stays draft. Only the batch's integration PR goes ready.
- The merge itself is not in this entry (see the standing merge grant record).

### Incidents for the owner PR and owner message entries

Marking ready a lone lane's pull request was refused twice, as "Unrequested Commit in a Connected App" (coordinator-reported): q_max #997 at 16:28 CST and banchi #1004 at 17:36 CST, 2026-11-01. Marking a batch's integration pull request ready has no measured refusal: unmeasured. The 2026-10-30 ruling names it, so it stays.

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

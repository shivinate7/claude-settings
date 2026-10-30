# Which acts auto mode allows with no ask

## Ruling

Owner, 2026-10-30 16:24 CDT, relayed by the coordinator session: the auto-mode classifier keeps refusing the coordinator's routine acts, which the owner always approves. Allow them. Owner, 16:37 CDT: keep one general record for which acts auto mode allows with no ask. This is that record.

### The test for a new entry

An act gets an allow entry only when all three hold:

- The owner always approves it. A named refusal shows it (`building-guard-needs-incident`).
- It can be undone, or it loses nothing.
- The entry names the act in its narrow form, quotes the measured command, and ends with a "Never covers" sentence. Never a broad class, such as "any GitHub write".

Each entry keeps `$defaults`, the classifier's built-in exceptions.

### Current entries

| Entry | Covers | Record |
|---|---|---|
| "Archived Branch Delete" (`settings.json` `autoMode.allow`) | A branch delete after its archive push, or of a merged branch | `archived-branch-delete-allowed` |
| Merge confirm (`merge/cloud_allow.json`, cloud only) | `~/.claude/bin/merge ... --confirm` | `session-tiers` |
| "Owner PR Housekeeping" (`settings.json` `autoMode.allow`) | Close a PR, or mark it ready, in a `shivinate7` repo, when the coordinator or batch runner named it in the visible conversation as replaced, empty or batched | this record |
| "Owner Session Message" (`settings.json` `autoMode.allow`) | `send_message` to a session in the owner's own account, asking only for acts the owner already granted | this record |

The merge confirm is a permission allow rule, not an `autoMode` entry. The classifier does not judge it.

"Owner PR Housekeeping" never covers a merge, an approval, a review, a title or body edit, a branch or ref delete, a force push, a PR nobody named, or a repo outside `shivinate7`. "Owner Session Message" never covers a request to change permissions, settings or overrides, or to merge.

### Incidents for the two new entries

Both were refused as "External System Writes" on 2026-10-30:

1. Closing joyous PR #54, the owner's own PR with an empty diff: `gh api -X PATCH repos/shivinate7/joyous/pulls/54 -f state=closed`.
2. `mcp__claude-code-remote__send_message` to the owner's own Remote Control session, asking it to run his granted acts.

Other classifier refusals that day: unknown. The coordinator's transcript could not be read from its lane (`elevated_session_untrusted_device`).

### Notes

- Not covered: the server's `elevated_session_untrusted_device` refusal is not the classifier. No entry can lift it. It also refused one of this lane's `send_message` calls to its coordinator.
- Widens a shared tool (t18, the uniform ruling): yes. The owner chose this knowing it. `settings.json` installs into `~/.claude`, so the entries apply in every repo. The `shivinate7` and own-account bounds keep them to the owner's own things.
- Home: the classifier reads `autoMode` only from `~/.claude/settings.json`, managed settings or `--settings`. `install.sh` links or copies this repo's `settings.json` there.
- Check: `hooks/test_auto_mode_allow.py`, the one check for all `autoMode` entries. It fails until each entry exists once, quotes its incident, and names its bounds in a "Never covers" sentence. It also fails a list that drops `$defaults`.
- Cost: none at run time. The classifier already runs; each entry adds prose to its prompt.
- Gap: the classifier sees the command, not who named the PR. A close on a misread task is still allowed when the conversation shows the PR named as replaced, empty or batched. A closed PR can be reopened.

Kind: process
Home: rule:parallelism-keep-going

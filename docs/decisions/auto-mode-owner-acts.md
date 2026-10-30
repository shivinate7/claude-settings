# Auto mode allows the coordinator's routine acts on the owner's own repos and sessions

## Ruling

Owner, 2026-10-30 16:24 CDT, relayed by the coordinator session: the auto-mode classifier keeps refusing the coordinator's routine acts, which the owner always approves. Allow them.

The installed settings carry two auto-mode allow entries:

- "Owner PR Housekeeping": close a pull request, or mark it ready, in a `shivinate7` repo, when the coordinator or batch runner named that PR in the visible conversation as replaced, empty or batched. Never a merge, an approval, a review, a title or body edit, a branch or ref delete, a force push, a PR nobody named, or a repo outside `shivinate7`.
- "Owner Session Message": `send_message` to a session in the owner's own account (one this session or its coordinator created, a `list_sessions` row with `mine: true`, or the owner's Remote Control session). The message asks only for acts the owner already granted. Never a request to change permissions, settings or overrides, or to merge.

Why: each refusal stopped the coordinator until the owner said yes, and the owner said yes each time.

- Risk: named incidents, both refused as "External System Writes" on 2026-10-30:
  1. Closing joyous PR #54, the owner's own PR with an empty diff: `gh api -X PATCH repos/shivinate7/joyous/pulls/54 -f state=closed`.
  2. `mcp__claude-code-remote__send_message` to the owner's own Remote Control session, asking it to run his granted acts.
- Other refusals that day: unknown. The coordinator's transcript could not be read from its lane (the server refused it as `elevated_session_untrusted_device`).
- Not covered: that server refusal is not the classifier, so no `autoMode` entry can lift it. It also refused this lane's `send_message` to its coordinator.
- Widens a shared tool (t18, the uniform ruling): yes. The owner chose this knowing it. `settings.json` installs into `~/.claude`, so the entries apply in every repo. The `shivinate7` and own-account bounds keep them to the owner's own things.
- Home: `settings.json` `autoMode.allow`, beside "Archived Branch Delete" (`archived-branch-delete-allowed`, a branch delete after its archive push).
- Check: `hooks/test_auto_mode_allow.py`. It fails until each entry exists once, quotes its incident, and names its bounds in a "Never covers" sentence.
- Cost: none at run time. The classifier already runs; the entries add prose to its prompt.
- Gap: the classifier sees the command, not who named the PR. A close on a misread task is still allowed when the conversation shows the PR named as replaced, empty or batched. A closed PR can be reopened.

Kind: process
Home: rule:parallelism-keep-going

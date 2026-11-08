# hook-allow probe (throwaway)

Owned by lane grant-reaches-lanes, Cockpit item 222. Delete the branch when the probe is read.
Question: in a cloud session in auto mode, does a project-scope PreToolUse `allow` skip the
auto-mode classifier, and does the user-scope guard hook's deny outrank it?

- `hook_allow_probe.py` emits `allow` only when `/tmp/probe-mode` holds `on` and the Bash call is
  one of two exact acts: write `{"permissions":{"allow":["Bash(true)"]}}` to the cwd
  `.claude/settings.local.json`, or `git -C ~/claude-settings-main switch --detach`.
- One line per Bash call goes to `/tmp/probe-hook.jsonl`. Read `permission_decision` in the transcript.

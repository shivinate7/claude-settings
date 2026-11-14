# A permission every session needs goes in the shared settings

## The question

Should a guard ask when a session adds an allow rule to a project's `settings.local.json`?

## The ruling

- Ruling: yes, an ask, never a refusal. The write stays allowed when the owner says yes at the prompt.
- The ask names the shared `settings.json` first. Its first remedy is a lane PR on claude-settings that puts the rule there.
- Only the allow rules the write adds are asked about. A rule already on disk asks nothing.
- Source: owner chat, 2026-11-13 20:16 CST, via the consultant. Triage grant, 2026-11-13 20:22 CST, ruling `own-reinstall-allow-a` (the triage ruling for this rule). Roadmap step `local-allow-goes-global` (the step that carries it).

## Mistake, harm and cost

- Mistake: an allowance that belongs to every session lands only in one project's local file.
- Harm: other sessions and repos keep hitting the same prompt.

Cost: It reads the write's content and the settings file on disk, up to 8 MiB, and resolves each write target's path once. A refusal appends to the guard log, as every refusal does. The rule itself starts no process. How often the ask fires is unmeasured.

## Code

Rule `local-allow-global` (the guard's name for this check) in hooks/guard.py, as write check 8a, in `is_local_settings_file` and `local_allow_added`. It covers the write tools only: Write, Edit and MultiEdit. A shell write is not read. Test: tests/guard/s21305-local-allow-global.py, the guard test for this rule. The ask prints no override line, since its remedy is a change to a shared file.

Kind: process
Home: hooks/guard.py

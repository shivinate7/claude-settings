# A state file that stops parsing is named at the call that broke it

## The ruling

Owner, 2026-11-06 11:38 CST: a self-caused mistake is a strong sign a guard is missing.

Incident, 2026-11-06: the coordinator ran `sed -i '$d'` on its feedback inbox. It deleted the
closing code fence. Only the Stop check in `hooks/feedback_guard.py` caught it, one turn later.

The mistake this stops: a Bash, Edit or Write call that leaves a state file unreadable. The harm:
later hooks and sessions read a broken inbox, handoff or JSON file, and the break is found turns
later, far from its cause.

## The check

`hooks/state_parse_check.py`, a PostToolUse hook on `Bash|PowerShell|Write|Edit|MultiEdit`. It
reads only the files the call names. When one breaks, it prints a PostToolUse `additionalContext`
that names the file, the line and the fault, so the model sees it at once. It never blocks and
never reverts.

- **Files it judges.**
  - Write, Edit, MultiEdit: the call's `file_path`, when it is a `*.json` or a `*.md` in the
    handoff folder.
  - Bash, PowerShell: the command is split with `shlex`. A path counts when it is a state file
    (the handoff folder, `settings*.json`, `roadmap/data/steps/*.json`), or a `*.json` in a write
    position: a `sed -i` operand, a `>` or `>>` target, or a `tee` argument. So `cat bad.json`
    says nothing.
  - The handoff folder comes from `precompact_handoff.handoff_path`, under `CLAUDE_CONFIG_DIR`,
    with either slash.
- **Faults.**
  - JSON: `json.loads` fails. The message gives line and column. The fence scan never runs on
    JSON, so a fence inside a JSON string is text.
  - Inbox (`*.inbox.md`): a fence left open. It uses the fence rule of `feedback_guard.parse`, the
    parser the Stop check reads, with no second copy and no turn-state write.
  - Other handoff `.md`: a fence left open, by the same rule.
  - Lost section, narrow: an Edit or MultiEdit on the inbox that lowers its count of block headers,
    and a handoff with no `Working premises` heading (`precompact_handoff._PREMISES_HEAD`).
- **No false alarm mid-edit.** An Edit or MultiEdit rebuilds the before-state from `old_string`
  and `new_string`. When the before-state was already broken, it says nothing. A missing file says
  nothing: a delete is not a break. A Write is judged as written.
- **Cost.** A shell pre-filter, after the `ci_wake.py` pattern, greps only `tool_input`. It exits
  unless the input names `.json` or the handoff folder, so most calls start no Python. Per call:
  one shell start. Per call that names a file: one Python start and one read per named file. It
  writes no file. `hooks/test_state_parse_check.py` proves the no-Python path.

## Covers

Step `inbox-fence-check` (the inbox fence check at the edit), proposed in decision
`mistake-means-missing-guard`. This check covers it.

## Note, not a debt

A path built at run time, such as `"$d/x.json"` or a Python script that writes JSON, is not seen
in a Bash call. Write and Edit see every path.

Kind: process
Home: hooks/state_parse_check.py

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
  - Bash, PowerShell: the command is read with the repo's one shell walk in `hooks/guard_core.py`
    (`strip_heredoc_bodies`, `split_segments`, `segment_tokens`, `dir_before_segment`), as the CI
    wake reads it. A heredoc body, a quoted `>` and a quoted `#` are text. A `cd <dir> &&` moves
    where a relative path resolves. A path counts only in a write position: a redirect target
    (`guard._redirect_targets`), a `tee` argument, a `sed -i` or `perl -i` operand, the last word of
    `mv` and `cp`, a `truncate` operand, or the target of `Set-Content`, `Add-Content`, `Out-File`.
    It must be a `*.json` or a `*.md` in the handoff folder. So `cat` of a broken file says
    nothing, even for a state file. A read changes nothing, and an alarm on each read would repeat
    until the file is fixed. The walk loads in a config folder that holds `hooks/` and no `lint/`,
    so the hook copies none of it.
  - The handoff folder comes from `precompact_handoff.handoff_path`, under `CLAUDE_CONFIG_DIR`,
    with either slash.
- **Faults.**
  - JSON: `json.loads` fails. The message gives line and column. The fence scan never runs on
    JSON, so a fence inside a JSON string is text. A file that fails only for a `//` or `/* */`
    comment (a `tsconfig.json`) or a UTF-8 byte order mark is fine. A redirect under a background
    `&` whose file is still empty is silent: the job has not written yet.
  - Inbox (`*.inbox.md`): a fence left open. It uses the fence rule of `feedback_guard.parse`, the
    parser the Stop check reads, with no second copy and no turn-state write.
  - Other handoff `.md`: a fence left open, by the rule of `feedback_guard.unfenced`: backticks
    or tildes, an info string allowed, at most three spaces of indent. The indent cap is a
    parameter, so `unfenced()` and the grant-word check keep their results. The inbox keeps
    `parse()`'s rule, so this check and the Stop check agree on the inbox.
  - One home for both loops: `hooks/fence_rule.py`, which `feedback_guard.py` calls from `parse` and
    `unfenced`. A leaf module, because `feedback_guard.py` imports `lint/_transcript.py` and the
    guard modules, and this hook must start in a config folder that holds `hooks/` and no `lint/`.
  - Lost section, narrow: an Edit or MultiEdit on the inbox that lowers its count of block headers,
    and a handoff with no `Working premises` heading (`precompact_handoff._premises_head`, read
    once per run, not once per candidate).
- **No false alarm mid-edit.** An Edit or MultiEdit rebuilds the before-state from `old_string`
  and `new_string`. Claude Code's PostToolUse input documents no before-content for Edit. When
  `new_string` appears more than once in the file, or is empty, each place it could have been
  gives one candidate. The check stays silent only when every candidate before-state was already
  broken. It caps the work (places times file size) before it builds any candidate, and stays
  silent past the cap. That silence holds for an Edit and a MultiEdit only. A Write, and a shell
  write such as an append, is judged as left, so it names a broken file even when the file was
  broken before. A missing file says nothing: a delete is not a break.
- **Cost.** The settings entry runs a shell pre-filter that greps only `tool_input`, as the
  CI wake entry does. It exits unless the input names `.json` or the handoff folder. A call that
  names neither starts no Python, which `test_state_parse_check.py` proves with a shim for `python3`
  that records each start. A call that names one starts at most one Python, which
  `test_state_parse_check.py` proves the same way. That Python makes at most one read per file it
  judges, and at most 20 files per call. It writes no file, which `test_state_parse_check.py`
  proves by listing the folders before and after. It logs nothing, so no log has a reader to name.

## Covers

Step `inbox-fence-check` (the inbox fence check at the edit), proposed in decision
`mistake-means-missing-guard`. This check covers it. Step `state-file-parse-check` builds it.

## Note, not a debt

Out of scope, so not seen in a Bash or PowerShell call: a path built at run time, such as
`"$d/x.json"`, a Python or Node script that writes JSON, `dd of=`, `cp -t` and `mv` into a
folder, `install`, `ln`, a download with `curl -o`, `sponge`, `find -exec sed -i`, and a command
inside `bash -c '...'` such as `bash -c 'sed -i ...'`. A JSONC file with a trailing comma is still
named: only comments are forgiven.
Write and Edit see every path. A background job that has begun to write a file leaves partial
text, which the check names as broken. `parse()` reads only the first fence in an inbox
block, so a lost closer of a second fence there is missed, by this check and the Stop check alike.

Known limits:

- A removal-only Edit on an already-broken file of 2000 chars or fewer can raise a false alarm.
  A made-up candidate place can repair the other fault.
- Silent by cap: a `new_string` with more than 64 places, and a MultiEdit with two or more
  removals on a file over about 5 KB.
- The pre-filter greps the literal `handoffs`. Renaming the folder in
  `precompact_handoff.handoff_path` needs the same change in `settings.json`.

Kind: process
Home: hooks/state_parse_check.py

# o5b, which hooks exist only to make sessions remember

Read-only audit. Checked: claude-settings main `b1e5a6d` (merge of batch PR #605), `settings.json` and
`hooks/`, plus the wired scripts outside `hooks/` (`lint/report_gate.py`, `janitor/`, `merge/`).
Nothing was deleted. Every retire or change pick is **Deferred: shiv's decision.**

## The finding that frames the table

Filing at once is two prose rules (`output-answer-has-a-home`, an answer to the owner gets a tracked
home; `building-never-drop-item-silently`, no item is dropped unsaid). Since Oct 26 it is also this
advisor project's habit (step c55). Neither is enforced by anything except two of the hooks below.

- These hooks run in local Claude Code sessions in every repo. The advisor project's habit does not
  reach those sessions, so it retires nothing there by itself.
- `outcomes-mechanize-rules` (each rule becomes a hook or check) points the other way: the hooks that
  make filing happen (`ruling_home`, `feedback_gate`) are filing at once's enforcement. Retiring them
  leaves the two rules as prose only.
- Filing at once can shrink what a session must remember (rulings, tasks), never in-flight state:
  branch, head, open PRs, pids and ports of servers, agents running. No file outside the session holds
  that, so the handoff hooks stay.
- guard.log fire counts (needed by `building-guard-needs-incident` for a cull) live on the owner's
  machines. Unknown here.

## Memory-aid hooks

| Hook | What it makes a session remember | Filing at once covers it? | Pick |
|---|---|---|---|
| `ruling_home.py` (Stop) | A ruling written to auto-memory must name a tracked home (`home:` line), so memory is never its only home | No. It is the enforcement of filing at once for memory writes | **Keep.** Retiring it turns `output-answer-has-a-home` back into prose |
| `feedback_gate.py` (Stop) + `local_time.py` fb capture + `feedback_judge.py` (child) | Every message of an owner `fb` burst is jotted as kinded items with a home before the turn ends | Partly. Jotting each item at once is filing at once. But the homes it accepts are mostly the handoff (ruling, task, standing), which is session memory | **Keep, change Deferred.** Re-point `task` and `ruling` homes to a tracked file (repo todo, a decision record), and check each closed item against that home, as step o5b's "why" asks. Then the handoff check for those kinds can go |
| `precompact_handoff.py` --nudge (Stop) | Rewrite the handoff at each context checkpoint | Partly. If rulings and tasks are filed at once, the handoff shrinks to in-flight state, which no file holds | **Keep.** Deferred option: trim the handoff template's "Rulings with NO HOME YET" and "rulings with a home" sections once filing is enforced |
| `precompact_handoff.py` PreCompact digest, --reorient, --session-end | Carry the transcript tail and the old handoff across compaction, /clear and fork | No. Compaction loss is of in-flight state | **Keep** |
| `reread_check.py` (PostCompact, PreToolUse Read, Stop) | Re-read the handoff after a compaction before ending a turn | No. Same reason | **Keep** |
| `agent_brief.py` (SubagentStart) | Gives each spawned agent the standing rules (no stash, push form, trailer, report cap) so a brief cannot forget a line | No. It delivers rules to a fresh context, it does not file items | **Keep** |
| `daily_note.py` (SessionStart, startup) | Once a day, names guard crashes in guard.log | No. It is monitoring with a named reader | **Keep** |
| `session_start.sh` (SessionStart) | Which checkout and branch the session stands in, and stale clones or disarmed sweeps | No. It reads live state, it does not recall items | **Keep** |
| `ci_wake.py` (PostToolUse, async) | Wakes the session when CI ends after `gh pr ready` | No. It replaces polling, not memory | **Keep** |
| `question_outcome.py` | Nothing: a stub, not wired in `settings.json` | n/a | **Already retiring.** `lint/check_hook_stubs.py` dates its removal |

## Hooks that are not memory aids

These guard acts, judge text, or clean up. None of them asks a session to remember. Out of scope for a
filing-at-once retire.

| Hook | What it does | Pick |
|---|---|---|
| `guard.py` and `guard_*.py`, `override_pass.py`, `rm_prompt_answer.py` | Refuse or ask on unsafe shell, git, kill, env and edit acts | Keep (not memory) |
| `config_watch.py` | Reverts an unasked subagent model cap change | Keep (not memory) |
| `stall_watch.py` | Reports a background job with no output for 300 s | Keep (not memory) |
| `lint/report_gate.py` | Report labels after a commit, push or merge | Keep (not memory) |
| `reply_judge.py`, `prose_judge.py`, the AskUserQuestion, Agent and SendMessage prompt hooks, `sendmessage_state.py` | Judge text or a spawn against rules | Keep (not memory) |
| `sim_boot_record.py`, `janitor/session_end_sweep.py`, `janitor/agent_end_reap.py`, `merge/install_from_main.sh` | Record and clean up simulators, worktrees and processes; refresh the install | Keep (not memory) |
| `local_time.py` time line and `override` pass | Central time and the owner's one-act pass | Keep (not memory) |
| `decision_watch.py`, `git_reads.py` | Libraries (one model caller, shared git reads), not wired | n/a |

## Result

No hook exists only to make a session remember something that filing at once replaces. The two
closest (`feedback_gate`, the handoff's rulings sections) are better changed than retired: point their
homes at tracked files so filing at once is enforced, not trusted. Deferred: shiv's decision.

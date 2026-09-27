# Which start shapes outlive the agent on Windows

This entry is step 1 of a plan. It measures. It fixes nothing. The owner
said that dev servers from finished subagents keep running and pile up.
The goal of the later fix: when an agent or its worktree ends, every
process it started under its checkout stops, and nothing else stops.

Machine: Windows 11, Git Bash, Python 3.14. Date: 2026-09-26. A builder
subagent ran each shape in its own worktree, one port each. The cwd of
each server was that worktree. Governing records:
decisions/unattended-sweep-stops-proven-orphans.md and
decisions/liveness-read-is-platform-specific-and-unreadable-is-not-death.md.

## The orchestrator's first data point

A Haiku subagent started `python -m http.server 8765` with
`run_in_background: true`. It answered 200. After the agent finished,
nothing listened on port 8765. So the harness stops a tracked background
task at agent end. The leak comes from a shape the harness does not track.

## MEASURED table

"Survives" means that the server still listened after its Bash call or
background task ended. "Sweep" is the verdict of a read-only run,
`python janitor/sweep.py C:/Users/ShivamSemwal/Clones/claude-settings`.
"Guard" is the verdict of the `detached-launch` rule in hooks/guard.py,
the installed copy, before the call ran.

| Shape | Guard | Survives call end | Parent chain (Windows) | Sweep |
|---|---|---|---|---|
| `cmd &` then another line, foreground Bash | allowed | yes | python <- bash stub (alive) <- tool shell (dead) | KEEP, not-orphaned |
| `cmd &` as the last token, foreground Bash | denied | not run | - | - |
| `nohup cmd &` | denied | not run | - | - |
| `setsid` | not present in Git Bash | - | - | - |
| `cmd &` then `disown` on the next line | allowed | yes | python <- bash stub (alive) <- tool shell (dead) | KEEP, not-orphaned |
| `( cmd & )`, the macOS incident shape | denied | not run | - | - |
| `sh -c 'cmd &'`, a parent that exits | allowed | yes | python <- sh stub (alive) <- tool shell (dead) | KEEP, not-orphaned |
| `$p = Start-Process ... -PassThru`, PowerShell | allowed | yes | python <- PowerShell tool shell (dead) | KEEP, live-session |
| `run_in_background: true`, then TaskStop, Bash | allowed | no | python <- bash <- bash <- bash <- claude.exe | not listening |
| `run_in_background: true`, then TaskStop, PowerShell | allowed | no | python <- powershell <- cmd <- claude.exe | not listening |
| `cmd &` inside a `run_in_background: true` call that exits | allowed | yes | python <- bash stub (alive) <- task shell (dead) | KEEP, not-orphaned |

All five survivors had the worktree as cwd. The builder stopped each one
by its own pid. Then `netstat -ano` showed no listener on 8770 to 8790,
and no stub pid was left.

## What the table shows

1. **The harness tracks only the tool shell.** Each survivor has a dead
   tool shell or task shell as its ancestor. So no walk down from
   `claude.exe` reaches it. A tree kill at agent end cannot find it.
2. **The MSYS stub hides the orphan.** When Git Bash starts a native
   program in the background, a copy of `bash.exe` (or `sh.exe`) stays
   alive as the Windows parent. It waits for the child. So
   `sweep.is_orphan` reads a live parent, created first, and answers
   "not orphaned". The sweep keeps these servers forever. The stub's own
   parent is dead. The sweep reads only the listener pid, not the stub.
3. **The sweep matches the primary checkout first.** Agent worktrees sit
   under `.claude/worktrees/` inside the primary checkout.
   `_matching_checkout` returns the first path that contains the cwd, and
   `parse_worktree_list` names the primary first. So every listener in an
   agent worktree is judged against the primary checkout. The
   orchestrator's own session record has its cwd there. So
   `worktree_live_session` answers "live", and the orphan from
   `Start-Process` is kept as live-session.
4. **No session record names a subagent.** The session directory held six
   records. None had a subagent's worktree as cwd. For this worktree,
   `guard.worktree_live_session` answered False while this subagent still
   ran. If finding 3 were fixed to take the deepest match, the sweep would
   see a running subagent as not live.
5. **The guard misses three shapes.** `detached-launch` denies a bare
   trailing `&`, `nohup`, and `( cmd & )`. It allowed `cmd &` followed by
   another line, `disown` on its own line, and `&` inside `sh -c '...'`.
   A replay of each command through hooks/guard.py gave the same verdicts.
   Its tests cover `cmd & disown` on one line only.
6. **`Start-Process -PassThru` is allowed by design.** The session gets
   the pid. The process still outlives the call, and nothing stops it
   unless the session remembers the pid.

## Which shapes need a real agent-end fixture

This builder cannot end itself and then look. The table proves survival
at call end and at TaskStop, not at agent end. These shapes need the
orchestrator's fixture, one per shape:

- `cmd &` followed by another line, foreground Bash
- `cmd &` then `disown` on the next line
- `sh -c 'cmd &'`
- `$p = Start-Process ... -PassThru`
- `cmd &` inside a `run_in_background: true` call

Expected, from finding 1: all five survive agent end. This is unmeasured.
The fixture also must record whether the harness removes a worktree that
still holds a running process. The sweep's pre-check refuses that
removal, but the harness does not run the sweep.

## Hook payloads

Sources: the Claude Code hooks reference,
https://code.claude.com/docs/en/hooks, read through a fetch summary on
2026-09-26. This is from docs. It is unmeasured on this machine.

- **Common fields, every event:** `session_id`, `transcript_path`, `cwd`,
  `hook_event_name`. Inside a subagent, also `agent_id` and `agent_type`.
  The docs say that `cwd` follows Claude into a worktree.
- **SubagentStop:** `agent_id`, `agent_type`, `agent_transcript_path`,
  `last_assistant_message`, plus `cwd`. No field names the worktree. The
  docs do not say whether `cwd` is the agent's worktree or the parent's.
  Unmeasured. The fixture must log one payload.
- **WorktreeRemove:** `worktree_path` and `worktree_name`, plus `cwd`. The
  event table says that it fires "when a subagent finishes". So
  `worktree_path` names the checkout to clean. Unmeasured.
- **SubagentStart:** `agent_id`, `agent_type`, `cwd`. It could record the
  agent's worktree at start. Unmeasured.

## Compaction

- **Does a server survive a compaction?** Compaction shrinks the context.
  It does not end the `claude.exe` process. So a tracked background task
  and every untracked survivor above keep running. Reasoned from the
  process tree above. Unmeasured, because a subagent cannot start a
  compaction.
- **Does a hook fire?** Yes. The docs list `PreCompact` ("Before context
  compaction") and `PostCompact` ("After context compaction completes").
  Both match on `manual` or `auto`. From docs, unmeasured.
- **Payload:** the common fields, plus the manual-or-auto field. One
  summary names that field `compact_reason`. Secondary sources name it
  `trigger`, with `custom_instructions` for a manual compaction. These
  disagree. A hook must log one real payload before it reads that field.
  Per a secondary source, PostCompact stdout goes back into context. So a
  PostCompact hook could print the pids and ports the session started.
  Unmeasured.
- **Owner's concern:** after compaction the session can forget which pids
  and ports it started. Nothing on disk records them today. The harness
  task list covers only `run_in_background` tasks.

Secondary sources:
https://www.developersdigest.tech/guides/pre-post-compact-hook and
https://github.com/anthropics/claude-code/issues/17237.

## What reopens it

A new Claude Code release that changes how tasks end or what hooks carry.
A real agent-end fixture that disagrees with the expected result above.

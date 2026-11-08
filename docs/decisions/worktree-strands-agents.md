# An EnterWorktree waits for the session's agents

## The ruling

An EnterWorktree call from the main session is refused while an agent of this session runs. `hooks/guard.py` refuses it with `worktree-strands-agents`. The refusal names each running agent id. It gives two remedies: wait for each agent's completion notice, or enter the worktree before you spawn agents. An owner override lifts it, and it is not in `never_lifted`: the owner may mean to enter now.

The call is the main session's when its payload has no `agent_id`. An agent's own call is not judged here. The rule covers EnterWorktree only. ExitWorktree is not judged.

## How a running agent is read

`stall_watch.open_agents` reads the parent transcript (`transcript_path`). It sits beside `scan_jobs`, the reader of the session's background commands, and reuses `closed_by_notice` and `stopped_ids`. There is no second reader.

- An agent opens on the answer to its spawn: a user line whose `toolUseResult` has `status` `async_launched` and an `agentId`.
- An agent reopens on the answer to a SendMessage whose `toolUseResult` has a `resumedAgentId`.
- An agent closes on a terminal task notice for its id (completed, failed, killed or stopped). Only a record whose text starts with the tag counts as a notice. The record is a user record, a queued attachment or a queue-operation enqueue line. A hand-back that quotes a notice mid-text closes nothing. A notice whose summary says the agent "is waiting on its own background work" closes nothing: the agent may resume.
- An agent closes on the result of a TaskStop call, read by `stopped_ids`.

Only lines that hold one of the keys are parsed. An unreadable file, a missing transcript and a failed import pass.

## The mistake

Twice on 2026-11-08 the orchestrator entered a session worktree while its background agents ran. Each agent was cut off from its own worktree, and `worktree-home` refused its next call.

## The harm

The agent's round is lost, and the orchestrator must respawn it. A respawn costs a full round, and the cut-off agent may hold uncommitted work.

## Cost

One transcript read per EnterWorktree call, a line scan that parses only lines holding a key. One more guard process start per EnterWorktree, as the matcher in `settings.json` now lists the tool. No new process, no timer, no file written beyond the refusal's one guard.log line.

## Accepted limits

The guard stops Claude's mistakes, not an attacker (`guard-guards-mistakes-only`).

- A foreground agent is not read. Its spawn answer is its end, and the main session is blocked while it runs.
- A `cd` into another checkout is not judged here. Rule `other-checkout` already refuses it.
- The TaskStop result shape is read through `stopped_ids`, the shape `stall_watch` already pins: a result that starts `Successfully stopped task: <id>`. It is unmeasured on a live sample.
- An agent that ends with no notice in the transcript (a crashed session, a notice that never arrived) reads as running, and the refusal stays until an override.

## Measure

`MUTATE_ONLY=worktree-strands-agents: hooks/test_guard.py`: 4 refusals and 7 passes. `hooks/mutate_guard.py` carries one mutant per edge those cases pin, labelled `worktree-strands-agents:`.

Kind: process
Home: hooks/guard.py

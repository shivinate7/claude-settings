# A lane messages its agents by the name given at spawn, never by a bare id

Kind: process
Home: hooks/guard_merge.py

## The mistake

- 2026-11-08 08:12 CST. The lane `notes-fix-page` sent three overlap lists to the wrong agents. It addressed each agent by its bare agent id. An id is an opaque string, so a mix-up reads as a normal send.
- The harm: a list reached an agent that was not meant to build it, so work was repeated or lost, and the lane learned of it only from the replies.

## The rule

Guard rule `agent-name-on-spawn`, judged only in a session proved a lane (its own record tags `cs-build:lane`, the one lane test `_own_tier_proved`). Calls with an `agent_id` pass.

- A built-in `SendMessage` whose `to` is the agent id of a spawn in the transcript, one trailing ` [<ref>]` stripped:
  - deny when that spawn had a non-blank `name`. The reason says to send to the name given at spawn. It never carries the agent id or the name (rule `git-remedy-never-names-target`).
  - ask when that spawn had no name, since no name can address it.
- An Agent or Task spawn with no `name`, or a blank one: deny. The reason says to give the spawn a name, so later messages address it by name.
- A send to `main`, to a name, or to an id no spawn holds passes. The remote `send_message` is not judged: it names sessions. A missing or unreadable transcript passes.

## Evidence

- Measured, Claude Code 2.1.319, probe 2026-11-08 08:19 CST: the Agent tool accepts `name` even where its listed schema omits it. The remedy is therefore one a lane can follow.
- The spawn and agent-id read is one helper, `_spawn_reads` in `hooks/guard_merge.py`. This rule and `resume-finished-reviewer` both call it (rule `building-one-home-per-capability`).

## Cost

- No new read of its own. A send shares the one transcript read per judged call (`_main_records`).
- The lane proof reads the transcript once. It runs for a built-in `SendMessage` and for an Agent or Task spawn with no name, so it costs one read per nameless main-session spawn and one per built-in send. A named spawn costs nothing.
- No subprocess, no network, no file written.

## Limits

- A spawn made by the Workflow tool is no Agent or Task call in the transcript, so a send to it is never judged.
- A send to an id the transcript does not hold passes. The guard cannot tell a typo from an agent started by another session.
- A transcript record of the wrong shape passes with no ask, unlike `resume-finished-reviewer`: an ask there would block a lane's sends on a read the guard cannot place.
- Round 3 weighs deny against ask for a bare-id send to a spawn that had no name. The rule asks today, so a lane can confirm an id it has no name for.

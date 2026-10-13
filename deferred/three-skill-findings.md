# Three skills have findings that wait

**What waits.** Fixes for three skills. Each line names what is wrong and where the skill
shows it. "Now" gives the current text.

- **compliance-check.**
  - Mark a rule parent-covered only if live settings match and `guard.log` shows recent
    verdicts. Now: `SKILL.md` line 24 marks it with no such check.
  - Probes use `python`, not `python3`. Now: `probes.md` lines 10 to 13 use `python3`.
  - Probe branch protection against the `requiredChecks` in `stamp.json`. Now: `probes.md`
    line 35 reads branch protection only.
  - Cite probe: cover the slug form, D plus a backtick slug. Now: `probes.md` line 44 matches
    D plus digits only.
  - Waiter probe: loops only. Now: `probes.md` line 40 greps `sleep`.
- **fresh-prose.**
  - Hook-injected rule copies need a source check. Now: `SKILL.md` names no source check.
  - Near-miss cites need a check. Now: `SKILL.md` names no check for cites.
  - Rewrite superseded entries in place. Now: `SKILL.md` says nothing on superseded text.
- **design-review.**
  - If a screen did not render, give an unknown verdict. Now: step 7 gives a verdict per
    screen, with no unknown case.
  - Use a headless browser, and announce before a window lands on the screen. Now: `SKILL.md`
    names no browser and no announce.
  - Spawn Reviewer B with agentType `reviewer`. Now: line 30 gives Reviewer B no agentType.
    Reviewer A has one, at line 25.
  - Add a three-round cap. Now: `SKILL.md` names no cap.

**Why it waits.** The owner ruled that these findings wait, on 2026-10-12/13.

**What keeps it from being lost.** This file.

**Trigger.** When a skill next changes, land its findings in that skill's file. Then delete them
here.

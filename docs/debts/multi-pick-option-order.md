# A multi pick out of option order keeps Take my pick

- **What.** On a `multi` item that is not `ranked`, ticks keep option order, but `pick` may be in any
  order. With `pick: ["c", "a"]`, ticking A and C leaves "Take my pick" shown. Pressing it saves
  `["c", "a"]`, while hand ticks save `["a", "c"]`. Design review round 3 of step c135 failed the
  Take my pick state on this.
- **Where.** `skills/waiting-page/page.html`, `pickKeys` and `pickChoice`, and the hide check that
  calls `sameList`. `skills/waiting-page/SKILL.md`, "The database", which lets an unranked `pick`
  be in any order.
- **Decision.** none
- **Retire.** `pickKeys` and `pickChoice` put an unranked `pick` in option order. A page test with
  `pick: ["c", "a"]` that ticks A and C shows Take my pick hidden, red on the old page.

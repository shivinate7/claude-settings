# This repo is claude-settings

This file loads only in sessions on this repo. The root `CLAUDE.md` loads in every repo.

This repo defines how Shivam works in every repo. Its rules, hooks, skills, agents and
output style load in each session on each repo.

- Judge each change by its effect on sessions in other repos, not in this repo only.
- When a session in another repo meets a gap in how Shivam works, the fix belongs here. A gap
  that only one repo has belongs in that repo.
- An edit, a review or a question here sets the pattern every session copies. Do each one to
  that standard.

## Standing grants

- **Acts the cloud refuses** (owner, 2026-10-30 16:20 CDT; changed by Cockpit item 219 a,
  2026-11-04 17:44 CST, and its follow-up pick a, 17:55 CST; until withdrawn). When any repo's
  coordinator asks, a session on Shivam's computer may do two acts. It may set branch protection to
  the shared form, with only the all-jobs-passed check required. It may delete a branch whose last
  commit is on the default branch or on an archive branch. A request for any other act needs his word.
- **Relayed yes** (owner, 2026-11-07 13:10 CST, coordinator-reported; typed in lane relayed-yes-allow,
  13:19 CST). An owner yes to merge a named pull request, which a coordinator (tag `cs-build:coordinator`)
  relays to its batch runner, is the owner's grant for that merge. The batch runner merges it with the merge tool,
  under every merge check (`settings.json` `autoMode.allow`, entry "Relayed Merge Yes"; decision
  `auto-mode-owner-acts`). A relayed yes covers no other act and no other session.

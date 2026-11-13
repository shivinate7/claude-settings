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
  coordinator asks, a session on Shivam's computer may do three acts. It may move main to the shared
  ruleset (owner, 2026-11-11 16:43 CST, ruling r): only the all-jobs-passed check required, and
  deletion and force-push of main blocked. The ruleset may also let the repository admin role skip
  the checks on pull requests only (owner, 16:49 CST, "yes with bypass"; coordinator-relayed). It may remove main's old branch protection
  only after step merge-reads-ruleset (the merge tool reads main's ruleset) has merged, and only once
  the ruleset is on; the grant covers no removal before that step lands. (restart-plan R45, ruling c, owner 19:49 CST Nov 11; the plan says the step lands before any sweep removes old protection) It may delete a branch whose last commit is on the default branch or on an archive
  branch. A request for any other act needs his word. Sources: decision `main-branch-protection` (ruling r, the shared ruleset; the admin bypass; ruling c, the merge tool reads rulesets); branch deletes: Cockpit item 219 a (2026-11-04 17:44 CST) and its pick a (17:55 CST), named in this bullet's header.
- **Relayed yes** (owner, 2026-11-07 13:10 CST, coordinator-reported; typed in lane relayed-yes-allow,
  13:19 CST). An owner yes to merge a named pull request, which a coordinator (tag `cs-build:coordinator`)
  relays to its batch runner, is the owner's grant for that merge. The batch runner merges it with the merge tool,
  under every merge check (`settings.json` `autoMode.allow`, entry "Relayed Merge Yes"; decision
  `auto-mode-owner-acts`). A relayed yes covers no other act and no other session.
- **Main merge into handed-in branches** (owner, 2026-11-13 13:12 CST; until withdrawn). The batch runner
  may push a plain merge of main into a handed-in PR branch when no lane has pushed there in the last 2 hours.
  No rebase, no force push. A conflict that changes behaviour goes back to the coordinator. Each new head gets
  a fix verifier and a fresh review log. Source: decision `standing-merge-grant`.
- **Overlaps between lane branches** (owner, 2026-11-13 14:17 CST, typed in runner 10's chat: "you have a
  standing grant to act on overlaps by me, owner"). The batch runner may act on overlaps between lane branches.
  Runner 10 reads that as a plain merge of one lane's head into another lane's branch, under the limits of the
  bullet above. The owner has not confirmed that reading. Source: decision `standing-merge-grant`.

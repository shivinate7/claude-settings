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
  ruleset (owner, 2026-11-11 16:43 CST, ruling r): no status check required (owner, 2026-11-15 19:08
  CST, ruling `own-all-jobs-passed-removed`: "all jobs passed has been removed as a status requirement"),
  and deletion and force-push of main blocked. The ruleset may also let the repository admin role skip
  the checks on pull requests only (owner, 16:49 CST, "yes with bypass"; coordinator-relayed). It may remove main's old branch protection
  only after step merge-reads-ruleset (the merge tool reads main's ruleset) has merged, and only once
  the ruleset is on; the grant covers no removal before that step lands. (restart-plan R45, ruling c, owner 19:49 CST Nov 11; the plan says the step lands before any sweep removes old protection) It may delete a branch whose last commit is on the default branch or on an archive
  branch. A request for any other act needs his word. Sources: decision `main-branch-protection` (ruling r, the shared ruleset; the admin bypass; ruling c, the merge tool reads rulesets); branch deletes: Cockpit item 219 a (2026-11-04 17:44 CST) and its pick a (17:55 CST), named in this bullet's header.
- **Relayed yes** (owner, 2026-11-07 13:10 CST, coordinator-reported; typed in lane relayed-yes-allow,
  13:19 CST). An owner yes to merge a named pull request, which a coordinator (tag `cs-build:coordinator`)
  relays to its batch runner, is the owner's grant for that merge. The batch runner merges it with the merge tool,
  under every merge check (`settings.json` `autoMode.allow`, entry "Relayed Merge Yes"; decision
  `auto-mode-owner-acts`). A relayed yes covers no other act and no other session. The owner's
  consultant (tag `cs-build:consultant`) may also relay a yes to a batch runner (entry "Consultant
  Relayed Merge Yes"). The entry has two paths. Direct: the owner typed `i want the allow rule` in batch
  runner 12's chat at 11:18 CST on 2026-11-15, which covers a consultant relay to the batch runner.
  Through triage: the consultant relayed at 11:31 CST, through the coordinator, that the owner typed "a" at
  11:29 CST. The incident path ran from the owner to the consultant, to triage, to the runner.
  The owner's own typed words do not name the triage hop. A yes that started at triage with no consultant is
  not covered. The yes binds to the head the pull request had when the consultant relayed it. That binding
  rests on the runner passing that head as `--head`, and on the classifier reading the chat. The merge tool
  accepts a live head that equals the `--head` passed, or sits on it with only a Record-claim commit,
  its revert, a page-only commit, or, on the default branch, clean merges of main. It does not check that `--head` against the relay.
  `relayed_head_holds` in `merge/merge.py` reads no review record.
- **Lane draft PR** (owner, 2026-11-12 17:19 CST; changed by owner, 12:58 CST Nov 16, "No now everyone merges",
  and 13:06 CST Nov 20, "let's lock that"; changed by owner, 14:46 CST Nov 23, 2026, ruling Q4 a; ruling Q2). Any lane that a coordinator or another lane started may open its own draft PR. It marks that PR
  ready after its review, and again after any return to draft, by the merge tool, and never marks another PR ready. It merges on whichever proof of its head arrives first: a green `all-jobs-passed` rollup, or a local lane-lint PASS. The proof may sit under the merge tool's own page-only commits or clean merges of main; the live head's own run must not be red or unknown. Source:
  decision `draft-until-reviewed` (every PR opens as a draft).
- **Main merge into handed-in branches** (owner, 2026-11-13 13:12 CST; until withdrawn; changed by owner,
  23:40 CST, waiting-page item 806 d; changed by owner, 14:46 CST Nov 23, 2026, ruling Q4 a). The batch runner may push a plain merge of main into a handed-in draft PR, with no clock rule. A ready PR takes no push: it returns to draft first, and main merges into it only on a conflict. A lane that pushes again to a handed-in draft branch says so first. No rebase,
  no force push. A conflict that changes behaviour goes back to the coordinator. Each new head gets a fix
  verifier and a fresh review log, except a clean merge of main, which takes none (decision `pr-review-record`,
  the review record). Source: decision `standing-merge-grant`.
- **Overlaps between lane branches** (owner, 2026-11-13 14:17 CST, typed in runner 10's chat: "you have a
  standing grant to act on overlaps by me, owner"). The batch runner may act on overlaps between lane branches.
  Runner 10 reads that as a plain merge of one lane's head into another lane's branch, under the limits of the
  bullet above. The owner has not confirmed that reading. Source: decision `standing-merge-grant`.
- **Merge in any repo** (owner, 2026-11-15 23:43 CST): any session may merge a PR in any of the owner's repos with the merge tool, under every merge check. The grant covers that wording only (ruling own-913-a-merge-any-repo-grant-line, owner, 2026-11-16 13:34 CST).

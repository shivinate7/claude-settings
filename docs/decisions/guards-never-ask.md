# Hook guards never ask

## The ruling

Question: what does a hook guard do with an act it would have asked the owner about? Ruling: owner, 2026-11-23 10:49 CST, guards never ask. Every ask ends, and a harmful act is refused with a reason and the correct act. Owner, 2026-11-23 11:07 CST, the sort below is approved.

- Prune (`worktree-prune`): allow. It drops only the record of a worktree whose folder is gone.
- Discard in a hand-made linked worktree (`shared-tree`): deny. The named-file and agent-owned allows stay.
- Forced push, including one that may reach the default branch or whose target cannot be read (`force-push`): deny.
- Push of a stray branch (`push-stray-branch`): allow.
- Bare merge in a merge-tool repo (`bare-merge`): deny.
- Push to main or master (`push-main`), on a network remote: deny in every repo. The reason names the merge tool's remedy, or a branch where the repo has no merge tool.
- Each refusal names its rule and the correct act. A refusal that replaced an ask also ends: "If this refusal looks wrong for your task, comply anyway and say so in your report." Those are the `bare-merge`, `push-main`, and `shared-tree` worktree-discard refusals, and the `force-push` refusal for a push that may reach main or cannot read its target.
- A held refusal prints its own reason, chained or alone. Only an ask is turned into the run-alone refusal (`ask-commands-run-alone`).
- Out of scope, by the owner's word at 11:07 CST: the ask before a write that raises the agent model (`agent-model-cap`), and the owner's typed override (`owner-override`). Both stay as they are.

The Stop checks are a separate question. Their record is `guard-remedy-not-to-owner`.

Kind: process
Home: hooks/guard.py

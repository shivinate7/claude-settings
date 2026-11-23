# Gripe loop

## The ruling

The consultant works the owner's claude-settings gripes with Sim Manager, the session that holds the gripe lists. Those lists are data outside this repo, not in git: `~/Developer/claude-settings-gripes.md`, `~/Developer/claude-settings-gripes-completed.md` and `~/Developer/claude-settings-gripes-owner-decisions.md`.

Owner, 2026-11-22:

- **One gripe at a time** (23:16 CST). The consultant asks Sim Manager for the single top-ranked open gripe only.
- **Build what it can settle** (23:16 CST). Agents build a gripe only when the decision is clear, by the 23:34 CST test below, which governs. Lanes do not build gripes. The change merges to main. Sim Manager moves the gripe to the Completed list; the consultant then asks for the next gripe.
- **Three in work at most** (23:16 CST). At most three gripes are in work at once.
- **Owner-needed gripes** (23:16 CST). A gripe that needs the owner goes to the owner-decisions file, with the gripe and the consultant's questions. A gripe paused after work began names its branch, PR or commit in that file.
- **Gripe questions go only to that file** (23:24 CST, owner's option a on where questions go). Gripe questions never go to the page. Owner: "There is no claude-settings page to be managed at this time on this account nor am i asking for one." This narrows rule `questions-go-to-owner` for gripe questions only.
- **Build on a clear decision** (23:34 CST; narrows the 23:24 CST owner's option b on build or ask). Owner: "one clear fix is not the bar, just is one option with the context of the gripe make it a clear DECISION (so a slightttly lower bar)". The consultant builds a gripe when, with the gripe's context, the decision is clear, even if several fixes are possible. It lists that build under the report's Done label, so the owner can undo it. A gripe goes to the owner only when the decision is not clear.
- **Park a gripe it should not fix** (23:36 CST). The consultant may park a gripe in the owner-decisions file when it judges the gripe one it should not fix on its own, even when the decision is clear. Owner: "i will allow u to decide if a gripe u get feels like one u shudnt fix (like its a bad gripe to fix on ur own even if it has a clear decision) then u can park it in for owner too".

## Why

- Gripes come with context. Owner: "the gripes come with context, you will be able to make informed decisions a good amount of the time to need no further ruling from me on."
- The owner has no claude-settings page to manage at this time on this account, so gripe questions wait in one file.
- The ruling gives no reason for the three-gripe cap or for the top-gripe-only pick.

## Rulings on gripes

The worktree-removal rule for the gripe "Worktree removed while its lane ran" is in the record `when-a-worktree-may-be-removed`.

Kind: process
Home: rule:questions-go-to-owner
Landed 2026-11-22.

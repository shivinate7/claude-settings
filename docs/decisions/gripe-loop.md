# Gripe loop

## The ruling

The consultant works the owner's claude-settings gripes with Sim Manager, the session that holds the gripe lists. Those lists are data outside this repo, not in git: `~/Developer/claude-settings-gripes.md`, `~/Developer/claude-settings-gripes-completed.md` and `~/Developer/claude-settings-gripes-owner-decisions.md`.

Owner, 2026-11-22:

- **One gripe at a time** (23:16 CST). The consultant asks Sim Manager for the single top-ranked open gripe only.
- **Build what it can settle** (23:16 CST). Agents build a gripe the consultant can settle. Lanes do not. The change merges to main. Then the consultant tells Sim Manager to move the gripe to the Completed list, and asks for the next gripe.
- **Three in work at most** (23:16 CST). At most three gripes are in work at once.
- **Owner-needed gripes** (23:16 CST). A gripe that needs the owner goes to the owner-decisions file, with the gripe and the consultant's questions. A gripe paused after work began names its branch, PR or commit in that file.
- **Gripe questions go only to that file** (23:24 CST, owner's option a on where questions go). Gripe questions never go to the waiting page. Owner: "There is no claude-settings page to be managed at this time on this account nor am i asking for one." This narrows rule `questions-go-to-owner` for gripe questions only.
- **Build on one clear recommendation** (23:24 CST, owner's option b on build or ask). The consultant builds a gripe when it can give one clear recommendation. It lists that build under the report's Done label, so the owner can undo it. A gripe goes to the owner only when no clear recommendation exists.

## Why

- Gripes come with context. Owner: "the gripes come with context, you will be able to make informed decisions a good amount of the time to need no further ruling from me on."
- The owner has no claude-settings page to manage, so gripe questions wait in one file.
- The ruling gives no reason for the three-gripe cap or for the top-gripe-only pick.

## Rulings on gripes

Owner, 2026-11-22 23:25 CST, on the gripe "Worktree removed while its lane ran":

- An idle worktree that the sweep removes automatically is fine. Its work is committed, so nothing is lost. Owner: "sometimes worktrees are auto swept on idling and thats usually okay bc everything is always committed and so nothing is actually lost".
- The harms to stop: removing a worktree while a process runs inside it, and removing work that exists only uncommitted in the tree.

Kind: process
Home: rule:questions-go-to-owner
Landed 2026-11-22.

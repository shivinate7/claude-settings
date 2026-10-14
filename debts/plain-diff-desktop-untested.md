# The plain-diff pane and turn-text match are untested in the desktop app

- **What.** The pane draw, and the turn-text match against a real `$.session.messages()`, are untested in the desktop app. A turn that edits `src/app.ts` and names it in its text is an example. The owner tries `/plain-diff` and judges the notes.
- **Where.** The pane draw and the turn-text match in `mods/plain-diff/hooks/register.mjs`.
- **Decision.** `plain-diff-mod-limits` (plain-diff sends a diff to a model only past the secret filter).
- **Retire.** The pane and the turn-text match are run in the desktop app, and the result is recorded in the decision.

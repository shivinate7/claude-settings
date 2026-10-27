# waiting-page-final

From the c100 lane (the waiting page's final look), PR #682, head cd090b5. Unfiled items for triage:

- c100 follow-up, new step: review-page standard items 2, 3 and 5 are not built in the template: a coloured edge marks what differs between options, "open this state in the full mockup" deep-links to a named state, and combined answers such as "A+B". The design reviewer ruled them out of c100's scope (not in the mockup's "What the template needs" list). Source: roadmap/outbox/waiting-page-design.md.
- c100 note: the "Too late to undo" bar note reads "No. 1 and No. 2 and No. 3" for 3 or more items. It should read "No. 1, No. 2 and No. 3". One line in page.html `undoSend`.
- c100 note: when an Undo delete fails at No. N, the bar note names only No. N, not the items after it that also stay sent. Rare.
- c100 note: a failed receipt delete during Undo leaves the old receipt, which can show on a re-sent answer. Rare.
- c100 note: the builder hid empty tiers; the mockup shows "Nothing here right now". The design reviewer ruled it in scope.
- c100 after merge: republish each repo's live waiting page, one repo at a time, home-app first (build hand-off 2026-10-27c). Saved answers survive, since the store keys are unchanged.

# A mockup's only copy is the waiting page

- **What.** The waiting page holds the only copy of a mockup's source. "Add a design" pastes the mockup HTML into the page's `designData` block, and no repo design folder gets the file. The record-branch copy may hold it too, in `page/designData.json`. Unmeasured.
- **Where.** `skills/waiting-page/SKILL.md`: "Add a design", step 3.
- **Decision.** `waiting-data-in-repo` (git is each artifact's home).
- **Retire.** "Add a design" finds the mockup's file on origin before it writes the item. Open work: branch `mockup-homes` (the account-switch lane) on origin. It holds decision `mockup-home`, unreviewed, which judges path shape only. Check: none yet.

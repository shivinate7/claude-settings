# A mockup is never its own file in a design folder

- **What.** A mockup lives only inside the `designData` block of the waiting page. "Add a design" pastes the mockup HTML into that block, and no repo design folder gets the file. The record branch copies the block to `waiting/page/designData.json`, which holds the page's 33 mockups on origin/roadmap. Measured 2026-11-02 for those 33: 1 exact file on a non-main ref, 8 topic matches on main, 22 `d4` files on origin/roadmap, 2 with an unknown home repo.
- **Where.** `skills/waiting-page/SKILL.md`: "Add a design", step 3.
- **Decision.** `waiting-data-in-repo` (git is each artifact's home).
- **Retire.** Guard rule `mockup-home` closes it. A waiting item's mockup must name a file in a mockup home: the repo's design folder, or the owner's machine-home folder outside the Claude app folders. The guard judges path shape only. The rule and its decision `mockup-home` are on branch `mockup-on-origin`, unmerged. Check: none yet.

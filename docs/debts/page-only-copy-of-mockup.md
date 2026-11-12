# A mockup is never its own file in a design folder

- **What.** A mockup lives only inside the `designData` block of the waiting page. "Add a design" pastes the mockup HTML into that block, and no repo design folder gets the file. The record branch copies the block to `waiting/page/designData.json`, which holds the page's 33 mockups on origin/roadmap. Measured 2026-11-02 for those 33: 1 exact file on a non-main ref, 8 topic matches on main, 22 `d4` files on origin/roadmap, 2 with an unknown home repo.
- **Where.** skill `waiting-page`, "Add a design", step 3.
- **Decision.** `waiting-data-in-repo` (git is each artifact's home).
- **Retire.** Guard rule `mockup-home` closes it. Open work: branch `mockup-on-origin`, decision `mockup-home`.

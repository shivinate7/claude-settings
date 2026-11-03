# Git is each artifact's home

## The ruling

Git is each artifact's home. The claude.ai link is one account's view of it.

- Owner, 2026-11-02 14:58 CST (feedback fb-1458-2): option a. An artifact is published only from a file in a repo, and listed in that repo's registry.
- Owner, 2026-11-02 14:56 CST (feedback fb-1456-1): artifacts are torn down and spun up as the owner switches accounts. Each must be cross-referencable across accounts. Committing them to GitHub is accepted.
- Mockups are artifacts too. The same rules hold for them (fb-1456-1).
- The registry is the `artifacts` key of the repo's extras file, read by `lint/layout.py`. An entry has an id (a slug of 32 characters or fewer), a url, a role, an account label (never an email) and the collections to export. The `waiting-page` role is the waiting page. The old `waiting-page` key is the fallback.
- Each export saves the page HTML, its supporting files and its database (fb-1458-2). It saves the HTML only when it changed (fb-1512-1).
- Each repo's copy lives on its record branch, the `roadmap` branch by default. The page writer pushes it with no PR (owner, 2026-11-02 15:12 CST, feedback fb-1512-1). Main moves only by pull request (rule `git-main-only-by-pr`, main moves only by pull request).
- Degen moves its copy to its record branch and retires its own export. It calls this repo's export (fb-1512-1).
- A cite names the artifact's id, as `artifact:<id>`. It never names the link. `lint/check_artifact_cites.py` refuses a bare link and an unregistered id.
- The 14 roadmap step links become `artifact:<id>` cites (fb-1458-2). Open: the links are still bare. Until they are fixed, the check runs with `--steps list`, which prints each step link and fails no step. Once they are fixed, the guard that checks page writes refuses a bare link at each write to the record branch.
- Owner, 2026-11-02 11:00 CST (waiting-page gripe, via the coordinator): the waiting page keeps a copy of its data in the repo, so a lost page loses no item. The owner did not take the ask verbatim. The gripe is real.
- The id `waiting-data-in-repo` names this decision. The writer's step lives in the waiting-page skill, not in a rule.
- The waiting page's copy is folder `waiting/` on the record branch. It holds five collections: `items`, `answers`, `groups`, `asks` and `meta`. Each document is one file, `waiting/<collection>/<doc_id>.json` (rule `git-record-own-file-per-kind`, one file per kind).
- The mockups live in the page's `designData` block. The export saves that block as `waiting/page/designData.json`.
- Files use sorted keys, two-space indent and a final newline. An unchanged document stays byte-identical, so a commit shows only real change.
- The page writer (skill `waiting-page`) copies the page at each wake and before each republish. It commits and pushes only when a file changed.
- The export scans every value and key before it writes. It refuses when it finds a token, a key, a cookie or auth header, a password, an email address or a phone number. The refusal prints each find's file, path and kind. It never prints the value. The writer fixes the item on the page first.
- Recovery needs no live page. The rebuild mode writes batch files of at most 50 writes each. The writer sends them to a new page, then puts the design data back into the page.
- The lint check flags a repo that has a waiting page but no `waiting/` folder on its record branch. It reads git refs. A missing ref, such as in a shallow clone, prints `unknown`. The check never passes or fails on that. Tools read the folder name through `lint/layout.py`, never as a literal.
- The export has an `--all` mode. It exports each registered artifact with the same scan and mirror rules, and prints one verdict line per artifact. One artifact's refusal holds back no other. The skill step "Before you switch Claude accounts" runs it.
- Briefs and handoffs are working files. The cite check does not read them.

Cost: each run of the writer makes one list call per page of each collection and starts one python process. It makes one commit when a file changed. No timer and no watcher.

Known limits:

- The scan reads shapes, not meaning. A personal fact in plain words, such as an employer or a city, passes.
- A truncated fetch, such as a missed page of results, deletes the missed documents from the copy. Git history keeps them.

Basis: owner rulings fb-1456-1, fb-1458-1, fb-1458-2 and fb-1512-1, and a named incident (see Incidents). Landed: set at merge.

Incidents:

- Date not recorded. The waiting page moved to another org, and Claude Code lost read access to it. 80 items were rebuilt from old transcripts. No repo held a copy of the page's database.

Kind: process
Home: skills/waiting-page/SKILL.md

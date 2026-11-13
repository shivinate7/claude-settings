# The page's git copy is a backup, not the store

## The ruling

The page's database is its one store, and git is its backup for recovery and account moves. Decision `page-one-store` (the one-store decision) sets this, and it replaces the earlier line here that git is each artifact's home. The one-store decision covers the page only. The rules below for other registered artifacts stand as written.

- Owner, 2026-11-02 14:58 CST (feedback fb-1458-2): "A", which picks option a of coordinator event e7ccdec6. An artifact is published only from a file in a repo, and listed in that repo's registry.
- Owner, 2026-11-02 14:56 CST (feedback fb-1456-1): artifacts are torn down and spun up as the owner switches accounts. Each must be cross-referencable across accounts. Committing them to GitHub is accepted.
- Mockups are artifacts too. The same rules hold for them (fb-1456-1).
- Coordinator, 2026-11-02 11:49 CST: the registry is the `artifacts` key of the repo's extras file, read by `lint/layout.py`. An entry has an id (a slug of 32 characters or fewer), a url, a role, an account label (never an email) and the collections to export. The `waiting-page` role is the waiting page. The old `waiting-page` key is the fallback. An optional `export` names the path an entry writes to. Pending, branch `artifact-registry`: `"export": false` for a page this account cannot read.
- Main today: `lint/layout.py` reads the `artifacts` key. This repo's extras file (`.claude/layout-extras.json`) still has only the old `waiting-page` key, so the fallback applies.
- Main today: the export saves the page's database and its designData block (`waiting/page/designData.json`). It does not save the page HTML or its supporting files.
- Ruled target, the owner's "A" on option a (fb-1458-2): each export saves the page HTML, its supporting files and its database. The HTML lands at `waiting/page/page.html`, and the supporting files at `waiting/page/files/<path>`. `skills/waiting-page/export_page.py` does this on main.
- Coordinator, 2026-11-02 15:12 CST (event f02abcb7-7474-4390-9b96-16384e4ee314), its gloss of fb-1512-1: the export saves the HTML only when it changed.
- Each repo's copy lives on its record branch, the `roadmap` branch by default. Owner, 2026-11-02 15:12 CST (fb-1512-1): "wb". The rest of that sentence is the sources' summary of the reply, not owner words: the page writer pushes the copy with no PR. Main moves only by pull request (rule `git-main-only-by-pr`, main moves only by pull request).
- Degen moves its copy to its record branch and retires its own export. It calls this repo's export (fb-1512-1, the same summary, not owner words).
- A cite names the artifact's id and its repo path, written `artifact:<id>`. It never names the link (ruled: the owner's "A" on option a, fb-1458-2). Open: `lint/check_artifact_cites.py` reads the id only, so the repo-path part is not checked yet. The check refuses a bare link and an unregistered id.
- The 14 roadmap step links become `artifact:<id>` cites under the same pick (fb-1458-2). Open: the links are still bare. Until they are fixed, the check runs with `--steps list`, which prints each step link and fails no step. Target, once the links are fixed: the guard that checks page writes refuses a bare link at each write to the record branch (coordinator's option a, event 46a1a427, 14:56 CST).
- Owner, 2026-11-02 11:00 CST (waiting-page gripe, through the coordinator): the waiting page keeps a copy of its data in the repo, so a lost page loses no item. The owner said not to take the ask verbatim, but the gripe is real.
- The id `waiting-data-in-repo` names this decision. The page writer's step lives in the waiting-page skill, not in a rule.
- The waiting page's copy is folder `waiting/` on the record branch. It holds five collections: `items`, `answers`, `groups`, `asks` and `meta`. Each document is one file, `waiting/<collection>/<doc_id>.json` (rule `git-record-own-file-per-kind`, one file per kind).
- The mockups live in the page's `designData` block. The export saves that block as `waiting/page/designData.json`.
- A kept mockup lands in the repo's design folder on main, by PR (layout kind `design`, `docs/design` by default). The record branch holds the artifact page copies. Process-only: the artifact lane's reading of the owner's words "my repos' design folders" (fb-1458-1). Design-explore step 7 closes the gap.
- Files use sorted keys, two-space indent and a final newline. An unchanged document stays byte-identical, so a commit shows only real change.
- The page writer (skill `waiting-page`) copies the page at each wake and before each republish. It commits and pushes only when a file changed. The Stop check in `hooks/feedback_guard.py` (roadmap step waiting-export-check) holds it: a page write with no later copy commit refuses the stop.
- The export scans every value and key, the page text and each supporting text file before it writes. It refuses a token, a key, a cookie or auth header, a named cookie set with `=`, a bare bearer or basic credential, a password or credentials in a URL. It refuses a secret, token, key or cookie name in any case form (`apiKey`, `SECRET_KEY_BASE`) set to a random-looking value. It refuses an email address, a phone number or a postal address. The refusal prints each find's file, path and kind. It never prints the value. The page writer fixes the item on the page first.
- Recovery needs no live page. The rebuild mode writes batch files of at most 50 writes each. The page writer sends them to a new page, then puts the design data back into the page.
- The lint check flags a repo that has a waiting page but no `waiting/` folder on its record branch. It reads git refs. A missing ref, such as in a shallow clone, prints `unknown`. The check never passes or fails on that. Tools read the folder name through `lint/layout.py`, never as a literal.
- The export has an `--all` mode. It exports each registered artifact with the same scan and mirror rules, and prints one verdict line per artifact. One artifact's refusal holds back no other. The skill step "Before you switch Claude accounts" runs it.
- Briefs and handoffs are working files. The cite check does not read them.

Cost: each run of the page writer makes one list call per page of each collection and starts one python process (unmeasured). It makes one commit when a file changed (unmeasured). No timer and no watcher.

Known limits:

- The scan reads shapes, not meaning. A personal fact in plain words, such as an employer or a city, passes. A password word whose whole value is a placeholder, a mask or a plain word also passes. So do `PWD=<path>`, a no-reply address and the ssh remote of a public git host.
- A truncated fetch, such as a missed page of results, deletes the missed documents from the copy. Git history keeps them.

Basis: owner rulings fb-1456-1, fb-1458-1, fb-1458-2 and fb-1512-1 ("wb"), the coordinator's note of 11:49 CST, and a named incident (see Incidents). Landed: set at merge.

Incidents:

- Date not recorded. The waiting page moved to another org, and Claude Code lost read access to it. 80 items were rebuilt from old transcripts. No repo held a copy of the page's database.

Kind: process
Home: skills/waiting-page/reference/copies-and-accounts.md

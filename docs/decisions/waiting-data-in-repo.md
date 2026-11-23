# Git is each artifact's home

## The ruling

Git is each artifact's home. The claude.ai link is one account's view of it.

- Owner, 2026-11-02 14:58 CST (feedback fb-1458-2): "A", which picks option a of coordinator event e7ccdec6. An artifact is published only from a file in a repo, and listed in that repo's registry.
- Owner, 2026-11-02 14:56 CST (feedback fb-1456-1): artifacts are torn down and spun up as the owner switches accounts. Each must be cross-referencable across accounts. Committing them to GitHub is accepted.
- Mockups are artifacts too. The same rules hold for them (fb-1456-1).
- Owner, 2026-11-15 13:16 CST ("i think A", on the artifact-links-per-account question): the registry is the `artifacts` key of the repo's extras file, read by `lint/layout.py`. Each artifact has one entry, keyed by its id (a slug of 32 characters or fewer). The entry holds a role, the collections to export, a required `export` (its git path, or `false` for a page held and never exported), and `links`: a list of `{account, url}`, one per account label, never an email. A session opens the link for its own account. When the entry has none, it rebuilds the page from git (the export's rebuild mode, or `--all`) and adds its new link. The list replaces the old single `url` and `account` fields; an entry that still has either is refused, with the remedy "move them into `links`".
- The `waiting-page` role is the waiting page. The old top-level `waiting-page` key is the fallback. `waiting_page(root, account)` reads that account's link, else the first.
- Main today: the export saves the page's database and its designData block (`waiting/page/designData.json`). It does not save the page HTML or its supporting files.
- Ruled target, the owner's "A" on option a (fb-1458-2): each export saves the page HTML, its supporting files and its database. The HTML lands at `waiting/page/page.html`, and the supporting files at `waiting/page/files/<path>`. `skills/waiting-page/export_page.py` does this on main.
- Coordinator, 2026-11-02 15:12 CST (event f02abcb7-7474-4390-9b96-16384e4ee314), its gloss of fb-1512-1: the export saves the HTML only when it changed.
- Each repo's copy lives on its record branch, the `roadmap` branch by default. Owner, 2026-11-02 15:12 CST (fb-1512-1): "wb". The rest of that sentence is the sources' summary of the reply, not owner words: the page writer pushes the copy with no PR. Main moves only by pull request (rule `git-main-only-by-pr`, main moves only by pull request).
- Degen moves its copy to its record branch and retires its own export. It calls this repo's export (fb-1512-1, the same summary, not owner words).
- A cite names the artifact's id and its repo path, written `artifact:<id>`. It never names the link (ruled: the owner's "A" on option a, fb-1458-2). Open: `lint/check_artifact_cites.py` reads the id only, so the repo-path part is not checked yet. The check refuses a bare link and an unregistered id.
- The 14 roadmap step links become `artifact:<id>` cites under the same pick (fb-1458-2). Open: the links are still bare. Until they are fixed, the check runs with `--steps list`, which prints each step link and fails no step. Target, once the links are fixed: the guard that checks page writes refuses a bare link at each write to the record branch (coordinator's option a, event 46a1a427, 14:56 CST).
- Owner, 2026-11-02 11:00 CST (waiting-page gripe, via the coordinator): the waiting page keeps a copy of its data in the repo, so a lost page loses no item. The owner said not to take the ask verbatim, but the gripe is real.
- The id `waiting-data-in-repo` names this decision. The page writer's step lives in the waiting-page skill, not in a rule.
- The waiting page's copy is folder `waiting/` on the record branch. It holds six collections: `items`, `answers`, `groups`, `asks`, `meta` and `receipts`. Each document is one file, `waiting/<collection>/<doc_id>.json` (rule `git-record-own-file-per-kind`, one file per kind). Receipts land at `waiting/receipts/<doc_id>.json`, the doc id being the answer id.
- Owner, 2026-11-22 21:02 CST: "yes closed items can be deleted, and frankly if they can even be expelled from git or in some sense clearly labeled in git as *deletes* that'd be beneficial so that way sessions don't even try to recover them." At 20:56 CST: an answered item kept in git "does not need to appear on the actual claude artifact for my review." So a closed item, with its answer and receipt, leaves the page and the copy.
- Owner, 2026-11-22 21:05 CST: "ensure that each ID is like confirmed deleted, like what if one artifact accidentally kept a question as #9 and another as #11, deletes need to be like verified off the data not just the label." So the export deletes an item only when its own data says `status: closed`, in the fetch, or in the copy when the fetch does not hold it open. It matches the doc key, never `n`. An item missing from the fetch stays, since another account's page may hold it open. Its answer (keyed by the item id or naming it in `item`) and that answer's receipt go with it. Each delete prints `deleted <collection>/<id>.json`. The writer commits the deletes on the record branch in a commit whose message starts `DELETE:` and lists each key. It then runs the export again: `same` confirms each key is gone and no open item left. Git history keeps them; the history is never rewritten. No session restores a deleted item to a page: `--rebuild` and `--merge` load open items only. A doc tied to no item, such as a park answer or receipt, and the `groups`, `asks` and `meta` docs stay in the copy when the fetch no longer lists them.
- The mockups live in the page's `designData` block. The export saves that block as `waiting/page/designData.json`.
- A kept mockup lands in the repo's design folder on main, by PR (layout kind `design`, `docs/design` by default). The record branch holds the artifact page copies. Process-only: the artifact lane's reading of the owner's words "my repos' design folders" (fb-1458-1). Design-explore step 7 closes the gap.
- Files use sorted keys, two-space indent and a final newline. An unchanged document stays byte-identical, so a commit shows only real change.
- The page writer (skill `waiting-page`) copies the page at each wake and before each republish. It commits and pushes only when a file changed. The Stop check in `hooks/feedback_guard.py` (roadmap step waiting-export-check) holds it: a page write with no later copy commit refuses the stop.
- The export scans every value and key, the page text and each supporting text file before it writes. It refuses a token, a key, a cookie or auth header, a named cookie set with `=`, a bare bearer or basic credential, a password or credentials in a URL. It refuses a secret, token, key or cookie name in any case form (`apiKey`, `SECRET_KEY_BASE`) set to a random-looking value. It refuses an email address, a phone number or a postal address. The refusal prints each find's file, path and kind. It never prints the value. The page writer fixes the item on the page first.
- Recovery needs no live page. The rebuild mode writes batch files of at most 50 writes each. The page writer sends them to a new page, then puts the design data back into the page.
- The lint check flags a repo that has a waiting page but no `waiting/` folder on its record branch. It reads git refs. A missing ref, such as in a shallow clone, prints `unknown`. The check never passes or fails on that. Tools read the folder name through `lint/layout.py`, never as a literal.
- The export has an `--all` mode. It exports each registered artifact with the same scan and copy rules, and prints one verdict line per artifact. One artifact's refusal holds back no other. The skill step "Before you switch Claude accounts" runs it.
- Briefs and handoffs are working files. The cite check does not read them.

Cost: each run of the page writer makes one list call per page of each collection and starts one python process (unmeasured). It makes one commit when a file changed (unmeasured). No timer and no watcher.

Known limits:

- The scan reads shapes, not meaning. A personal fact in plain words, such as an employer or a city, passes. A password word whose whole value is a placeholder, a mask or a plain word also passes. So do `PWD=<path>`, a no-reply address and the ssh remote of a public git host.
- A truncated fetch, such as a missed page of results, deletes nothing: a doc is deleted only for data that says closed.
- A routed closed item keeps its answer on the page until the done report, but the next export deletes the answer's copy. A lost page then loses that answer.

Basis: owner rulings fb-1456-1, fb-1458-1, fb-1458-2 and fb-1512-1 ("wb"), the coordinator's note of 11:49 CST, and a named incident (see Incidents). Landed: set at merge.

Incidents:

- Date not recorded. The waiting page moved to another org, and Claude Code lost read access to it. 80 items were rebuilt from old transcripts. No repo held a copy of the page's database.

Kind: process
Home: skills/waiting-page/reference/copies-and-accounts.md

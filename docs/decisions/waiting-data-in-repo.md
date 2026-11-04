# A copy of the waiting page lives in the repo, so a lost page loses no item

## The ruling

Owner, 2026-11-02 11:00 CST (waiting-page gripe, via the coordinator): the waiting page keeps a copy of its data in the repo, so a lost page loses no item.

The owner said not to take the ask verbatim, but the gripe is real. The id `waiting-data-in-repo` names this decision. The writer's step lives in the waiting-page skill, not in a rule.

- The copy lives on the record branch, not on main. The record branch is the repo's `roadmap` branch by default. It is an orphan branch with no pull request and no CI run. Main moves only by pull request (rule `git-main-only-by-pr`). Process-only: the lane orchestrator chose the record branch.
- The copy is folder `waiting/` on that branch. It holds five collections: `items`, `answers`, `groups`, `asks` and `meta`. Each document is one file, `waiting/<collection>/<doc_id>.json` (rule `git-record-own-file-per-kind`).
- The page's design data is one file, `waiting/page/designData.json`. The mockups stay in the page HTML.
- Files use sorted keys, two-space indent and a final newline. An unchanged document stays byte-identical, so a commit shows only real change.
- The page writer (skill `waiting-page`) copies the page at each wake and before each republish. It commits and pushes only when a file changed.
- The export script scans every value and key before it writes. It refuses when it finds a token, a key, a cookie or auth header, a password, an email address or a phone number. The refusal prints each find's file, path and kind. It never prints the value. The writer fixes the item on the page first.
- Recovery needs no live page. The rebuild mode writes batch files of at most 50 writes each. The writer sends them to a new page, then puts the design data back into the page.
- The lint check flags a repo that has a waiting page but no `waiting/` folder on its record branch. It reads git refs. A missing ref, such as in a shallow clone, prints `unknown`. The check never passes or fails on that.
- Tools read the folder name through `lint/layout.py`, never as a literal.
- Coordinator, 2026-11-02 11:49 CST: the same copy covers every claude.ai artifact a repo holds. Each artifact is one entry in the `artifacts` key of the repo's extras file, read by `lint/layout.py`. An entry has an id (a slug of 32 characters or fewer), a url, a role, an account label (never an email) and the collections to export. The `waiting-page` role is the waiting page. The old `waiting-page` key is the fallback. This replaces the sketch's `.claude/artifacts.json`: the extras file stays the one home of the page URL.
- The export script has an `--all` mode. It exports each registered artifact to its export path, with the same scan and mirror rules, and prints one verdict line per artifact. One artifact's refusal holds back no other. The skill step "Before you switch Claude accounts" runs it.
- A decision or a debt cites an artifact as `artifact:<id>`, never by its link. `lint/check_artifact_cites.py` refuses a bare link and an unregistered id. A roadmap step is refused too, unless the run says `--steps list`. That mode only lists a step's links, because lanes never write the roadmap and triage moves them. Briefs and handoffs are working files, outside the check.

Cost: each run of the writer makes one list call per page of each collection and starts one python process. It makes one commit when a file changed. No timer and no watcher.

Known limits:

- The scan reads shapes, not meaning. A personal fact in plain words, such as an employer or a city, passes.
- A truncated fetch, such as a missed page of results, deletes the missed documents from the copy. Git history keeps them.

Basis: named incident (see Incidents). Landed: set at merge.

Incidents:

- Date not recorded. The waiting page moved to another org, and Claude Code lost read access to it. 80 items were rebuilt from old transcripts. No repo held a copy of the page's database.

Kind: process
Home: skills/waiting-page/SKILL.md

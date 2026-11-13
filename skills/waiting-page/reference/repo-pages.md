# Repo pages

Read this when a repo makes its waiting page, when its roadmap block changes, or when a batch republishes each waiting page.

## Make a repo's page

Triage runs this when `python3 ~/.claude/lint/layout.py waiting-page <repo root>` prints `unknown`.
The repo has no page. The coordinator-and-triage setup is the grant: the first triage does this, with no
separate grant. It never marks the repo rolled out.

A fork (a worktree whose work never reaches main) makes its own page and writes its own `waiting-page`
key. It never reuses main's.

1. Load the `artifact-capabilities` skill.
2. Publish `page.html` from this skill folder as a new private artifact with the capabilities
   `db` and `comments` (the full form, `{comments: {}}`). Before you publish, set the page's
   `<title>` to "<repo> Cockpit" (owner ruling, 2026-11-02 11:12 CST). Change nothing else. A republish keeps the title, and renames an old "Queue" or "Roadmap" title to "<repo> Cockpit" (`splice.carry`). A page
   published with `db` only keeps working and wakes no one. Republish it with both capabilities
   to turn this on.
3. Triage writes `meta/page` with `checked`, an empty `parked` and `identity`. Take `brand` and `icon` from
   `python3 ~/.claude/lint/repo_colour.py identity <repo root>`. It reads the repo's own extras keys
   `waiting-page-colour` (#rrggbb) and `waiting-page-icon` (an .svg or .png path in the repo) first,
   then `docs/design/repo-colours.json`. Exit 2 means the colour is unknown: leave `brand` out. Never
   invent a colour. The page still checks each text colour for 4.5:1 contrast.
4. Set the URL once: `python3 ~/.claude/lint/layout.py set-waiting-page <repo root> <url>`. It writes the
   `waiting-page` key of the repo's extras file, `.claude/layout-extras.json`. Exit 0 wrote it. Exit 1 means
   the key is already set: it prints the URL and writes nothing. Exit 2 means the URL is not an artifact
   link, or the extras file cannot be read or written. The file alone does not mark the repo as rolled
   out; that is its own key, `"rolled-out": true`, added only in the repo's roll-out.
5. Check with `python3 ~/.claude/lint/layout.py waiting-page <repo root>`.

A local session can write to the database (measured on the Mac, Oct 26). A Windows session is
unmeasured.

## Update the roadmap block

The roadmap build makes the Status tab's data, the roadmap block. The page writer alone
publishes the page file, so the repo has one page and one publisher. The skill roadmap publishes nothing.
The Status tab draws each phase id that its steps use, and a step with no phase goes under "No phase".

1. Build the roadmap block: `python3 ~/.claude/skills/roadmap/build.py --repo <checkout> --block --out <block file>`
   (add `--live <file>` as the skill roadmap says). The live file's pull rows carry `createdAt` (GitHub's
   `created_at`; its item rows carry `lane` when the page item has one; its `landedPulls` rows are the pull requests
   closed in the last 14 days with the default branch as base, each with `number`, `branch`, `head` and `merged`). Exit 1 with `todo step with an open PR`
   lines still writes a valid block: splice and publish as usual, then set each named step to `doing`. Exit 1
   with `stalled step:` lines does the same: splice, publish, then dispose each one (a step: set it `todo` or
   `done`, or write its `paused` field; an item: re-route it, close it, or resume its lane). The unknown
   lines (`stalled step: unknown (...)`, `stalled step: items unknown (...)`) exit 0 and need no disposal.
2. Read the live page with `Artifact` action `read` and save it. Never build the new page from an
   older copy: the live page holds the designs for the items still open.
3. Splice: `python3 ~/.claude/skills/waiting-page/splice.py --page <live page> --block <block file> --out <new page>`.
   It replaces the roadmap block, from `<!-- roadmap:data -->` to `<!-- /roadmap:data -->`, and keeps
   every other byte, the `designData` block among them. It refuses a page with no roadmap block or an
   unclosed one. A page that predates the roadmap block has none: first carry it into the template
   (`splice.py --page <skill folder>/page.html --carry <live page> --out <carried page>`), then splice
   the block into `<carried page>`.
4. Publish `<new page>` to the same URL with the capabilities `db` and `{comments: {}}`. One publish
   at a time, never with `force`. Whether the database stays is unmeasured until the step 4 live
   check of "Update a repo's pages".
5. A design republish ("Add a design", step 5) is the same act the other way: it changes only the
   `designData` block of the live page and keeps the roadmap block.

Page URL keys and the retired roadmap URL: skill `roadmap`, first paragraph.

## Update a repo's pages

A batch that changes `page.html` republishes each waiting page this account can reach, before the
batch report. The pages are the `waiting-page` keys of the repos' extras files, read by
`live_pages()` in `~/.claude/lint/layout.py`.

1. Fetch each page with `Artifact` action `read` into one folder, as `<artifact id>.html`. A page
   that cannot be read gets an empty `<artifact id>.unreadable`. A read that gives a summary, not
   raw HTML, or that does not name this account a writer, is unreadable too. Write an empty
   `<artifact id>.notfound` instead only when the read says "not found" AND `Artifact` action `list`
   with scope `all` holds no such id. Page the list to its end (`page_token` until none is returned)
   before an id counts as absent. Any other failed read stays `.unreadable`.
2. Run `python3 ~/.claude/skills/waiting-page/stale_pages.py <folder>`. It names each page that is
   `behind`, `unknown` or `not-found` with its owner, and exits non-zero. An unread page is never
   current. A `not-found` page is reported with the claude-settings waiting page as the place to re-file that
   repo's items: the URL recorded in the extras file of the claude-settings checkout that holds the script, not
   fetched. The target reads `the claude-settings waiting page is unknown` when that checkout has no page, its
   extras file cannot be read, or its page has a `.notfound` or `.unreadable` marker in the folder. The check
   never repoints a page: the owner decides.
3. For each `behind` page, build the page to publish from the live page you fetched in step 1, never
   from plain `page.html`, as "Keep the page on main's code" step 2 says:
   `stale_pages.py --page <fetched page> --write <new page>`.
   `--write` carries the live `designData` block, roadmap block and `<title>` text into main's page, byte for byte. A live
   page with no roadmap block gives its `designData` block, and the template keeps its empty roadmap
   block. The carry refuses, with nothing written and the verdict `unknown`. It refuses when the template
   lacks either block, when the live page has no `designData` block, or when either file has a
   broken or doubled block. Before the republish, check the pictures of the open items against `<new page>`, never the live page:
   `python3 ~/.claude/skills/waiting-page/export_page.py --check --fetched <items folder> --page <new page>`, one `<items folder>` per behind page. It holds
   the `items` and `answers` of that page's own artifact, fetched as "Keep a copy in the repo" step 2 does (`ArtifactData list`
   on that page's `url`, `.complete` after each last page), never this repo's copy. It writes nothing. Hold the republish on any exit but 0, as in the other two
   republish routes (exit 4 a held item, exit 3 `checks unknown`, exit 2 no page file). Republish `<new page>` to the same URL
   with the capabilities `db` and `{comments: {}}`, one publish at a time, never with `force`. A
   republish of plain `page.html` drops the open items' designs and the Status tab.
   `stale_pages.py` empties both blocks before it compares, so it cannot tell that they were lost: it
   reads such a page current. After the publish, re-read the republished page (`Artifact` action
   `read`) and check that its `designData` block equals the one in the page you fetched in step 1.
4. Update one page first, then read its items: they must all still be there. That the database and
   its saved answers survive a republish is unmeasured until this live check is run.
5. Run the command again. The batch report lists its verdict line, with each `unknown` or `not-found` page
   and its owner.

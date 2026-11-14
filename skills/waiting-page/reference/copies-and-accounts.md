# Copies and accounts

Read this when the writer keeps the page's copy in the repo, when a repo registers an artifact, or before the Claude account, the org or the machine changes.

## Keep a copy in the repo

A page that is lost or moved to another org takes its items with it. So the writer keeps a copy of the page's data in the repo (decision
`waiting-data-in-repo`). The copy lives on the repo's record branch, never on main. Main moves only by pull
request. The record branch (`roadmap` by default, `~/.claude/lint/layout.py` `record_branch()`) takes a direct push.

The writer runs this at each wake, as step 3 of "Keep the page on main's code", before any republish. A lane
never runs it. There is one path: the record branch's own worktree. Never write the copy anywhere else.

1. Check out the record branch in its own worktree (`roadmap`; the repo's extras file may name another).
   Name the copy folder: take the path `python3 ~/.claude/lint/layout.py path <repo root> waiting-data` prints,
   and use that path inside the worktree.
2. Fetch each of the six collections: `items`, `answers`, `groups`, `asks`, `meta` and `receipts`. Use
   `ArtifactData list <collection>` with `out_dir` set to one new folder, and `query.limit` 1000.
   Follow `next_cursor` until it is empty. A list call that errors, or that ends with a cursor still
   pending, stops the run: touch no `.complete` file and run no export. A missed cursor page deletes docs
   from the copy. After the last page of a collection, touch `.complete` in its folder. An empty collection
   is an empty folder with that marker. Make the folder by hand if the tool wrote none.
3. Run `python3 ~/.claude/skills/waiting-page/export_page.py --fetched <folder> --out <copy folder> --page <file>`.
   `<file>` is the page that "Keep the page on main's code" step 1 already read. Its HTML lands in the copy as
   `page/page.html`, written only when it changed.
   Name a collection that really emptied with `--allow-empty <collection>`. Without it, an emptied
   collection is `unknown`.
4. Read the verdict line.
   - `same`: stop. Commit nothing.
   - `changed <n>`: in the same worktree, run `git add` on the copy folder, then
     commit and push the record branch. The commit message names the count.
   - `held item <n>: <sentence>` after the verdict line (exit 4): after `changed`, the copy was written; commit it as for `changed`. After `same`, commit nothing. The page would
     draw that item's picture wrong. Fix the item, export again, and do not republish while one is held.
   - `refused`: nothing was written. Make no commit. The reply names each find: the file, the JSON path and
     the kind, never the value. Fix the item on the page first, then run the steps again.
   - `unknown`: nothing was written. Say the line in the reply. A missing collection folder or marker, an
     emptied collection and a crash (exit 3) are the usual causes.

The copy holds one JSON file per doc, `<collection>/<doc id>.json`, and `page/designData.json`. The mockups live
in the page's `designData` block, not in the database.
The scan reads shapes: tokens, keys, cookie and auth headers, named cookies set with `=`, bare bearer or basic credentials,
passwords, URL query secrets and credentials in a URL. It reads secret, token, key or cookie names in any case form set to a random-looking value
(`API_SECRET=...`, `apiKey: ...`). It also reads email addresses,
phone numbers and postal addresses (street, PO box, "City, ST ZIP"). A personal fact in plain words, such as an employer or a city name alone, passes. Do not write one in an item.
A password word with a placeholder, a mask or a plain word as its value, and only blanks or plain prose after it on
its line, passes. Prose is a function word, then letter words. After a `,` `;` or and/or/but/is/are, a later word on the
line that is no function word refuses. The `,` `;` or `.` that ends the value does not count. So `none, then swordfish`
passes, and `none and swordfish` does not. `PWD=<path>`, a no-reply address and the ssh remote of a public git host pass
too. So does a `key` that ends one of nine everyday words (monkey, hotkey, turkey, turnkey, donkey, whiskey, jockey,
hockey, lackey), when the word starts at a non-letter or the string start: `turnkey=` passes, `superturnkey=` refuses.

Cost: one list call per page of each collection, one python process, and one commit when something changed. No
timer, no watcher.

## Register and cite an artifact

Each claude.ai artifact a repo holds is one entry in the `artifacts` key of its extras file
(`python3 ~/.claude/lint/layout.py artifacts <repo root>` prints them). An entry has `id`, `url`, `role` and
`account`. A role other than `waiting-page` also has `collections`, the collections to export. An empty list
(`"collections": []`) makes a page-only entry: its page and files export, and no database does. `id` is a slug of
32 characters or fewer. `account` is a plain label such as `work`, never an email. The role `waiting-page` marks
the repo's waiting page. Its default collections are the six above, and its export folder is the waiting-data
folder. Any other artifact exports to `artifacts/<id>/`. The old `waiting-page` key stays the fallback when no entry
has that role.

A decision or a debt cites an artifact as `artifact:<id>`, never by its link. A link breaks when a page moves, and
the registry then needs one edit. `python3 lint/check_artifact_cites.py` refuses a bare link and an unregistered id
in decisions and debts. A brief or a handoff is a working file, and the check does not read it. The roadmap steps
of a repo may still hold links. List them for triage to move with `python3 ~/.claude/lint/check_artifact_cites.py --root <repo root> --steps list`.

## Before you switch Claude accounts

Run this once before the account, the org or the machine changes. It copies every registered artifact, not only
the waiting page. A page that moves loses its read access, and the repo then holds its last copy.

1. Check out the record branch in its own worktree, as "Keep a copy in the repo" step 1 says.
2. Make one new folder. For each entry of the registry, make `<folder>/<id>/`. In it, run `ArtifactData list` for
   each collection the entry lists, with `out_dir` set to `<folder>/<id>`, `query.limit` 1000, and
   `next_cursor` followed until it is empty. A list call that errors, or that ends with a cursor still pending,
   stops the run for that artifact: touch no `.complete` for it. After the last page of a collection, touch
   `<folder>/<id>/<collection>/.complete`. Make the folder by hand if the tool wrote none. Also save the page from `Artifact` action `read` to `<folder>/<id>/page.html`,
   and each file of `Artifact` action `list` scope `files` to `<folder>/<id>/files/<path>`.
3. Run `python3 ~/.claude/skills/waiting-page/export_page.py --all <repo root> --fetched <folder> --worktree <worktree>`.
   It prints one line per artifact, `<id>: <verdict>`, with the verdicts of a single export, or
   `<id>: skipped - no export` for an entry held with `"export": false`, which needs no folder. When the session
   can read only one account's pages, pass `--account <label>` with its own account's label from the registry; without
   it, each page the session cannot fetch prints `<id>: unknown`. An entry of another account prints
   `<id>: skipped - account <its account>`, needs no folder and writes nothing. A label no entry holds, or an empty
   one, prints one `unknown` line, writes nothing and exits 2. The page and each
   text file are scanned like the docs; a find refuses that artifact only.
4. Run `git add` on the export folder of each artifact whose line says `changed`. Then commit and push the record
   branch. A `refused` artifact wrote nothing, so its folder is as it was. An `unknown` one wrote nothing too. A `checks unknown: collections lack <name>` line is not a verdict: its artifact wrote the copy, says `same` or `changed <n>`, and exits 2. Say each such line in
   the reply, and fix the cause first.

Cost: one list call per page of each collection of each entry, one python process, and one commit when something
changed. No timer, no watcher.

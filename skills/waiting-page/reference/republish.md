# Republish, rebuild and merge the page

Read this when the writer republishes the page, rebuilds it from the repo, or merges a copy into a live page.

## Keep the page on main's code

The writer runs this at each wake and before each republish. A lane never runs it. Every republish
is main's `page.html` with the live `designData` and roadmap blocks kept, never the live page's own code (owner,
2026-10-29 14:47 CDT; decision `questions-go-to-owner`).

1. Read the page with `Artifact` action `read`. Use the file the read names as the saved full page.
   A read that gives a summary, not the raw page, is `unknown`.
2. Run `python3 ~/.claude/skills/waiting-page/stale_pages.py --page <file> --write <out> --items <items> --answers <answers>`, where
   `<items>` and `<answers>` are what `ArtifactData list items` and `ArtifactData list answers` saved. It
   compares the page's code outside `designData` with `skills/waiting-page/page.html` on
   claude-settings main, and prints one line: `current`, `behind` or `unknown`, with the source it
   read. Code outside main's page, other than the host's document skeleton, is `behind`. Then it prints one
   `wait:` line per open item with `waits` (`ended`, `waiting` or `unknown`), and one `waiting` lane line per open item with
   `lane` and `lastAnswer` and no `waits`. Last, one `kept-answer:` line per closed item whose `answers/<id>` is still kept
   (never an open item, an arbiter ruling or a park answer). A closed item with `waits` gets a line that says it is closed with waits. The exit code stays the page's.
   After the writer routes each ask and answers the ones it holds, save the asks with `ArtifactData list asks`,
   touching `.complete` only when no list call fails and no cursor is pending.
   Save them into one new folder, with `query.limit` 1000, and follow `next_cursor` until it is empty ("Keep a copy in the repo" step 2 saves the same list). "Route an ask" says how the writer routes.
   Right after that, run the end check as its own run, apart from the plain run and never with `--write`:
   `python3 ~/.claude/skills/waiting-page/stale_pages.py --page <file> --asks <asks>` (`<asks>` is the folder saved in this step). It prints one
   `open-ask:` line per ask with no `reply`, a routed ask included. If an ask is listed or the asks list cannot be read, it also prints a `FAIL:` line.
   On a current page, exit 1 means that an ask is open, and exit 2 means that the asks list could not be read. The session that holds an ask answers it ("Route an ask"); the writer routes it or names the holder.
3. Keep a copy of the page in the repo, from the same file ("Keep a copy in the repo"). Do it before any
   republish, so the copy holds the page as it was.
4. Before any republish, check the pictures of the open items, against the file about to be published (`<out>`, the `--write` output of
   step 2), never the live page: `python3 ~/.claude/skills/waiting-page/export_page.py --check --fetched <folder> --page <out>`
   (`<folder>` is the fetch of "Keep a copy in the repo", step 2). It writes nothing. Hold the republish on any exit but 0.
   `held item <n>: ...` (exit 4): fix that item, check again. `checks unknown: ...` (exit 3), or no page file (exit 2):
   a check that cannot read its input fails, never passes (owner ruling, item 276 a): say the line in the reply,
   and republish nothing until a check passes. `checks pass` (exit 0): go on.
   `behind`: republish `<out>` to the same URL with the capabilities `db` and `{comments: {}}`.
   `<out>` is main's page with the live `designData` and roadmap blocks kept, byte for byte
   (`--write` calls `splice.carry`). A live page with no roadmap block keeps the template's empty one.
   When you also add a design, do it in
   `<out>` first and republish once ("Add a design").
5. `unknown`: republish nothing, and say the line in the reply. The line names the cause: the page
   could not be read, or main's `page.html` could not be read (no claude-settings clone, or no
   `origin/main` in it). Only main proves a page current; the installed copy never does.

The guard enforces this (rule `page-stale`, decision `page-stale-publish`): an `Artifact` publish of this
repo's waiting page from a file behind main is refused, and its reason repeats steps 1, 2 and 4. An allowed
publish of main's page stamps main's page version, and the next session start says when the page is behind.

Cost: on demand, inside a wake already running. One `Artifact read` and two python processes: the plain run and the end check.
Each python process starts at most one short read-only git process, with no fetch. The plain run makes one gh call per open item with `waits`. With `--answers`, one more `ArtifactData list answers` read.
One `ArtifactData list asks` read for the end check, per page of 1000 asks; that save writes one file per ask and the `.complete` marker. The python processes write `<out>` only, and no file without
`--write`. No timer, no watcher. `test_stale_pages.py` proves the file count.

## Rebuild a page from the repo

Use this when the page is gone, or moved to an org this account cannot read. It needs the repo only, never the
live page.

1. Make a new page ("Make a repo's page"), and note its URL. The new page has an empty database.
2. Check out the record branch in its own worktree and name the copy folder in it, as "Keep a copy in the repo"
   step 1 says.
3. Make one new empty folder. Run
   `python3 ~/.claude/skills/waiting-page/export_page.py --rebuild <copy folder> --batches <new folder>`.
   For an artifact other than the waiting page, add `--collections <names>`: the `collections` of its registry entry,
   or its folders are `unknown`. It prints `batches <k> docs <n>`. An empty or missing copy folder is `unknown`. Stop
   and say so. A page-only copy (registry `collections: []`) has no docs, so `--rebuild` reports it holds no docs.
   Restore it by publishing its `page/page.html` (and `page/files/`) to a new page.
4. Send each `batch-NNN.json` list to the new page as one `ArtifactData batch`, in order. Each entry is a `set`.
5. Put the mockups back. Take main's `page.html`. Replace the text inside its `designData` script element with
   the JSON of `page/designData.json`. Write each `<` as `\u003c`, so no string can close the script. Publish
   it to the new URL, as "Keep the page on main's code" step 4 says.
6. Read the new page's items back. Their count must equal the count of files in the copy's `items` folder.
7. Write the new URL into the repo's extras file, in a pull request. Set the `url` of the `waiting-page` role entry
   in `artifacts`. If the repo has no such entry, set the `waiting-page` key.

## Merge a copy into a live page

Use this when two accounts each wrote a page for the same repo. One account's page is live. The other account's
export is in the repo copy. This adds the copy's missing items to the live page. The live page wins, so a live item
is never changed.

1. Check out the record branch in its own worktree and name the copy folder, as "Keep a copy in the repo" step 1 says.
2. Fetch the live page's collections into one new folder, `<live folder>`, as "Keep a copy in the repo" step 2 says.
   Touch `.complete` in each collection folder after its last page. A folder with no marker is `unknown`. Also read
   the live page with `Artifact` action `read`, and use the file the read names as `<html file>`. A read that gives a
   summary, not the raw page, is `unknown`.
3. Make one new empty folder, `<out folder>`. Run
   `python3 ~/.claude/skills/waiting-page/export_page.py --merge <copy folder> --live <live folder> --batches <out folder> --live-page <html file>`.
   For an artifact other than the waiting page, add `--collections <names>`.
4. Read the last line: `batches <k> docs <n> kept-live <s> renumbered <r> designs <d>`. `renumbered` counts the copied
   items that took a new `n` because the live page holds theirs. Each such item's answer takes the same `n`. A copy
   answer is skipped when the live page holds its item. An `unknown` line writes nothing. Say it in the reply.
5. Send each `batch-NNN.json` list to the live page as one `ArtifactData batch`, in order. Each entry is a `set`.
6. Read the live page's items back. Their count must equal the count of live items from step 2, plus the items among
   the `<n>` written docs.
7. Put the mockups in, on main's code ("Keep the page on main's code"). Run its read, `stale_pages.py --write` and copy
   steps on the live page. The page that `--write` writes is main's `page.html` with the live roadmap block carried
   over. In that page, replace the text inside the `designData` script element with `<out folder>/designData.json`,
   as is. The file already writes each `<` as `\u003c`, so no string can close the script. Publish that page once to
   the live URL, as that section's republish step says.
8. Rewrite each `page item <n>` cite of the copy's account in the roadmap, with `<out folder>/renumbered.json`: the
   key is the old `n`, and the value is the new one. Commit it on the record branch.

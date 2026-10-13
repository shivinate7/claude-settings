# plain-diff

A mod. It adds one command, `/plain-diff`. It draws nothing else.

The command opens a pane. The pane lists each changed file. Each file has a short note in plain English above its diff. The note says what changed and why it matters.

## What it shows

- One header line: the count of files, added lines, and removed lines.
- Per file: the path, the note, and the diff.
- A diff longer than 40 lines stays closed. Press the button to open it.
- The pane shows 30 files at most. It says so when there are more.
- The diff is `git diff HEAD`: the working tree and the staged changes, against HEAD. New files that git does not track yet are not shown.

## Where a note comes from

1. Claude's own words in the turn that edited the file. This costs nothing.
2. One small-model call (`haiku`) for a file with no such words. The pane marks the note "(summarised by a model)". At most 5 calls run at one time, for all runs together. Each call gets at most 6000 characters of one diff.
3. If no call is possible, the pane shows "No note" and the diff.

A model error never blocks the pane. Notes are kept in memory for the session, by file path and diff hash. The mod does not write to `$.store`. File text leaves the machine only through `$.model.complete`.

## Secret files

The mod skips a secret file. A secret file is one with a name such as `.env`, `*.pem`, `id_rsa`, or `credentials.json`. A file is also secret when its change holds a key in a known form. Examples are a private key block and a cloud or API token. The pane shows "Skipped: secret file" and no diff. The text is never sent to a model. The check runs before any model call. A secret in a form the mod does not know is not caught.

## Check

- `node mods/plain-diff/plain-diff.test.mjs` runs the tests. `node mods/plain-diff/check.mjs` is a small extra check of the helpers.
- `claude plugin validate mods/plain-diff` checks the mod.
- `docs/mockup.html` shows what the pane looks like for one real diff. Its notes are written by hand.

## Try it

`claude --plugin-dir mods/plain-diff`, then type `/plain-diff`. In a running session, use `/reload-plugins` after an edit.

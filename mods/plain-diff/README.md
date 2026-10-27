# plain-diff

A mod. It adds one command, `/plain-diff`. It draws nothing else.

The command opens a pane. The pane lists each changed file. Each file has a short note in plain English above its diff. The note says what changed and why it matters.

## What it shows

- One header line: the count of files, added lines, and removed lines.
- Per file: the path, the note, and the diff.
- A diff longer than 40 lines stays closed. Press the button to open it.
- The pane shows 30 files at most. It says so when there are more.
- The diff is `git diff HEAD`: the working tree and the staged changes, against HEAD. New files that git does not track yet are not shown.
- In a repo with no commit yet, the diff is against the empty tree. Every staged file shows as new.
- If git output is cut, the header says "Diff truncated: some files are not shown". The count is then not complete.

## Where a note comes from

1. Claude's own words in the turn that edited the file. This costs nothing.
2. One small-model call (`haiku`) for a file with no such words. The pane marks the note "(summarised by a model)". The limit is at most 5 calls per run, shared by overlapping runs. Runs that overlap share one budget of 5. A call that hangs is freed after 25 seconds. Each call gets at most 6000 characters of one diff.
3. If no call is possible, the pane shows "No note" and the diff.

A model error never stops the pane. Notes are kept in memory for the session, by file path and diff hash. The mod does not write to `$.store`. File text leaves the machine only through `$.model.complete`.

## Secret files

The mod skips a secret file. A secret file is one with a name such as `.env`, `*.pem`, `id_rsa`, or `credentials.json`. A file is also secret when its change holds a key in a known form. Examples are a private key block and a cloud or API token. The pane shows "Skipped: secret file" and no diff. The text is never sent to a model. The check runs before any model call. A note from Claude's own turn text is dropped when it holds a secret in a known form.

Known limits, in plain words:

- A secret in a form the mod does not know is not caught.
- The check can also hide ordinary source. It flagged about 1% of the changes in this repo's history. Those files show "Skipped: secret file" with no note and no diff.
- Some secret file names are not caught by name. Examples are `terraform.tfstate`, `.kube/config`, `wp-config.php`, and `AuthKey_*.p8`.
- A quoted path with an emoji or other non-ASCII text may show a wrong label.
- A `.env` file that git shows as a new file under an innocent name is not caught by name. A rename that git detects is checked by its old name.

## Check

- `node mods/plain-diff/plain-diff.test.mjs` runs the tests. `node mods/plain-diff/check.mjs` is a small extra check of the helpers.
- `claude plugin validate mods/plain-diff` checks the mod.
- `docs/mockup.html` shows what the pane looks like for one real diff. Its notes are written by hand.

## Try it

`claude --plugin-dir mods/plain-diff`, then type `/plain-diff`. In a running session, use `/reload-plugins` after an edit.

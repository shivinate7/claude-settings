# plain-diff sends a diff to a model only past the secret filter

## The question

Does the plain-diff mod (`mods/plain-diff`, command `/plain-diff`) send a changed file's diff to a model? If it does, what stops a secret from going?

## The ruling

The mod sends a diff to `$.model.complete` only for a file that passes the secret filter.

Owner intent: the owner rarely reads diffs. The owner wants a plain-English note for each changed file. No secret leaves the machine.

The filter has two parts:

- A path deny-list. It tests the file name. Examples: `.env`, `*.pem`, `id_rsa`, `credentials.json`.
- A content test. It runs on each line in chunks of 3000 characters, with 200 characters of overlap. It runs on the full diff after control characters are removed. That text holds everything the model receives. It matches these shapes:
  - A private key block.
  - AWS keys (AKIA, ASIA), GitHub tokens, `sk-` keys, Stripe live keys, Slack tokens and Google API keys.
  - JWTs, URLs with `user:pass@`, and Bearer tokens.
  - A `KEY=value` line where the name holds API_KEY, SECRET, PASSWORD, PASSWD or TOKEN.

The rules:

- The filter runs before any model call. It tests the new path and the old path of a rename.
- A skipped file shows "Skipped: secret file" and no diff. Nothing from the file is kept, shown or sent.
- A note from Claude's own turn text passes the same content test. A turn text that holds a secret gives no note. A turn-text note wins over a model note and costs no model call.
- Model calls are capped at 5 per run. One limiter is shared by all runs. It counts calls while any call is in flight, and it resets when none is. A file past the cap shows "No note: model limit or timeout".
- Each model call is passed a 20 s timeout. The shared limiter frees a call's slot after 25 s.
- Git calls use fixed prefixes, `--src-prefix=a/` and `--dst-prefix=b/`. They also use `--no-ext-diff`, `--no-textconv` and `-c core.fsmonitor=false`. A repo's own diff programs and fsmonitor command do not run.
- Notes are plain text. Markdown links reduce to their label and URL without the scheme. HTML is escaped. Control characters are stripped.
- Notes are cached in memory only, keyed by path and diff hash.

Files: `mods/plain-diff/hooks/lib.mjs` (`isSecretPath`, `looksSecret`, `makeLimiter`, `trimNote`, `gitDiffArgs`) and `mods/plain-diff/hooks/register.mjs`. Details: `mods/plain-diff/README.md`, Secret files section.

## Why

The owner wants plain-English notes and no secret off the machine. A model call sends file text out of the machine. The test runs before that call. A file that fails is skipped, not sent. A false match hides a file. It never sends one.

## What it costs

- A false match hides ordinary source. See Holes.
- Note quality is unmeasured. The owner tries `/plain-diff` and judges the notes.

## What protects it

- `mods/plain-diff/plain-diff.test.mjs`. 72 cases, 72 pass. The red runs are recorded at 658a23c (round 1 tests), 4313f3f (round 2) and f06cbb2 (round 3).

## Review rounds

Three review rounds. Blockers found and fixed:

- A secret bypass through `diff.noprefix`.
- A suffix collision in note matching.
- A regex freeze on long hex lines.
- Missed secrets that end in a semicolon or a comment.
- Git textconv and fsmonitor ran repo programs.

## Holes, named

Each hole ships under the three-round review cap. The last hole was found while writing this record, after the rounds.

- A secret in a form the filter does not know passes. Example: an npm token, `npm_` then 36 letters. Why it ships: rules are added per incident or measured miss.
- The `KEY=value` rule skips all-digit values, values under 8 characters, and values with characters outside `A-Za-z0-9/+_=-`. Examples: `TOKEN=abc.def.ghi.jkl` and `API_KEY=12345678901` both pass. Why it ships: no measured miss, and a wider value class is unmeasured.
- False positives hide ordinary source behind "Skipped: secret file". The figures given are about 1% of this repo's history, and 0.7% of Python's standard library. Those figures are not re-measured here. Examples: `TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"` and `self.tokenizer = tokenizer`. Why it ships: a hidden file is the chosen failure mode.
- Some secret file names are not caught by name. Examples: `terraform.tfstate`, `.kube/config`, `wp-config.php`, `AuthKey_*.p8`. The `.p8` file is caught only when the diff shows its BEGIN line. Why it ships: the name list holds the names known so far.
- A file with `.env` content that git shows as new under an innocent name is not caught by name. Example: a new `notes.txt` that holds `ENCRYPTION_KEY=7f3a9c2e1b8d4f6a`. Why it ships: the content test is the only check on it, and no rule names `ENCRYPTION_KEY`.
- A quoted path with an emoji shows a wrong label, so no turn note matches it. Example: `notes 🙂 "draft".md`, which git quotes because of its double quotes. An emoji in an unquoted path shows the right label. Why it ships: not a blocker, and the three-round cap was reached.
- On a line over 3000 characters, the end-of-line anchor can match at a chunk end. This adds a false positive only. Example: a minified line over 3000 characters with `token` near a chunk end. Why it ships: a false positive hides a file and leaks nothing.
- A call that outlasts the 25 s limiter timeout frees its slot while the host call may still run. Example: a model call that hangs past 25 s. The 20 s model timeout is passed to the host. This repo does not verify that the host honours it. Why it ships: unmeasured.
- The pane draw, and the turn-text match against a real `$.session.messages()`, are untested in the desktop app. Example: a turn that edits `src/app.ts` and names it in its text. Why it ships: the owner tries `/plain-diff` and judges the notes.
- The mockup notes are written by hand. `docs/mockup.html` shows one real diff. Example: the mockup's note for one file is typed, not made by the model. Why it ships: it shows the layout, not model output.
- Untracked files are not shown. The diff base is `HEAD`, or the empty tree when no commit exists. Example: a new file that is not yet `git add`ed. Why it ships: `git diff` lists tracked files only.
- The notes cache lives in memory only. A reload of the mod clears it, so a model note is requested again. Example: `/reload-plugins` after an edit. Why it ships: the code comment accepts the loss.
- Output over the host's limit is cut, and the header says "Diff truncated". This repo sets no such limit. It reads the host's `isStdoutTruncated` flag. The 4 MiB figure is not confirmed in code. Example: a diff too large for one `$.process.run` call. Why it ships: a cut diff is never shown as complete.
- The table-row regex in `trimNote` was quadratic only on absurd input. It was not re-checked after the round 3 fixes. Example: a long line of pipes, dashes and spaces. Why it ships: unmeasured on real input.

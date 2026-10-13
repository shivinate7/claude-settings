# plain-diff sends a diff to a model only past the secret filter

## The question

Does the plain-diff mod (`mods/plain-diff`, command `/plain-diff`) send a changed file's diff to a model? If it does, what stops a secret from going?

## The ruling

The mod sends a diff to `$.model.complete` only for a file that passes the secret filter.

Owner intent: the owner rarely reads diffs. The owner wants a plain-English note for each changed file. No secret leaves the machine.

The filter has two parts:

- A path deny-list. It tests the file name. Examples: `.env`, `*.pem`, `id_rsa`, `credentials.json`.
- A content test. It runs on each line in chunks of 3000 characters. Chunks overlap by 200 characters. It runs on the full diff after control characters are removed. That text holds everything the model receives. It matches known key shapes, such as a private key block. It also matches `KEY=value` lines where the name holds API_KEY, SECRET, PASSWORD, PASSWD or TOKEN.

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

Each hole ships under the three-round review cap.

- A secret in a form the filter does not know passes. Example: a bare token with no key name. Why it ships: rules are added per incident or measured miss.
- The `KEY=value` rule skips all-digit values, values under 8 characters, and values with characters outside `A-Za-z0-9/+_=-`. Example: `TOKEN=abc.def.ghi.jkl` passes. Why it ships: no measured miss, and a wider value class is unmeasured.
- False positives hide ordinary source behind "Skipped: secret file". About 1% of this repo's history, and 0.7% of Python's standard library. Examples: `TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"` and `self.tokenizer = tokenizer`. Why it ships: a hidden file is the chosen failure mode.
- Some secret file names are not caught by name. Examples: `terraform.tfstate`, `.kube/config`, `wp-config.php`, `AuthKey_*.p8`. The `.p8` file is caught only when the diff shows its BEGIN line. Why it ships: the name list holds the names known so far.
- A `.env` file that git shows as new under an innocent name, such as `notes.txt`, is not caught by name. Example: a new `notes.txt` that holds `DATABASE_URL=postgres://user:pass@host/db`. Why it ships: the content test is the only check on it.
- A quoted path with an emoji shows a wrong label, so no turn note matches it. Why it ships: named as a hole at the three-round cap.
- On a line over 3000 characters, the end-of-line anchor can match at a chunk end. This adds a false positive only. Example: a minified line over 3000 characters with `token` near a chunk end. Why it ships: a false positive hides a file and leaks nothing.
- A call that outlasts the 25 s limiter timeout frees its slot while the host call may still run. The 20 s model timeout is passed to the host. This repo does not verify that the host honours it. Why it ships: unmeasured.
- The pane draw, and the turn-text match against a real `$.session.messages()`, are untested in the desktop app. Why it ships: the owner tries `/plain-diff` and judges the notes.
- The mockup notes are written by hand. `docs/mockup.html` shows one real diff. Why it ships: it shows the layout, not model output.
- Untracked files are not shown. The diff base is `HEAD`, or the empty tree when no commit exists. Why it ships: `git diff` lists tracked files only.
- The notes cache lives in memory only. A reload of the mod clears it, so a model note is requested again. Why it ships: the code comment accepts the loss.
- Host output over 4 MiB is cut, and the header says "Diff truncated". The 4 MiB limit is set by the host, not by this repo. Example: a diff over 4 MiB. Why it ships: a cut diff is never shown as complete.
- The table-row regex in `trimNote` was quadratic only on absurd input. It was not re-checked after the round 3 fixes. Example: a long line of pipes, dashes and spaces. Why it ships: unmeasured on real input.

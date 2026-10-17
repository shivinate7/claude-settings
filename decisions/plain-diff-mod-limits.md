# plain-diff sends a diff to a model only past the secret filter

## The ruling

The plain-diff mod (`mods/plain-diff`, command `/plain-diff`) sends a diff to `$.model.complete` only
for a file that passes the secret filter. Reason: the owner wants a plain-English note for each changed
file, and no secret leaves the machine. A false match hides a file. It never sends one.

The filter has two parts:

- A path deny-list on the file name. Examples: `.env`, `*.pem`, `id_rsa`, `credentials.json`.
- A content test on each line, in chunks of 3000 characters with 200 characters of overlap. It runs on
  the full diff after control characters are removed, which is everything the model receives. It matches:
  - A private key block.
  - AWS keys (AKIA, ASIA), GitHub tokens, `sk-` keys, Stripe live keys, Slack tokens and Google API keys.
  - JWTs, URLs with `user:pass@`, and Bearer tokens.
  - A `KEY=value` line where the name holds API_KEY, SECRET, PASSWORD, PASSWD or TOKEN.

The rules:

- The filter runs before any model call. It tests the new path and the old path of a rename.
- A skipped file shows "Skipped: secret file" and no diff. Nothing from the file is kept, shown or sent.
- A note from Claude's own turn text passes the same content test. A turn text that holds a secret gives
  no note. A turn-text note wins over a model note and costs no model call.
- Model calls are capped at 5 per run. One limiter is shared by all runs. It counts calls while any call
  is in flight, and it resets when none is. A file past the cap shows "No note: model limit or timeout".
- Each model call has a 20 s timeout. The shared limiter frees a call's slot after 25 s.
- Git calls use `--src-prefix=a/`, `--dst-prefix=b/`, `--no-ext-diff`, `--no-textconv` and
  `-c core.fsmonitor=false`. A repo's own diff programs and fsmonitor command do not run.
- Notes are plain text. Markdown links reduce to their label and URL without the scheme. HTML is
  escaped. Control characters are stripped.
- Notes are cached in memory only, keyed by path and diff hash. A reload of the mod clears the cache.

Files: `mods/plain-diff/hooks/lib.mjs` (`isSecretPath`, `looksSecret`, `makeLimiter`, `trimNote`,
`gitDiffArgs`) and `mods/plain-diff/hooks/register.mjs`. Details: `mods/plain-diff/README.md`, Secret
files section.

Kind: build
Plan: decisions/plain-diff-mod-limits.md#the-ruling (all)
Home: mods/plain-diff/hooks/register.mjs

## Named limits

- A secret in a form the filter does not know passes. An npm token (`npm_` then 36 letters) is an
  example. Rules are added per incident or measured miss.
- False positives hide ordinary source behind "Skipped: secret file". A hidden file is the chosen failure
  mode. The figures, about 1% of this repo's history and 0.7% of Python's standard library, are not
  re-measured.
- Note quality is unmeasured. The owner tries `/plain-diff` and judges the notes.
- The mockup notes in `docs/mockup.html` are typed by hand. They show the layout, not model output.
- Untracked files are not shown. The diff base is `HEAD`, or the empty tree when no commit exists.

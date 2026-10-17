# plain-diff sends a diff to a model only past the secret filter

## The ruling

The plain-diff mod (`mods/plain-diff`, command `/plain-diff`) sends a diff to `$.model.complete` only
for a file that passes the secret filter. Reason: the owner wants a plain-English note for each changed
file, and no secret leaves the machine. A false match hides a file. It never sends one. A hidden file is
the chosen failure mode.

The filter has two parts:

- A path deny-list on the file name. Examples: `.env`, `*.pem`, `id_rsa`, `credentials.json`.
- A content test on each line of the full diff, after control characters are removed. That is
  everything the model receives. It matches:
  - A private key block, common cloud and API tokens, JWTs, URLs with `user:pass@`, and Bearer tokens.
  - A `KEY=value` line where the name holds API_KEY, SECRET, PASSWORD, PASSWD or TOKEN.

A secret in a form the filter does not know passes. Rules are added per incident or measured miss.

The rules:

- The filter runs before any model call. It tests the new path and the old path of a rename.
- A skipped file shows "Skipped: secret file" and no diff. Nothing from the file is kept, shown or sent.
- A note from Claude's own turn text passes the same content test. A turn text that holds a secret gives
  no note. A turn-text note wins over a model note and costs no model call.
- Model calls are capped at 5 per run. One limiter is shared by all runs. A file past the cap shows "No
  note: model limit or timeout". Each model call has a 20 s timeout.
- Git calls use `--src-prefix=a/`, `--dst-prefix=b/`, `--no-ext-diff`, `--no-textconv` and
  `-c core.fsmonitor=false`. A repo's own diff programs and fsmonitor command do not run.
- Notes are plain text. Markdown links reduce to their label and URL without the scheme. HTML is
  escaped. Control characters are stripped.
- Notes are cached in memory only, keyed by path and diff hash. A reload of the mod clears the cache.
- The diff base is `HEAD`, or the empty tree when no commit exists. Untracked files are not shown.

Details: `mods/plain-diff/README.md`, Secret files section.

Kind: build
Plan: decisions/plain-diff-mod-limits.md#the-ruling (all)
Home: mods/plain-diff/hooks/register.mjs

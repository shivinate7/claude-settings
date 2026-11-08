# A delete of a branch runs only after its archive push succeeded

## The question

When one command archives a remote branch and then deletes it, what must stop the delete if the archive push fails?

## The ruling

Rule `archive-then-delete` in `hooks/guard.py` refuses a remote branch delete (`git push --delete b`, `git push origin :b`) that follows an archive push of the same branch (a refspec whose destination is `archive/<name>` or `refs/heads/archive/<name>`) when the push's failure does not stop the chain first. Rule `shared-trees-archive-then-delete` says the delete is lossless only after the push succeeds.

1. A delete pairs with the nearest earlier archive push of its name. Names match after quotes are cut, `${x}` is read as `$x`, and `refs/heads/` is cut. An archive push whose branch word holds a `$` variable (a loop) pairs with any later delete. A delete with no same-name archive push keeps its old verdict.
2. The push's failure stops the chain in these forms, and the delete is then allowed:
   - every end from the push to the delete is `&&` (a `|` in a middle segment passes), also when the push ends a brace group: `{ push; } && delete`;
   - `|| exit` follows the push, or `|| { …; exit 1; }`; `|| continue` and `|| break` count only in a loop body holding the delete; `|| return` only in a function body holding the delete;
   - the push is in an `if` condition, and the delete is in its success branch: the `then` branch of `if push`, or the `else` branch of `if ! push`;
   - or the delete follows the `fi`, and the failure branch stops: `if ! push; then <exit, continue, break or return>; fi`, or `if push; then …; else <exit, continue, break or return>; fi` with no `elif`. Each stop word follows the loop and function rules above;
   - `set -e` (or `set -o errexit`) came earlier and the push ends with `;` or a newline.
   A pipe on the push hides its status unless `set -o pipefail` came earlier too.
3. A `;`, a newline, a `||` with no stop word, or a pipe on the archive push breaks the chain, and the delete is refused. At top level `|| continue`, `|| break` and `|| return` stop nothing.
4. Rule `zsh-var-modifier` refuses a `git push` word with an unbraced `$name:` and a letter after it. zsh reads `:r`, `:a`, `:e` there as a modifier (zsh manual, Parameter Expansion, Modifiers), so `$b:archive/$b` sends another word. The remedy is `${name}:`. Only `git push` calls are read, through `git_calls` and `_push_parse`, so `docker push $IMG:latest` is silent. Measured only by the manual: the container has no zsh.
5. Both rules are POSIX only: a PowerShell call is not judged. Not read: `bash -c` bodies, heredocs, script files, PowerShell, `gh api -X DELETE …/git/refs/heads/…`. Nor is one push call that archives and deletes in one refspec list without `--atomic` read (`guard-guards-mistakes-only`). Read wrongly, by design of the first build: a subshell `( … || exit 1 )` counts as stopping the chain, though `exit` leaves only the subshell. A `set -e` before an earlier `if` counts as stopping it. A lone `&` does not split a command. Each is a line in `docs/debts/notes.md`.

Risk kind: likely risk. Incident 2026-11-07: zsh read `$b:r` as a filename modifier, so six archive pushes failed. `| tail` hid each failure, and the delete after them removed six branches on GitHub with no archive copy.
The harm: lost work on branches with no copy.

Kind: process
Home: hooks/guard_push_delete.py

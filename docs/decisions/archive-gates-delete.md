# An archive push gates the delete of its branch

## The question

When one command archives a remote branch and then deletes it, what must stop the delete if the archive push fails?

## The ruling

Rule `archive-gates-delete` in `hooks/guard.py` refuses a remote branch delete (`git push --delete b`, `git push origin :b`) that follows an archive push of the same branch (a refspec whose destination is `archive/<name>` or `refs/heads/archive/<name>`) when the push's failure does not stop the chain first. Rule `shared-trees-archive-then-delete` says the delete is lossless only after the push succeeds.

1. A delete pairs with the nearest earlier archive push of its name. Names match after quotes are cut, `${x}` is read as `$x`, and `refs/heads/` is cut. A delete with no same-name archive push keeps its old verdict.
2. The push's failure stops the chain when every end from the push to the delete is `&&` (a `|` in a middle segment passes); when `|| exit`, `|| return`, `|| continue` or `|| break` follows the push; when the push is the condition of an `if` and the delete is in its `then` branch; or when `set -e` (or `set -o errexit`) came earlier and the push ends with `;` or a newline. A pipe on the push hides its status unless `set -o pipefail` came earlier too.
3. A `;`, a newline, a `||` with no exit, or a pipe on the archive push breaks the gate, and the delete is refused.
4. Rule `zsh-var-modifier` refuses a `git push` word with an unbraced `$name:` and a letter after it. zsh reads `:r`, `:a`, `:e` there as a modifier (zsh manual, Parameter Expansion, Modifiers), so `$b:archive/$b` sends another word. The remedy is `${name}:`. Measured only by the manual: the container has no zsh.
5. Both rules are POSIX only: a PowerShell call is not judged. Not read: `bash -c` bodies, heredocs, script files, PowerShell, `gh api -X DELETE …/git/refs/heads/…`, and one push call that archives and deletes in one refspec list without `--atomic` (`guard-guards-mistakes-only`; each is a line in `docs/debts/notes.md`).

Risk kind: likely risk. Incident 2026-11-07: six archive pushes failed because zsh read `$b:r` as a filename modifier, `| tail` hid each failure, and the delete after them removed six branches on GitHub with no archive copy.
The harm: lost work on branches with no copy.

Kind: process
Home: hooks/guard_push_delete.py

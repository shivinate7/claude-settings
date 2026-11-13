# A remote branch delete after its archive push runs only when `&&` gates it

## The ruling

Rule `archive-push-gates-delete` in `hooks/guard.py` refuses a remote branch delete that follows an archive push of the same branch in one command. It runs only when `&&` joins every step from the push to the delete. The delete is `git push --delete origin <b>` or `git push origin :<b>`. The archive push is a refspec whose destination is `archive/<name>`.

1. The mistake: in the Degen repo, a loop ran `git push origin "origin/$b:refs/heads/archive/$b" 2>&1 | tail -1; git push origin --delete $b` under zsh, where `$b:r` also expands as a modifier. The `| tail` hid each failed archive push and the `;` ran the delete anyway. Six branches were deleted with no archive copy. They were restored from a local clone, by luck.
2. The harm stopped: a branch deleted on the remote after its archive push failed, which loses it with no copy (rule `shared-trees-archive-then-delete`).
3. Only `&&` gates the delete on the push's exit status. A `;`, a newline, `||` or a pipe ends or hides that status, and each is refused. A pipe followed by `&&` is refused too, since `&&` then reads the last pipe stage, not the push.
4. A push and a delete pair when they name the same branch by text. `${b}` folds to `$b`, and `$b` pairs with `$b` by equality, with no expansion read.
   - An explicit source names its own branch alone. `origin/<name>` is `<name>`, whatever the archive name is.
   - A `HEAD` or `@` source names no branch. The archive name stands for it, with and without a `-N` suffix.
   - A delete of a branch pairs only with its own archive push, never with the archive push of another branch.
   - An archive push with an empty name (`HEAD:archive/`) pairs with nothing.
   - The shape of a taken name is `ARCHIVE_COPY_SUFFIX`, the one home that `hooks/guard_merge.py` also reads for its copy check.
5. The remedy names `&&`. Retry with the delete joined to the push by `&&` alone.
6. The check runs for POSIX shells only. It reads segments through `split_segments`, so a quoted `;` is text.

Named limits (`guard-guards-mistakes-only`):

- `if git push ...; then git push --delete ...; fi`, `set -e`, and `git push ... || exit` gate the delete and are still refused. One retry with `&&` fixes each.
- One push that carries both refspecs (`git push origin HEAD:archive/x :x`) never pairs. Git sends both refs in one call and the pair is not read. It stays a note.
- `bash -c` bodies, heredocs, script files and PowerShell are not read.

Risk kind: likely risk. The loop was written in normal work.

Kind: process
Home: rule:shared-trees-archive-then-delete

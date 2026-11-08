# Every PR opens as a draft, and CI skips drafts

## The ruling

Owner, 2026-10-10 and 2026-10-13: every PR opens as a draft, and CI skips draft PRs. Lane PRs stay drafts. Only one integration PR per batch goes ready, and its run is the batch's only CI run (`git-integration-branch-merge`).

- Guard rule `draft-pr` refuses `gh pr create` without `--draft` or `-d`. It reads `sh -c` scripts, command substitutions and subshells. The last `--draft`, `-d` or `--draft=X` wins. A value is true only in gh's ParseBool true set (1, t, T, TRUE, true, True).
- The guard also refuses the MCP tool `mcp__github__create_pull_request` unless its input has `draft: true`.
- `checks.yml` runs on `opened`, `synchronize`, `reopened` and `ready_for_review`. The `scope` job skips when the PR is a draft. Each other job needs `scope`, so each skips too. Push to main, schedule and manual runs are unchanged.
- The `concurrency` group holds the PR draft state (`format('{0}-{1}', github.ref, github.event.pull_request.draft)`), so a draft run replaces only draft runs and a ready run only ready runs. Turning off cancel for drafts is not enough: GitHub keeps one pending run per group and replaces it even with `cancel-in-progress: false`. Snippet 4 of skill ci-hygiene carries the same expression.
- The merge tool never merges a draft pull request. On a draft, `--confirm` is the records page step and stops before any claim, wait or merge (`records-index-at-merge`). It reads the draft state at the start and again under the merge lock.
- A job skipped by `if:` reports as passing, unless an `all-jobs-passed` rollup needs it (skill ci-hygiene, "Before you skip a required job"). A draft needs no check, because GitHub does not merge a draft. Marking it ready fires `ready_for_review`, with the same scoped range as a `synchronize` run (`.github/scripts/ci-scope.sh`). A skipped draft run satisfies each required check (`main-branch-protection`, the one home of required-check state). The merge tool refuses a head whose checks all skipped.

Why: a draft run that arrives while a ready run is in progress cancels it, and a pending ready run is replaced. Pushes to a PR branch also spent CI on commits known to be red.

Limits:

- A shell-run heredoc body is read whole. An unquoted body's `$(` is read, because bash runs it while writing the file.
- A quoted body that python, perl, ruby or node runs is not read as shell lines. A bare `gh pr create` line in a body with no backtick is allowed.
- A quoted perl, ruby or node body with any backtick is read whole, split at each backtick. A body with none is not read.
- A body that python alone runs adds no text, even with a backtick. Python can still hand text to a shell through `os.system`, which the guard does not read.
- A body piped into a shell (`python3 - <<'EOF' | sh`) is read only when the body itself holds the words as shell text. A body that only prints them is allowed, as on main.
- Each body is judged by its own stage of the header line, or for a written file by the stages that run it.
- Words decide who runs a body, never a path. A file named `python/t.pl` that perl runs is read, and a written file's own name is no runner.
- Perl and ruby run a backtick span as a shell. Node does so through `execSync` and the like.
- The guard pairs no backticks, so a lone backtick in a string cannot hide a real span.
- A false alarm exists: a backtick span in a perl, ruby or node body that runs nothing is refused. A perl print of a string holding a span is one.
- The impeccable rule shares this read.
- A written file run through a known wrapper word (`env python3 f`, `sudo python3 f`) or as `./f` keeps its body read.
- A body fed to python on stdin stays python's, even behind a known wrapper word.
- A runner word the guard does not know in front of python (`stdbuf -o0 python3 f.py`) leaves the body python's, so it is allowed.
- A runner word outside the guard's interpreter list (ash, nodejs, perl5.36) is not known, so `python3 f.py && ash f.py` is allowed.
- An unknown runner drops the body, as on main, for a non-.sh file name and for stdin. A .sh name stays read, so `mysh f.sh` is refused.
- A PowerShell here-string is read as shell lines when `iex` or `Invoke-Expression` takes it after a space.
- It is also read when `[scriptblock]::Create(` builds a block from it, or when `pwsh` or `powershell` takes it after `-Command` or `-c`.
- It is also read when it is piped into `iex`, `Invoke-Expression`, or a pwsh that reads stdin (`| & pwsh -`), with any `Out-String` stages between.
- Not read: `iex(@"`, `Create (@"`, a pwsh switch the guard does not know before the stdin dash, and `ForEach-Object { iex $_ }`. Main reads none of them.
- Not read: a pipe split across lines before `iex`, `iex ("" + @"…"@)`, and a here-string written with `Set-Content` and run later.
- A here-string given to `Set-Content` is allowed.
- A rare false alarm: `Write-Output iex @'…'@` is refused, because the word `iex` sits before the here-string.
- Another rare false alarm: `pwsh -File x.ps1 -c @"…"@` and `pwsh x.ps1 -c @"…"@` are refused. Any earlier `-c` counts, even a script's own argument.
- Not read, as on main: a pwsh named by path before `-c` (`/usr/bin/pwsh -c @"`), and `pwsh -c:@"`.
- A here-string given to a POSIX shell's `-c` (`bash -c`, `sh -c`, `bash -lc`) is read, behind `sudo` or `timeout N` too.
- Not read, as on main: a here-string piped to `bash`, or given to `cmd /c`.
- Not followed: a `Set-Content` file that bash or pwsh runs later.
- A here-string held in a variable is not read, even when a later line runs it (`iex $b`, `$b | iex`). Main allows it too.
- The guard does not judge a `gh api` POST to the pulls endpoint, or `hub pull-request`. Each can open a non-draft PR.
- A short-flag cluster such as `-dt x` is refused, a rare false alarm.
- A pull request that turns draft during the merge wait is not stopped.
- Unmeasured: that `ready_for_review` starts this workflow (it comes from GitHub's documented behavior), and the saving in runs.

Kind: process
Home: hooks/guard.py

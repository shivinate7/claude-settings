# section 6590
FAMILY = "stream"
#
# A follow flag never ends on its own, so it outlives the turn and the agent that started it.

sh("stream: tail -f never ends", "tail -f app.log", "deny", "live-stream", cwd=NOGIT)
sh("stream: tail -F retries across rotation", "tail -F app.log", "deny", "live-stream", cwd=NOGIT)
sh("stream: the long follow flag", "tail --follow=name app.log", "deny", "live-stream", cwd=NOGIT)
sh("stream: a combined short flag", "tail -fn 20 app.log", "deny", "live-stream", cwd=NOGIT)
sh("stream: Get-Content -Wait never ends", "Get-Content app.log -Wait", "deny", "live-stream",
   tool="PowerShell", cwd=NOGIT)

sh("stream: an ordinary line count", "tail -n 50 app.log", "allow", cwd=NOGIT)
sh("stream: a short line count", "tail -5 app.log", "allow", cwd=NOGIT)
sh("stream: a pipe into a bounded tail", "python x.py | tail -5", "allow", cwd=NOGIT)
sh("stream: Get-Content -Tail reads and stops", "Get-Content app.log -Tail 20", "allow",
   tool="PowerShell", cwd=NOGIT)

# A follow flag in a loop's do-block is still the command word's own flag: the loop keyword and the
# wrappers are skipped before the command word is read. Pinned so reading the command word, not every
# token, does not let the do-block through.
sh("stream: tail -f inside a loop's do-block denies unchanged",
   "while true; do tail -f app.log; done", "deny", "live-stream", cwd=NOGIT)

# The rule reads every token of a segment, not the
# command word, so a command that only NAMES `tail` or `Get-Content` before a flag is a false alarm:
# a commit message or a note that names the refused form, and `grep ... tail -F`, where -F is grep's
# fixed-string flag. Claude writes the first two whenever it works on this rule.
for _name, _command in (
    ("a commit message that names tail -f", VCS + ' commit -m "Refuse tail -f in the guard"'),
    ("a commit message that names Get-Content -Wait",
     VCS + ' commit -m "Refuse Get-Content -Wait on logs"'),
    ("an echo that names tail -f", 'echo "never tail -f app.log"'),
    ("grep for tail with -F after the pattern", "grep -rn tail -F hooks/"),
):
    sh("stream: false alarm: " + _name + " is no follow", _command, "allow", cwd=NOGIT)
# A follow behind a wrapper, a path or a later command stays refused (`bash -c` and `ssh host` forms are not pinned).
for _name, _command in (
    ("behind sudo", "sudo tail -f app.log"),
    ("behind env and an assignment", "env X=1 tail -f app.log"),
    ("by absolute path", "/usr/bin/tail -f app.log"),
    ("as the second command", "cd logs && tail -f app.log"),
):
    sh("stream: tail -f " + _name + " still denies", _command, "deny", "live-stream", cwd=NOGIT)

# A follow run via a container or pod exec, find -exec, a remote or nested shell, or a wrapper (stdbuf, flock, ...).
for _name, _command in (
    ("behind docker exec", "docker exec c tail -f x"),
    ("behind podman exec", "podman exec c tail -f x"),
    ("behind kubectl exec and --", "kubectl exec p -- tail -f x"),
    ("behind find -exec", "find . -exec tail -f {} \\;"),
    ("behind ssh and docker exec", "ssh host docker exec c tail -f x"),
    ("behind sh -c around ssh", "sh -c 'ssh host tail -f x'"),
    ("behind stdbuf", "stdbuf -oL tail -f x"),
    ("behind unbuffer", "unbuffer tail -f x"),
    ("behind caffeinate", "caffeinate tail -f x"),
    ("behind flock", "flock F tail -f x"),
):
    sh("stream: tail -f " + _name + " denies", _command, "deny", "live-stream", cwd=NOGIT)
# A quoted pattern that names the follow is a search, not a follow.
sh("stream: grep for the text tail -f in a file is no follow", "grep 'tail -f' notes.txt", "allow",
   cwd=NOGIT)

# A wrapper with options or a subcommand ahead of the command (`docker run --rm alpine`), or no skip rule (watch, uv run).
for _name, _command in (
    ("behind docker run with an option", "docker run --rm alpine tail -f /dev/null"),
    ("behind docker-compose exec", "docker-compose exec web tail -f log"),
    ("behind docker compose run", "docker compose run web tail -f log"),
    ("behind docker compose -f exec", "docker compose -f x.yml exec web tail -f log"),
    ("behind docker --context exec", "docker --context x exec c tail -f x"),
    ("behind kubectl run and --", "kubectl run x --image=a -- tail -f /dev/null"),
    ("behind kubectl exec without --", "kubectl exec pod tail -f x"),
    ("behind gtimeout", "gtimeout 5 tail -f x"),
    ("behind watch", "watch tail -f x"),
    ("behind uv run", "uv run tail -f x"),
):
    sh("stream: tail -f " + _name + " denies", _command, "deny", "live-stream", cwd=NOGIT)
# A wrapper around a bounded command, and text that names the follow, are no follow.
for _name, _command in (
    ("an echo that names the follow", "echo 'tail -f log'"),
    ("docker run around a bounded command", "docker run --rm alpine ls"),
    ("uv run around a bounded command", "uv run pytest"),
    ("kubectl exec around a bounded command", "kubectl exec pod -- cat log"),
):
    sh("stream: " + _name + " is no follow", _command, "allow", cwd=NOGIT)

# SCANNER PINS (rule building-scanner-respects-strings) for the fallback that reads a segment shlex
# cannot parse, word by word (guard_stream.py, live_stream_hit). Three constructs a scanner can
# get wrong: a comment opener inside quotes, a quoted string over several lines, and a lone
# apostrophe in plain text (the text of a shell line that is not a quoted string at all).
# DENY: each construct sits ahead of a real follow, and none may hide it. The `it's`
# rows leave the segment unparseable, so the fallback reads them.
for _name, _command in (
    ("a # inside quotes ahead of it", 'echo "a # b"; tail -f app.log'),
    ("a # inside quotes and a lone apostrophe ahead of it", 'echo "# x" it\'s; tail -f app.log'),
    ("a // inside quotes ahead of it", 'echo "a // b"; tail -f app.log'),
    ("a /* inside quotes ahead of it", 'echo "/* x"; tail -f app.log'),
    ("a multi-line quote ahead of it", 'echo "first line\nsecond line"\ntail -f app.log'),
    ("a multi-line quote and a lone apostrophe ahead of it",
     'echo "a\nb" it\'s\ntail -f app.log'),
    ("a lone apostrophe ahead of it", "echo don't; tail -f app.log"),
    ("a lone apostrophe in a trailing comment", "tail -f app.log # don't"),
):
    sh("stream: tail -f behind " + _name + " denies", _command, "deny", "live-stream", cwd=NOGIT)
# ALLOW: the same constructs around text that follows nothing.
for _name, _command in (
    ("a # inside quotes", 'echo "# tail -f app.log"'),
    ("a multi-line quote", 'echo "first line\ntail -f app.log\nlast line"'),
    ("a lone apostrophe in text", "echo it's fine"),
    ("a lone apostrophe in a trailing comment", "tail -n 5 app.log # don't"),
):
    sh("stream: scanner: " + _name + " is no follow", _command, "allow", cwd=NOGIT)


# =========================================================================== 2c. shell traps
#
# Three traps ported from banchi's `scripts/guard-shell.py`. Each has a red case, an allowed case,
# and two false-alarm cases: a command that reads like the trap and is not it. Each is judged on the
# act (the command word, the flags, what the path or the branch resolves to), never on a substring.

# --- a narrating command piped into tail (extends the live-stream rule)
sh("narrate: merge --confirm piped to tail hides its heartbeat",
   "merge 12 --confirm 2>&1 | tail -18", "deny", "live-stream", cwd=NOGIT)
sh("narrate: the script run by path, piped to head",
   "~/.claude/bin/merge 12 --confirm | head -5", "deny", "live-stream", cwd=NOGIT)
sh("narrate: the launcher script run through python, piped to tail",
   "python merge/launch.py 12 --confirm 2>&1 | tail -5", "deny", "live-stream", cwd=NOGIT)
sh("narrate: a versioned python runs the merge script, piped to tail",
   "python3.11 merge/merge.py 12 --confirm | tail -3", "deny", "live-stream", cwd=NOGIT)
sh("narrate: uv run python runs the merge script, piped to tail",
   "uv run python merge/merge.py 12 --confirm 2>&1 | tail -3", "deny", "live-stream", cwd=NOGIT)
sh("narrate: --confirm on a command off the roster", "deploy 12 --confirm 2>&1 | tail -5",
   "allow", cwd=NOGIT)
sh("narrate: a merge preview is not a wait", "merge 12 2>&1 | tail -5", "allow", cwd=NOGIT)
sh("narrate: tee keeps every byte", "merge 12 --confirm 2>&1 | tee run.out", "allow", cwd=NOGIT)
sh("narrate: an ordinary command piped to tail", "make check 2>&1 | tail -40", "allow", cwd=NOGIT)
sh("narrate: tail of a file, no pipe", "tail -n 5 notes.txt", "allow", cwd=NOGIT)
sh("narrate: merge --confirm named in a quoted argument runs nothing",
   "echo 'merge 12 --confirm' | tail -1", "allow", cwd=NOGIT)

# --- a pipe out of a verdict stage (extends the live-stream rule)
#
# verdict prints its FAIL line first, and a pipe cuts it off. A pipeline's exit is its last stage's,
# so `verdict CMD | tail` reads tail's exit and a red run reads 0. Any pipe out of verdict is refused,
# whatever the filter. A verdict that is the last stage has no pipe out of it, so it is allowed.
VERDICT_PIPE = "verdict-pipe"


def verdict_pipe(name, command, expected):
    """One case of the verdict-pipe rule. A deny names the rule; an allow has no reason to name it."""
    sh("verdict-pipe: " + name, command, expected, VERDICT_PIPE if expected == "deny" else None,
       cwd=NOGIT)


for _name, _command in (
    ("a bare verdict piped to tail", "verdict false | tail"),
    ("stderr piped to grep", "verdict false 2>&1 | grep x"),
    ("a pipe into tee", "verdict false | tee out"),
    ("the script run by path, piped to tail", "~/.claude/bin/verdict pytest | tail -5"),
    ("a variable ahead of verdict, piped to head", "VERDICT_LOG=/tmp/x verdict false | head"),
    ("a cd ahead of verdict, piped to tail", "cd x && verdict false | tail"),
    ("a pipe that takes stderr too, |&", "verdict false |& tail"),
    ("the repo's runner form, piped to tail", "python bin/verdict pytest | tail -5"),
    ("a timeout ahead of verdict, piped to tail", "timeout 600 verdict pytest | tail -5"),
    ("a lone apostrophe ahead of it", "echo don't; verdict false | tail"),
    ("a # inside quotes ahead of it", 'echo "a # b"; verdict false | tail'),
    ("a multi-line quote ahead of it", 'echo "first line\nsecond line"\nverdict false | tail'),
    ("a pipe at a line end, then tail", "verdict x |\ntail -5"),
    ("a pipe in a command substitution, to tail", "x=$(verdict pytest | tail -5)"),
    ("a pipe in a double-quoted substitution, to tail", 'echo "$(verdict x | tail)"'),
    ("a pipe in bash -c, to tail", "bash -c 'verdict x | tail'"),
    ("a pipe in sh -c, to head", 'sh -c "verdict x | head"'),
    ("the .cmd runner, piped to tail", "verdict.cmd pytest | tail -5"),
):
    verdict_pipe(_name, _command, "deny")
for _name, _command in (
    ("a bare verdict", "verdict false"),
    ("verdict then a second command, &&", "verdict x && y"),
    ("verdict then echo, ||", "verdict x || echo red"),
    ("output redirected to a file", "verdict x > out"),
    ("a quoted pipe in verdict's own argument", "verdict grep 'a|b' f"),
    ("a quoted script in verdict's own argument", "verdict bash -c 'a | b'"),
    ("grep names verdict, pipe out of grep", "grep verdict f | tail"),
    ("echo names verdict, pipe out of echo", "echo verdict | cat"),
    ("verdict last in a pipeline", "cat f | verdict pytest"),
    ("the whole pipe quoted as text", 'echo "verdict false | tail"'),
    ("a pipe inside a comment", "verdict false # don't | tail"),
    ("command -v names verdict, piped to head", "command -v verdict | head -1"),
    ("type names verdict, piped to head", "type verdict | head -1"),
    ("a substitution that runs verdict, no pipe", "x=$(verdict pytest)"),
    ("bash -c runs verdict, no pipe", "bash -c 'verdict x'"),
):
    verdict_pipe(_name, _command, "allow")

# --- ln -s onto a directory that is already there
sh("ln: -s over a real directory nests the link inside it",
   "ln -s /opt/tool/realdir realdir", "deny", "ln-over-directory", cwd=TRAPLN)
if LINKS_MADE:
    sh("ln: -sf over a link to a directory descends into it",
       "ln -sf /opt/tool/linkdir linkdir", "deny", "ln-over-directory", cwd=TRAPLN)
    sh("ln: -sfn replaces a link to a directory", "ln -sfn /opt/tool/linkdir linkdir", "allow",
       cwd=TRAPLN)
    sh("ln: -sf over a link to a file replaces the link, as -f says",
       "ln -sf /opt/tool/other linkfile", "allow", cwd=TRAPLN)
sh("ln: a free name", "ln -s /opt/tool/x brand-new", "allow", cwd=TRAPLN)
sh("ln: a trailing slash says the destination is a directory",
   "ln -s /opt/tool/x realdir/", "allow", cwd=TRAPLN)
sh("ln: a hard link over a directory name is not symbolic", "ln /opt/tool/x realdir", "allow",
   cwd=TRAPLN)

# --- a roster command piped into tail or head (rule check-tail)
#
# A backgrounded `merge --lane-lint 1476 2>&1 | tail -8` loses its verdict (decision
# background-check-through-verdict holds the incident). The roster is named, one spelling per entry: `merge`, `merge.cmd`,
# `~/.claude/bin/merge`, `python merge/merge.py`, `python merge/launch.py`, and `ci-job checks --lint`.
# `merge --lane-lint` and `merge --review-record` are refused in the foreground and in the background.
# `ci-job` is refused only in the background. The whole pipeline is read, so a filter between the check
# and tail or head does not hide it. A `tee` stage does not end the check's reach: a tee before tail or
# head is refused, since tail still cuts what the agent reads. A tee with nothing after it is allowed. A pipe out of `verdict` is
# refused by rule verdict-pipe (decision verdict-pipe-refused), so those rows name that rule. A verdict
# call with no pipe after it is allowed here.
# Every backgrounded case names an until note, so background-end decides none of them. sh() takes no
# run_in_background, so the backgrounded cases use add(), the form the background-end section uses.
TAIL_BG_UNTIL = "Lane lint in the background. until: the lint prints its verdict"

add("check-tail: the incident line, backgrounded, is refused", "deny",
    "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="~/.claude/bin/merge --lane-lint 1476 2>&1 | tail -8")
add("check-tail: merge --lane-lint piped to head, backgrounded, is refused", "deny",
    "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="merge --lane-lint 7 | head -5")
add("check-tail: merge.cmd --lane-lint piped to tail, backgrounded, is refused", "deny",
    "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="merge.cmd --lane-lint 7 2>&1 | tail -3")
add("check-tail: the script run through python piped to tail, backgrounded, is refused",
    "deny", "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="python merge/merge.py --lane-lint 7 2>&1 | tail -3")
add("check-tail: the launcher run through python piped to head, backgrounded, is refused",
    "deny", "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="python merge/launch.py --lane-lint 7 | head -3")
add("check-tail: ci-job checks --lint piped to tail, backgrounded, is refused", "deny",
    "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="~/.claude/bin/ci-job checks --lint --base origin/main 2>&1 | tail -20")
add("check-tail: a quoted # does not hide a roster command after it, backgrounded, is refused",
    "deny", "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command='echo "# lint"; merge --lane-lint 7 | tail -3')
add("check-tail: a lone apostrophe in quotes does not hide a roster command, backgrounded, is refused",
    "deny", "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command='echo "it\'s up"; merge --lane-lint 7 2>&1 | tail -3')
add("check-tail: merge --lane-lint through grep -v and tail, backgrounded, is refused", "deny",
    "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="merge --lane-lint 1476 2>&1 | grep -v DEBUG | tail -8")

# A pipe out of verdict is refused by verdict-pipe, which runs before check-tail. The same call with
# no pipe keeps the point these rows had: the verdict form is not a check-tail refusal.
add("verdict-pipe: the incident line through verdict piped to tail, backgrounded, is refused", "deny",
    "verdict-pipe", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="~/.claude/bin/verdict ~/.claude/bin/merge --lane-lint 1476 2>&1 | tail -8")
add("check-tail: the incident line through verdict with no pipe, backgrounded, is allowed", "allow",
    cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="~/.claude/bin/verdict ~/.claude/bin/merge --lane-lint 1476 2>&1")
add("verdict-pipe: a python3 verdict wrapper piped to tail, backgrounded, is refused", "deny",
    "verdict-pipe", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="python3 ~/.claude/bin/verdict merge --lane-lint 1476 | tail -3")
add("check-tail: a python3 verdict wrapper with no pipe, backgrounded, is allowed", "allow",
    cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="python3 ~/.claude/bin/verdict merge --lane-lint 1476")
add("check-tail: wait-pid piped to tail, backgrounded, is allowed", "allow",
    cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="~/.claude/bin/wait-pid 1836 2>&1 | tail -3")
add("check-tail: output kept in a file, then grep piped to tail, backgrounded, is allowed",
    "allow", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="~/.claude/bin/merge --lane-lint 1476 > /tmp/x/lanelint.log 2>&1; echo \"rc=$?\"; "
            "grep -E '^(PASS|FAIL)' /tmp/x/lanelint.log | tail -15")
add("check-tail: merge --lane-lint piped to tee, backgrounded, is allowed", "allow",
    cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="merge --lane-lint 1476 2>&1 | tee run.out")
add("check-tail: a tee between the check and grep and tail, backgrounded, is refused", "deny",
    "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="merge --lane-lint 1476 2>&1 | tee x | grep FAIL | tail -3")
add("check-tail: merge --lane-lint through tee and tail, backgrounded, is refused", "deny",
    "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="merge --lane-lint 7 2>&1 | tee lint.log | tail -5")
add("check-tail: ci-job checks --lint through tee and head, backgrounded, is refused", "deny",
    "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="~/.claude/bin/ci-job checks --lint --base origin/main 2>&1 | tee lint.log | head -20")
add("check-tail: merge --lane-lint through tee with nothing after it, backgrounded, is allowed", "allow",
    cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="merge --lane-lint 7 2>&1 | tee lint.log")
add("check-tail: grep naming the script, piped to tail, backgrounded, is allowed", "allow",
    cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command='grep -n "--lane-lint" merge/merge.py | tail -20')
add("check-tail: an ordinary command piped to tail, backgrounded, is allowed", "allow",
    cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="make check 2>&1 | tail -40")
add("check-tail: a roster name inside echo's quotes, backgrounded, is allowed", "allow",
    cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="echo 'merge --lane-lint 1' | tail -1")
add("check-tail: a roster name after a quoted #, backgrounded, is allowed", "allow",
    cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command='echo "# merge --lane-lint 1 | tail -3"')
add("check-tail: a roster name in a multi-line quote, backgrounded, is allowed", "allow",
    cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command='echo "first line\nmerge --lane-lint 1 | tail -3\nlast line"')
# Wrapper forms (`uv run`, a versioned python, a `VAR=x` prefix) read as the bare spellings do. The
# allow cases name calls a wider match must not refuse: a pytest run and a grep that names the script.
add("check-tail: uv run ci-job checks --lint piped to tail, backgrounded, is refused", "deny",
    "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="uv run ci-job checks --lint 2>&1 | tail -20")
add("check-tail: env VAR=x then ci-job checks --lint piped to tail, backgrounded, is refused",
    "deny", "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="env CI=1 ~/.claude/bin/ci-job checks --lint | tail -5")
add("check-tail: python3 runs the ci-job script piped to tail, backgrounded, is refused",
    "deny", "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="python3 bin/ci-job checks --lint | tail -5")
add("check-tail: python3 -W ignore runs the ci-job script piped to tail, backgrounded, is refused",
    "deny", "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="python3 -W ignore bin/ci-job checks --lint | tail -5")
add("check-tail: uv run python -m pytest piped to tail, backgrounded, is allowed", "allow",
    cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="uv run python -m pytest | tail -5")
add("check-tail: uv run grep naming the script piped to tail, backgrounded, is allowed", "allow",
    cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command='uv run grep -n "--lane-lint" merge/merge.py | tail -20')
add("check-tail: uv run -w pytest then ci-job checks --lint piped to tail, backgrounded, is refused",
    "deny", "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="uv run -w pytest ci-job checks --lint | tail -5")
add("check-tail: uv run --cache-dir then ci-job checks --lint piped to tail, backgrounded, is refused",
    "deny", "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="uv run --cache-dir /tmp/c ci-job checks --lint | tail -5")
add("check-tail: pytest with bin/ci-job as an argument piped to tail, backgrounded, is allowed",
    "allow", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="python3 -m pytest hooks/test_guard.py -k bin/ci-job | tail -5")

# Wrapper forms in the foreground: each deny reads its check through the wrapper, each allow does not.
sh("check-tail: uv run python runs the script piped to tail in the foreground is refused",
   "uv run python merge/merge.py --lane-lint 7 2>&1 | tail -8", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: uv run runs merge --lane-lint piped to tail in the foreground is refused",
   "uv run merge --lane-lint 7 | tail -8", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: python3.11 runs the script piped to tail in the foreground is refused",
   "python3.11 merge/merge.py --lane-lint 7 | tail -3", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: env VAR=x then merge --lane-lint piped to tail in the foreground is refused",
   "env FOO=1 merge --lane-lint 7 | tail -3", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: env VAR=x then python3 runs the script piped to head in the foreground is refused",
   "env FOO=1 python3 merge/merge.py --review-record --head 0123456789abcdef0123456789abcdef01234567 "
   "| head -5", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: a VAR=x prefix on merge --lane-lint piped to tail in the foreground is refused",
   "FOO=1 merge --lane-lint 7 | tail -3", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: uv run python -m pytest piped to tail in the foreground is allowed",
   "uv run python -m pytest | tail -5", "allow", cwd=NOGIT)
sh("check-tail: uv run --no-group dev then merge --lane-lint piped to tail in the foreground is refused",
   "uv run --no-group dev merge --lane-lint 7 | tail -8", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: a uv global flag before run, then merge --lane-lint piped to tail is refused",
   "uv --quiet run merge --lane-lint 7 | tail -8", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: uv run --with-editable then python runs the script piped to tail is refused",
   "uv run --with-editable . python merge/merge.py --lane-lint 7 | tail -3", "deny", "check-tail",
   cwd=NOGIT)
# `uv run` runs a script operand with no interpreter word, so the script is the command word. The check
# reads only an interpreter's operand, so these uv spellings must still be refused.
sh("check-tail: uv run merge/merge.py --lane-lint piped to tail in the foreground is refused",
   "uv run merge/merge.py --lane-lint 7 | tail -3", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: uv run --with x merge/merge.py --review-record piped to head is refused",
   "uv run --with x merge/merge.py --review-record 7 | head -5", "deny", "check-tail", cwd=NOGIT)
# Pins: pythonw and the -X value flag are read as interpreter spellings already. Dropping pythonw from
# SCRIPT_INTERPRETER, or -X from INTERPRETER_VALUE_FLAGS, turns the matching row red.
sh("check-tail: pythonw runs the merge script piped to tail in the foreground is refused",
   "pythonw merge/merge.py --lane-lint 7 | tail -3", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: python3 -X dev runs the merge script piped to tail in the foreground is refused",
   "python3 -X dev merge/merge.py --lane-lint 7 | tail -3", "deny", "check-tail", cwd=NOGIT)
# Control: a uv run of another script that names --lane-lint is not the merge script, so it is allowed.
sh("check-tail: uv run of another script naming --lane-lint piped to tail is allowed",
   "uv run lint/other.py --lane-lint | tail -3", "allow", cwd=NOGIT)
# An unquoted substitution in the script operand splits into several words, so the first word after the
# interpreter is not the script. Each spelling below names the merge script, so each must still be refused.
sh("check-tail: an unquoted $(git rev-parse) script path piped to tail in the foreground is refused",
   "python3 $(git rev-parse --show-toplevel)/merge/merge.py --lane-lint 7 | tail -3", "deny", "check-tail",
   cwd=NOGIT)
sh("check-tail: an unquoted $(dirname $0) script path piped to head in the foreground is refused",
   "python3 $(dirname $0)/merge/merge.py --review-record 7 | head -5", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: a backtick script path piped to tail in the foreground is refused",
   "python3 `git rev-parse --show-toplevel`/merge/merge.py --lane-lint 7 | tail -3", "deny", "check-tail",
   cwd=NOGIT)
# Pins: a quoted substitution and one with no space are one word already, so these pass on the current guard.
sh("check-tail: a quoted $(git rev-parse) script path piped to tail in the foreground is refused",
   'python3 "$(git rev-parse --show-toplevel)/merge/merge.py" --lane-lint 7 | tail -3', "deny", "check-tail",
   cwd=NOGIT)
sh("check-tail: a $(pwd) script path with no space piped to tail in the foreground is refused",
   "python3 $(pwd)/merge/merge.py --lane-lint 7 | tail -3", "deny", "check-tail", cwd=NOGIT)
# Control: an unquoted substitution that names another script is not the merge script, so it is allowed.
sh("check-tail: an unquoted $(git rev-parse) path to another script naming --lane-lint is allowed",
   "python3 $(git rev-parse --show-toplevel)/lint/other.py --lane-lint | tail -3", "allow", cwd=NOGIT)

# A pipe out of verdict is refused whatever wraps the call (uv run, env VAR=x) and whatever follows
# the pipeline (;, &&, ||), since the pipe hides verdict's exit. A verdict call with no pipe is allowed.
verdict_pipe("env VAR=x then verdict merge --lane-lint piped to tail is refused",
             "env FOO=1 verdict merge --lane-lint 7 | tail -3", "deny")
verdict_pipe("uv run verdict merge --lane-lint piped to tail is refused",
             "uv run verdict merge --lane-lint 7 | tail -3", "deny")
verdict_pipe("verdict piped to tail, then && commit, is refused",
             "verdict python3 lint/check_x.py 2>&1 | tail -3 && git commit -m x", "deny")
verdict_pipe("the absolute bin path piped to tail, then ;, is refused",
             "~/.claude/bin/verdict python3 hooks/test_guard.py | tail -5; git push", "deny")
verdict_pipe("two verdict pipes joined by ; are refused",
             "verdict python3 lint/a.py 2>&1 | tail -3; verdict python3 lint/b.py 2>&1 | tail -3",
             "deny")
verdict_pipe("verdict piped to tail, then ; echo, is refused",
             "verdict python3 lint/a.py | tail -1; echo ---", "deny")
verdict_pipe("the relative bin path piped to head, then &&, is refused",
             "bin/verdict make check | head -3 && echo ok", "deny")
verdict_pipe("an env assignment before verdict piped to tail, then &&, is refused",
             "GUARD_FAMILY=stream verdict python3 hooks/test_guard.py 2>&1 | tail -3 && git push",
             "deny")
verdict_pipe("the shortened incident line piped to tail, then && add and commit, is refused",
             "~/.claude/bin/verdict python3 lint/ste_lint.py docs/decisions/x.md 2>&1 | tail -1 && "
             "git add docs/decisions/x.md && git commit -q -m x", "deny")
verdict_pipe("verdict piped to tail, then || echo, is refused",
             "verdict python3 lint/check_x.py | tail -1 || echo failed", "deny")
verdict_pipe("verdict piped to grep -q, then && push, is refused",
             "verdict python3 lint/check_x.py 2>&1 | grep -q PASS && git push", "deny")
verdict_pipe("verdict piped to sed -n, then && push, is refused",
             "verdict make check | sed -n 1p && git push", "deny")
verdict_pipe("verdict.cmd piped to tail, then && push, is refused",
             "verdict.cmd python3 lint/check_x.py | tail -3 && git push", "deny")
verdict_pipe("verdict piped to tail as the last pipeline is refused",
             "verdict python3 lint/check_x.py | tail -3", "deny")
verdict_pipe("verdict piped to grep as the last command is refused",
             "verdict make check | grep FAIL", "deny")
verdict_pipe("pipefail set earlier with set -o does not lift the refusal, then && commit, is refused",
             "set -o pipefail; verdict python3 lint/check_x.py | tail -3 && git commit -m x", "deny")
verdict_pipe("pipefail set earlier in set -euo does not lift the refusal, then && push, is refused",
             "set -euo pipefail && verdict python3 lint/check_x.py | tail -3 && git push", "deny")
verdict_pipe("set +o pipefail undoes an earlier set -o, then && push, is refused",
             "set -o pipefail; set +o pipefail; verdict python3 lint/check_x.py | tail -3 && git push",
             "deny")
add("verdict-pipe: verdict piped to tail, then && commit, backgrounded, is refused", "deny",
    VERDICT_PIPE, cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="verdict python3 lint/check_x.py 2>&1 | tail -3 && git commit -m x")
verdict_pipe("a bare verdict call is allowed", "verdict python3 lint/check_x.py", "allow")
verdict_pipe("verdict then && commit, with no pipe, is allowed",
             "verdict python3 lint/check_x.py && git commit -m x", "allow")
verdict_pipe("a pipe with no verdict in it is allowed", "cat x.log | tail -3 && echo ok", "allow")
verdict_pipe("verdict inside single quotes is not a call",
             "echo 'verdict a | tail -1 && b'", "allow")

# Foreground: merge --lane-lint and merge --review-record piped to tail or head are refused. ci-job is
# not refused in the foreground. A verdict call piped to tail is refused by verdict-pipe; with no pipe
# after it, a verdict call is allowed.
sh("check-tail: the incident line in the foreground is refused",
   "~/.claude/bin/merge --lane-lint 1476 2>&1 | tail -8", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: merge --lane-lint piped to tail in the foreground is refused",
   "merge --lane-lint 1476 2>&1 | tail -8", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: merge --review-record piped to head in the foreground is refused",
   "~/.claude/bin/merge 12 --review-record --head 0123456789abcdef0123456789abcdef01234567 | head -20",
   "deny", "check-tail", cwd=NOGIT)
sh("check-tail: ci-job piped to tail in the foreground is allowed",
   "~/.claude/bin/ci-job checks --lint --base origin/main 2>&1 | tail -20", "allow", cwd=NOGIT)
sh("check-tail: ci-job checks --lint piped to tail in the foreground is allowed",
   "~/.claude/bin/ci-job checks --lint 2>&1 | tail -20", "allow", cwd=NOGIT)
sh("verdict-pipe: a verdict call piped to tail in the foreground is refused",
   "verdict merge --lane-lint 1476 | tail -3", "deny", "verdict-pipe", cwd=NOGIT)
sh("check-tail: a verdict call with no pipe in the foreground is allowed",
   "verdict merge --lane-lint 1476", "allow", cwd=NOGIT)
# `merge --release-check` prints one verdict line per pull request, so tail or head cuts it like a lint verdict.
# The lane-lint row is the control: its refusal is the one these rows must match.
sh("check-tail: merge --lane-lint 5 piped to tail -2 in the foreground is refused (control)",
   "merge --lane-lint 5 | tail -2", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: merge --release-check piped to tail in the foreground is refused",
   "merge --release-check 5 6 | tail -3", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: merge --release-check piped to head in the foreground is refused",
   "merge --release-check 5 6 | head -1", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: the bin merge --release-check piped to tail in the foreground is refused",
   "~/.claude/bin/merge --release-check 5 6 | tail -3", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: merge --release-check with no pipe in the foreground is allowed (control)",
   "merge --release-check 5 6", "allow", cwd=NOGIT)
add("check-tail: merge --release-check piped to tail, backgrounded, is refused", "deny",
    "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="merge --release-check 5 6 2>&1 | tail -3")
add("check-tail: merge --release-check with no pipe, backgrounded, is allowed (control)", "allow",
    cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="merge --release-check 5 6")

# --- check-tail: any filter after a merge verdict call, a glued `&`, and the merge option forms
# (decision background-check-through-verdict; detached-launch reads the glued `&`).
#
# ANY FILTER. After merge --lane-lint or --review-record, any filter cuts what the agent reads, not only tail
# and head. The writers tee, tee.exe, Tee-Object and Out-File with nothing after them are the exception. So are
# a verdict call, a redirect to a file, and a grep of that file in a later command.
sh("check-tail: merge --lane-lint piped to sed -n 1,5p, with no tail or head, is refused",
   "merge --lane-lint 7 | sed -n 1,5p", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: merge --lane-lint piped to grep -m1 FAIL, with no tail or head, is refused",
   "merge --lane-lint 7 | grep -m1 FAIL", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: merge --review-record piped to awk, with no tail or head, is refused",
   "merge --review-record 7 | awk 'END{print}'", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: merge --lane-lint through tee, then sed -n, is refused",
   "merge --lane-lint 7 | tee x | sed -n 1,5p", "deny", "check-tail", cwd=NOGIT)
add("check-tail: ci-job checks --lint piped to grep FAIL, backgrounded, is refused", "deny",
    "check-tail", cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    command="~/.claude/bin/ci-job checks --lint | grep FAIL")
sh("check-tail: merge --lane-lint piped to tee, with nothing after it, is allowed",
   "merge --lane-lint 7 | tee lint.log", "allow", cwd=NOGIT)
sh("check-tail: merge --lane-lint piped to tee.exe, with nothing after it, is allowed",
   "merge --lane-lint 7 | tee.exe lint.log", "allow", cwd=NOGIT)
sh("check-tail: merge --lane-lint piped to Tee-Object, with nothing after it, is allowed",
   "merge --lane-lint 7 | Tee-Object -FilePath lint.log", "allow", cwd=NOGIT)
sh("check-tail: merge --lane-lint piped to Out-File, with nothing after it, is allowed",
   "merge --lane-lint 7 | Out-File lint.log", "allow", cwd=NOGIT)
sh("check-tail: a verdict call of merge --lane-lint, with no pipe, is allowed",
   "~/.claude/bin/verdict merge --lane-lint 7 2>&1", "allow", cwd=NOGIT)
sh("check-tail: merge --lane-lint redirected to a file, with no pipe, is allowed",
   "merge --lane-lint 7 > lint.log 2>&1", "allow", cwd=NOGIT)
sh("check-tail: merge --lane-lint into a file, then grep -m1 of the file, is allowed",
   "merge --lane-lint 7 > lint.log 2>&1; grep -m1 FAIL lint.log", "allow", cwd=NOGIT)
sh("check-tail: merge --lane-lint into a file, then grep -m1 of the file piped to tail, is allowed",
   "merge --lane-lint 7 > lint.log 2>&1; grep -m1 FAIL lint.log | tail -1", "allow", cwd=NOGIT)

# GLUED `&`. A `&` glued to the word before it ends a job as a spaced `&` does. detached-launch refuses the job
# when no pid is captured, and check-tail refuses a named check whose job is cut. A `&` that is no job is a `&&`,
# a `|&`, a `>&` or `2>&1`, a quoted `&`, a `&` after a comment's `#`, a `&` inside a multi-line quote, bash
# arithmetic, or PowerShell's call operator.
add("detached-launch: ci-job checks piped to tail -3&, the & glued to the word, is refused", "deny",
    "detached-launch", cwd=NOGIT, description=TAIL_BG_UNTIL, command="ci-job checks | tail -3&")
add("detached-launch: ci-job checks|tail&, with no space around the pipe or the &, is refused", "deny",
    "detached-launch", cwd=NOGIT, description=TAIL_BG_UNTIL, command="ci-job checks|tail&")
add("detached-launch: ci-job checks piped to grep '#x'&, a glued & after a quoted #, is refused", "deny",
    "detached-launch", cwd=NOGIT, description=TAIL_BG_UNTIL, command="ci-job checks | grep '#x'&")
add("detached-launch: ci-job checks piped to grep \"don't\"&, a glued & after a quoted apostrophe, is refused",
    "deny", "detached-launch", cwd=NOGIT, description=TAIL_BG_UNTIL, command='ci-job checks | grep "don\'t"&')
add("detached-launch: (ci-job x | tail)&, a subshell backgrounded by a glued &, is refused", "deny",
    "detached-launch", cwd=NOGIT, description=TAIL_BG_UNTIL, command="(ci-job x | tail)&")
add("detached-launch: cmd 2>&1&, a glued & after a redirect, is refused", "deny",
    "detached-launch", cwd=NOGIT, description=TAIL_BG_UNTIL, command="cmd 2>&1&")
add("check-tail: ci-job checks piped to tail -3&, a newline, then echo $!, is refused", "deny",
    "check-tail", cwd=NOGIT, description=TAIL_BG_UNTIL, command="ci-job checks | tail -3&\necho $!")
add("check-tail: ci-job checks piped to tail -3& echo $!, the glued & with the pid captured, is refused", "deny",
    "check-tail", cwd=NOGIT, description=TAIL_BG_UNTIL, command="ci-job checks | tail -3& echo $!")
add("check-tail: ci-job checks piped to grep '#x'& echo $!, a glued & after a quoted #, is refused", "deny",
    "check-tail", cwd=NOGIT, description=TAIL_BG_UNTIL, command="ci-job checks | grep '#x'& echo $!")
add("check-tail: ci-job checks | tail -3 && echo done & echo $!, a spaced & backgrounds the && list, is refused",
    "deny", "check-tail", cwd=NOGIT, description=TAIL_BG_UNTIL,
    command="ci-job checks | tail -3 && echo done & echo $!")
add("check-tail: ci-job checks | tail -3 && echo done& echo $!, a glued & backgrounds the && list, is refused",
    "deny", "check-tail", cwd=NOGIT, description=TAIL_BG_UNTIL,
    command="ci-job checks | tail -3 && echo done& echo $!")
add("check-tail: ci-job checks --lint piped to grep FAIL & echo $!, a spaced & with the pid captured, is refused",
    "deny", "check-tail", cwd=NOGIT, description=TAIL_BG_UNTIL,
    command="~/.claude/bin/ci-job checks --lint | grep FAIL & echo $!")
add("detached-launch: ci-job checks piped to tail -3 with a spaced &, is refused (control)", "deny",
    "detached-launch", cwd=NOGIT, description=TAIL_BG_UNTIL, command="ci-job checks | tail -3 &")
sh("check-tail: ci-job checks |& tail -3, the & of |& is a pipe, is allowed",
   "ci-job checks |& tail -3", "allow", cwd=NOGIT)
sh("check-tail: ci-job checks|&tail -3, the & of |& glued to the next word, is allowed",
   "ci-job checks|&tail -3", "allow", cwd=NOGIT)
sh("check-tail: ci-job checks && tail x, a && list with no job, is allowed",
   "ci-job checks && tail x", "allow", cwd=NOGIT)
sh("check-tail: echo a&&b, a && glued to both words, is allowed", "echo a&&b", "allow", cwd=NOGIT)
sh("check-tail: ci-job checks piped to grep 'a&', a & inside quotes, is allowed",
   "ci-job checks | grep 'a&'", "allow", cwd=NOGIT)
sh("check-tail: ci-job checks piped to tail -3 >&2, the & of a redirect, is allowed",
   "ci-job checks | tail -3 >&2", "allow", cwd=NOGIT)
sh("check-tail: ci-job checks piped to tail -3 2>&1, the & of a redirect, is allowed",
   "ci-job checks | tail -3 2>&1", "allow", cwd=NOGIT)
sh("check-tail: cmd 2>&1 piped to tail, the & of a redirect, is allowed",
   "cmd 2>&1 | tail", "allow", cwd=NOGIT)
sh("check-tail: cmd >&2 then echo, the & of a redirect, is allowed", "cmd >&2; echo x", "allow", cwd=NOGIT)
sh("check-tail: ci-job checks piped to tail -3 # bg&, a & after a comment's #, is allowed",
   "ci-job checks | tail -3 # bg&", "allow", cwd=NOGIT)
sh("check-tail: ci-job checks piped to tail -3 # a& b, a & after a comment's #, is allowed",
   "ci-job checks | tail -3 # a& b", "allow", cwd=NOGIT)
sh("check-tail: ci-job checks piped to grep, a & at a line's end inside a multi-line quote, is allowed",
   'ci-job checks | grep "first line&\nsecond line"', "allow", cwd=NOGIT)
sh("check-tail: ci-job checks piped to grep, a & inside a multi-line quote, is allowed",
   'ci-job checks | grep "x& y\nz"', "allow", cwd=NOGIT)
sh("check-tail: grep of a quoted lone &, is allowed", "grep '&' file", "allow", cwd=NOGIT)
sh("check-tail: cut of a quoted lone & piped to head, is allowed",
   "cut -d '&' -f1 q | head -3", "allow", cwd=NOGIT)
sh("check-tail: ci-job checks piped to grep -c of a quoted lone &, is allowed",
   "ci-job checks | grep -c '&'", "allow", cwd=NOGIT)
sh("check-tail: grep of a double-quoted lone & piped to tail, is allowed",
   'grep "&" file | tail -3', "allow", cwd=NOGIT)
sh("detached-launch: (& $tool x).Count, a call operator in a grouped expression, is allowed",
   "(& $tool x).Count", "allow", tool="PowerShell", cwd=NOGIT)
sh("detached-launch: $a = @(& $tool x), a call operator inside @(), is allowed",
   "$a = @(& $tool x)", "allow", tool="PowerShell", cwd=NOGIT)
sh("detached-launch: 1..3 | ForEach-Object {&$tool $_}, a glued call operator in a scriptblock, is allowed",
   "1..3 | ForEach-Object {&$tool $_}", "allow", tool="PowerShell", cwd=NOGIT)
sh("detached-launch: $r = (& ci-job checks), a call operator on a roster command, is allowed",
   "$r = (& ci-job checks)", "allow", tool="PowerShell", cwd=NOGIT)
sh("detached-launch: echo $((5&3)), a bitwise & in arithmetic expansion, is allowed",
   "echo $((5&3))", "allow", cwd=NOGIT)
sh("detached-launch: if (( n&1 )); then echo odd; fi, a bitwise & in an arithmetic test, is allowed",
   "if (( n&1 )); then echo odd; fi", "allow", cwd=NOGIT)
sh("detached-launch: echo ${s//&/and}, a & in a parameter pattern, is allowed",
   "echo ${s//&/and}", "allow", cwd=NOGIT)

# MERGE OPTIONS. The merge tool's parser takes an exact option name only: allow_abbrev is off in merge/merge.py
# build_parser (decision merge-confirm-repo). A prefix such as `--lane` or `--lane=7` exits 2 and runs nothing, so
# the guard allows it. `--name=value` splits at the `=`, so `--lane-lint=7` is the check. A merge run as a module
# (`-m merge.merge`) runs the merge script.
sh("check-tail: merge --lane-l, a prefix of --lane-lint, piped to tail is allowed",
   "merge --lane-l 7 2>&1 | tail -3", "allow", cwd=NOGIT)
sh("check-tail: merge --review-r, a prefix of --review-record, piped to head is allowed",
   "merge --review-r 7 | head -5", "allow", cwd=NOGIT)
sh("check-tail: merge --lane, a prefix of --lane-lint, piped to tail is allowed",
   "merge --lane 7 | tail -8", "allow", cwd=NOGIT)
sh("check-tail: merge --lane-lint=7 in the = form, piped to tail is refused",
   "merge --lane-lint=7 | tail -3", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: merge --lane=7, a prefix in the = form, piped to tail is allowed",
   "merge --lane=7 | tail -3", "allow", cwd=NOGIT)
sh("check-tail: merge --l, a prefix that names two options so argparse refuses it, piped to tail is allowed",
   "merge --l 7 | tail -3", "allow", cwd=NOGIT)
sh("check-tail: python3 -m merge.merge --lane-lint piped to tail is refused",
   "python3 -m merge.merge --lane-lint 7 | tail -3", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: python3 -Im merge.merge --lane-lint piped to tail is refused",
   "python3 -Im merge.merge --lane-lint 7 | tail -3", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: python3 -W ignore -m merge.merge --lane-lint piped to tail is refused",
   "python3 -W ignore -m merge.merge --lane-lint 7 | tail -3", "deny", "check-tail", cwd=NOGIT)

# A lint script piped into a filter, with a commit or push later in the call, hides the lint's exit: the commit
# reads the last stage's exit. Each spelling below is refused. Its form with no commit after it is allowed.
sh("check-tail: python3 lint/ste_lint.py piped to tail, then && git commit, is refused",
   "python3 lint/ste_lint.py x.md | tail -3 && git commit -m x", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: python3 lint/ste_lint.py piped to tail, with no commit or push after it, is allowed",
   "python3 lint/ste_lint.py x.md | tail -3", "allow", cwd=NOGIT)
sh("check-tail: verdict python3 lint/ste_lint.py, then && git commit, with no pipe, is allowed",
   "verdict python3 lint/ste_lint.py x.md && git commit -m x", "allow", cwd=NOGIT)
sh("check-tail: python3 -m pytest piped to tail, then && git commit, is allowed",
   "python3 -m pytest -q | tail -3 && git commit -m x", "allow", cwd=NOGIT)
sh("check-tail: cd lint, then python3 -m pytest piped to tail, then && git commit, is allowed",
   "cd lint && python3 -m pytest -q | tail -3 && git commit -m x", "allow", cwd=NOGIT)
sh("check-tail: cd lint, then a bare lint script piped to tail, then && git commit, is refused",
   "cd lint && ./ste_lint.py x.md | tail -3 && git commit -m x", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: python3 -m lint.ste_lint piped to tail, then && git commit, is refused",
   "python3 -m lint.ste_lint x.md | tail -3 && git commit -m x", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: python3 -Im lint.ste_lint piped to tail, then && git commit, is refused",
   "python3 -Im lint.ste_lint x.md | tail -3 && git commit -m x", "deny", "check-tail", cwd=NOGIT)
sh("check-tail: python3 -W ignore -m lint.ste_lint piped to tail, then && git commit, is refused",
   "python3 -W ignore -m lint.ste_lint x.md | tail -3 && git commit -m x", "deny", "check-tail", cwd=NOGIT)

# =========================================================================== 2c. waiter loops
#
# Rule 9, approved by the owner. A pause between polls turns waiting into a loop of turns that
# each print a word.

# Narrowed by the owner, 2026-10-12. One foreground sleep under 25 seconds is allowed, anywhere
# in the command. A loop, two sleeps with a check between them, and a sleep of 25 seconds or
# more are refused. `gh pr checks --watch` is refused in the foreground and allowed in the
# background. `gh run watch` is refused in both (decision ci-wait-reads-run-status, below).
# "waiter: a bare sleep" keeps its name: hooks/mutate_guard.py selects this case by that name.
sh("waiter: a bare sleep", "sleep 30", "deny", "waiter", cwd=NOGIT)
sh("waiter: one sleep 5 is allowed", "sleep 5", "allow", cwd=NOGIT)
sh("waiter: sleep 24, under 25 seconds, is allowed", "sleep 24", "allow", cwd=NOGIT)
sh("waiter: sleep 25, at the limit, is refused", "sleep 25", "deny", "waiter", cwd=NOGIT)
sh("waiter: one short sleep ahead of a poll is allowed", "sleep 5 && gh pr list", "allow",
   cwd=NOGIT)
sh("waiter: a short sleep ahead of a later call is allowed", "cd a && sleep 15; gh run list",
   "allow", cwd=NOGIT)
sh("waiter: a 30 s sleep ahead of a later call is refused", "cd a && sleep 30; gh run list",
   "deny", "waiter", cwd=NOGIT)
sh("waiter: an until-loop waiting on a file is refused", "until [ -s f ]; do sleep 2; done",
   "deny", "waiter", cwd=NOGIT)
sh("waiter: two sleeps, each followed by a check, are refused",
   "sleep 5; gh run view 1; sleep 5; gh run view 1", "deny", "waiter", cwd=NOGIT)
sh("waiter: Start-Sleep -Seconds 10 is allowed", "Start-Sleep -Seconds 10", "allow",
   tool="PowerShell", cwd=NOGIT)
sh("waiter: a PowerShell while-loop with Start-Sleep is refused",
   "while (-not (Test-Path f)) { Start-Sleep -Seconds 2 }", "deny", "waiter",
   tool="PowerShell", cwd=NOGIT)
sh("waiter: a PowerShell for-loop with Start-Sleep is refused",
   "for ($i = 0; $i -lt 5; $i++) { Start-Sleep -Seconds 2 }", "deny", "waiter",
   tool="PowerShell", cwd=NOGIT)
sh("waiter: timeout /t on Windows cmd", "timeout /t 5", "deny", "waiter", cwd=NOGIT)

# A watcher blocks the foreground call. `gh pr checks --watch` is allowed under run_in_background,
# because the harness tracks that job and the session waits for its completion notice.
# `gh run watch` is refused there too: owner ruling 2026-10-16 03:00 CDT, "Change them too"
# (decision ci-wait-reads-run-status, "Claude's own waits"). The cases of that ruling are in the
# block "ci-wait" below this one.
sh("waiter: a foreground gh pr checks --watch is refused", "gh pr checks 12 --watch", "deny",
   "waiter", cwd=NOGIT)
sh("waiter: a foreground gh run watch is refused", "gh run watch 7", "deny", "waiter",
   cwd=NOGIT)
add("waiter: gh run watch under run_in_background is refused", "deny", "waiter", cwd=NOGIT,
    command="gh run watch 7", run_in_background=True)
add("waiter: gh pr checks --watch under run_in_background is allowed", "allow", cwd=NOGIT,
    command="gh pr checks 5 --watch", run_in_background=True)
add("waiter: a short sleep before a background gh run watch is refused", "deny", "waiter",
    cwd=NOGIT, command="sleep 5; gh run watch 7", run_in_background=True)
add("waiter: a short sleep before a background gh pr checks --watch is allowed", "allow",
    cwd=NOGIT, command="sleep 5; gh pr checks 5 --watch", run_in_background=True)

# A sleep, a timeout /t, or a loop inside quoted text or a heredoc body is data, not a command.
# Each shape is one that split_segments could cut in the wrong place.
sh('waiter: sleep inside double quotes is allowed', 'echo "sleep 99"', "allow", cwd=NOGIT)
sh('waiter: a semicolon then sleep inside double quotes is allowed', 'echo "a; sleep 99"',
   "allow", cwd=NOGIT)
sh('waiter: timeout /t inside double quotes is allowed', 'echo "timeout /t 5"', "allow",
   cwd=NOGIT)
sh("waiter: a multi-line quoted string with a sleep line is allowed",
   'echo "first line\nsleep 5 later"', "allow", cwd=NOGIT)
sh("waiter: a sleep line in a heredoc body is allowed",
   "cat > notes.txt <<'EOF'\nsleep 5\nEOF", "allow", cwd=NOGIT)
sh("waiter: a lone apostrophe in a heredoc body is allowed",
   "cat <<'EOF'\nDon't sleep 5 here\nEOF", "allow", cwd=NOGIT)
sh("waiter: a loop inside a heredoc body is allowed",
   "cat <<'EOF'\nwhile true; do sleep 5; done\nEOF", "allow", cwd=NOGIT)
sh("waiter: a comment opener in quotes does not hide a loop, refused",
   'echo "it\'s # fine"; while true; do sleep 5; done', "deny", "waiter", cwd=NOGIT)

# Each refused shape below waits by repeating or by a long
# pause; each allowed shape is a false alarm the guard raised on a non-waiting command.
# A bare `&` job is refused first by detached-launch (rule 2b), so the waiter rule is not reached
# for these two. They pin the refusal; the rule named is the one that fires.
sh("waiter: two sleeps joined by a background & are refused", "sleep 5 & sleep 5", "deny",
   "detached-launch", cwd=NOGIT)
sh("waiter: a sleep then a foreground watcher, joined by &, is refused",
   "sleep 5 & gh run watch 1", "deny", "detached-launch", cwd=NOGIT)
sh("waiter: a PowerShell while-loop with Start-Sleep in braces is refused",
   "while(1){Start-Sleep 1}", "deny", "waiter", tool="PowerShell", cwd=NOGIT)
sh("waiter: a PowerShell range piped to % with Start-Sleep is refused",
   "1..10 | % { Start-Sleep 2 }", "deny", "waiter", tool="PowerShell", cwd=NOGIT)
sh("waiter: a PowerShell range piped to ForEach-Object with Start-Sleep is refused",
   "1..10 | ForEach-Object { Start-Sleep 2 }", "deny", "waiter", tool="PowerShell", cwd=NOGIT)
sh("waiter: gh.exe run watch in the foreground is refused", "gh.exe run watch 1", "deny",
   "waiter", cwd=NOGIT)
sh("waiter: gh pr checks --watch=true in the foreground is refused",
   "gh pr checks 5 --watch=true", "deny", "waiter", cwd=NOGIT)
sh("waiter: sleep 1m, 60 seconds, is refused", "sleep 1m", "deny", "waiter", cwd=NOGIT)
sh("waiter: Start-Sleep -Milliseconds 30000, 30 seconds, is refused",
   "Start-Sleep -Milliseconds 30000", "deny", "waiter", tool="PowerShell", cwd=NOGIT)
sh("waiter: Start-Sleep -Milliseconds 5000, 5 seconds, is allowed",
   "Start-Sleep -Milliseconds 5000", "allow", tool="PowerShell", cwd=NOGIT)
add("waiter: a loop under run_in_background is still refused", "deny", "waiter", cwd=NOGIT,
    command="until [ -s f ]; do sleep 2; done", run_in_background=True)
sh("waiter: gh pr view -w is allowed (no watch)", "gh pr view 1 -w", "allow", cwd=NOGIT)
sh("waiter: gh repo view -w is allowed (no watch)", "gh repo view -w", "allow", cwd=NOGIT)
sh("waiter: gh pr list -w is allowed (no watch)", "gh pr list -w", "allow", cwd=NOGIT)
sh("waiter: gh issue list --label watch is allowed", "gh issue list --label watch", "allow",
   cwd=NOGIT)
sh("waiter: gh issue create --title watch is allowed", "gh issue create --title watch", "allow",
   cwd=NOGIT)

# `-w` is `--web` for `gh pr checks` (open the browser), and
# `--watch` has no short form, so `-w` there is not a watcher. A repo flag (`-R o/r`) sits
# between the command group and its verb, so the verb is not the token after `gh`.
sh("waiter: gh pr checks -w, --web, in the foreground is allowed", "gh pr checks 5 -w", "allow",
   cwd=NOGIT)
sh("waiter: gh run -R o/r watch in the foreground is refused", "gh run -R o/r watch 1", "deny",
   "waiter", cwd=NOGIT)
sh("waiter: gh pr -R o/r checks --watch in the foreground is refused",
   "gh pr -R o/r checks 5 --watch", "deny", "waiter", cwd=NOGIT)
add("waiter: gh run -R o/r watch under run_in_background is refused", "deny", "waiter",
    cwd=NOGIT, command="gh run -R o/r watch 1", run_in_background=True)
sh("waiter: a readiness check is allowed", "curl --retry 5 http://localhost:3000", "allow",
   cwd=NOGIT)
sh("waiter: an unrelated log query is allowed", VCS + " log --since=yesterday", "allow", cwd=NOGIT)

# Rule 9 missed every loop body. `split_segments` cuts a loop on its own `;`, so the segment
# after it is `do sleep 1`, and the command word read as `do`, not `sleep`. MEASURED against the
# live guard before this fix: the two loops below were both wrongly allowed.
sh("waiter: a while-loop with a pattern-polling condition, MEASURED wrongly allowed",
   "while ! pgrep -f server; do sleep 1; done", "deny", "waiter",
   carries=("condition polls",))
sh("waiter: an until-loop over a plain readiness check, MEASURED wrongly allowed",
   "until curl -sf localhost:3000; do sleep 2; done", "deny", "waiter")
sh("waiter: a for-loop's own do-block still denies",
   "for i in 1 2 3; do sleep 1; done", "deny", "waiter")
sh("waiter: a non-waiter loop body stays allowed",
   'while read l; do echo "$l"; done', "allow", cwd=NOGIT)

# `split_segments` read the `'` in a `#` comment as opening a quote that ran to the end of the
# text, so every loop under such a comment was invisible. MEASURED in Banchi on 2026-09-19 on
# its lifted copy: the runaway-driver fixture went from refused to allowed. A `#` that starts
# a word is a comment to the end of its line; one inside a word or a quote is not.
sh("waiter: a loop under a comment holding an apostrophe, MEASURED wrongly allowed",
   "# the merge driver's shape\nwhile true; do sleep 5; done", "deny", "waiter")
sh("waiter: a `#` inside a word is not a comment, so the loop after it still denies",
   "echo fix#3; while true; do sleep 5; done", "deny", "waiter")


# ------------------------------------------------------------------ ci-wait: no gh run watch at all
#
# Owner ruling 2026-10-16 03:00 CDT, "Change them too" (decision ci-wait-reads-run-status, "Claude's
# own waits"). Claude and its agents run no `gh run watch`, in the foreground or the background. A
# session waits on CI through the CI-wake hook (it fires after `gh pr ready`; a push starts
# none). Incident: one `gh run watch` made 131 API calls in 60 s (MEASURED 2026-10-16 06:28
# UTC), and merges failed on GitHub limits all night. The ruling names `gh run watch` only, so
# `gh pr checks --watch` stays allowed in the background.
# Rule name: waiter. Case names start "ci-wait:", so MUTATE_ONLY=ci-wait picks them out.
# The read-only allow cases and the data cases pin that no read and no text that only names the
# command is refused.
# A refusal's reason may name no pause (`sleep` is in FORBIDDEN_IN_A_REASON) and no settings file.
CI_WAIT_REMEDY = "CI-wake"  # the remedy names the CI-wake notice
# The remedy never names the refused call, its flag, or bin/merge: the ruling says Claude's own wait
# ends in a merge, so the remedy points at the CI-wake notice only.
NO_RUN_WATCH = ("run watch", "--exit-status", "bin/merge")

for _tool, _command in (
        ("Bash", "gh run watch 7"),
        ("Bash", "gh run watch 7 --exit-status"),
        ("Bash", "gh run watch 7 --exit-status -R owner/repo"),
        ("Bash", "gh run --repo owner/repo watch 7 --exit-status"),
        ("Bash", "verdict gh run watch 7 --exit-status"),
        ("Bash", "gh run watch 7 --exit-status && echo done"),
        ("Bash", 'echo "it\'s # fine"; gh run watch 7'),  # a quote and a # ahead do not hide it
        ("PowerShell", "gh run watch 7"),
        ("PowerShell", "gh run watch 7 --exit-status"),
        ("PowerShell", "gh.exe run watch 7 --exit-status -R owner/repo"),
        ("PowerShell", "gh run watch 7; Write-Host done"),
):
    add("ci-wait: %s %s under run_in_background is refused, remedy names a CI-wake wait"
        % (_tool, _command), "deny", "waiter", tool=_tool, cwd=NOGIT,
        carries=(CI_WAIT_REMEDY,), lacks=NO_RUN_WATCH, command=_command, run_in_background=True)

for _tool, _command in (
        ("Bash", "gh run watch 7 --exit-status"),
        ("Bash", "gh run watch 7 --exit-status -R owner/repo"),
        ("Bash", "gh run --repo owner/repo watch 7"),
        ("PowerShell", "gh run watch 7 --exit-status"),
        ("PowerShell", "gh.exe run watch 7 -R owner/repo"),
):
    add("ci-wait: foreground %s %s stays refused" % (_tool, _command), "deny", "waiter",
        tool=_tool, cwd=NOGIT, command=_command)

# Every remedy the stream family prints, reached by its own trigger. The two checks are apart, so
# each goes red alone: the refused call or bin/merge is named, and the CI-wake notice is not named.
for _label, _trigger in (
        ("a foreground gh run watch", "gh run watch 7 --exit-status"),
        ("a loop around a pause", "until [ -s f ]; do sleep 2; done"),
        ("a loop whose condition polls a pattern", "while ! pgrep -f server; do sleep 1; done"),
):
    add("ci-wait: the remedy of %s never names the refused call or bin/merge" % _label, "deny", "waiter",
        cwd=NOGIT, lacks=NO_RUN_WATCH, command=_trigger)
    add("ci-wait: the remedy of %s names the CI-wake notice" % _label, "deny",
        "waiter", cwd=NOGIT, carries=(CI_WAIT_REMEDY,), command=_trigger)

# ------------------------------------------------------------------ wait-pid: the one wait on a pid
#
# Roadmap step wait-for-pid-form: after the stall watch trips, the session holds a stranded job's
# pid and the guard refuses every way to wait on it. `bin/wait-pid PID [--timeout SECS]` is the one
# allowed form (its own cases: lint/test_wait_pid.py). The guard allows the helper and keeps
# refusing the loops, so each refusal case pins that it did not move. The three remedies below
# point at the helper.
WAIT_PID = "wait-pid"
for _label, _command in (("a pid", "wait-pid 12345"), ("a pid and a timeout", "wait-pid 12345 --timeout 500")):
    sh("wait-pid: %s is allowed in the foreground" % _label, _command, "allow", cwd=NOGIT)
    add("wait-pid: %s is allowed under run_in_background" % _label, "allow", cwd=NOGIT,
        command=_command, run_in_background=True)
sh("wait-pid: a kill -0 loop stays refused, and its remedy names the helper",
   "while kill -0 12345; do sleep 5; done", "deny", "waiter", cwd=NOGIT, carries=(WAIT_PID,))
sh("wait-pid: tail --pid with a follow stays refused", "tail --pid=12345 -f /dev/null", "deny",
   "live-stream", cwd=NOGIT)
sh("wait-pid: a pgrep loop stays refused", "while pgrep x; do sleep 5; done", "deny", "waiter",
   cwd=NOGIT)
# Each remedy is reached by its own trigger. The pattern remedy must not advise `kill -0`: a bare
# kill -0 loop is a refused form, so that advice sends the reader into a second refusal.
for _label, _trigger, _rule, _lacks in (
        ("a followed stream", "tail -f app.log", "live-stream", ()),
        ("a pause", "sleep 30", "waiter", ()),
        ("a loop whose condition polls a pattern", "while ! pgrep -f server; do sleep 1; done", "waiter",
         ("kill -0",)),
):
    add("wait-pid: the remedy of %s names the helper" % _label, "deny", _rule, cwd=NOGIT,
        carries=(WAIT_PID,), lacks=_lacks, command=_trigger)
# The three triggers, each reaching one waiter-family remedy by its own rule. The bin-path cases of wait-pid
# and of wait-until both loop over them.
REMEDY_TRIGGERS = (
        ("a followed stream", "tail -f app.log", "live-stream"),
        ("a pause", "sleep 30", "waiter"),
        ("a loop whose condition polls a pattern", "while ! pgrep -f server; do sleep 1; done", "waiter"),
)
# A bare `wait-pid` is not on PATH in an agent worktree, so each remedy names the helper by its bin path.
for _label, _trigger, _rule in REMEDY_TRIGGERS:
    sh("wait-pid: the remedy of %s names the helper by its bin path" % _label, _trigger, "deny", _rule,
       cwd=NOGIT, carries=("bin/wait-pid",))
# The path forms a remedy may name are allowed, in the foreground and under run_in_background.
for _command in ("~/.claude/bin/wait-pid 12345", "bin/wait-pid 12345"):
    sh("wait-pid: %s is allowed in the foreground" % _command, _command, "allow", cwd=NOGIT)
    add("wait-pid: %s is allowed under run_in_background" % _command, "allow", cwd=NOGIT,
        command=_command, run_in_background=True)

# Reads stay allowed, in the foreground and under run_in_background. `gh pr checks <n>` without
# `--watch` is allowed on main, and stays so.
for _tool, _command in (
        ("Bash", "gh run view 7 --json status"),
        ("Bash", "gh run view 7 --json status,conclusion -R owner/repo"),
        ("Bash", "gh run list --limit 5"),
        ("Bash", "gh run list -R owner/repo --branch main --json status,conclusion"),
        ("Bash", "gh pr checks 5"),
        ("PowerShell", "gh run view 7 --json status"),
        ("PowerShell", "gh pr checks 5"),
):
    for _bg in (False, True):
        add("ci-wait: %s %s%s is allowed" % (_tool, _command, " under run_in_background" if _bg else ""),
            "allow", tool=_tool, cwd=NOGIT, command=_command,
            **({"run_in_background": True} if _bg else {}))

# The text of a command is data. A scanner that finds `gh run watch` in these would refuse a note, a
# commit message or an issue title. Shapes: quoted text, a lone apostrophe in a heredoc body, a
# multi-line quoted string, a comment line, an argument, and a quoted `#` ahead of a read.
for _label, _command in (
        ("quoted text", 'echo "gh run watch 7"'),
        ("a heredoc body with a lone apostrophe", "cat > notes.txt <<'EOF'\nDon't gh run watch here\nEOF"),
        ("a multi-line quoted string", 'echo "first line\ngh run watch 7 later"'),
        ("a comment line", "# start gh run watch 7 later\necho ready"),
        ("an issue title", 'gh issue create --title "gh run watch"'),
        ("a read after a quoted comment opener", 'echo "# x"; gh run view 7 --json status'),
):
    for _bg in (False, True):
        add("ci-wait: gh run watch named in %s is data, allowed%s"
            % (_label, " under run_in_background" if _bg else ""), "allow", cwd=NOGIT,
            command=_command, **({"run_in_background": True} if _bg else {}))


# ------------------------------------------------------------------ wait-until: a wait for a clock time
#
# A session waits until a clock time, then runs one command. Under run_in_background a loop may wait on the
# clock only when its one test orders `date` output against a literal time, in the direction that turns
# false at that time: `until` with `>`, `-ge` or `-gt`, or `while` with `<`, `-lt` or `-le`. Such a loop
# ends at that time, so it is a deadline and not a wait with no end. Equality, a second test, a second
# loop, a poll of a file and the other direction never reach the time, so each stays refused. A pause of
# 25 s or more is allowed under run_in_background only when a command follows it. The one helper for a
# wait on a time is `bin/wait-until TIME [--timeout SECS]` (its own cases: lint/test_wait_until.py).
WAIT_UNTIL_TIME = "2026-11-06T22:48:00Z"
WAIT_UNTIL_CLOCK_LOOP = (r'until [ "$(date -u +%Y-%m-%dT%H:%M:%S)" \> "2026-11-06T22:48:00" ]; '
                         r'do sleep 15; done; node tool.mjs')

# Allowed under run_in_background: a pause of 25 s or more when a command follows it, and a loop whose test
# orders the clock against a literal in the direction that ends it. A quote, a `#` or a line break ahead of a
# loop is text, so the scan still finds the loop.
add("wait-until: a pause of 600 s, then one command, is allowed under run_in_background", "allow",
    cwd=NOGIT, command="sleep 600; node tool.mjs", run_in_background=True)
add("wait-until: a clock loop, then one command, is allowed under run_in_background", "allow",
    cwd=NOGIT, command=WAIT_UNTIL_CLOCK_LOOP, run_in_background=True)
add("wait-until: the same clock loop split over lines is allowed under run_in_background", "allow",
    cwd=NOGIT, run_in_background=True,
    command='until [ "$(date -u +%Y-%m-%dT%H:%M:%S)" \\> "2026-11-06T22:48:00" ]\ndo sleep 15; done\nnode tool.mjs')
add("wait-until: a quote and a # ahead of the clock loop are text, and the loop is allowed under run_in_background",
    "allow", cwd=NOGIT, command='echo "it\'s # fine"; ' + WAIT_UNTIL_CLOCK_LOOP, run_in_background=True)

# Refused in these shapes, so a change to the clock rule cannot widen them: the clock loop in the foreground,
# a pause in the foreground, two pauses, a loop with no clock bound, a loop that names the date only inside a
# string, and gh run watch.
sh("wait-until: the clock loop in the foreground stays refused", WAIT_UNTIL_CLOCK_LOOP, "deny", "waiter",
   cwd=NOGIT)
sh("wait-until: a 30 s pause in the foreground stays refused", "sleep 30", "deny", "waiter", cwd=NOGIT)
add("wait-until: two pauses under run_in_background stay refused", "deny", "waiter", cwd=NOGIT,
    command="sleep 5; sleep 5; node tool.mjs", run_in_background=True)
add("wait-until: a loop with no clock bound stays refused under run_in_background", "deny", "waiter",
    cwd=NOGIT, command="until grep -q x f; do sleep 15; done", run_in_background=True)
add("wait-until: a loop that names the date only inside a string stays refused under run_in_background",
    "deny", "waiter", cwd=NOGIT, command='until grep -q "date" f; do sleep 15; done; node tool.mjs',
    run_in_background=True)
for _bg in (False, True):
    add("wait-until: gh run watch 7 stays refused%s" % (" under run_in_background" if _bg else ""),
        "deny", "waiter", cwd=NOGIT, command="gh run watch 7", **({"run_in_background": True} if _bg else {}))

# Refused under run_in_background. Each shape looks like a clock wait and is not one. Its test does not end the
# loop at the named time: the other direction ends it at once, equality rarely holds, a poll of a file names no
# time, and an extra test adds a condition. Or a second loop follows, or a long pause has no command after it.
# Each case covers one check in clock_loop or waiter_verdict.
add("wait-until: a loop on a literal time with no date stays refused under run_in_background", "deny",
    "waiter", cwd=NOGIT, command="until [ -s 2026-11-06T22:48:00 ]; do sleep 15; done; cmd", run_in_background=True)
add("wait-until: a loop on date with no literal time stays refused under run_in_background", "deny",
    "waiter", cwd=NOGIT, command='until [ "$(date +%s)" -gt "$X" ]; do sleep 15; done; cmd', run_in_background=True)
add("wait-until: a loop whose test has a && clause after it stays refused under run_in_background", "deny",
    "waiter", cwd=NOGIT,
    command=r'until [ "$(date -u +%Y-%m-%dT%H:%M:%S)" \> "2026-11-06T22:48:00" ] && true; do sleep 15; done; cmd',
    run_in_background=True)
add("wait-until: two clock loops in one command stay refused under run_in_background", "deny",
    "waiter", cwd=NOGIT,
    command=(r'until [ "$(date -u +%Y-%m-%dT%H:%M:%S)" \> "2026-11-06T22:48:00" ]; do sleep 15; done; '
             r'until [ "$(date -u +%Y-%m-%dT%H:%M:%S)" \> "2026-11-07T00:00:00" ]; do sleep 15; done; cmd'),
    run_in_background=True)
add("wait-until: a bare sleep of 600 s with nothing after it stays refused under run_in_background", "deny",
    "waiter", cwd=NOGIT, command="sleep 600", run_in_background=True)
add("wait-until: a while loop that waits while the clock is later than a literal stays refused under "
    "run_in_background", "deny", "waiter", cwd=NOGIT,
    command='while [ "$(date +%s)" -gt 1700000000 ]; do sleep 15; done; cmd', run_in_background=True)
add("wait-until: a loop that tests the date for equality stays refused under run_in_background", "deny",
    "waiter", cwd=NOGIT, command='until [ "$(date +%F)" = "2026-11-06" ]; do sleep 15; done; cmd',
    run_in_background=True)
add("wait-until: a loop that polls a file for a dated name stays refused under run_in_background", "deny",
    "waiter", cwd=NOGIT, command='until grep -q "$(date +%F)" 2026-11-07.log; do sleep 15; done; cmd',
    run_in_background=True)
add("wait-until: a clock loop with an extra file test stays refused under run_in_background", "deny",
    "waiter", cwd=NOGIT, command='until [ "$(date +%s)" -gt 1700000000 -a -f done.flag ]; do sleep 15; done; cmd',
    run_in_background=True)
add("wait-until: a clock loop then a second loop with no pause stays refused under run_in_background", "deny",
    "waiter", cwd=NOGIT,
    command=r'until [ "$(date -u +%Y-%m-%dT%H:%M:%S)" \> "2026-11-06T22:48:00" ]; do sleep 15; done; '
            r'until [ -f x ]; do :; done; cmd',
    run_in_background=True)
# A read of another command is no clock read, even with a +%s format, so its order against an epoch never
# reaches a clock time.
add("wait-until: a loop on a read of another command with a +%s format stays refused under run_in_background",
    "deny", "waiter", cwd=NOGIT, command='until [ "$(clock +%s)" -gt 1762470000 ]; do sleep 15; done; cmd',
    run_in_background=True)
add("wait-until: a loop that tests the clock for equality with a full ISO time stays refused under "
    "run_in_background", "deny", "waiter", cwd=NOGIT,
    command='until [ "$(date -u +%Y-%m-%dT%H:%M:%S)" = "2026-11-06T22:48:00" ]; do sleep 15; done; cmd',
    run_in_background=True)
add("wait-until: a loop written as an arithmetic test stays refused under run_in_background", "deny",
    "waiter", cwd=NOGIT, command='until (( $(date +%s) -gt 1762470000 )); do sleep 15; done; cmd',
    run_in_background=True)
# Each read and literal disagree in kind, so the test never turns and the loop never ends: `-gt` and `-ge` on a
# text read are an error, not an order; a text order of epoch digits against an ISO time puts the digits first,
# so `\>` never holds and `\<` always does.
add("wait-until: a numeric order on an ISO date-time read stays refused under run_in_background", "deny",
    "waiter", cwd=NOGIT,
    command='until [ "$(date -u +%Y-%m-%dT%H:%M:%S)" -gt "2026-11-06T22:48:00" ]; do sleep 15; done; cmd',
    run_in_background=True)
add("wait-until: a numeric order with -ge on an ISO date-time read stays refused under run_in_background", "deny",
    "waiter", cwd=NOGIT,
    command='until [ "$(date -u +%Y-%m-%dT%H:%M:%S)" -ge "2026-11-06T22:48:00" ]; do sleep 15; done; cmd',
    run_in_background=True)
add("wait-until: an ISO date-time read ordered numerically against an epoch stays refused under run_in_background",
    "deny", "waiter", cwd=NOGIT,
    command='until [ "$(date -u +%Y-%m-%dT%H:%M:%S)" -ge 1762470000 ]; do sleep 15; done; cmd', run_in_background=True)
add("wait-until: a text order of an epoch read against an ISO time stays refused under run_in_background", "deny",
    "waiter", cwd=NOGIT,
    command=r'until [ "$(date +%s)" \> "2026-11-06T22:48:00" ]; do sleep 15; done; cmd', run_in_background=True)
add("wait-until: a [[ ]] text order of an epoch read against an ISO time stays refused under run_in_background",
    "deny", "waiter", cwd=NOGIT,
    command='until [[ "$(date +%s)" > "2026-11-06T22:48:00" ]]; do sleep 15; done; cmd', run_in_background=True)
add("wait-until: a while text order of an epoch read below an ISO time stays refused under run_in_background",
    "deny", "waiter", cwd=NOGIT,
    command=r'while [ "$(date +%s)" \< "2026-11-06T22:48:00" ]; do sleep 15; done; cmd', run_in_background=True)
# A `for` loop is a loop of its own, so the command has two loops and the clock loop is not its one loop.
add("wait-until: a clock loop with a command body, then a for loop with pauses, stays refused under run_in_background",
    "deny", "waiter", cwd=NOGIT,
    command='until [ "$(date +%s)" -gt 1762470000 ]; do cmd; done; for i in 1 2; do sleep 15; done',
    run_in_background=True)
# A numeric order needs an epoch read and an epoch literal; a text order needs an ISO read and an ISO literal.
# Each pairing here crosses the two, so the test never turns and the loop never ends.
add("wait-until: a numeric order on a +%s read against an ISO date-time stays refused under run_in_background",
    "deny", "waiter", cwd=NOGIT,
    command='until [ "$(date +%s)" -gt "2026-11-06T22:48:00" ]; do sleep 15; done; cmd', run_in_background=True)
add("wait-until: a text order on an ISO read against an epoch stays refused under run_in_background", "deny",
    "waiter", cwd=NOGIT,
    command=r'until [ "$(date -u +%Y-%m-%dT%H:%M:%S)" \> 1762470000 ]; do sleep 15; done; cmd', run_in_background=True)
# A read whose time is not the clock reaches no clock time, whatever its format: a fixed date, a file's time, or a
# text format that is not an ISO date-time.
add("wait-until: a loop on a fixed date read with -d stays refused under run_in_background", "deny",
    "waiter", cwd=NOGIT,
    command='until [ "$(date -d 2026-01-01 +%s)" -gt 1762470000 ]; do sleep 15; done; cmd', run_in_background=True)
add("wait-until: a loop on a fixed date read with --date stays refused under run_in_background", "deny",
    "waiter", cwd=NOGIT,
    command='until [ "$(date --date=2026-01-01 +%s)" -gt 1762470000 ]; do sleep 15; done; cmd', run_in_background=True)
add("wait-until: a loop on a file's time read with -r stays refused under run_in_background", "deny",
    "waiter", cwd=NOGIT,
    command='until [ "$(date -r stamp.txt +%s)" -gt 1762470000 ]; do sleep 15; done; cmd', run_in_background=True)
add("wait-until: a loop on a text format that is not an ISO date-time stays refused under run_in_background",
    "deny", "waiter", cwd=NOGIT,
    command=r'until [ "$(date +%m-%d)" \> "2026-11-06T22:48:00" ]; do sleep 15; done; cmd', run_in_background=True)
# Allowed under run_in_background: a numeric order of an epoch read, and a while loop that waits while the clock is
# earlier than a literal. The order and the read agree in kind, so the test turns at the time it names.
add("wait-until: a clock loop on an epoch that is reached is allowed under run_in_background", "allow",
    cwd=NOGIT, command='until [ "$(date +%s)" -ge 1762470000 ]; do sleep 15; done; cmd', run_in_background=True)
add("wait-until: a while loop that waits while the clock is earlier than a literal is allowed under "
    "run_in_background", "allow", cwd=NOGIT,
    command=r'while [ "$(date -u +%FT%T)" \< "2026-11-06T22:48:00" ]; do sleep 15; done; cmd',
    run_in_background=True)
# The ISO formats a session writes for a text order, with and without the zone suffix and the -u flag.
add("wait-until: a clock loop on a read with +%FT%TZ is allowed under run_in_background", "allow", cwd=NOGIT,
    command=r'until [ "$(date -u +%FT%TZ)" \> "2026-11-06T22:48:00Z" ]; do sleep 15; done; cmd', run_in_background=True)
add("wait-until: a clock loop on a read with +%FT%T and no -u is allowed under run_in_background", "allow", cwd=NOGIT,
    command=r'until [ "$(date +%FT%T)" \> "2026-11-06T22:48:00" ]; do sleep 15; done; cmd', run_in_background=True)

# Each waiter-family remedy names the helper by its bin path in backticks, since a bare `wait-until` is not on
# PATH in a session. The remedy check below reads those forms.
for _label, _trigger, _rule in REMEDY_TRIGGERS:
    sh("wait-until: the remedy of %s names the helper by its bin path" % _label, _trigger, "deny", _rule,
       cwd=NOGIT, carries=("`bin/wait-until",))

# The helper is never refused, in the foreground or under run_in_background. Nothing judges it yet, so these
# pin that a waiter rule never refuses the one allowed form. A command after the helper is allowed too.
for _command in ("wait-until %s" % WAIT_UNTIL_TIME, "wait-until %s --timeout 500" % WAIT_UNTIL_TIME):
    sh("wait-until: %s is allowed in the foreground" % _command, _command, "allow", cwd=NOGIT)
    add("wait-until: %s is allowed under run_in_background" % _command, "allow", cwd=NOGIT,
        command=_command, run_in_background=True)
add("wait-until: the helper, then one command, is allowed under run_in_background", "allow", cwd=NOGIT,
    command="wait-until %s; node tool.mjs" % WAIT_UNTIL_TIME, run_in_background=True)

# THE REMEDY CHECK. Every command form that a waiter-family remedy names in backticks is allowed, in the
# foreground and under run_in_background: the guard must not refuse the advice it gives. The remedies are read
# from guard_stream, the one home of them. A form is tried with its optional `[...]` part and without it.
WAIT_SAMPLES = {"PID": "12345", "SECS": "500", "TIME": WAIT_UNTIL_TIME, "T": WAIT_UNTIL_TIME}
REMEDY_CONSTANTS = ("WAITER_REASON", "LIVE_STREAM_REASON", "PATTERN_POLLER_REASON")


def remedy_forms(reason):
    """The command forms a remedy names in backticks, each placeholder filled from WAIT_SAMPLES. A placeholder
    with no sample is kept as `<NAME>`, so the check names it."""
    forms = []
    for span in re.findall(r"`([^`]+)`", reason):
        for form in (re.sub(r"[\[\]]", "", span), re.sub(r"\s*\[[^\]]*\]", "", span)):
            words = [WAIT_SAMPLES.get(w, "<%s>" % w) if re.fullmatch(r"[A-Z][A-Z_]*", w) else w
                     for w in form.split()]
            forms.append(" ".join(words))
    return list(dict.fromkeys(forms))


def remedy_refusal(form):
    """'' when the guard allows `form` in the foreground and under run_in_background, else what it refused."""
    for background in (False, True):
        tool_input = {"command": form}
        if background:
            tool_input["run_in_background"] = True
        got, reason = decide({"raw": None, "tool": "Bash", "cwd": NOGIT, "session": None,
                              "env_path": None, "tool_input": tool_input})
        if got != "allow":
            return "%s%s is %s (%s)" % (form, " under run_in_background" if background else "", got, reason[:70])
    return ""


def remedy_check(constant):
    """A log check: the remedy named by `constant` names at least one command form, every form is a placeholder
    the check can fill, and the guard allows every form."""
    def check():
        import guard_stream  # the one home of the waiter-family remedies (hooks/guard_stream.py)
        reason = getattr(guard_stream, constant, None)
        if not isinstance(reason, str):
            return False, "guard_stream has no %s to read the remedy from" % constant
        forms = remedy_forms(reason)
        if not forms:
            return False, "%s names no command form in backticks, so the check reads nothing" % constant
        unfilled = [f for f in forms if "<" in f]
        if unfilled:
            return False, "%s names a placeholder the check cannot fill: %s" % (constant, unfilled[0])
        refused = [m for m in (remedy_refusal(f) for f in forms) if m]
        if refused:
            return False, "%s names a form the guard refuses: %s" % (constant, refused[0])
        return True, "%s names %d command forms, and the guard allows each" % (constant, len(forms))
    return check


# =========================================================================== background end condition
#
# Owner ruling 2026-10-13 23:41 CDT, "End condition at start". A background server or watcher needs
# an `until: <condition>` note in the Bash call's `description`. A refusal without one names the note
# in its remedy. stall_watch.py --stop shows the note beside each quiet shell (its cases are in
# test_stall_watch_stop.py). Incident: a file server on port 3202 ran 27 h unnoticed.
# A one-off build or test is not a long-runner, so it passes with no note. `gh run watch` is no
# long-runner case either: the waiter rule refuses it under run_in_background, with or without a
# note (decision ci-wait-reads-run-status, "Claude's own waits").
# Rule name: background-end. The allow cases pin that the rule refuses no finished job, and that a
# note does not unlock a rule that already refuses (`tail -f`, live-stream).

add("background-end: a python http.server under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="python3 -m http.server 3202", run_in_background=True)
add("background-end: npm run dev under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="npm run dev", run_in_background=True)
add("background-end: npx vite under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="npx vite --port 5173", run_in_background=True)
add("background-end: next dev under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="npx next dev -p 3000", run_in_background=True)
add("background-end: serve under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="npx serve -s dist -l 3000", run_in_background=True)
add("background-end: tsc --watch under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="npx tsc --watch", run_in_background=True)
add("background-end: an empty until in the description is no note, so refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="python3 -m http.server 3202", run_in_background=True,
    description="Serve q_max files. until:   ")
add("background-end: a description with no until is no note, so refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="npm run dev", run_in_background=True, description="dev server for the q_max page")
add("background-end: an until written in the command text is no note, so refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="npm run dev  # until: round 1 bids are served", run_in_background=True)
add("background-end: a server after a quoted # is still refused, the # does not hide it",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command='echo "# q_max"; npm run dev', run_in_background=True)
add("background-end: a server after a lone apostrophe in quotes is still refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command='echo "it\'s up"; python3 -m http.server 3202', run_in_background=True)
add("background-end: a note does not unlock tail -f, the live-stream rule still refuses it",
    "deny", "live-stream", cwd=NOGIT, carries=("live-stream",),
    command="tail -f server.out", run_in_background=True,
    description="until: round 1 bids are served")

add("background-end: a server with an until note in its description is allowed", "allow",
    cwd=NOGIT, command="python3 -m http.server 3202", run_in_background=True,
    description="Serve q_max files on 3202. until: round 1 bids are served")
add("background-end: a dev server with an until note is allowed", "allow", cwd=NOGIT,
    command="npm run dev", run_in_background=True, description="until: round 1 bids are served")
add("background-end: a build under run_in_background needs no note, allowed", "allow",
    cwd=NOGIT, command="npm run build", run_in_background=True)
add("background-end: the guard suite under run_in_background needs no note, allowed", "allow",
    cwd=NOGIT, command="python3 hooks/test_guard.py", run_in_background=True)
add("background-end: a note does not unlock gh run watch, the waiter rule still refuses it",
    "deny", "waiter", cwd=NOGIT, command="gh run watch 7", run_in_background=True,
    description="until: run 7 ends")
add("background-end: a server named in quoted text is data, allowed", "allow", cwd=NOGIT,
    command='echo "python3 -m http.server 3202"', run_in_background=True)
add("background-end: a server named in a heredoc body is data, allowed", "allow", cwd=NOGIT,
    command="cat > notes.txt <<'EOF'\nDon't run npm run dev here\nEOF", run_in_background=True)
add("background-end: a server named in a multi-line quoted string is data, allowed", "allow",
    cwd=NOGIT, command='echo "first line\nnpm run dev later"', run_in_background=True)
add("background-end: a server named in a comment line is not run, allowed", "allow", cwd=NOGIT,
    command="# start npm run dev later\necho ready", run_in_background=True)

# Each starts a server or watcher that never ends on its own, and has no note: a flag before the
# script name, a Windows executable name, a wrapper that runs the command, or a script name that serves or watches.
add("background-end: npm --prefix web run dev under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="npm --prefix web run dev", run_in_background=True)
add("background-end: npm -w web run dev under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="npm -w web run dev", run_in_background=True)
add("background-end: pnpm -C web dev under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="pnpm -C web dev", run_in_background=True)
add("background-end: pnpm --filter web dev under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="pnpm --filter web dev", run_in_background=True)
add("background-end: npm.cmd run dev under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="npm.cmd run dev", run_in_background=True)
add("background-end: python.exe -m http.server under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="python.exe -m http.server", run_in_background=True)
add("background-end: python -u -m http.server under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="python -u -m http.server", run_in_background=True)
add("background-end: py -3 -m http.server under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="py -3 -m http.server", run_in_background=True)
add("background-end: cmd /c npm run dev under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="cmd /c npm run dev", run_in_background=True)
# A backslash before ; hides the server in a cmd /c script when the cmd /c tail is read as bash text.
add("background-end: a cmd /c with a backslash before ; hides npm run dev under run_in_background, denies",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command=r'cmd /c "echo C:\x\; npm run dev"', run_in_background=True)
add("background-end: bash -c around npm run dev under run_in_background is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command='bash -c "npm run dev"', run_in_background=True)
add("background-end: a '# ready' comment opener in a bash -c string does not hide npm run dev",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command='bash -c "echo \'# ready\'; npm run dev"', run_in_background=True)
add("background-end: a PowerShell call operator before npm run dev is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"), tool="PowerShell",
    command="& npm run dev", run_in_background=True)
add("background-end: npm run dev in a subshell under run_in_background is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="(npm run dev)", run_in_background=True)
add("background-end: npx vite@5 under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="npx vite@5", run_in_background=True)
add("background-end: npx vite build --watch under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=("background-end", "until:"),
    command="npx vite build --watch", run_in_background=True)

# Pins: these end by themselves, and must stay allowed with no note.
add("background-end: vite build under run_in_background needs no note, allowed", "allow",
    cwd=NOGIT, command="vite build", run_in_background=True)
add("background-end: next build under run_in_background needs no note, allowed", "allow",
    cwd=NOGIT, command="next build", run_in_background=True)
add("background-end: a server named inside a bash -c string is data, allowed", "allow",
    cwd=NOGIT, command='bash -c "echo \'npm run dev\'"', run_in_background=True)


# Each deny starts a server or watcher the roster lacked. `--watch=false`, `--watch false`, `npm run build-docs` allow.
DEVSERVER_DENY = ("background-end", "until:")

add("background-end: bun --watch server.ts under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command="bun --watch server.ts", run_in_background=True)
add("background-end: bun --hot server.ts under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command="bun --hot server.ts", run_in_background=True)
add("background-end: deno task dev under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command="deno task dev", run_in_background=True)
add("background-end: flask run under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command="flask run", run_in_background=True)
add("background-end: deno serve main.ts under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command="deno serve main.ts", run_in_background=True)
add("background-end: uvicorn app:app --reload under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command="uvicorn app:app --reload", run_in_background=True)
add("background-end: jupyter lab under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command="jupyter lab", run_in_background=True)
add("background-end: webpack serve under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command="webpack serve", run_in_background=True)
add("background-end: astro dev under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command="astro dev", run_in_background=True)
add("background-end: rails s under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command="rails s", run_in_background=True)
add("background-end: streamlit run app.py under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command="streamlit run app.py", run_in_background=True)
add("background-end: npm run build:watch under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command="npm run build:watch", run_in_background=True)
add("background-end: npm run dev:frontend under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command="npm run dev:frontend", run_in_background=True)
add("background-end: npm run dev-server under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command="npm run dev-server", run_in_background=True)
add("background-end: npm run start-api under run_in_background with no note is refused",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command="npm run start-api", run_in_background=True)

add("background-end: jest --watch=false under run_in_background needs no note, allowed", "allow",
    cwd=NOGIT, command="jest --watch=false", run_in_background=True)
add("background-end: vitest --watch=false under run_in_background needs no note, allowed", "allow",
    cwd=NOGIT, command="vitest --watch=false", run_in_background=True)
add("background-end: vitest --watch false under run_in_background needs no note, allowed", "allow",
    cwd=NOGIT, command="vitest --watch false", run_in_background=True)
add("background-end: npm test -- --watch=false under run_in_background needs no note, allowed",
    "allow", cwd=NOGIT, command="npm test -- --watch=false", run_in_background=True)
add("background-end: npm run build-docs under run_in_background needs no note, allowed", "allow",
    cwd=NOGIT, command="npm run build-docs", run_in_background=True)

# Bash reads `\&` and `\;` as text, so the server after them is one segment that the background-end check must still see.
add("background-end: a bash cd with a backslash before && hides npm run dev, denies",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command=r"cd C:\x\&& npm run dev", run_in_background=True)
add("background-end: a bash pwsh -c with a backslash before ; hides npm run dev, denies",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY,
    command=r'pwsh -c "cd C:\x\; npm run dev"', run_in_background=True)
add("background-end: a PowerShell cd with a quoted backslash path before ; still denies npm run dev",
    "deny", "background-end", cwd=NOGIT, carries=DEVSERVER_DENY, tool="PowerShell",
    command=r'cd "C:\x\"; npm run dev', run_in_background=True)


# =========================================================================== 2c-bis. the WSL launch allow list
#
# Owner ruling 2026-10-13 15:20: an agent may run a fixed list of Linux test commands through WSL.
# Allowed: `wsl -e` or `wsl --exec` with a test runner and test paths, from any role. Refused: every
# other WSL form. A refusal's reason names WSL_RULE. The allow cases pin the allowed forms so the
# rule cannot narrow them.

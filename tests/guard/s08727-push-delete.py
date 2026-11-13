# section 8727
FAMILY = "push-delete"

LEASE = " --force-with-lease --force-if-includes"
SHA = "0123456789abcdef0123456789abcdef01234567"
REMEDY = "retry with --force-with-lease --force-if-includes"


def push_case(name, tail, expected, cwd=PUSHFEAT, tool="Bash", rule=None, silent=False, lacks=(), word=VCS):
    """One `git push` case. An ask names `rule` when one is given (rulings 206 a and 207 a), else
    force-push. `silent` marks an allow that must print nothing. `word` is the command word the call
    names: the plain `git`, or a form of it that the shell reads as git."""
    sh("push: " + name, word + " push " + tail, expected,
       rule or ("force-push" if expected != "allow" else None), cwd=cwd, tool=tool,
       carries=REMEDY if expected == "deny" else (), silent=silent, lacks=lacks)


# ALLOW: a lease that cannot overwrite newer work, off the default branch.
push_case("lease with includes, bare", "--force-with-lease --force-if-includes", "allow")
push_case("lease with includes, naming a ref", "--force-with-lease=feat --force-if-includes origin feat",
          "allow")
push_case("lease with includes, naming ref and sha",
          "--force-with-lease=feat:" + SHA + " --force-if-includes origin feat", "allow")
push_case("lease naming ref and sha is stale-safe alone", "--force-with-lease=feat:" + SHA + " origin feat",
          "allow")
push_case("lease with includes, flags in the other order", "--force-if-includes --force-with-lease origin HEAD",
          "allow")
push_case("lease with includes from the PowerShell tool as well", "--force-with-lease --force-if-includes",
          "allow", tool="PowerShell")
push_case("lease with includes to main-fix, not the default branch",
          "--force-with-lease --force-if-includes origin HEAD:main-fix", "allow")
push_case("lease with includes to a branch under the default name's prefix",
          "--force-with-lease --force-if-includes origin HEAD:refs/heads/main-fix", "allow")
push_case("lease to a branch main-fix when the default branch is trunk",
          "--force-with-lease --force-if-includes origin HEAD:main", "allow", cwd=PUSHTRUNK)

# DENY with the remedy: any force that can overwrite newer work.
push_case("the long force flag", "--force", "deny")
push_case("the short force flag", "-f origin feat", "deny")
push_case("the short force flag inside a bundle", "-fu origin feat", "deny")
push_case("a force prefix", "--forc origin feat", "deny")
push_case("a shorter force prefix", "--fo origin feat", "deny")
push_case("a plus refspec", "origin +HEAD:feat", "deny")
push_case("a plus refspec with the branch name", "origin +feat", "deny")
push_case("a bare lease without includes", "--force-with-lease", "deny")
push_case("a lease naming a ref, without includes", "--force-with-lease=feat origin feat", "deny")
push_case("a force beside a lease and includes", "--force" + LEASE, "deny")
push_case("includes alone is not a force, so a plain push allows", "--force-if-includes", "allow")
push_case("a force while the default branch is trunk, main is ordinary there",
          "--force origin HEAD:main", "deny", cwd=PUSHTRUNK)
push_case("a push option value is not the remote", "--force-with-lease --force-if-includes -o x origin HEAD:trunk",
          "ask", cwd=PUSHTRUNK)
push_case("a push option value with --push-option is not the remote",
          "--force-with-lease --force-if-includes --push-option x origin HEAD:trunk", "ask",
          cwd=PUSHTRUNK)
push_case("a force with no default branch ref, to a feature branch", "--force origin feat", "deny",
          cwd=PUSHNOHEAD)

# ASK: any forced push that reaches the default branch, or whose destination cannot be read.
for form, tail in (
        ("bare, on main", "--force"),
        ("lease with includes, bare, on main", "--force-with-lease --force-if-includes"),
        ("lease with includes, HEAD, on main", "--force-with-lease --force-if-includes origin HEAD"),
        ("the current branch named, on main", "--force-with-lease --force-if-includes origin main"),
        ("HEAD:main", "--force-with-lease --force-if-includes origin HEAD:main"),
        ("a full ref", "--force-with-lease --force-if-includes origin x:refs/heads/main"),
        ("a plus refspec", "origin +HEAD:main"),
        ("a pinned lease", "--force-with-lease=main:" + SHA + " origin HEAD:main"),
        ("--mirror", "--mirror --force"),
        ("--mirror alone, which forces by itself", "--mirror"),
        ("--all", "--all --force"),
        ("--all with a lease", "--all" + LEASE),
        ("--branches, git's alias of --all", "--branches --force"),
        ("--branches with a lease", "--branches" + LEASE),
        ("a glob refspec", "--force origin refs/heads/*:refs/heads/*"),
        ("the short flag", "-f origin HEAD:main")):
    push_case("forced to the default branch asks: " + form, tail, "ask",
              cwd=PUSHMAIN if "on main" in form or form == "HEAD" else PUSHFEAT)
push_case("forced to the default branch from a feature branch asks", "--force origin HEAD:main", "ask")
push_case("forced to the default branch named by origin/HEAD, not by name", "--force origin HEAD:trunk",
          "ask", cwd=PUSHTRUNK)
# A local branch named origin/trunk must not hide the name origin/HEAD holds: the second case is the
# same push where that branch is absent.
push_case("forced to the default branch named by origin/HEAD asks", "--force origin trunk", "ask",
          cwd=PUSHTRUNK)
push_case("forced to the default branch asks when a local branch is named origin/trunk",
          "--force origin trunk", "ask", cwd=PUSHTRUNKLOCAL)
push_case("forced to master when no origin/HEAD is read asks (fallback)", "--force origin HEAD:master",
          "ask", cwd=PUSHNOHEAD)
push_case("forced to main when no origin/HEAD is read asks (fallback)", "--force origin HEAD:main",
          "ask", cwd=PUSHNOHEAD)
# A tag named main makes the short read of HEAD print `heads/main`. The guard must still read main.
push_case("a tag named like the branch, a lease push of HEAD on main asks",
          LEASE.strip() + " origin HEAD", "ask", cwd=PUSHSAMETAG)
push_case("a tag named like the branch, a bare lease push on main asks", LEASE.strip(), "ask",
          cwd=PUSHSAMETAG)
push_case("forced from a detached HEAD, no current branch to resolve, asks",
          "--force-with-lease --force-if-includes", "ask", cwd=PUSHDETACHED)
push_case("forced where git cannot be read asks",
          "--force-with-lease --force-if-includes origin HEAD:feat", "ask",
          cwd=NOGIT)
push_case("forced with a plus where git cannot be read asks", "origin +HEAD:feat", "ask", cwd=NOGIT)

LE = "--force-with-lease --force-if-includes "
push_case("a quoted refspec to the default branch asks", LE + 'origin "HEAD:main"', "ask")
push_case("a single-quoted plus refspec to the default branch asks", "origin '+main'", "ask")
push_case("a quoted remote is unquoted", LE + '"origin" HEAD:main', "ask")
push_case("lease with --repo=, refspec to the default branch asks", "--repo=origin " + LE + "HEAD:main",
          "ask")
push_case("lease with --repo and its value, refspec to the default branch asks",
          "--repo origin " + LE + "HEAD:main", "ask")
push_case("lease with --repo off the default branch", "--repo=origin " + LE + "HEAD:feat", "allow")
push_case("a delete refspec at the default branch asks", "origin :main", "ask")
push_case("a delete refspec at a full default ref asks", "origin :refs/heads/main", "ask")
push_case("deleting with --delete at the default branch asks", "--delete origin main", "ask")
push_case("deleting with -d at the default branch asks", "-d origin main", "ask")
# A dangling origin/HEAD does not hide the default branch (owner's read order 2026-10-16). The three
# forms below reach main and ask, exactly as they do where origin/HEAD resolves.
push_case("a dangling origin/HEAD, a forced push to main asks",
          "--force-with-lease --force-if-includes origin main", "ask", cwd=PUSHDANGLING)
push_case("a dangling origin/HEAD, a delete refspec at main asks", "origin :main", "ask",
          cwd=PUSHDANGLING)
push_case("a dangling origin/HEAD, --delete after the remote at main asks", "origin --delete main", "ask",
          cwd=PUSHDANGLING)
# Where origin/HEAD does not name the branch (dangling, or unset), main AND master stay protected:
# the read order finds origin/main, but a repository that has origin/main may still hold master.
for why, fixture in (("a dangling origin/HEAD", PUSHDANGLING),
                   ("no origin/HEAD, origin/main present", PUSHNOHEADMAIN)):
    push_case(why + ", a forced push to master asks",
              "--force-with-lease --force-if-includes origin master", "ask", cwd=fixture)
    push_case(why + ", a delete refspec at master asks", "origin :master", "ask", cwd=fixture)
    push_case(why + ", --delete at master asks", "origin --delete master", "ask", cwd=fixture)
    push_case(why + ", a delete off the default names allows", "origin :feat", "allow", cwd=fixture)
push_case("no origin/HEAD, only origin/master present, a delete refspec at main asks", "origin :main",
          "ask", cwd=PUSHONLYMASTER)
push_case("no origin/HEAD, only origin/master present, a delete off the default names allows",
          "origin :feat", "allow", cwd=PUSHONLYMASTER)
# A push reads the PUSHED remote's default branch (upstream/HEAD -> main), never origin's (develop).
push_case("another remote, --delete at its default branch asks", "--delete upstream main", "ask",
          cwd=PUSHUPSTREAM)
push_case("another remote, --delete at the branch origin names as default allows, it is ordinary there",
          "--delete upstream develop", "allow", cwd=PUSHUPSTREAM)
push_case("another remote, a bare lease follows branch.feat.remote to its default branch asks",
          LEASE.strip(), "ask", cwd=PUSHUPSTREAM)
push_case("origin with its own origin/HEAD, --delete at its default branch asks", "--delete origin develop",
          "ask", cwd=PUSHUPSTREAM)
push_case("a deletion off the default branch, refspec", "origin :feat", "allow")
push_case("a deletion off the default branch, --delete", "--delete origin feat", "allow")
push_case("--no-force-if-includes cancels --force-if-includes",
          "--force-with-lease --force-if-includes --no-force-if-includes", "deny")
push_case("--no-force-with-lease cancels the lease, so nothing is forced",
          "--force-with-lease --no-force-with-lease --force-if-includes origin feat", "allow")
push_case("a glued push option is not -f", "-ofoo origin feat", "allow")
push_case("a push option with its value is not -f", "-o foo origin feat", "allow")
push_case("a bare lease with push.default upstream follows the upstream to the default branch",
          LE.strip(), "ask", cwd=PUSHUP)
push_case("a bare lease with push.default upstream follows an upstream off the default branch",
          LE.strip(), "allow", cwd=PUSHUPSELF)
push_case("a bare lease with push.default upstream and no upstream asks", LE.strip(), "ask",
          cwd=PUSHNOUP)
push_case("a bare lease with push.default matching asks", LE.strip(), "ask", cwd=PUSHMATCH)
push_case("a bare lease with an abbreviated force-with-lease and includes allows",
          "--force-with --force-if-inc", "allow")

push_case("a glued push option then force denies", "-ofoo --force origin feat", "deny")
push_case("a glued push option in a cluster then force denies", "-vofoo --force origin feat", "deny")
push_case("a glued push option, other letters, then force denies", "-oyo --force origin feat", "deny")
push_case("a push option with its value then force denies", "-o foo --force origin feat", "deny")

# THE TARGET DIRECTORY. Config and the default branch are read where the push runs: a `git -C`,
# a `cd` before it, a `-c` override on the call. The session's cwd here is never the answer.
sh("push: lease with git -C naming the default branch's checkout asks",
   VCS + " -C " + slash(PUSHMAIN) + " push " + LE.strip(), "ask", "force-push", cwd=PUSHFEAT)
sh("push: lease with git -C naming a feature checkout allows from the main checkout",
   VCS + " -C " + slash(PUSHFEAT) + " push " + LE.strip(), "allow", cwd=PUSHMAIN)
sh("push: a git -C on another call is not the push's directory",
   VCS + " -C " + slash(PUSHMAIN) + " status && " + VCS + " push " + LE.strip(), "allow",
   cwd=PUSHFEAT)
sh("push: lease after cd into the default branch's checkout asks, the leading cd is no second command",
   "cd " + slash(PUSHMAIN) + " && " + VCS + " push " + LE.strip(), "ask", "force-push",
   cwd=PUSHFEAT, lacks=(CHAIN_ASK,))
sh("push: lease after cd into a feature checkout allows from the main checkout",
   "cd " + slash(PUSHFEAT) + " && " + VCS + " push " + LE.strip(), "allow", cwd=PUSHMAIN)
sh("push: lease with git -C naming a directory that is not there asks",
   VCS + " -C " + slash(os.path.join(ROOT, "nowhere")) + " push " + LE.strip(), "ask", "force-push",
   cwd=PUSHFEAT)
sh("push: lease with -c push.default=upstream follows the upstream to the default branch",
   VCS + " -c push.default=upstream push " + LE.strip(), "ask", "force-push", cwd=PUSHUP)
sh("push: lease with -c push.default=current ignores the repository's upstream",
   VCS + " -c push.default=current push " + LE.strip(), "allow", cwd=PUSHUP)
sh("push: lease with -c push.default=matching asks",
   VCS + " -c push.default=matching push " + LE.strip(), "ask", "force-push", cwd=PUSHFEAT)

# THE COMMAND WORD SPLIT OR QUOTED INTO PIECES. The guard reads such a word as `git`, as the shell does.
# A shlex reader does that for the shell forms below, which already ask: green locks that keep it so.
# Bash's ANSI-C quoting also expands to `git`, but the reader does not unquote `$'...'`, so the word reads
# as `$git` and the act is allowed. Those are the red rows. Each form expects the plain word's verdict.
SPLIT_FORCE = "--force origin main"
SPLIT_PUSH_MAIN = "origin HEAD:main"
SPLIT_ANSI_WORDS = ["$'g'it", "g$'i't", "$'\\147it'"]
SPLIT_SHELL_WORDS = ["g'i't", 'gi""t', '"g"it', "\\git", 'g""it', "gi\\t", "env g'i't", "command g'i't"]
for _word in SPLIT_ANSI_WORDS + SPLIT_SHELL_WORDS:
    push_case("split word " + _word + " force-pushes main, asks", SPLIT_FORCE, "ask", word=_word)
    push_case("split word " + _word + " pushes to main, asks", SPLIT_PUSH_MAIN, "ask",
              rule=PUSH_MAIN_RULE, word=_word)
# Controls: a plain word that only contains git is text, so it stays allowed.
sh("split word control: digit, a word with git inside, allows", "digit", "allow")
sh("split word control: gitk-free, a word with git inside, allows", "gitk-free", "allow")
sh("split word control: echo git, git as text, allows", "echo git", "allow")

# FALSE ALARMS: a guard that cries wolf is spent.
# Re-pointed from allow by ruling 207 a: a non-forced push of main asks.
push_case("a non-forced push of main asks, on main", "origin main", "ask", cwd=PUSHMAIN, rule=PUSH_MAIN_RULE)
# PUSHMAIN has no upstream, so git refuses a bare push itself ("has no upstream branch"): no ask is needed.
push_case("a bare push on main with no upstream is git's refusal, allows", "", "allow", cwd=PUSHMAIN)
push_case("a non-forced push with -u of the current branch", "-u origin HEAD", "allow")
push_case("a non-forced push with -u where git cannot be read", "-u origin HEAD", "allow", cwd=NOGIT)
push_case("a push of a branch whose name holds force", "origin force-fix", "allow")
# DATA, NOT A PUSH. A forced push to the default branch named inside a JSON payload piped to python
# runs nothing, so it allows.
sh("push: a JSON payload naming a forced push to main, piped to python, allows",
   "printf '%s' '" + json.dumps({"tool_input": {"command": VCS + " push --force origin main"}})
   + "' | python hooks/guard.py", "allow", cwd=PUSHMAIN)
sh("false alarm: --force quoted in a commit message",
   VCS + ' commit -m "never git push --force here"', "allow", cwd=PUSHFEAT)
sh("false alarm: --force quoted in an echo", 'echo "git push --force"', "allow", cwd=PUSHFEAT)
sh("false alarm: --force as a log grep pattern", VCS + " log --grep=--force", "allow", cwd=PUSHFEAT)
sh("false alarm: --force in a heredoc body",
   "cat <<'EOF'\n" + VCS + " push --force\nEOF", "allow", cwd=PUSHFEAT)
sh("false alarm: a lease to main-fix", VCS + " push --force-with-lease --force-if-includes origin HEAD:main-fix",
   "allow", cwd=PUSHMAIN)
# A `git push` inside a python3 -c argument whose quotes are escaped. The `+1` is printed, not pushed, but
# the push reader takes it as a `+` refspec. The two controls pin the plain push and a real force in the same shape.
sh("false alarm: a python -c that prints +1 after a plain push allows, escaped quotes",
   r'python3 -c "import os; os.system(\"' + VCS + r' push origin HEAD:x\"); print(\"+1\")"',
   "allow", cwd=PUSHFEAT)
sh("python -c escaped plain push allows (control)",
   r'python3 -c "import os; os.system(\"' + VCS + r' push origin HEAD:x\")"', "allow", cwd=PUSHFEAT)
sh("python -c escaped forced push still denies (control)",
   r'python3 -c "import os; os.system(\"' + VCS + r' push -f origin x\")"', "deny", "force-push",
   cwd=PUSHFEAT, carries=REMEDY)
# PRINTED, NOT RUN. A forced push quoted inside a print or an echo is text the interpreter shows, so each
# allows. The nested reader splits on the escaped quotes and takes the printed text as a command. The
# control pins a forced push to main that bash -c runs: it asks on the head and on main.
# MUTATE_ONLY="nested quote" runs these cases alone.
sh("push: nested quote, python -c prints a forced push, allows",
   r'python3 -c "print(\"' + VCS + r' push -f\")"', "allow", cwd=PUSHFEAT)
sh("push: nested quote, echo quotes a forced push in a sentence, allows",
   r'echo "run \"' + VCS + r' push --force\" later"', "allow", cwd=PUSHFEAT)
sh("push: nested quote, python -c prints a sentence naming a forced push, allows",
   r'python3 -c "print(\"use ' + VCS + r' push --force\")"', "allow", cwd=PUSHFEAT)
sh("push: nested quote control, bash -c runs a forced push to main, still asks",
   'bash -c "' + VCS + ' push -f origin main"', "ask", "force-push", cwd=PUSHFEAT)
# RUN, NOT PRINTED. An escaped-quote pair that a call runs is a command, whatever the call is named: a
# module alias, a from-import, a shlex.split argument, a variable. Each denies on a forced push.
sh("push: nested quote, subprocess.run takes a shlex.split of a forced push, denies",
   r'python3 -c "import subprocess; subprocess.run(shlex.split(\"' + VCS + r' push -f origin x\"))"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: nested quote, an aliased subprocess call runs a forced push, denies",
   r'python3 -c "import subprocess as sp; sp.run(\"' + VCS + r' push -f origin x\", shell=True)"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: nested quote, a from-import check_call runs a forced push, denies",
   r'python3 -c "from subprocess import check_call; check_call(\"' + VCS + r' push -f origin x\", shell=True)"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: nested quote, a variable holding a forced push that os.system runs, denies",
   r'python3 -c "cmd=\"' + VCS + r' push -f origin x\"; import os; os.system(cmd)"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# RUN PINS. Each of these runs its string argument and denies today. The first three calls are named by the
# runner list, so a list cut to os.system alone turns each one red. The bash -c eval pin is held by the
# script reader in guard_core, which no runner cut reaches.
sh("push: nested quote pin, subprocess.run with shell=True runs a forced push, denies",
   r'python3 -c "import subprocess; subprocess.run(\"' + VCS + r' push -f origin x\", shell=True)"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: nested quote pin, Popen with shell=True runs a forced push, denies",
   r'python3 -c "from subprocess import Popen; Popen(\"' + VCS + r' push -f origin x\", shell=True)"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: nested quote pin, os.popen runs a forced push, denies",
   r'python3 -c "import os; os.popen(\"' + VCS + r' push -f origin x\")"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: nested quote pin, bash -c eval runs a forced push, denies",
   r'bash -c "eval \"' + VCS + r' push -f origin x\""', "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# PRINTED ALLOWS, by printer name. printf and console.log print their string, so each allows, even inside
# bash -c or node -e.
sh("push: nested quote, bash -c printf prints a forced push, allows",
   r'bash -c "printf \"%s\" \"' + VCS + r' push -f\""', "allow", cwd=PUSHFEAT)
sh("push: nested quote, node -e console.log prints a forced push, allows",
   r'node -e "console.log(\"' + VCS + r' push -f\")"', "allow", cwd=PUSHFEAT)
# NAME PINS. Each case goes red on a scratch guard with the name it pins removed, except System.out.print*,
# which print\w* also matches. ruby and perl are read only by INTERPRETER_RUNNER, and `system` also matches
# CALL_RUNNER, so their pins use `spawn` and `readpipe`. No pin names deno: SCRIPT_RUNNER's `eval` and
# INTERPRETER_RUNNER's deno alternative both read `deno eval`, so removing one changes no deno case's verdict.
sh("push: nested quote runner pin, ruby -e spawns a forced push, denies",
   r'ruby -e "spawn(\"' + VCS + r' push -f origin x\")"', "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: nested quote runner pin, perl -e readpipe runs a forced push, denies",
   r'perl -e "readpipe(\"' + VCS + r' push -f origin x\")"', "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: nested quote printer pin, ruby -e puts prints a forced push, allows",
   r'ruby -e "puts(\"' + VCS + r' push -f origin x\")"', "allow", cwd=PUSHFEAT)
sh("push: nested quote printer pin, perl -e say prints a forced push, allows",
   r'perl -e "say(\"' + VCS + r' push -f origin x\")"', "allow", cwd=PUSHFEAT)
sh("push: nested quote printer pin, python -c logger.info prints a forced push, allows",
   r'python3 -c "import logging; logger = logging.getLogger(); logger.info(\"' + VCS + r' push -f origin x\")"',
   "allow", cwd=PUSHFEAT)
sh("push: nested quote printer pin, bash -c System.out.println prints a forced push, allows",
   r'bash -c "System.out.println(\"' + VCS + r' push -f origin x\")"', "allow", cwd=PUSHFEAT)
sh("push: nested quote printer pin, bash -c Write-Host prints a forced push, allows",
   r'bash -c "Write-Host (\"' + VCS + r' push -f origin x\")"', "allow", cwd=PUSHFEAT)
sh("push: nested quote printer pin, bash -c Write-Output prints a forced push, allows",
   r'bash -c "Write-Output (\"' + VCS + r' push -f origin x\")"', "allow", cwd=PUSHFEAT)
sh("push: nested quote printer pin, bash -c sudo echo prints a forced push, allows",
   r'bash -c "sudo echo \"' + VCS + r' push -f origin x\""', "allow", cwd=PUSHFEAT)
sh("push: nested quote printer pin, bash -c command printf prints a forced push, allows",
   r'bash -c "command printf \"%s\" \"' + VCS + r' push -f origin x\""', "allow", cwd=PUSHFEAT)
# GAPS. php -r runs its string as a script, and a Deno.Command call names git as an argument. Each one
# denies: php -r is an INTERPRETER_RUNNER runner, and the pairs of an argv call join into one command line.
sh("push: nested quote gap, php -r shell_exec runs a forced push, denies",
   r'php -r "shell_exec(\"' + VCS + r' push -f origin x\")"', "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: nested quote gap, deno eval spawns git through Deno.Command, denies",
   r'deno eval "new Deno.Command(\"' + VCS + r'\", {args: [\"push\", \"-f\", \"origin\", \"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# CONTROLS for the cases below. Text that is only printed, and a shell call that runs no push, allow.
sh("push: echo prints a forced push in double quotes, allows (control)",
   'echo "' + VCS + ' push -f origin x"', "allow", cwd=PUSHFEAT)
sh("push: bash -c runs git status, allows (control)",
   'bash -c "' + VCS + ' status"', "allow", cwd=PUSHFEAT)
# SINGLE-QUOTED OUTER BODY. A single-quoted argument of a runner holds its script the same way a double-quoted
# one does, and its double-quoted pairs are the script's strings. _push_scan reads the escaped-quote spans of
# double quotes only, so these pairs are text and the forced push allows. The double-quoted node -e execSync
# form denies today, and is the control for the three.
sh("push: nested quote control, node -e execSync runs a forced push, denies",
   r'node -e "require(\"child_process\").execSync(\"' + VCS + r' push -f origin x\")"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: single-quoted python -c os.system runs a forced push, denies",
   "python3 -c 'import os; os.system(\"" + VCS + " push -f origin x\")'",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: single-quoted node -e execSync runs a forced push, denies",
   "node -e 'require(\"child_process\").execSync(\"" + VCS + " push -f origin x\")'",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: single-quoted php -r shell_exec runs a forced push, denies",
   "php -r 'shell_exec(\"" + VCS + " push -f origin x\");'",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: single-quoted python -c prints a plain push, allows (control)",
   "python3 -c 'print(\"" + VCS + " push -f\")'", "allow", cwd=PUSHFEAT)
# PRINTER WRAPS A RUN CALL. A printer names the call that runs its string, and the call inside it still runs:
# shell_exec, check_output and spawnSync are not in CALL_RUNNER, so the printed pair is read as text. A printer
# that prints the push text alone runs nothing, so it allows.
sh("push: nested quote printer wraps shell_exec in php echo, runs a forced push, denies",
   r'php -r "echo shell_exec(\"' + VCS + r' push -f origin x\");"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: nested quote printer wraps check_output in python print, runs a forced push, denies",
   r'python3 -c "from subprocess import check_output; print(check_output(\"' + VCS + r' push -f origin x\", shell=True))"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: nested quote printer wraps spawnSync in console.log, runs a forced push, denies",
   r'node -e "const cp=require(\"child_process\"); console.log(cp.spawnSync(\"' + VCS + r' push -f origin x\",{shell:true}))"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: nested quote printer echo prints a forced push, php -r, allows (control)",
   r'php -r "echo \"' + VCS + r' push -f origin x\";"', "allow", cwd=PUSHFEAT)
# A SHELL RUNS WHAT A PIPE FEEDS IT. The printed text of `echo` or `printf` piped into `sh` is a script, so
# the forced push in it runs. The same text piped into cat is printed and allows.
sh("push: bash -c echo a forced push piped into sh, denies",
   r'bash -c "echo \"' + VCS + r' push -f origin x\" | sh"', "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: sh -c printf a forced push piped into sh, denies",
   "sh -c \"printf '%s\\n' \\\"" + VCS + " push -f origin x\\\" | sh\"",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: bash -c echo a forced push piped into cat, allows (control)",
   r'bash -c "echo \"' + VCS + r' push -f origin x\" | cat"', "allow", cwd=PUSHFEAT)
# HEREDOC INTO AN INTERPRETER. An interpreter that reads its program from stdin (`python3 -`, `deno run -`)
# runs the heredoc body as code, so a forced push in the body runs. A heredoc into cat is text (see the
# cat heredoc control above).
sh("push: heredoc into python3 -, os.system runs a forced push, denies",
   "python3 - <<'EOF'\nimport os; os.system(\"" + VCS + " push -f origin x\")\nEOF",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: heredoc into deno run -A -, an argv call runs a forced push, denies",
   "deno run -A - <<'EOF'\nnew Deno.Command(\"" + VCS + "\", {args: [\"push\", \"-f\", \"origin\", \"x\"]}).outputSync()\nEOF",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# PRINTER WRAPS A FORMATTER. json.dumps, str.format and repr build a string and print it, so the forced push in
# that string is data and runs nothing. Each allows, in double quotes and in single quotes.
sh("push: nested quote, json.dumps prints a forced push in a dict, allows",
   r'python3 -c "print(json.dumps({\"cmd\": \"' + VCS + r' push -f\"}))"', "allow", cwd=PUSHFEAT)
sh("push: nested quote, str.format prints a forced push, allows",
   r'python3 -c "print(\"{}\".format(\"' + VCS + r' push -f origin x\"))"', "allow", cwd=PUSHFEAT)
sh("push: nested quote, repr prints a forced push, allows",
   r'python3 -c "print(repr(\"' + VCS + r' push -f origin x\"))"', "allow", cwd=PUSHFEAT)
sh("push: single-quoted python -c, json.dumps prints a forced push in a dict, allows",
   "python3 -c 'print(json.dumps({\"cmd\": \"" + VCS + " push -f\"}))'", "allow", cwd=PUSHFEAT)
sh("push: single-quoted python -c, str.format prints a forced push, allows",
   "python3 -c 'print(\"{}\".format(\"" + VCS + " push -f origin x\"))'", "allow", cwd=PUSHFEAT)
sh("push: single-quoted python -c, repr prints a forced push, allows",
   "python3 -c 'print(repr(\"" + VCS + " push -f origin x\"))'", "allow", cwd=PUSHFEAT)
# WRITTEN, NOT RUN. sys.stdout.write puts its string on the output as print does, so a forced push in it allows.
sh("push: single-quoted python -c, sys.stdout.write prints a forced push, allows",
   "python3 -c 'import sys; sys.stdout.write(\"" + VCS + " push -f origin x\")'", "allow", cwd=PUSHFEAT)
sh("push: nested quote, sys.stdout.write prints a forced push, allows",
   r'python3 -c "import sys; sys.stdout.write(\"' + VCS + r' push -f origin x\")"', "allow", cwd=PUSHFEAT)
# PRINTER AROUND A NON-FORMATTER CALL. A printer runs its string only when the call that holds the string is a
# run call. guard.check, len, json_encode and path.basename are not run calls, so a forced push in their string
# is data and allows.
sh("push: single-quoted python -c, print of guard.check of a forced push, allows",
   "python3 -c 'import guard; print(guard.check(\"" + VCS + " push -f origin x\"))'", "allow", cwd=PUSHFEAT)
sh("push: nested quote, print of guard.check of a forced push, allows",
   r'python3 -c "import guard; print(guard.check(\"' + VCS + r' push -f origin x\"))"', "allow", cwd=PUSHFEAT)
sh("push: single-quoted python -c, print of len of a forced push, allows",
   "python3 -c 'print(len(\"" + VCS + " push -f origin x\"))'", "allow", cwd=PUSHFEAT)
sh("push: single-quoted php -r, echo of json_encode of a forced push, allows",
   "php -r 'echo json_encode(\"" + VCS + " push -f origin x\");'", "allow", cwd=PUSHFEAT)
sh("push: single-quoted node -e, console.log of path.basename of a forced push, allows",
   "node -e 'console.log(path.basename(\"" + VCS + " push -f origin x\"))'", "allow", cwd=PUSHFEAT)
# PINS, GREEN NOW. A run call under a wrapper still runs: os.system under str(), and check_output under print.
sh("push: single-quoted python -c, os.system of str of a forced push, denies",
   "python3 -c 'import os; os.system(str(\"" + VCS + " push -f origin x\"))'",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: single-quoted python -c, print of check_output of a forced push, denies",
   "python3 -c 'import subprocess; print(subprocess.check_output(\"" + VCS + " push -f origin x\", shell=True))'",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# ARGV LIST RUN. subprocess.run and check_call run the words of their list, so a forced push written as a list
# runs, and denies the way a plain force-push does.
sh("push: single-quoted python -c, subprocess.run takes a list of a forced push, denies",
   "python3 -c 'import subprocess; subprocess.run([\"" + VCS + "\",\"push\",\"-f\",\"origin\",\"x\"])'",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: single-quoted python -c, subprocess.check_call takes a list of a forced push, denies",
   "python3 -c 'import subprocess; subprocess.check_call([\"" + VCS + "\",\"push\",\"-f\",\"origin\",\"x\"])'",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: nested quote, subprocess.run takes a list of a forced push, denies",
   r'python3 -c "import subprocess; subprocess.run([\"' + VCS + r'\",\"push\",\"-f\",\"origin\",\"x\"])"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# ARGV LIST, A COMMAND-LINE ELEMENT. ssh, su -c and watch run a list element as a command line, so a forced push
# in that element runs and denies the way a plain force-push does.
sh("push: python -c, ssh runs a list element that is a forced push, denies",
   r'python3 -c "import subprocess; subprocess.run([\"ssh\",\"host\",\"' + VCS + r' push -f origin x\"])"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: python -c, ssh runs a list element that is a cd and a forced push, denies",
   r'python3 -c "import subprocess; subprocess.run([\"ssh\",\"host\",\"cd /srv && ' + VCS + r' push -f origin x\"])"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: python -c, su -c runs a list element that is a forced push, denies",
   r'python3 -c "import subprocess; subprocess.run([\"su\",\"-c\",\"' + VCS + r' push -f origin x\",\"user\"])"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: python -c, watch runs a list element that is a forced push, denies",
   r'python3 -c "import subprocess; subprocess.run([\"watch\",\"' + VCS + r' push -f origin x\"])"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# PINS, GREEN NOW. A list of git status, echo of a forced push, and a git commit with one in its message: all allow.
sh("push: python -c, subprocess.run takes git status as a list, allows (control)",
   "python3 -c 'import subprocess; subprocess.run([\"" + VCS + "\",\"status\"])'", "allow", cwd=PUSHFEAT)
sh("push: python -c, subprocess.run takes echo of a forced push as a list, allows (control)",
   "python3 -c 'import subprocess; subprocess.run([\"echo\",\"" + VCS + " push -f origin x\"])'", "allow", cwd=PUSHFEAT)
sh("push: python -c, subprocess.run takes git commit with a forced push in its message, allows (control)",
   "python3 -c 'import subprocess; subprocess.run([\"" + VCS + "\",\"commit\",\"-m\",\"fix; " + VCS + " push -f origin x\"])'",
   "allow", cwd=PUSHFEAT)
# ARGV LIST, A WRAPPER THAT HANDS ON A COMMAND LINE. docker exec, kubectl exec and flock hand the element after
# their sh -c on as a command line, as ssh and su -c do. A forced push there runs, and denies the way a plain one does.
sh("push: python -c, docker exec hands sh -c a forced push in a list, denies",
   r'python3 -c "import subprocess; subprocess.run([\"docker\",\"exec\",\"c\",\"sh\",\"-c\",\"' + VCS + r' push -f origin x\"])"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: python -c, kubectl exec hands sh -c a forced push in a list, denies",
   r'python3 -c "import subprocess; subprocess.run([\"kubectl\",\"exec\",\"p\",\"--\",\"sh\",\"-c\",\"' + VCS + r' push -f origin x\"])"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: python -c, flock hands sh -c a forced push in a list, denies",
   r'python3 -c "import subprocess; subprocess.run([\"flock\",\"/tmp/l\",\"sh\",\"-c\",\"' + VCS + r' push -f origin x\"])"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# A LONE APOSTROPHE IN PRINTED TEXT. The `'\''` escape closes the shell quote, writes one apostrophe and reopens it,
# so the os.system call after it is shell-level code that runs. The apostrophe is text, not the end of the string.
sh("push: single-quoted python -c, an apostrophe escape ahead of os.system of a forced push, denies",
   "python3 -c 'print(\"don'\\''t\"); import os; os.system(\"" + VCS + " push -f origin x\")'",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# SINGLE QUOTES INSIDE A DOUBLE-QUOTED -c. The single quotes are python text, and os.system runs its string.
sh("push: double-quoted python -c, os.system of a single-quoted forced push, denies",
   "python3 -c \"import os; os.system('" + VCS + " push -f origin x')\"",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# A CALL SPLIT OVER LINES. os.system( and its string sit on different lines, in a heredoc body.
sh("push: heredoc into python3 -, os.system split over lines runs a forced push, denies",
   "python3 - <<'EOF'\nimport os\nos.system(\n\"" + VCS + " push -f origin x\"\n)\nEOF",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# FALSE ALARMS, ALLOW. A forced push that is only text: in a git commit message, an echo, and a gh comment body.
sh("push: git commit -m names a list push in its message, allows",
   VCS + r' commit -m "Fix: subprocess.run([\"' + VCS + r'\",\"push\",\"-f\"]) is read"', "allow", cwd=PUSHFEAT)
sh("push: echo of check_output of a forced push in quotes, allows",
   r'echo "see check_output(\"' + VCS + r' push -f origin x\")"', "allow", cwd=PUSHFEAT)
sh("push: gh pr comment body names shell_exec of a forced push, allows",
   r'gh pr comment 1 --body "shell_exec(\"' + VCS + r' push -f origin x\") now refuses"', "allow", cwd=PUSHFEAT)
# A PRINT SPLIT OVER LINES. print( and its string sit on different lines, and print writes the string as text.
sh("push: single-quoted python -c, print split over lines of a forced push, allows",
   "python3 -c 'print(\n\"" + VCS + " push -f origin x\"\n)'", "allow", cwd=PUSHFEAT)
# PINS, GREEN NOW. A -c script that splits os.system( from its string already denies. A watch runs a quoted
# command line, so a forced push in it denies. A watch of git status allows.
sh("push: single-quoted python -c, os.system split over lines runs a forced push, denies",
   "python3 -c 'import os; os.system(\n\"" + VCS + " push -f origin x\"\n)'",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: watch of a quoted forced push, denies",
   "watch \"" + VCS + " push -f origin x\"", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: watch -n 2 of git status, allows",
   "watch -n 2 " + VCS + " status", "allow", cwd=PUSHFEAT)
# CONTROL. Printed text with no escaped quote allows.
sh("push: python -c prints hello, allows (control)", r'python3 -c "print(\"hello\")"', "allow", cwd=PUSHFEAT)
# A PYTHON REACHED BY A PATH OR WITH A VALUE FLAG. `.venv/bin/python`, `/usr/bin/python3` and `python3 -W ignore`
# run their -c script as a bare python3 does, so a single-quoted forced push in its check_output, or in its
# argv list, runs and denies.
sh("push: .venv/bin/python -c, check_output shell=True of a single-quoted forced push, denies",
   ".venv/bin/python -c \"import subprocess; subprocess.check_output('" + VCS + " push -f origin x', shell=True)\"",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: /usr/bin/python3 -c, check_output shell=True of a single-quoted forced push, denies",
   "/usr/bin/python3 -c \"import subprocess; subprocess.check_output('" + VCS + " push -f origin x', shell=True)\"",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: python3 -W ignore -c, check_output shell=True of a single-quoted forced push, denies",
   "python3 -W ignore -c \"import subprocess; subprocess.check_output('" + VCS + " push -f origin x', shell=True)\"",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# PIN, GREEN NOW. The same call with the forced push in escaped double quotes denies, whatever the interpreter's path.
sh("push: .venv/bin/python -c, check_output shell=True of an escaped forced push, denies (control)",
   r'.venv/bin/python -c "import subprocess; subprocess.check_output(\"' + VCS + r' push -f origin x\", shell=True)"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: /usr/bin/python3 -c, subprocess.run takes a forced push as a list, denies",
   r'/usr/bin/python3 -c "import subprocess; subprocess.run([\"' + VCS + r'\",\"push\",\"-f\",\"origin\",\"x\"])"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: .venv/bin/python -c, os.system of a single-quoted forced push, denies",
   ".venv/bin/python -c \"import os; os.system('" + VCS + " push -f origin x')\"",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# A COMMENT OPENER. `# print(` is a python comment, so it opens no call, and the os.system on the next line is code
# that runs. The comment's text is not a call that holds the lines after it.
sh("push: heredoc into python3 -, a comment with print( ahead of os.system of a forced push, denies",
   "python3 - <<'EOF'\n# print(\nos.system('" + VCS + " push -f origin x')\nEOF",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# PIN, GREEN NOW. In a -c script the same run denies too, since the call it sits in is the innermost open one.
sh("push: python3 -c, a comment with print( ahead of os.system of a forced push, denies (control)",
   "python3 -c \"# print(\nos.system('" + VCS + " push -f origin x')\"",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# A SINGLE-QUOTED STRING NO RUN CALL TAKES. An assignment, a write to a file and an assert hold text, not a command,
# so each allows, even with a forced push in its quotes.
sh("push: python3 -c, assigns a single-quoted forced push then prints it, allows",
   "python3 -c \"x = '" + VCS + " push -f origin x'; print(x)\"", "allow", cwd=PUSHFEAT)
sh("push: python3 -c, open().write of a single-quoted forced push, allows",
   "python3 -c \"open('notes.txt','w').write('" + VCS + " push -f origin x')\"", "allow", cwd=PUSHFEAT)
sh("push: python3 -c, assert of a single-quoted push -f text, allows",
   "python3 -c \"s = 'ok'; assert '" + VCS + " push -f' not in s\"", "allow", cwd=PUSHFEAT)
sh("push: python3 -c, assigns a single-quoted push origin main then prints it, allows",
   "python3 -c \"msg = '" + VCS + " push origin main'; print(msg)\"", "allow", cwd=PUSHFEAT)
# A HEREDOC LINE THAT IS ONE STRING. A list item alone on its line, and a print( split over lines, hold text when no
# run call takes the string. Each allows.
sh("push: heredoc into python3 -, a last list item alone on its line holds a forced push, allows",
   "python3 - <<'EOF'\nitems = [\n    \"" + VCS + " push -f origin x\"\n]\nEOF", "allow", cwd=PUSHFEAT)
# PIN, GREEN NOW. The same list item with a comma after it allows.
sh("push: heredoc into python3 -, a list item with a comma alone on its line holds a forced push, allows (control)",
   "python3 - <<'EOF'\nitems = [\n    \"" + VCS + " push -f origin x\",\n]\nEOF", "allow", cwd=PUSHFEAT)
sh("push: heredoc into python3 -, print split over lines of a forced push, allows",
   "python3 - <<'EOF'\nprint(\n\"" + VCS + " push -f origin x\"\n)\nEOF", "allow", cwd=PUSHFEAT)
# PIN, GREEN NOW. A comment opener inside a string is text, so the os.system after it still runs and denies. A
# reader that stops at `#` would miss this run.
sh("push: python3 -c, a # inside a single-quoted string ahead of os.system of a forced push, denies",
   "python3 -c \"x = '# print('\nimport os; os.system('" + VCS + " push -f origin x')\"",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# A COMMENT OPENER INSIDE A SINGLE-QUOTED STRING, ON A -c LINE. The `#` is text, so the os.system after it on the
# same line still runs. A reader that stops at `#` misses that run.
sh("push: python3 -c, a # in a single-quoted string on the same line as os.system of a forced push, denies",
   "python3 -c \"msg = 'fix #12'; import os; os.system(\\\"" + VCS + " push -f origin x\\\")\"",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# CONTROL. The same line with no `#` in its string denies.
sh("push: python3 -c, a single-quoted string with no # ahead of os.system of a forced push, denies (control)",
   "python3 -c \"msg = 'fix 12'; import os; os.system(\\\"" + VCS + " push -f origin x\\\")\"",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# PIN, GREEN NOW. A comment after an assignment hides only its own line, so the os.system on the next line runs.
sh("push: python3 -c, a # comment after a single-quoted assignment, then os.system of a forced push, denies",
   "python3 -c \"msg = 'fix'  # note\nimport os; os.system(\\\"" + VCS + " push -f origin x\\\")\"",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# A TEMPLATE LITERAL IN node -e. The ` #` span is JS text, so the execSync after it on the same line still runs.
sh("push: node -e, a template literal with a # in its text, then execSync of a forced push, denies",
   "node -e \"const m = \\`fix #12\\`; require(\\\"child_process\\\").execSync(\\\"" + VCS + " push -f origin x\\\")\"",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# CONTROL. The same template literal with no `#` denies.
sh("push: node -e, a template literal with no # then execSync of a forced push, denies (control)",
   "node -e \"const m = \\`fix 12\\`; require(\\\"child_process\\\").execSync(\\\"" + VCS + " push -f origin x\\\")\"",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# A PYTHON NAMED BY ANOTHER NAME. pypy3 is a python3 build, and $PYTHON names the interpreter by a variable. Each
# runs its -c script as python3 does, so a forced push in its run list or its check_output denies.
sh("push: pypy3 -c, subprocess.run takes a forced push as a list, denies",
   r'pypy3 -c "import subprocess; subprocess.run([\"' + VCS + r'\",\"push\",\"-f\",\"origin\",\"x\"])"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: $PYTHON -c, check_output shell=True of an escaped forced push, denies",
   r'$PYTHON -c "from subprocess import check_output; check_output(\"' + VCS + r' push -f origin x\", shell=True)"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# A QUOTED INTERPRETER PATH. A path in double quotes is read as no interpreter, so the -c script after it is never
# checked. The unquoted path denies, as the control below shows.
sh("push: quoted interpreter path with a space, check_output shell=True of an escaped forced push, denies",
   r'"/opt/py 3/bin/python3" -c "from subprocess import check_output; check_output(\"' + VCS + r' push -f origin x\", shell=True)"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: quoted interpreter path with no space, check_output shell=True of an escaped forced push, denies",
   r'"/opt/py3/bin/python3" -c "from subprocess import check_output; check_output(\"' + VCS + r' push -f origin x\", shell=True)"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: /opt/py3/bin/python3 unquoted, check_output shell=True of an escaped forced push, denies (control)",
   r'/opt/py3/bin/python3 -c "from subprocess import check_output; check_output(\"' + VCS + r' push -f origin x\", shell=True)"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# PIN, GREEN NOW. A from-import check_output under a .venv interpreter path denies, whatever the import form.
sh("push: .venv/bin/python -c, from-import check_output shell=True of an escaped forced push, denies (pin)",
   r'.venv/bin/python -c "from subprocess import check_output; check_output(\"' + VCS + r' push -f origin x\", shell=True)"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# A HEREDOC LIST SPLIT OVER LINES. The items of one subprocess.run list, each on its own line, hold the same text
# as the one-line list. A commit message and an echo argument allow, and the one-line forms are the controls.
sh("push: heredoc into python3 -, subprocess.run git commit list split over lines names a forced push in its message, allows",
   "python3 - <<'EOF'\nimport subprocess\nsubprocess.run([\"" + VCS + "\",\"commit\",\"-m\",\n    \"Doc: " + VCS
   + " push -f needs a lease\"\n])\nEOF", "allow", cwd=PUSHFEAT)
sh("push: heredoc into python3 -, subprocess.run echo list split over lines names a forced push, allows",
   "python3 - <<'EOF'\nimport subprocess\nsubprocess.run([\"echo\",\n    \"" + VCS + " push -f origin x\"\n])\nEOF",
   "allow", cwd=PUSHFEAT)
sh("push: heredoc into python3 -, subprocess.run git commit list on one line names a forced push in its message, allows (control)",
   "python3 - <<'EOF'\nimport subprocess\nsubprocess.run([\"" + VCS + "\",\"commit\",\"-m\",\"Doc: " + VCS
   + " push -f needs a lease\"])\nEOF", "allow", cwd=PUSHFEAT)
sh("push: heredoc into python3 -, subprocess.run echo list on one line names a forced push, allows (control)",
   "python3 - <<'EOF'\nimport subprocess\nsubprocess.run([\"echo\",\"" + VCS + " push -f origin x\"])\nEOF",
   "allow", cwd=PUSHFEAT)
# A GREP PATTERN. Text in a grep pattern runs nothing, even one that spells an os.system call of a forced push. The
# same forced push with no call around it allows too (control).
sh("push: grep -e of an os.system call naming a forced push in quotes, allows",
   "grep -rn src/python -e 'os.system(\"" + VCS + " push -f origin x\")'", "allow", cwd=PUSHFEAT)
sh("push: grep -e of a forced push in quotes with no os.system call, allows (control)",
   "grep -rn src/python -e '" + VCS + " push -f origin x'", "allow", cwd=PUSHFEAT)
# PIN, GREEN NOW. A class private field, `#x`, is JS text rather than a comment, so the execSync after it on the
# same line still runs. A reader that takes `#` as a comment for node misses that run.
sh("push: node -e, a class private field #x ahead of execSync of a forced push, denies",
   "node -e \"class A { #x = 1 }; require(\\\"child_process\\\").execSync(\\\"" + VCS + " push -f origin x\\\")\"",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# CONTROL. The same class with no `#` field denies.
sh("push: node -e, a class field with no # ahead of execSync of a forced push, denies (control)",
   "node -e \"class A { x = 1 }; require(\\\"child_process\\\").execSync(\\\"" + VCS + " push -f origin x\\\")\"",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# PIN, GREEN NOW. A launcher runs python, and python runs its -c script, so an escaped forced push in
# check_output denies under uv run or poetry run as it does under a bare python3.
sh("push: uv run python -c, check_output shell=True of an escaped forced push, denies",
   r'uv run python -c "from subprocess import check_output; check_output(\"' + VCS + r' push -f origin x\", shell=True)"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: poetry run python -c, check_output shell=True of an escaped forced push, denies",
   r'poetry run python -c "from subprocess import check_output; check_output(\"' + VCS + r' push -f origin x\", shell=True)"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# PIN, GREEN NOW. In rg, src/python names a path to search, and the os.system call in the -e pattern is text, so
# nothing runs and the forced push allows. The rg control below has no os.system call.
sh("push: rg -e of an os.system call naming a forced push in quotes, allows",
   "rg -n src/python -e 'os.system(\"" + VCS + " push -f origin x\")'", "allow", cwd=PUSHFEAT)
sh("push: rg -e of a forced push in quotes with no os.system call, allows (control)",
   "rg -n src/python -e '" + VCS + " push -f origin x'", "allow", cwd=PUSHFEAT)
# ARGV CALLS. A Deno.Command call names its program and its arguments as separate strings, and the pairs
# of one call are joined into one command line. The join keeps each argument's bounds: a quoted "my repo"
# is one argument, so -C takes that whole path and push is the subcommand.
sh("push: argv call, -C takes a quoted path with a space, then a forced push, denies",
   r'deno eval "new Deno.Command(\"' + VCS + r'\", {args: [\"-C\", \"my repo\", \"push\", \"-f\", '
   r'\"origin\", \"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: argv call, -c takes a quoted value with a space, then a forced push, denies",
   r'deno eval "new Deno.Command(\"' + VCS + r'\", {args: [\"-c\", \"user.name=A B\", \"push\", \"-f\", '
   r'\"origin\", \"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# The Deno permission flags come after `eval` here, before the script. No runner pattern reads a script
# after them.
sh("push: deno eval --allow-run after eval, argv forced push, denies",
   r'deno eval --allow-run "new Deno.Command(\"' + VCS + r'\", {args: [\"push\", \"-f\", \"origin\", '
   r'\"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: deno eval -A after eval, argv forced push, denies",
   r'deno eval -A "new Deno.Command(\"' + VCS + r'\", {args: [\"push\", \"-f\", \"origin\", '
   r'\"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: deno eval --allow-all after eval, argv forced push, denies",
   r'deno eval --allow-all "new Deno.Command(\"' + VCS + r'\", {args: [\"push\", \"-f\", \"origin\", '
   r'\"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# The program is rg, so git and push are its search arguments, not a git call.
sh("push: argv call runs rg with git and push as arguments, allows",
   r'deno eval "new Deno.Command(\"rg\", {args: [\"' + VCS + r'\", \"push\", \".\"]}).outputSync()"',
   "allow", cwd=PUSHFEAT)
# Two calls: a git status, then an echo that prints push -f. Each call is its own command line.
sh("push: argv calls run git status then echo push -f, allows",
   r'deno eval "new Deno.Command(\"' + VCS + r'\", {args: [\"status\"]}).outputSync(); '
   r'new Deno.Command(\"echo\", {args: [\"push\", \"-f\"]}).outputSync()"',
   "allow", cwd=PUSHFEAT)
# Scanner shapes on the argv path. An argument is string text, so a comment opener, a lone quote or a
# template literal inside one does not hide the forced push that follows it. Each one denies.
sh("push: argv call, // in a push argument with a space, then -f, denies",
   r'deno eval "new Deno.Command(\"' + VCS + r'\", {args: [\"push\", \"// a\", \"-f\", \"origin\", '
   r'\"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: argv call, /* in a push argument with a space, then -f, denies",
   r'deno eval "new Deno.Command(\"' + VCS + r'\", {args: [\"push\", \"/* a\", \"-f\", \"origin\", '
   r'\"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: argv call, # in a push argument with a space, then -f, denies",
   r'deno eval "new Deno.Command(\"' + VCS + r'\", {args: [\"push\", \"# not\", \"-f\", \"origin\", '
   r'\"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: argv call, a lone quote in a push argument with a space, then -f, denies",
   r'deno eval "new Deno.Command(\"' + VCS + r'\", {args: [\"push\", \"it' + "'" + r's a\", \"-f\", '
   r'\"origin\", \"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: a multi-line template literal before an argv forced push, denies",
   'deno eval "const s = `line one\nline two`; new Deno.Command(\\"' + VCS + r'\", '
   r'{args: [\"push\", \"-f\", \"origin\", \"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# DENO SCRIPT, PLAIN AND ARGV. A deno eval script that spawns a forced push denies, and the argv call
# that runs the same push through a shell denies with the same reason. `bash -c` and `sh -c` take the next
# argument as their script, so each argv form below runs the forced push.
sh("push: deno eval spawns a forced push by its plain script, denies",
   r'deno eval "spawn(\"' + VCS + r' push -f origin x\")"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: deno eval -A runs bash -c with a forced push in an argv call, denies",
   r'deno eval -A "new Deno.Command(\"bash\", {args: [\"-c\", \"' + VCS + r' push -f origin x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: deno eval -A runs sh -c with a forced push in an argv call, denies",
   r'deno eval -A "new Deno.Command(\"sh\", {args: [\"-c\", \"' + VCS + r' push -f origin x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: deno eval -A runs bash -c with a forced push and a cwd after the args, denies",
   r'deno eval -A "new Deno.Command(\"bash\", {args: [\"-c\", \"' + VCS + r' push -f origin x\"], '
   r'cwd: \"/tmp\"}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: deno eval with no -A runs bash -c with a forced push, denies",
   r'deno eval "new Deno.Command(\"bash\", {args: [\"-c\", \"' + VCS + r' push -f origin x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# DENO FLAG VALUES. A deno eval flag that takes a value, such as `--ext ts`, `--config x.json`,
# `--seed 1` or `--cert a.pem`, puts a bare word between the flag and the script. Each form runs the
# forced push, so each denies.
sh("push: deno eval --ext ts before an argv forced push, denies",
   r'deno eval --ext ts "new Deno.Command(\"' + VCS + r'\", '
   r'{args: [\"push\", \"-f\", \"origin\", \"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: deno eval --config x.json before an argv forced push, denies",
   r'deno eval --config x.json "new Deno.Command(\"' + VCS + r'\", '
   r'{args: [\"push\", \"-f\", \"origin\", \"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: deno eval --seed 1 before an argv forced push, denies",
   r'deno eval --seed 1 "new Deno.Command(\"' + VCS + r'\", '
   r'{args: [\"push\", \"-f\", \"origin\", \"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: deno eval --cert a.pem before an argv forced push, denies",
   r'deno eval --cert a.pem "new Deno.Command(\"' + VCS + r'\", '
   r'{args: [\"push\", \"-f\", \"origin\", \"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# EMPTY AND APOSTROPHE ARGUMENTS. An empty argument is a word of its own, and an argument with an
# apostrophe is string text, so neither one hides the forced push that follows it. Each denies.
sh("push: argv call, empty arguments around a forced push, denies",
   r'deno eval "new Deno.Command(\"' + VCS + r'\", '
   r'{args: [\"push\", \"\", \"-f\", \"\", \"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("push: argv call, apostrophes in two arguments around a forced push, denies",
   r'deno eval "new Deno.Command(\"' + VCS + r'\", {args: [\"push\", \"it' + "'" + r's\", \"-f\", '
   r'\"can' + "'" + r't\", \"x\"]}).outputSync()"',
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
# A bash -c that runs git status is no push, so it allows.
sh("push: argv call runs bash -c git status, allows",
   r'deno eval "new Deno.Command(\"bash\", {args: [\"-c\", \"' + VCS + r' status\"]}).outputSync()"',
   "allow", cwd=PUSHFEAT)
# The push text reader's scanner shapes. A comment opener or a multi-line string inside quotes is text, so
# each is an allow control, green today. A lone quote in text opens no string that hides a push: nothing
# after an unterminated quote runs, so the push-looking text after `it's #` is not a live push.
sh("push text: a # inside a quoted push argument allows", VCS + ' push origin HEAD:x "# not --force"',
   "allow", cwd=PUSHFEAT)
sh("push text: a // inside a quoted push argument allows",
   VCS + ' push origin HEAD:x "https://example.com --force"', "allow", cwd=PUSHFEAT)
sh("push text: a /* inside a quoted push argument allows", VCS + ' push origin HEAD:x "/* --force"',
   "allow", cwd=PUSHFEAT)
sh("push text: a multi-line commit message naming a force push allows",
   VCS + ' commit -m "fix\n' + VCS + ' push --force"', "allow", cwd=PUSHFEAT)
sh("push text: a multi-line echo with a # line naming a force push allows",
   'echo "a\n# ' + VCS + ' push --force\nb"', "allow", cwd=PUSHFEAT)
sh("false alarm: a lone quote in text before a # comment naming a force push allows",
   "echo it's # " + VCS + " push --force", "allow", cwd=PUSHFEAT)
sh("push: a force push inside a loop's do-block still counts",
   "while true; do " + VCS + " push --force; done", "deny", "force-push", cwd=PUSHFEAT,
   carries=REMEDY)
# SUBSTITUTION, push. A forced push inside `$( )` or double quotes runs, so it takes the verdict and the
# rule of the plain forced push to the same destination from the same checkout (PUSH_SUBST_PLAIN below).
PUSH_SUBST_FORCE = VCS + " push --force origin main"
PUSH_SUBST_VERDICT = "ask"   # the plain forced push's verdict, pinned by the control case below
sh("substitution: push, the plain forced push to main from a feature branch", PUSH_SUBST_FORCE,
   PUSH_SUBST_VERDICT, "force-push", cwd=PUSHFEAT)
sh("substitution: push, an assignment from a dollar paren with a forced push",
   "x=$(" + PUSH_SUBST_FORCE + ")", PUSH_SUBST_VERDICT, "force-push", cwd=PUSHFEAT)
sh("substitution: push, a dollar paren in double quotes with a forced push",
   'echo "$(' + PUSH_SUBST_FORCE + ')"', PUSH_SUBST_VERDICT, "force-push", cwd=PUSHFEAT)

# ASK-STEP-HIDDEN (debt ask-step-hidden-in-script). A force push one shell step down, in a substitution,
# a quoted script or a commit message's substitution, still runs. Each form denies as the plain form does.
# The controls allow a push that is only quoted, commented or written into a heredoc body: none of them runs.
FORCE = VCS + " push --force"
HIDDEN_PUSH = FORCE + " origin feat"
sh("ask-step-hidden: control, a plain force push denies",
   HIDDEN_PUSH, "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("ask-step-hidden: a force push inside bash -c denies",
   "bash -c '" + HIDDEN_PUSH + "'", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("ask-step-hidden: a force push inside sh -c denies",
   "sh -c '" + HIDDEN_PUSH + "'", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("ask-step-hidden: a force push inside a quoted eval denies",
   "eval '" + HIDDEN_PUSH + "'", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("ask-step-hidden: a force push in a glued command substitution denies",
   "x=$(" + HIDDEN_PUSH + ")", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("ask-step-hidden: a force push in glued backticks denies",
   "x=`" + HIDDEN_PUSH + "`", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("ask-step-hidden: a force push in a commit message's substitution denies",
   VCS + ' commit -m "n $(' + HIDDEN_PUSH + ')"', "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("ask-step-hidden: a force push on the second line of a multi-line bash -c denies",
   "bash -c 'echo ready\n" + HIDDEN_PUSH + "'", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("ask-step-hidden: a comment opener and a /* in quotes do not hide a bash -c force push, denies",
   "echo 'a // b /* c # d'; bash -c '" + HIDDEN_PUSH + "'", "deny", "force-push", cwd=PUSHFEAT,
   carries=REMEDY)
sh("ask-step-hidden: a lone apostrophe in double quotes does not hide a bash -c force push, denies",
   "echo \"it's\"; bash -c '" + HIDDEN_PUSH + "'", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("ask-step-hidden: control, a commit message single-quoting a substitution that names a force push allows",
   VCS + " commit -m 'n $(" + FORCE + ")'", "allow", cwd=PUSHFEAT)
sh("ask-step-hidden: control, a comment naming a bash -c force push allows",
   "# bash -c '" + FORCE + "'", "allow", cwd=PUSHFEAT)
sh("ask-step-hidden: control, a commit whose heredoc body names a bash -c force push allows",
   VCS + " commit -F - <<'EOF'\nbash -c '" + FORCE + "'\nEOF", "allow", cwd=PUSHFEAT)
sh("ask-step-hidden: control, an echo that quotes a bash -c force push allows",
   'echo "use bash -c \'' + FORCE + '\' never"', "allow", cwd=PUSHFEAT)
# ASK-STEP-HIDDEN, inside a wrapper (debt ask-step-hidden-in-script). A `bash -c` or `sh -c` script runs its
# own `$( )` and backticks, so a force push there still runs and denies. A heredoc body in a wrapper is data.
sh("ask-step-hidden: a force push in a bash -c substitution denies",
   "bash -c 'x=$(" + HIDDEN_PUSH + ")'", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("ask-step-hidden: a force push in bash -c glued backticks denies",
   "bash -c 'x=`" + HIDDEN_PUSH + "`'", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("ask-step-hidden: a force push in a sh -c double-quoted substitution denies",
   "sh -c 'echo \"$(" + HIDDEN_PUSH + ")\"'", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("ask-step-hidden: control, a heredoc body naming a force push inside bash -c allows",
   "bash -c 'cat <<EOF\n" + HIDDEN_PUSH + "\nEOF'", "allow", cwd=PUSHFEAT)

# ASK, owner rulings 206 a and 432 a. An implied destination (a bare push, HEAD, @, or a colon-less refspec
# naming the current branch) that lands off the branch's upstream asks while the destination is not yet on
# origin, that is, no refs/remotes/origin/<name> (ruling 432 a). A push with -u that names the local branch is
# silent (the silent cases below). PUSHSTRAY is `mylocal`, whose upstream is origin/lane/x, and origin/mylocal
# is absent, so its rows ask.
push_case("stray branch, HEAD asks", "origin HEAD", "ask", cwd=PUSHSTRAY, rule=PUSH_STRAY_RULE)
push_case("stray branch, @ asks", "origin @", "ask", cwd=PUSHSTRAY, rule=PUSH_STRAY_RULE)
push_case("stray branch, the current branch named by its colon-less refspec asks", "origin mylocal", "ask",
          cwd=PUSHSTRAY, rule=PUSH_STRAY_RULE)
# The same pushes without -u still ask: -u is what makes a new upstream on purpose.
push_case("stacked lane, HEAD without -u asks", "origin HEAD", "ask", cwd=PUSHSTACK, rule=PUSH_STRAY_RULE)
push_case("stacked lane, the local name without -u asks", "origin lane/fix", "ask", cwd=PUSHSTACK,
          rule=PUSH_STRAY_RULE)
push_case("stray branch, HEAD with an output tail is one clean ask", "origin HEAD 2>&1 | tail -1", "ask",
          cwd=PUSHSTRAY, rule=PUSH_STRAY_RULE, lacks=(CHAIN_ASK,))
# Two refspecs: the explicit one is fine, the second is implied, so the call still asks.
push_case("stray branch, a second refspec that names the current branch asks",
          "origin HEAD:push-guard-asks mylocal", "ask", cwd=PUSHSTRAY, rule=PUSH_STRAY_RULE)
sh("push: stray branch, a bare push under push.default current asks",
   VCS + " -c push.default=current push", "ask", PUSH_STRAY_RULE, cwd=PUSHSTRAY)
# The remedy names the explicit form with a placeholder only (ruling 432 a). The real branch names of PUSHSTRAY
# never appear in it.
sh("push: stray branch, the ask names the explicit form HEAD:<branch>", VCS + " push origin HEAD", "ask",
   PUSH_STRAY_RULE, cwd=PUSHSTRAY, carries=("HEAD:<branch>",), lacks=("HEAD:mylocal", "HEAD:lane/x"))

# DENY, rule push-agent-branch. A non-forced push whose destination is an agent-worktree name is refused, with or
# without -u. push-stray-branch stays silent on a branch with no upstream, so this rule carries that case. The
# names are agent-<hex>, claude/agent-<hex> and worktree-agent-<hex>, with 8 or more hex characters after the
# prefix. PUSHAGENT sits on its claude/agent- branch, with no upstream. The case names keep their "asks"
# wording: hooks/mutate_guard.py matches on them.


def agent_refused(name, command, cwd=PUSHFEAT, **kw):
    """One push the agent-branch rule refuses: a deny under its rule id, whose reason prints the lane's remedy
    and names no agent branch."""
    sh(name, command, "deny", PUSH_AGENT_RULE, cwd=cwd, carries=(PUSH_AGENT_REMEDY,), lacks=PUSH_AGENT_LACKS, **kw)


def push_sh(name, command, expected, rule=None, **kw):
    """sh() for a push case. A case that puts a stand-in git first on PATH goes through stand_in_sh, which skips it on
    Windows: the guard starts git by name, and Windows finds git.exe there, never the extensionless stand-in."""
    (stand_in_sh if "env_path" in kw else sh)(name, command, expected, rule, **kw)


def all_refused(name, tail, cwd=PUSHFEAT, **kw):
    """One plain push the all-branches rule refuses: a deny under its rule id, whose reason prints the lane's remedy,
    names its own cause ("sends every branch", which the agent rule's reason never says) and names no main or master
    target."""
    push_sh("push: " + name, VCS + " push " + tail, "deny", PUSH_ALL_RULE, cwd=cwd,
            carries=(PUSH_AGENT_REMEDY, "Rule (Git): ", "sends every branch"), lacks=PUSH_ALL_LACKS, **kw)


def all_allowed(name, tail, cwd=PUSHFEAT, **kw):
    """One plain push the all-branches rule allows: it writes no main or master on the remote, so it prints nothing."""
    sh("push: " + name, VCS + " push " + tail, "allow", cwd=cwd, silent=True, **kw)


def all_agent_refused(name, tail, cwd):
    """One plain push the all-branches rule refuses for a local agent-named branch that --all or --branches would send
    to origin, while main equals its tracking ref. A deny under its rule id, whose reason names an agent, prints the
    lane's remedy, and names neither a main target nor an agent branch as its target. The reason may not say that main
    would update, since in these fixtures it would not."""
    sh("push: " + name, VCS + " push " + tail, "deny", PUSH_ALL_RULE, cwd=cwd,
       carries=(PUSH_ALL_RULE + ": Rule (Git): ", "sends every branch", "named like an agent worktree", "agent",
                PUSH_AGENT_REMEDY),
       lacks=PUSH_ALL_LACKS + PUSH_ALL_AGENT_LACKS + ("may update the default branch",))


def all_update_refused(name, tail, cwd, **kw):
    """One plain push the all-branches rule refuses because it would update main or master, or cannot tell that it
    would not, while a local agent-named branch is also present. The reason opens with the rule id, names the update
    and no agent: the update is judged first."""
    push_sh("push: " + name, VCS + " push " + tail, "deny", PUSH_ALL_RULE, cwd=cwd,
            carries=(PUSH_ALL_RULE + ": Rule (Git): ", "may update the default branch", PUSH_AGENT_REMEDY),
            lacks=("agent",) + PUSH_ALL_LACKS, **kw)


# A failed ref read refuses, since unknown is never safe. PUSHFAILSHIM is a git stand-in that fails every for-each-ref
# and runs the real git for the rest, so PUSHFEAT's tracking-ref read comes back unknown although local main equals it.
PUSHFAILSHIM = os.path.join(ROOT, "pushfailshim")
# PUSHTRACKFAILSHIM fails only the read of the tracking refs (the update test), so the local-branch listing answers.
PUSHTRACKFAILSHIM = os.path.join(ROOT, "pushtrackfailshim")
TRACKING_REF_READ = "%(objectname)"


def _build_push_failshim():
    make_git_stand_in(PUSHFAILSHIM, fail_on="for-each-ref")
    make_git_stand_in(PUSHTRACKFAILSHIM, fail_on=TRACKING_REF_READ)
    if os.name == "nt":
        # Windows cannot start an extensionless stand-in, so the probes below need a POSIX host.
        return
    probe = subprocess.run([os.path.join(PUSHFAILSHIM, VCS), "for-each-ref", "refs/heads/main"],
                           cwd=ROOT, capture_output=True)
    if probe.returncode == 0:
        sys.exit("fixture setup failed in build_fixtures: the for-each-ref stand-in exited 0, so it fails no read")
    probe = subprocess.run([os.path.join(PUSHTRACKFAILSHIM, VCS), "for-each-ref", "--format=%(refname) %(objectname)",
                            "refs/heads/main"], cwd=ROOT, capture_output=True)
    if probe.returncode == 0:
        sys.exit("fixture setup failed in build_fixtures: the tracking-ref stand-in exited 0, so it fails no read")


lazy_fixture([PUSHFAILSHIM, PUSHTRACKFAILSHIM], _build_push_failshim)


agent_refused("push: agent branch, HEAD asks", VCS + " push origin HEAD", cwd=PUSHAGENT)
agent_refused("push: agent branch, -u HEAD asks", VCS + " push -u origin HEAD", cwd=PUSHAGENT)
agent_refused("push: agent branch, @ asks", VCS + " push origin @", cwd=PUSHAGENT)
agent_refused("push: agent branch, the current name as a colon-less refspec asks",
              VCS + " push origin claude/agent-a22bb0ed47825117b", cwd=PUSHAGENT)
agent_refused("push: agent branch, a bare push under push.default current asks",
              VCS + " -c push.default=current push", cwd=PUSHAGENT)
agent_refused("push: agent worktree, worktree-agent-<hex>, -u HEAD asks", VCS + " push -u origin HEAD",
              cwd=PUSHAGENTWT)
agent_refused("push: agent worktree, agent-<hex>, -u HEAD asks", VCS + " push -u origin HEAD", cwd=PUSHAGENTBARE)
# An explicit agent destination from a branch with no upstream (PUSHFEAT, `feat`).
agent_refused("push: explicit agent destination from a branch with no upstream asks",
              VCS + " push origin HEAD:claude/agent-a22bb0ed47825117b")
# Under push.autoSetupRemote, git pushes the current name and sets its upstream itself, so a bare push, `origin`
# or `-u origin` writes the agent name. The key rides on the call, where the guard reads it.
agent_refused("push: agent branch, a bare push under autoSetupRemote asks",
              VCS + " -c push.autoSetupRemote=true push", cwd=PUSHAGENT)
agent_refused("push: agent branch, origin under autoSetupRemote asks",
              VCS + " -c push.autoSetupRemote=true push origin", cwd=PUSHAGENT)
agent_refused("push: agent branch, -u origin under autoSetupRemote asks",
              VCS + " -c push.autoSetupRemote=true push -u origin", cwd=PUSHAGENT)
# The config-file form: push.autoSetupRemote is in the repo's own config, not on the call, so a bare push is refused.
agent_refused("push: agent branch, a bare push under a config autoSetupRemote asks", VCS + " push",
              cwd=PUSHAGENTCFG)
# The exact shape: eight hex characters after the prefix are refused.
agent_refused("push: agent-12345678, -u HEAD asks (8 hex is the exact shape)", VCS + " push -u origin HEAD",
              cwd=PUSHAGENTEIGHT)
# The refusal names the lane's own branch, and it does not echo the agent's name from the command. The push names
# the agent branch as its destination from a lane checkout (PUSHFEAT, `feat`), so the name is in the command.
sh("push: agent branch named in the command, the refusal names the lane-branch remedy, not the agent name",
   VCS + " push origin claude/agent-a22bb0ed47825117b", "deny", PUSH_AGENT_RULE, cwd=PUSHFEAT,
   carries=(PUSH_AGENT_REMEDY,), lacks=PUSH_AGENT_LACKS + ("claude/agent-a22bb0ed47825117b",))


def agent_refusal_opens_with_rule_case():
    """The printed reason is "<rule id>: <reason>", and the reason opens "Rule (Git): " as the sibling push refusals
    do (PUSH_REASON, PUSH_MAIN_REASON). No refusal can open with "Rule (" itself."""
    got, reason = decide({
        "raw": None, "tool": "Bash", "cwd": PUSHAGENT, "session": None,
        "env_path": None, "tool_input": {"command": VCS + " push origin HEAD"},
    })
    want = PUSH_AGENT_RULE + ": Rule (Git): "
    if got != "deny":
        return False, "expected deny, got %s" % got
    if not reason.startswith(want):
        return False, "the reason does not open with %r: %r" % (want, reason[:90])
    return True, "a deny whose reason opens with %r" % want


# A side effect pin: under push.autoSetupRemote, a bare push from main with no upstream writes main, so push-main asks.
sh("push: main with no upstream, a bare push under autoSetupRemote asks push-main",
   VCS + " -c push.autoSetupRemote=true push", "ask", PUSH_MAIN_RULE, cwd=PUSHMAIN)

# SILENT, rule push-agent-branch. Each is an allow that prints nothing. The lane and feature branch controls
# are the no-upstream rows above (PUSHFEAT, `feat`): their -u and HEAD pushes stay silent under this rule too.
push_case("agent branch, HEAD to lane-x is silent", "origin HEAD:lane-x", "allow", cwd=PUSHAGENT, silent=True)
push_case("agent branch, HEAD to refs/heads/lane-x is silent", "origin HEAD:refs/heads/lane-x", "allow",
          cwd=PUSHAGENT, silent=True)
push_case("agent branch, a dry run of HEAD is not this rule", "--dry-run origin HEAD", "allow",
          cwd=PUSHAGENT, silent=True)
push_case("agent branch, --delete of the agent name is not this rule",
          "--delete origin claude/agent-a22bb0ed47825117b", "allow", cwd=PUSHAGENT, silent=True)
push_case("agent branch, a colon delete of the agent name is not this rule",
          "origin :claude/agent-a22bb0ed47825117b", "allow", cwd=PUSHAGENT, silent=True)
push_case("agent-notes, -u HEAD is silent (no hex after the prefix)", "-u origin HEAD", "allow",
          cwd=PUSHAGENTNOTES, silent=True)
push_case("my-agent-abc, -u HEAD is silent (too short to be hex)", "-u origin HEAD", "allow",
          cwd=PUSHAGENTMYABC, silent=True)
push_case("my-agent-<hex>, -u HEAD is silent (the shape must open the name)", "-u origin HEAD", "allow",
          cwd=PUSHAGENTMYHEX, silent=True)
push_case("agent-1234567, -u HEAD is silent (7 hex is one short of the shape)", "-u origin HEAD", "allow",
          cwd=PUSHAGENTSHORT, silent=True)
# The same autoSetupRemote forms on a lane branch with no upstream (PUSHFEAT, `feat`) stay silent.
sh("push: lane branch, a bare push under autoSetupRemote is silent",
   VCS + " -c push.autoSetupRemote=true push", "allow", cwd=PUSHFEAT, silent=True)
sh("push: lane branch, origin under autoSetupRemote is silent",
   VCS + " -c push.autoSetupRemote=true push origin", "allow", cwd=PUSHFEAT, silent=True)
sh("push: lane branch, -u origin under autoSetupRemote is silent",
   VCS + " -c push.autoSetupRemote=true push -u origin", "allow", cwd=PUSHFEAT, silent=True)
# Controls for the refusal, all silent allows. PUSHOWNREF is `lane-x`, tracking origin/batch-1, with origin/lane-x on
# the remote. The archive row pushes an agent's own branch to archive/, which shared-trees-archive-then-delete
# requires before a delete, so it must stay silent.
sh("push: lane branch, lane-x pushed by its own name is silent", VCS + " push origin lane-x", "allow",
   cwd=PUSHOWNREF, silent=True)
sh("push: lane branch, -u origin of lane-x is silent", VCS + " push -u origin lane-x", "allow",
   cwd=PUSHOWNREF, silent=True)
sh("push: lane branch, --delete of lane-x is silent", VCS + " push --delete origin lane-x", "allow",
   cwd=PUSHOWNREF, silent=True)
sh("push: agent checkout, HEAD to lane/x is silent", VCS + " push origin HEAD:lane/x", "allow",
   cwd=PUSHAGENT, silent=True)
sh("push: agent checkout, HEAD to archive/ of the agent's own branch is silent",
   VCS + " push origin HEAD:archive/claude/agent-a22bb0ed47825117b", "allow", cwd=PUSHAGENT, silent=True)

# ASK, owner rulings 207 a. A non-forced push whose destination is the literal
# name main or master asks. The name is literal: origin/HEAD does not decide it.
push_case("main, HEAD:main from a feature branch asks", "origin HEAD:main", "ask", rule=PUSH_MAIN_RULE)
push_case("main, a push of main from a feature branch asks", "origin main", "ask", rule=PUSH_MAIN_RULE)
push_case("main, a full ref to refs/heads/main asks", "origin x:refs/heads/main", "ask", rule=PUSH_MAIN_RULE)
push_case("master, a push to master asks", "origin master", "ask", rule=PUSH_MAIN_RULE)
# A space beside a refspec name is no branch. git's ref-name check refuses " main" and "main ", so no push of either reaches
# main, and the guard allows each. names_default_branch does not strip: it compares the name as given, so an escaped space,
# which the reader keeps in the name, is not a default name and allows. The only strip is the MCP call site (hooks/guard.py,
# `branch.strip()` before names_default_branch), which takes a branch argument, not a refspec. A quoted space never reaches
# the name: push_text blanks quoted text, so the two quoted forms are controls that allow already.
push_case("a refspec with an escaped leading space allows, git refuses that ref", "origin \\ main", "allow")
push_case("a refspec with an escaped trailing space allows, git refuses that ref", "origin main\\ ", "allow")
push_case('a quoted refspec " main" allows, its text is blanked before the reader', 'origin " main"', "allow")
push_case('a quoted refspec "main " allows, its text is blanked before the reader', 'origin "main "', "allow")
push_case("main, a second refspec that reaches main asks", "origin HEAD:push-guard-asks HEAD:main", "ask",
          rule=PUSH_MAIN_RULE)
# On a lane checkout with local main equal to origin/main, --all and --branches are silent: neither push writes main.
# The refusal and allow rows are in the section below.
all_allowed("lane checkout, --all with local main equal to origin/main is silent", "--all origin", cwd=PUSHFEAT)
all_allowed("lane checkout, --branches with local main equal to origin/main is silent", "--branches origin",
            cwd=PUSHFEAT)
# A -u push of the local name writes main when the checkout is main, and -u does not hide a second refspec to main.
push_case("main, -u HEAD on main asks", "-u origin HEAD", "ask", cwd=PUSHMAIN, rule=PUSH_MAIN_RULE)
push_case("stacked lane, -u HEAD with a second refspec to main asks", "-u origin HEAD main", "ask",
          cwd=PUSHSTACK, rule=PUSH_MAIN_RULE)
push_case("main, HEAD:main asks where origin/HEAD names trunk", "origin HEAD:main", "ask", cwd=PUSHTRUNK,
          rule=PUSH_MAIN_RULE)
# A branch that tracks main writes main on a bare push. The upstream is main, so 206 a stays silent here.
push_case("main tracking origin/main, a bare push asks", "", "ask", cwd=PUSHMAINUP, rule=PUSH_MAIN_RULE)
push_case("main tracking origin/main, HEAD asks", "origin HEAD", "ask", cwd=PUSHMAINUP, rule=PUSH_MAIN_RULE)
sh("push: main, a bare push under push.default current on main asks",
   VCS + " -c push.default=current push", "ask", PUSH_MAIN_RULE, cwd=PUSHMAIN)
sh("push: main, a bare push under push.default upstream from a branch tracking main asks",
   VCS + " push", "ask", PUSH_MAIN_RULE, cwd=PUSHUP)

# The host's file-write tools push too. A write to main or master asks, as the shell push does (rule push-main); a write to a
# feature branch is silent. Each call names its branch in its input, so no repo is read.
PUSH_MAIN_TOOLS = (
    ("mcp__github__push_files", {"files": [{"path": "f.txt", "content": "x"}], "message": "x"}),
    ("mcp__github__create_or_update_file", {"path": "f.txt", "content": "x", "message": "x"}),
    ("mcp__github__delete_file", {"path": "f.txt", "message": "x"}),
)
for _tool, _fields in PUSH_MAIN_TOOLS:
    for _branch in ("main", "master"):
        add("push-main: %s to %s asks" % (_tool, _branch), "ask", PUSH_MAIN_RULE, tool=_tool, cwd=NOGIT,
            owner="y", repo="x", branch=_branch, **_fields)
    add("push-main: %s to a feature branch is silent" % _tool, "allow", silent=True, tool=_tool, cwd=NOGIT,
        owner="y", repo="x", branch="feat", **_fields)
# A full ref names the same branch as the bare name: the shell form strips refs/heads/ before it reads main or master.
for _tool in ("mcp__github__push_files", "mcp__github__create_or_update_file"):
    for _branch in ("refs/heads/main", "refs/heads/master"):
        add("push-main: %s to %s asks" % (_tool, _branch), "ask", PUSH_MAIN_RULE, tool=_tool, cwd=NOGIT,
            owner="y", repo="x", branch=_branch, **dict(PUSH_MAIN_TOOLS)[_tool])
    add("push-main: %s to refs/heads/feat is silent" % _tool, "allow", silent=True, tool=_tool, cwd=NOGIT,
        owner="y", repo="x", branch="refs/heads/feat", **dict(PUSH_MAIN_TOOLS)[_tool])
# The MCP call with a branch named " main" still asks. The MCP side is judged apart from the shell's strip above.
add('push-main: mcp__github__push_files to " main" still asks', "ask", PUSH_MAIN_RULE, tool="mcp__github__push_files",
    cwd=NOGIT, owner="y", repo="x", branch=" main", **dict(PUSH_MAIN_TOOLS)["mcp__github__push_files"])

# ASK, rule push-main, judged on the remote the push names. A network remote still asks: an scp-form origin, a
# network URL named on the command line, and a `-C` into a repo whose origin is a network URL. The https
# origin rows above (PUSHFEAT) and the bare push resolving to main on PUSHUP are the other controls.
push_case("main, an scp-form origin asks", "origin main", "ask", cwd=PUSHSSH, rule=PUSH_MAIN_RULE)
push_case("main, a network URL named as the remote asks, from a repo with no remote",
          "https://example.invalid/r.git main", "ask", cwd=PUSHNOREMOTE, rule=PUSH_MAIN_RULE)
sh("main, git -C into a repo with a network origin asks, from a repo with no remote",
   VCS + " -C " + slash(PUSHFEAT) + " push origin main", "ask", PUSH_MAIN_RULE, cwd=PUSHNOREMOTE)

# SILENT, rule push-main. The remote the push names is a local path (absolute, relative or file://), or the
# repo has no remote of that name, so no network remote is written. Each is an allow that prints nothing.
push_case("main, an origin that is a local path, a push of main is silent", "origin main", "allow",
          cwd=PUSHLOCAL, silent=True)
push_case("main, an origin that is a local path, HEAD:main is silent", "origin HEAD:main", "allow",
          cwd=PUSHLOCAL, silent=True)
push_case("main, a local path named as the remote is silent", slash(BRANCHREMOTE) + " main", "allow",
          cwd=PUSHFEAT, silent=True)
push_case("main, a relative path named as the remote is silent", "../branchremote.git main", "allow",
          cwd=PUSHFEAT, silent=True)
push_case("main, a file URL named as the remote is silent", "file://" + slash(BRANCHREMOTE) + " main",
          "allow", cwd=PUSHFEAT, silent=True)
push_case("main, a remote the repo does not have is silent", "upstream main", "allow", cwd=PUSHFEAT,
          silent=True)
push_case("main, no remote in the repo is silent", "origin main", "allow", cwd=PUSHNOREMOTE, silent=True)
sh("main, git -C into a repo with no remote is silent, from a repo with a network origin",
   VCS + " -C " + slash(PUSHNOREMOTE) + " push origin main", "allow", cwd=PUSHFEAT, silent=True)

# ASK, rules push-stray-branch and push-main, and DENY, rule push-agent-branch, on a local-path origin. A main
# refspec there is silent, and the refspec after it still decides. The controls decide with no main refspec ahead:
# HEAD on PUSHLOCALSTRAY (its branch tracks origin/other) is stray, and the agent name on PUSHLOCAL is refused.
push_case("local origin, main then HEAD on a branch tracking another name asks stray", "origin main HEAD", "ask",
          cwd=PUSHLOCALSTRAY, rule=PUSH_STRAY_RULE)
agent_refused("push: local origin, main then the agent name asks the agent rule",
              VCS + " push origin main claude/agent-deadbeef01", cwd=PUSHLOCAL)
push_case("local origin, HEAD on a branch tracking another name asks stray (control)", "origin HEAD", "ask",
          cwd=PUSHLOCALSTRAY, rule=PUSH_STRAY_RULE)
agent_refused("push: local origin, the agent name alone asks the agent rule (control)",
              VCS + " push origin claude/agent-deadbeef01", cwd=PUSHLOCAL)
# On a network origin, a main refspec before an agent name is refused by the agent rule, not asked as push-main.
# One click on the push-main ask would otherwise carry the agent branch to origin as well. The agent name is in the
# push, so the refusal holds from any checkout. A main refspec before a lane name still asks push-main, and so does
# `origin main HEAD`.
push_case("network origin, main then HEAD asks push-main", "origin main HEAD", "ask", rule=PUSH_MAIN_RULE)
push_case("network origin, main then a lane name asks push-main", "origin main HEAD:lane-x", "ask",
          rule=PUSH_MAIN_RULE)
sh("push: network origin, main then the agent name asks the agent rule",
   VCS + " push origin main claude/agent-deadbeef01", "deny", PUSH_AGENT_RULE,
   carries=(PUSH_AGENT_REMEDY,), lacks=PUSH_AGENT_LACKS + ("claude/agent-deadbeef01",))
sh("push: network origin, main then HEAD:agent-<hex> asks the agent rule",
   VCS + " push origin main HEAD:agent-deadbeef01", "deny", PUSH_AGENT_RULE,
   carries=(PUSH_AGENT_REMEDY,), lacks=PUSH_AGENT_LACKS + ("agent-deadbeef01",))
# A combined push from an agent checkout: --all sends main and the agent's own branch, so the agent rule refuses it.
agent_refused("push: agent checkout, --all with main asks the agent rule", VCS + " push --all origin", cwd=PUSHAGENT)
# A `git -c remote.origin.url=` override names the remote's URL for the read, so the local origin is a network one.
sh("main, a local origin made a network remote by git -c remote.origin.url asks push-main",
   VCS + " -c remote.origin.url=https://example.invalid/r.git push origin main", "ask", PUSH_MAIN_RULE,
   cwd=PUSHLOCAL)

# ASK, rule push-main, on a remote the shell has not expanded. The token holds `$`, a backtick or `$(`. It names no
# remote in the repo, yet the shell may expand it to a network remote, so the push asks. PUSHFEAT's origin is https,
# so only the token decides the ask here.
push_case("main, a double-quoted shell variable as the remote asks push-main", '"$REMOTE" main', "ask",
          rule=PUSH_MAIN_RULE)
push_case("main, an unquoted shell variable as the remote asks push-main", "$REMOTE HEAD:main", "ask",
          rule=PUSH_MAIN_RULE)
push_case("main, a backtick as the remote asks push-main", "`printf origin` main", "ask", rule=PUSH_MAIN_RULE)
push_case("main, a command substitution as the remote asks push-main", "$(printf origin) main", "ask",
          rule=PUSH_MAIN_RULE)
sh("main, a bare push with a shell variable as the remote asks push-main under push.default current",
   VCS + ' -c push.default=current push "$REMOTE"', "ask", PUSH_MAIN_RULE, cwd=PUSHMAIN)

# SILENT, rule push-main, the controls of that ask. A shell-variable remote on a feature destination writes no main.
# A `$` in the source of a push to main stays in the refspec: the remote is the local origin, so the push is silent.
push_case("a shell variable as the remote, HEAD to a feature name, is silent", '"$REMOTE" HEAD:feat-x', "allow",
          silent=True)
push_case("a shell variable in the source of a push to main on a local origin is silent", 'origin "$SRC":main',
          "allow", cwd=PUSHLOCALMAIN, silent=True)

# Local origin on main (PUSHLOCALMAIN, tracking origin/main) and its network twin on the same branch and upstream
# (PUSHMAINUP). Each form that writes main is silent on the local path and asks on the network remote.
sh("main tracking origin/main, local origin, a bare push under push.default simple is silent",
   VCS + " -c push.default=simple push", "allow", cwd=PUSHLOCALMAIN, silent=True)
sh("main tracking origin/main, network origin, a bare push under push.default simple asks push-main",
   VCS + " -c push.default=simple push", "ask", PUSH_MAIN_RULE, cwd=PUSHMAINUP)
push_case("main tracking origin/main, local origin, HEAD is silent", "origin HEAD", "allow", cwd=PUSHLOCALMAIN,
          silent=True)
push_case("main tracking origin/main, network origin, HEAD asks push-main", "origin HEAD", "ask", cwd=PUSHMAINUP,
          rule=PUSH_MAIN_RULE)
push_case("main tracking origin/main, local origin, --all is silent", "origin --all", "allow", cwd=PUSHLOCALMAIN,
          silent=True)
all_allowed("main tracking origin/main, network origin, --all is silent, local main equal", "origin --all",
            cwd=PUSHMAINUP)

# ASK, rule push-main. A folder that does not exist cannot be read, and an unreadable config is unknown, which asks.
# The session's own folder is the local origin, so only the missing folder the push runs in can make it a network one.
sh("main, cd into a folder that does not exist, then origin main, asks push-main",
   "cd " + slash(os.path.join(ROOT, "pushmissing")) + " && " + VCS + " push origin main", "ask", PUSH_MAIN_RULE,
   cwd=PUSHLOCALMAIN)

# --all and --branches never ask. A plain push of every branch is refused when it would update main or master on the
# remote, and allowed when it would not. The remote's main is read from its remote-tracking ref. A ref that differs from
# local main, or is missing, counts as an update, since the push may write main. A ref that matches local main is trusted:
# the guard never contacts the remote.
# The four checkouts give the same verdict, except the agent rows. The agent-branch rule refuses an agent checkout's
# --all and --branches, since the agent branch in that push would still reach origin.
for form in ("--all", "--branches"):
    all_refused(form + " from a main checkout, local main ahead of origin/main, refuses", form + " origin",
                cwd=PUSHAHEAD)
    all_refused(form + " from a lane checkout, local main ahead of origin/main, refuses", form + " origin",
                cwd=PUSHAHEADLANE)
    all_refused(form + " from a detached checkout, local main ahead of origin/main, refuses", form + " origin",
                cwd=PUSHAHEADDET)
    agent_refused("push: agent checkout, " + form + " with local main ahead, refuses under the agent rule",
                  VCS + " push " + form + " origin", cwd=PUSHAHEADAGENT)
all_refused("--all with no remote named, from a main checkout, local main ahead, refuses", "--all", cwd=PUSHAHEAD)
# A glob refspec from every branch to every branch reaches main as --all does. Its agent row is pinned to this rule:
# the agent-branch rule covers only --all and --branches.
all_refused("glob refspec refs/heads/*:refs/heads/* from a main checkout, local main ahead, refuses",
            "origin refs/heads/*:refs/heads/*", cwd=PUSHAHEAD)
all_refused("glob refspec refs/heads/*:refs/heads/* from a lane checkout, local main ahead, refuses",
            "origin refs/heads/*:refs/heads/*", cwd=PUSHAHEADLANE)
all_refused("glob refspec refs/heads/*:refs/heads/* from a detached checkout, local main ahead, refuses",
            "origin refs/heads/*:refs/heads/*", cwd=PUSHAHEADDET)
all_refused("glob refspec refs/heads/*:refs/heads/* from an agent checkout, local main ahead, refuses",
            "origin refs/heads/*:refs/heads/*", cwd=PUSHAHEADAGENT)
# git's `*` matches an empty name, so `main*` and `*main` each name main itself and reach it as `*` does. The lane
# checkout keeps PUSHAHEADLANE's fixture: local main ahead of its tracking ref, on a network origin.
all_refused("glob refspec refs/heads/main*:refs/heads/main* from a lane checkout, local main ahead, refuses",
            "origin refs/heads/main*:refs/heads/main*", cwd=PUSHAHEADLANE)
all_refused("glob refspec refs/heads/*main:refs/heads/*main from a lane checkout, local main ahead, refuses",
            "origin refs/heads/*main:refs/heads/*main", cwd=PUSHAHEADLANE)
all_refused("quoted glob refspec refs/heads/main*:refs/heads/main* from a lane checkout, local main ahead, refuses",
            "origin 'refs/heads/main*:refs/heads/main*'", cwd=PUSHAHEADLANE)
# Master is the other default name: a glob that names master itself refuses, with no local main.
all_refused("glob refspec refs/heads/master*:refs/heads/master* from a master checkout, local master ahead, refuses",
            "origin refs/heads/master*:refs/heads/master*", cwd=PUSHMASTERAHEAD)
all_refused("glob refspec refs/heads/*master:refs/heads/*master from a master checkout, local master ahead, refuses",
            "origin refs/heads/*master:refs/heads/*master", cwd=PUSHMASTERAHEAD)
all_allowed("glob refspec refs/heads/*:refs/heads/* with local main equal to origin/main is silent",
            "origin refs/heads/*:refs/heads/*", cwd=PUSHFEAT)
# A star that cannot name main stays silent: lane* matches no default branch, with the refusals' own lane fixture.
all_allowed("glob refspec refs/heads/lane*:refs/heads/lane* from a lane checkout, local main ahead, is silent",
            "origin refs/heads/lane*:refs/heads/lane*", cwd=PUSHAHEADLANE)
# A main-matching glob is silent when local main equals its tracking ref: the push writes nothing to main.
all_allowed("glob refspec refs/heads/main*:refs/heads/main* with local main equal to origin/main is silent",
            "origin refs/heads/main*:refs/heads/main*", cwd=PUSHMAIN)
all_allowed("glob refspec refs/heads/*main:refs/heads/*main with local main equal to origin/main is silent",
            "origin refs/heads/*main:refs/heads/*main", cwd=PUSHMAIN)
# A glob to a local-path origin is no network push, however far local main is ahead of its tracking ref.
all_allowed("glob refspec refs/heads/*:refs/heads/* to a local-path origin with local main ahead, is silent",
            "origin refs/heads/*:refs/heads/*", cwd=PUSHLOCALAHEAD)
# A glob into another name does not reach main: main lands on lane/main, a new branch.
all_allowed("glob refspec refs/heads/*:refs/heads/lane/* from a main checkout, local main ahead, is silent",
            "origin refs/heads/*:refs/heads/lane/*", cwd=PUSHAHEAD)
all_allowed("glob refspec refs/heads/*:refs/heads/lane/* from a lane checkout, local main ahead, is silent",
            "origin refs/heads/*:refs/heads/lane/*", cwd=PUSHAHEADLANE)
all_allowed("glob refspec refs/heads/*:refs/heads/lane/* from a detached checkout, local main ahead, is silent",
            "origin refs/heads/*:refs/heads/lane/*", cwd=PUSHAHEADDET)
# A colon-less glob names the same ref on both sides: `refs/tags/v*` is `refs/tags/v*:refs/tags/v*`. Its source
# cannot name main, so it sends no main and is silent, even with local main ahead of its tracking ref.
all_allowed("glob refspec refs/tags/v* (colon-less) from a lane checkout, local main ahead, is silent",
            "origin 'refs/tags/v*'", cwd=PUSHAHEADLANE)
all_allowed("glob refspec refs/heads/lane/* (colon-less) from a lane checkout, local main ahead, is silent",
            "origin 'refs/heads/lane/*'", cwd=PUSHAHEADLANE)
# A colon-less glob whose source reaches main maps onto itself and reaches main, so it refuses as the colon form does.
all_refused("glob refspec refs/heads/* (colon-less) from a lane checkout, local main ahead, refuses",
            "origin 'refs/heads/*'", cwd=PUSHAHEADLANE)
all_refused("glob refspec refs/heads/main* (colon-less) from a lane checkout, local main ahead, refuses",
            "origin 'refs/heads/main*'", cwd=PUSHAHEADLANE)
# A tracking ref that is missing, or that differs from local main, refuses. The push may write main.
all_refused("--all from a lane checkout, no origin/main tracking ref, refuses", "--all origin", cwd=PUSHNOTRACK)
all_refused("--branches from a lane checkout, no origin/main tracking ref, refuses", "--branches origin",
            cwd=PUSHNOTRACK)
all_refused("--all from a main checkout, local main behind origin/main, refuses", "--all origin", cwd=PUSHBEHIND)
# Master is the other default name: a local master ahead of origin/master refuses, with no local main.
all_refused("--all from a master checkout, local master ahead of origin/master, refuses", "--all origin",
            cwd=PUSHMASTERAHEAD)
all_refused("--branches from a master checkout, local master ahead of origin/master, refuses", "--branches origin",
            cwd=PUSHMASTERAHEAD)
# ALLOW: the push writes no main or master. Local main equals the tracking ref, or neither name exists locally.
all_allowed("--all from a main checkout, local main equal to origin/main, is silent", "--all origin", cwd=PUSHMAIN)
all_allowed("--branches from a main checkout, local main equal to origin/main, is silent", "--branches origin",
            cwd=PUSHMAIN)
all_allowed("--all from a detached checkout, local main equal to origin/main, is silent", "--all origin",
            cwd=PUSHDETACHED)
all_allowed("--branches from a detached checkout, local main equal to origin/main, is silent", "--branches origin",
            cwd=PUSHDETACHED)
all_allowed("--all with no local main or master, from a lane checkout, is silent", "--all origin", cwd=PUSHNOMAIN)
all_allowed("--branches with no local main or master, is silent", "--branches origin", cwd=PUSHNOMAIN)
# DRY RUN AND LOCAL PATHS keep their allow: a dry run writes nothing, and a local path is no network remote.
all_allowed("--all dry run with local main ahead, is silent", "--all --dry-run origin", cwd=PUSHAHEAD)
all_allowed("--all to a local-path origin with local main ahead, is silent", "--all origin", cwd=PUSHLOCALAHEAD)
all_allowed("--branches to a local-path origin with local main ahead, is silent", "--branches origin",
            cwd=PUSHLOCALAHEAD)
# A second remote is read under its own name. On PUSHUPSTREAM, local main equals upstream/main and origin has no main.
# A bare --all resolves to upstream through branch.feat.remote, so it is silent as well.
all_allowed("--all to a second remote whose main ref equals local main, is silent", "--all upstream", cwd=PUSHUPSTREAM)
all_allowed("--all with no remote named, a branch tracking a second remote, is silent", "--all", cwd=PUSHUPSTREAM)
all_refused("--all to origin, which has no main ref, from a branch tracking a second remote, refuses", "--all origin",
            cwd=PUSHUPSTREAM)
# A failed ref read refuses: the tracking ref cannot be read, so the push may write main.
all_refused("--all from a lane checkout, a failed ref read, refuses", "--all origin", cwd=PUSHFEAT,
            env_path=PUSHFAILSHIM + os.pathsep + GIT_PATH)

# REFUSED, rule push-all-main, for a local agent-named branch. --all and --branches send every local branch to origin,
# so a branch named like an agent worktree reaches origin although main equals its tracking ref. The refusal's remedy is
# a push of named branches. The glob refspec that sends every branch to main is refused the same way.
for form in ("--all", "--branches"):
    all_agent_refused(form + " with a local agent-named branch, main matching its tracking ref, refuses",
                      form + " origin", cwd=PUSHALLAGENT)
    all_agent_refused(form + " with a local worktree-agent-named branch, main matching its tracking ref, refuses",
                      form + " origin", cwd=PUSHALLAGENTWT)
    all_agent_refused(form + " with a local claude/agent-named branch, main matching its tracking ref, refuses",
                      form + " origin", cwd=PUSHALLAGENTCLAUDE)
all_agent_refused("glob refspec refs/heads/*:refs/heads/* with a local agent-named branch, main matching its tracking "
                  "ref, refuses", "origin refs/heads/*:refs/heads/*", cwd=PUSHALLAGENT)
# Green controls beside them. The same fixture with no agent-named branch is silent, and a push of a named branch is
# unchanged by an agent-named branch that sits in the same repo.
for form in ("--all", "--branches"):
    all_allowed(form + " with no agent-named local branch, main matching its tracking ref, is silent", form + " origin",
                cwd=PUSHALLNOAGENT)
all_allowed("glob refspec refs/heads/*:refs/heads/* with no agent-named local branch, main matching its tracking ref, "
            "is silent", "origin refs/heads/*:refs/heads/*", cwd=PUSHALLNOAGENT)
push_case("origin feature with a local agent-named branch present, is silent", "origin feature", "allow",
          cwd=PUSHALLAGENT, silent=True)

# REFUSED, rule push-all-main, when the listing of the local branches fails. The tracking refs show no update, so the
# agent test reads the local branches next. A failed read is unknown, and unknown is never safe. PUSHALLBROKEN holds an
# agent-named branch, and a packed ref that the listing of refs/heads/ cannot read.
all_refused("--all with a failed read of the local branches, main matching its tracking ref, refuses", "--all origin",
            cwd=PUSHALLBROKEN)
all_refused("--branches with a failed read of the local branches, main matching its tracking ref, refuses",
            "--branches origin", cwd=PUSHALLBROKEN)
all_refused("glob refspec refs/heads/*:refs/heads/* with a failed read of the local branches refuses",
            "origin refs/heads/*:refs/heads/*", cwd=PUSHALLBROKEN)
# A failed read of the tracking refs refuses for the update even when a local agent-named branch is present: the
# tracking read is judged first, so the reason is the update's, not the agent's.
all_update_refused("--all with a failed read of the tracking refs, and a local agent-named branch, refuses for the update",
                   "--all origin", cwd=PUSHALLAGENT, env_path=PUSHTRACKFAILSHIM + os.pathsep + GIT_PATH)
# REFUSED for the update, not for the agent branch. Local main is one commit past its tracking ref, and a local
# agent-named branch is present, so the reason names the update: the update is judged first.
for form in ("--all", "--branches"):
    all_update_refused(form + " with main ahead of its tracking ref and a local agent-named branch refuses for the update",
                       form + " origin", cwd=PUSHALLAGENTAHEAD)
all_update_refused("glob refspec refs/heads/*:refs/heads/* with main ahead of its tracking ref and a local agent-named "
                   "branch refuses for the update", "origin refs/heads/*:refs/heads/*", cwd=PUSHALLAGENTAHEAD)
# REFUSED, a glob whose source side matches a local agent-named branch, though it reaches no main or master.
all_agent_refused("glob refspec agent-*:agent-* with a local agent-named branch refuses, though it reaches no main",
                  "origin agent-*:agent-*", cwd=PUSHALLAGENT)
all_agent_refused("glob refspec refs/heads/agent-*:refs/heads/agent-* with a local agent-named branch refuses, though "
                  "it reaches no main", "origin refs/heads/agent-*:refs/heads/agent-*", cwd=PUSHALLAGENT)
# SILENT, a glob is judged by the local branches its source side matches. A glob that sends main and no agent-named
# branch is silent beside one, and so is a glob whose prefix and suffix overlap inside a name no branch carries.
all_allowed("glob refspec refs/heads/main* with a local agent-named branch, main matching its tracking ref, is silent",
            "origin refs/heads/main*:refs/heads/main*", cwd=PUSHALLAGENT)
all_allowed("glob refspec refs/heads/agent-*x with a local agent-named branch, no branch ends in x, is silent",
            "origin refs/heads/agent-*x:refs/heads/agent-*x", cwd=PUSHALLAGENT)
all_allowed("glob refspec whose prefix and suffix overlap, with a local agent-named branch, is silent",
            "origin refs/heads/agent-*-0123456789abcdef:refs/heads/agent-*-0123456789abcdef", cwd=PUSHALLAGENT)

# SILENT, the false alarms of both rulings. Each is an allow that prints nothing.
# Inherited and own upstreams: a lane cut from main or master, and a branch that tracks its own name.
push_case("lane from main, -u HEAD is silent", "-u origin HEAD", "allow", cwd=PUSHLANE, silent=True)
push_case("lane from main, HEAD is silent", "origin HEAD", "allow", cwd=PUSHLANE, silent=True)
push_case("lane from master, HEAD is silent", "origin HEAD", "allow", cwd=PUSHLANEMASTER, silent=True)
push_case("own upstream, HEAD is silent", "origin HEAD", "allow", cwd=PUSHSELF, silent=True)
# No upstream yet: the first push of a branch.
push_case("first push with no upstream, -u HEAD is silent", "-u origin HEAD", "allow", silent=True)
push_case("first push with no upstream, HEAD is silent", "origin HEAD", "allow", silent=True)
# Explicit destinations, the form agents push by, from a branch whose upstream differs.
push_case("explicit destination from a mismatched upstream is silent", "origin HEAD:push-guard-asks", "allow",
          cwd=PUSHSTRAY, silent=True)
push_case("archive, feat named to archive/feat is silent", "origin feat:archive/feat", "allow", silent=True)
push_case("archive, HEAD to archive/x from a mismatched upstream is silent", "origin HEAD:archive/x", "allow",
          cwd=PUSHSTRAY, silent=True)
# A bare push that git itself refuses: push.default simple, the upstream names another branch.
push_case("push.default simple, a bare push with a mismatched upstream is git's refusal, silent", "", "allow",
          cwd=PUSHSTRAY, silent=True)
# Another remote than the upstream's remote: the rule reads only branch.<cur>.remote.
push_case("another remote than the upstream's is silent", "fork HEAD", "allow", cwd=PUSHSTRAY, silent=True)
# A -u push whose destination is the local branch's own name sets that upstream on purpose (ruling 206 a).
# PUSHSTACK is lane/fix, cut from origin/lane/base. PUSHSTRAY is `mylocal`,
# tracking origin/lane/x: its -u push writes `mylocal` by the same rule, so it is silent too.
push_case("stacked lane, -u HEAD is silent", "-u origin HEAD", "allow", cwd=PUSHSTACK, silent=True)
push_case("stacked lane, --set-upstream HEAD is silent", "--set-upstream origin HEAD", "allow", cwd=PUSHSTACK,
          silent=True)
push_case("stacked lane, -u naming the local branch is silent", "-u origin lane/fix", "allow", cwd=PUSHSTACK,
          silent=True)
sh("push: stacked lane, a bare -u under push.default current writes the local name, is silent",
   VCS + " -c push.default=current push -u origin", "allow", cwd=PUSHSTACK, silent=True)
push_case("stray branch, -u with HEAD writes the local name, is silent", "-u origin HEAD", "allow",
          cwd=PUSHSTRAY, silent=True)
# Decision plain-push-asks, item 432 a.
# A destination already on origin (refs/remotes/origin/<name>) is no stray. PUSHOWNREF is
# `lane-x`, tracking origin/batch-1, with origin/lane-x present: each implied push to its own name is silent.
push_case("own ref on origin, HEAD is silent", "origin HEAD", "allow", cwd=PUSHOWNREF, silent=True)
push_case("own ref on origin, @ is silent", "origin @", "allow", cwd=PUSHOWNREF, silent=True)
push_case("own ref on origin, the current name as a colon-less refspec is silent", "origin lane-x", "allow",
          cwd=PUSHOWNREF, silent=True)
sh("push: own ref on origin, a bare push under push.default current is silent",
   VCS + " -c push.default=current push", "allow", cwd=PUSHOWNREF, silent=True)
# A push that moves no branch: tags are not a branch destination, even on main.
push_case("--tags on main is silent", "origin --tags", "allow", cwd=PUSHMAIN, silent=True)
push_case("a tag name on main is silent", "origin v1.0", "allow", cwd=PUSHMAIN, silent=True)
# A dry run moves nothing, so it stays silent even at main. The dry-run check before push_ask_hit in
# guard.py is what keeps these silent.
push_case("a dry run to main, --dry-run origin HEAD:main, is silent", "--dry-run origin HEAD:main", "allow",
          silent=True)
push_case("a dry run to main, -n origin main, is silent", "-n origin main", "allow", silent=True)
push_case("a dry run of --branches, --branches --dry-run origin, is silent", "--branches --dry-run origin",
          "allow", silent=True)
# Tags move no branch. On main tracking origin/main a bare push would ask main, so the tags check is what
# keeps this one silent.
push_case("--tags on main tracking origin/main is silent", "origin --tags", "allow", cwd=PUSHMAINUP, silent=True)
# The main rule reads literal names. trunk is the default here, so a push to it is ordinary.
push_case("trunk, named by origin/HEAD, is ordinary for the main rule", "origin HEAD:trunk", "allow",
          cwd=PUSHTRUNK, silent=True)
# A plain push whose destination cannot be resolved stays allowed, as it is today.
push_case("a plain push, detached HEAD, no destination to read, stays allowed", "origin HEAD", "allow",
          cwd=PUSHDETACHED, silent=True)
push_case("a plain bare push, push.default matching, no destination to read, stays allowed", "", "allow",
          cwd=PUSHMATCH, silent=True)
push_case("a plain push where git cannot be read stays allowed", "origin HEAD", "allow", cwd=NOGIT, silent=True)

# Quoted and heredoc push text is data, never a push. The rules judge the command, not its text.
sh("push: text, a commit message that names a push to main, is silent",
   VCS + ' commit -m "git push origin main"', "allow", cwd=PUSHFEAT, silent=True)
sh("push: text, an echo that names a push of HEAD:main, is silent",
   'echo "' + VCS + ' push origin HEAD:main"', "allow", cwd=PUSHFEAT, silent=True)
sh("push: text, a heredoc body naming a push to main, is silent",
   "cat <<'EOF'\n" + VCS + " push origin main\nEOF", "allow", cwd=PUSHFEAT, silent=True)
sh("push: text, a multi-line quoted string naming a push to main, is silent",
   'echo "one line\n' + VCS + ' push origin main"', "allow", cwd=PUSHFEAT, silent=True)
# A comment opener inside a string does not hide the real push after it, and a lone quote in a message
# does not either (building-scanner-respects-strings). The push is a second command, so it denies alone.
chained_ask("push: a comment opener inside a string does not hide a push to main that follows it",
            'echo "#" && ' + VCS + " push origin main", cwd=PUSHMAIN)
chained_ask("push: a lone quote in a commit message does not hide a push to main that follows it",
            VCS + ' commit -m "don\'t" && ' + VCS + " push origin main", cwd=PUSHFEAT)
chained_ask("push: a lone quote in a commit message does not hide a stray push that follows it",
            VCS + ' commit -m "don\'t" && ' + VCS + " push origin HEAD", cwd=PUSHSTRAY)
# The agent push is refused on its own, by its rule, not by the ask-alone chain: no ask is chained with it.
agent_refused("push: agent branch, a lone quote in a commit message does not hide a push to an agent name",
              VCS + ' commit -m "don\'t" && ' + VCS + " push origin HEAD", cwd=PUSHAGENT)
agent_refused("push: agent branch, a comment opener inside a string does not hide a push to an agent name",
              'echo "#" && ' + VCS + " push origin HEAD", cwd=PUSHAGENT)
sh("push: text, an echo that names a push to an agent name, is silent",
   'echo "' + VCS + ' push origin HEAD:claude/agent-a22bb0ed47825117b"', "allow", cwd=PUSHAGENT, silent=True)
sh("push: text, a multi-line quoted string naming a push to an agent name, is silent",
   'echo "one line\n' + VCS + ' push origin HEAD"', "allow", cwd=PUSHAGENT, silent=True)

sh("push: setting the upstream", VCS + " push -u origin claude/lane", "allow", cwd=NOGIT)

sh("delete: the home directory", "rm -fr ~", "deny", "destructive-delete", cwd=NOGIT)
sh("delete: the home variable", "rm -rf $HOME", "deny", "destructive-delete", cwd=NOGIT)
sh("delete: the working directory", "rm -rf .", "deny", "destructive-delete", cwd=NOGIT)
sh("delete: a glob", "rm -rf *", "deny", "destructive-delete", cwd=NOGIT)
sh("delete: a drive root", "rm -rf C:/", "deny", "destructive-delete", cwd=NOGIT)
sh("delete: Remove-Item at a drive root", "Remove-Item -Recurse -Force C:\\", "deny",
   "destructive-delete", tool="PowerShell", cwd=NOGIT)
sh("delete: Remove-Item at the working directory", "Remove-Item -Recurse -Force .", "deny",
   "destructive-delete", tool="PowerShell", cwd=NOGIT)
sh("delete: Remove-Item with abbreviated flags at a glob", "Remove-Item -r -fo *", "deny",
   "destructive-delete", tool="PowerShell", cwd=NOGIT)
sh("delete: the alias, a drive root, and the flags after the target", "ri C:\\ -Recurse -Force",
   "deny", "destructive-delete", tool="PowerShell", cwd=NOGIT)
sh("delete: PowerShell folds case", "REMOVE-ITEM -RECURSE -FORCE ~", "deny", "destructive-delete",
   tool="PowerShell", cwd=NOGIT)

# PARITY is the point, not breadth. `rm -rf build/` is allowed, so its PowerShell twin must be too.
# A guard that answers differently for the same act teaches which tool to reach for.
sh("delete: a named build folder", "rm -rf build/", "allow", cwd=NOGIT)
sh("delete: a named dependency folder", "rm -rf node_modules", "allow", cwd=NOGIT)
sh("delete: the PowerShell twin of a named folder", "Remove-Item -Recurse -Force node_modules",
   "allow", tool="PowerShell", cwd=NOGIT)
sh("delete: one scratch file", "rm -f /tmp/scratch.txt", "allow", cwd=NOGIT)

# THE CMD.EXE VERBS. `rd`/`rmdir` and `del`/`erase` take `/s` (recurse) and `/q` (quiet,
# optional, never required), never `rm`'s or `Remove-Item`'s dash flags. Each denied case here
# has an rm or Remove-Item twin above that already denies, so the verdict carries over. Checked
# under BOTH tool names, since the guard reads the command TEXT, not which shell it says it runs
# it.
sh("delete: rd /s /q at a drive root, Bash", "rd /s /q C:\\", "deny", "destructive-delete",
   cwd=NOGIT)
sh("delete: rd /s /q at a drive root, PowerShell", "rd /s /q C:\\", "deny",
   "destructive-delete", tool="PowerShell", cwd=NOGIT)
sh("delete: rmdir /s (no /q) at a glob", "rmdir /s *", "deny", "destructive-delete", cwd=NOGIT)
sh("delete: del /s at the home variable", "del /s $HOME", "deny", "destructive-delete",
   cwd=NOGIT)
sh("delete: erase /s /q at a drive root", "erase /s /q C:/", "deny", "destructive-delete",
   cwd=NOGIT)
sh("delete: flags are case-insensitive", "RD /S /Q ~", "deny", "destructive-delete", cwd=NOGIT)

# THE THREE MEASURED COMMANDS (2026-09-24), two of the three. `%USERPROFILE%` and
# `$env:USERPROFILE` are the home directory, same as `$HOME` and `~` above. `C:\*` is a glob
# at a drive root, same shape as the bare glob and the bare drive root above, just combined.
sh("delete: cmd /c rd /s /q %USERPROFILE%, Bash", "cmd /c rd /s /q %USERPROFILE%", "deny",
   "destructive-delete", cwd=NOGIT)
sh("delete: cmd /c rd /s /q %USERPROFILE%, PowerShell", "cmd /c rd /s /q %USERPROFILE%",
   "deny", "destructive-delete", tool="PowerShell", cwd=NOGIT)
sh("delete: cmd.exe /c rmdir /s /q $env:USERPROFILE", "cmd.exe /c rmdir /s /q $env:USERPROFILE",
   "deny", "destructive-delete", tool="PowerShell", cwd=NOGIT)
sh("delete: del /s /q C:\\*, Bash", "del /s /q C:\\*", "deny", "destructive-delete", cwd=NOGIT)
sh("delete: del /s /q C:\\*, PowerShell", "del /s /q C:\\*", "deny", "destructive-delete",
   tool="PowerShell", cwd=NOGIT)

# refusal-vs-rule (destructive-delete, heredoc text): a quoted heredoc writes its body to a file, so a
# body that names a delete deletes nothing. The body is literal text for the three scanner shapes too: a
# comment opener, a multi-line backtick span, and a lone apostrophe. The forms that run the body refuse:
# a shell reads it. NOT PINNED HERE, and allowed on main: an unquoted heredoc's backticks and `$(...)`,
# and a python heredoc's rmtree. They are looser gaps, reported, not stricter refusals.
sh("delete: a quoted heredoc writes text that names the delete, deletes nothing",
   "cat <<'EOF' > notes.md\nrm -rf ./*\nEOF", "allow", cwd=NOGIT)
sh("delete: a quoted heredoc body with a comment opener names the delete, deletes nothing",
   "cat <<'EOF' > notes.md\n# clean up with rm -rf ./*\nEOF", "allow", cwd=NOGIT)
sh("delete: a quoted heredoc body with a multi-line backtick span names the delete, deletes nothing",
   "cat <<'EOF' > notes.md\n`first\nrm -rf ./*\nlast`\nEOF", "allow", cwd=NOGIT)
sh("delete: a quoted heredoc body with a lone apostrophe names the delete, deletes nothing",
   "cat <<'EOF' > notes.md\nit's the note: rm -rf ./*\nEOF", "allow", cwd=NOGIT)
sh("delete: a heredoc body piped to sh runs the delete", "cat <<EOF | sh\nrm -rf ./*\nEOF",
   "deny", "destructive-delete", cwd=NOGIT)
sh("delete: a heredoc body given to bash runs the delete", "bash <<EOF\nrm -rf ./*\nEOF",
   "deny", "destructive-delete", cwd=NOGIT)
sh("delete: a lone apostrophe in a quoted heredoc body does not hide a delete after it",
   "cat <<'EOF' > notes.md\nit's the note\nEOF\nrm -rf ./*", "deny", "destructive-delete", cwd=NOGIT)

# A file name ending in `py`, or a `py` folder, heads no interpreter: `cat > gen.py <<'EOF'` and
# `cat > py/notes.md <<'EOF'` write their body to the file, so a delete or a forced push in the body runs nothing.
sh("delete: a heredoc written to gen.py names a delete, deletes nothing",
   "cat > gen.py <<'EOF'\nrm -rf /\nEOF", "allow", cwd=NOGIT)
sh("push: a heredoc written to gen.py names a forced push, pushes nothing",
   "cat > gen.py <<'EOF'\n" + VCS + " push --force origin main\nEOF", "allow", cwd=NOGIT)
sh("delete: a heredoc written to py/notes.md names a delete, deletes nothing",
   "cat > py/notes.md <<'EOF'\nrm -rf ./*\nEOF", "allow", cwd=NOGIT)

# THE POWERSHELL ALIASES. `remove-item`, `ri`, `rd` and `rmdir` already matched the dash-flag
# pattern before this change. `del`, `erase` and `rm` did not: PowerShell's own aliases for
# Remove-Item, taking its `-Recurse`/`-Force` parameters rather than `rm`'s combined `-rf`.
sh("delete: del -Recurse -Force at the home directory", "del -Recurse -Force ~", "deny",
   "destructive-delete", tool="PowerShell", cwd=NOGIT)
sh("delete: erase -r -fo at a glob", "erase -r -fo *", "deny", "destructive-delete",
   tool="PowerShell", cwd=NOGIT)
sh("delete: rm -Recurse -Force at the home directory, the PowerShell alias, not the POSIX flag",
   "rm -Recurse -Force ~", "deny", "destructive-delete", tool="PowerShell", cwd=NOGIT)

# GREEN: the forms that stay allowed, parity with the rm/Remove-Item cases above.
sh("delete: a non-recursive del", "del file.txt", "allow", cwd=NOGIT)
sh("delete: rd with no /s", "rd emptydir", "allow", cwd=NOGIT)
sh("delete: rd /s /q at a plain relative subdir, parity with rm -rf build/", "rd /s /q build",
   "allow", cwd=NOGIT)

# QUOTED AND GREP FORMS. The command word is read in COMMAND POSITION off a quote-aware
# tokenizer, the same defect class rule 2's kill check was built to avoid: text sitting inside a
# quoted argument, or inside a grep pattern, never calls anything.
sh("delete: a quoted echo of the cmd.exe form calls nothing", 'echo "rd /s /q"', "allow",
   cwd=NOGIT)
sh("delete: a grep pattern naming the cmd.exe form calls nothing",
   'grep "del /s" notes.md', "allow", cwd=NOGIT)

# The `rm` pattern reads raw text: a target must end
# at a space or the end, the flags must be one `-rf` cluster, and a quote hides nothing. Three
# misses and one false alarm, each a form Claude writes.
#
# MISSES: a trailing slash or glob on a root or home, the long flags, and `--` before the
# target. Each is the same act as `rm -rf /` or `rm -rf ~`, which deny.
for _name, _command in (
    ("the home directory with a trailing slash", "rm -rf ~/"),
    ("everything under the root", "rm -rf /*"),
    ("everything under the home directory", "rm -rf ~/*"),
    ("the root, long flags", "rm --recursive --force /"),
    ("the home directory, long flags", "rm --recursive --force ~"),
    ("the home variable, long flags in the other order", "rm --force --recursive $HOME"),
    ("the root after --", "rm -rf -- /"),
    ("the home directory after --", "rm -rf -- ~"),
):
    sh("delete: " + _name, _command, "deny", "destructive-delete", cwd=NOGIT)
# More misses: a capital R, an extra flag letter after f, and the working directory spelled `./` or
# `./*` (`rm -rf .` and `rm -rf *` deny).
for _name, _command in (
    ("the root, capital R", "rm -Rf /"),
    ("the home directory, a verbose flag after f", "rm -rfv ~"),
    ("the working directory as ./", "rm -rf ./"),
    ("everything in the working directory as ./*", "rm -rf ./*"),
):
    sh("delete: " + _name, _command, "deny", "destructive-delete", cwd=NOGIT)
# THE SHELL SPELLINGS OF THE WORKING FOLDER. `$(pwd)` names the working folder, so a recursive
# delete of everything in it is the `./*` delete and gets its verdict. A named folder through
# `$(pwd)` or `$PWD` is the `./build` delete and passes. `$PWD` belongs to the variable rule
# (rm-var-unguarded), which refuses `$PWD/*` today and keeps it, so that row expects its rule.
# `"$PWD"/*` is pinned by the rm-var cases above, so it is not repeated here.
for _name, _command in (
    ("quoted $(pwd) before a glob", 'rm -rf "$(pwd)"/*'),
    ("unquoted $(pwd) before a glob", "rm -rf $(pwd)/*"),
):
    sh("looser-git-acts: delete: everything in the working folder, " + _name + ", is denied",
       _command, "deny", "destructive-delete", cwd=NOGIT)
sh("looser-git-acts: delete: everything in the working folder, unquoted $PWD before a glob, is denied",
   "rm -rf $PWD/*", "deny", "rm-var-unguarded", cwd=NOGIT)
for _command in ('rm -rf "$(pwd)"/build', "rm -rf $(pwd)/build", 'rm -rf "$PWD"/dist', "rm -rf $PWD/dist"):
    sh("looser-git-acts: delete: a named folder as " + _command + " is allowed", _command,
       "allow", cwd=NOGIT)
# FALSE ALARMS: the text of the command sits inside a quoted argument of another command
# (a note, a commit message, a grep pattern). The cmd.exe forms above are already read by token.
for _name, _command in (
    ("an echo that quotes the root form", 'echo "rm -rf /"'),
    ("an echo that quotes the home form", "echo 'rm -rf ~'"),
    ("a commit message that names the root form", VCS + " commit -m 'never run rm -rf / here'"),
    ("a grep for the root form", 'grep "rm -rf /" notes.md'),
):
    sh("delete: " + _name + " calls nothing", _command, "allow", cwd=NOGIT)
# Reading tokens must still see a delete that sits in a quoted argument of a shell that RUNS it, and
# behind a wrapper (`ssh host 'rm -rf /'` is not pinned).
for _name, _command in (
    ("bash -c", "bash -c 'rm -rf /'"),
    ("sh -c", 'sh -c "rm -rf ~"'),
    ("eval", 'eval "rm -rf /"'),
    ("sudo", "sudo rm -rf /"),
):
    sh("delete: the root form behind " + _name + " still denies", _command, "deny",
       "destructive-delete", cwd=NOGIT)
# A named folder stays allowed in every spelling the matches read.
for _name, _command in (
    ("a dot-slash folder", "rm -rf ./build"),
    ("a folder after --", "rm -rf -- build"),
    ("a folder, long flags", "rm --recursive --force build/"),
):
    sh("delete: " + _name + " is allowed", _command, "allow", cwd=NOGIT)
# THE SPLIT FLAGS IN QUOTED TEXT. `rm -r -f .` and `del -Recurse -Force C:/` in an echo are text, as
# `rm -rf .` already is. A shell that runs the same text still refuses it.
sh("delete: an echo of rm with split flags at the working folder calls nothing",
   'echo "rm -r -f ."', "allow", cwd=NOGIT)
sh("delete: an echo of the PowerShell delete at a drive root calls nothing",
   'echo "del -Recurse -Force C:/"', "allow", cwd=NOGIT)
sh("delete: sh -c of rm with split flags at the working folder still denies",
   'sh -c "rm -rf ."', "deny", "destructive-delete", cwd=NOGIT)
sh("delete: bash -c of rm with split flags at the working folder still denies",
   'bash -c "rm -r -f ."', "deny", "destructive-delete", cwd=NOGIT)
sh("delete: eval of rm at the working folder still denies",
   'eval "rm -rf ."', "deny", "destructive-delete", cwd=NOGIT)
sh("delete: pwsh -Command of a PowerShell delete at a drive root still denies",
   'pwsh -Command "Remove-Item -Recurse -Force C:/"', "deny", "destructive-delete", cwd=NOGIT)
sh("delete: pwsh -Command of a PowerShell delete at a drive root with no -Force denies",
   'pwsh -Command "Remove-Item -Recurse C:/"', "deny", "destructive-delete", cwd=NOGIT)
# THE SPLIT-FLAG DELETE IN A WRAPPER'S STRING. parallel, script -qc, watch and runuser each run their quoted
# text as a shell command, so `rm -r -f .` inside the quotes deletes the working folder, as bash -c's does.
for _name, _command in (
    ("parallel", 'parallel "rm -r -f ." ::: a'),
    ("script -qc", 'script -qc "rm -r -f ." /dev/null'),
    ("watch", 'watch "rm -r -f ."'),
    ("runuser -c", 'runuser -c "rm -r -f ." u'),
):
    sh("delete: the split-flag rm at the working folder behind " + _name + " denies", _command, "deny",
       "destructive-delete", cwd=NOGIT)
# A single-quoted substitution is text, as the echo of the split-flag rm above is. It runs nothing.
sh("delete: an echo of a single-quoted $(rm -r -f .) calls nothing",
   "echo '$(rm -r -f .)'", "allow", cwd=NOGIT)
# A LIVE SUBSTITUTION INSIDE DOUBLE QUOTES. `"$( )"` runs the command inside it, so a delete there is a
# command, not text. The echo cases above stay allowed, since their delete is not inside `$( )`. A `#`, a
# line break or a lone apostrophe around the substitution does not hide it.
sh("delete: a live $(rm -r -f .) inside double quotes denies",
   '''echo "$(rm -r -f .)"''', "deny", "destructive-delete", cwd=NOGIT)
sh("delete: a live $(Remove-Item -Recurse -Force C:/) inside double quotes denies",
   '''echo "$(Remove-Item -Recurse -Force C:/)"''', "deny", "destructive-delete", tool="PowerShell",
   cwd=NOGIT)
sh("delete: a live $(rm -r -f .) after a # inside double quotes denies",
   '''echo "# $(rm -r -f .)"''', "deny", "destructive-delete", cwd=NOGIT)
sh("delete: a live $(rm -r -f .) on a second line of a double quote denies",
   'echo "first line\n$(rm -r -f .)\nlast line"', "deny", "destructive-delete", cwd=NOGIT)
sh("delete: a live $(rm -r -f .) after a lone apostrophe denies",
   '''echo don't && echo "$(rm -r -f .)"''', "deny", "destructive-delete", cwd=NOGIT)
# THE INDEX-ONLY FORM. `git rm --cached` removes a path from the index and leaves the working folder
# alone, so `git rm -rf --cached .` deletes nothing on disk. The same words without `--cached` delete
# every file under the working folder, and a chained delete still denies.
sh("delete: git rm -rf --cached . touches the index only, and is allowed",
   VCS + " rm -rf --cached .", "allow", cwd=NOGIT)
sh("delete: git rm -r -f --cached . touches the index only, and is allowed",
   VCS + " rm -r -f --cached .", "allow", cwd=NOGIT)
sh("delete: git rm -rf . with no --cached still denies", VCS + " rm -rf .", "deny",
   "destructive-delete", cwd=NOGIT)
sh("delete: git rm -r -f . with no --cached still denies", VCS + " rm -r -f .", "deny",
   "destructive-delete", cwd=NOGIT)
sh("delete: git rm -rf --cached . chained with rm -rf . still denies",
   VCS + " rm -rf --cached . && rm -rf .", "deny", "destructive-delete", cwd=NOGIT)

# Each is a program that runs the real command: find -exec, su -c, a container exec, and flock.
for _name, _command in (
    ("behind find -exec", "find . -exec rm -rf / \\;"),
    ("behind su -c", "su -c 'rm -rf /'"),
    ("behind docker exec", "docker exec c rm -rf /"),
    ("behind flock", "flock F rm -rf /"),
):
    sh("delete: the root form " + _name + " denies", _command, "deny", "destructive-delete",
       cwd=NOGIT)

# `docker run --rm alpine` and `docker-compose exec web` have options or a hyphenated name
# ahead of the real command.
for _name, _command in (
    ("behind docker run with an option", "docker run --rm alpine rm -rf /"),
    ("behind docker-compose exec", "docker-compose exec web rm -rf /"),
):
    sh("delete: the root form " + _name + " denies", _command, "deny", "destructive-delete",
       cwd=NOGIT)
# A commit message that names the form deletes nothing wide.
sh("delete: a commit message that names the root form is no wide delete",
   VCS + ' commit -m "stop rm -rf / mistakes"', "allow", cwd=NOGIT)

# TWO WIDE-TARGET SETS DISAGREE. A segment shlex can parse is read by `_rm_args_wide`, against
# RM_WIDE_TARGET, which takes a trailing slash and a glob on a root or home. A segment it cannot
# parse (one lone quote) is read by RM_RAW, against WIDE_TARGET, which takes neither. So `rm -rf ~/`
# denies and `rm -rf ~/ 'x` allows: the same act, split by an apostrophe.
for _name, _command in (
    ("a trailing slash on the home directory, one lone quote", "rm -rf ~/ 'x"),
    ("a trailing slash on the home directory, a lone apostrophe in text", "rm -rf ~/ it's"),
    ("everything under the home directory, a lone apostrophe in text", "rm -rf ~/* it's"),
    ("everything under the root, a lone apostrophe in text", "rm -rf /* it's"),
    ("the working directory as ./, a lone apostrophe in text", "rm -rf ./ it's"),
):
    sh("delete: " + _name, _command, "deny", "destructive-delete", cwd=NOGIT)

# SCANNER PINS (rule building-scanner-respects-strings) for the fallback that reads a segment shlex
# cannot parse as raw text (guard_push_delete.py, RM_RAW). The same three constructs as the stream
# family: a comment opener inside quotes, a quoted string over several lines, and a lone apostrophe
# in plain text. DENY: each construct sits beside a real delete, and none may hide it.
for _name, _command in (
    ("a # inside quotes ahead of it", 'echo "a # b"; rm -rf /'),
    ("a # inside quotes and a lone apostrophe ahead of it", 'echo "# x" it\'s; rm -rf /'),
    ("a // inside quotes ahead of it", 'echo "a // b"; rm -rf /'),
    ("a multi-line quote ahead of it", 'echo "first line\nsecond line"\nrm -rf /'),
    ("a multi-line quote and a lone apostrophe ahead of it", 'echo "a\nb" it\'s\nrm -rf /'),
    ("a lone apostrophe ahead of it", "echo don't && rm -rf /"),
    ("a lone apostrophe in a trailing comment", "rm -rf / # don't"),
):
    sh("delete: the root form behind " + _name + " denies", _command, "deny",
       "destructive-delete", cwd=NOGIT)
# ALLOW: the same constructs around text that deletes nothing wide.
for _name, _command in (
    ("a single-quoted echo of the root form", "echo 'rm -rf /'"),
    ("a # inside quotes", 'echo "# rm -rf /"'),
    ("a multi-line quote", 'echo "first line\nrm -rf /\nlast line"'),
    ("a lone apostrophe in a trailing comment", "rm -rf build # don't"),
):
    sh("delete: scanner: " + _name + " is no wide delete", _command, "allow", cwd=NOGIT)

# A RECURSIVE DELETE OF `.`, `..`, THE WORKING FOLDER OR A PARENT OF IT (decision rm-path-wrapper,
# the rm shim on PATH refuses these calls; the guard must refuse the same ones on every platform
# and in both shells).
# Recursion alone is enough: no force flag is needed. A named folder, a sibling of the working folder
# and a call that is not recursive stay allowed. Every name below carries `rm-parent`, so
# MUTATE_ONLY=rm-parent runs this block and nothing else. The existing `delete:` cases pin the rest.
# Where a folder change comes first (`cd`, `pushd`, `Set-Location`, `sl`, `chdir`) the reason must
# also say how to write the delete so it passes.
RM_PARENT_HINT = {"Bash": "rm -rf build", "PowerShell": "Remove-Item -Recurse build"}


def rm_parent(name, command, expected="deny", **kw):
    """One case of the block: a deny names destructive-delete, an allow names nothing."""
    sh("rm-parent: " + name.replace("\n", " ; "), command, expected,
       "destructive-delete" if expected == "deny" else None, cwd=NOGIT, **kw)


# The flag spellings, on `.` and `..`: one cluster, split flags, a capital R, a verbose letter, the
# long names, recursion with no force flag at all, and the flags ended by `--`.
for _flags in ("-rf", "-r -f", "-fr", "-Rf", "-rfv", "-r", "-R", "--recursive",
               "--recursive --force", "-rf --"):
    for _target in (".", ".."):
        rm_parent("rm %s %s" % (_flags, _target), "rm %s %s" % (_flags, _target))
# The target spellings, on a recursive call with no force flag.
for _target in ("./", "../", "../..", "./..", "../../..", ".\\", "..\\", "..\\..", '"."', '".."',
                "'..'", '"../.."'):
    rm_parent("rm -r " + _target, "rm -r " + _target)
# A root, a home and the glob of a parent, recursive with no force flag.
for _command in ("rm -r /", "rm -R /", "rm --recursive /", "rm -r ~", "rm -r ~/", "rm -r ~/*",
                 "rm -r ../*", "rm -r ../../*"):
    rm_parent(_command, _command)
# A segment shlex cannot parse (one lone quote) is read as raw text: the same act must still deny.
for _command in ("rm -rf .. it's", "rm -rf ../ it's", "rm -r .. it's", "rm -r ./ it's"):
    rm_parent("a lone apostrophe: " + _command, _command)

# PowerShell: the verbs and their abbreviated flags, with and without -Force, positional.
for _verb in ("Remove-Item -Recurse", "Remove-Item -r", "Remove-Item -Rec", "ri -Recurse",
              "del -Recurse", "Remove-Item -Recurse -Force"):
    for _target in (".", "..", ".\\", "..\\", "'..'"):
        rm_parent("PowerShell %s %s" % (_verb, _target), "%s %s" % (_verb, _target),
                  tool="PowerShell")
# PowerShell: the target named by -Path or -LiteralPath, ahead of the flag or after it.
for _form in ("Remove-Item -Path %s -Recurse", "Remove-Item -LiteralPath %s -Recurse",
              "Remove-Item %s -Recurse", "Remove-Item -Recurse -Path %s",
              "Remove-Item -Recurse -LiteralPath %s -Force", "ri -Path %s -r",
              "del -LiteralPath %s -Recurse"):
    for _target in (".", ".."):
        rm_parent("PowerShell " + _form % _target, _form % _target, tool="PowerShell")

# cmd.exe: `rd`, `rmdir`, `del` and `erase` read `/s` as the recursive flag, bare or after `cmd /c`.
for _tool in ("Bash", "PowerShell"):
    for _command in ("rmdir /s .", "rmdir /s /q ..", "rd /s /q ..", "rd /s ..\\..", "RD /S /Q ..",
                     "cmd /c rd /s /q ..", "cmd.exe /c rmdir /s /q ."):
        rm_parent("%s %s" % (_tool, _command), _command, tool=_tool)

# A folder change earlier in the same command is not tracked: `.` and a relative parent are refused
# after it, and the reason carries a rewrite hint.
for _tool, _command in (
    ("Bash", "cd .. && rm -rf ."),
    ("Bash", "cd build && rm -rf ."),
    ("Bash", "cd build && rm -r ."),
    ("Bash", "cd build && rm --recursive .."),
    ("Bash", "cd build; rm -rf ../.."),
    ("Bash", "pushd build && rm -rf ."),
    ("Bash", "cd build\nrm -r ."),
    ("PowerShell", "cd build; Remove-Item -Recurse ."),
    ("PowerShell", "Set-Location build; Remove-Item -Recurse ."),
    ("PowerShell", "sl build; Remove-Item -Recurse .."),
    ("PowerShell", "chdir build; Remove-Item -Recurse ."),
    ("PowerShell", "pushd build; Remove-Item -Recurse -Force ."),
    ("PowerShell", "Set-Location build\nri -r .."),
):
    rm_parent("a folder change ahead of it: " + _command, _command, tool=_tool,
              carries=RM_PARENT_HINT[_tool])
# Scanner pins (building-scanner-respects-strings) for the same reads: a comment opener inside
# quotes, a multi-line quote and a lone apostrophe ahead of the delete must hide nothing.
for _name, _command in (
    ("a # inside quotes ahead of it", 'echo "a # b"; rm -r ..'),
    ("a // inside quotes ahead of it", 'echo "a // b"; rm -r ..'),
    ("a multi-line quote ahead of it", 'echo "first line\nsecond line"\nrm -r ..'),
    ("a lone apostrophe ahead of it", "echo don't && rm -r .."),
    ("a lone apostrophe in a trailing comment", "rm -r .. # don't"),
):
    rm_parent("the delete behind " + _name, _command)
for _name, _command in (
    ("a # inside quotes", 'echo "a # b"; cd build && rm -r .'),
    ("a // inside quotes", 'echo "a // b"; cd build && rm -r .'),
    ("a multi-line quote", 'echo "first line\nsecond line"\ncd build\nrm -r .'),
):
    rm_parent("the folder change behind " + _name, _command, carries=RM_PARENT_HINT["Bash"])

# The working folder and its parents by ABSOLUTE path, in every spelling Windows reads: `C:/x`,
# `C:\x` and Git Bash `/c/x`. NOGIT is the working folder of each case, and ROOT is its parent.
_CWD = os.path.join(os.path.realpath(ROOT), "nogit")
_PARENT = os.path.realpath(ROOT)
_GRAND = os.path.dirname(_PARENT)


def _spellings(path):
    """The (kind, text) spellings of one folder that this platform reads."""
    if os.name != "nt":
        return [("posix", path)]
    forward = path.replace("\\", "/")
    return [("C:/", forward), ("C:\\", path), ("/c/", "/" + forward[0].lower() + forward[2:])]


for _label, _folder in (("the working folder", _CWD), ("its parent", _PARENT)):
    for _kind, _text in _spellings(_folder):
        rm_parent("Bash rm -r %s as %s" % (_label, _kind), 'rm -r "%s"' % _text)
        if _kind != "/c/":   # `/c/x` is a Git Bash path: PowerShell does not read it
            rm_parent("PowerShell Remove-Item -Recurse %s as %s" % (_label, _kind),
                      'Remove-Item -Recurse "%s"' % _text, tool="PowerShell")
for _kind, _text in _spellings(_GRAND):
    rm_parent("Bash rm -rf its grandparent as " + _kind, 'rm -rf "%s"' % _text)
for _kind, _text in _spellings(_PARENT)[:1]:
    rm_parent("Bash rm -r its parent with a trailing slash as " + _kind, 'rm -r "%s/"' % _text)
rm_parent("rm -r the working folder named through its parent", "rm -r ../nogit")
if os.name != "nt":
    skip_case("rm-parent: the C:/, C:\\ and /c/ spellings of the working folder and its parents",
              "a drive-letter spelling names no folder on this platform, so only the plain path runs")

# ALLOWED: a named folder, a sibling that is not a parent, a folder whose name merely starts with a
# dot or the working folder's name, a call that is not recursive, and a delete that follows a folder
# change but names a folder.
for _name, _command in (
    ("a dot-slash folder, recursive with no force flag", "rm -r ./build"),
    ("a sibling folder", "rm -rf ../sibling"),
    ("a sibling folder, recursive with no force flag", "rm -r ../sibling"),
    ("a folder whose name starts with two dots", "rm -rf ..cache"),
    ("a folder whose name starts with a dot", "rm -rf .cache"),
    ("rm of the working folder, not recursive", "rm ."),
    ("rm of the parent, not recursive", "rm .."),
    ("rm -f of the working folder, not recursive", "rm -f ."),
    ("rd of the parent, no /s", "rd .."),
    ("rmdir /q of the parent, no /s", "rmdir /q .."),
    ("rd /s /q of a sibling", "rd /s /q ..\\sibling"),
    ("a folder named after a folder change, by absolute path", "cd build && rm -rf /tmp/build/out"),
    ("a folder named after pushd", "pushd build && rm -r out"),
    ("a folder named after a change to the parent, by absolute path", "cd .. && rm -rf /tmp/build"),
    ("a child of the working folder by absolute path", 'rm -rf "%s/build"' % _CWD),
    ("a sibling whose name starts with the working folder's name", 'rm -rf "%s2"' % _CWD),
    ("a sibling of the working folder by absolute path", 'rm -rf "%s/sibling"' % _PARENT),
):
    rm_parent(_name, _command, "allow")
for _name, _command in (
    ("Remove-Item -Recurse of a dot-slash folder", "Remove-Item -Recurse ./build"),
    ("Remove-Item -Recurse of a sibling folder", "Remove-Item -Recurse ..\\sibling"),
    ("Remove-Item of the working folder, not recursive", "Remove-Item ."),
    ("Remove-Item -Force of the parent, not recursive", "Remove-Item -Force .."),
    ("a folder named after Set-Location", "Set-Location build; Remove-Item -Recurse out"),
    ("a folder named after sl", "sl build; Remove-Item -Recurse -Force ./out"),
    ("a child of the working folder by absolute path",
     'Remove-Item -Recurse "%s\\build"' % _CWD),
):
    rm_parent("PowerShell " + _name, _command, "allow", tool="PowerShell")
# Text that only names a delete calls nothing.
for _name, _command in (
    ("a single-quoted echo", "echo 'rm -r ..'"),
    ("a # inside quotes", 'echo "# rm -r .."'),
    ("a multi-line quote", 'echo "first line\nrm -r ..\nlast line"'),
    ("a folder change named in a quoted echo", 'echo "cd .. && rm -r ." && rm -rf ./build'),
    ("a grep pattern", 'grep "rm -rf .." notes.md'),
    ("a commit message", VCS + " commit -m 'never run rm -r . here'"),
    ("a lone apostrophe in a trailing comment", "rm -r build # don't"),
):
    rm_parent("allows " + _name, _command, "allow")
rm_parent("PowerShell allows a quoted Write-Host", "Write-Host 'Remove-Item -Recurse ..'", "allow",
          tool="PowerShell")

# FALSE ALARMS. A delete named inside a double-quoted message, an echo or a search pattern is text.
# Main allows each of these (no `-Force`, so no old pattern read them), and so must this rule. The
# PowerShell verbs are read from raw text with no regard for quotes, so a quoted `Remove-Item
# -Recurse .`, a quoted `ri -r .` or a quoted word `del` ahead of `-r .` looks like a call. The `rm`
# form is read by tokens unless shlex cannot parse the segment, and a lone apostrophe in an earlier
# step makes the rest of the line unparseable: its raw read must still skip a quoted message, and
# still deny a bare `rm -rf .. it's` (cases above).
for _tool in ("Bash", "PowerShell"):
    for _name, _command in (
        ("a commit message naming Remove-Item -Recurse .",
         VCS + ' commit -m "Never run Remove-Item -Recurse . here"'),
        ("an echo of Remove-Item -Recurse ~", 'echo "Remove-Item -Recurse ~"'),
        ("a grep for del with -r over .", 'grep "del" -r .'),
    ):
        rm_parent("%s allows %s" % (_tool, _name), _command, "allow", tool=_tool)
rm_parent("PowerShell allows a Write-Host of Remove-Item -Recurse .",
          'Write-Host "Remove-Item -Recurse ."', "allow", tool="PowerShell")
rm_parent("Bash allows an echo of ri -r .", 'echo "ri -r ."', "allow")
for _name, _command in (
    ("a commit message naming rm -rf .. behind a lone apostrophe",
     "echo don't && " + VCS + ' commit -m "Never run rm -rf .. here"'),
    ("a commit message naming rm -rf .. behind a lone apostrophe and a semicolon",
     "echo don't; " + VCS + ' commit -m "Never run rm -rf .. here"'),
    ("a commit message naming rm -r . behind a lone apostrophe",
     "echo don't && " + VCS + ' commit -m "Never run rm -r . here"'),
    ("a double-quoted echo of rm -rf .. behind a lone apostrophe",
     "echo don't && echo \"rm -rf ..\""),
    ("a single-quoted echo of rm -rf .. behind a lone apostrophe",
     "echo don't && echo 'rm -rf ..'"),
):
    rm_parent("Bash allows " + _name, _command, "allow")

# SAFETY HOLES. A delete inside `( )`, `$( )` or backticks must deny like the bare one: the closing
# parenthesis is no part of the target. `rm -rf /` inside a group is the same safety hole on a root.
for _command in ("(rm -rf .)", "(rm -rf ..)", "x=$(rm -rf .)", "echo $(rm -rf .)",
                 "echo `rm -rf .`", "(rm -rf /)", "(rm -rf ~)", "x=$(rm -rf /)",
                 "(cd build && rm -rf .)"):
    rm_parent("Bash inside a group or substitution: " + _command, _command)
for _command in ("(Remove-Item -Recurse -Force .)", "(Remove-Item -Recurse .)",
                 "(Remove-Item -Recurse ..)", "$(Remove-Item -Recurse -Force .)",
                 "$x = (Remove-Item -Recurse -Force ..)", "(Remove-Item -Recurse -Force /)",
                 "(Remove-Item -Recurse -Force ~)", "(ri -r .)"):
    rm_parent("PowerShell inside a group or substitution: " + _command, _command,
              tool="PowerShell")
# A space inside the group changes nothing, so it denies like the bare form. A group around a named
# folder deletes nothing wide, so it allows.
rm_parent("Bash inside a group with spaces: ( rm -rf . )", "( rm -rf . )")
rm_parent("Bash allows a group around a named folder", "(rm -rf build)", "allow")
rm_parent("Bash allows a substitution around a named folder", "x=$(rm -rf ./build)", "allow")
rm_parent("PowerShell allows a group around a named folder", "(Remove-Item -Recurse build)", "allow",
          tool="PowerShell")

# A QUOTED TARGET. The quotes are no part of the name: `"."` is the working folder, and `'~'` is the
# home folder to PowerShell. Bash reads `'~'` as a folder named `~`; the guard keeps the wider
# reading, as it does for `'..'` above.
for _target in ('"."', "'.'", '"~"', "'~'"):
    rm_parent("Bash rm -rf " + _target, "rm -rf " + _target)
    for _form in ("Remove-Item -Recurse %s", "Remove-Item -Recurse -Force %s",
                  "Remove-Item -Path %s -Recurse"):
        rm_parent("PowerShell " + _form % _target, _form % _target, tool="PowerShell")

# AN ESCAPED QUOTE IS NO OPEN QUOTE. A backslash before a quote (`it\'s`, `a\"b`, `$'it\'s'`) makes
# the quote plain text to the shell, so it must not hide a wide delete that follows it. Main denies
# each of these.
for _prefix in ("echo it\\'s", 'echo "a\\"b"', "echo $'it\\'s'"):
    for _target in ("/", "~", ".", ".."):
        rm_parent("an escaped quote ahead of rm -rf %s: %s" % (_target, _prefix),
                  "%s && rm -rf %s" % (_prefix, _target))

# A `git rm` IS NOT `rm`. It drops tracked files from the index, so `-r .` there names no wide
# delete. Main allows each of these. A real `rm -rf .` after a `git` command is still refused.
for _command in (VCS + " rm -r --cached .", VCS + " rm -r .", VCS + " rm -r --cached .."):
    rm_parent("allows " + _command, _command, "allow")
rm_parent("a real rm -rf . after a git command", VCS + " status && rm -rf .")

# KNOWN OPEN. A shell operator glued to the target (`..&`, `..>x`, `.>/dev/null`) leaves the target
# unread by both the token read and the raw read. These cases record today's verdict and are not a
# ruling that it is right: when a fix makes one deny, re-point it here.
for _command in ("rm -rf ..&", "rm -rf ..>x", "rm -rf .>/dev/null"):
    rm_parent("known open: " + _command, _command, "allow")


# =========================================================================== 3b. linked node_modules
# q_max links a worktree's node_modules to main's install with a Windows junction. Through that link a
# hand-run `npm ci` empties main's node_modules (measured on npm 12.0.2). The guard refuses a
# dependency install, and a recursive delete inside node_modules, when the working folder holds
# node_modules as a link. A real folder, or no folder, is judged as it always was.

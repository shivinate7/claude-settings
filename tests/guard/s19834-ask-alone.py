# section 19834
FAMILY = "ask-alone"
#
# A command the guard would ASK on, chained with other commands (`&&`, `||`, `;`, `|`, newline), denies to
# the agent, and the remedy says to run that command alone or drop it (CHAIN_ASK and ALONE, near sh()).
# A lone ask command still asks. A deny anywhere in the command still wins. The ask commands, one case
# each below, are the four shell routes that print an "ask" (guard.py, judge_shell):
#   rule 1  `git worktree prune`, with a stale record to drop        (WORKTREE_PRUNE_ASK_REASON)
#   rule 1  a discard in a linked worktree: reset --hard, restore .  (TREE_ASK_REASON)
#   rule 4  a forced push that may reach the default branch          (PUSH_ASK_REASON)
#   rule 8  a shell write of a settings file that names the cap key  (CAP_ASK_REASON)
# The fifth route, rule 8 on a Write/Edit/MultiEdit call, holds one tool call and no chain, so it has
# no chained form. The re-pointed cases above (named "denies as a chained ask command") cover the
# cd, export, PowerShell, pipe and `-C` shapes of the same rules.

PRUNE = VCS + " worktree prune"


def chained_prune(name, command, **kw):
    """A chained prune: a deny that names the prune command and says to run it alone."""
    chained_ask(name, command, cwd=WTPRUNE, carries=("worktree prune",), **kw)


# (a) THE INCIDENT, then every chain operator, a command before the prune, the PowerShell tool, a
# agent, and two ask commands in one command.
chained_prune("ask-alone: the incident, prune then worktree add then grep, denies and names the prune",
              PRUNE + " && " + VCS + ' worktree add -b x "$TEMP/wt-x" origin/y && grep -c x README.md')
for _label, _tail in (("||", " || echo x"), (";", "; echo x"),
                      ("a pipe", " | cat"), ("a newline", "\necho x")):
    chained_prune("ask-alone: a prune joined to another command by %s denies" % _label, PRUNE + _tail)
# An output tail is no second command (ask-commands-run-alone): the echo after `&&` is the named tail form.
sh("ask-alone: a prune with an && echo tail asks, the echo is no second command", PRUNE + " && echo x",
   "ask", "shared-tree", cwd=WTPRUNE, lacks=(CHAIN_ASK,))
chained_prune("ask-alone: a command before the prune denies", "echo x && " + PRUNE)
chained_prune("ask-alone: a line before the prune denies", "echo x\n" + PRUNE)
chained_prune("ask-alone: two prunes in one command deny", PRUNE + " && " + PRUNE)
chained_prune("ask-alone: a prune chained in the PowerShell tool denies", PRUNE + "; Write-Output x",
              tool="PowerShell")
chained_prune("ask-alone: an agent's chained prune denies the same way", PRUNE + "; echo x",
              agent_id="agent-ask-alone")

# STRINGS AND COMMENTS (building-scanner-respects-strings). The count of commands comes from the shell's
# own quoting: a comment opener inside a string hides no command, a newline inside a string adds none,
# a lone quote in a comment or a heredoc body swallows none, and a separator inside a string,
# a comment or a heredoc body is no chain.
chained_prune("ask-alone: a # inside a quoted argument does not hide the command after it",
              PRUNE + ' --expire "a # b"; echo x')
chained_prune("ask-alone: a /* inside a quoted argument does not hide the command after it",
              PRUNE + " --expire '/* x'; echo x")
chained_prune("ask-alone: a // inside a quoted argument before the prune does not hide it",
              "echo 'http://x' && " + PRUNE)
chained_prune("ask-alone: a newline inside a quoted argument adds no command, the command after it does",
              PRUNE + ' --expire "a\nb"; echo x')
chained_prune("ask-alone: a heredoc with a lone apostrophe in its body, after the prune, denies",
              PRUNE + "\ncat <<'EOF'\ndon't\nEOF")

# (b) A LONE ASK COMMAND STILL ASKS, whatever its text holds: a trailing newline, a comment line, a
# trailing comment with && and a lone quote, a flag, a quoted flag value full of separators and
# comment openers, a multi-line quoted flag value, and heredoc bodies with separators or a lone quote.
sh("ask-alone: a prune alone in the PowerShell tool still asks", PRUNE, "ask", "shared-tree",
   tool="PowerShell", cwd=WTPRUNE)
sh("ask-alone: a prune with a trailing newline is alone, so it asks", PRUNE + "\n", "ask",
   "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a prune under a comment line is alone, so it asks",
   "# drop the stale record\n" + PRUNE, "ask", "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a prune with a trailing comment holding && and a lone quote is alone, so it asks",
   PRUNE + " # it's && echo x", "ask", "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a prune with a flag is alone, so it asks", PRUNE + " --expire 2.days", "ask",
   "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a quoted flag value holding every separator and comment opener is no chain",
   PRUNE + ' --expire "a && b; c || d | e # f // g /* h"', "ask", "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a quoted flag value holding a newline is no chain",
   PRUNE + ' --expire "1.day\n2.days"', "ask", "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a heredoc body holding && and ; is no chain",
   PRUNE + " <<'EOF'\na && b; c\nEOF", "ask", "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a heredoc body holding a lone apostrophe is no chain",
   PRUNE + " <<'EOF'\ndon't && stop\nEOF", "ask", "shared-tree", cwd=WTPRUNE)

# (c) THE OTHER ASK COMMANDS, each alone (still asks) and chained with an echo (denies, except the named
# `&& echo done` tail, which asks: ask-commands-run-alone). The reason
# names the command by its own text or by the rule that asked for it, and says to run it alone.
sh("ask-alone: a whole-tree restore alone in a worktree still asks, and names the -C form",
   VCS + " restore .", "ask", "shared-tree", cwd=GITWT, carries="git -C <lane> restore <file>")
sh("ask-alone: a hard reset in a worktree with an && echo done tail asks",
   VCS + " reset --hard && echo done", "ask", "shared-tree", cwd=GITWT, lacks=(CHAIN_ASK,))
sh("ask-alone: a forced push to the default branch with an && echo done tail asks",
   VCS + " push --force origin HEAD:main && echo done", "ask", "force-push", cwd=PUSHFEAT,
   lacks=(CHAIN_ASK,))
CHAIN_CAP_WRITE = "printf '%s' '" + cap_settings(compact=True) + "' > settings.local.json"
sh("ask-alone: a cap write alone to a settings file still asks", CHAIN_CAP_WRITE, "ask",
   "agent-model-cap", cwd=PROJ)
chained_ask("ask-alone: a cap write to a settings file chained after an echo denies",
            "echo done && " + CHAIN_CAP_WRITE, cwd=PROJ,
            carries=((CAP_KEY, "settings.local.json", "agent-model-cap"),))

# (d) NO ASK COMMAND, NO DENY. A chain that holds no ask command keeps its old answer, so the new deny
# cannot turn an ordinary chain, a read, or a noted discard into a refusal.
sh("ask-alone: a dry-run prune chained with an echo allows", PRUNE + " -n && echo x", "allow",
   cwd=WTPRUNE)
sh("ask-alone: a prune with nothing to prune, chained with an echo, allows", PRUNE + " && echo x",
   "allow", cwd=WTMAIN)
sh("ask-alone: a discard in an agent's own worktree is noted, not asked, so a chain allows",
   VCS + " reset --hard && echo done", "allow", cwd=AGENTWT)
sh("ask-alone: a lease push off the default branch, chained with an echo, allows",
   VCS + " push --force-with-lease --force-if-includes && echo x", "allow", cwd=PUSHFEAT)
sh("ask-alone: a settings write that names neither cap variable, chained, allows",
   "echo x && printf '%s' '" + json.dumps({"env": {"TZ": "UTC"}}) + "' > settings.local.json",
   "allow", cwd=PROJ)
sh("ask-alone: a chain of git reads in a worktree allows",
   VCS + " status && " + VCS + " diff --stat", "allow", cwd=GITWT)

# A forced push in a heredoc body is text, even when the file it writes is later formatted by npx. The formatter
# reads the file and runs nothing in it, so the chain holds no live ask command.
sh("ask-alone: a heredoc body holding a forced push, written to a file npx formats, chained, allows",
   "cat > notes.md <<'EOF'\n" + VCS + " push --force origin main\nEOF\nnpx prettier --write notes.md",
   "allow", cwd=NOGIT)

# (e) A DENY ANYWHERE STILL WINS, in either order: a deny that stands after the ask in the guard's own
# rule order (kill, env file, a stash push) still prints. The printed reason is the deny rule's own,
# and never the ask-alone reason.


def deny_beats(name, command, rule, **kw):
    sh(name, command, "deny", rule, lacks=(CHAIN_ASK,), **kw)


deny_beats("ask-alone: a kill after the prune still denies as a kill",
           PRUNE + " && pkill -f node", "machine-wide-kill", cwd=WTPRUNE)
deny_beats("ask-alone: a kill before the prune still denies as a kill",
           "pkill -f node && " + PRUNE, "machine-wide-kill", cwd=WTPRUNE)
deny_beats("ask-alone: an env file read before the prune still denies as an env file",
           "cat " + ENV + " && " + PRUNE, "env-file", cwd=WTPRUNE)
deny_beats("ask-alone: an env file read after a forced push ask still denies as an env file",
           VCS + " push --force origin HEAD:main && cat " + ENV, "env-file", cwd=PUSHFEAT)
deny_beats("ask-alone: a stash push after a hard reset in a worktree denies as a stash push",
           VCS + " reset --hard && " + VCS + " stash push -u -m lane", "shared-tree", cwd=GITWT,
           carries="stash stack")
deny_beats("ask-alone: a stash push before a hard reset in a worktree denies as a stash push",
           VCS + " stash push -u -m lane && " + VCS + " reset --hard", "shared-tree", cwd=GITWT,
           carries="stash stack")
deny_beats("ask-alone: a kill before a cap write still denies as a kill",
           "pkill -f node && " + CHAIN_CAP_WRITE, "machine-wide-kill", cwd=PROJ)

# (f) A SINGLE `&` IS A CHAIN, AND A COMMAND HIDDEN IN AN INLINE SCRIPT, A COMMAND SUBSTITUTION, A LOOP
# OR A PIPE TO Out-Null STILL COUNTS. W is the cap write with no quote in it, so it
# nests inside `bash -c "..."`, `$( )` and a loop: `echo <key>=<value> > settings.local.json`. A
# redirect that holds a `&` (`&>`, `>&`) is one command, never a chain, so W with either still asks.
CAP_PLAIN = "echo " + CAP_KEY + "=" + OPUS + " > settings.local.json"
CAP_STEP = (("agent-model-cap", "settings.local.json"),)

sh("ask-alone: W alone still asks", CAP_PLAIN, "ask", "agent-model-cap", cwd=PROJ)
sh("ask-alone: W with an &> redirect is one command, so it asks", CAP_PLAIN + " &> log", "ask",
   "agent-model-cap", cwd=PROJ)
sh("ask-alone: W with a >& redirect is one command, so it asks", CAP_PLAIN + " >& log", "ask",
   "agent-model-cap", cwd=PROJ)
chained_ask("ask-alone: W sent to the background, then echo $! to a file, denies",
            CAP_PLAIN + " & echo $! > pid.txt", cwd=PROJ, carries=CAP_STEP)
chained_ask("ask-alone: W sent to the background, then P=$!, denies",
            CAP_PLAIN + " & P=$!", cwd=PROJ, carries=CAP_STEP)
chained_ask("ask-alone: W after echo inside bash -c with double quotes denies",
            'bash -c "echo hi; ' + CAP_PLAIN + '"', cwd=PROJ, carries=CAP_STEP)
chained_ask("ask-alone: W after echo inside bash -c with single quotes denies",
            "bash -c 'echo hi; " + CAP_PLAIN + "'", cwd=PROJ, carries=CAP_STEP)
chained_ask("ask-alone: W inside a command substitution, after another command, denies",
            "echo hi; echo $( " + CAP_PLAIN + " )", cwd=PROJ, carries=CAP_STEP)
chained_ask("ask-alone: a for loop holding W and another command denies",
            "for f in a b; do " + CAP_PLAIN + "; echo $f; done", cwd=PROJ, carries=CAP_STEP)
sh("ask-alone: W piped to Out-Null in the PowerShell tool asks",
   CAP_PLAIN + " | Out-Null", "ask", "agent-model-cap", tool="PowerShell", cwd=PROJ,
   lacks=(CHAIN_ASK,))

# (g) A CHAIN HIDDEN IN ANOTHER INTERPRETER'S SCRIPT. Each wrapper runs its argument
# as a script, so an echo and an ask command inside it are a chain and deny. `bash -o pipefail -c` hides
# its script behind a flag, and `eval` is no wrapper at all. The lone forms, with no echo, must still
# ask: the wrapper's own command is counted once, never twice.
NESTED_FORMS = (
    ("pwsh -Command", 'pwsh -Command "%s"', "; "),
    ("powershell -c", 'powershell -c "%s"', "; "),
    ("cmd /c with single &", 'cmd /c "%s"', " & "),
    ("cmd /c with double &&", 'cmd /c "%s"', " && "),
    ("iex", 'iex "%s"', "; "),
    ("env -S", "env -S '%s'", "; "),
    ("bash -o pipefail -c", 'bash -o pipefail -c "%s"', "; "),
    ("eval", 'eval "%s"', "; "),
)
for _label, _form, _sep in NESTED_FORMS:
    chained_ask("ask-alone: an ask command after echo inside %s denies" % _label,
                _form % ("echo hi" + _sep + CAP_PLAIN), cwd=PROJ, carries=CAP_STEP)
    sh("ask-alone: an ask command alone inside %s still asks" % _label, _form % CAP_PLAIN,
       "ask", "agent-model-cap", cwd=PROJ)

# (h) AN EMPTY OR COMMENT-ONLY SCRIPT ADDS NO COMMAND. One ask command with an empty `bash -c` script is one
# command, so it asks. A script that holds no command must never lower the count below the ask command's own.
sh("ask-alone: an ask command then an empty bash -c script is one command, so it asks",
   CAP_PLAIN + '; bash -c " "', "ask", "agent-model-cap", cwd=PROJ)
sh("ask-alone: an ask command then a bash -c script of one comment is one command, so it asks",
   CAP_PLAIN + '; bash -c "# x"', "ask", "agent-model-cap", cwd=PROJ)

# (i) A SINGLE `&` INSIDE QUOTES IS NO CHAIN. An ampersand in a quoted cap value, in a quoted URL beside
# the cap write, or beside an escaped double quote is part of one word: each cap write stays one command
# and asks.
sh("ask-alone: a single & inside a quoted cap value is one command, so it asks",
   'echo "' + CAP_KEY + '=' + OPUS + ' a & b" > settings.local.json', "ask", "agent-model-cap",
   cwd=PROJ)
sh("ask-alone: a single & inside a quoted URL beside the cap write is one command, so it asks",
   "echo " + CAP_KEY + "=" + OPUS + " 'https://x.test/?a=1&b=2' > settings.local.json",
   "ask", "agent-model-cap", cwd=PROJ)
sh("ask-alone: an escaped double quote around a single & is one command, so it asks",
   'echo "' + CAP_KEY + '=v \\" & \\"" > settings.local.json', "ask", "agent-model-cap", cwd=PROJ)

# (j) THE NAMED HARMLESS FORMS (decision ask-commands-run-alone). Before the ask
# command: a move into a folder (`cd X &&`, PowerShell `Set-Location X;`) or an export (`export NAME=value
# &&`). After it: an output tail (`| tail -N`, `| head -N`, `| Out-Null`, `&& echo done`, PowerShell
# `; Write-Host done`). One case per form. The ask commands rotate through the four kinds, and each is
# built from pieces, so no ask text sits on a shell command line.
ASK_PRUNE = PRUNE
ASK_DISCARD = VCS + " reset --hard"
ASK_LEASE = VCS + " push " + LE + "origin HEAD:main"
ASK_CAP = CAP_PLAIN


def asks_alone(name, command, rule, **kw):
    """One case: `command` holds a harmless lead or tail around one ask command, so it asks, once."""
    sh(name, command, "ask", rule, lacks=(CHAIN_ASK,), **kw)


# The leading forms: cd, Set-Location, export.
asks_alone("ask-alone: a cd into the prune's checkout, then the prune, asks",
           "cd " + slash(WTPRUNE) + " && " + ASK_PRUNE, "shared-tree", cwd=NOGIT)
# cwd is the lane itself: the guard reads only a `cd` as the run directory, so a Set-Location into
# another folder from a plain folder is judged where the shell stands (a separate gap, reported).
asks_alone("ask-alone: a Set-Location to the lane's own folder, then the reset, in the PowerShell tool asks",
           "Set-Location " + slash(GITWT) + "; " + ASK_DISCARD, "shared-tree", tool="PowerShell",
           cwd=GITWT)
asks_alone("ask-alone: an export before the cap write asks",
           "export LANE_NOTE=ask && " + ASK_CAP, "agent-model-cap", cwd=PROJ)
# A Windows path is no escaped quote, so its backslashes do not make the lead a command
# (ask-commands-run-alone). The paths are raw strings, so `\U` and `\x` reach the guard as typed.
asks_alone("ask-alone: a cd to a Windows path, then the cap write, asks",
           r"cd C:\Users\x\repo && " + ASK_CAP, "agent-model-cap", cwd=PROJ)
asks_alone("ask-alone: a PowerShell Set-Location to a Windows path, then the cap write, asks",
           r"Set-Location C:\Users\x\repo; " + ASK_CAP, "agent-model-cap", tool="PowerShell", cwd=PROJ)

# The output tails: tail, head, Out-Null, && echo done, and PowerShell ; Write-Host done.
asks_alone("ask-alone: the lease push to the default branch, piped to tail, asks",
           ASK_LEASE + " | tail -5", "force-push", cwd=PUSHFEAT)
asks_alone("ask-alone: the reset in a worktree, piped to head, asks",
           ASK_DISCARD + " | head -3", "shared-tree", cwd=GITWT)
asks_alone("ask-alone: the prune piped to Out-Null in the PowerShell tool asks",
           ASK_PRUNE + " | Out-Null", "shared-tree", tool="PowerShell", cwd=WTPRUNE)
asks_alone("ask-alone: the cap write with an && echo done tail asks",
           ASK_CAP + " && echo done", "agent-model-cap", cwd=PROJ)
asks_alone("ask-alone: the lease push to the default branch, then Write-Host done in the PowerShell tool asks",
           ASK_LEASE + "; Write-Host done", "force-push", tool="PowerShell", cwd=PUSHFEAT)

# Both harmless forms in one shell call still add no command.
asks_alone("ask-alone: a cd, the prune, then an && echo done tail, asks",
           "cd " + slash(WTPRUNE) + " && " + ASK_PRUNE + " && echo done", "shared-tree", cwd=NOGIT)

# DENY CONTROLS. A tail that is a command with effects, and a real
# second command, are not harmless, so the chain still denies as a chained ask command.
chained_ask("ask-alone: the discard piped to tee, a command with effects, still denies",
            ASK_DISCARD + " | tee lane.log", cwd=GITWT)
chained_ask("ask-alone: the prune piped to sh, a command with effects, still denies",
            ASK_PRUNE + " | sh", cwd=WTPRUNE)
chained_ask("ask-alone: a cd, the prune, then a removal of y, still denies",
            "cd " + slash(WTPRUNE) + " && " + ASK_PRUNE + " && rm -rf /tmp/y", cwd=NOGIT)

# TWO SAFETY HOLES, from an owner review. Both must DENY. The first: the `\"` inside the echo is an
# escaped quote, so the `; rm -rf y` after it is a real command. The second: `cd -` moves to the previous
# folder, which no path in the command names, so it is no harmless lead, and the prune after it is a
# chained ask command.
chained_prune("ask-alone: an escaped quote in an echo tail does not hide a removal after it, the prune denies",
              ASK_PRUNE + ' && echo "a \\" b" ; rm -rf y')
chained_prune("ask-alone: a cd - to the previous folder before the prune is no named lead, so it denies",
              "cd - && " + ASK_PRUNE)


# A COMMENT OPENER OR A LONE APOSTROPHE INSIDE A HARMLESS TAIL (debt ask-alone-tail-test-gap). The tail is read with the
# shell's own quoting: a quoted #, a quoted /* and a lone apostrophe in a double-quoted echo or Write-Host text hide no
# command and open no comment, so each call still asks once. Test only: the guard already reads these tails this way,
# so these cases pin the current verdict, and no guard change is needed for them.
for _label, _text in (("a quoted hash", "a # b"), ("a quoted block opener", "x /* y"),
                      ("a lone apostrophe", "don't stop")):
    asks_alone("ask-alone: %s in an && echo tail still asks once" % _label,
               ASK_PRUNE + ' && echo "' + _text + '"', "shared-tree", cwd=WTPRUNE)
    asks_alone("ask-alone: %s in a ; Write-Host tail still asks once" % _label,
               ASK_PRUNE + '; Write-Host "' + _text + '"', "shared-tree", tool="PowerShell", cwd=WTPRUNE)


# =========================================================================== 6d. an interpreter heredoc is one command

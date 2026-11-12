# section 20106
FAMILY = "ask-alone"
#
# OWNER RULING (2026-10-14 22:25): an inline interpreter script, a `python - <<PY`, `node`, `perl` or
# `ruby` heredoc, is ONE command, so one shell call holding an ask command asks once, as a lone ask command does.
# A chain before or after the heredoc, a pipe after the header, two
# interpreter heredocs, and a bash or `ssh host "bash -s"` body still count more than one command. A deny
# in a body still wins (the shared-tree and kill sections hold those cases).
LANE_STASH = VCS + " stash push -u -m lane"
FORCE_PUSH = VCS + " push --force origin HEAD:main"

sh("ask-alone: a one-command python heredoc holding a prune asks, not denies",
   "python3 - <<'PY'\n" + PRUNE + "\nPY", "ask", "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a one-command python heredoc with a print line and a prune asks once",
   "python3 - <<'PY'\nprint(1)\n" + PRUNE + "\nPY", "ask", "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a one-command node heredoc holding a prune asks, not denies",
   "node <<'JS'\n" + PRUNE + "\nJS", "ask", "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a one-command perl heredoc holding a prune asks, not denies",
   "perl <<'PL'\n" + PRUNE + "\nPL", "ask", "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a one-command ruby heredoc holding a prune asks, not denies",
   "ruby <<'RB'\n" + PRUNE + "\nRB", "ask", "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a one-command python heredoc holding a forced push asks, not denies",
   "python3 - <<'PY'\n" + FORCE_PUSH + "\nPY", "ask", "force-push", cwd=PUSHFEAT)
sh("ask-alone: a one-command python heredoc holding a hard reset in a worktree asks, not denies",
   "python3 - <<'PY'\n" + VCS + " reset --hard\nPY", "ask", "shared-tree", cwd=GITWT)
sh("cap data: a one-command python heredoc holding a cap write as text allows "
   "[step agent-model-cap-string-false-alarm: a false-alarm fix, interpreter string data that writes no file "
   "is not the act; incident 2026-11-02 01:16 CST]",
   "python3 - <<'PY'\n" + CAP_PLAIN + "\nPY", "allow", cwd=PROJ)
sh("cap data: a one-command python heredoc whose os.system runs a cap write asks "
   "[regression pin: passes on main]",
   "python3 - <<'PY'\nimport os; os.system('" + CAP_PLAIN + "')\nPY", "ask", "agent-model-cap", cwd=PROJ,
   carries=(CAP_KEY,))

# Alias bypass: a cap write through an import alias asks, as the spelled-out call does. CAP_ECHO_LOCAL
# is the cap write every case below names.
CAP_ECHO_LOCAL = "echo " + CAP_KEY + "=" + OPUS + " > .claude/settings.local.json"
sh("cap alias: a python heredoc importing run from subprocess, a cap write run with shell=True, asks "
   "[alias bypass, main asks]",
   "python3 - <<'PY'\nfrom subprocess import run\nrun('" + CAP_ECHO_LOCAL + "', shell=True)\nPY",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap alias: a python heredoc importing subprocess as sp, a cap write run by sp.run with shell=True, asks "
   "[alias bypass, main asks]",
   "python3 - <<'PY'\nimport subprocess as sp\nsp.run('" + CAP_ECHO_LOCAL + "', shell=True)\nPY",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap alias: a python heredoc importing os as o, a cap write run by o.system, asks "
   "[alias bypass, main asks]",
   "python3 - <<'PY'\nimport os as o\no.system('" + CAP_ECHO_LOCAL + "')\nPY",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap alias: a python heredoc importing system from os, a cap write run by system, asks "
   "[alias bypass, main asks]",
   "python3 - <<'PY'\nfrom os import system\nsystem('" + CAP_ECHO_LOCAL + "')\nPY",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap alias: a python heredoc importing call from subprocess, a cap write run by call with shell=True, asks "
   "[alias bypass, main asks]",
   "python3 - <<'PY'\nfrom subprocess import call\ncall('" + CAP_ECHO_LOCAL + "', shell=True)\nPY",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
# A python comment is text, not a shell spot: a body whose only spot is a comment is data.
sh("cap comment: a python heredoc whose only spot is a comment naming a cap write, allows "
   "[comment false alarm, main allows]",
   "python3 - <<'PY'\n# os.system('" + CAP_ECHO_LOCAL + "')\nPY", "allow", cwd=PROJ)

# Python file operations, node aliases, os.path imports and written-then-run scripts. Each case names a write
# the way a probe would: CAP_ECHO_LOCAL is the cap write, CFG_HOOK the hook path a frozen write lands on, ENV
# the env file.
sh("frozen python: a heredoc copying onto the hook path with shutil.copy denies",
   "python3 - <<'PY'\nimport shutil; shutil.copy('src','" + CFG_HOOK + "')\nPY", "deny", "frozen-path", cwd=NOGIT)
sh("frozen python: a heredoc moving onto the hook path with shutil.move denies",
   "python3 - <<'PY'\nimport shutil; shutil.move('src','" + CFG_HOOK + "')\nPY", "deny", "frozen-path", cwd=NOGIT)
sh("frozen python: a heredoc copying onto the hook path through shutil as sh denies",
   "python3 - <<'PY'\nimport shutil as sh; sh.copy('src','" + CFG_HOOK + "')\nPY", "deny", "frozen-path",
   cwd=NOGIT)
sh("frozen python: a heredoc changing the mode of the hook path with os.chmod denies",
   "python3 - <<'PY'\nimport os; os.chmod('" + CFG_HOOK + "', 0o755)\nPY", "deny", "frozen-path", cwd=NOGIT)
sh("frozen python: a python -c copying onto the hook path with shutil.copy denies",
   "python3 -c \"import shutil; shutil.copy('src','" + CFG_HOOK + "')\"", "deny", "frozen-path", cwd=NOGIT)
sh("frozen python: a body written to x.py, copying onto the hook path with shutil.copy, then run, denies",
   "cat > x.py <<'PY'\nimport shutil; shutil.copy('src','" + CFG_HOOK + "')\nPY\npython3 x.py",
   "deny", "frozen-path", cwd=NOGIT)

sh("cap node: a node heredoc calling a cap write through childProcess.exec asks",
   "node - <<'J'\nconst childProcess=require('child_process'); childProcess.exec('" + CAP_ECHO_LOCAL + "')\nJ",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap node: a node heredoc calling a cap write through a destructured execSync renamed e asks",
   "node - <<'J'\nconst {execSync: e}=require('child_process'); e('" + CAP_ECHO_LOCAL + "')\nJ",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap node: a node import of execSync as e calling a cap write asks",
   "node - <<'J'\nimport {execSync as e} from 'child_process'; e('" + CAP_ECHO_LOCAL + "')\nJ",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap node: a node heredoc calling a cap write through cp.execSync held in run asks",
   "node - <<'J'\nconst cp=require('child_process');\nconst run=cp.execSync;\nrun('" + CAP_ECHO_LOCAL + "')\nJ",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap node: a node heredoc calling a cap write through promisified exec asks",
   "node - <<'J'\nconst {exec}=require('child_process');\nconst execAsync=require('util').promisify(exec);\n"
   "await execAsync('" + CAP_ECHO_LOCAL + "')\nJ", "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap node: a node -e calling a cap write through cp.execSync asks",
   "node -e \"const cp=require('child_process'); cp.execSync('" + CAP_ECHO_LOCAL + "')\"",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("frozen node: a node heredoc copying onto the hook path through childProcess.exec denies",
   "node - <<'J'\nconst childProcess=require('child_process'); childProcess.exec('cp x " + CFG_HOOK + "')\nJ",
   "deny", "frozen-path", cwd=NOGIT)
sh("env node: a node heredoc reading the env file in a template string through cp.execSync denies",
   "node - <<'J'\nconst cp=require('child_process'); cp.execSync(`cat " + ENV + "`)\nJ",
   "deny", "env-file", cwd=PROJ)

sh("cap import: a python heredoc importing os.path, then os.system on a cap write, asks",
   "python3 - <<'PY'\nimport os.path\nos.system('" + CAP_ECHO_LOCAL + "')\nPY",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap import: a python -c importing os.path, then os.system on a cap write, asks",
   "python3 -c \"import os.path; os.system('" + CAP_ECHO_LOCAL + "')\"",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))

chained_ask("cap script: a body written to x.py that runs a cap write with subprocess run and shell=True, then run, "
   "denies as a chained ask command [main's verdict]",
   "cat > x.py <<'PY'\nfrom subprocess import run\ncmd='" + CAP_ECHO_LOCAL + "'\nrun(cmd, shell=True)\nPY\n"
   "python3 x.py", cwd=PROJ, carries=("agent-model-cap",))
chained_ask("cap script: a body written to x.py that runs a cap write with os as o system, then run, "
   "denies as a chained ask command [main's verdict]",
   "cat > x.py <<'PY'\nimport os as o\ncmd='" + CAP_ECHO_LOCAL + "'\no.system(cmd)\nPY\npython3 x.py",
   cwd=PROJ, carries=("agent-model-cap",))

# Pins for the from-import forms, the interpolated shell calls in perl and node, and a data print that allows.
sh("frozen python: a heredoc importing copy from shutil, copying onto the hook path, denies [pin]",
   "python3 - <<'PY'\nfrom shutil import copy; copy('src','" + CFG_HOOK + "')\nPY", "deny", "frozen-path", cwd=NOGIT)
sh("frozen python: a heredoc importing chmod from os, changing the mode of the hook path, denies [pin]",
   "python3 - <<'PY'\nfrom os import chmod; chmod('" + CFG_HOOK + "', 0o755)\nPY", "deny", "frozen-path", cwd=NOGIT)
sh("cap perl: a perl heredoc whose system runs a cap write held in a variable, asks [pin]",
   "perl <<'PL'\nmy $c = 'echo " + CAP_KEY + "=" + OPUS + " > .claude/settings.local.json'; system(\"$c\");\nPL",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap node: a node heredoc calling execSync on a cap write in a template literal, asks [pin]",
   "node - <<'J'\nconst c='" + CAP_ECHO_LOCAL + "'; require('child_process').execSync(`${c}`)\nJ",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap node: a node heredoc calling execSync on a cap write joined by concatenation, asks [pin]",
   "node - <<'J'\nconst c='" + CAP_ECHO_LOCAL + "'; require('child_process').execSync('' + c)\nJ",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap data: a python heredoc printing a path join beside a cap write as text, allows [pin]",
   "python3 - <<'PY'\nimport os; print(os.path.join('a','b'), '" + CAP_ECHO_LOCAL + "')\nPY",
   "allow", cwd=PROJ)

# Scanner cases (building-scanner-respects-strings): a comment opener, a lone apostrophe and a
# multi-line template literal inside the body. None of them hides the prune or adds a command.
sh("ask-alone: a # line with a lone apostrophe in a python body holds no quote, so the prune asks",
   "python3 - <<'PY'\n# don't\n" + PRUNE + "\nPY", "ask", "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a // line with a lone apostrophe in a python body holds no quote, so the prune asks",
   "python3 - <<'PY'\n// don't\n" + PRUNE + "\nPY", "ask", "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a /* opener in a python body opens no quote, so the prune asks",
   "python3 - <<'PY'\n/* x */\n" + PRUNE + "\nPY", "ask", "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a lone apostrophe in plain python body text, then the prune, asks",
   "python3 - <<'PY'\ndon't stop\n" + PRUNE + "\nPY", "ask", "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a prune inside a multi-line node template literal asks, not denies",
   "node <<'JS'\nconst s = `\n" + PRUNE + "\n`;\nJS", "ask", "shared-tree", cwd=WTPRUNE)
sh("ask-alone: a python body that holds a shell prune only as a # comment is no command, so it allows",
   "python3 - <<'PY'\n# " + PRUNE + "\nPY", "allow", cwd=WTPRUNE)

# The delimiter `E-F` is read as the whole word.
sh("ask-alone: a one-command python heredoc with the delimiter E-F, holding a prune, asks",
   "python3 - <<E-F\n" + PRUNE + "\nE-F", "ask", "shared-tree", cwd=WTPRUNE)
chained_prune("ask-alone: a whole-word delimiter E-F, a python body, then a prune, still denies",
              "python3 - <<E-F\nprint(1)\nE-F\n" + PRUNE)

# Each is more than one command, so the prune denies as a chained ask command.
chained_prune("ask-alone: a chain before a python heredoc holding a prune still denies",
              "echo hi && python3 - <<'PY'\n" + PRUNE + "\nPY")
chained_prune("ask-alone: a python heredoc holding a prune, then echo, still denies",
              "python3 - <<'PY'\n" + PRUNE + "\nPY\necho x")
chained_prune("ask-alone: a python heredoc header with a trailing pipe to tee still denies",
              "python3 - <<'PY' | tee out.txt\n" + PRUNE + "\nPY")
chained_prune("ask-alone: a bash heredoc body holding a prune still counts each line, so it denies",
              "bash <<'SH'\n" + PRUNE + "\nSH")
chained_prune("ask-alone: an ssh bash -s heredoc body holding a prune still counts each line",
              'ssh host "bash -s" <<\'SH\'\n' + PRUNE + "\nSH")
chained_prune("ask-alone: two python heredocs, a prune in the first, still deny as two commands",
              "python3 - <<'A'\n" + PRUNE + "\nA\npython3 - <<'B'\nprint(1)\nB")
chained_prune("ask-alone: a python heredoc holding a prune, then a bash heredoc, still denies",
              "python3 - <<'PY'\n" + PRUNE + "\nPY\nbash <<'SH'\necho x\nSH")
chained_prune("ask-alone: a bash heredoc holding a prune, then a python heredoc, still denies",
              "bash <<'SH'\n" + PRUNE + "\nSH\npython3 - <<'PY'\nprint(1)\nPY")
chained_prune("ask-alone: a python header in quoted echo text is no heredoc, so the prune after it denies",
              'echo "python <<EOF"\n' + PRUNE)
deny_beats("ask-alone: a python body holding a prune and a stash push denies as the stash push",
           "python3 - <<'PY'\n" + PRUNE + "\n" + LANE_STASH + "\nPY", "shared-tree", cwd=GITWT,
           carries="stash stack")


# H1. A delimiter with a backslash or a quote closes at the word bash reads: `E\OF`, `E'OF'` and `"E"OF`
# are all `EOF`.
for _label, _open in (("backslash", "E\\OF"), ("single-quoted", "E'OF'"), ("double-quoted", '"E"OF')):
    chained_prune("ask-alone: r1-hd a python heredoc, %s delimiter closed at EOF, then a prune, denies" % _label,
                  "python3 - <<" + _open + "\nx\nEOF\n" + PRUNE)

# H2. A header that pipes into a shell counts as a shell body. Its closer is EOF-X, so the EOF line in the
# body closes nothing, and the prune in the body is a command.
for _shell in ("sh", "bash"):
    chained_prune("ask-alone: r1-hd a cat heredoc piped to %s, closer EOF-X, a prune in the body, denies" % _shell,
                  "cat <<EOF-X | " + _shell + "\nx\nEOF\n" + PRUNE + "\nEOF-X")

# AN UNCLOSED BODY. Bash reads every line to the end of input, so every line is a command.
chained_prune("ask-alone: r1-hd a python heredoc with no closer, a prune after it, denies",
              "python3 - <<'PY'\nprint(1)\n" + PRUNE)

# Two prune lines in one python body are one command, so the call asks once.
sh("ask-alone: r1-hd two prune lines in one python body ask once, not deny",
   "python3 - <<'PY'\n" + PRUNE + "\n" + PRUNE + "\nPY", "ask", "shared-tree", cwd=WTPRUNE)

# SCANNERS (building-scanner-respects-strings): a comment with a lone apostrophe, a lone apostrophe in
# body text, a header shape inside quoted text, and a multi-line template literal.
sh("ask-alone: r1-hd a comment with a lone apostrophe after a python header asks once for the prune",
   "python3 - <<'PY' # don't\n" + PRUNE + "\nPY", "ask", "shared-tree", cwd=WTPRUNE)
chained_prune("ask-alone: r1-hd a lone apostrophe in a python body under a backslash delimiter, then a prune, denies",
              "python3 - <<E\\OF\nDon't\nEOF\n" + PRUNE)
chained_prune("ask-alone: r1-hd a header shape inside a double-quoted echo, then a prune, denies",
              'echo "# <<EOF-X | sh"\n' + PRUNE)
chained_prune("ask-alone: r1-hd a template literal in a node body closed at E'OF', then a prune, denies",
              "node <<E'OF'\nconst s = `\nEOF\n" + PRUNE)
sh("ask-alone: r1-hd a prune in a node template literal under a backslash delimiter asks once",
   "node <<E\\OF\nconst s = `\n" + PRUNE + "\n`;\nEOF", "ask", "shared-tree", cwd=WTPRUNE)

# A plain cat heredoc piped to sh, with a prune in its body.
chained_prune("ask-alone: r1-hd a plain cat heredoc piped to sh, a prune in the body, denies (red on main too)",
              "cat <<EOF | sh\n" + PRUNE + "\nEOF")

# settle_ask strips the bodies once: a stray line equal to a delimiter (the lone EOF) must not open a
# phantom body that holds the ask command.
chained_ask("ask-alone: r2-hd a stray EOF line after a closed heredoc, then a cap write, denies",
            "cat <<EOF\nbody line\nEOF\n" + CAP_PLAIN + "\nEOF", cwd=PROJ, carries=CAP_STEP)
chained_prune("ask-alone: r2-hd a stray EOF line after a closed heredoc, then a prune, denies",
              "cat <<EOF\nbody line\nEOF\n" + PRUNE + "\nEOF")

# ITEM 2, the ask payload. The forms of the kill section, with a cap write in the body: one ask command.
for _label, _form in R2_FORMS + (R2_EVAL_FORM,):
    chained_ask("ask-alone: r2-hd a heredoc in %s, a cap write in the body, denies" % _label,
                _form.replace("BODY", CAP_PLAIN), cwd=PROJ, carries=CAP_STEP)

# SCANNER PIN (building-scanner-respects-strings). A node body holds a template literal
# across lines, with `$(cat <<'EOF-1'` text and one prune in it. An interpreter body is one command, so it asks
# once.
sh("ask-alone: r2-hd a node heredoc whose template literal holds $( heredoc text and a prune asks once",
   "node <<E\\OF\nconst s = `\n$(cat <<'EOF-1'\n" + PRUNE + "\n`;\nEOF", "ask", "shared-tree", cwd=WTPRUNE)


# A prune or a push delete in a body that is kept in view is a second command, so the command denies as a chained ask.
# The scanner shapes (a comment opener in quotes, a lone apostrophe, a template literal) are pinned here too.
chained_prune("ask-alone: r3-bd a prune after a stray EOF line, written then sh on the next line, denies",
              "cat <<'EOF-1' > x.sh\necho hi\nEOF\n" + PRUNE + "\nEOF-1\nsh x.sh")
chained_prune("ask-alone: r3-bd a prune after a stray EOF line, piped to tee, then bash, denies",
              "cat <<'EOF-1' | tee x.sh\necho hi\nEOF\n" + PRUNE + "\nEOF-1\nbash x.sh")
chained_prune("ask-alone: r3-bd a prune on a backslash delimiter piped to python3, denies",
              "cat <<\\EOF | python3 -\necho hi\n" + PRUNE + "\nEOF")
chained_prune("ask-alone: r3-bd a prune on an unquoted EOF-1 that main reads as EOF, denies",
              "cat <<EOF-1 > x.sh\necho hi\nEOF\n" + PRUNE + "\nEOF-1\nsh x.sh")
chained_prune("ask-alone: r3-bd a prune after a comment opener in quotes on the header, denies",
              'echo "a # b" && cat <<\'EOF-1\' > x.sh\necho hi\nEOF\n' + PRUNE + "\nEOF-1\nsh x.sh")
chained_prune("ask-alone: r3-bd a prune after a lone apostrophe in a body comment, denies",
              "cat <<'EOF-1' > x.sh\n# don't\nEOF\n" + PRUNE + "\nEOF-1\nsh x.sh")
chained_prune("ask-alone: r3-bd a prune inside a multi-line template literal in the body, denies",
              "cat <<'EOF-1' > x.sh\nconst s = `\nEOF\n" + PRUNE + "\n`;\nEOF-1\nsh x.sh")
# The push-delete path reads the same walk. The verdict here does not turn on the run dir, so this pins the walk
# through the body, not a `cd`: the body holds the cd and the push, and the push asks on main.
chained_ask("ask-alone: r3-bd a body with a cd and a push delete of main, written then sh, denies",
            "cat <<'EOF-1' > x.sh\nEOF\ncd " + slash(PUSHMAIN) + "\ngit push origin :main\nEOF-1\nsh x.sh",
            cwd=PUSHFEAT)



# (h) A KEPT HEREDOC BODY IS TEXT, NOT A SHELL STEP. A heredoc body that a later command runs is kept in view,
# and the guard reads it. An interpreter body that calls no shell runs no `$( )` and no backtick, so a push named
# in its prose is data, and the shapes below allow. A push line that `sh` runs, and a substitution in a shell body,
# still run and still deny. A body that calls a shell runs its `$( )`, and the (h) shell-out block below denies it.
# The words `git` and `.env` are built from VCS and ENV, as in the rest of this file.
SCRATCH = slash(os.path.join(ROOT, "scratch"))
REPRO_LINE = ('cases = {"subst": "' + VCS + ' commit -m \\"$(cat <<\'EOF\'\\nfix: no ' + VCS
              + ' push --force here\\nEOF\\n)\\" && ' + VCS + ' push origin lane-x"}')
REPRO = "S=" + SCRATCH + "\ncat > $S/r.py <<'EOF'\n" + REPRO_LINE + "\nEOF\npython3 $S/r.py"
sh("ask-alone: the repro, a file written by heredoc with a prose force-push in $( ) and then run, allows",
   REPRO, "allow", cwd=PUSHFEAT)

TRIAGE_NOTE = "`" + VCS + " push origin roadmap` is the one writer, and a force-push is refused."
TRIAGE = ("python3 - <<'PY'\nfrom pathlib import Path\np = Path(\"roadmap/steps.md\")\n"
          "p.write_text(p.read_text() + \"\\nNote: " + TRIAGE_NOTE + "\\n\")\nPY\n"
          "python3 roadmap/build.py && " + VCS + " add -A && " + VCS + " commit -m x && "
          + VCS + " push origin lane-x")
sh("ask-alone: the triage shape, a python step-note edit with a backtick push and force-push prose, then a push to lane-x, allows",
   TRIAGE, "allow", cwd=PUSHFEAT)

# The scanner shapes: a `#` line with a lone apostrophe, and a backtick span over two lines, in one python body.
SCAN = ("python3 - <<'PY'\n# don't re-run this by hand\nnote = \"\"\"Do not run `" + VCS
        + " push --force\norigin roadmap` here: the force-push is refused.\"\"\"\nPY\n"
        "python3 roadmap/build.py && " + VCS + " add -A && " + VCS + " commit -m x && "
        + VCS + " push origin lane-x")
sh("ask-alone: a python body with a # line, a lone apostrophe and a two-line backtick span, then a push to lane-x, allows",
   SCAN, "allow", cwd=PUSHFEAT)

# A python body without a shell-out call runs no shell, so a $( ) in its print text is text, as a quoted commit message is.
sh("ask-alone: a python body that prints a $( ) around a forced push to main is text, allows",
   "python3 - <<'PY'\nprint(\"$(" + VCS + " push --force origin HEAD:main) is refused\")\nPY",
   "allow", cwd=PUSHFEAT)

# CONTROLS: a real push keeps its verdict, so a read of body text must never drop one.
FORCE_LANE = VCS + " push --force origin lane-x"
sh("ask-alone: control, a plain chain of add, commit and a push to lane-x allows",
   VCS + " add -A && " + VCS + " commit -m x && " + VCS + " push origin lane-x", "allow", cwd=PUSHFEAT)
sh("ask-alone: control, a forced push to lane-x alone denies",
   FORCE_LANE, "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("ask-alone: control, a forced push to lane-x chained after an add and a commit denies",
   VCS + " add -A && " + VCS + " commit -m x && " + FORCE_LANE, "deny", "force-push", cwd=PUSHFEAT,
   carries=REMEDY)
sh("ask-alone: control, a forced push to lane-x inside a dollar paren in a plain echo denies",
   'echo "$(' + FORCE_LANE + ')"', "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("ask-alone: control, a forced push to lane-x in backticks in a plain echo denies",
   "echo `" + FORCE_LANE + "`", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY)
sh("ask-alone: control, a forced push line in a heredoc body that a later sh runs denies",
   "cat > x.sh <<'EOF'\n" + FORCE_LANE + "\nEOF\nsh x.sh", "deny", "force-push", cwd=PUSHFEAT,
   carries=REMEDY)
sh("ask-alone: control, a forced push in backticks in a heredoc body that a later sh runs denies",
   "cat > x.sh <<'EOF'\necho `" + FORCE_LANE + "`\nEOF\nsh x.sh", "deny", "force-push", cwd=PUSHFEAT,
   carries=REMEDY)
sh("ask-alone: control, a forced push to main alone asks",
   VCS + " push --force origin HEAD:main", "ask", "force-push", cwd=PUSHFEAT)
chained_ask("ask-alone: control, a forced push to main chained after an add denies as a chained ask command",
            VCS + " add -A && " + VCS + " push --force origin HEAD:main", cwd=PUSHFEAT)
chained_prune("ask-alone: a prune chained after an add, then a push to lane-x, denies",
              VCS + " add -A && " + PRUNE + " && " + VCS + " push origin lane-x")

# (h) SHAPES THAT RUN A QUOTED HEREDOC BODY. Each body holds a forced push to lane-x inside `$( )`, and a shell
# runs it. Cases 1 and 2 write the body to a file that sh runs: the written-file arm of _shell_reads_bodies. Case 1
# names the file x.sh, whose name ends in the shell word sh, so the whole-text arm also denies it; case 2 names run.txt,
# which no shell word ends, and pins the written-file arm alone. Cases 3 to 5 are a body a shell reads from its
# header or its pipe: bash, a pipe into sh on the next line, and an eval whose backtick opens on the line before the
# header: the SHELL_HEREDOC arm of _shell_reads_bodies. An eval whose `$(` opens there is denied by the judged text, so it pins
# neither arm. Each denies as a force-push.
BODY_PUSH = 'x="$(' + FORCE_LANE + ')"'
sh("ask-alone: a quoted body written to x.sh and run by sh, a forced push in $( ), denies as force-push",
   "cat > x.sh <<'EOF'\n" + BODY_PUSH + "\nEOF\nsh x.sh", "deny", "force-push", cwd=PUSHFEAT,
   carries=REMEDY, lacks=(CHAIN_ASK,))
sh("ask-alone: a quoted body written to run.txt and run by sh, a forced push in $( ), denies as force-push",
   "cat > run.txt <<'EOF'\n" + BODY_PUSH + "\nEOF\nsh run.txt", "deny", "force-push", cwd=PUSHFEAT,
   carries=REMEDY, lacks=(CHAIN_ASK,))
sh("ask-alone: a quoted body fed to bash, a forced push in $( ), denies as force-push",
   "bash <<'EOF'\n" + BODY_PUSH + "\nEOF", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY,
   lacks=(CHAIN_ASK,))
sh("ask-alone: a quoted body piped to sh on the next line, a forced push in $( ), denies as force-push",
   "cat <<'EOF' |\n" + BODY_PUSH + "\nEOF\nsh", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY,
   lacks=(CHAIN_ASK,))
sh("ask-alone: a quoted body under an eval whose backtick is on the line before, a forced push in $( ), denies as force-push",
   'eval `\ncat <<\'EOF\'\n' + BODY_PUSH + '\nEOF\n`', "deny", "force-push", cwd=PUSHFEAT,
   carries=REMEDY, lacks=(CHAIN_ASK,))

# (h) SHAPES THAT SHELL OUT FROM AN INTERPRETER BODY. A body that hands a string to a shell (`os.system`, `os.popen`,
# `subprocess` with `shell=True` or a `bash -c` argv, `create_subprocess_shell`, `execSync`, a perl `system(`, a ruby
# backtick) makes the shell run the `$( )` in it. Each body holds a forced push to lane-x inside `$( )` and denies as a
# force-push. The two git-env bodies hold a GIT_DIR set inside `$( )` and deny as a git-env set. The file-run body is
# written to f.py and run by python3: the shell-out arm keeps its body, and the written-file arm reads the run.
PY_HEADER = "python3 - <<'PY'\n"
PY_PUSH = "$(" + FORCE_LANE + ")"
PY_ENV = "$(GIT_DIR=/tmp/x " + VCS + " status)"
sh("ask-alone: (h) a python body calling os.system around a forced push in $( ), denies as force-push",
   PY_HEADER + "import os\nos.system(\"echo " + PY_PUSH + "\")\nPY", "deny", "force-push", cwd=PUSHFEAT,
   carries=REMEDY, lacks=(CHAIN_ASK,))
sh("ask-alone: (h) a python body calling os.popen around a forced push in $( ), denies as force-push",
   PY_HEADER + "import os\nos.popen(\"echo " + PY_PUSH + "\")\nPY", "deny", "force-push", cwd=PUSHFEAT,
   carries=REMEDY, lacks=(CHAIN_ASK,))
sh("ask-alone: (h) a python body calling subprocess.run with shell=True around a forced push in $( ), denies as force-push",
   PY_HEADER + "import subprocess\nsubprocess.run(\"echo " + PY_PUSH + "\", shell=True)\nPY", "deny", "force-push",
   cwd=PUSHFEAT, carries=REMEDY, lacks=(CHAIN_ASK,))
sh("ask-alone: (h) a python body calling subprocess.run with a bash -c argv around a forced push in $( ), denies as force-push",
   PY_HEADER + "import subprocess\nsubprocess.run([\"bash\", \"-c\", \"echo " + PY_PUSH + "\"])\nPY", "deny", "force-push",
   cwd=PUSHFEAT, carries=REMEDY, lacks=(CHAIN_ASK,))
sh("ask-alone: (h) a python body calling subprocess.Popen with a sh -c argv around a forced push in $( ), denies as force-push",
   PY_HEADER + "import subprocess\nsubprocess.Popen([\"sh\", \"-c\", \"echo " + PY_PUSH + "\"])\nPY", "deny", "force-push",
   cwd=PUSHFEAT, carries=REMEDY, lacks=(CHAIN_ASK,))
sh("ask-alone: (h) a python body calling asyncio create_subprocess_shell around a forced push in $( ), denies as force-push",
   PY_HEADER + "import asyncio\nasyncio.create_subprocess_shell(\"echo " + PY_PUSH + "\")\nPY", "deny", "force-push",
   cwd=PUSHFEAT, carries=REMEDY, lacks=(CHAIN_ASK,))
sh("ask-alone: (h) a perl body calling system around a forced push in $( ), denies as force-push",
   "perl - <<'PL'\nsystem(\"echo " + PY_PUSH + "\");\nPL", "deny", "force-push", cwd=PUSHFEAT,
   carries=REMEDY, lacks=(CHAIN_ASK,))
sh("ask-alone: (h) a node body calling execSync around a forced push in $( ), denies as force-push",
   "node - <<'JS'\nrequire('child_process').execSync(\"echo " + PY_PUSH + "\")\nJS", "deny", "force-push",
   cwd=PUSHFEAT, carries=REMEDY, lacks=(CHAIN_ASK,))
sh("ask-alone: (h) a ruby body holding a backtick around a forced push in $( ), denies as force-push",
   "ruby - <<'RB'\nputs `echo " + PY_PUSH + "`\nRB", "deny", "force-push", cwd=PUSHFEAT,
   carries=REMEDY, lacks=(CHAIN_ASK,))
sh("ask-alone: (h) a python os.system body written to f.py and run by python3, a forced push in $( ), denies as force-push",
   "cat > f.py <<'EOF'\nimport os\nos.system(\"echo " + PY_PUSH + "\")\nEOF\npython3 f.py", "deny", "force-push",
   cwd=PUSHFEAT, carries=REMEDY, lacks=(CHAIN_ASK,))
sh("ask-alone: (h) a python body calling os.system around a GIT_DIR set in $( ), denies as git-env-set",
   PY_HEADER + "import os\nos.system(\"echo " + PY_ENV + "\")\nPY", "deny", GIT_ENV_RULE, cwd=NOGIT)
sh("ask-alone: (h) a python body calling subprocess.run with shell=True around a GIT_DIR set in $( ), denies as git-env-set",
   PY_HEADER + "import subprocess\nsubprocess.run(\"echo " + PY_ENV + "\", shell=True)\nPY", "deny", GIT_ENV_RULE,
   cwd=NOGIT)
# (h) A LONE SHELL-OUT BODY THAT NAMES A PUSH AS TEXT. The push is prose in an interpreter body, not a `$( )`, and
# the shell-out runs the build. Run alone, the call asks on the push. The shells-only read must not count the
# interpreter's shell-out, or the body stays in view and the lone call denies as ask-alone.
F2_BODY = "import os\nNote: " + VCS + " push --force origin HEAD:main\nos.system(\"python3 roadmap/build.py\")"
sh("ask-alone: (h) a lone python body that calls os.system and names a forced push to main as text, asks as force-push",
   PY_HEADER + F2_BODY + "\nPY", "ask", "force-push", cwd=PUSHFEAT)
sh("ask-alone: (h) a lone python body that calls subprocess.run with shell=True and names a forced push to main as text, asks as force-push",
   PY_HEADER + "import subprocess\nNote: " + VCS + " push --force origin HEAD:main\n"
   "subprocess.run(\"python3 roadmap/build.py\", shell=True)\nPY", "ask", "force-push", cwd=PUSHFEAT)


# (h) A SCRIPT WHOSE OUTPUT A SHELL RUNS. A python body that prints a `$( )` is text only while nothing runs its
# output. Written to x.sh and run by sh, or piped to sh, the `$( )` runs: both deny as a force-push.
sh("ask-alone: (h) a python body printing a forced push in $( ), written to x.sh and run by sh, denies as force-push",
   "python3 - <<'PY' > x.sh\nprint(\"" + PY_PUSH + "\")\nPY\nsh x.sh", "deny", "force-push", cwd=PUSHFEAT,
   carries=REMEDY, lacks=(CHAIN_ASK,))
sh("ask-alone: (h) a python body printing a forced push in $( ), piped to sh, denies as force-push",
   "python3 - <<'PY' | sh\nprint(\"" + PY_PUSH + "\")\nPY", "deny", "force-push", cwd=PUSHFEAT,
   carries=REMEDY, lacks=(CHAIN_ASK,))
# Two more ways a script hands a string to a shell: a zx template (a dollar sign then a backtick) and os.spawnl.
sh("ask-alone: (h) a node body running a zx template around a forced push in $( ), denies as force-push",
   "node - <<'JS'\nawait $`echo " + PY_PUSH + "`\nJS", "deny", "force-push", cwd=PUSHFEAT,
   carries=REMEDY, lacks=(CHAIN_ASK,))
sh("ask-alone: (h) a python body calling os.spawnl around a forced push in $( ), denies as force-push",
   PY_HEADER + "import os\nos.spawnl(os.P_WAIT, \"/bin/bash\", \"bash\", \"-c\", \"echo " + PY_PUSH + "\")\nPY",
   "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY, lacks=(CHAIN_ASK,))


# =========================================================================== ordinary work

# section 26657
FAMILY = "command-in-item"
#
# A waiting task's steps never send the owner to a file for a command: the owner would open the file
# and copy the command out. The steps are judged joined, since the two halves can sit in separate
# steps. The red case is the old shape of item 39, rebuilt from its step note: one step opened a plan
# file and the next said to run its command. A decision is not judged by this rule.

CI_DOC = "c152-stale-branch-deletes"
CI_STEPS = ["Open plans/c152-stale-branch-deletes.md", "Run its command"]
CI_TERMINAL = ["Open Terminal", "Paste the command below and run it"]
# A task's `command` is {powershell, mac}, one string per shell (decision act-in-place).
CMD_BOTH_SHELLS = {"powershell": "git push origin --delete old-a", "mac": "git push origin --delete old-a"}


def ci_task(steps, **over):
    # The Why yours line keeps each case on the command rule; task-names-check reads it (TN_WHY).
    task = {"id": CI_DOC, "kind": "task", "status": "open", "title": "Delete the stale branches",
            "steps": steps, "context": TN_WHY}
    task.update(over)
    return {k: v for k, v in task.items() if v is not None}


def ci(name, expected, item, **extra):
    wp_write("command in item: " + name, expected, "command-in-item", item, doc_id=CI_DOC, **extra)


ci("a step that opens a plan file, then one that says run its command, is denied", "deny", ci_task(CI_STEPS))
ci("the refusal names the command to add", "deny", ci_task(CI_STEPS),
   carries=("`command`", "paste the command below"))
ci("an update that carries those steps is denied", "deny", {"steps": CI_STEPS}, action="update")
ci("a run-the-command-in-file step is denied", "deny",
   ci_task(["Run the command in plans/c152-stale-branch-deletes.md"]))
ci("a copy-the-command-from-file step is denied", "deny",
   ci_task(["Copy the command from plans/c152-stale-branch-deletes.md"]))
ci("a file opened and its command run in one step is denied", "deny",
   ci_task(["Open plans/c152-stale-branch-deletes.md and run its command"]))
ci("a terminal step with the command on the item is allowed", "allow",
   ci_task(CI_TERMINAL, command=CMD_BOTH_SHELLS))
ci("a decision that opens a file and runs its command is not judged", "allow",
   {"id": CI_DOC, "kind": "decision", "status": "open", "title": "Delete the stale branches?",
    "context": OJ_FORM + "\n" + QD_LINE + "\nThe plan file lists them.",
    "options": [{"key": "a", "label": "Delete them",
                 "how": "Open plans/c152-stale-branch-deletes.md and run its command.", "gain": "g", "lose": "l"},
                {"key": "b", "label": "Keep them", "how": "Do nothing yet.", "gain": "g", "lose": "l"}]})


ci("a file step with the command set is denied", "deny",
   ci_task(CI_STEPS, command=CMD_BOTH_SHELLS))
ci("a run-the-command-in-file step with the command set is denied", "deny",
   ci_task(["Run the command in plans/c152.md"], command=CMD_BOTH_SHELLS))

# The command is {powershell, mac}: a bash-only string is refused, and so is a dict missing a shell or
# holding a blank string. The refusal names both shells.
ci("a bash-only command string on a set is denied", "deny",
   ci_task(CI_TERMINAL, command="git push origin --delete old-a"), carries=("powershell", "mac"))
ci("an update that sets a bash-only command string is denied", "deny", {"command": "git push"}, action="update")
ci("a command with no mac is denied", "deny",
   ci_task(CI_TERMINAL, command={"powershell": "git push origin --delete old-a"}))
ci("a command with no powershell is denied", "deny",
   ci_task(CI_TERMINAL, command={"mac": "git push origin --delete old-a"}))
ci("a command whose mac string is empty is denied", "deny",
   ci_task(CI_TERMINAL, command=dict(CMD_BOTH_SHELLS, mac="")))
ci("a command whose powershell string is blank is denied", "deny",
   ci_task(CI_TERMINAL, command=dict(CMD_BOTH_SHELLS, powershell="   ")))

# PowerShell 5.1 has none of these operators (item 78 failed on && and <<<). The same text under mac is allowed.
PS_OPERATOR_LINES = [("&&", "cd repo && git push origin --delete old-a"),
                     ("||", "git push origin --delete old-a || echo failed"),
                     ("<<<", "cat <<< old-a"),
                     ("<<", "cat <<EOF")]
for op, line in PS_OPERATOR_LINES:
    ci("a powershell line with %s is denied" % op, "deny",
       ci_task(CI_TERMINAL, command={"powershell": line, "mac": CMD_BOTH_SHELLS["mac"]}))
    ci("a mac line with %s and a clean powershell line is allowed" % op, "allow",
       ci_task(CI_TERMINAL, command={"powershell": CMD_BOTH_SHELLS["powershell"], "mac": line}))

# A shell line in a step's backtick span or fence is a command in the step. It belongs in the item's command field.
ci("a step that runs a git line in backticks is denied", "deny", ci_task(["Run `git push origin --delete old-a`"]))
ci("a step that runs a cd and && line in backticks is denied", "deny", ci_task(["Run `cd repo && npm test`"]))
ci("a step that runs a PowerShell cmdlet in backticks is denied", "deny", ci_task(["Run `Get-ChildItem -Recurse`"]))
ci("a step with a shell line in a fence is denied", "deny", ci_task(["Run this:\n```\ngit push origin --delete old-a\n```"]))
ci("a step with a backticked file name and no command verb is allowed", "allow",
   ci_task(["Check `README.md` reads well"]))
ci("a step that mentions git in prose is allowed", "allow", ci_task(["Look at the git branch list on the page"]))
ci("a step with a backticked word that is not a command is allowed", "allow", ci_task(["Pick `main`"]))
ci("an update with no command key and plain steps is allowed", "allow",
   {"steps": ["Read the summary on the page."]}, action="update")

# A command on the item excuses the loose verb match, as on main (decision act-in-place).
ci("a file step and a run-the-command step with a command on the item are allowed", "allow",
   ci_task(["Open plans/c152.md", "Run the command"], command=CMD_BOTH_SHELLS))
ci("a backticked file to read and a paste-in-PowerShell step with a command on the item are allowed", "allow",
   ci_task(["Open `plans/x.md` to read the plan", "Paste the command in PowerShell and run it"],
           command=CMD_BOTH_SHELLS))
ci("a paste-from-the-box step and a result-file step with a command on the item are allowed", "allow",
   ci_task(["Paste the command from the box below", "Check the result in `out.log`"], command=CMD_BOTH_SHELLS))
ci("a backticked ./ doc path to open is allowed", "allow", ci_task(["Open `./docs/a.md`"]))
ci("a backticked ./ source path with a line number to edit is allowed", "allow",
   ci_task(["Edit `./hooks/guard.py` line 3"]))
# A PowerShell string holds PowerShell only: a 2>/dev/null redirect or an export statement is bash.
ci("a powershell line with a 2>/dev/null redirect is denied", "deny",
   ci_task(CI_TERMINAL, command={"powershell": "git push origin --delete a 2>/dev/null",
                                 "mac": CMD_BOTH_SHELLS["mac"]}))
ci("a powershell line that starts with export is denied", "deny",
   ci_task(CI_TERMINAL, command={"powershell": "export A=1; git push origin --delete a",
                                 "mac": CMD_BOTH_SHELLS["mac"]}))
# A known program with an argument in backticks is a shell line. A known program alone is prose.
BACKTICK_RUNS = ["Run `make test`", "Run `pytest -q`", "Run `docker compose up`", "Run `mkdir out`",
                 "Run `gcloud auth login`", "Run `bq ls`", "Run `winget install Tool.Id`", "Run `./cleanup.sh`",
                 "Run `./build --release`"]
for step in BACKTICK_RUNS:
    ci("a step with a backticked command and an argument is denied: " + step, "deny", ci_task([step]))
BACKTICK_PROSE = ["Check `git` is installed", "Confirm `node` is 20 or later", "Read the `npm` section"]
for step in BACKTICK_PROSE:
    ci("a step with a known program alone in backticks is allowed: " + step, "allow", ci_task([step]))

# A span or fence is a shell line only when it chains with an operator and starts with a program or cmdlet.
# Text with an operator, a lone quote and a comment opener are no command, and must not hide a real one after them.
ci("a step with a regex span, foo|bar, is allowed", "allow", ci_task(["Search for `foo|bar` in the page"]))
ci("a step with a semicolon span that starts with no program is allowed", "allow",
   ci_task(["Read the `title; subtitle` line on the page"]))
ci("a step with a lone quote in text before a regex span is allowed", "allow",
   ci_task(["Don't search for `foo|bar` in the page"]))
ci("a step with a comment opener inside a span is allowed", "allow", ci_task(["Search for `// a | b` in the page"]))
ci("a step with a markdown table in a multi-line fence is allowed", "allow",
   ci_task(["Check the table:\n```\n| lane | state |\n| N1 | done |\n```"]))
ci("a step with a git log pipe in backticks is denied", "deny", ci_task(["Check the log with `git log | head`"]))
ci("a step with a Get-ChildItem pipe in backticks is denied", "deny",
   ci_task(["Check the list with `Get-ChildItem | Select`"]))
ci("a step with a cd and semicolon line in backticks is denied", "deny", ci_task(["Run `cd x; npm test`"]))
ci("a step with a lone quote before a git log pipe in backticks is denied", "deny",
   ci_task(["Don't run `git log | head` yet"]))
ci("a comment opener span does not hide a git log pipe after it, so the step is denied", "deny",
   ci_task(["Run `// note` then `git log | head`"]))
# A span whose first word no program in the list names still holds a second command after an operator.
for span in ("grep -n x a.py | head", "find . -name x | xargs rm", "yarn install && yarn test",
             "dir | findstr x", "get-process | sort", "env git log | head", "time git log | head",
             "$(git log) | head", "cmd /c git log | head"):
    ci("a step holding `%s` is denied" % span, "deny", ci_task(["Check the output of `%s`" % span]))
ci("a fence holding grep x a | head is denied", "deny", ci_task(["Check the output:\n```\ngrep x a | head\n```"]))


# --------------------------------------------------------------------------- a gh command handed to the owner switches login first

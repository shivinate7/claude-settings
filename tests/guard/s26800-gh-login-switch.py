# section 26800
FAMILY = "gh-login-switch"
#
# The default gh login is shivinate7; ssemwal-cdc is only for a repo shivinate7 cannot reach (decision
# `act-in-place`). A task's `command` runs on the owner's computer, so a gh command in it runs as whichever
# login is active there. The command switches first: `gh auth switch -u <login>` before the first non-auth
# gh command. Why: a handed PATCH needs admin, and the owner could not tell which login would run it.
# A decision is not judged by this rule.

GL_PATCH = ("gh api -X PATCH repos/shivinate7/claude-settings/branches/main/protection/"
            "required_status_checks -f strict=true")
GL_SWITCH = "gh auth switch -u shivinate7"
GL_DOC = "gh-login-main-protection"
GL_TITLE = "Protect main on claude-settings"


def gl(name, expected, mac, ps, carries=(), **over):
    """One task whose `command` is {powershell, mac}, each judged by its own shell's rules. `mac` is bash
    and `ps` is its PowerShell 5.1-safe twin: no `&&`, `||`, `export`, `<<` or `/dev/null`. The steps and
    the Why yours line come from ci_task, the one task builder."""
    item = ci_task(["Open Terminal", "Paste the command below and run it"],
                   **dict({"command": {"powershell": ps, "mac": mac}, "id": GL_DOC, "title": GL_TITLE}, **over))
    wp_write("gh login switch: " + name, expected, "gh-login-switch", item, doc_id=GL_DOC, carries=carries)


gl("today's incident: a branch-protection PATCH with no switch is denied", "deny", GL_PATCH, GL_PATCH)
gl("the refusal names the switch to add", "deny", GL_PATCH, GL_PATCH, carries=("gh auth switch",))
gl("a switch after the gh line is denied", "deny", GL_PATCH + "\n" + GL_SWITCH, GL_PATCH + "\n" + GL_SWITCH)
gl("a cd then gh pr ready, with no switch, is denied", "deny", "cd x && gh pr ready 5", "cd x; gh pr ready 5")
gl("a switch to ssemwal-cdc before a shivinate7/ repo is denied", "deny",
   "gh auth switch -u ssemwal-cdc && " + GL_PATCH, "gh auth switch -u ssemwal-cdc; " + GL_PATCH)
gl("the long form, a switch to ssemwal-cdc before a shivinate7/ repo, is denied", "deny",
   "gh auth switch --user ssemwal-cdc && " + GL_PATCH, "gh auth switch --user ssemwal-cdc; " + GL_PATCH)
gl("a switch to a login outside the pair is denied", "deny",
   "gh auth switch -u someoneelse && gh pr ready 5", "gh auth switch -u someoneelse; gh pr ready 5")
gl("a gh command after a semicolon, with no switch, is denied", "deny", "cd x; gh pr ready 5", "cd x; gh pr ready 5")
gl("a gh command after a pipe, with no switch, is denied", "deny",
   "printf '{}' | gh api -X PUT repos/shivinate7/claude-settings/branches/main/protection --input -",
   "'{}' | gh api -X PUT repos/shivinate7/claude-settings/branches/main/protection --input -")
gl("a gh api piped to a parser, with no switch, is denied", "deny",
   "gh api repos/shivinate7/claude-settings/branches/main/protection | jq .",
   "gh api repos/shivinate7/claude-settings/branches/main/protection | ConvertFrom-Json")
gl("a gh api split by line continuations, with no switch, is denied", "deny",
   "gh api -X PATCH \\\n  repos/shivinate7/claude-settings/branches/main/protection/required_status_checks \\\n  -f strict=true",
   "gh api -X PATCH `\n  repos/shivinate7/claude-settings/branches/main/protection/required_status_checks `\n  -f strict=true")
gl("a # inside quotes does not hide a gh command, with no switch, is denied", "deny",
   'echo "# note" && gh api repos/shivinate7/claude-settings/branches/main/protection',
   'echo "# note"; gh api repos/shivinate7/claude-settings/branches/main/protection')
gl("a # after a quote does not cut off a gh command, with no switch, is denied", "deny",
   'echo "x #" ; gh pr ready 5', 'echo "x #" ; gh pr ready 5')
gl("a gh command after a multi-line quoted argument, with no switch, is denied", "deny",
   'gh pr comment 5 --body "first\nsecond"', 'gh pr comment 5 --body "first\nsecond"')
gl("a switch named inside quotes does not count, so the gh command is denied", "deny",
   'echo "gh auth switch -u shivinate7" && gh pr ready 5', 'echo "gh auth switch -u shivinate7"; gh pr ready 5')
gl("a switch named in a # comment line does not count, so the gh command is denied", "deny",
   "# gh auth switch -u shivinate7\ngh pr ready 5", "# gh auth switch -u shivinate7\ngh pr ready 5")
gl("a lone quote in text before a gh command, with no switch, is denied", "deny",
   "echo Don't && gh pr ready 5", 'echo "Don\'t"; gh pr ready 5')

gl("a switch to shivinate7, then gh api, is allowed", "allow", GL_SWITCH + " && " + GL_PATCH, GL_SWITCH + "; " + GL_PATCH)
gl("the long form, a switch to shivinate7, is allowed", "allow",
   "gh auth switch --user shivinate7 && gh pr ready 5", "gh auth switch --user shivinate7; gh pr ready 5")
gl("a switch and a gh command joined by a semicolon are allowed", "allow",
   GL_SWITCH + "; gh pr ready 5", GL_SWITCH + "; gh pr ready 5")
gl("a cd line, then the switch, then gh, is allowed", "allow",
   "cd x\n" + GL_SWITCH + "\ngh pr ready 5", "cd x\n" + GL_SWITCH + "\ngh pr ready 5")
gl("a # open Git Bash line, then cd, then the switch, then gh, is allowed", "allow",
   "# open Git Bash\ncd x\n" + GL_SWITCH + "\ngh pr ready 5", "# open Git Bash\ncd x\n" + GL_SWITCH + "\ngh pr ready 5")
gl("a switch with no gh command after it is allowed", "allow", GL_SWITCH, GL_SWITCH)
gl("a # comment line holding a gh command is allowed", "allow", "# gh pr ready 5", "# gh pr ready 5")
gl("a gh command echoed as text is allowed", "allow", 'echo "gh pr list"', 'echo "gh pr list"')
gl("a command that is only gh auth login is allowed", "allow", "gh auth login", "gh auth login")
gl("a command with no gh is allowed", "allow", "python3 hooks/test_guard.py", "python3 hooks/test_guard.py")
gl("ghq is not gh and is allowed", "allow", "ghq get x", "ghq get x")
gl("ssemwal-cdc on a repo not under shivinate7 is allowed", "allow",
   "gh auth switch -u ssemwal-cdc && gh api repos/ssemwal-cdc/ops-tools/pulls/5",
   "gh auth switch -u ssemwal-cdc; gh api repos/ssemwal-cdc/ops-tools/pulls/5")
gl("a lone quote in a comment line before the switch is allowed", "allow",
   "# Don't forget\n" + GL_SWITCH + "\ngh pr ready 5", "# Don't forget\n" + GL_SWITCH + "\ngh pr ready 5")
gl("a continued gh api after the switch is allowed", "allow",
   GL_SWITCH + "\ngh api -X PATCH \\\n  repos/shivinate7/claude-settings/branches/main/protection/required_status_checks \\\n  -f strict=true",
   GL_SWITCH + "\ngh api -X PATCH `\n  repos/shivinate7/claude-settings/branches/main/protection/required_status_checks `\n  -f strict=true")
gl("a multi-line quoted argument after the switch is allowed", "allow",
   GL_SWITCH + '\ngh pr comment 5 --body "first\nsecond"', GL_SWITCH + '\ngh pr comment 5 --body "first\nsecond"')

# Cases for PowerShell paths, gh text in a quoted body, a lone quote, sudo and env wrappers, and a
# bare fallback switch. The PowerShell lines are raw strings, so each backslash is literal.
# The mac twin of a PowerShell path uses forward slashes: bash would read `"C:\repo\"` as an open quote.
gl("a PowerShell Set-Location to a path with a trailing backslash in quotes, then the switch, then gh, is allowed",
   "allow", 'cd "/repo/"\n' + GL_SWITCH + "\ngh pr view 5", r'Set-Location "C:\repo\"' + "\n" + GL_SWITCH + "\ngh pr view 5")
gl("a PowerShell cd to a backslash path, then the switch, then gh, is allowed", "allow",
   "cd /Users/me/repo\n" + GL_SWITCH + "\ngh pr view 5", r"cd C:\Users\me\repo" + "\n" + GL_SWITCH + "\ngh pr view 5")
gl("a PowerShell Set-Location to a path with a trailing backslash, then gh with no switch, is denied", "deny",
   'cd "/repo/"\ngh pr view 5', r'Set-Location "C:\repo\"' + "\ngh pr view 5")
gl("a multi-line quoted body that holds gh text, after the switch, is allowed", "allow",
   GL_SWITCH + '\ngh pr comment 5 --body "first\ngh pr merge 5\nsecond"',
   GL_SWITCH + '\ngh pr comment 5 --body "first\ngh pr merge 5\nsecond"')
gl("a lone quote in text after the switch is allowed", "allow",
   GL_SWITCH + "\necho Don't\ngh pr ready 5", GL_SWITCH + '\necho "Don\'t"\ngh pr ready 5')
gl("sudo gh after the switch is allowed", "allow", GL_SWITCH + " && sudo gh pr ready 5", GL_SWITCH + "; sudo gh pr ready 5")
gl("sudo gh with no switch is denied", "deny", "sudo gh pr ready 5", "sudo gh pr ready 5")
gl("env GH_HOST=x gh after the switch is allowed", "allow",
   GL_SWITCH + " && env GH_HOST=x gh pr ready 5", GL_SWITCH + "; env GH_HOST=x gh pr ready 5")
gl("env GH_HOST=x gh with no switch is denied", "deny", "env GH_HOST=x gh pr ready 5", "env GH_HOST=x gh pr ready 5")
gl("a bare switch to ssemwal-cdc, then gh api on a shivinate7 repo, one per line, is denied", "deny",
   "gh auth switch -u ssemwal-cdc\ngh api repos/shivinate7/x", "gh auth switch -u ssemwal-cdc\ngh api repos/shivinate7/x")

# Deny pins: each shell judges its own text. A switch in one shell does not stand for the other.
gl("a switch to shivinate7 in mac only is denied", "deny", GL_SWITCH + " && " + GL_PATCH, GL_PATCH)
gl("a switch to shivinate7 in powershell only is denied", "deny", GL_PATCH, GL_SWITCH + "; " + GL_PATCH)
gl("ssemwal-cdc on a shivinate7/ repo in mac only is denied", "deny",
   "gh auth switch -u ssemwal-cdc && " + GL_PATCH, GL_SWITCH + "; " + GL_PATCH)
gl("ssemwal-cdc on a shivinate7/ repo in powershell only is denied", "deny",
   GL_SWITCH + " && " + GL_PATCH, "gh auth switch -u ssemwal-cdc; " + GL_PATCH)
gl("ssemwal-cdc on a repo not under shivinate7 in powershell only is allowed", "allow",
   GL_SWITCH + " && gh api repos/shivinate7/x", "gh auth switch -u ssemwal-cdc; gh api repos/ssemwal-cdc/ops-tools/pulls/5")

# A decision is not judged: it carries the command, with the form lines and gain and lose, and no switch.
wp_write("gh login switch: a decision that holds a gh command with no switch is not judged", "allow", "gh-login-switch",
         {"id": GL_DOC, "kind": "decision", "status": "open", "title": "Protect main on claude-settings?",
          "context": OJ_FORM + "\n" + QD_LINE + "\nThe branch rule needs admin, and the active login decides who can run it.",
          "command": {"powershell": GL_PATCH, "mac": GL_PATCH},
          "options": [{"key": "a", "label": "Apply the rule", "how": "Run the command the item holds.",
                       "gain": "g", "lose": "l"},
                      {"key": "b", "label": "Keep it", "how": "Do nothing yet.", "gain": "g", "lose": "l"}]},
         doc_id=GL_DOC)

# A str_replace on the task's `command` is judged on the text that replaces old_str.
wp_write("gh login switch: a str_replace that adds a gh command with no switch to command is denied", "deny",
         "gh-login-switch", None, action="str_replace", doc_id=GL_DOC, field="command",
         old_str="step one", new_str="step one\ngh pr merge 5")
wp_write("gh login switch: a str_replace on command that adds a switch, then gh, is allowed", "allow",
         "gh-login-switch", None, action="str_replace", doc_id=GL_DOC, field="command",
         old_str="step one", new_str=GL_SWITCH + "\ngh pr merge 5")
wp_write("gh login switch: a str_replace on command with no gh text is allowed", "allow",
         "gh-login-switch", None, action="str_replace", doc_id=GL_DOC, field="command",
         old_str="step one", new_str="step two")
# A gh line changed to another gh line adds no gh line, so the switch the stored command holds still stands.
wp_write("gh login switch: a str_replace that changes one gh line to another, on a command that keeps its switch, is allowed",
         "allow", "gh-login-switch", None, action="str_replace", doc_id=GL_DOC, field="command",
         old_str="gh pr view 3", new_str="gh pr view 4")
wp_write("gh login switch: a str_replace that removes the switch and leaves a gh line is denied", "deny",
         "gh-login-switch", None, action="str_replace", doc_id=GL_DOC, field="command",
         old_str="gh auth switch -u shivinate7\ngh pr view 3", new_str="gh pr view 3")
wp_write("gh login switch: a str_replace that adds a gh line beside a gh line, with no switch, is denied", "deny",
         "gh-login-switch", None, action="str_replace", doc_id=GL_DOC, field="command",
         old_str="gh pr view 3", new_str="gh pr view 3\ngh pr merge 3")
wp_write("gh login switch: a str_replace that adds a -R shivinate7/ repo to a gh line is denied", "deny",
         "gh-login-switch", None, action="str_replace", doc_id=GL_DOC, field="command",
         old_str="gh pr view 3", new_str="gh pr view 3 -R shivinate7/repo")


# --------------------------------------------------------------------------- a task names the check that showed only the owner can do it

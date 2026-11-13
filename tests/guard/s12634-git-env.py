# section 12634
FAMILY = "git-env"  # GIT_ENV_RULE, the rule id, is set in the shared-tree section above
FAMILIES["git-env"] = "a command that sets GIT_DIR, GIT_WORK_TREE or GIT_INDEX_FILE"
_GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")

# A per-file restore from a worktree, with a GIT_WORK_TREE setter in front of it: a bash prefix row,
# a lower-case prefix row, a bare-name export row and one PowerShell $env: row. The loops below set
# each variable alone.
sh("per-file deny: GIT_WORK_TREE set to the shared checkout by a prefix assignment, from a worktree",
   "GIT_WORK_TREE=" + slash(GITMAIN) + " " + VCS + " restore f.txt", "deny", GIT_ENV_RULE,
   cwd=GITWT)
sh("per-file deny: late probe, lower-case git_work_tree prefix sets GIT_WORK_TREE to the shared "
   "checkout, from a worktree",
   "git_work_tree=" + slash(GITMAIN) + " " + VCS + " restore f.txt", "deny", GIT_ENV_RULE,
   cwd=GITWT)
sh("per-file deny: late probe, read -r then export sets GIT_WORK_TREE to the shared checkout, "
   "from a worktree",
   "read -r GIT_WORK_TREE <<< \"" + slash(GITMAIN) + "\"; export GIT_WORK_TREE; " + VCS
   + " restore f.txt", "deny", GIT_ENV_RULE, cwd=GITWT)
sh("per-file deny: late probe, PowerShell $env: assignment sets GIT_WORK_TREE to the shared checkout",
   '$env:GIT_WORK_TREE = "' + slash(GITMAIN) + '"; ' + VCS + " restore f.txt", "deny",
   GIT_ENV_RULE, tool="PowerShell", cwd=GITWT)

# Bash forms that set one of the three. The tail is a harmless test run, so the setter decides.
for _name in _GIT_ENV_VARS:
    for _label, _cmd in (
        ("export", "export %s=/x; python -m pytest" % _name),
        ("export with +=", "export %s+=/x; python -m pytest" % _name),
        ("a prefix assignment", "%s=/x python -m pytest" % _name),
        ("env", "env %s=/x python -m pytest" % _name),
        ("declare -x", "declare -x %s=/x; python -m pytest" % _name),
    ):
        sh("git env set: Bash %s by %s, denies" % (_name, _label), _cmd, "deny", GIT_ENV_RULE,
           cwd=NOGIT)
sh("git env set: the incident shape in Bash, two variables exported before a test run, denies",
   "export GIT_DIR=/c/x/.git GIT_WORK_TREE=/c/scratch; python -m pytest", "deny", GIT_ENV_RULE,
   cwd=NOGIT)
sh("git env set: the incident shape in Bash, two prefixes on a test run, denies",
   "GIT_DIR=/c/x/.git GIT_WORK_TREE=/c/scratch python -m pytest", "deny", GIT_ENV_RULE, cwd=NOGIT)

# PowerShell forms that set one of the three: the env drive in every spelling, and the ni alias.
# The full New-Item cmdlet is in the split-name rows below.
for _cmd in (
    r'$env:GIT_DIR = "C:\x\.git"; python -m pytest',
    r'$env:GIT_WORK_TREE = "C:\scratch"; python -m pytest',
    r'$env:GIT_INDEX_FILE = "C:\x\index"; python -m pytest',
    r'$env:GIT_DIR += ";C:\x\.git"; python -m pytest',
    r'$env:git_dir = "C:\x\.git"; python -m pytest',
    r'${env:GIT_WORK_TREE} = "C:\scratch"; python -m pytest',
    r'[Environment]::SetEnvironmentVariable("GIT_DIR", "C:\x\.git", "Process"); python -m pytest',
    r'Set-Item env:GIT_INDEX_FILE "C:\x\index"; python -m pytest',
    r'ni env:GIT_DIR -Value C:\x\.git; python -m pytest',
):
    sh("git env set: PowerShell %s, denies" % _cmd.split(";")[0][:40], _cmd, "deny", GIT_ENV_RULE,
       tool="PowerShell", cwd=NOGIT)
sh("git env set: the incident shape in PowerShell, two variables set before a test run, denies",
   r'$env:GIT_DIR = "C:\x\.git"; $env:GIT_WORK_TREE = "C:\scratch"; python -m pytest',
   "deny", GIT_ENV_RULE, tool="PowerShell", cwd=NOGIT)

# Scanner cases: a comment opener, a lone quote, and a newline inside a string must not hide the
# setter that follows them (building-scanner-respects-strings).
sh('git env set: a hash opener inside quotes does not hide a Bash setter, denies',
   'echo "# note"; export GIT_DIR=/x; python -m pytest', "deny", GIT_ENV_RULE, cwd=NOGIT)
sh('git env set: a double slash inside quotes does not hide a Bash setter, denies',
   'echo "// note"; export GIT_WORK_TREE=/x; python -m pytest', "deny", GIT_ENV_RULE, cwd=NOGIT)
sh('git env set: a slash-star inside quotes does not hide a Bash setter, denies',
   'echo "/* note"; export GIT_INDEX_FILE=/x; python -m pytest', "deny", GIT_ENV_RULE, cwd=NOGIT)
sh("git env set: a lone apostrophe inside double quotes does not hide a Bash setter, denies",
   "echo \"Don't\"; export GIT_DIR=/x; python -m pytest", "deny", GIT_ENV_RULE, cwd=NOGIT)
sh("git env set: a lone apostrophe in unquoted text does not hide a Bash setter, denies",
   "echo don't; export GIT_DIR=/x; python -m pytest", "deny", GIT_ENV_RULE, cwd=NOGIT)
sh("git env set: a newline inside a quoted string does not hide a setter on the next line, denies",
   "echo \"first line\nsecond line\"\nexport GIT_DIR=/x\npython -m pytest", "deny", GIT_ENV_RULE,
   cwd=NOGIT)
sh("git env set: a commit message ending in a newline does not hide a setter after it, denies",
   VCS + ' commit -m "note\nline"\nexport GIT_WORK_TREE=/x; python -m pytest', "deny",
   GIT_ENV_RULE, cwd=NOGIT)
sh("git env set: a PowerShell here-string does not hide a setter on the next line, denies",
   "@'\nnote about the variable\n'@\n$env:GIT_DIR = \"C:\\x\\.git\"", "deny", GIT_ENV_RULE,
   tool="PowerShell", cwd=NOGIT)

# Allow: the same spellings when they only name the variable, print it, or read it.
sh('git env set: a hash opener in quotes that only names the variable, allowed',
   'echo "# export GIT_DIR=/x"', "allow", cwd=NOGIT)
sh("git env set: a quoted apostrophe that only names the variable, allowed",
   "echo \"Don't mention GIT_DIR\"", "allow", cwd=NOGIT)
sh("git env set: a quoted echo of a setter line prints it and sets nothing, allowed",
   'echo "export GIT_DIR=/x"', "allow", cwd=NOGIT)
sh("git env set: a commit message that only names the variables, allowed",
   VCS + ' commit -m "doc\nexport GIT_DIR=/x and GIT_WORK_TREE in the message"', "allow",
   cwd=NOGIT)
sh("git env set: a PowerShell here-string that only names the variable, allowed",
   "@'\nexport GIT_DIR=/x\n'@", "allow", tool="PowerShell", cwd=NOGIT)

# Allow: reads and unsets, a git variable outside the list, and names that only start the same.
for _cmd in (
    "echo $GIT_DIR",
    'echo "$GIT_WORK_TREE"',
    "unset GIT_DIR; python -m pytest",
    "unset GIT_WORK_TREE GIT_INDEX_FILE; python -m pytest",
    "env -u GIT_DIR python -m pytest",
    "GIT_TRACE=1 " + VCS + " rev-parse --git-dir",
    "GIT_DIRX=1 python -m pytest",
    "MYGIT_DIR=1 python -m pytest",
    "export FOO=bar; python -m pytest",
):
    sh("git env set: Bash allowed, %s" % _cmd[:40], _cmd, "allow", cwd=NOGIT)
for _cmd in (
    r"$env:GIT_DIR",
    r"Write-Output $env:GIT_WORK_TREE",
    r"Remove-Item env:GIT_DIR",
    r"Remove-Item Env:GIT_INDEX_FILE",
    r'$env:GIT_DIRX = "1"; python -m pytest',
    r'$env:MYGIT_DIR = "1"; python -m pytest',
    r'$env:GIT_TRACE = "1"; python -m pytest',
    r"Select-String '$env:GIT_DIR = ' f.ps1",
):
    sh("git env set: PowerShell allowed, %s" % _cmd[:40], _cmd, "allow", tool="PowerShell",
       cwd=NOGIT)

# A set inside a substitution, a backtick, a negation, a wrapper, a
# script block, a persistent setter or cmd /c. The guard is for accidental sets, not an attacker, so
# each form is pinned by name and no more.
for _cmd in (
    "echo $(GIT_DIR=x " + VCS + " init)",
    "echo `GIT_DIR=x " + VCS + " init`",
    '"$(GIT_WORK_TREE=x ' + VCS + ' status)"',
    "! GIT_DIR=x " + VCS + " init",
    "nice -n 5 env GIT_DIR=x " + VCS + " init",
):
    sh("git env set: Bash, a set in front of a git call, %s" % _cmd[:40], _cmd, "deny",
       GIT_ENV_RULE, cwd=NOGIT)
for _cmd in (
    r"& { $env:GIT_DIR='x'; " + VCS + " init }",
    r"Invoke-Command -ScriptBlock { $env:GIT_WORK_TREE='x' }",
    "setx GIT_DIR x",
):
    sh("git env set: PowerShell, a set in a script block or a setter, %s" % _cmd[:40], _cmd,
       "deny", GIT_ENV_RULE, tool="PowerShell", cwd=NOGIT)
sh("git env set: cmd /c set, then a git call, denies",
   "cmd /c set GIT_DIR=x && " + VCS + " init", "deny", GIT_ENV_RULE, cwd=NOGIT)
sh("git env set: export -n only drops the export attribute, allowed",
   "export -n GIT_DIR", "allow", cwd=NOGIT)

# A set inside a PowerShell block (if, foreach, a pipeline's block, try),
# a set in a parenthesised assignment, a set in a pwsh -c string, a set after the value, and a set in
# a bash heredoc. The heredoc runs its substitution only when the delimiter is unquoted.
for _cmd in (
    r"if ($true) {$env:GIT_DIR='x'}",
    r"foreach ($i in 1) {$env:GIT_DIR='x'}",
    r"1 | ForEach-Object {$env:GIT_DIR='x'}",
    r"try {$env:GIT_DIR='x'} finally {}",
    r"($env:GIT_DIR='x')",
):
    sh("git env set: PowerShell, a set in a block or a group, %s" % _cmd[:40], _cmd, "deny",
       GIT_ENV_RULE, tool="PowerShell", cwd=NOGIT)
sh("git env set: pwsh -c with a set inside an if block, denies",
   "pwsh -c \"if ($true) {$env:GIT_DIR='x'}\"", "deny", GIT_ENV_RULE, cwd=NOGIT)
sh("git env set: Bash export with -n after the value, denies",
   "export GIT_DIR=x -n", "deny", GIT_ENV_RULE, cwd=NOGIT)
sh("git env set: Bash unquoted heredoc runs a substitution with a set, denies",
   "cat <<EOF\n$(GIT_DIR=x " + VCS + " init)\nEOF", "deny", GIT_ENV_RULE, cwd=NOGIT)
sh("git env set: Bash quoted heredoc runs no substitution, allowed",
   "cat <<'EOF'\n$(GIT_DIR=x " + VCS + " init)\nEOF", "allow", cwd=NOGIT)

# A PowerShell block opener glued to its word hides the set inside it from
# the guard. The spaced forms deny in the PowerShell-block cases above. One template per
# opener: `@@` takes the set for the deny case and a body that sets nothing for the allow case, so
# each form has both directions. A glued opener the guard must read, and one it must leave alone.
# Three openers, one per tokenizer shape: a symbol alias (`%{`), a keyword after a paren (`if (...){`),
# and an assignment (`$sb={`). Each has a deny and an allow.
_GLUED_OPENERS = (
    ("pipeline %{", "1..2|%{@@}"),
    ("if ($t){", "if ($t){@@}"),
    ("$sb={", "$sb={@@}; & $sb"),
)
for _label, _template in _GLUED_OPENERS:
    sh("git env set: PowerShell, a set in a glued %s block, denies" % _label,
       _template.replace("@@", "$env:GIT_DIR='x'"), "deny", GIT_ENV_RULE, tool="PowerShell",
       cwd=NOGIT)
    sh("git env set: PowerShell, a glued %s block that sets nothing, allowed" % _label,
       _template.replace("@@", "$_"), "allow", tool="PowerShell", cwd=NOGIT)
# The same three openers, a space before the set.
for _label, _template in _GLUED_OPENERS:
    sh("git env set: PowerShell, a set after a space in a glued %s block, denies" % _label,
       _template.replace("@@", " $env:GIT_DIR='x' "), "deny", GIT_ENV_RULE, tool="PowerShell",
       cwd=NOGIT)
sh("git env set: Bash, pwsh -c with a space before the set in a glued block, denies",
   """pwsh -c 'if(1){ $env:GIT_DIR="x" }'""", "deny", GIT_ENV_RULE, cwd=NOGIT)
# A double-quoted here-string (`@"..."@`) expands its
# `$( )`, so a set inside it runs and denies. A single-quoted one (`@'...'@`) is text: the same set
# in it allows, and so does a double-quoted one that holds no set.
for _label, _text in (
    ("a bare here-string", '''@"\n$($env:GIT_DIR='x')\n"@'''),
    ("after a command word", '''Write-Host @"\nline one\n$($env:GIT_DIR='x')\n"@'''),
    ("with an apostrophe line ahead of the set", '''@"\ndon't\n$($env:GIT_DIR='x')\n"@'''),
):
    sh("git env set: PowerShell, a set in a $( ) of a double-quoted here-string, %s, denies"
       % _label, _text, "deny", GIT_ENV_RULE, tool="PowerShell", cwd=NOGIT)
sh("git env set: PowerShell, a double-quoted here-string that holds no set, allowed",
   '@"\nplain text, no set\n"@', "allow", tool="PowerShell", cwd=NOGIT)
for _label, _text in (
    ("a $( ) set", "@'\n$($env:GIT_DIR='x')\n'@"),
    ("a glued pipeline block", "@'\n1..2|%{$env:GIT_DIR='x'}\n'@"),
    ("a glued if block with a space before the set", "@'\nif($t){ $env:GIT_DIR='x' }\n'@"),
):
    sh("git env set: PowerShell, a single-quoted here-string that holds %s as text, allowed"
       % _label, _text, "allow", tool="PowerShell", cwd=NOGIT)
# Control: the spaced spelling of the three openers the PowerShell-block cases above do not cover.
for _cmd in (
    "if (0) {1} else {$env:GIT_DIR='x'}",
    "do {$env:GIT_DIR='x'} while (0)",
    "$sb = {$env:GIT_DIR='x'}; & $sb",
):
    sh("git env set: PowerShell, a set in a spaced block, %s, denies" % _cmd[:30], _cmd, "deny",
       GIT_ENV_RULE, tool="PowerShell", cwd=NOGIT)
# A cmdlet set and a lower-case name inside a glued block. The other names take the same branch.
for _cmd in (
    "1..2|%{Set-Item env:GIT_DIR x}",
    "if($t){$env:git_dir='x'}",
):
    sh("git env set: PowerShell, a glued block with %s, denies" % _cmd.split("{")[1][:26], _cmd,
       "deny", GIT_ENV_RULE, tool="PowerShell", cwd=NOGIT)
# Allow: a glued block that only reads the name, unsets it, sets another, or holds it as text.
for _cmd in (
    "1..2|%{$env:GIT_DIR}",
    "1..2|%{$env:GIT_DIR=$null}",
    "if($t){Remove-Item env:GIT_DIR}",
    "Write-Host 'if($t){$env:GIT_DIR=1}'",
    'Write-Host "# 1..2|%{$env:GIT_DIR=1}"',
    'Write-Host "first line\n1..2|%{$env:GIT_DIR=1}\nlast line"',
    "@'\n1..2|%{$env:GIT_DIR=1}\n'@",
):
    sh("git env set: PowerShell, a glued block that does not set, allowed, %s" % _cmd[:36].replace(
        "\n", " "), _cmd, "allow", tool="PowerShell", cwd=NOGIT)
# Scanner cases (building-scanner-respects-strings): a comment opener, a lone apostrophe, a
# newline inside a string and a here-string ahead of a glued set must not hide it.
for _label, _head in (
    ("a hash opener in quotes", 'Write-Host "# note"; '),
    ("a double slash in quotes", 'Write-Host "// note"; '),
    ("a slash-star in quotes", 'Write-Host "/* note"; '),
    ("a lone apostrophe in double quotes", 'Write-Host "Don\'t"; '),
    ("a newline inside a quoted string", 'Write-Host "first line\nsecond line"\n'),
    ("a multi-line here-string", "@'\nnote about a block {x}\n'@\n"),
):
    sh("git env set: PowerShell, %s does not hide a glued set, denies" % _label,
       _head + "1..2|%{$env:GIT_DIR='x'}", "deny", GIT_ENV_RULE, tool="PowerShell", cwd=NOGIT)
# Bash `pwsh -c` reads the same glued blocks, and the same scanner cases hold before it.
for _label, _head in (
    ("no text ahead", ""),
    ("a hash opener in quotes", 'echo "# note"; '),
    ("a lone apostrophe in double quotes", 'echo "Don\'t"; '),
    ("a lone apostrophe in unquoted text", "echo don't; "),
    ("a newline inside a quoted string", 'echo "first line\nsecond line"\n'),
):
    sh("git env set: Bash, pwsh -c with a glued if block, %s, denies" % _label,
       _head + """pwsh -c 'if(1){$env:GIT_DIR="x"}'""", "deny", GIT_ENV_RULE, cwd=NOGIT)
sh("git env set: Bash, pwsh -c with a glued pipeline block, denies",
   """pwsh -c '1..2|%{$env:GIT_DIR="x"}'""", "deny", GIT_ENV_RULE, cwd=NOGIT)
sh("git env set: Bash, pwsh -c with a glued if block that sets nothing, allowed",
   "pwsh -c 'if(1){$_}'", "allow", cwd=NOGIT)
sh("git env set: Bash, a quoted pwsh -c line that only names a glued set, allowed",
   """echo 'pwsh -c "if(1){$env:GIT_DIR=1}"'""", "allow", cwd=NOGIT)

# The backtick pins are PowerShell: the outer shell takes the escape before pwsh runs the script, and in
# Bash a backtick opens a substitution. The heredoc pins are Bash: an apostrophe in an unquoted body
# is text, so the later substitution still runs, and a quoted delimiter runs none.
sh("git env set: PowerShell, pwsh -c with a backtick-escaped $env inside an if block, denies",
   "pwsh -c \"if (1) {`$env:GIT_DIR='x'}\"", "deny", GIT_ENV_RULE, tool="PowerShell", cwd=NOGIT)
sh("git env set: PowerShell, a backtick-escaped quote keeps the rest of the string text, allowed",
   'Write-Host "a `" b $env:GIT_DIR=1"', "allow", tool="PowerShell", cwd=NOGIT)
sh("git env set: Bash unquoted heredoc body with an apostrophe, then a set substitution, denies",
   "cat <<EOF\ndon't\n$(export GIT_DIR=x)\nEOF", "deny", GIT_ENV_RULE, cwd=NOGIT)
sh("git env set: Bash quoted heredoc body with an apostrophe, then a set substitution, allowed",
   "cat <<'EOF'\ndon't\n$(export GIT_DIR=x)\nEOF", "allow", cwd=NOGIT)
# The shared group-opener pattern (`&{`, `.{`, `$(`, `@(`), glued: pinned, so a new opener rule
# cannot drop one of them.
for _cmd in (
    "&{$env:GIT_DIR='x'}",
    ".{$env:GIT_DIR='x'}",
    "$($env:GIT_DIR='x')",
    "@($env:GIT_DIR='x')",
):
    sh("git env set: PowerShell, a glued group opener, %s, denies" % _cmd[:12], _cmd, "deny",
       GIT_ENV_RULE, tool="PowerShell", cwd=NOGIT)
# A name split by a substitution. The walk reads each
# `$(...)` as `x`, so `GIT_INDE$(echo X)_FILE` reads as `GIT_INDEx_FILE`, and the case fold makes
# that the watched name. The raw text holds no whole name, so a quick test of the raw text must not
# skip the walk.
# KNOWN LIMIT: GIT_DIR and GIT_WORK_TREE hold no X, so no substitution builds either name, and the
# walk allows their split forms. A bare split assignment with no command after
# it is allowed too (a bare name in capitals is denied only when it is written whole).
_SPLIT = "GIT_INDE$(echo X)_FILE"
sh("git env set: Bash, a name split by a substitution, export, denies",
   "export %s=/x; python -m pytest" % _SPLIT, "deny", GIT_ENV_RULE, cwd=NOGIT)
sh("git env set: Bash, a name split by a substitution, typeset -x, denies",
   "typeset -x %s=/x; python -m pytest" % _SPLIT, "deny", GIT_ENV_RULE, cwd=NOGIT)
sh("git env set: PowerShell, a name split by a substitution, New-Item, denies",
   r"New-Item env:%s -Value C:\x\index; python -m pytest" % _SPLIT, "deny", GIT_ENV_RULE,
   tool="PowerShell", cwd=NOGIT)

# A name split by a printf directive. `%s` and `%b` with
# no argument print nothing, so the profile gets `GIT_DIR=/x`. The walk drops the directives
# (`_PRINTF_DIRECTIVE`) before it reads the name, so the raw text holds no whole name and a quick
# test of the raw text or of a substitution's text must not skip the walk.
sh("git env set: Bash printf into a profile, a name split by a printf directive, denies",
   r"printf 'GIT_%sDIR=/x\n' >> ~/.bashrc", "deny", GIT_ENV_RULE, cwd=NOGIT)

# The quick test cannot read a printf directive by a strip over the whole text, in either order with
# `QUOTE_MARKS`. Each case below pins one way a whole-text strip under-matches, so the quick test
# sends any printf on to the walk.
sh("git env set: Bash, a percent sign and a space before a set, no printf, denies",
   "x=5% GIT_DIR=/x " + VCS + " status", "deny", GIT_ENV_RULE, cwd=NOGIT)   # `% G` is no directive
sh("git env set: Bash printf into a profile, a directive split by adjacent quotes, denies",
   r"printf 'GIT_%''sDIR=/x\n' >> ~/.bashrc", "deny", GIT_ENV_RULE, cwd=NOGIT)
# KNOWN LIMIT: printf reads `\n` in this argument as a newline, so the file gets `GIT_` and
# `DIR=/x` and sets nothing. The walk drops `\n` as a directive and denies: a false deny on the
# safe side, pinned.
sh("git env set: Bash printf into a profile, a doubled backslash before n inside a name, denies",
   r"printf GIT_\\nDIR=/x >> ~/.bashrc", "deny", GIT_ENV_RULE, cwd=NOGIT)

# =========================================================================== hook bypass
# A git commit, merge or push that skips the git hooks is denied under rule hook-bypass. Five spellings of
# one act: `-c core.hooksPath=...` on the command (the key in any case), `--no-verify` on commit, merge or
# push, `-n` on commit alone, and the key set in the environment through GIT_CONFIG_COUNT or
# GIT_CONFIG_PARAMETERS. `-n` is no bypass on push (--dry-run) or on merge (--no-stat), so both stay allowed.
# The glued form `-ccore.hooksPath=x` is no spelling: git 2.43.0 refuses it as an unknown option, so no case
# names it.
#
# Each deny has a green control beside it: the same command with the bypass taken out. A control that is not
# allowed means another rule fires on that shape, so the deny beside it proves nothing about this rule.
# The hooks path is `x`, a value no hook lives at, so the key alone decides, except in the one env case that
# names /dev/null, as git's own examples do.

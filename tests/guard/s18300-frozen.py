# section 18300
FAMILY = "frozen"
#
# The sed operand reader. The frozen-path rule must refuse a write to a frozen file whatever flags,
# wrapper, `w` command, delimiter or pipe feed the `sed` takes, and must allow a sed that only names
# the file as text or reads it. Each CONTROL pins a form the rule refuses or allows. The cost of a
# long command is judged in section 35200.
#
# Failure classes, one per group: flag-cluster, flag-suffix, flag-long, flag-after-operand,
# w-command, wrapper, pipe-feed, false-alarm, script-as-target, script-file, scanner-strings,
# delimiter, quoted-command.

# --- flag-cluster: -i inside a cluster of short flags is a write (class: flag-cluster) ---
sh("sed-operand flag-cluster: sed -ni onto a frozen hook is refused",
   "sed -ni 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand flag-cluster: sed -Ei onto a frozen hook is refused",
   "sed -Ei 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand flag-cluster: sed -i -e onto a frozen hook stays refused",
   "sed -i -e 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand flag-cluster: sed -E -i onto a frozen hook stays refused",
   "sed -E -i 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)

# --- flag-suffix: -i takes an attached suffix, so -ie is -i with suffix e (class: flag-suffix) ---
sh("sed-operand flag-suffix: sed -ie is -i with suffix e, onto a frozen hook is refused",
   "sed -ie 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand flag-suffix: sed -i.bak onto a frozen hook stays refused",
   "sed -i.bak 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)

# --- flag-long: the long form with an attached suffix (class: flag-long) ---
sh("sed-operand flag-long: sed --in-place=.bak onto a frozen hook is refused",
   "sed --in-place=.bak 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)

# --- flag-after-operand: GNU sed permutes options, so -i may follow the file (class: flag-after-operand) ---
sh("sed-operand flag-after-operand: sed script and file, then -i, onto a frozen hook is refused",
   "sed 's/a/b/' " + CFG_HOOK + " -i", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand flag-after-operand: sed script and file, then -i.bak, onto a frozen hook is refused",
   "sed 's/a/b/' " + CFG_HOOK + " -i.bak", "deny", "frozen-path", cwd=NOGIT)

# --- w-command: the w command writes the file it names, with or without -i (class: w-command) ---
sh("sed-operand w-command: sed -n with a w to a frozen hook is refused",
   "sed -n 'w " + CFG_HOOK + "' x", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand w-command: sed s with a w flag to a frozen hook is refused",
   "sed 's/a/b/w " + CFG_HOOK + "' x", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand w-command control: sed -n p reads a frozen hook and is allowed",
   "sed -n 'p' " + CFG_HOOK, "allow", cwd=NOGIT)
sh("sed-operand w-command control: sed with no -i reads a frozen hook and is allowed",
   "sed 's/a/b/' " + CFG_HOOK, "allow", cwd=NOGIT)

# --- false-alarm: a frozen path in a script's text, where the text starts with w, is no write (class: false-alarm) ---
sh("sed-operand false-alarm: a frozen hook in an s replacement that starts with w, with no -i, is allowed",
   "sed 's/x/w " + CFG_HOOK + "/' other.txt", "allow", cwd=NOGIT)
sh("sed-operand false-alarm: a frozen hook in an a text that starts with w, with no -i, is allowed",
   "sed '$a w " + CFG_HOOK + "' other.txt", "allow", cwd=NOGIT)
sh("sed-operand false-alarm: a frozen hook in an i text that starts with w, with -n and no -i, is allowed",
   "sed -n '1i w " + CFG_HOOK + "' other.txt", "allow", cwd=NOGIT)

# --- wrapper: a shell, sudo, xargs or find that runs sed (class: wrapper) ---
sh("sed-operand wrapper control: sudo sed -i onto a frozen hook stays refused",
   "sudo sed -i 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand wrapper control: xargs sed -i onto a frozen hook stays refused",
   "xargs sed -i 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand wrapper control: find -exec sed -i onto a frozen hook stays refused",
   "find . -exec sed -i 's/a/b/' " + CFG_HOOK + " \\;", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand wrapper control: bash -c sed -i onto a frozen hook stays refused",
   "bash -c \"sed -i 's/a/b/' " + CFG_HOOK + "\"", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand wrapper control: bash -c with -i after the file stays refused",
   "bash -c \"sed 's/a/b/' " + CFG_HOOK + " -i\"", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand wrapper: sudo sed -ni onto a frozen hook is refused",
   "sudo sed -ni 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand wrapper: bash -c sed -ni onto a frozen hook is refused",
   "bash -c \"sed -ni 's/a/b/' " + CFG_HOOK + "\"", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand wrapper: bash -c sed -n with a w to a frozen hook is refused",
   "bash -c \"sed -n 'w " + CFG_HOOK + "' x\"", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand wrapper: a frozen hook piped to xargs sed -i is refused",
   "printf '%s\\n' " + CFG_HOOK + " | xargs sed -i 's/a/b/'", "deny", "frozen-path", cwd=NOGIT)
add("sed-operand wrapper: find -exec sed -i in the frozen hooks folder is refused", "deny", "frozen-path",
    tool="Bash", cwd=DUP_HOOKS_CWD, command="find . -name guard.py -exec sed -i 's/a/b/' {} +")

# --- pipe-feed: xargs sed -i takes its files from the list a grep prints, so a grep that names a frozen path feeds a write (class: pipe-feed) ---
sh("sed-operand pipe-feed: grep -l naming a frozen hook, piped to xargs sed -i, is refused",
   "grep -l guard " + CFG_HOOK + " | xargs sed -i 's/a/b/g'", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand pipe-feed: grep -rl naming the frozen hooks folder, piped to xargs sed -i, is refused",
   "grep -rl guard " + slash(os.path.join(CFG, "hooks")) + " | xargs sed -i 's/a/b/g'", "deny", "frozen-path", cwd=NOGIT)

# --- script-as-target: a frozen path inside a sed script is text, not a write target (class: script-as-target) ---
sh("sed-operand script-as-target: a frozen path in a script with no -i is text and is allowed",
   "sed -i 's#x#y#' other.txt", "allow", cwd=NOGIT)
sh("sed-operand script-as-target: a frozen path in a script, target another file, is allowed",
   "sed -i 's#x#" + CFG_HOOK + "#' other.txt", "allow", cwd=NOGIT)
sh("sed-operand script-as-target: a relative hooks/guard.py in a script, target another file, is allowed",
   "sed -i 's#x#hooks/guard.py#' other.txt", "allow", cwd=CFG)
sh("sed-operand script-as-target: a frozen path after a space in a script, target another file, is allowed",
   "sed -i 's#old# see " + CFG_HOOK + " #' other.txt", "allow", cwd=NOGIT)

# --- script-file: sed -f reads a script file, it does not write it (class: script-file) ---
sh("sed-operand script-file: sed -i -f a frozen hook reads it and is allowed",
   "sed -i -f " + CFG_HOOK + " other.txt", "allow", cwd=NOGIT)

# --- scanner-strings: a comment opener or a lone quote inside a sed script (class: scanner-strings) ---
sh("sed-operand scanner-strings control: # as the s delimiter, onto a frozen hook stays refused",
   "sed -i 's#x#y#' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand scanner-strings control: // inside the script, onto a frozen hook stays refused",
   "sed -i 's#//#/#' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand scanner-strings control: a hash in the script, onto a frozen hook stays refused",
   "sed -i 's/#x//' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand scanner-strings control: a block-comment opener in the script, onto a frozen hook stays refused",
   "sed -i 's/a/\\/*/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand scanner-strings control: a lone quote in a double-quoted script, onto a frozen hook stays refused",
   "sed -i \"s/don't/do not/\" " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand scanner-strings: -ni with a # delimiter, onto a frozen hook is refused",
   "sed -ni 's#x#y#' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand scanner-strings: -ni with a lone quote in the script, onto a frozen hook is refused",
   "sed -ni \"s/don't/do not/\" " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand scanner-strings: -ni with a quoted newline in the script, onto a frozen hook is refused",
   "sed -ni '1i\\\ntext' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)

# --- delimiter: an s command takes any character as its delimiter, so its w flag reads after that character (class: delimiter) ---
sh("sed-operand delimiter: sed s with a | delimiter and a w flag to a frozen hook is refused",
   "sed 's|a|b|w " + CFG_HOOK + "' x", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand delimiter: sed s with a # delimiter and a w flag to a frozen hook is refused",
   "sed 's#a#b#w " + CFG_HOOK + "' x", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand delimiter: sed s with a : delimiter and a w flag to a frozen hook is refused",
   "sed 's:a:b:w " + CFG_HOOK + "' x", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand delimiter: sed s with a @ delimiter and a w flag to a frozen hook is refused",
   "sed 's@a@b@w " + CFG_HOOK + "' x", "deny", "frozen-path", cwd=NOGIT)

# --- quoted-command: a double-quoted sed name is still sed, so its -ni is a write (class: quoted-command) ---
sh("sed-operand quoted-command: a double-quoted sed name with -ni onto a frozen hook is refused",
   "\"sed\" -ni 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)

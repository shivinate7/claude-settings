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
# delimiter, quoted-command, address, line-address, block, expression, s-end, comment,
# newline-script, label, nested-newline, find-exec, nested-pipe.

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
sh("sed-operand w-command control: sed s with an empty w flag and no file is allowed",
   "sed 's/a/b/w' x", "allow", cwd=NOGIT)
sh("sed-operand w-command control: sed -n w to another file is allowed",
   "sed -n 'w out.txt' x", "allow", cwd=NOGIT)

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
sh("sed-operand script-as-target control: sed -i with no frozen path, target another file, is allowed",
   "sed -i s/a/b/ other.txt", "allow", cwd=NOGIT)

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

# --- address: a /re/ address ends at its closing delimiter, so the w after it is a command (class: address) ---
sh("sed-operand address: sed -n with a /re/ address then w to a frozen hook is refused",
   "sed -n '/x/w " + CFG_HOOK + "' x", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand address control: sed -n with a /re/ address then p reads a frozen hook and is allowed",
   "sed -n '/w/p' " + CFG_HOOK, "allow", cwd=NOGIT)

# --- line-address: a line number or $ with ! is an address, and the w after it is a command (class: line-address) ---
sh("sed-operand line-address: sed -n with a 1,3 range then w to a frozen hook is refused",
   "sed -n '1,3w " + CFG_HOOK + "' x", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand line-address: sed -n with $! then w to a frozen hook is refused",
   "sed -n '$!w " + CFG_HOOK + "' x", "deny", "frozen-path", cwd=NOGIT)

# --- block: a w inside { } is a command (class: block) ---
sh("sed-operand block: sed -n with a w inside braces to a frozen hook is refused",
   "sed -n '{w " + CFG_HOOK + "}' x", "deny", "frozen-path", cwd=NOGIT)

# --- expression: a glued -e and a --expression= value are scripts, so their w is a command (class: expression) ---
sh("sed-operand expression: sed -n -e with a glued w to a frozen hook is refused",
   "sed -n -e'w " + CFG_HOOK + "' x", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand expression: sed -n --expression= with a w to a frozen hook is refused",
   "sed -n --expression='w " + CFG_HOOK + "' x", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand expression control: sed --expression=p reads a frozen hook and is allowed",
   "sed --expression=p " + CFG_HOOK, "allow", cwd=NOGIT)

# --- s-end: a # inside an s replacement is text, and the ; after the s ends it, so the w after is a command (class: s-end) ---
sh("sed-operand s-end: sed -n with a # in an s replacement, then ; and w to a frozen hook is refused",
   "sed -n 's/a/#/;w " + CFG_HOOK + "' x", "deny", "frozen-path", cwd=NOGIT)

# --- comment: a # starts a comment that runs to the line end, so a w in it is text (class: comment) ---
sh("sed-operand comment: sed -n with a # comment holding w to a frozen hook is allowed",
   "sed -n '# w " + CFG_HOOK + "' x", "allow", cwd=NOGIT)

# --- newline-script: a line break ends a sed command, so a w on the next line is a command (class: newline-script) ---
sh("sed-operand newline-script: sed -n with an a text, a line break, then w to a frozen hook is refused",
   "sed -n 'a x\nw " + CFG_HOOK + "' x", "deny", "frozen-path", cwd=NOGIT)

# --- label: a label ends at whitespace as well as ; or a line end, so a w after it is a command (class: label) ---
sh("sed-operand label: sed -n with a :a label, a space, then w to a frozen hook is refused",
   "sed -n ':a w " + CFG_HOOK + "' x", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand label: sed -n with a :a label, then a block holding w to a frozen hook is refused",
   "sed -n ':a {w " + CFG_HOOK + "\n}' x", "deny", "frozen-path", cwd=NOGIT)
sh("sed-operand label control: sed -n a loop with n and ba reads a frozen hook and is allowed",
   "sed -n ':a;n;ba' " + CFG_HOOK, "allow", cwd=NOGIT)

# --- nested-newline: a line break inside a sh -c script ends a sed command there (class: nested-newline) ---
sh("sed-operand nested-newline: bash -c with an a text, a line break, then w to a frozen hook is refused",
   "bash -c \"sed -n 'a x\nw " + CFG_HOOK + "' y\"", "deny", "frozen-path", cwd=NOGIT)

# --- find-exec: a sed behind find -exec is a command word, so its -ni is a write (class: find-exec) ---
sh("sed-operand find-exec: find -exec sed -ni onto a frozen hook is refused",
   "find . -exec sed -ni 's/a/b/' " + CFG_HOOK + " \\;", "deny", "frozen-path", cwd=NOGIT)

# --- nested-pipe: a pipe into xargs sed -ni inside a sh -c script is a write (class: nested-pipe) ---
sh("sed-operand nested-pipe: bash -c with a frozen hook piped to xargs sed -ni is refused",
   "bash -c \"echo " + CFG_HOOK + " | xargs sed -ni 's/a/b/'\"", "deny", "frozen-path", cwd=NOGIT)

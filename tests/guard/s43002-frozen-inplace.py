# section 43002
FAMILY = "frozen"
#
# An in-place edit by perl or ruby writes the file it names, as `sed -i` does. A frozen path after the
# in-place flag is refused the same way, whichever interpreter runs it. The script is `s/a/b/` in every
# case: the guard reads the command text, and a `$`, brace, parenthesis or backslash in a script sends
# the command to the script reader instead. The script need not run.

for _name, _command in (
    ("perl -pi -e on a frozen hook", "perl -pi -e 's/a/b/' " + CFG_HOOK),
    ("perl -i -pe on a frozen settings file", "perl -i -pe 's/a/b/' " + CFG_SETTINGS),
    ("perl -i.bak -pe on a frozen hook", "perl -i.bak -pe 's/a/b/' " + CFG_HOOK),
    ("ruby -i -pe on a frozen hook", "ruby -i -pe 's/a/b/' " + CFG_HOOK),
    ("ruby -pi -e on a frozen settings file", "ruby -pi -e 's/a/b/' " + CFG_SETTINGS),
    ("perl -pi -e inside sh -c on a frozen hook", "sh -c 'perl -pi -e s/a/b/ " + CFG_HOOK + "'"),
):
    sh("frozen inplace: " + _name + " denies", _command, "deny", "frozen-path", cwd=NOGIT)

# Controls. The sed twin of the sh -c case denies on main today, so it pins the behaviour the perl form must match.
sh("frozen inplace: sed -i inside sh -c on a frozen hook denies (control)",
   "sh -c 'sed -i s/a/b/ " + CFG_HOOK + "'", "deny", "frozen-path", cwd=NOGIT)
sh("frozen inplace: perl -n reads a frozen hook and is allowed (control)",
   "perl -n -e 'print' " + CFG_HOOK, "allow", cwd=NOGIT)
sh("frozen inplace: perl -pi -e on a project settings file is allowed (control)",
   "perl -pi -e 's/a/b/' " + PROJ_SETTINGS, "allow", cwd=NOGIT)

# A `-i` that is no perl or ruby in-place flag: a search pattern, an echo, a quoted print string or a
# comment. None of these writes the frozen file, so each allows.
for _name, _command in (
    ("grep -n perl -i naming a frozen hook", "grep -n perl -i " + CFG_HOOK),
    ("rg -n perl -i naming a frozen hook", "rg -n perl -i " + CFG_HOOK),
    ("echo perl -i naming a frozen hook", "echo perl -i " + CFG_HOOK),
    ("perl -ne whose print string holds -i, on a frozen hook", "perl -ne 'print \" -i \"' " + CFG_HOOK),
    ("perl -ne whose body comment ends in -i, on a frozen hook", "perl -ne 'print; # edit in -i' " + CFG_HOOK),
):
    sh("frozen inplace: " + _name + " allows", _command, "allow", cwd=NOGIT)

# An include directory whose name ends in i is no in-place flag: perl reads the frozen file and writes nothing.
sh("frozen inplace: perl -Iui -ne on a frozen hook is allowed",
   "perl -Iui -ne 'print' " + CFG_HOOK, "allow", cwd=NOGIT)

# Controls for the include and library flags beside it. An include dir that is no in-place flag stays allowed.
sh("frozen inplace: perl -Ilib -ne on a frozen hook is allowed (control)",
   "perl -Ilib -ne 'print' " + CFG_HOOK, "allow", cwd=NOGIT)
sh("frozen inplace: ruby -rtime -ne on a frozen hook is allowed (control)",
   "ruby -rtime -ne 'print' " + CFG_HOOK, "allow", cwd=NOGIT)

# A real in-place flag still denies when an include dir comes before it.
sh("frozen inplace: perl -Iui -pi -e on a frozen hook denies",
   "perl -Iui -pi -e 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)

# A digit in the flag cluster: `-0pi` is the record-separator flag `-0` with `-p` and `-i`, so it is an
# in-place edit and denies. `-0777` is its own word, and the `-pi` after it still denies. `-0` with no i
# reads the frozen file and writes nothing, so it allows.
sh("frozen inplace: perl -0pi -e on a frozen hook denies",
   "perl -0pi -e 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("frozen inplace: perl -0777 -pi -e on a frozen hook denies (control)",
   "perl -0777 -pi -e 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("frozen inplace: perl -0 -ne on a frozen hook is allowed (control)",
   "perl -0 -ne 'print' " + CFG_HOOK, "allow", cwd=NOGIT)

# A real in-place edit after another command, joined by `;`, `&&` or `|`, still denies.
sh("frozen inplace: grep x; perl -pi -e on a frozen hook denies",
   "grep x; perl -pi -e 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("frozen inplace: echo a && perl -pi -e on a frozen hook denies",
   "echo a && perl -pi -e 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("frozen inplace: echo a | perl -pi -e on a frozen hook denies",
   "echo a | perl -pi -e 's/a/b/' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)

# A `#` starts a comment, so the `; perl -pi` after it is text, and the call allows.
sh("frozen inplace: echo a # c; perl -pi on a frozen hook is a comment and allows",
   "echo a # c; perl -pi " + CFG_HOOK, "allow", cwd=NOGIT)

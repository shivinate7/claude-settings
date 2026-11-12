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

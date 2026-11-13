# section 18212
FAMILY = "frozen"
#
# Loops and brace words in the frozen-path shell check (hooks/guard_frozen.py, `_shell_write_hit`). A `for NAME in
# WORDS` loop and a comma brace expand as bash does, so the path a loop variable or a brace names is judged as the
# file it writes. Each red is a write that reaches a frozen file only through a loop or a brace. Each green is a
# form bash does not expand, or one over the cap, which keeps today's literal judgment.
FROZEN_RULE = "frozen-path"
FROZEN_CAP = 32  # the most words a loop expands; a longer list keeps its literal judgment
CFG_BRACE = slash(os.path.join(CFG, "{settings.json,x}"))
CFG_EMPTY_ALT = slash(os.path.join(CFG, "{,settings.json}"))
CFG_RANGE = slash(os.path.join(CFG, "settings.json.{1..2}"))


def loop_for(words, body):
    return "for f in %s; do %s; done" % (" ".join(words), body)


SED_EDIT = 'sed -i "s/a/b/" '

# --- red: the write reaches a frozen file through a loop or a brace ---
sh("frozen: a loop's sed -i onto the config settings through its loop variable is refused",
   loop_for([CFG_SETTINGS], 'sed -i "s/a/b/" "$f"'), "deny", FROZEN_RULE, cwd=NOGIT)
sh("frozen: a sed -i onto a brace that names the config settings is refused",
   SED_EDIT + CFG_BRACE, "deny", FROZEN_RULE, cwd=NOGIT)
sh("frozen: a sed -i onto a brace with an empty alternative that names the config settings is refused",
   SED_EDIT + CFG_EMPTY_ALT, "deny", FROZEN_RULE, cwd=NOGIT)
sh("frozen: a loop of 32 words that ends on the config settings is refused: the full-size list expands",
   loop_for(["w%d" % i for i in range(1, FROZEN_CAP)] + [CFG_SETTINGS], 'sed -i "s/a/b/" "$f"'),
   "deny", FROZEN_RULE, cwd=NOGIT)
sh("frozen: a loop over a brace that names the config settings is refused",
   loop_for([CFG_BRACE], 'sed -i "s/a/b/" "$f"'), "deny", FROZEN_RULE, cwd=NOGIT)
sh("frozen: a loop whose list holds a quoted # still expands the config settings after it",
   loop_for(['"a#b"', CFG_SETTINGS], 'sed -i "s/a/b/" "$f"'), "deny", FROZEN_RULE, cwd=NOGIT)
sh("frozen: a loop whose list holds a quoted newline still expands the brace after it",
   'for f in "a\nb" %s; do sed -i "s/a/b/" "$f"; done' % CFG_BRACE, "deny", FROZEN_RULE, cwd=NOGIT)
sh("frozen: a lone single quote inside double quotes does not stop a loop's expansion",
   'echo "it\'s"; ' + loop_for([CFG_BRACE], 'sed -i "s/a/b/" "$f"'), "deny", FROZEN_RULE, cwd=NOGIT)

# --- control: a literal path in a loop body is already refused on main; the build must keep it refused ---
sh("frozen: a loop body's sed -i onto the config settings, the path literal, is refused",
   'for f in x; do sed -i "s/a/b/" %s; done' % CFG_SETTINGS, "deny", FROZEN_RULE, cwd=NOGIT)

# --- green: a form bash does not expand, or one over the cap, keeps today's literal judgment ---
sh("frozen: a loop of 33 words keeps today's literal judgment: over the cap, the frozen word is not expanded",
   loop_for(["w%d" % i for i in range(1, FROZEN_CAP + 1)] + [CFG_SETTINGS], 'sed -i "s/a/b/" "$f"'),
   "allow", cwd=NOGIT)
sh("frozen: a quoted brace is one literal name, bash does not expand it",
   SED_EDIT + '"%s"' % CFG_BRACE, "allow", cwd=NOGIT)
sh("frozen: a brace range is not expanded, so its literal name is not the config settings",
   SED_EDIT + CFG_RANGE, "allow", cwd=NOGIT)
sh("frozen: a loop variable reassigned in the body keeps its literal judgment",
   'for f in %s; do f=/tmp/x; sed -i "s/a/b/" "$f"; done' % CFG_SETTINGS, "allow", cwd=NOGIT)
sh("frozen: a read of the config settings through a loop is allowed",
   loop_for([CFG_SETTINGS], 'cat "$f"'), "allow", cwd=NOGIT)
sh("frozen: a # inside a quoted loop word is text, so a loop over a non-frozen word is allowed",
   loop_for(['"a#b"'], 'sed -i "s/a/b/" "$f"'), "allow", cwd=NOGIT)
sh("frozen: mkdir -p over a brace list makes its folders and does not crash",
   "mkdir -p src/{a,b}", "allow", cwd=NOGIT)

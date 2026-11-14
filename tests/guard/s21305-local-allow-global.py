# section 21305
FAMILY = "local-allow-global"
# Loads after s21304-diff, which creates LOG_CHECKS_EXTRA, so the remedy check below can register.
#
# Rule local-allow-global. A write that adds an allow rule to a project's settings.local.json asks,
# never refuses: the write stays allowed on approval. The ask's first remedy names the shared
# settings.json, where a rule every session needs goes by a lane PR on claude-settings. The rule
# tests only the basename settings.local.json, so the shared file and every non-allow write keep
# their old answer.
#
# THE ADDED RULE IS THE ONE THE DISK DOES NOT HOLD. A re-write of a rule already in the file asks
# nothing. The fixtures reach the empty state (`{}`), the one-rule state and a 150-rule state.
#
# THE SCANNERS. An allow rule is read through a JSON parse where the text parses, and through a
# string-aware pass where the text is a fragment. The openers `//`, `/*` and `#`, a lone quote and a
# multi-line body are each pinned on both sides: an allow rule carrying them asks, and a non-allow
# field carrying them does not.

LA_DIR = os.path.join(ROOT, "local-allow")
LA_LOCAL = slash(os.path.join(LA_DIR, ".claude", "settings.local.json"))  # absent on disk
LA_SHARED = slash(os.path.join(LA_DIR, ".claude", "settings.json"))  # absent on disk
LA_EMPTY = slash(os.path.join(LA_DIR, "empty", ".claude", "settings.local.json"))  # `{}`
LA_PRESENT = slash(os.path.join(LA_DIR, "present", ".claude", "settings.local.json"))  # one allow rule
LA_BIG = slash(os.path.join(LA_DIR, "big", ".claude", "settings.local.json"))  # 150 allow rules

RULE_GIT = "Bash(git status)"
RULE_NEW = "Bash(npm test)"
RULE_SCAN = "Bash(curl https://h.example/* # note)"  # holds //, /* and #
RULE_QUOTE = "Bash(echo 'a)"
RULE_DONT = "Bash(echo don't)"
BIG_RULES = ["Bash(tool %d)" % index for index in range(150)]

ASK_CARRIES = ("settings.json", "every session")
NO_OVERRIDE = ("override",)
NOT_RULE = ("local-allow-global",)


def local_json(allow=(), deny=()):
    """The text of a settings.local.json that holds the given allow and deny rules."""
    permissions = {"allow": list(allow)}
    if deny:
        permissions["deny"] = list(deny)
    return json.dumps({"permissions": permissions}, indent=2)


def write_fixture(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)


def build_empty():
    write_fixture(LA_EMPTY, "{}\n")


def build_present():
    write_fixture(LA_PRESENT, local_json(allow=[RULE_GIT]))


def build_big():
    write_fixture(LA_BIG, local_json(allow=BIG_RULES))


lazy_fixture([LA_EMPTY], build_empty)
lazy_fixture([LA_PRESENT], build_present)
lazy_fixture([LA_BIG], build_big)

# ASK. A write that adds an allow rule to a project settings.local.json asks, and names the shared file.
add("local-allow: Write of a project settings.local.json adding an allow rule asks", "ask",
    "local-allow-global", tool="Write", cwd=NOGIT, file_path=LA_LOCAL,
    content=local_json(allow=[RULE_GIT]), carries=ASK_CARRIES, lacks=NO_OVERRIDE)
add("local-allow: Edit adding a second allow rule to a settings.local.json that holds one asks", "ask",
    "local-allow-global", tool="Edit", cwd=NOGIT, file_path=LA_PRESENT,
    old_string='"' + RULE_GIT + '"', new_string='"' + RULE_GIT + '",\n      "' + RULE_NEW + '"',
    carries=ASK_CARRIES, lacks=NO_OVERRIDE)
add("local-allow: MultiEdit adding an allow rule to an empty settings.local.json asks, in any edit", "ask",
    "local-allow-global", tool="MultiEdit", cwd=NOGIT, file_path=LA_EMPTY,
    edits=[{"old_string": "{}", "new_string": "{}"},
           {"old_string": "{}", "new_string": local_json(allow=[RULE_NEW])}],
    carries=ASK_CARRIES, lacks=NO_OVERRIDE)
add("local-allow: Write adding one rule to a settings.local.json that holds 150 asks", "ask",
    "local-allow-global", tool="Write", cwd=NOGIT, file_path=LA_BIG,
    content=local_json(allow=BIG_RULES + [RULE_NEW]), carries=ASK_CARRIES, lacks=NO_OVERRIDE)
add("local-allow: Write of an allow rule holding //, /* and # asks", "ask",
    "local-allow-global", tool="Write", cwd=NOGIT, file_path=LA_LOCAL,
    content=local_json(allow=[RULE_SCAN]), carries=ASK_CARRIES, lacks=NO_OVERRIDE)
add("local-allow: Edit fragment adding an allow rule holding //, /* and # asks", "ask",
    "local-allow-global", tool="Edit", cwd=NOGIT, file_path=LA_PRESENT,
    old_string='"' + RULE_GIT + '"', new_string='"' + RULE_GIT + '",\n      "' + RULE_SCAN + '"',
    carries=ASK_CARRIES, lacks=NO_OVERRIDE)
add("local-allow: Write of allow rules holding a lone quote asks", "ask",
    "local-allow-global", tool="Write", cwd=NOGIT, file_path=LA_LOCAL,
    content=local_json(allow=[RULE_QUOTE, RULE_DONT]), carries=ASK_CARRIES, lacks=NO_OVERRIDE)
add("local-allow: Edit fragment adding an allow rule holding a lone quote asks", "ask",
    "local-allow-global", tool="Edit", cwd=NOGIT, file_path=LA_PRESENT,
    old_string='"' + RULE_GIT + '"', new_string='"' + RULE_GIT + '",\n      "' + RULE_QUOTE + '"',
    carries=ASK_CARRIES, lacks=NO_OVERRIDE)
# THE FRAGMENT READ. A text that does not parse as JSON, such as a commented settings file, is read by the scanner.
# The two cases below are the only asks that reach it: every other ask case above is valid JSON.
add("local-allow: a Write of a settings.local.json with // comments adding an allow rule asks", "ask",
    "local-allow-global", tool="Write", cwd=NOGIT, file_path=LA_LOCAL,
    content='// this checkout only, /* see the shared file # here\n{\n  "permissions": {\n    "allow": [\n      "'
            + RULE_NEW + '" # new\n    ]\n  }\n}\n',
    carries=ASK_CARRIES, lacks=NO_OVERRIDE)
add("local-allow: an Edit adding an allow rule beside a // comment asks", "ask",
    "local-allow-global", tool="Edit", cwd=NOGIT, file_path=LA_PRESENT,
    old_string='"' + RULE_GIT + '"', new_string='"' + RULE_GIT + '", // note\n      "' + RULE_NEW + '"',
    carries=ASK_CARRIES, lacks=NO_OVERRIDE)

# NOT ASK. The shared settings.json, a deny, ask, env, model, hook or string write, and a scanner
# fragment that names allow without adding a rule. Each passes on the old code too: a green control.
add("local-allow: an allow rule written to the shared settings.json does not ask", "allow",
    tool="Write", cwd=NOGIT, file_path=LA_SHARED, content=local_json(allow=[RULE_GIT]), lacks=NOT_RULE)
add("local-allow: an Edit adding an allow rule to the shared settings.json does not ask", "allow",
    tool="Edit", cwd=NOGIT, file_path=LA_SHARED, old_string="{}",
    new_string=local_json(allow=[RULE_NEW]), lacks=NOT_RULE)
add("local-allow: an Edit adding only a deny rule to settings.local.json does not ask", "allow",
    tool="Edit", cwd=NOGIT, file_path=LA_EMPTY, old_string="{}",
    new_string=local_json(deny=["Bash(git push)"]), lacks=NOT_RULE)
add("local-allow: an Edit adding an ask rule to settings.local.json does not ask", "allow",
    tool="Edit", cwd=NOGIT, file_path=LA_EMPTY, old_string="{}",
    new_string='{"permissions": {"ask": ["Bash(git push)"]}}', lacks=NOT_RULE)
add("local-allow: a Write adding an env key to settings.local.json does not ask", "allow",
    tool="Write", cwd=NOGIT, file_path=LA_LOCAL, content=json.dumps({"env": {"TZ": "UTC"}}, indent=2),
    lacks=NOT_RULE)
add("local-allow: a Write adding a model key to settings.local.json does not ask", "allow",
    tool="Write", cwd=NOGIT, file_path=LA_LOCAL, content=json.dumps({"model": "sonnet"}, indent=2),
    lacks=NOT_RULE)
add("local-allow: a Write adding a hook to settings.local.json does not ask", "allow",
    tool="Write", cwd=NOGIT, file_path=LA_LOCAL,
    content=json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo done"}]}]}}, indent=2),
    lacks=NOT_RULE)
add("local-allow: a string field naming the word allow in settings.local.json does not ask", "allow",
    tool="Write", cwd=NOGIT, file_path=LA_LOCAL,
    content=json.dumps({"description": "allow list is kept in settings.json"}, indent=2), lacks=NOT_RULE)
add("local-allow: a non-allow Edit fragment naming allow beside //, /* and # does not ask", "allow",
    tool="Edit", cwd=NOGIT, file_path=LA_EMPTY, old_string="{}",
    new_string='{"note": "allow // see https://h.example/* and # here"}', lacks=NOT_RULE)
add("local-allow: a multi-line string in a non-allow field naming allow does not ask", "allow",
    tool="Edit", cwd=NOGIT, file_path=LA_EMPTY, old_string="{}",
    new_string='{"note": "first line\nallow the list here\nlast line"}', lacks=NOT_RULE)
add("local-allow: a template-literal body in a non-allow field naming allow does not ask", "allow",
    tool="Edit", cwd=NOGIT, file_path=LA_EMPTY, old_string="{}",
    new_string='{"note": `\nallow ${list}\n`}', lacks=NOT_RULE)
# A broken write holds deny and ask rules, so the scanner reads its fragment and must skip both keys: a rule
# under deny or ask is never an allow rule, and the file is not JSON, so the fragment read is the one that runs.
add("local-allow: a broken settings.local.json write holding only deny and ask rules does not ask", "allow",
    tool="Write", cwd=NOGIT, file_path=LA_LOCAL,
    content='// broken draft, see the shared file\n{\n  "permissions": {\n    "deny": ["Bash(git push)"],\n'
            '    "ask": ["Bash(rm -rf /tmp/x)"]\n',
    lacks=NOT_RULE)
add("local-allow: a lone quote in a non-allow field naming allow does not ask", "allow",
    tool="Edit", cwd=NOGIT, file_path=LA_EMPTY, old_string="{}",
    new_string='{"note": "don\'t allow it, echo \'a"}', lacks=NOT_RULE)

# RE-WRITES. A rule the file already holds is not added, so it asks nothing: one rule, a rule beside a
# new deny, 150 rules (full size), and an empty allow list over an empty file (empty state).
add("local-allow: an Edit re-writing the allow rule already on disk does not ask", "allow",
    tool="Edit", cwd=NOGIT, file_path=LA_PRESENT, old_string='"' + RULE_GIT + '"',
    new_string='"' + RULE_GIT + '"', lacks=NOT_RULE)
add("local-allow: a Write re-stating the rule on disk beside a new deny rule does not ask", "allow",
    tool="Write", cwd=NOGIT, file_path=LA_PRESENT,
    content=local_json(allow=[RULE_GIT], deny=["Bash(git push)"]), lacks=NOT_RULE)
add("local-allow: a Write re-stating all 150 rules on disk does not ask", "allow",
    tool="Write", cwd=NOGIT, file_path=LA_BIG, content=local_json(allow=BIG_RULES), lacks=NOT_RULE)
add("local-allow: a Write of an empty allow list over an empty file does not ask", "allow",
    tool="Write", cwd=NOGIT, file_path=LA_EMPTY, content=local_json(allow=[]), lacks=NOT_RULE)


def local_allow_remedy_case():
    """The ask for an allow rule in settings.local.json names the shared settings.json as its first
    remedy, names settings.local.json only as its File line, and prints no override line. The decision
    is read first, so a write that does not ask fails on its decision, never on its reason."""
    got, reason = decide({
        "raw": None, "tool": "Write", "cwd": NOGIT, "session": None, "env_path": None,
        "tool_input": {"file_path": LA_LOCAL, "content": local_json(allow=[RULE_GIT])},
    })
    if got != "ask":
        return False, "expected ask, got %s" % got
    if "override" in reason:
        return False, "the ask prints an override line: %s" % reason[:90]
    remedy = reason.replace("File: " + LA_LOCAL, "")
    if "settings.local" in remedy:
        return False, "the ask names settings.local.json outside its File line: %s" % remedy[:90]
    if "settings.json" not in remedy:
        return False, "the ask does not name the shared settings.json: %s" % reason[:90]
    approve = remedy.lower().find("approve")
    if 0 <= approve < remedy.find("settings.json"):
        return False, "the ask names a second remedy before the shared settings.json"
    return True, "asks, names the shared settings.json, and names settings.local.json only in its File line"


LOG_CHECKS_EXTRA.append(("local-allow: the ask names the shared settings.json first, names settings.local.json "
                         "only in its File line, and prints no override line", local_allow_remedy_case))

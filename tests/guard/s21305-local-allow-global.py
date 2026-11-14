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
# A broken write holds deny and ask rules, so the fragment read is the one that runs: a rule under deny or ask
# is never an allow rule, whatever the scanner does with those keys.
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

# FALSE ALARMS. A rule-shaped string is an allow rule only at the top of a fragment, or under the real `allow` key.
# A string under any other list key, such as a directory or an MCP server name, is not one, whether the text parses.
# The two cases below read the fragment scanner: an absent file, and a text that does not parse.
def broken_allow(items, key="allow"):
    """A settings.local.json text that does not parse (a trailing comma), with the strings under `key`.
    Each item is the text between its quotes, so an item that holds a quote carries the escape itself."""
    return '{"permissions": {"%s": [%s],}}' % (key, ", ".join('"%s"' % item for item in items))


add("local-allow: an Edit to an absent settings.local.json adding non-allow lists of rule-shaped strings does not ask",
    "allow", tool="Edit", cwd=NOGIT, file_path=LA_LOCAL, old_string="",
    new_string='{"permissions":{"additionalDirectories":["Documents"]},"enabledMcpjsonServers":["Github"]}',
    lacks=NOT_RULE)
add("local-allow: a write that does not parse, with a rule-shaped string under a non-allow list, does not ask",
    "allow", tool="Write", cwd=NOGIT, file_path=LA_LOCAL,
    content=broken_allow(["Documents"], key="additionalDirectories"), lacks=NOT_RULE)
# Controls for the two false alarms: the same name under text that parses, and a rule-shaped string at the top.
add("local-allow: a valid JSON write naming Documents under additionalDirectories does not ask", "allow",
    tool="Write", cwd=NOGIT, file_path=LA_LOCAL,
    content=json.dumps({"permissions": {"additionalDirectories": ["Documents"]}}, indent=2), lacks=NOT_RULE)
add("local-allow: a rule-shaped string at the top of a fragment still asks", "ask", "local-allow-global",
    tool="Write", cwd=NOGIT, file_path=LA_LOCAL, content='"' + RULE_NEW + '",  // the shared file\n',
    carries=ASK_CARRIES + (RULE_NEW,), lacks=NO_OVERRIDE)
# FALSE ALARMS, LISTS OF LISTS. A list inside a list has no key of its own, so it is not a list of unknown key at the top
# of a fragment, and its strings are no rule. A valid JSON text that is not an object holds no settings rule either.
add("local-allow: a Write of valid JSON that is a list, not an object, naming rule-shaped strings does not ask", "allow",
    tool="Write", cwd=NOGIT, file_path=LA_LOCAL, content='["Documents","Github"]', lacks=NOT_RULE)
add("local-allow: a write that does not parse, with a list of lists under a non-allow key, does not ask", "allow",
    tool="Write", cwd=NOGIT, file_path=LA_LOCAL, content='{"matrix": [["Alpha","Beta"]],}', lacks=NOT_RULE)
# Controls: an allow rule under the real key still asks in a write that does not parse, alone and behind a list of
# lists, so a fix to the nested-list case leaves the allow key's rules counted.
add("local-allow: a write that does not parse, with an allow rule under the allow key, still asks", "ask",
    "local-allow-global", tool="Write", cwd=NOGIT, file_path=LA_LOCAL, content=broken_allow([RULE_NEW]),
    carries=ASK_CARRIES + (RULE_NEW,), lacks=NO_OVERRIDE)
add("local-allow: a write that does not parse, with a list of lists ahead of an allow rule, still asks", "ask",
    "local-allow-global", tool="Write", cwd=NOGIT, file_path=LA_LOCAL,
    content='{"matrix": [["Alpha","Beta"]], "permissions": {"allow": ["' + RULE_NEW + '"],}}',
    carries=ASK_CARRIES + (RULE_NEW,), lacks=NO_OVERRIDE)

# FRAGMENT SCANNER. A text that does not parse is read by `_local_allow_fragment`, so each write below holds a
# trailing comma and the JSON parser never reads it. Each case pins one arm no case above reaches: // and # inside
# an allow string, a lone quote in a comment line, an escaped quote, a rule over 80 characters with a count of the
# rest, and an Edit whose old_string already holds the rule it restates.
RULE_QUOTED = 'Bash(echo "hi")'
LONG_RULES = ["Bash(step-%d %s)" % (index, "p" * 80) for index in range(1, 6)]  # five rules, each over 80 characters
add("local-allow: a write that does not parse, with an allow rule holding //, /* and #, asks", "ask",
    "local-allow-global", tool="Write", cwd=NOGIT, file_path=LA_LOCAL, content=broken_allow([RULE_SCAN]),
    carries=ASK_CARRIES + (RULE_SCAN,), lacks=NO_OVERRIDE)
add("local-allow: a lone quote in a comment line ahead of an allow rule asks for the rule", "ask",
    "local-allow-global", tool="Write", cwd=NOGIT, file_path=LA_LOCAL,
    content='// the "shared file, see below\n{\n  "permissions": {\n    "allow": [\n      "' + RULE_NEW
            + '"\n    ]\n  }\n}\n',
    carries=ASK_CARRIES + (RULE_NEW,), lacks=NO_OVERRIDE)
add("local-allow: an escaped quote inside an allow rule of a write that does not parse asks with the rule whole",
    "ask", "local-allow-global", tool="Write", cwd=NOGIT, file_path=LA_LOCAL,
    content=broken_allow([RULE_QUOTED.replace('"', '\\"')]), carries=ASK_CARRIES + (RULE_QUOTED,),
    lacks=NO_OVERRIDE)
add("local-allow: five long rules in a write that does not parse show three, each cut at 80 characters, and a count",
    "ask", "local-allow-global", tool="Write", cwd=NOGIT, file_path=LA_LOCAL, content=broken_allow(LONG_RULES),
    carries=ASK_CARRIES + (" and 2 more", LONG_RULES[0][:80] + " [cut]"),
    lacks=NO_OVERRIDE + (LONG_RULES[0], "Bash(step-4", "Bash(step-5"))
add("local-allow: an Edit restating the rule its old_string already holds does not ask", "allow",
    tool="Edit", cwd=NOGIT, file_path=LA_LOCAL, old_string='"' + RULE_NEW + '"',
    new_string='"' + RULE_NEW + '"', lacks=NOT_RULE)

# A SYMLINK ALIAS. The link's own name is not settings.local.json, so the rule reads the file the link resolves to.
LA_ALIAS = slash(os.path.join(LA_DIR, "alias", "shared-rules.json"))  # a symlink to the empty file LA_EMPTY


def build_alias():
    write_fixture(LA_EMPTY, "{}\n")   # not build_empty: the harness rebinds that name to another signature
    os.makedirs(os.path.dirname(LA_ALIAS), exist_ok=True)
    os.symlink(LA_EMPTY, LA_ALIAS)


ALIAS_CASE = "local-allow: an Edit to a symlink named otherwise, pointing at an empty settings.local.json, asks"
if LINKS_MADE:
    lazy_fixture([LA_ALIAS], build_alias)
    add(ALIAS_CASE, "ask", "local-allow-global", tool="Edit", cwd=NOGIT, file_path=LA_ALIAS, old_string="{}",
        new_string=local_json(allow=[RULE_NEW]), carries=ASK_CARRIES + (RULE_NEW,), lacks=NO_OVERRIDE)
else:
    skip_case(ALIAS_CASE, NO_LINK_HERE)


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


# A FORCED RAISE. Rule 8a's read fails open: a guard defect inside it adds no rule and allows the write. The control
# run asks for the same write unforced, so the write is shown to reach the read. The raise replaces the read in a
# child process that loads the guard under test, as the crash case in s27664 replaces `judge`.
LA_FAIL_OPEN = os.path.join(LA_DIR, "fail-open")  # the config folder the forced runs read


def loaded_guard_run(payload, forced):
    """One guard run on a payload, in a child that loads GUARD. `forced` replaces the 8a read before `main`."""
    patch = "g.local_allow_added = lambda *args, **kwargs: 1 / 0\n" if forced else ""
    code = ("import io, sys, importlib.util as u\n"
            "spec = u.spec_from_file_location('g', %r)\n"
            "g = u.module_from_spec(spec); spec.loader.exec_module(g)\n"
            "%s"
            "sys.stdin = io.StringIO(%r)\n"
            "g.main()\n" % (GUARD, patch, payload))
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env["CLAUDE_CONFIG_DIR"] = LA_FAIL_OPEN
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60)


def local_allow_fail_open_case():
    """A raise in the 8a read allows the write silently. The same write, unforced, asks for its rule."""
    os.makedirs(LA_FAIL_OPEN, exist_ok=True)
    payload = json.dumps({"tool_name": "Write", "cwd": NOGIT,
                          "tool_input": {"file_path": LA_LOCAL, "content": local_json(allow=[RULE_NEW])}})
    control = loaded_guard_run(payload, forced=False)
    got, reason = read_decision(control.stdout)
    if got != "ask":
        return False, "the unforced control write did not ask, so it never reaches the read: %s" % got
    forced = loaded_guard_run(payload, forced=True)
    if forced.returncode != 0:
        return False, "the forced raise exited %d, not 0: %s" % (forced.returncode, forced.stderr.strip()[:90])
    if forced.stdout.strip():
        return False, "the forced raise printed a decision, not a silent allow: %s" % forced.stdout.strip()[:90]
    return True, "the forced raise allows silently; the unforced write asks"


LOG_CHECKS_EXTRA.append(("local-allow: a forced raise in the settings.local.json read still allows, and the same "
                         "write asks unforced", local_allow_fail_open_case))

# section 21922
FAMILY = "frozen"
_MIRROR_SHELL = re.compile(r'^MAIN_MIRROR="\$HOME/([^"/$]+)"[ \t\r]*$', re.M)
_PIN_SHELL = re.compile(r'^pin="\$clone([^"/$]*)"[ \t\r]*$', re.M)


def _module_literal(text, name):
    """The value of the top-level assignment `name = <literal>` in a Python module's text, or None."""
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return None
    return None


def mirror_name_problems(install_sh, install_from_main, guard_frozen):
    """One line per copy that differs from its shell literal, or [] when every copy agrees. Each argument is
    the text of one file."""
    problems = []
    mirror = _MIRROR_SHELL.findall(install_sh)
    pin = _PIN_SHELL.findall(install_from_main)
    name = _module_literal(guard_frozen, "MAIN_MIRROR_NAME")
    suffix = _module_literal(guard_frozen, "LIVE_PIN_SUFFIX")
    if len(mirror) != 1:
        problems.append("install.sh does not set MAIN_MIRROR to $HOME/<name> exactly once")
    elif name != mirror[0]:
        problems.append("MAIN_MIRROR_NAME is %r but install.sh MAIN_MIRROR is $HOME/%s" % (name, mirror[0]))
    if len(pin) != 1:
        problems.append('install_from_main.sh does not set pin="$clone<suffix>" exactly once')
    elif suffix != pin[0]:
        problems.append("LIVE_PIN_SUFFIX is %r but install_from_main.sh pin suffix is %r" % (suffix, pin[0]))
    return problems


def _mirror_names_tie():
    """MAIN_MIRROR_NAME and LIVE_PIN_SUFFIX in guard_frozen.py equal the shell names they copy."""
    def read(*parts):
        with open(os.path.join(REPO, *parts), encoding="utf-8") as handle:
            return handle.read()

    problems = mirror_name_problems(read("install.sh"), read("merge", "install_from_main.sh"),
                                    read("hooks", "guard_frozen.py"))
    if problems:
        return False, "; ".join(problems)
    return True, "MAIN_MIRROR_NAME and LIVE_PIN_SUFFIX equal install.sh MAIN_MIRROR and the install_from_main.sh pin"


LOG_CHECKS_EXTRA.append(("frozen: MAIN_MIRROR_NAME and LIVE_PIN_SUFFIX equal the shell names they copy",
                         _mirror_names_tie))

# ---- resolve-vars: `_resolve_vars` of guard_frozen, read as the shell reads each assignment. A check reads
# the use site (the last `;` segment, double quotes removed), so a fix that rewrites an assignment's own text
# still passes. The guard under test is loaded as every check loads it (GUARD_UNDER_TEST is honoured).
def _resolver_under_test():
    """`_resolve_vars` of guard_frozen as the guard under test loads it, or None when it has none."""
    _load_guard_module()
    return getattr(sys.modules.get("guard_frozen"), "_resolve_vars", None)


def _use_site(text):
    """The last `;` segment of a resolved command, with its double quotes removed."""
    return text.split(";")[-1].strip().replace('"', "")


def resolve_case(command, want):
    """A check: the use site of `command`, once resolved, reads `want`."""
    def check():
        resolve = _resolver_under_test()
        if resolve is None:
            return False, "guard_frozen has no _resolve_vars"
        got = _use_site(resolve(command))
        if got != want:
            return False, "%r resolves its use site to %r, want %r" % (command, got, want)
        return True, "%r resolves its use site to %r" % (command, want)
    FIXTURELESS_CHECKS.add(check)
    return check


_CHAIN = "; ".join(["A0=x"] + ["A%d=$A%d" % (n, n - 1) for n in range(1, 200)] + ["use $A199"])
RESOLVE_CASES = (
    # Red on the old code: each names one fault of the resolver.
    ("frozen resolve-vars: a value split at its quote keeps the text after the quote",
     'BASE=.claude/worktrees; WT="$BASE"/../lane; cp src $WT', "cp src .claude/worktrees/../lane"),
    ("frozen resolve-vars: a reassignment after an apostrophe in double quotes is seen",
     "S=a; echo \"don't\"; S=b; echo 'x'; use $S", "use b"),
    ("frozen resolve-vars: a variable set after an apostrophe in double quotes is resolved",
     "echo \"don't\" ; X=1; echo 'q'; echo $X", "echo 1"),
    ("frozen resolve-vars: an assignment on the second line of a double-quoted string is text",
     'echo "x\nS=a"; use $S', "use $S"),
    ("frozen resolve-vars: an assignment after a # inside double quotes is text",
     'echo "# S=a"; use $S', "use $S"),
    ("frozen resolve-vars: a prefix assignment does not change the word its own command expands",
     'S=x cmd "$S"', "S=x cmd $S"),
    ("frozen resolve-vars: a prefix assignment's command expands the value before it",
     'S=/safe; S=x cmd "$S"', "S=x cmd /safe"),
    ("frozen resolve-vars: a prefix assignment does not reach the text after it",
     'S=x cmd "$S"; use $S', "use $S"),
    ("frozen resolve-vars: the value before a prefix assignment reaches the text after it",
     'S=/safe; S=x cmd "$S"; use $S', "use /safe"),
    ("frozen resolve-vars: a subshell's assignment does not reach the text after its paren",
     "(S=x); echo $S", "echo $S"),
    ("frozen resolve-vars: the value before a subshell's assignment reaches the text after it",
     "S=/safe; (S=x); use $S", "use /safe"),
    # Keep-green controls: the behaviour the fix must keep.
    ("frozen resolve-vars: control, the last assignment wins",
     "D=a; D=b; use $D", "use b"),
    ("frozen resolve-vars: control, unset clears the variable",
     "S=a; unset S; use $S", "use $S"),
    ("frozen resolve-vars: control, single quotes do not expand",
     "S=a; use '$S'", "use '$S'"),
    ("frozen resolve-vars: control, export of two names reads both",
     "export A=1 D=v; use $D", "use v"),
    ("frozen resolve-vars: control, $HOME reads as ~",
     "echo $HOME/x", "echo ~/x"),
    ("frozen resolve-vars: control, the brief's apostrophe text with no second quote is still read",
     "echo \"don't\"; S=a; S=b; use $S", "use b"),
    ("frozen resolve-vars: control, the brief's second apostrophe text is still read",
     "echo \"don't\" ; X=1; echo $X", "echo 1"),
    ("frozen resolve-vars: control, a # inside double quotes is text, so a later reassignment is seen",
     'echo "# note"; S=b; use $S', "use b"),
    ("frozen resolve-vars: control, a // inside double quotes is text",
     'echo "http://x"; S=b; use $S', "use b"),
    ("frozen resolve-vars: control, a /* inside double quotes is text",
     'echo "/* x"; S=b; use $S', "use b"),
    ("frozen resolve-vars: control, a subshell's assignment holds inside the subshell",
     "(S=x; use $S)", "use x)"),
    ("frozen resolve-vars: control, a brace group keeps its assignment for the next command",
     "{ S=x; }; use $S", "use x"),
    ("frozen resolve-vars: control, a bare assignment before && keeps it for the next command",
     "S=x && use $S", "S=x && use x"),
    ("frozen resolve-vars: control, an empty command stays empty", "", ""),
    ("frozen resolve-vars: control, a 200-link chain of assignments resolves to its first value",
     _CHAIN, "use x"),
)
for _label, _command, _want in RESOLVE_CASES:
    LOG_CHECKS_EXTRA.append((_label, resolve_case(_command, _want)))

# ---- merge: gh_call_of reads the pr verb past a repo flag. Its callers (merge_call_of, the draft-PR read,
# ci_wake and guard.py's title read) take the first two words it returns, so a -R or --repo in front of the verb,
# or after the group word, hides the verb from each of them. One check per flag form, called on gh_call_of directly.

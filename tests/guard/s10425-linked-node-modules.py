# section 10425
FAMILY = "linked-node-modules"
NM_RULE = "linked-node-modules"
# The remedy names the link and the real folder to make, and never names the refused act.
NM_REMEDY = ("link", ("real folder", "real directory"), "setup")
NM_LACKS = ("npm ci", "rm -rf")
NMTARGET = os.path.join(ROOT, "nmtarget")    # stands in for main's install, outside every working folder
NMLINKED = os.path.join(ROOT, "nmlinked")    # a working folder whose node_modules is a link
NMREAL = os.path.join(ROOT, "nmreal")        # a working folder whose node_modules is a real folder
NMABSENT = os.path.join(ROOT, "nmabsent")    # a working folder with no node_modules
NMTILDE = os.path.join(ROOT, "nmlinked~dir")  # a working folder whose name holds a ~, and whose node_modules is a link
NMSHIM = os.path.join(ROOT, "nmshim")        # a folder whose sitecustomize drops os.path.isjunction
NM_PKG = ('{"name": "app", "scripts": {"setup": "node setup.js", "build": "node build.js",'
          ' "test": "node test.js"}}\n')
NM_SHIM_SOURCE = ("import os.path\n"
                  "if hasattr(os.path, 'isjunction'):\n"
                  "    del os.path.isjunction\n")


def _is_link(path):
    """True for a symlink or a junction. A junction is a reparse point, read the same way on every
    Python 3 that CI runs. os.path.isjunction exists only from Python 3.12."""
    if os.path.islink(path):
        return True
    if os.name != "nt":
        return False
    try:
        attributes = os.stat(path, follow_symlinks=False).st_file_attributes
    except OSError:
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _make_dir_link(target, link):
    """A junction on Windows, which needs no symlink privilege, else a directory symlink."""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(target, link)   # the source comes first: `link` points at `target`
    else:
        os.symlink(target, link, target_is_directory=True)
    if not _is_link(link):
        sys.exit("fixture setup failed: %r is not a link to %r" % (link, target))


def _build_linked_nm():
    """The five working folders of this section, and the shim folder. NMLINKED and NMTILDE hold a link to
    the target, NMREAL holds a real folder, NMABSENT holds none."""
    for folder in (NMTARGET, NMLINKED, NMREAL, NMABSENT, NMTILDE):
        write(os.path.join(folder, "package.json"), NM_PKG)
    write(os.path.join(NMTARGET, "pkg.js"), "module.exports = {};\n")
    _make_dir_link(NMTARGET, os.path.join(NMLINKED, "node_modules"))
    _make_dir_link(NMTARGET, os.path.join(NMTILDE, "node_modules"))
    write(os.path.join(NMREAL, "node_modules", "pkg.js"), "module.exports = {};\n")
    write(os.path.join(NMSHIM, "sitecustomize.py"), NM_SHIM_SOURCE)


lazy_fixture([NMTARGET, NMLINKED, NMREAL, NMABSENT, NMTILDE, NMSHIM], _build_linked_nm)


def nm_case(name, command, expected, cwd, tool="Bash"):
    """One case of this section. Each is tagged for the Windows slice, because a junction is Windows-only."""
    if expected == "deny":
        add(name, expected, rule=NM_RULE, tool=tool, cwd=cwd, windows=True, command=command,
            carries=NM_REMEDY, lacks=NM_LACKS)
    else:
        add(name, expected, tool=tool, cwd=cwd, windows=True, command=command)


# THE INSTALLS, and the commands that rewrite node_modules too: prune, dedupe, rebuild, link and audit fix.
# Each is refused in a linked folder, and each is allowed in a real folder and an absent one.
NM_INSTALLS = (
    ("npm ci", "Bash"), ("npm ci", "PowerShell"),
    ("npm install", "Bash"), ("npm install left-pad", "Bash"),
    ("npm i", "Bash"), ("npm i left-pad", "Bash"),
    ("npm add", "Bash"), ("npm add left-pad", "Bash"),
    ("npm uninstall", "Bash"), ("npm uninstall left-pad", "Bash"),
    ("npm update", "Bash"), ("npm update left-pad", "Bash"),
    ("npm prune", "Bash"), ("npm dedupe", "Bash"), ("npm rebuild", "Bash"), ("npm link", "Bash"),
    ("npm audit fix", "Bash"), ("npm audit --json fix", "Bash"),
)
# THE RECURSIVE DELETES inside node_modules. A bare `rm -rf node_modules` names the link itself, not a
# file inside it, so it is not pinned here.
NM_DELETES = (
    ("rm -rf node_modules/", "Bash"), ("rm -rf node_modules/*", "Bash"),
    ("rm -rf ./node_modules/x", "Bash"), ("Remove-Item -Recurse node_modules\\*", "PowerShell"),
)

for _command, _tool in NM_INSTALLS + NM_DELETES:
    nm_case("linked-nm: refuse " + _command + " (" + _tool + ") in a linked folder",
            _command, "deny", NMLINKED, _tool)
    nm_case("linked-nm: " + _command + " (" + _tool + ") in a real folder is allowed",
            _command, "allow", NMREAL, _tool)
    nm_case("linked-nm: " + _command + " (" + _tool + ") in a folder with no node_modules is allowed",
            _command, "allow", NMABSENT, _tool)

# THE CD FORMS. The working folder is the one the cd names, not the payload cwd.
nm_case("linked-nm: cd into the linked folder, then npm ci, is refused",
        "cd " + slash(NMLINKED) + " && npm ci", "deny", NMABSENT)
nm_case("linked-nm: cd into a real folder, then npm ci, is allowed, though the payload cwd is linked",
        "cd " + slash(NMREAL) + " && npm ci", "allow", NMLINKED)
nm_case("linked-nm: cd into a folder with no node_modules, then npm ci, is allowed",
        "cd " + slash(NMABSENT) + " && npm ci", "allow", NMLINKED)
nm_case("linked-nm: a variable folder linked, cd \"$R\" then npm ci, is refused, as the literal cd is",
        "R=" + slash(NMLINKED) + "; cd \"$R\" && npm ci", "deny", NMABSENT)
nm_case("linked-nm: the literal twin, a cd to the linked folder then npm ci, is refused",
        "cd " + slash(NMLINKED) + " && npm ci", "deny", NMABSENT)
# A ~ inside a folder's name is a plain character, so the variable naming it is read. The literal twin comes
# first: it must deny on the same folder before the variable form means anything. The Windows temp folder
# (RUNNER~1) is the real case; this folder's name carries the same ~ on every platform.
nm_case("linked-nm: the literal twin, a cd to a linked folder whose name holds ~, then npm ci, is refused",
        "cd " + slash(NMTILDE) + " && npm ci", "deny", NMABSENT)
nm_case("linked-nm: a variable folder linked, whose name holds ~, cd \"$R\" then npm ci, is refused, as its literal twin is",
        "R=" + slash(NMTILDE) + "; cd \"$R\" && npm ci", "deny", NMABSENT)

# THE PREFIX FLAG. `npm ci --prefix <dir>` installs into <dir>, so the folder the flag names is the one judged,
# not the working folder. Each case is the other folder's answer: a real prefix from a linked folder is allowed,
# and a linked prefix from a real folder is refused.
nm_case("linked-nm: npm ci --prefix a real folder, run from a linked folder, is allowed",
        "npm ci --prefix " + slash(NMREAL), "allow", NMLINKED)
nm_case("linked-nm: npm ci --prefix a linked folder, run from a real folder, is refused",
        "npm ci --prefix " + slash(NMLINKED), "deny", NMREAL)

# THE PREFIX FLAG, UNRESOLVED AND REPEATED. A prefix the guard cannot name (a shell variable, a command substitution,
# a home path) must not hide the working folder: the walk from it still decides, so a linked folder stays refused.
# The other forms of the flag (`--prefix=dir`, a relative dir, a repeated flag) name the folder npm installs into.
nm_case('linked-nm: npm ci --prefix "$PWD" from a linked folder is refused',
        'npm ci --prefix "$PWD"', "deny", NMLINKED)
nm_case('linked-nm: npm ci --prefix "$(git rev-parse --show-toplevel)" from a linked folder is refused',
        'npm ci --prefix "$(git rev-parse --show-toplevel)"', "deny", NMLINKED)
nm_case("linked-nm: npm ci --prefix ~/linked from a linked folder is refused",
        "npm ci --prefix ~/linked", "deny", NMLINKED)
nm_case("linked-nm: npm ci --prefix=<linked folder>, run from a real folder, is refused",
        "npm ci --prefix=" + slash(NMLINKED), "deny", NMREAL)
nm_case("linked-nm: npm ci --prefix=<real folder>, run from a linked folder, is allowed",
        "npm ci --prefix=" + slash(NMREAL), "allow", NMLINKED)
nm_case("linked-nm: npm ci --prefix ../nmlinked, relative, run from a real folder, is refused",
        "npm ci --prefix ../nmlinked", "deny", NMREAL)
nm_case("linked-nm: npm ci with a repeated --prefix whose last value is linked, from a real folder, is refused",
        "npm ci --prefix " + slash(NMREAL) + " --prefix " + slash(NMLINKED), "deny", NMREAL)
nm_case("linked-nm: npm ci with a repeated --prefix whose last value is real, from a linked folder, is allowed",
        "npm ci --prefix " + slash(NMLINKED) + " --prefix " + slash(NMREAL), "allow", NMLINKED)

# THE CONTROLS IN A LINKED FOLDER. Each is the job of a linked folder, and none is refused.
for _command, _tool in (("npm run setup", "Bash"),
                        ("rm node_modules", "Bash"), ("Remove-Item node_modules", "PowerShell")):
    nm_case("linked-nm: " + _command + " (" + _tool + ") in a linked folder is allowed",
            _command, "allow", NMLINKED, _tool)
nm_case("linked-nm: cd into the linked folder, then npm run setup, is allowed",
        "cd " + slash(NMLINKED) + " && npm run setup", "allow", NMABSENT)

# SCANNER CASES. The guard reads the command as shell text. A comment opener, or a lone quote, inside a
# string must not hide a real `npm ci` after it, and a `npm ci` inside a string, heredoc or comment is data.
nm_case("linked-nm: scanner: a # inside quotes does not hide npm ci after it",
        'echo "# ready"; npm ci', "deny", NMLINKED)
nm_case("linked-nm: scanner: a /* inside quotes does not hide npm ci after it",
        'echo "/* open"; npm ci', "deny", NMLINKED)
nm_case("linked-nm: scanner: a lone apostrophe inside quotes does not hide npm ci after it",
        "echo \"Don't\"; npm ci", "deny", NMLINKED)
nm_case("linked-nm: scanner: npm ci in a single-quoted echo is data, allowed",
        "echo 'run npm ci later'", "allow", NMLINKED)
nm_case("linked-nm: scanner: npm ci in a heredoc body with a lone apostrophe is data, allowed",
        "cat <<'EOF'\nDon't run npm ci here\nEOF", "allow", NMLINKED)
nm_case("linked-nm: scanner: npm ci in a multi-line quoted string is data, allowed",
        'echo "first line\nnpm ci later"', "allow", NMLINKED)
nm_case("linked-nm: scanner: npm ci in a comment line is not run, allowed",
        "# install with npm ci later\necho ready", "allow", NMLINKED)


# THE PER-SEGMENT FOLDER. A `cd` moves the working folder for the segments after it, and no others, so
# each install is judged by the folder it runs in.
nm_case("linked-nm: cd into the linked folder, npm ci, then cd .. is refused",
        "cd " + slash(NMLINKED) + " && npm ci && cd ..", "deny", NMABSENT)
nm_case("linked-nm: cd into the linked folder, npm ci, then cd into a real folder is refused",
        "cd " + slash(NMLINKED) + " && npm ci && cd " + slash(NMREAL), "deny", NMABSENT)
nm_case("linked-nm: cd into a real folder, npm ci, then cd into the linked folder is allowed",
        "cd " + slash(NMREAL) + " && npm ci && cd " + slash(NMLINKED), "allow", NMLINKED)

# THE GROUPS AND SUBSTITUTIONS. A subshell or a command substitution runs its install in the folder it is in.
nm_case("linked-nm: a subshell that cds into the linked folder, then npm ci, is refused",
        "(cd " + slash(NMLINKED) + " && npm ci)", "deny", NMABSENT)
nm_case("linked-nm: npm ci in a subshell, run in the linked folder, is refused",
        "(npm ci)", "deny", NMLINKED)
nm_case("linked-nm: npm ci in a command substitution, run in the linked folder, is refused",
        "echo $(npm ci)", "deny", NMLINKED)

# THE ALIASES. npm resolves each of these to an install, an update or a removal of the same tree.
NM_ALIASES = ("npm clean-install", "npm install-clean", "npm ic", "npm cit",
              "npm remove x", "npm rm x", "npm r x", "npm un x", "npm up", "npm upgrade",
              "npm in x", "npm ins x", "npm isntall x")
for _command in NM_ALIASES:
    nm_case("linked-nm: refuse " + _command + " (Bash) in a linked folder", _command, "deny", NMLINKED)

# THE VALUE FLAGS. A global flag that takes a value, placed before the subcommand, runs the same install.
nm_case("linked-nm: refuse npm --loglevel error ci (Bash) in a linked folder",
        "npm --loglevel error ci", "deny", NMLINKED)
nm_case("linked-nm: refuse npm --prefix . ci (Bash) in a linked folder",
        "npm --prefix . ci", "deny", NMLINKED)

# THE OFF-LIST COMMANDS. The guard allows only the read-only commands it lists. Each of these is refused in a
# linked folder: some rewrite node_modules, and the rest are not on the list. A real folder and a folder with
# no node_modules allow each, since neither is a link.
NM_OFF_LIST = (
    "npm unlink x", "npm ddp", "npm rb", "npm ln x", "npm pru", "npm it", "npm install-test",
    "npm install-ci-test", "npm sit", "npm edit x", "npm explore x", "npm init", "npm shrinkwrap",
    "npm instal x", "npm -C . ci",
)
for _command in NM_OFF_LIST:
    nm_case("linked-nm: refuse " + _command + " (Bash) in a linked folder", _command, "deny", NMLINKED)
    nm_case("linked-nm: " + _command + " (Bash) in a real folder is allowed", _command, "allow", NMREAL)
    nm_case("linked-nm: " + _command + " (Bash) in a folder with no node_modules is allowed",
            _command, "allow", NMABSENT)

# THE WORKSPACE FLAGS ON `npm version`. With a workspace flag, npm reifies the linked root, so the command
# changes the install through the link. Without one it only rewrites package.json (a control below).
# `verison` is npm's own alias of version, so it takes the same flags.
NM_WORKSPACE_VERSION = (
    "npm version patch -w a", "npm version patch --workspaces", "npm version patch -ws",
    "npm version patch --workspace=a", "npm -w a version patch", "npm verison patch -w a",
)
# THE DRY RUNS THAT STILL RUN INSTALL SCRIPTS. npm rebuild, rb and edit run install scripts even with
# --dry-run, so a dry run is no no-change for them. `npm prune --dry-run` and `npm audit fix --dry-run`
# stay allowed (a control below). npm reads an unambiguous abbreviation as the full command, so `reb`,
# `rebuil` and `edi` are these same writers.
NM_DRY_RUN_WRITERS = (
    "npm rebuild --dry-run", "npm rb x --dry-run", "npm edit x --dry-run", "npm --dry-run rebuild",
    "npm rebuil --dry-run", "npm reb --dry-run", "npm edi x --dry-run",
)
for _command in NM_WORKSPACE_VERSION + NM_DRY_RUN_WRITERS:
    nm_case("linked-nm: refuse " + _command + " (Bash) in a linked folder", _command, "deny", NMLINKED)
    nm_case("linked-nm: " + _command + " (Bash) in a real folder is allowed", _command, "allow", NMREAL)
    nm_case("linked-nm: " + _command + " (Bash) in a folder with no node_modules is allowed",
            _command, "allow", NMABSENT)

# THE WORKSPACE-UPDATE FLAG. `--no-workspaces-update` turns npm's reify off, so a workspace flag with it changes no
# install. `--workspaces-update=false` with no workspace flag never enters npm's workspace path, so it changes no
# install either. The last case is a control: the positive flag with a workspace flag still reifies, so it is refused.
nm_case("linked-nm: npm version patch -w a --no-workspaces-update (Bash) in a linked folder is allowed",
        "npm version patch -w a --no-workspaces-update", "allow", NMLINKED)
nm_case("linked-nm: npm version patch --workspaces-update=false (Bash) in a linked folder is allowed",
        "npm version patch --workspaces-update=false", "allow", NMLINKED)
nm_case("linked-nm: npm version patch -w a --workspaces-update (Bash) in a linked folder is refused",
        "npm version patch -w a --workspaces-update", "deny", NMLINKED)

# THE FALSE-ALARM CONTROLS in a linked folder. None of these changes the linked install, so none is refused.
nm_case("linked-nm: npm i -g x (Bash) in a linked folder is allowed, a global install",
        "npm i -g x", "allow", NMLINKED)
nm_case("linked-nm: npm install --help (Bash) in a linked folder is allowed",
        "npm install --help", "allow", NMLINKED)
nm_case("linked-nm: npm ci --dry-run (Bash) in a linked folder is allowed",
        "npm ci --dry-run", "allow", NMLINKED)
nm_case("linked-nm: npm ci in a quoted echo, in a linked folder, is allowed",
        'echo "npm ci"', "allow", NMLINKED)
# THE READ-ONLY ABBREVIATIONS. npm reads `pac` as pack and `publ` as publish, and both are read-only, so a dry run of
# either is allowed. The full names are the controls, and the guard already allows them.
nm_case("linked-nm: npm pac --dry-run (Bash) in a linked folder is allowed, pac is pack",
        "npm pac --dry-run", "allow", NMLINKED)
nm_case("linked-nm: npm publ --dry-run (Bash) in a linked folder is allowed, publ is publish",
        "npm publ --dry-run", "allow", NMLINKED)
nm_case("linked-nm: npm pack --dry-run (Bash) in a linked folder is allowed",
        "npm pack --dry-run", "allow", NMLINKED)
nm_case("linked-nm: npm publish --dry-run (Bash) in a linked folder is allowed",
        "npm publish --dry-run", "allow", NMLINKED)

# THE READ-ONLY CONTROLS in a linked folder. Each runs a command on the read-only list or a dry run, or
# names no command (bare `npm`, `npm -v`), so none is refused.
NM_READ_ONLY = (
    "npm", "npm -v", "npm ls", "npm list", "npm -C . ls", "npm view x", "npm outdated", "npm audit",
    "npm audit signatures", "npm explain x", "npm fund", "npm exec -- tsc", "npm config get registry",
    "npm help install", "npm prune --dry-run", "npm audit fix --dry-run", "npm version patch",
    "npm version", "npm rebuild --help", "npm run build", "npm test", "npm verison patch", "npm reb --help",
)
for _command in NM_READ_ONLY:
    nm_case("linked-nm: " + _command + " (Bash) in a linked folder is allowed", _command, "allow", NMLINKED)

# THE JUNCTION WITHOUT os.path.isjunction. Python 3.11, the CI interpreter, has no os.path.isjunction, so
# the link test must read the junction itself. This case runs the guard with that function removed.
def nm_case_without_isjunction(name, command, expected, cwd, tool="Bash"):
    """nm_case, run with os.path.isjunction removed from the guard's interpreter by NMSHIM."""
    nm_case(name, command, expected, cwd, tool)
    CASES[-1]["env"] = {"PYTHONPATH": os.pathsep.join(
        filter(None, (NMSHIM, os.environ.get("PYTHONPATH"))))}


nm_case_without_isjunction("linked-nm: npm ci in a junction is refused with os.path.isjunction removed",
                           "npm ci", "deny", NMLINKED)


# THE WALK UP. npm runs an install in the first folder, from the working folder upward, that holds a
# package.json or a node_modules. So a sub folder with neither installs into the linked root above it,
# and a sub folder with either installs into its own tree, whatever the root holds.
NMNEST = os.path.join(ROOT, "nmnest")    # a root whose node_modules is a link, with sub folders under it
NM_SUB = os.path.join(NMNEST, "sub")                        # no package.json, no node_modules
NM_DEEP = os.path.join(NMNEST, "sub", "deep", "er")         # two levels down, still neither
NM_WEB = os.path.join(NMNEST, "packages", "web")            # a workspace folder with no package.json
NM_OWN_REAL = os.path.join(NMNEST, "own_real")              # its own package.json and a real node_modules
NM_OWN_PKG = os.path.join(NMNEST, "own_pkg")                # its own package.json, no node_modules
NM_REAL_ONLY = os.path.join(NMNEST, "real_only")            # a real node_modules, no package.json


def _build_linked_nm_nest():
    write(os.path.join(NMNEST, "package.json"), NM_PKG)
    _make_dir_link(NMTARGET, os.path.join(NMNEST, "node_modules"))
    for folder in (NM_SUB, NM_DEEP, NM_WEB):
        write(os.path.join(folder, "notes.txt"), "x\n")
    write(os.path.join(NM_OWN_REAL, "package.json"), NM_PKG)
    write(os.path.join(NM_OWN_REAL, "node_modules", "pkg.js"), "module.exports = {};\n")
    write(os.path.join(NM_OWN_PKG, "package.json"), NM_PKG)
    write(os.path.join(NM_REAL_ONLY, "node_modules", "pkg.js"), "module.exports = {};\n")


lazy_fixture([NMNEST], _build_linked_nm_nest)

for _command in ("npm ci", "npm install", "npm install left-pad"):
    nm_case("linked-nm: walk: refuse " + _command + " in a sub folder with no package.json under a linked root",
            _command, "deny", NM_SUB)
nm_case("linked-nm: walk: refuse npm ci two levels below a linked root",
        "npm ci", "deny", NM_DEEP)
nm_case("linked-nm: walk: refuse npm install in a workspace folder under a linked root",
        "npm install", "deny", NM_WEB)
nm_case("linked-nm: walk: refuse cd packages/web, then npm install, from a linked root",
        "cd packages/web && npm install", "deny", NMNEST)
nm_case("linked-nm: walk: refuse cd into a sub folder by full path, then npm ci",
        "cd " + slash(NM_SUB) + " && npm ci", "deny", NMABSENT)
# The false-alarm controls. npm stops at the first package.json or node_modules, so each folder below
# installs into its own tree and the linked root is never touched.
nm_case("linked-nm: walk: npm ci in a sub folder with its own package.json and a real node_modules is allowed",
        "npm ci", "allow", NM_OWN_REAL)
nm_case("linked-nm: walk: npm install in a sub folder with its own package.json and no node_modules is allowed",
        "npm install", "allow", NM_OWN_PKG)
nm_case("linked-nm: walk: npm ci in a sub folder with a real node_modules and no package.json is allowed",
        "npm ci", "allow", NM_REAL_ONLY)
nm_case("linked-nm: walk: cd into a sub folder with its own package.json, then npm ci, is allowed",
        "cd own_pkg && npm ci", "allow", NMNEST)
nm_case("linked-nm: walk: npm run build in a sub folder under a linked root is allowed",
        "npm run build", "allow", NM_SUB)


# THE WORKSPACE PACKAGES. npm runs an install in a workspace package from the workspace root, so a package folder
# with its own package.json still installs into the linked root above it. A folder that the root's workspaces field
# does not name keeps its own tree, and so does every folder under a root with no workspaces field.
NMWS = os.path.join(ROOT, "nmws")                       # a root with workspaces, whose node_modules is a link
NMWSREAL = os.path.join(ROOT, "nmwsreal")               # the same root, whose node_modules is a real folder
NMSTAND = os.path.join(ROOT, "nmstand")                 # a root with no workspaces field, whose node_modules is a link
NMBRACE = os.path.join(ROOT, "nmbrace")                 # a root whose workspaces field is a brace glob, a link
NMNEG = os.path.join(ROOT, "nmneg")                     # a root that lists `!packages/a` before its glob, a link
NMNEG2 = os.path.join(ROOT, "nmneg2")                   # a root that lists `!packages/a` after its glob, a link
NMWSLINK = os.path.join(ROOT, "nmwslink")               # a root whose node_modules is a real folder, with a member that has a link
NM_WSLINK_MEMBER = os.path.join(NMWSLINK, "packages", "linked")  # that member: its own node_modules is a link to NMTARGET
NM_WSLINK_PLAIN = os.path.join(NMWSLINK, "packages", "plain")    # a member of that root with no node_modules of its own
NM_WS_PKG = os.path.join(NMWS, "packages", "a")         # a workspace package, with its own package.json
NM_WS_OUT = os.path.join(NMWS, "tools", "x")            # a folder the workspaces field does not name
NM_STAND_NESTED = os.path.join(NMSTAND, "nested")       # a package under the root with no workspaces field
NM_MEMBER_PKG = '{"name": "member", "version": "1.0.0"}\n'
# (root, workspaces field, member folders, is node_modules a link). Each member gets its own package.json, so a
# folder the glob names is the first stop of the walk, and a folder it does not name has its own tree. The
# member `.hid` is a dot folder: packages/* names it, and npm does not.
NM_WS_ROOTS = (
    (NMWS, ["packages/*"], ("a", ".hid"), True),
    (NMWSREAL, ["packages/*"], ("a",), False),
    (NMBRACE, ["packages/{a,b}"], ("a", "b", "c"), True),
    (NMNEG, ["!packages/a", "packages/*", "packages/a"], ("a", "b"), True),
    (NMNEG2, ["packages/*", "!packages/a"], ("a", "b"), True),
    (NMWSLINK, ["packages/*"], ("linked", "plain"), False),
)
# (root, member) pairs whose member's own node_modules is a link to NMTARGET. Each root's node_modules is set above.
NM_WS_LINKED_MEMBERS = ((NMWSLINK, "linked"),)


def _build_linked_nm_workspaces():
    materialize(NMTARGET)  # the link's target is built by its own home first, so no link points at nothing
    for root, workspaces, members, linked in NM_WS_ROOTS:
        write(os.path.join(root, "package.json"),
              json.dumps({"name": "root", "private": True, "workspaces": workspaces}) + "\n")
        for member in members:
            write(os.path.join(root, "packages", member, "package.json"), NM_MEMBER_PKG)
        if linked:
            _make_dir_link(NMTARGET, os.path.join(root, "node_modules"))
        else:
            write(os.path.join(root, "node_modules", "pkg.js"), "module.exports = {};\n")
    for root, member in NM_WS_LINKED_MEMBERS:
        _make_dir_link(NMTARGET, os.path.join(root, "packages", member, "node_modules"))
    write(os.path.join(NM_WS_OUT, "package.json"), NM_MEMBER_PKG)
    write(os.path.join(NMSTAND, "package.json"), NM_PKG)
    write(os.path.join(NM_STAND_NESTED, "package.json"), NM_MEMBER_PKG)
    _make_dir_link(NMTARGET, os.path.join(NMSTAND, "node_modules"))


lazy_fixture([NMWS, NMWSREAL, NMSTAND, NMBRACE, NMNEG, NMNEG2, NMWSLINK], _build_linked_nm_workspaces)

nm_case("linked-nm: workspace: refuse cd packages/a, then npm install, from a linked workspace root",
        "cd packages/a && npm install", "deny", NMWS)
nm_case("linked-nm: workspace: refuse npm install with the workspace package as the working folder",
        "npm install", "deny", NM_WS_PKG)
# npm version without a workspace flag, run in a workspace package, takes npm's workspace path and reifies the root.
nm_case("linked-nm: workspace: refuse cd packages/a, then npm version patch, from a linked workspace root",
        "cd packages/a && npm version patch", "deny", NMWS)
# A BARE `npm version` names no bump, so it only lists the versions and reifies nothing (npm 10.9.9). The bump from
# the same member, the case above, is the control that stays refused.
nm_case("linked-nm: workspace: cd packages/a, then bare npm version, from a linked workspace root is allowed",
        "cd packages/a && npm version", "allow", NMWS)
# The controls. A real root under the same workspaces allows, a folder the workspaces field does not name allows,
# and a standalone package under a root with no workspaces field allows, for an install and for a version bump.
nm_case("linked-nm: workspace: cd packages/a, then npm install, under a real root is allowed",
        "cd packages/a && npm install", "allow", NMWSREAL)
nm_case("linked-nm: workspace: cd tools/x, then npm install, under a linked workspace root is allowed",
        "cd tools/x && npm install", "allow", NMWS)
nm_case("linked-nm: workspace: cd nested, then npm install, under a linked root with no workspaces field is allowed",
        "cd nested && npm install", "allow", NMSTAND)
nm_case("linked-nm: workspace: cd nested, then npm version patch, under a linked root with no workspaces field is allowed",
        "cd nested && npm version patch", "allow", NMSTAND)

# THE BRACE GLOB. npm expands `packages/{a,b}` as minimatch does, so it names a and b and not c (npm 10.9.9). A folder
# the glob names is a member, and an install in it runs from the linked root above it.
nm_case("linked-nm: workspace: refuse cd packages/a, then npm install, under a brace glob workspaces field",
        "cd packages/a && npm install", "deny", NMBRACE)
nm_case("linked-nm: workspace: cd packages/c, then npm install, under a brace glob workspaces field is allowed",
        "cd packages/c && npm install", "allow", NMBRACE)

# THE NEGATION ORDER. npm 10.9.9 visits packages/a under ["!packages/a", "packages/*", "packages/a"], and does not
# visit it under ["packages/*", "!packages/a"]. The second root is the control, so a guard that ignores `!` fails here.
nm_case("linked-nm: workspace: refuse cd packages/a, then npm install, under a root that lists !packages/a before its glob",
        "cd packages/a && npm install", "deny", NMNEG)
nm_case("linked-nm: workspace: cd packages/a, then npm install, under a root that lists !packages/a after its glob is allowed",
        "cd packages/a && npm install", "allow", NMNEG2)

# THE DOT FOLDER. npm's glob does not match a name that starts with a dot, so `packages/*` leaves out packages/.hid
# (npm 10.9.9). That folder installs into its own tree.
nm_case("linked-nm: workspace: cd packages/.hid, then npm install, under a linked root whose glob is packages/* is allowed",
        "cd packages/.hid && npm install", "allow", NMWS)

# THE DRY RUN OF A VERSION BUMP. A dry run does not reify the linked root (it still bumps package.json) (npm 10.9.9: a real
# `npm version patch` creates the root's node_modules, a dry run creates none). The real runs stay refused above.
nm_case("linked-nm: workspace: cd packages/a, then npm version patch --dry-run, under a linked workspace root is allowed",
        "cd packages/a && npm version patch --dry-run", "allow", NMWS)
nm_case("linked-nm: workspace: npm version -w a --dry-run, under a linked workspace root is allowed",
        "npm version -w a --dry-run", "allow", NMWS)

# THE NO-WORKSPACES FLAG. With `--no-workspaces`, npm's prefix is the member itself (npm 10.9.9: `npm prefix
# --no-workspaces` run in the member prints the member), so the install writes the member's own folder and never the
# root's link. The deny at the top of this block is the scope check on this folder: without the flag, the same
# command walks up to the linked root and is refused.
nm_case("linked-nm: workspace: npm ci --no-workspaces in a member under a linked workspace root is allowed",
        "npm ci --no-workspaces", "allow", NM_WS_PKG)

# THE WORKSPACES-OFF FORMS. `--workspaces=false` and `--workspaces false` turn workspaces off as `--no-workspaces`
# does (npm 10.9.9: `npm prefix --workspaces=false` and `npm prefix --workspaces false`, run in the member, print the
# member). The member has no node_modules of its own, so the install writes nothing through the linked root.
nm_case("linked-nm: workspace: npm ci --workspaces=false in a member under a linked workspace root is allowed",
        "npm ci --workspaces=false", "allow", NM_WS_PKG)
nm_case("linked-nm: workspace: npm ci --workspaces false in a member under a linked workspace root is allowed",
        "npm ci --workspaces false", "allow", NM_WS_PKG)
# THE LATER WORKSPACES FLAG. The last workspaces option wins, as in npm, so `--workspaces` or `-ws` after
# `--no-workspaces` turns workspaces on again and the walk reaches the linked root (npm 10.9.9: `npm prefix
# --no-workspaces --workspaces` and `npm prefix --no-workspaces -ws`, run in the member, print the root).
nm_case("linked-nm: workspace: npm ci --no-workspaces --workspaces in a member under a linked workspace root is refused",
        "npm ci --no-workspaces --workspaces", "deny", NM_WS_PKG)
nm_case("linked-nm: workspace: npm ci --no-workspaces -ws in a member under a linked workspace root is refused",
        "npm ci --no-workspaces -ws", "deny", NM_WS_PKG)


# =========================================================================== 4. environment files

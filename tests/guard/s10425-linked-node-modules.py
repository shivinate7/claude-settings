# section 10425
FAMILY = "linked-node-modules"
FAMILIES["linked-node-modules"] = "a dependency install or a recursive delete through a node_modules that is a link"
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
NM_WORKSPACE_VERSION = (
    "npm version patch -w a", "npm version patch --workspaces", "npm version patch -ws",
    "npm version patch --workspace=a", "npm -w a version patch",
)
# THE DRY RUNS THAT STILL RUN INSTALL SCRIPTS. npm rebuild, rb and edit run install scripts even with
# --dry-run, so a dry run is no no-change for them. `npm prune --dry-run` and `npm audit fix --dry-run`
# stay allowed (a control below).
NM_DRY_RUN_WRITERS = (
    "npm rebuild --dry-run", "npm rb x --dry-run", "npm edit x --dry-run", "npm --dry-run rebuild",
)
for _command in NM_WORKSPACE_VERSION + NM_DRY_RUN_WRITERS:
    nm_case("linked-nm: refuse " + _command + " (Bash) in a linked folder", _command, "deny", NMLINKED)
    nm_case("linked-nm: " + _command + " (Bash) in a real folder is allowed", _command, "allow", NMREAL)
    nm_case("linked-nm: " + _command + " (Bash) in a folder with no node_modules is allowed",
            _command, "allow", NMABSENT)

# THE FALSE-ALARM CONTROLS in a linked folder. None of these changes the linked install, so none is refused.
nm_case("linked-nm: npm i -g x (Bash) in a linked folder is allowed, a global install",
        "npm i -g x", "allow", NMLINKED)
nm_case("linked-nm: npm install --help (Bash) in a linked folder is allowed",
        "npm install --help", "allow", NMLINKED)
nm_case("linked-nm: npm ci --dry-run (Bash) in a linked folder is allowed",
        "npm ci --dry-run", "allow", NMLINKED)
nm_case("linked-nm: npm ci in a quoted echo, in a linked folder, is allowed",
        'echo "npm ci"', "allow", NMLINKED)

# THE READ-ONLY CONTROLS in a linked folder. Each runs a command on the read-only list or a dry run, or
# names no command (bare `npm`, `npm -v`), so none is refused.
NM_READ_ONLY = (
    "npm", "npm -v", "npm ls", "npm list", "npm -C . ls", "npm view x", "npm outdated", "npm audit",
    "npm audit signatures", "npm explain x", "npm fund", "npm exec -- tsc", "npm config get registry",
    "npm help install", "npm prune --dry-run", "npm audit fix --dry-run", "npm version patch",
    "npm rebuild --help", "npm run build", "npm test",
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


# =========================================================================== 4. environment files

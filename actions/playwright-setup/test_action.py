"""Static and fake-run checks of actions/playwright-setup. `python3 actions/playwright-setup/test_action.py`.
Asserts the opt-in `system-deps` input (default empty), that its step runs the Playwright install-deps
command for exactly the listed browsers, on Linux only, under a time cap, and that chromium or an unknown
name fails the job with one line. Every other step runs no apt. The browser cache key holds the OS id and
version that pin.sh writes (`os=ubuntu-24.04`), never a runner env value or a literal version. pin.sh falls
back to RUNNER_OS, with a warning, when os-release has no VERSION_ID or is missing, and the
cache step has no restore-keys, because a prefix restore would bring back a browser built for another OS.
It proves the step's shape and its shell scripts, not a real WebKit launch. Stdlib only."""
import atexit, os, re, shutil, stat, subprocess, sys, tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(HERE)), "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

RUN_FOLDER = _test_temp.run_folder()  # its sweep of old sibling folders is proved in lint/test_find_copies.py
atexit.register(shutil.rmtree, RUN_FOLDER, True)

text = open(os.path.join(HERE, "action.yml"), encoding="utf-8").read()
PIN = os.path.join(HERE, "pin.sh")
STEP_NAME = "Install the system libraries"
CACHE_STEP = "Cache the browsers"
GOOD_KEY = "playwright-${{ runner.os }}-${{ steps.pin.outputs.os }}-${{ steps.pin.outputs.version }}-${{ inputs.browsers }}"
APT = re.compile(r"install-deps|--with-deps|\bapt(-get)?\b")
FIELD = re.compile(r"^\s*(?:- )?([\w-]+):(?:\s+(.*))?$")
BLOCK_OPEN = re.compile(r"(?:^|\s)[|>][+-]?\d?$")
BASH = "/bin/bash" if os.path.exists("/bin/bash") else "bash"

failed = 0


def check(name, ok, out=""):
    global failed
    print(("ok - " if ok else "FAIL - ") + name)
    if not ok:
        failed += 1
        if out:
            print(out)


def steps(src=None):
    """{name: block text} for each step under `runs.steps`."""
    src = text if src is None else src
    body = src.split("\n  steps:\n", 1)[1] if "\n  steps:\n" in src else ""
    out = {}
    for chunk in re.split(r"\n(?=    - name: )", body):
        m = re.match(r"\s*- name: (.+)", chunk)
        if m:
            out[m.group(1).strip()] = chunk
    return out


def run_script(block):
    """The step's `run: |` block, dedented 8 spaces."""
    if "      run: |\n" not in block:
        return ""
    lines = block.split("      run: |\n", 1)[1].split("\n")
    kept = []
    for l in lines:
        if l.strip() and not l.startswith("        "):
            break
        kept.append(l[8:])
    return "\n".join(kept)


def env_value(block, key):
    m = re.search(r"^        %s: \"?([^\"\n]*)\"?$" % re.escape(key), block, re.M)
    return m.group(1) if m else None


def strip_comment(line):
    """The line without a trailing YAML comment. A `#` starts one only after a space and outside quotes.
    A quote opens a string only at the start of a value, so an apostrophe or a quote inside plain text is text."""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'" and (not line[:i].strip() or line[:i].rstrip()[-1] in ":-[{,"):
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def fields(block):
    """(key, value) for each YAML key line in a step block. Comment lines and block-scalar bodies
    (after `run: |` and the like) are skipped, so a `key:` inside a script does not count."""
    out, body_indent = [], None
    for line in block.splitlines():
        indent = len(line) - len(line.lstrip(" "))
        if body_indent is not None:
            if not line.strip() or indent > body_indent:
                continue
            body_indent = None
        m = FIELD.match(strip_comment(line))
        if not m:
            continue
        value = m.group(2) or ""
        out.append((m.group(1), value))
        if BLOCK_OPEN.search(value):
            body_indent = indent
    return out


def cache_key(src=None):
    """The cache step's `key:` value, or None when the step has no single key."""
    keys = [v for k, v in fields(steps(src).get(CACHE_STEP, "")) if k == "key"]
    return keys[0] if len(keys) == 1 else None


def has_restore_keys(src=None):
    return any(k == "restore-keys" for k, _ in fields(steps(src).get(CACHE_STEP, "")))


def key_refs_os(key):
    return bool(key) and re.search(r"\$\{\{\s*steps\.pin\.outputs\.os\s*\}\}", key) is not None


def key_has_image_os(key):
    return bool(key) and "ImageOS" in key


def key_has_version_literal(key):
    return bool(key) and re.search(r"\d+\.\d+", key) is not None


def cache_problems(src):
    """What is wrong with the cache step in `src`, as short names. [] is a pass."""
    key = cache_key(src)
    if key is None:
        return ["no single key"]
    bad = [] if key_refs_os(key) else ["no os"]
    if key_has_image_os(key):
        bad.append("ImageOS")
    if key_has_version_literal(key):
        bad.append("version literal")
    if has_restore_keys(src):
        bad.append("restore-keys")
    return bad


def cache_action(key_value, extra=""):
    """A minimal action.yml that holds only the cache step, so fixtures never depend on the real file."""
    return ("runs:\n  steps:\n    - name: %s\n      uses: actions/cache@x # v5.1.0\n      with:\n"
            "        path: ~/.cache/ms-playwright\n        key: %s\n%s" % (CACHE_STEP, key_value, extra))


def fake_node(folder, body):
    """Write an executable `node` into folder/bin, with `body` as its shell script. Returns the bin folder."""
    bindir = os.path.join(folder, "bin")
    os.mkdir(bindir)
    node = os.path.join(bindir, "node")
    with open(node, "w") as f:
        f.write("#!/bin/sh\n" + body)
    os.chmod(node, os.stat(node).st_mode | stat.S_IEXEC)
    return bindir


def fake_run(script, deps, runner_os="Linux", cap="30", node_sleep=0):
    """Run `script` with a fake `node` on PATH that records its arguments. Returns (rc, output, calls)."""
    with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
        log = os.path.join(d, "calls")
        bindir = fake_node(d, 'shift\necho "$*" >> "%s"\nsleep %d\n' % (log, node_sleep))
        path = os.path.join(d, "step.sh")
        with open(path, "w", newline="\n") as f:
            f.write(script)
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ.get("PATH", ""), CLI="/x/cli.js",
                   DEPS=deps, RUNNER_OS=runner_os, CAP=cap)
        p = subprocess.run([BASH, path], env=env, capture_output=True, text=True, timeout=60)
        calls = open(log).read().splitlines() if os.path.exists(log) else []
        return p.returncode, (p.stdout + p.stderr).strip(), calls


def pin_run(os_release, runner_os="Linux", image_os="ubuntu99", env_extra=None):
    """Run pin.sh with a fake `node`. `os_release` is the os-release text, or None for no file at OS_RELEASE.
    ImageOS is a decoy (ubuntu99) unless `image_os` says otherwise. ID and VERSION_ID are removed from the
    environment, so a case that needs them sets them in `env_extra`. A script that reads a decoy, or an
    exported ID that should not fill a gap, fails here. Returns (rc, output, GITHUB_OUTPUT lines)."""
    with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
        bindir = fake_node(d, 'case "$2" in\n  *require.resolve*) echo "%s/node_modules/playwright-core/package.json" ;;\n'
                              '  *) echo 1.55.0 ;;\nesac\n' % d)
        release, out_file = os.path.join(d, "os-release"), os.path.join(d, "github-output")
        if os_release is not None:
            with open(release, "w") as f:
                f.write(os_release)
        open(out_file, "w").close()
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ.get("PATH", ""), DIR=d,
                   GITHUB_OUTPUT=out_file, RUNNER_OS=runner_os, OS_RELEASE=release)
        for name in ("ImageOS", "ID", "VERSION_ID"):
            env.pop(name, None)
        if image_os:
            env["ImageOS"] = image_os
        env.update(env_extra or {})
        p = subprocess.run([BASH, PIN], env=env, capture_output=True, text=True, timeout=60)
        with open(out_file) as f:
            gh = f.read().splitlines()
        return p.returncode, (p.stdout + p.stderr).strip(), gh


def os_line(gh):
    return [l for l in gh if l.startswith("os=")]


def warns(out):
    return any(l.startswith("::warning::") for l in out.splitlines())


check("input system-deps exists, default empty (off)",
      re.search(r'^  system-deps:\n(?:    .*\n)*?    default: ""', text, re.M) is not None)

all_steps = steps()
block = all_steps.get(STEP_NAME, "")
script = run_script(block)
check("a step named '%s' exists" % STEP_NAME, bool(block) and bool(script))
check("the step runs only when system-deps is non-empty",
      re.search(r"^      if: \$\{\{ inputs\.system-deps != '' \}\}$", block, re.M) is not None, block)
check("the step hands the input to the script as DEPS and the CLI from the pin step",
      "DEPS: ${{ inputs.system-deps }}" in block and "CLI: ${{ steps.pin.outputs.cli }}" in block, block)

cap = env_value(block, "CAP")
check("the step has a time cap CAP, in seconds, of at most 600 (under the 11 min incident)",
      cap is not None and cap.isdigit() and 0 < int(cap) <= 600, block)
check("the install-deps call runs under `timeout -k 30 \"$CAP\"`, so a process that ignores SIGTERM is killed",
      re.search(r'timeout -k 30 "\$CAP" node "\$CLI" install-deps \$DEPS', script) is not None, script)

if script:
    rc, out, calls = fake_run(script, "webkit")
    check("webkit on Linux: exit 0, one install-deps call for webkit", rc == 0 and calls == ["install-deps webkit"],
          "%s %s %s" % (rc, out, calls))
    rc, out, calls = fake_run(script, "webkit firefox")
    check("webkit firefox on Linux: one call for exactly those browsers",
          rc == 0 and calls == ["install-deps webkit firefox"], "%s %s %s" % (rc, out, calls))
    rc, out, calls = fake_run(script, "webkit", runner_os="macOS")
    check("webkit on macOS: exit 0, no apt", rc == 0 and calls == [], "%s %s %s" % (rc, out, calls))
    for deps in ("chromium", "safari", "webkit chromium"):
        for os_name in ("Linux", "macOS"):
            rc, out, calls = fake_run(script, deps, runner_os=os_name)
            check("%r on %s: fails with one line, no apt" % (deps, os_name),
                  rc != 0 and calls == [] and len(out.splitlines()) == 1 and "::error" in out,
                  "%s %r %s" % (rc, out, calls))
    for deps in (" ", "\n", " \n "):
        rc, out, calls = fake_run(script, deps)
        check("blank system-deps %r: fails with one line, no install-deps (it would install every browser)" % deps,
              rc != 0 and calls == [] and len(out.splitlines()) == 1 and "::error" in out,
              "%s %r %s" % (rc, out, calls))
    rc, out, calls = fake_run(script, "webkit", cap="1", node_sleep=5)
    check("a run past the cap fails with one line that names the cap",
          rc != 0 and len(out.splitlines()) == 1 and "::error" in out and "1 s" in out, "%s %r" % (rc, out))

others = {n: b for n, b in all_steps.items() if n != STEP_NAME}
bad = [n for n, b in others.items() if APT.search("\n".join(l for l in b.splitlines() if not l.strip().startswith("#")))]
check("the default path runs no apt: no other step names install-deps, --with-deps or apt", others and not bad, str(bad))

# pin.sh writes the OS id and version of the runner into the browser cache key.
pins = {ver: pin_run('ID=ubuntu\nVERSION_ID="%s"\n' % ver) for ver in ("24.04", "26.04")}
rc, out, gh = pins["24.04"]
check("pin.sh on Linux exits 0 and still writes version= (the output it already had)",
      rc == 0 and "version=1.55.0" in gh, "%s %r %s" % (rc, out, gh))
for ver, (rc, out, gh) in pins.items():
    check("pin.sh on Ubuntu %s writes os=ubuntu-%s, from the os-release file" % (ver, ver),
          [l for l in gh if l.startswith("os=")] == ["os=ubuntu-" + ver], "%s %r %s" % (rc, out, gh))
os_24, os_26 = ([l for l in pins[v][2] if l.startswith("os=")] for v in ("24.04", "26.04"))
check("the os value differs between Ubuntu 24.04 and 26.04", bool(os_24) and os_24 != os_26, "%s %s" % (os_24, os_26))

# Fallbacks. A rolling distro has no VERSION_ID; no file means RUNNER_OS; an exported ID or VERSION_ID
# never fills a gap in os-release; non-Linux takes ImageOS, else RUNNER_OS. Each fallback warns on Linux.
rolling = pin_run("ID=arch\n")
check("pin.sh on Linux with ID but no VERSION_ID (rolling) exits 0 and writes os=arch",
      rolling[0] == 0 and os_line(rolling[2]) == ["os=arch"], "%s %r %s" % rolling)
check("pin.sh on Linux with ID but no VERSION_ID (rolling) prints a ::warning:: line",
      rolling[0] == 0 and warns(rolling[1]), "%s %r" % rolling[:2])
no_file = pin_run(None)
check("pin.sh on Linux with no os-release file exits 0 and writes os=Linux (RUNNER_OS), not ImageOS",
      no_file[0] == 0 and os_line(no_file[2]) == ["os=Linux"], "%s %r %s" % no_file)
check("pin.sh on Linux with no os-release file prints a ::warning:: line",
      no_file[0] == 0 and warns(no_file[1]), "%s %r" % no_file[:2])
gaps = pin_run("ID=debian\n", env_extra={"ID": "arch", "VERSION_ID": "9.9"})
check("exported ID and VERSION_ID do not fill gaps: os-release with only ID=debian writes os=debian",
      gaps[0] == 0 and os_line(gaps[2]) == ["os=debian"], "%s %r %s" % gaps)
mac = pin_run(None, runner_os="macOS", image_os="macos15")
check("pin.sh on macOS with ImageOS=macos15 writes os=macos15",
      mac[0] == 0 and os_line(mac[2]) == ["os=macos15"], "%s %r %s" % mac)
win = pin_run(None, runner_os="Windows", image_os=None)
check("pin.sh on Windows with no ImageOS writes os=Windows (RUNNER_OS)",
      win[0] == 0 and os_line(win[2]) == ["os=Windows"], "%s %r %s" % win)

# The cache step's key. Checks read the key line only, so a comment that mentions a name does not count.
check("a step named '%s' exists" % CACHE_STEP, bool(all_steps.get(CACHE_STEP)))
key = cache_key()
check("the browser cache key references steps.pin.outputs.os", key_refs_os(key), "key: %r" % key)
check("the browser cache key holds no ImageOS (the env context does not hold it, so it would be empty)",
      key is not None and not key_has_image_os(key), "key: %r" % key)
check("the browser cache key holds no literal version (no \\d+\\.\\d+)",
      key is not None and not key_has_version_literal(key), "key: %r" % key)
check("the cache step has no restore-keys (a prefix restore would bring back a browser for another OS)",
      not has_restore_keys(), "steps: %r" % steps().get(CACHE_STEP, ""))

# Self-checks: the scanner and each check go red on the defect they guard, using fixtures.
check("the fixture with the intended key passes every cache check", cache_problems(cache_action(GOOD_KEY)) == [],
      repr(cache_problems(cache_action(GOOD_KEY))))
check("a key that reads steps.pin.outputs.os is replaced by env.ImageOS: flagged",
      cache_problems(cache_action(GOOD_KEY.replace("${{ steps.pin.outputs.os }}", "${{ env.ImageOS }}"))) ==
      ["no os", "ImageOS"], "")
check("a key with a literal ubuntu-24.04 is flagged for the version literal and the missing os",
      cache_problems(cache_action(GOOD_KEY.replace("${{ steps.pin.outputs.os }}", "ubuntu-24.04"))) ==
      ["no os", "version literal"], "")
check("a restore-keys line in the cache step is flagged",
      cache_problems(cache_action(GOOD_KEY, extra="        restore-keys: playwright-${{ runner.os }}-\n")) ==
      ["restore-keys"], "")
check("a comment on the key line that names ImageOS and 24.04 does not count",
      cache_problems(cache_action(GOOD_KEY + "  # ImageOS 24.04 and restore-keys: not in the key")) == [],
      repr(cache_problems(cache_action(GOOD_KEY + "  # ImageOS 24.04 and restore-keys: not in the key"))))
check("a comment line that names restore-keys does not count",
      cache_problems(cache_action(GOOD_KEY, extra="        # restore-keys: would bring the bug back\n")) == [],
      "")
check("a block scalar whose body holds key: and restore-keys: lines does not count",
      cache_problems(cache_action(GOOD_KEY, extra="      run: |\n        key: x\n        restore-keys: y\n")) == [],
      "")
check("strip_comment keeps a '#' inside quotes and drops the comment after it",
      strip_comment('key: "a # b" # c') == 'key: "a # b"', strip_comment('key: "a # b" # c'))
check("strip_comment reads an apostrophe in plain text as text, not as a quote",
      strip_comment("key: say it's # c") == "key: say it's", strip_comment("key: say it's # c"))
check("strip_comment reads a quote mid plain text as text, so the comment after it goes",
      strip_comment('key: say "hi # c') == 'key: say "hi', strip_comment('key: say "hi # c'))
check("strip_comment turns a comment-only line into nothing", strip_comment("   # whole line") == "")

sys.exit(1 if failed else 0)

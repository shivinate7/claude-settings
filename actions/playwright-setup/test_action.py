"""Static and fake-run checks of actions/playwright-setup. `python3 actions/playwright-setup/test_action.py`.
Asserts the opt-in `system-deps` input (default empty), that its step runs the Playwright install-deps
command for exactly the listed browsers, on Linux only, under a time cap, and that chromium or an unknown
name fails the job with one line. Every other step runs no apt.
It proves the step's shape and its shell script, not a real WebKit launch. Stdlib only."""
import os, re, stat, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
text = open(os.path.join(HERE, "action.yml"), encoding="utf-8").read()
STEP_NAME = "Install the system libraries"
APT = re.compile(r"install-deps|--with-deps|\bapt(-get)?\b")
BASH = "/bin/bash" if os.path.exists("/bin/bash") else "bash"

failed = 0


def check(name, ok, out=""):
    global failed
    print(("ok - " if ok else "FAIL - ") + name)
    if not ok:
        failed += 1
        if out:
            print(out)


def steps():
    """{name: block text} for each step under `runs.steps`."""
    body = text.split("\n  steps:\n", 1)[1] if "\n  steps:\n" in text else ""
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


def fake_run(script, deps, runner_os="Linux", cap="30", node_sleep=0):
    """Run `script` with a fake `node` on PATH that records its arguments. Returns (rc, output, calls)."""
    with tempfile.TemporaryDirectory() as d:
        bindir, log = os.path.join(d, "bin"), os.path.join(d, "calls")
        os.mkdir(bindir)
        node = os.path.join(bindir, "node")
        with open(node, "w") as f:
            f.write('#!/bin/sh\nshift\necho "$*" >> "%s"\nsleep %d\n' % (log, node_sleep))
        os.chmod(node, os.stat(node).st_mode | stat.S_IEXEC)
        path = os.path.join(d, "step.sh")
        with open(path, "w", newline="\n") as f:
            f.write(script)
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ.get("PATH", ""), CLI="/x/cli.js",
                   DEPS=deps, RUNNER_OS=runner_os, CAP=cap)
        p = subprocess.run([BASH, path], env=env, capture_output=True, text=True, timeout=60)
        calls = open(log).read().splitlines() if os.path.exists(log) else []
        return p.returncode, (p.stdout + p.stderr).strip(), calls


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
check("the install-deps call runs under `timeout \"$CAP\"`",
      re.search(r'timeout "\$CAP" node "\$CLI" install-deps \$DEPS', script) is not None, script)

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
    rc, out, calls = fake_run(script, "webkit", cap="1", node_sleep=5)
    check("a run past the cap fails with one line that names the cap",
          rc != 0 and len(out.splitlines()) == 1 and "::error" in out and "1 s" in out, "%s %r" % (rc, out))

others = {n: b for n, b in all_steps.items() if n != STEP_NAME}
bad = [n for n, b in others.items() if APT.search("\n".join(l for l in b.splitlines() if not l.strip().startswith("#")))]
check("the default path runs no apt: no other step names install-deps, --with-deps or apt", others and not bad, str(bad))

sys.exit(1 if failed else 0)

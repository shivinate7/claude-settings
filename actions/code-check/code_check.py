#!/usr/bin/env python3
"""code-check: one type check and one bug lint per language, read from standard.json (the one home of the table).
    python3 code_check.py [--root DIR] [--base REF]
Fails when a tracked file has a language with no row, when a row is malformed, when a tool finds a bug, or when the
repo's mypy list (.code-check.json, "mypy_modules") lost a module since --base. Tools are pinned in standard.json and
run through pipx or npx. CODE_CHECK_TOOLS=path runs the tools already on PATH instead (tests, a dev machine).
Formatter layers are skipped until o2 (one layout) lands; their rows say so."""
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = ".code-check.json"
ZERO = "0" * 40


def sh(cmd, cwd, text=True):
    # nowindow: runs on a Linux CI runner only; the action may be used without hooks/_nowindow.py
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=text)


def load_standard():
    with open(os.path.join(HERE, "standard.json"), encoding="utf-8") as f:
        return json.load(f)


def table_problems(std, runners):
    """Every language row has every layer: a known runner or a one-line skip reason."""
    out = []
    for name, row in std["languages"].items():
        if not (row.get("extensions") or row.get("shebangs")):
            out.append("row %s names no extension and no shebang" % name)
        for layer in std["layers"]:
            cell = row.get(layer)
            if not isinstance(cell, dict) or len(cell) != 1:
                out.append("row %s: layer %s needs one of run or skip" % (name, layer))
            elif "run" in cell and cell["run"] not in runners:
                out.append("row %s: layer %s names unknown runner %s" % (name, layer, cell["run"]))
            elif "skip" in cell and (not str(cell["skip"]).strip() or "\n" in cell["skip"]):
                out.append("row %s: layer %s skip needs a one-line reason" % (name, layer))
    return out


def tracked(root, exclude):
    raw = sh(["git", "ls-files", "-z"], root, text=False).stdout.decode("utf-8", "replace")
    names = [n for n in raw.split("\0") if n and os.path.isfile(os.path.join(root, n))]
    return [n for n in names if not any(n.startswith(p) for p in exclude)]


def interpreter(root, name):
    """The interpreter a script's shebang names, version digits dropped, or None with no shebang."""
    with open(os.path.join(root, name), "rb") as f:
        first = f.readline(200).decode("utf-8", "replace").strip()
    if not first.startswith("#!"):
        return None
    words = [w for w in first[2:].split() if not w.startswith("-") and os.path.basename(w) != "env"]
    return re.sub(r"[\d.]+$", "", os.path.basename(words[0])) if words else ""


def classify(root, files, std):
    """Returns ({language: [files]}, [files with no row])."""
    by_ext, by_shebang = {}, {}
    for lang, row in std["languages"].items():
        by_ext.update({e: lang for e in row["extensions"]})
        by_shebang.update({s: lang for s in row["shebangs"]})
    skip = set(std["not_code"]["extensions"])
    found, missing = {}, []
    for n in files:
        base = os.path.basename(n)
        ext = os.path.splitext(base)[1].lower() or (base.lower() if base.startswith(".") else "")
        if ext in by_ext:
            found.setdefault(by_ext[ext], []).append(n)
        elif ext in skip:
            continue
        elif ext:
            missing.append(n)
        else:
            shebang = interpreter(root, n)
            if shebang is None:
                continue
            if shebang in by_shebang:
                found.setdefault(by_shebang[shebang], []).append(n)
            else:
                missing.append(n)
    return found, missing


def shrink_problems(root, base, modules):
    """Modules the base ref listed that the list no longer holds. A list that only grows."""
    if not base or base == ZERO:
        print("code-check: mypy list shrink check unknown: no base ref given")
        return []
    if sh(["git", "rev-parse", "--verify", "--quiet", base + "^{commit}"], root).returncode:
        return ["base %s is not in this clone; check out with fetch-depth 0" % base]
    old = sh(["git", "show", "%s:%s" % (base, CONFIG)], root)
    if old.returncode:
        return []  # the base had no list: first adoption
    gone = [m for m in json.loads(old.stdout).get("mypy_modules", []) if m not in modules]
    return ["mypy list shrank: %s left %s since the base ref; the list only grows" % (m, CONFIG) for m in gone]


def tool(std, name):
    version = std["tools"][name]
    if os.environ.get("CODE_CHECK_TOOLS") == "path":
        return {"shellcheck-py": ["shellcheck"], "typescript": ["tsc"]}.get(name, [name])
    if name == "typescript":
        return ["npx", "--yes", "-p", "typescript@" + version, "tsc"]
    if name == "shellcheck-py":
        return ["pipx", "run", "--spec", "shellcheck-py==" + version, "shellcheck"]
    return ["pipx", "run", "%s==%s" % (name, version)]


def run_ruff(ctx):
    files = ctx["found"].get("python", [])
    return ("ruff", tool(ctx["std"], "ruff") + ["check", "--force-exclude"] + files) if files else None


def run_mypy(ctx):
    mods = ctx["modules"]
    if not mods:
        return None
    return ("mypy", tool(ctx["std"], "mypy") + ["--strict", "--follow-imports=silent", "--cache-dir=" + os.devnull] + mods)


def run_shellcheck(ctx):
    files = ctx["found"].get("shell", [])
    return ("shellcheck", tool(ctx["std"], "shellcheck-py") + ["--severity=warning"] + files) if files else None


def run_tsc(ctx):
    cmds = []
    for n in ctx["files"]:
        if os.path.basename(n) == "tsconfig.json":
            cmds.append(tool(ctx["std"], "typescript") + ["--noEmit", "-p", n])
    return ("tsc", cmds) if cmds else None


RUNNERS = {"ruff": run_ruff, "mypy": run_mypy, "shellcheck": run_shellcheck, "tsc": run_tsc}


def execute(name, cmd, root):
    cmds = cmd if cmd and isinstance(cmd[0], list) else [cmd]
    for c in cmds:
        try:
            p = sh(c, root)
        except FileNotFoundError as e:
            return ["%s could not start: %s" % (name, e)]
        if p.returncode:
            lines = (p.stdout + p.stderr).strip().splitlines()
            return ["%s found problems (exit %d):" % (name, p.returncode)] + lines[:40]
    return []


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--base", default="")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    std = load_standard()
    failures = table_problems(std, RUNNERS)
    cfg_path = os.path.join(root, CONFIG)
    cfg = json.load(open(cfg_path, encoding="utf-8")) if os.path.exists(cfg_path) else {}
    modules = cfg.get("mypy_modules", [])
    files = tracked(root, cfg.get("exclude", []))
    found, missing = classify(root, files, std)
    for n in missing:
        failures.append("%s: language has no row in actions/code-check/standard.json; add a row or list the path in %s exclude" % (n, CONFIG))
    failures += shrink_problems(root, args.base, modules)
    for m in modules:
        if m not in files:
            failures.append("mypy list names %s, which is not a tracked file" % m)
    if "python" not in found and modules:
        failures.append("mypy list is set but the repo tracks no Python")
    ctx = {"std": std, "files": files, "found": found, "modules": [m for m in modules if m in files]}
    for lang in sorted(found):
        row = std["languages"][lang]
        for layer in std["layers"]:
            cell = row[layer]
            if "skip" in cell:
                print("code-check: %s %s: skipped, %s" % (lang, layer, cell["skip"]))
                continue
            plan = RUNNERS[cell["run"]](ctx)
            if plan is None:
                print("code-check: %s %s: nothing to run for %s" % (lang, layer, cell["run"]))
                continue
            problems = execute(plan[0], plan[1], root)
            print("code-check: %s %s: %s %s" % (lang, layer, plan[0], "FAIL" if problems else "pass"))
            failures += problems
    for f in failures:
        print(f)
        if f and not f.startswith((" ", "\t")):
            print("::error title=code-check::%s" % f.replace("\n", " ").replace("%", "%25"))
    print("code-check: %s" % ("FAIL, %d problems" % len(failures) if failures else "PASS"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

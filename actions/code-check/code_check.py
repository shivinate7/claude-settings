#!/usr/bin/env python3
"""code-check: one type check and one bug lint per language, read from standard.json (the one home of the table).
    python3 code_check.py [--root DIR] [--base REF]
Fails when a tracked file has a language with no row, when a row is malformed, when a tool finds a bug, or when the
repo's mypy list (.code-check.json, "mypy_modules") lost a module since --base (the exclude list likewise only shrinks). Tools are pinned in standard.json and
run through pipx or npx. Astro projects are checked by astro-check, the @astrojs/check CLI that `astro check`
calls. CODE_CHECK_TOOLS=path runs the tools already on PATH instead (tests, a dev machine).
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


def base_config(root, base):
    """The base ref's .code-check.json as a dict, or None (printed as unknown) when it cannot be read."""
    if not base or base == ZERO:
        print("code-check: list shrink check unknown: no base ref given")
        return None
    if sh(["git", "rev-parse", "--verify", "--quiet", base + "^{commit}"], root).returncode:
        print("code-check: list shrink check unknown: base %s is not in this clone (use fetch-depth 0)" % base)
        return None
    old = sh(["git", "show", "%s:%s" % (base, CONFIG)], root)
    return json.loads(old.stdout) if old.returncode == 0 else None  # none: first adoption


def list_problems(old, cfg, files):
    """Both lists only shrink. A module may leave mypy_modules once its file is gone; exclude may only lose entries."""
    if old is None:
        return []
    out = ["mypy list shrank: %s left %s while the file still exists; the list only grows" % (m, CONFIG)
           for m in old.get("mypy_modules", []) if m not in cfg.get("mypy_modules", []) and m in files]
    out += ["exclude grew: %s is new in %s; the list only shrinks" % (e, CONFIG)
            for e in cfg.get("exclude", []) if e not in old.get("exclude", [])]
    return out


def tool(std, name):
    version = std["tools"][name]
    if os.environ.get("CODE_CHECK_TOOLS") == "path":
        return {"shellcheck-py": ["shellcheck"], "typescript": ["tsc"], "@astrojs/check": ["astro-check"]}.get(name, [name])
    if name == "typescript":
        return ["npx", "--yes", "-p", "typescript@" + version, "tsc"]
    if name == "@astrojs/check":
        return ["npx", "--yes", "-p", "@astrojs/check@" + version, "-p", "typescript@" + std["tools"]["typescript"], "astro-check"]
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


ASTRO_CONFIG = re.compile(r"astro\.config\.(mjs|js|ts|mts|cjs|cts)$")


def run_astro_check(ctx):
    # astro-check, not `astro check`: the latter loads @astrojs/check from the project's node_modules, which CI
    # does not install, and exits 0 at its install prompt. Roots: each tracked astro.config.* folder, plus the
    # common folder of .astro files under no config (a re-check of a project inside it is harmless).
    roots = sorted({os.path.dirname(n) or "." for n in ctx["files"] if ASTRO_CONFIG.match(os.path.basename(n))})
    orphans = [n for n in ctx["found"].get("astro", []) if not any(r == "." or n.startswith(r + "/") for r in roots)]
    if orphans:
        roots.append(os.path.commonpath([os.path.dirname(n) or "." for n in orphans]) or ".")
    cmds = [tool(ctx["std"], "@astrojs/check") + ["--root", r] for r in roots]
    return ("astro-check", cmds) if cmds else None


RUNNERS = {"ruff": run_ruff, "mypy": run_mypy, "shellcheck": run_shellcheck, "tsc": run_tsc, "astro-check": run_astro_check}


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
    ap.add_argument("--pins", action="store_true", help="print the pip specs of the tools the tests install, then exit")
    args = ap.parse_args(argv)
    if args.pins:
        tools = load_standard()["tools"]
        print(" ".join("%s==%s" % (k, tools[k]) for k in ("ruff", "mypy", "shellcheck-py")))
        return 0
    root = os.path.abspath(args.root)
    std = load_standard()
    failures = table_problems(std, RUNNERS)
    cfg_path = os.path.join(root, CONFIG)
    cfg = json.load(open(cfg_path, encoding="utf-8")) if os.path.exists(cfg_path) else {}
    modules = cfg.get("mypy_modules", [])
    for e in cfg.get("exclude", []):
        if not e.strip().strip("/"):
            failures.append("empty exclude entry %r in %s matches every file" % (e, CONFIG))
    files = tracked(root, [e for e in cfg.get("exclude", []) if e.strip().strip("/")])
    found, missing = classify(root, files, std)
    for n in missing:
        failures.append("%s: language has no row in actions/code-check/standard.json; add a row or list the path in %s exclude" % (n, CONFIG))
    failures += list_problems(base_config(root, args.base), cfg, files)
    for m in modules:
        if m not in files:
            failures.append("mypy list names %s, which is not a tracked file; remove it from mypy_modules, or list its new path" % m)
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

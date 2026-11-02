#!/usr/bin/env python3
"""code-check: one type check and one bug lint per language, read from standard.json (the one home of the table).
    python3 code_check.py [--root DIR] [--base REF] [--main REF]
Fails when a tracked file has a language with no row, when a row is malformed, when a tool finds a bug, or when the
repo's mypy list (.code-check.json, "mypy_modules") lost a module since --base or since --main, the current default
branch (the exclude list likewise only shrinks). A module renamed since that ref must be listed at its new path.
Against main, only entries the branch's merge-base with main also holds count, so a branch merely behind main passes.
Known limit: a move whose edits fall below git's 50% rename similarity reads as a plain delete and may leave the list.
Rare false alarm: a deleted module paired by git with an unrelated, similar new file reads as a rename.
Tools are pinned in standard.json and run through pipx or npx. Astro projects are checked by astro-check, the
@astrojs/check CLI that `astro check` calls. CODE_CHECK_TOOLS=path runs the tools already on PATH instead (tests,
a dev machine). Formatter layers are skipped until o2 (one layout) lands; their rows say so.
It also runs lint/check_comment_narration.py (rule building-comments-say-why) on the Python, JS/TS, Astro and Swift lines the change adds
since --base, minus the exclude folders. It reads the lint/ and hooks/ folders of the repo the action is pinned to,
which GitHub fetches whole at the pinned sha."""
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = ".code-check.json"
ZERO = "0" * 40


def sh(cmd, cwd, text=True):
    # nowindow: runs on a Linux CI runner only; the action may be used without hooks/_nowindow.py
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=text)


COMMENT_CHECK = os.path.join(HERE, "..", "..", "lint", "check_comment_narration.py")


def comment_check(root, base, exclude):
    """Failures from the comment check on lines added since base. No base is a skip, an unread diff is unknown;
    neither fails. The check is the one in lint/, run as a child, so it has one home."""
    if not base or base == ZERO:
        print("comment check: skipped, no base to diff against")
        return []
    if not os.path.isfile(COMMENT_CHECK):
        print("comment check: unknown, %s is not in this copy of the action" % os.path.normpath(COMMENT_CHECK))
        return []
    cmd = [sys.executable, COMMENT_CHECK, "--base", base] + ["--exclude=" + e for e in exclude if e.strip().strip("/")]
    p = sh(cmd, root)
    if p.returncode == 0:
        print("comment check: pass")
        return []
    rows = [r for r in p.stdout.splitlines() if r.strip()]
    err = (p.stderr.strip().splitlines() or ["exit %d" % p.returncode])[-1]
    hits = ["comment check: %s" % r for r in rows]
    if p.returncode == 2:  # an unread file ends the run, but hits found before it still fail
        print("comment check: unknown, %s" % err)
        return hits
    if p.returncode == 1 and rows:
        return hits
    # Exit 3 is the node tool failing to run; exit 1 with no hit row is a crash. Neither is a verdict, so neither is
    # a clean diff.
    return hits + ["comment check could not run: %s" % err.replace("COULD NOT RUN: ", "", 1)]


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


def commit(root, ref):
    """The commit a ref names, or None when it is empty or not in this clone."""
    if not ref or ref == ZERO:
        return None
    p = sh(["git", "rev-parse", "--verify", "--quiet", ref + "^{commit}"], root)
    return p.stdout.strip() if p.returncode == 0 else None


def base_config(root, base, label="base"):
    """The ref's .code-check.json as a dict, or None (printed as unknown) when it cannot be read."""
    if not base or base == ZERO:
        print("code-check: list shrink check unknown: no %s ref given" % label)
        return None
    if commit(root, base) is None:
        print("code-check: list shrink check unknown: %s %s is not in this clone (use fetch-depth 0)" % (label, base))
        return None
    old = sh(["git", "show", "%s:%s" % (base, CONFIG)], root)
    return json.loads(old.stdout) if old.returncode == 0 else None  # none: first adoption


def main_config(root, main):
    """main's config cut to what the branch's fork point also holds, and the fork point, or (None, None) as
    unknown. A loss counts against main only when the merge-base lists it too; else the branch is just behind
    main and a merge keeps main's entry. An exclude entry main dropped after the fork counts as still there."""
    cfg = base_config(root, main, "main")
    if cfg is None:
        return None, None
    p = sh(["git", "merge-base", main, "HEAD"], root)
    if p.returncode:
        print("code-check: list shrink check unknown: main %s shares no merge-base with HEAD" % main)
        return None, None
    fork = p.stdout.strip()
    at_fork = base_config(root, fork, "merge-base") or {}
    held = at_fork.get("mypy_modules", [])
    return {"mypy_modules": [m for m in cfg.get("mypy_modules", []) if m in held],
            "exclude": cfg.get("exclude", []) + at_fork.get("exclude", [])}, fork


def renames(root, ref):
    """{old path: new path} for files git sees renamed between ref and the working tree, so it holds pre-commit."""
    p = sh(["git", "diff", "-M", "--name-status", "-z", "--diff-filter=R", ref], root)
    words = p.stdout.split("\0") if p.returncode == 0 else []
    return {words[i + 1]: words[i + 2] for i in range(0, len(words) - 2, 3) if words[i].startswith("R")}


def list_problems(old, cfg, files, moved=None):
    """Both lists only shrink. A module may leave mypy_modules once its file is gone, unless git saw it renamed
    (moved: {old: new}); then the new path must be listed. exclude may only lose entries."""
    if old is None:
        return []
    moved = moved or {}
    now = cfg.get("mypy_modules", [])
    lost = [m for m in old.get("mypy_modules", []) if m not in now]
    out = ["mypy list shrank: %s left %s while the file still exists; the list only grows" % (m, CONFIG)
           for m in lost if m in files]
    for m in lost:
        new = moved.get(m)
        if m in files or not new or new in now:
            continue
        if new in files and new.endswith((".py", ".pyi")):
            out.append("mypy list lost %s, renamed to %s; list %s in %s" % (m, new, new, CONFIG))
        else:
            # Listing the new path cannot work: tracked() drops excluded paths, and mypy checks only Python.
            out.append("mypy list lost %s, renamed to %s, which mypy cannot check (excluded or not Python); "
                       "move it back, or out of the excluded folder" % (m, new))
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
    ap.add_argument("--main", default="", help="the current default branch; the shrink check runs against it too")
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
    refs = [(args.base, "base")]
    main_commit = commit(root, args.main)
    if main_commit is None or main_commit != commit(root, args.base):
        refs.append((args.main, "main"))
    for ref, label in refs:
        if label == "main":
            old, ref = main_config(root, ref)
        else:
            old = base_config(root, ref, label)
        moved = renames(root, ref) if old is not None else {}
        # Both refs often report the same loss; print it once.
        failures += [f for f in list_problems(old, cfg, files, moved) if f not in failures]
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
    failures += comment_check(root, args.base, cfg.get("exclude", []))
    for f in failures:
        print(f)
        if f and not f.startswith((" ", "\t")):
            print("::error title=code-check::%s" % f.replace("\n", " ").replace("%", "%25"))
    print("code-check: %s" % ("FAIL, %d problems" % len(failures) if failures else "PASS"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

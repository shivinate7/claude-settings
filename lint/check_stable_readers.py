#!/usr/bin/env python3
"""Do the stable branch's readers accept this tree? The merge tool runs from branch `stable`, which lags main, so a pull request that gives main's
data a form the older reader does not know must be red before it merges, not when the tool meets it after.

Usage: python3 lint/check_stable_readers.py --stable-tree DIR --head-tree DIR [--base-ref REF]
  --stable-tree  a tree of the stable branch (merge/, lint/, hooks/, actions/ at least), never the live clone.
  --head-tree    the pull request's tree, a git checkout. Its data is read: .github/stamp.json, .github/workflows, the records page.
  --base-ref     optional git ref in the head tree. The records page is judged only when the head changed it against that ref, because a
                 page left stale by a new record is normal on a pull request: the merge tool regenerates it at merge. A pull request that
                 changes no data file against that ref (the stamp, the workflows, the records page) has each stable-versus-head difference
                 waived, with one printed line naming its key: the data is the same as on the base, so the difference is the reader's, and
                 the pull request that lands the reader is the one the rule says to land first. A refusal is never waived.
Exit 0 every stable reader accepts the tree; 1 a reader refuses or reads it differently from the head's own reader (each finding names the
reader and its key); 2 a bad call.

Each tree's code runs in its own child process, because the two copies share module names. A child gets `python3 -I`, so this script's
folder, which belongs to the head, never shadows the stable copy's modules. The readers, by name: merge.py parse_config, ready_job_groups,
base_job_caps, base_stamp (the stamp `kinds`), page_is_generated; hooks/guard_merge.py pinned_required; hooks/agent_brief.py cite_form; and
the stable copy's lint/hook_catalog.py --records-only --check. A reader that accepts a form but reads it differently (the silent form) shows
only as a difference from the head reader's result on the same data, so the head's children run too.
"""
import argparse, contextlib, copy, importlib.util, io, json, os, subprocess, sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

CODE_DIRS = ("hooks", "lint", "merge", "actions")
CONFIG = os.path.join(".github", "stamp.json")  # glossary-ok: the file the readers read, by its real name
KEYS = {  # the data each reader reads, named in a finding
    "parse_config": CONFIG + " merge block", "ready_job_groups": "merge.readyChecks", "base_job_caps": ".github/workflows",
    "base_stamp": "kinds", "page_is_generated": "the records page", "pinned_required": "merge.requiredChecks", "cite_form": "cite.form",  # glossary-ok: the reader's name in merge/merge.py
}
CHANGED = "data_changed"  # the probe's own key: the data files the pull request changes against the base, not a reader
PROBE_SECONDS, CATALOG_SECONDS = 300, 120  # unmeasured: the longest read is one worktree add and one generator run


def jsonable(value):
    return json.loads(json.dumps(value, default=repr))


def probe(code_tree, data, base_ref):
    """Run this code tree's readers on the data tree. -> {reader: {"value": ...} or {"error": text}}; a reader that does not apply is left out."""
    for sub in CODE_DIRS:
        sys.path.insert(0, os.path.join(code_tree, sub))
    spec = importlib.util.spec_from_file_location("probe_merge", os.path.join(code_tree, "merge", "merge.py"))
    merge = importlib.util.module_from_spec(spec)
    results = {}

    def read(name, fn):
        sink = io.StringIO()
        try:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                results[name] = {"value": jsonable(fn())}
        except (Exception, SystemExit) as e:  # a tool that stops with SystemExit is a refusal here, never a crash of the probe
            results[name] = {"error": f"{type(e).__name__}: {e}"}

    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            spec.loader.exec_module(merge)
    except (Exception, SystemExit) as e:
        return {"merge.py": {"error": f"cannot load merge/merge.py (unknown): {type(e).__name__}: {e}"}}
    try:
        with open(os.path.join(data, CONFIG), encoding="utf-8") as f:
            cfg = json.load(f)
    except OSError:
        cfg = None
    except ValueError as e:
        cfg = None
        results["parse_config"] = {"error": f"{CONFIG} is not JSON: {e}"}
    if isinstance(cfg, dict):
        read("parse_config", lambda: merge.parse_config(data, copy.deepcopy(cfg), "HEAD", "head", CONFIG, "", fill=False))
        ready = cfg.get("merge", {}).get("readyChecks") if isinstance(cfg.get("merge"), dict) else None
        if isinstance(ready, list) and all(isinstance(r, str) for r in ready):
            read("ready_job_groups", lambda: list(merge.ready_job_groups(ready).items()))
    read("base_job_caps", lambda: merge.base_job_caps(data, "HEAD"))
    read("base_stamp", lambda: merge.base_stamp(data, CONFIG, "HEAD")[1])  # glossary-ok: the reader's name in merge/merge.py
    page = merge.RECORDS_PAGE
    if merge.git(data, "cat-file", "-e", f"HEAD:{page}")[0] == 0:  # a tree with no page has none to prove: the generator would stop on it
        untouched = base_ref and merge.git(data, "diff", "--quiet", base_ref, "HEAD", "--", page)[0] == 0
        if not untouched:
            read("page_is_generated", lambda: merge.page_is_generated(data, merge.git(data, "rev-parse", "HEAD")[1]))
    import guard_merge  # noqa: E402  hooks/guard_merge.py of this code tree
    guard_merge._MERGE_MODULE.append(merge)  # its merge_module() would load the live clone's tool: this tree's own is the one under test
    read("pinned_required", lambda: guard_merge.pinned_required(data))
    import agent_brief  # noqa: E402
    read("cite_form", lambda: agent_brief.cite_form(data))
    if base_ref:  # an unreadable diff leaves the key out: no waiver is given on an unknown
        code, out = merge.git(data, "diff", "--name-only", base_ref, "HEAD", "--", CONFIG, ".github/workflows", page)
        if code == 0:
            results[CHANGED] = {"value": out.split()}
    return results


def run_probe(code_tree, data, base_ref):
    """The probe of `code_tree` in a child. -> (results, None), or (None, why) when the child gave no JSON."""
    cmd = [sys.executable, "-I", os.path.abspath(__file__), "--probe", code_tree, "--head-tree", data]
    if base_ref:
        cmd += ["--base-ref", base_ref]
    try:
        r = _nowindow.run(cmd, capture_output=True, text=True, cwd=data, timeout=PROBE_SECONDS)
        return json.loads(r.stdout), None
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        detail = getattr(e, "stderr", None) or ""
        return None, f"{type(e).__name__}: {e} {str(detail)[-300:]}".strip()


def differing_keys(stable, head):
    """The merge or top-level keys of two parsed stamps that read differently, as a text; the reader's own name when it is not a stamp."""
    if not (isinstance(stable, dict) and isinstance(head, dict)):
        return ""
    keys = [f"merge.{k}" for k in sorted(set(stable.get("merge", {})) | set(head.get("merge", {}))) if stable.get("merge", {}).get(k) != head.get("merge", {}).get(k)]
    keys += [k for k in sorted(set(stable) | set(head)) if k != "merge" and stable.get(k) != head.get(k)]
    return ", ".join(keys)


def compare(stable, head):
    """-> (findings, differences): one line per reader that refuses the head's data, or reads it differently from the head's own reader.
    `differences` are the findings that are a plain difference between two values, the only kind a reader-only pull request may waive."""
    findings, differences = [], []
    for name, got in stable.items():
        key = KEYS.get(name, name)
        if "error" in got:
            findings.append(f"{name} ({key}): the stable reader refuses this tree: {got['error']}")
        elif name == "page_is_generated" and got["value"] is not True:
            findings.append(f"{name} ({key}): the stable generator does not write the committed page: it was edited by hand or the generator reads the records differently")
        elif name in head and head[name] != got:
            keys = differing_keys(got.get("value"), head[name].get("value")) if name == "parse_config" else ""
            line = (f"{name} ({keys or key}): the stable reader reads this tree differently from the head's reader: "
                    f"stable {json.dumps(got.get('value'))[:160]}, head {json.dumps(head[name].get('value', head[name]))[:160]}")
            (differences if "value" in head[name] else findings).append(line)
    return findings, differences


def catalog_finding(stable_tree, head_tree):
    """The stable copy's records generator in check mode on the head tree. -> a finding, or None."""
    cmd = [sys.executable, "-I", os.path.join(stable_tree, "lint", "hook_catalog.py"), "--records-only", "--check", "--root", head_tree]
    try:
        r = _nowindow.run(cmd, capture_output=True, text=True, cwd=head_tree, timeout=CATALOG_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"hook_catalog (the records page): the stable generator could not run (unknown): {type(e).__name__}: {e}"
    if r.returncode:
        return f"hook_catalog (the records page): the stable generator refuses this tree, exit {r.returncode}: {' '.join((r.stdout + r.stderr).split())[:300]}"
    return None


def main(argv):
    parser = argparse.ArgumentParser(description="Run the stable branch's readers on a pull request's tree.")
    parser.add_argument("--stable-tree", help="a tree of the stable branch")
    parser.add_argument("--head-tree", required=True, help="the pull request's tree, a git checkout")
    parser.add_argument("--base-ref", help="judge the records page only when the head changed it against this ref")
    parser.add_argument("--probe", help="internal: run this code tree's readers on --head-tree and print them as JSON")
    args = parser.parse_args(argv)
    if args.probe:
        sys.stdout.write(json.dumps(probe(os.path.abspath(args.probe), os.path.abspath(args.head_tree), args.base_ref)))
        return 0
    for label, tree in (("--stable-tree", args.stable_tree), ("--head-tree", args.head_tree)):
        if not tree or not os.path.isdir(tree):
            print(f"check_stable_readers: {label} {tree!r} is not a folder", file=sys.stderr)
            return 2
    if not os.path.isfile(os.path.join(args.stable_tree, "merge", "merge.py")):
        print(f"check_stable_readers: --stable-tree {args.stable_tree!r} has no merge/merge.py", file=sys.stderr)
        return 2
    stable_tree, head_tree = os.path.abspath(args.stable_tree), os.path.abspath(args.head_tree)
    stable, why = run_probe(stable_tree, head_tree, args.base_ref)
    head, head_why = run_probe(head_tree, head_tree, args.base_ref)
    findings, waived = [], []
    if stable is None:
        findings.append(f"probe (the stable readers): could not run (unknown): {why}")
    elif head is None:
        findings.append(f"probe (the head's readers): could not run (unknown): {head_why}")
    elif "merge.py" in stable or "merge.py" in head:  # a merge tool that does not load gives no reader to compare: unknown, never a pass
        findings += [f"merge.py ({side}'s tool): {got['merge.py']['error']}" for side, got in (("stable", stable), ("head", head)) if "merge.py" in got]
    else:
        changed = head.pop(CHANGED, None)
        stable.pop(CHANGED, None)
        found, differences = compare(stable, head)
        findings += found
        if changed is not None and not changed["value"]:
            waived = differences
        else:
            findings += differences
    found = catalog_finding(stable_tree, head_tree)
    if found:
        findings.append(found)
    for line in waived:
        key = line.split(" (", 1)[1].split("):", 1)[0]
        print(f"stable readers: waived {key}: this pull request changes no data file against {args.base_ref}, so the difference is the reader's")
    for line in findings:
        print(f"stable readers: {line}")
    if findings:
        print("The merge tool runs from branch stable. Land the reader first, move stable, then land the data that needs it.")
        return 1
    print("stable readers accept this tree")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

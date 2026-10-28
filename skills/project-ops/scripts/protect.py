#!/usr/bin/env python3
"""Sets branch protection with the required checks on an adopting repo, so no repo starts with none.

    python3 protect.py --repo <owner>/<name> --check <name> [--check <name> ...] [--branch main] [--confirm]

Without --confirm it only reads the branch's protection and prints what it would set. With --confirm it
sets the required checks: a branch with no protection gets it (the checks, no review rule, no restriction);
a protected branch with a check rule gets only its check list set (its strict setting stays), and an equal list is left alone.
A branch protected without a check rule is refused, naming its rules: a PUT would replace them. merge/merge.py reads the
required checks from this protection (merge.requiredChecks "protection"), so this is their one home.
Exit 0 done or previewed, 1 a gh call failed, 2 a bad argument.
"""
import argparse
import json
import re
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a child start with no console window (hooks/_nowindow.py)

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9_./-]+$")


def run_gh(args, body=None):
    """-> (code, output) of `gh api`, with `body` as its JSON input."""
    p = _nowindow.run(["gh", "api", *args] + (["--input", "-"] if body is not None else []),
                       input=json.dumps(body) if body is not None else None, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def main(argv, gh=run_gh):
    ap = argparse.ArgumentParser(description="Set branch protection with the required checks.")
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--check", action="append", default=[], help="a check name; repeat for each (a name may hold a comma)")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--confirm", action="store_true", help="set the protection; without it, only preview")
    a = ap.parse_args(argv)
    checks = [c.strip() for c in a.check if c.strip()]
    if not REPO_RE.match(a.repo) or not BRANCH_RE.match(a.branch):
        print("protect: --repo must be owner/name, and --branch a plain branch name", file=sys.stderr)
        return 2
    if not checks:
        print("protect: no --check named. A repo never starts with none.", file=sys.stderr)
        return 2
    base = f"repos/{a.repo}/branches/{a.branch}/protection"
    code, out = gh(["-X", "GET", base + "/required_status_checks"])
    if code == 0:
        try:
            held = json.loads(out)["contexts"]
        except (ValueError, KeyError, TypeError):
            print(f"protect: cannot read the required checks of {a.branch}: {out}", file=sys.stderr)
            return 1
        if set(held) == set(checks):
            print(f"protect: {a.branch} already requires {', '.join(checks)}. Nothing to set.")
            return 0
        call, body = ["-X", "PATCH", base + "/required_status_checks"], {"contexts": checks}
        what = f"set the required checks of {a.branch} to {', '.join(checks)} (now: {', '.join(held) or 'none'})"
    elif "404" in out:
        code, whole = gh(["-X", "GET", base])  # a 404 also answers "protected, but no check rule": a PUT would replace its other rules
        if code == 0:
            try:
                rules = ", ".join(sorted(k for k, v in json.loads(whole).items() if v))
            except (ValueError, AttributeError):
                rules = "unreadable rules"
            print(f"protect: {a.branch} is protected without a check rule ({rules}). A PUT would replace them, so nothing was set. Add the checks by hand.", file=sys.stderr)
            return 1
        if "404" not in whole:
            print(f"protect: cannot read the protection of {a.branch}: {whole}", file=sys.stderr)
            return 1
        call = ["-X", "PUT", base]
        body = {"required_status_checks": {"strict": False, "contexts": checks}, "enforce_admins": False,
                "required_pull_request_reviews": None, "restrictions": None}
        what = f"protect {a.branch} with the required checks {', '.join(checks)}"
    else:
        print(f"protect: cannot read the protection of {a.branch}: {out}", file=sys.stderr)
        return 1
    if not a.confirm:
        print(f"protect: would {what}. Run again with --confirm to set it.")
        return 0
    code, out = gh(call, body)
    if code:
        print(f"protect: the call failed: {out}", file=sys.stderr)
        return 1
    print(f"protect: {what}. Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Sets branch protection with the one required check on an adopting repo, so no repo starts with none.

    python3 protect.py --repo <owner>/<name> --check all-jobs-passed [--branch main] [--confirm]

The one check is the all-jobs-passed rollup (decision same-check-kinds), the constant REQUIRED_CHECK; any other --check name is refused.
Without --confirm it only reads the branch's protection and prints what it would set. With --confirm it
sets the required check: a branch with no protection gets it (the check, strict off, admins included, no review rule, no restriction);
a protected branch with a check rule gets only its required check set (its strict setting stays), and an equal check is left alone.
The PATCH keeps the app id of the required check, read from the live rule and never a constant: the app id held by the entry named
REQUIRED_CHECK (null and -1 ignored), else the one app id all held entries share. With no such id it sends the check with no app id, and
GitHub then picks the app that recently posted the check, or any app if none did. The PATCH never sends `contexts`; the PUT still does, with no
app id. The printed line names the app id, or says "no app id"; an equal check with no app id says so before "Nothing to set.".
A branch protected without a check rule is refused, naming its rules: a PUT would replace them. merge/merge.py reads the
required checks from this protection (merge.requiredChecks "protection"), so this is their one home.
Exit 0 done or previewed, 1 a gh call failed, 2 a bad argument or a check other than REQUIRED_CHECK.
"""
import argparse
import json
import re
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a child start with no console window (hooks/_nowindow.py)
from required_check import REQUIRED_CHECK  # noqa: E402  the one home of the required check's name (hooks/required_check.py)

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
    ap.add_argument("--check", action="append", default=[], help=f"the one required check, only {REQUIRED_CHECK} is allowed; a second distinct name is refused")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--confirm", action="store_true", help="set the protection; without it, only preview")
    a = ap.parse_args(argv)
    checks = list(dict.fromkeys(c.strip() for c in a.check if c.strip()))  # the same name twice is one check
    if not REPO_RE.match(a.repo) or not BRANCH_RE.match(a.branch):
        print("protect: --repo must be owner/name, and --branch a plain branch name", file=sys.stderr)
        return 2
    if not checks:
        print("protect: no --check named. A repo never starts with none.", file=sys.stderr)
        return 2
    if len(checks) > 1:  # action="append" keeps a second name so it reaches this refusal, not a silent overwrite
        print(f"protect: only one --check is allowed, got {len(checks)} ({', '.join(checks)}). Branch protection requires exactly one check, "
              f"the {REQUIRED_CHECK} rollup (decision same-check-kinds).", file=sys.stderr)
        return 2
    if checks[0] != REQUIRED_CHECK:  # the allowed name is the constant merge.py emits, never a copy
        print(f"protect: --check {checks[0]!r} is refused. Branch protection requires one check, {REQUIRED_CHECK} (decision same-check-kinds).", file=sys.stderr)
        return 2
    base = f"repos/{a.repo}/branches/{a.branch}/protection"
    code, out = gh(["-X", "GET", base + "/required_status_checks"])
    if code == 0:
        try:
            rule = json.loads(out)
            held = rule["contexts"]
            live = rule.get("checks") or []
            own = {c.get("app_id") for c in live if c.get("context") == REQUIRED_CHECK} - {None, -1}  # the required check's own id wins
            ids = own or ({c.get("app_id") for c in live} - {None, -1})
        except (ValueError, KeyError, TypeError, AttributeError):
            print(f"protect: cannot read the required checks of {a.branch}: {out}", file=sys.stderr)
            return 1
        if set(held) == set(checks):
            print(f"protect: {a.branch} already requires {', '.join(checks)}{'' if len(ids) == 1 else ' (no app id)'}. Nothing to set.")
            return 0
        pin = {"app_id": next(iter(ids))} if len(ids) == 1 else {}  # one live app id is kept; none or several send no app id
        call, body = ["-X", "PATCH", base + "/required_status_checks"], {"checks": [{"context": REQUIRED_CHECK, **pin}]}
        what = f"set the required checks of {a.branch} to {', '.join(checks)} ({'app id ' + str(pin['app_id']) if pin else 'no app id'}; now: {', '.join(held) or 'none'}{'; drops: ' + ', '.join(sorted(set(held) - set(checks))) if set(held) - set(checks) else ''})"
    elif "HTTP 404" in out:
        code, whole = gh(["-X", "GET", base])  # a 404 also answers "protected, but no check rule": a PUT would replace its other rules
        if code == 0:
            try:
                rules = ", ".join(sorted(k for k, v in json.loads(whole).items() if v))
            except (ValueError, AttributeError):
                rules = "unreadable rules"
            print(f"protect: {a.branch} is protected without a check rule ({rules}). A PUT would replace them, so nothing was set. Add the checks by hand.", file=sys.stderr)
            return 1
        if "HTTP 404" not in whole:
            print(f"protect: cannot read the protection of {a.branch}: {whole}", file=sys.stderr)
            return 1
        call = ["-X", "PUT", base]
        body = {"required_status_checks": {"strict": False, "contexts": checks}, "enforce_admins": True,
                "required_pull_request_reviews": None, "restrictions": None}
        what = f"protect {a.branch} with the required checks {', '.join(checks)} (no app id)"
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

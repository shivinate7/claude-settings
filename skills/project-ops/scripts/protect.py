#!/usr/bin/env python3
"""Sets a ruleset on an adopting repo's branch with the one required check, so no repo starts with none.

    python3 protect.py --repo <owner>/<name> --check all-jobs-passed [--branch main] [--confirm]

The one check is the all-jobs-passed rollup (decision same-check-kinds), the constant REQUIRED_CHECK; any other --check name is refused.
The ruleset follows decision main-branch-protection: active, on the named branch,
the rollup as its one required check, deletion and force-push blocked, and the repository Admin role as its one bypass actor, on pull requests only.
It sets no strict policy of its own and no pull-request rule: those are planned, not ruled.
Without --confirm it only reads the repo's rulesets and prints what it would set. With --confirm it writes: a branch with no ruleset gets one
(POST); a branch whose ruleset differs from the ruled form is updated in place (PUT, its other rules, its conditions and its strict setting kept);
a ruleset already in the form is left alone. The classic branch protection is never read or written here: its removal is a later act.
merge/merge.py reads the required checks from the ruleset first (merge.requiredChecks "protection"), so this is their one home.
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
# The Admin repository role's actor_id. 5 is unconfirmed against a live ruleset (none exists yet); read it back at the first live one.
ADMIN_ROLE_ID = 5
BYPASS = {"actor_type": "RepositoryRole", "actor_id": ADMIN_ROLE_ID, "bypass_mode": "pull_request"}
OWNED_RULES = ("required_status_checks", "deletion", "non_fast_forward")  # the rule types the ruled form names; any other rule on a ruleset is kept
PAGE = 100


def run_gh(args, body=None):
    """-> (code, output) of `gh api`, with `body` as its JSON input."""
    p = _nowindow.run(["gh", "api", *args] + (["--input", "-"] if body is not None else []),
                       input=json.dumps(body) if body is not None else None, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def list_rulesets(repo, gh):
    """-> every ruleset summary of the repo, all pages (a list read gives 30 unless asked for more), or None when a read fails.
    Rulesets of an organization are skipped: this repo cannot write them."""
    found = []
    for n in range(1, 50):
        code, out = gh(["-X", "GET", "-f", f"per_page={PAGE}", "-f", f"page={n}", f"repos/{repo}/rulesets"])
        try:
            page = json.loads(out) if code == 0 else None
        except ValueError:
            return None
        if not isinstance(page, list):
            return None
        found += [r for r in page if r.get("source_type", "Repository") == "Repository"]
        if len(page) < PAGE:
            return found
    return None


def differences(ruleset, check):
    """-> what in `ruleset` departs from the ruled form, as short phrases; [] when it already is that form. A rule or setting the form does not name is not compared."""
    rules = ruleset.get("rules", [])
    contexts = [c["context"] for r in rules if r["type"] == "required_status_checks" for c in r["parameters"]["required_status_checks"]]
    types = {r["type"] for r in rules}
    gaps = []
    if ruleset.get("enforcement") != "active":
        gaps.append("not active")
    if contexts != [check]:
        gaps.append(f"required checks are {', '.join(contexts) or 'none'}")
    gaps += [f"no {t} rule" for t in ("deletion", "non_fast_forward") if t not in types]
    if [{k: b.get(k) for k in BYPASS} for b in ruleset.get("bypass_actors", [])] != [BYPASS]:
        gaps.append("bypass is not the Admin role on pull requests only")
    return gaps


def ruled_body(check, branch, name, held=None):
    """-> the ruleset body of the ruled form. `held` is the ruleset it replaces: its name, conditions, strict setting and other rules carry over.
    The API wants a strict value on a required-check rule, and the ruling names none: a new rule gets false (the classic gold form's value)."""
    held = held or {}
    strict = next((r["parameters"].get("strict_required_status_checks_policy", False) for r in held.get("rules", []) if r["type"] == "required_status_checks"), False)
    rules = [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": check}], "strict_required_status_checks_policy": strict}},
             {"type": "deletion"}, {"type": "non_fast_forward"}]
    rules += [r for r in held.get("rules", []) if r["type"] not in OWNED_RULES]
    return {"name": held.get("name", name), "target": "branch", "enforcement": "active",
            "conditions": held.get("conditions") or {"ref_name": {"include": [f"refs/heads/{branch}"], "exclude": []}},
            "rules": rules, "bypass_actors": [dict(BYPASS)]}


def main(argv, gh=run_gh):
    ap = argparse.ArgumentParser(description="Set a ruleset with the required check.")
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--check", action="append", default=[], help=f"the one required check, only {REQUIRED_CHECK} is allowed; a second distinct name is refused")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--confirm", action="store_true", help="set the ruleset; without it, only preview")
    a = ap.parse_args(argv)
    checks = list(dict.fromkeys(c.strip() for c in a.check if c.strip()))  # the same name twice is one check
    if not REPO_RE.match(a.repo) or not BRANCH_RE.match(a.branch):
        print("protect: --repo must be owner/name, and --branch a plain branch name", file=sys.stderr)
        return 2
    if not checks:
        print("protect: no --check named. A repo never starts with none.", file=sys.stderr)
        return 2
    if len(checks) > 1:  # action="append" keeps a second name so it reaches this refusal, not a silent overwrite
        print(f"protect: only one --check is allowed, got {len(checks)} ({', '.join(checks)}). A ruleset requires exactly one check, "
              f"the {REQUIRED_CHECK} rollup (decision same-check-kinds).", file=sys.stderr)
        return 2
    if checks[0] != REQUIRED_CHECK:  # the allowed name is the constant merge.py emits, never a copy
        print(f"protect: --check {checks[0]!r} is refused. A ruleset requires one check, {REQUIRED_CHECK} (decision same-check-kinds).", file=sys.stderr)
        return 2
    base = f"repos/{a.repo}/rulesets"
    listed = list_rulesets(a.repo, gh)
    if listed is None:
        print(f"protect: cannot read the rulesets of {a.repo}", file=sys.stderr)
        return 1
    ref, held = f"refs/heads/{a.branch}", None
    for summary in listed:  # the list read gives no conditions or rules: each ruleset is read whole
        code, out = gh(["-X", "GET", f"{base}/{summary['id']}"])
        try:
            one = json.loads(out) if code == 0 else None
        except ValueError:
            one = None
        if not isinstance(one, dict):
            print(f"protect: cannot read ruleset {summary['id']} of {a.repo}: {out}", file=sys.stderr)
            return 1
        if one.get("target") == "branch" and ref in one.get("conditions", {}).get("ref_name", {}).get("include", []):
            held = one
            break
    if held is None:
        call, body = ["-X", "POST", base], ruled_body(checks[0], a.branch, f"{a.branch}-required-check")
        what = f"create a ruleset on {a.branch} that requires {checks[0]}, blocks deletion and force-push, and lets the Admin role bypass on pull requests"
    else:
        gaps = differences(held, checks[0])
        if not gaps:
            print(f"protect: the ruleset {held.get('name')} on {a.branch} is already in the ruled form. Nothing to set.")
            return 0
        call, body = ["-X", "PUT", f"{base}/{held['id']}"], ruled_body(checks[0], a.branch, held.get("name", ""), held)
        what = f"update the ruleset {held.get('name')} on {a.branch} to the ruled form (now: {'; '.join(gaps)})"
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

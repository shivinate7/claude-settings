#!/usr/bin/env python3
"""CI check: every CLAUDE.md rule anchor maps to a mechanism, or an argued `unmechanized`.

CLAUDE.md says to turn each rule into a hook or a check, and calls itself "the fallback, not
the enforcement". Nothing measured that claim. This is the measurement. It runs in CI only,
never at Stop: the map does not change turn to turn, so there is nothing to gain from paying
its cost on every reply.

WHAT COUNTS AS A RULE. Each prescriptive sentence in CLAUDE.md carries an inline anchor,
`<!-- rule:<slug> -->`, placed right after the sentence it names. The anchor is the stable
key. A rule's wording can be reworded around its anchor without breaking this check; only
deleting or renaming the anchor comment does. Purely descriptive or argumentative sentences
that assert no independent, checkable behavior carry no anchor and are not rules for this
check. That line is a judgment call the person who adds a rule makes when they add its
anchor, not something this script infers from prose.

THE MAP. lint/rule_mechanisms.json holds one row per anchor. A row's mechanism is one of:
  - `guard`: a rule name string this session's hooks/guard.py actually passes as the third
    argument to `refuse(...)` or `record(...)`.
  - `gate`: a file, named by its path from the repo root, that exists on disk. An optional
    `needle` is a substring that must still appear in that file, so a citation of a gate
    whose relevant code moved away reads as stale rather than as coverage.
  - `ci`: a step name that appears in a `- name:` line of .github/workflows/gates.yml.
  - `unmechanized`: the literal token, paired with a `reason` of real length. A rule that
    genuinely cannot be checked by a machine still needs a row saying so, and saying why.

NON-VACUITY, TWO WAYS. A reader that finds no anchors must never print `ok`: that is this
repo's own signature defect in a new coat, a check that cannot tell "nothing is wrong" from
"nothing is known yet". So a fall in the anchor count below RULE_FLOOR fails loud, and names
the drop, rather than reporting a clean map over a page the parser stopped seeing.
UNMECHANIZED_EXPECTED is an equality on purpose, not a ceiling: a ceiling lets a mutation that
deletes an honest `unmechanized` admission pass silently, because the count only falls, which
reads as debt paid rather than as debt hidden. Both directions are guarded: build a mechanism
for a rule and lower this pin in the same commit, or add a rule with no mechanism and raise it
and say why.

WHAT THIS CANNOT SEE, BY NAME. It reads a citation, not the coverage behind it: a row can name
a real guard rule that does not actually cover what the CLAUDE.md sentence demands, and this
check passes it anyway. It cannot judge whether an `unmechanized` reason is a good argument,
only whether one was written at length. And it governs only CLAUDE.md's own text: a rule
recorded in a decision file or an agent prompt is a different surface, ungoverned here.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAUDE_MD = os.path.join(ROOT, "CLAUDE.md")
MAP_FILE = os.path.join(ROOT, "lint", "rule_mechanisms.json")
GUARD_PY = os.path.join(ROOT, "hooks", "guard.py")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "gates.yml")

ANCHOR_RE = re.compile(r"<!--\s*rule:([a-z0-9][a-z0-9-]*)\s*-->")
GUARD_RULE_RE = re.compile(r'(?:refuse|record)\(\s*\w+\s*,\s*"[a-z-]+"\s*,\s*"([a-z-]+)"')
CI_STEP_RE = re.compile(r'^\s*-\s*name:\s*(.+?)\s*$', re.MULTILINE)

# THREE PINNED NUMBERS, HELD DELIBERATELY RATHER THAN COUNTED FRESH EVERY RUN. See the
# module docstring, "NON-VACUITY, TWO WAYS", for the argument. Update RULE_FLOOR when a rule
# is deliberately removed. Update UNMECHANIZED_EXPECTED in the SAME commit that builds a
# mechanism (lower it) or adds an unmechanized rule (raise it, and say why in the message).
RULE_FLOOR = 76
UNMECHANIZED_EXPECTED = 54
REASON_MIN_WORDS = 8

KINDS = {"guard", "gate", "ci", "unmechanized"}


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def claude_md_anchors(text: str) -> List[str]:
    return [m.group(1) for m in ANCHOR_RE.finditer(text)]


def guard_rule_names(text: str):
    return set(GUARD_RULE_RE.findall(text))


def ci_step_names(text: str):
    return {m.group(1).strip().strip('"').strip("'") for m in CI_STEP_RE.finditer(text)}


def check(
    claude_text: str,
    rule_map: dict,
    guard_text: str,
    workflow_text: str,
    rule_floor: int = RULE_FLOOR,
    unmechanized_expected: int = UNMECHANIZED_EXPECTED,
) -> List[str]:
    """Return every problem found. An empty list means the audit passes.

    `rule_floor` and `unmechanized_expected` default to this repo's own pinned numbers.
    Fixture tests pass their own, sized to the small CLAUDE.md fragment they build, so a
    fixture's rule count is never mistaken for a shrunk real document.
    """
    problems: List[str] = []

    anchors = claude_md_anchors(claude_text)
    if len(anchors) < rule_floor:
        problems.append(
            f"found {len(anchors)} rule anchors in CLAUDE.md, fewer than the pinned floor "
            f"{rule_floor}. An anchor was likely deleted, or this reader broke on a reword. "
            f"Lower RULE_FLOOR in lint/rule_audit.py deliberately if a rule genuinely went. "
            f"Never let a shrinking reader report clean."
        )

    dupes = sorted({a for a in anchors if anchors.count(a) > 1})
    if dupes:
        problems.append("duplicate rule anchors in CLAUDE.md: " + ", ".join(dupes))

    anchor_set = set(anchors)
    rules = rule_map.get("rules") if isinstance(rule_map, dict) else None
    if not isinstance(rules, dict):
        problems.append("lint/rule_mechanisms.json has no top-level \"rules\" object.")
        return problems

    missing = sorted(anchor_set - rules.keys())
    for slug in missing:
        problems.append(f"CLAUDE.md rule `{slug}` has no row in lint/rule_mechanisms.json.")

    orphaned = sorted(rules.keys() - anchor_set)
    for slug in orphaned:
        problems.append(
            f"lint/rule_mechanisms.json row `{slug}` names no rule anchor left in CLAUDE.md. "
            f"Remove the row, or restore the anchor."
        )

    guard_names = guard_rule_names(guard_text)
    ci_names = ci_step_names(workflow_text)

    unmechanized_count = 0
    for slug in sorted(rules.keys() & anchor_set):
        entry = rules[slug]
        mech = entry.get("mechanism") if isinstance(entry, dict) else None
        if not isinstance(mech, dict):
            problems.append(f"row `{slug}` has no \"mechanism\" object.")
            continue
        kind = mech.get("kind")
        if kind not in KINDS:
            problems.append(f"row `{slug}` has an unknown mechanism kind {kind!r}.")
            continue

        if kind == "unmechanized":
            unmechanized_count += 1
            reason = (mech.get("reason") or "").strip()
            if len(reason.split()) < REASON_MIN_WORDS:
                problems.append(
                    f"row `{slug}` is `unmechanized` with {len(reason.split())} words of "
                    f"reason. Say what a hook or a check would have to see, in at least "
                    f"{REASON_MIN_WORDS} words, or the token is a rubber stamp."
                )
            continue

        ref = mech.get("ref")
        if not ref:
            problems.append(f"row `{slug}` names kind {kind!r} with no \"ref\".")
            continue

        if kind == "guard":
            if ref not in guard_names:
                problems.append(
                    f"row `{slug}` names guard rule `{ref}`, which is not a `refuse`/`record` "
                    f"rule name in hooks/guard.py any more. Stale row."
                )
        elif kind == "gate":
            path = os.path.join(ROOT, ref)
            if not os.path.exists(path):
                problems.append(f"row `{slug}` names gate file `{ref}`, which does not exist.")
            else:
                needle = mech.get("needle")
                if needle and needle not in read(path):
                    problems.append(
                        f"row `{slug}` names gate file `{ref}`, but the text it depends on, "
                        f"{needle!r}, is gone from that file. Stale row."
                    )
        elif kind == "ci":
            if ref not in ci_names:
                problems.append(
                    f"row `{slug}` names CI step {ref!r}, which is not a step name in "
                    f".github/workflows/gates.yml any more. Stale row."
                )

    if unmechanized_count != unmechanized_expected:
        direction = "more" if unmechanized_count > unmechanized_expected else "fewer"
        problems.append(
            f"{unmechanized_count} rules read `unmechanized`, {direction} than the pinned "
            f"{unmechanized_expected}. Built a mechanism for one? Lower UNMECHANIZED_EXPECTED "
            f"in this commit. Added a rule with no mechanism? Raise it and say why. This "
            f"count moves only in the commit that changes it."
        )

    return problems


def main() -> None:
    if not os.path.exists(CLAUDE_MD):
        print("rule_audit: FAIL\n - CLAUDE.md does not exist.")
        sys.exit(1)
    if not os.path.exists(MAP_FILE):
        print("rule_audit: FAIL\n - lint/rule_mechanisms.json does not exist.")
        sys.exit(1)

    claude_text = read(CLAUDE_MD)
    try:
        rule_map = json.loads(read(MAP_FILE))
    except Exception as e:
        print(f"rule_audit: FAIL\n - lint/rule_mechanisms.json is not valid JSON: {e}")
        sys.exit(1)

    guard_text = read(GUARD_PY) if os.path.exists(GUARD_PY) else ""
    workflow_text = read(WORKFLOW) if os.path.exists(WORKFLOW) else ""

    problems = check(claude_text, rule_map, guard_text, workflow_text)
    if problems:
        print("rule_audit: FAIL")
        for p in problems:
            print(" - " + p)
        sys.exit(1)

    anchors = claude_md_anchors(claude_text)
    rules = rule_map["rules"]
    unmechanized = sum(1 for s in anchors if rules[s]["mechanism"]["kind"] == "unmechanized")
    print(
        f"rule_audit: OK. {len(anchors)} rule anchors, "
        f"{len(anchors) - unmechanized} name a mechanism that resolves, "
        f"{unmechanized} argue `unmechanized` (pinned at {UNMECHANIZED_EXPECTED})."
    )


if __name__ == "__main__":
    main()

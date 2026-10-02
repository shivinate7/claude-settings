#!/usr/bin/env python3
"""CI check: every rule anchor maps to a mechanism, or an argued `unmechanized`.

RULE_FILES names the files read for anchors: CLAUDE.md, and the output style that holds the
rules for the main session's replies. The anchors of all files form one list, so a slug
used in two files reads as a duplicate.

CLAUDE.md says to turn each rule into a hook or a check, and calls itself "the fallback, not
the enforcement". Nothing measured that claim. This is the measurement. It runs in CI only,
never at Stop: the map does not change turn to turn, so there is nothing to gain from paying
its cost on every reply.

WHAT COUNTS AS A RULE. Each prescriptive sentence in a rule file carries an inline anchor,
`<!-- rule:<slug> -->`, placed right after the sentence it names. The anchor is the stable
key. A rule's wording can be reworded around its anchor without breaking this check; only
deleting or renaming the anchor comment does. Purely descriptive or argumentative sentences
that assert no independent, checkable behavior carry no anchor and are not rules for this
check. That line is a judgment call the person who adds a rule makes when they add its
anchor, not something this script infers from prose.

THE MAP. lint/rule_mechanisms.json holds one row per anchor. A row's mechanism is one of:
  - `guard`: a rule name string this session's hooks/guard.py actually passes as the third
    argument to `refuse(...)` or `record(...)`.
  - `gate`: a file, named by its path from the repo root, that exists on disk, plus the proof
    that the gate WORKS. A row carries `test`, `setting`, or both. `needle` (a substring
    that must appear in the file) is refused: a docstring or a label satisfies it while the
    code under it does nothing (decisions/known-bad-input-proves-the-gate.md).
      - `test`: a test id, `path::name` or `path::Class.name`, resolved by `citation_problem`.
        A `.py` id must name a `def` (a unittest method, or a case function that the file
        references), or a case registered by a literal first argument to `add(`, `sh(` or
        `check(`. All of that is read from the AST. A `.mjs` id must name a top-level
        `test("name", ...)` registration; no JavaScript parser ships here, so that one is a
        line-anchored pattern on the registry key. That is a bandaid, named.
      - `setting`: `{"file": "settings.json", "path": "env.NAME", "equals": "v"}` or
        `"contains": "v"`. The value is read from the parsed JSON, never the name. `[*]` in a
        path fans out over a list.
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
a real guard rule, or a real test, that does not actually cover what the rule sentence
demands, and this check passes it anyway. It proves a cited test exists and is collected, not
that the test goes red on the defect; the fixture tests in lint/test_rule_audit.py and the
mutants in hooks/mutate_guard.py carry that proof for the checks changed with them. It cannot judge whether an `unmechanized` reason is a good argument,
only whether one was written at length. And it governs only the RULE_FILES text: a rule
recorded in a decision file or an agent prompt is a different surface, ungoverned here.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from typing import Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Paths relative to the repo root, so a fixture test reads the same list under its own root.
RULE_FILES = ["CLAUDE.md", os.path.join("output-styles", "shiv-stylisms.md")]
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
RULE_FLOOR = 91
UNMECHANIZED_EXPECTED = 75
REASON_MIN_WORDS = 8

KINDS = {"guard", "gate", "ci", "unmechanized"}
# A case-registering call whose first argument is a literal case name.
CASE_REGISTRARS = {"add", "sh", "check"}


def _defs(tree):
    """Every function def in `tree`, as (class name or None, node)."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append((node.name, item))
    in_class = {id(n) for _, n in out}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and id(node) not in in_class:
            out.append((None, node))
    return out


def citation_problem(test_id: str, root: str = ROOT):
    """Return why `test_id` names no test that runs, or None when it does.

    `path::name`, `path::Class.name`. The file must exist; the name must resolve as the
    module docstring says. A name defined twice in one class is refused: the second `def`
    silently replaces the first, so the cited body never runs.
    """
    path, sep, name = test_id.partition("::")
    if not sep or not name:
        return f"test id {test_id!r} is not `path::name`."
    full = os.path.join(root, path)
    if not os.path.exists(full):
        return f"test file `{path}` does not exist."
    text = read(full)
    if path.endswith(".mjs"):
        if re.search(r'^test\(\s*"' + re.escape(name) + r'"\s*,', text, re.MULTILINE):
            return None
        return f"`{path}` registers no test named {name!r}."
    if not path.endswith(".py"):
        return f"test file `{path}` is neither .py nor .mjs."
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return f"`{path}` does not parse: {e}."
    cls, _, func = name.rpartition(".")
    matches = [n for c, n in _defs(tree) if n.name == func and (not cls or c == cls)]
    if len(matches) > 1:
        return f"`{path}` defines {name!r} {len(matches)} times; the last silently wins."
    if matches:
        node = matches[0]
        owners = {id(n): c for c, n in _defs(tree)}
        if owners[id(node)] is not None:
            if not func.startswith("test"):
                return f"`{name}` in `{path}` is a method that unittest never collects."
            return None
        used = sum(1 for n in ast.walk(tree)
                   if isinstance(n, ast.Name) and n.id == func and isinstance(n.ctx, ast.Load))
        if used == 0:
            return f"`{name}` in `{path}` is defined and never referenced, so no run calls it."
        return None
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id in CASE_REGISTRARS and n.args
                and isinstance(n.args[0], ast.Constant) and n.args[0].value == name):
            return None
    return f"`{path}` has no test, case function, or registered case named {name!r}."


def _walk(value, parts):
    """Yield every value at `parts` under `value`. A `name[*]` part fans out over a list."""
    if not parts:
        yield value
        return
    head, rest = parts[0], parts[1:]
    fan = head.endswith("[*]")
    key = head[:-3] if fan else head
    if not isinstance(value, dict) or key not in value:
        return
    child = value[key]
    if fan:
        if isinstance(child, list):
            for item in child:
                yield from _walk(item, rest)
    else:
        yield from _walk(child, rest)


def setting_problem(spec, root: str = ROOT):
    """Return why a `setting` spec does not hold in its JSON file, or None when it does."""
    if not isinstance(spec, dict) or not spec.get("file") or not spec.get("path"):
        return "a `setting` needs \"file\" and \"path\"."
    if ("equals" in spec) == ("contains" in spec):
        return "a `setting` needs exactly one of \"equals\" and \"contains\"."
    full = os.path.join(root, spec["file"])
    try:
        data = json.loads(read(full))
    except Exception as e:
        return f"`{spec['file']}` is unreadable as JSON: {e}."
    found = list(_walk(data, spec["path"].split(".")))
    if "equals" in spec:
        ok = any(v == spec["equals"] for v in found)
        want = f"= {spec['equals']!r}"
    else:
        ok = any(isinstance(v, str) and spec["contains"] in v for v in found)
        want = f"containing {spec['contains']!r}"
    if ok:
        return None
    return (f"`{spec['file']}` at `{spec['path']}` does not hold {want} "
            f"(found {found!r}).")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def claude_md_anchors(text: str) -> List[str]:
    return [m.group(1) for m in ANCHOR_RE.finditer(text)]


def rule_text(root: str = ROOT) -> str:
    """The text of every RULE_FILES entry under `root`, joined. One list of anchors."""
    return "\n".join(read(os.path.join(root, p)) for p in RULE_FILES)


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
            f"found {len(anchors)} rule anchors in the rule files, fewer than the pinned floor "
            f"{rule_floor}. An anchor was likely deleted, or this reader broke on a reword. "
            f"Lower RULE_FLOOR in lint/rule_audit.py deliberately if a rule genuinely went. "
            f"Never let a shrinking reader report clean."
        )

    dupes = sorted({a for a in anchors if anchors.count(a) > 1})
    if dupes:
        problems.append("duplicate rule anchors across the rule files: " + ", ".join(dupes))

    anchor_set = set(anchors)
    rules = rule_map.get("rules") if isinstance(rule_map, dict) else None
    if not isinstance(rules, dict):
        problems.append("lint/rule_mechanisms.json has no top-level \"rules\" object.")
        return problems

    missing = sorted(anchor_set - rules.keys())
    for slug in missing:
        problems.append(f"rule `{slug}` has no row in lint/rule_mechanisms.json.")

    orphaned = sorted(rules.keys() - anchor_set)
    for slug in orphaned:
        problems.append(
            f"lint/rule_mechanisms.json row `{slug}` names no rule anchor left in the rule files. "
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
                continue
            if "needle" in mech:
                problems.append(
                    f"row `{slug}` cites a `needle`, which passes on a docstring or a label. "
                    f"Cite a `test` that exercises the behaviour, or a `setting` value, or "
                    f"downgrade the row to `unmechanized`."
                )
            if not mech.get("test") and not mech.get("setting"):
                problems.append(
                    f"row `{slug}` names gate file `{ref}` and proves nothing about it. "
                    f"Add a `test` id or a `setting`."
                )
            if mech.get("test"):
                why = citation_problem(mech["test"])
                if why:
                    problems.append(f"row `{slug}` cites a test that does not resolve: {why}")
            if mech.get("setting"):
                why = setting_problem(mech["setting"])
                if why:
                    problems.append(f"row `{slug}` cites a setting that does not hold: {why}")
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
    for path in RULE_FILES:
        if not os.path.exists(os.path.join(ROOT, path)):
            print(f"rule_audit: FAIL\n - {path} does not exist.")
            sys.exit(1)
    if not os.path.exists(MAP_FILE):
        print("rule_audit: FAIL\n - lint/rule_mechanisms.json does not exist.")
        sys.exit(1)

    claude_text = rule_text()
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

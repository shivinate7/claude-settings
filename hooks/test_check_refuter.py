#!/usr/bin/env python3
"""Cases for the check refuter: hooks/check_refuter.py, the one home of the refuter, and the send_message site of
hooks/call_judge.py that calls it on a lane brief (guard_merge.LANE_BRIEF_MARKER).

A lane brief's Done check line is read blind: the refuter sees only the step's title and why, read from the record
at refs/remotes/origin/<record branch>, and the Done check line. It answers met, gap or unknown. A gap or an unknown
refuses the send under rule `check-refuter`. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_check_refuter.py

Interface the module must match (the builder's contract):
- hooks/check_refuter.py: REFUTER_MODEL == "sonnet"; REFUTER_TIMEOUT, an int under the call_judge hook timeout
  in settings.json (70 s).
- refute(title, why, check) -> (verdict, case). One call to decision_watch.invoke_model(prompt, model=REFUTER_MODEL,
  timeout=REFUTER_TIMEOUT, shape=decision_watch.VERDICT_SHAPE, ...). ALLOW -> ("met", ""). FLAG -> ("gap", the model's
  why). (None, err) -> ("unknown", err). An odd answer -> ("unknown", ...). Never "met" on an error or an odd answer.
- ask_for_step(root, step) -> (title, why), from roadmap/data/steps/<step>.json at refs/remotes/origin/<record
  branch>. A missing ref, file or field raises, or returns no title.
- done_check_line(brief) -> the text after the first line-start `Done check:` (bold allowed), or None.
- hooks/call_judge.py: a send_message whose first non-blank line carries the lane brief marker is judged. No Done
  check line refuses with no model call. Otherwise one refute call per brief: gap and unknown refuse, met allows.
  Any other send_message makes no model call and no import of check_refuter.
- settings.json: the call_judge row's matcher includes mcp__claude-code-remote__send_message.

The hook cases reuse hooks/test_call_judge.py: its run_hook, its claude stub and its make_repo (the one home of the
harness and the step fixture). The refute cases replace decision_watch.invoke_model in this process. A missing module
fails each case with a named cause, never a crash.

The non-brief cases are controls: they pass on main, where call_judge ignores send_message, and they guard the
builder's marker check.
"""
import contextlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import decision_watch  # noqa: E402  the one model caller; a case replaces its invoke_model
import guard_merge  # noqa: E402  BRIEF_TOOL and LANE_BRIEF_MARKER, the one home of the brief's names
import test_call_judge as tcj  # noqa: E402  the call_judge harness: run_hook, make_repo, git, check, detail

REFUTER_PATH = os.path.join(HERE, "check_refuter.py")
STEP = "refute1"
TITLE = "A blind reader flags a done-check that can pass with the ask unmet"
WHY = "Work can't be marked done by a check that misses the point."
CHECK = "tests and lint green through bin/verdict."
DONE_LINE = "Done check: " + CHECK
GAP_WHY = "The check passes on a run that never reads the ask."
GAP_ANSWER = json.dumps({"verdict": "FLAG", "why": GAP_WHY})
ALLOW_ANSWER = json.dumps({"verdict": "ALLOW"})
DEFAULT_FIELDS = {"title": TITLE, "why": WHY}
NOTE_SENTINEL = "SENTINEL-STEP-NOTE-9b2e"  # in the step's note: the refuter never reads it
BODY_SENTINEL = "SENTINEL-BRIEF-BODY-4c7a"  # in the brief body: the refuter never reads it
REFUTER_CALL_MODEL = "sonnet"  # the model the refuter names, as the brief fixes it
check, detail = tcj.check, tcj.detail


# ------------------------------------------------------------------ loading and fakes

def load_refuter():
    """(module, "") or (None, why it does not load). A missing module is a named failure of each case."""
    try:
        return tcj.load_file_module(REFUTER_PATH, "check_refuter_probe"), ""
    except Exception as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)


def missing(mod, *names):
    """The names the module does not define, in order."""
    return [name for name in names if not hasattr(mod, name)]


@contextlib.contextmanager
def model_answers(answer):
    """Replace decision_watch.invoke_model with one canned (verdict, error) answer for the block. Yields the calls,
    each as (prompt, keyword arguments)."""
    calls = []

    def fake(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return answer

    real = decision_watch.invoke_model
    decision_watch.invoke_model = fake
    try:
        yield calls
    finally:
        decision_watch.invoke_model = real


def refute_with(mod, answer, title=TITLE, why=WHY, check_line=CHECK):
    """(got, calls, error). A raise from refute is the error text, so a case names it and never crashes."""
    with model_answers(answer) as calls:
        try:
            return mod.refute(title, why, check_line), calls, ""
        except Exception as exc:
            return None, calls, "refute raised %s: %s" % (type(exc).__name__, exc)


def read_step(mod, root):
    """(got, error) for ask_for_step(root, STEP). A raise is the error text."""
    try:
        return mod.ask_for_step(root, STEP), ""
    except Exception as exc:
        return None, "ask_for_step raised %s: %s" % (type(exc).__name__, exc)


def is_unknown(got, error):
    """A raise, or a return with no title, is unknown."""
    return bool(error) or not (isinstance(got, (tuple, list)) and len(got) == 2 and got[0])


# ------------------------------------------------------------------ fixtures

def ask_repo(name, fields=None, origin=True):
    """A repo whose roadmap holds the step, with its title and why unless `fields` replaces them (a None value drops
    the field). `origin` makes refs/remotes/origin/roadmap, the ref the refuter reads."""
    merged = dict(DEFAULT_FIELDS)
    merged.update(fields or {})
    repo = tcj.make_repo(name, steps={STEP: NOTE_SENTINEL}, step_fields={STEP: merged})
    if origin:
        tcj.git(repo, "update-ref", "refs/remotes/origin/roadmap", "refs/heads/roadmap")
    return repo


def brief_text(done=DONE_LINE, body=None):
    """A lane brief: the marker on the first non-blank line, a body, then the Done check line unless `done` is None."""
    lines = ["%s %s. Topic: check-refuter." % (guard_merge.LANE_BRIEF_MARKER, STEP), "",
             body if body is not None else BODY_SENTINEL + " The brief names files and rulings only.", ""]
    if done is not None:
        lines.append(done)
    return "\n".join(lines)


def send_input(message, cwd):
    """A PreToolUse payload for a send_message call with `message`, from the checkout at `cwd`."""
    return json.dumps({"session_id": tcj.SID_A, "tool_name": guard_merge.BRIEF_TOOL, "cwd": cwd,
                       "tool_input": {"session_id": "ses00003", "message": message}})


def done_text(got):
    """The Done check text with its bold stars and spaces removed; "" for None."""
    return "" if got is None else str(got).strip().strip("*").strip()


# ------------------------------------------------------------------ module contract

def case_refuter_module_defines_the_contract():
    mod, err = load_refuter()
    if mod is None:
        check("check_refuter loads from hooks/check_refuter.py", False, err)
        return
    names = missing(mod, "REFUTER_MODEL", "REFUTER_TIMEOUT", "refute", "ask_for_step", "done_check_line")
    check("check_refuter defines REFUTER_MODEL, REFUTER_TIMEOUT, refute, ask_for_step and done_check_line",
          not names, "missing: " + ", ".join(names))


def case_refuter_timeout_is_under_call_judge_timeout():
    mod, err = load_refuter()
    if mod is None:
        check("REFUTER_TIMEOUT is an int", False, "hooks/check_refuter.py does not load: " + err)
        return
    timeout = getattr(mod, "REFUTER_TIMEOUT", None)
    check("REFUTER_TIMEOUT is an int number of seconds", isinstance(timeout, int) and not isinstance(timeout, bool),
          repr(timeout))
    rows = tcj.call_judge_rows()
    hook_timeout = rows[0][1].get("timeout") if len(rows) == 1 else None
    check("REFUTER_TIMEOUT is under the call_judge hook timeout in settings.json",
          isinstance(timeout, int) and isinstance(hook_timeout, int) and timeout < hook_timeout,
          "REFUTER_TIMEOUT=%r, hook timeout=%r" % (timeout, hook_timeout))


def case_settings_matcher_includes_send_message():
    rows = tcj.call_judge_rows()
    matcher = (rows[0][0].get("matcher") or "").split("|") if len(rows) == 1 else []
    check("settings: the call_judge row's matcher includes the send_message tool",
          guard_merge.BRIEF_TOOL in matcher, "matcher=%r rows=%d" % ("|".join(matcher), len(rows)))


# ------------------------------------------------------------------ refute (blind verdict, mocked model)

def case_refute_flag_is_a_gap_that_names_the_case():
    mod, err = load_refuter()
    if mod is None:
        check("refute FLAG: the verdict is gap", False, "hooks/check_refuter.py does not load: " + err)
        return
    absent = missing(mod, "refute")
    if absent:
        check("refute FLAG: the verdict is gap", False, "check_refuter defines no refute()")
        return
    got, calls, error = refute_with(mod, ({"verdict": "FLAG", "why": GAP_WHY}, None))
    check("refute FLAG: the verdict is gap", got is not None and got[0] == "gap", error or repr(got))
    check("refute FLAG: the case is the model's why", got is not None and GAP_WHY in str(got[1]), error or repr(got))


def case_refute_allow_is_met():
    mod, err = load_refuter()
    if mod is None or missing(mod, "refute"):
        check("refute ALLOW: returns (met, empty case)", False,
              err or "check_refuter defines no refute()")
        return
    got, calls, error = refute_with(mod, ({"verdict": "ALLOW"}, None))
    check("refute ALLOW: returns (met, empty case)", got is not None and tuple(got) == ("met", ""),
          error or repr(got))


def case_refute_error_is_unknown():
    mod, err = load_refuter()
    if mod is None or missing(mod, "refute"):
        check("refute model error: the verdict is unknown", False, err or "check_refuter defines no refute()")
        return
    got, calls, error = refute_with(mod, (None, "model subprocess timed out"))
    check("refute model error: the verdict is unknown, never met", got is not None and got[0] == "unknown",
          error or repr(got))
    check("refute model error: the case carries the error text",
          got is not None and "model subprocess timed out" in str(got[1]), error or repr(got))


def case_refute_odd_answer_is_unknown():
    mod, err = load_refuter()
    if mod is None or missing(mod, "refute"):
        check("refute odd answer: the verdict is unknown", False, err or "check_refuter defines no refute()")
        return
    odd = ({"verdict": "MAYBE"}, {"ok": True}, {"verdict": ["ALLOW"]}, {})
    for answer in odd:
        got, calls, error = refute_with(mod, (answer, None))
        check("refute odd answer %s: the verdict is unknown, never met" % json.dumps(answer),
              got is not None and got[0] == "unknown", error or repr(got))
    got, calls, error = refute_with(mod, (None, None))
    check("refute with no answer and no error: the verdict is unknown", got is not None and got[0] == "unknown",
          error or repr(got))


def case_refute_one_call_with_the_contract_arguments():
    mod, err = load_refuter()
    if mod is None or missing(mod, "refute", "REFUTER_MODEL", "REFUTER_TIMEOUT"):
        check("refute: one invoke_model call per refute", False,
              err or "check_refuter defines no refute() or REFUTER_MODEL or REFUTER_TIMEOUT")
        return
    got, calls, error = refute_with(mod, ({"verdict": "ALLOW"}, None))
    check("refute: one invoke_model call per refute", len(calls) == 1, error or "calls=%d" % len(calls))
    kwargs = calls[0][1] if calls else {}
    check("refute: REFUTER_MODEL is the one named setting, sonnet, and the call uses it",
          mod.REFUTER_MODEL == REFUTER_CALL_MODEL and kwargs.get("model") == mod.REFUTER_MODEL,
          "REFUTER_MODEL=%r call model=%r" % (mod.REFUTER_MODEL, kwargs.get("model")))
    check("refute: the call's timeout is REFUTER_TIMEOUT", kwargs.get("timeout") == mod.REFUTER_TIMEOUT,
          "call timeout=%r" % (kwargs.get("timeout"),))
    check("refute: the call's shape is decision_watch.VERDICT_SHAPE",
          kwargs.get("shape") == decision_watch.VERDICT_SHAPE, "call shape=%r" % (kwargs.get("shape"),))


def case_refute_prompt_holds_the_three_lines():
    mod, err = load_refuter()
    if mod is None or missing(mod, "refute"):
        check("refute prompt: it holds the step's title", False, err or "check_refuter defines no refute()")
        return
    got, calls, error = refute_with(mod, ({"verdict": "ALLOW"}, None))
    prompt = calls[0][0] if calls else ""
    check("refute prompt: it holds the step's title", TITLE in prompt, error or "title not in the prompt")
    check("refute prompt: it holds the step's why", WHY in prompt, error or "why not in the prompt")
    check("refute prompt: it holds the Done check line", CHECK in prompt, error or "check line not in the prompt")


# ------------------------------------------------------------------ ask_for_step (the record, read at the origin ref)

def case_ask_for_step_reads_the_origin_ref():
    mod, err = load_refuter()
    if mod is None or missing(mod, "ask_for_step"):
        check("ask_for_step: the origin ref's step gives its title and why", False,
              err or "check_refuter defines no ask_for_step()")
        return
    got, error = read_step(mod, ask_repo("refuter-origin"))
    check("ask_for_step: the origin ref's step gives its title and why",
          got is not None and tuple(got) == (TITLE, WHY), error or repr(got))


def case_ask_for_step_missing_ref_is_unknown():
    mod, err = load_refuter()
    if mod is None or missing(mod, "ask_for_step"):
        check("ask_for_step: no origin ref is unknown", False, err or "check_refuter defines no ask_for_step()")
        return
    got, error = read_step(mod, ask_repo("refuter-no-ref", origin=False))
    check("ask_for_step: no origin ref is unknown, and the local roadmap branch is not read instead",
          is_unknown(got, error), error or repr(got))


def case_ask_for_step_missing_field_is_unknown():
    mod, err = load_refuter()
    if mod is None or missing(mod, "ask_for_step"):
        check("ask_for_step: a step with no why is unknown", False, err or "check_refuter defines no ask_for_step()")
        return
    got, error = read_step(mod, ask_repo("refuter-no-why", fields={"why": None}))
    check("ask_for_step: a step with no why is unknown", is_unknown(got, error), error or repr(got))


def case_ask_for_step_record_branch_key():
    mod, err = load_refuter()
    if mod is None or missing(mod, "ask_for_step"):
        check("ask_for_step: record-branch names the ref read", False, err or "check_refuter defines no ask_for_step()")
        return
    repo = ask_repo("refuter-records")
    extras = os.path.join(repo, ".claude", "layout-extras.json")
    with open(extras, encoding="utf-8") as f:
        data = json.load(f)
    data["record-branch"] = "records"
    with open(extras, "w", encoding="utf-8") as f:
        json.dump(data, f)
    got, error = read_step(mod, repo)
    check("ask_for_step: with record-branch set to records and no records ref, it is unknown, not the roadmap's step",
          is_unknown(got, error), error or repr(got))
    tcj.git(repo, "update-ref", "refs/remotes/origin/records", "refs/heads/roadmap")
    got, error = read_step(mod, repo)
    check("ask_for_step: with record-branch set, it reads refs/remotes/origin/records",
          got is not None and tuple(got) == (TITLE, WHY), error or repr(got))


# ------------------------------------------------------------------ done_check_line (text of the brief)

def case_done_check_line_reads_the_line_start_line():
    mod, err = load_refuter()
    if mod is None or missing(mod, "done_check_line"):
        check("done_check_line: a plain Done check line gives its text", False,
              err or "check_refuter defines no done_check_line()")
        return
    got = mod.done_check_line("Brief.\n" + DONE_LINE + "\n")
    check("done_check_line: a plain Done check line gives its text", done_text(got) == CHECK, repr(got))
    got = mod.done_check_line("Brief.\n**Done check:** " + CHECK)
    check("done_check_line: a bold Done check line gives its text", done_text(got) == CHECK, repr(got))
    got = mod.done_check_line("See the Done check: line below.")
    check("done_check_line: a Done check not at a line start is not read", got is None, repr(got))
    got = mod.done_check_line("Brief only, no check line.")
    check("done_check_line: a brief with no Done check line gives None", got is None, repr(got))
    got = mod.done_check_line("")
    check("done_check_line: an empty brief gives None", got is None, repr(got))
    got = mod.done_check_line("Done check: " + CHECK + "\nDone check: some other check.")
    check("done_check_line: the first Done check line wins", done_text(got) == CHECK, repr(got))
    long_body = "\n".join("Body line %d names a file." % i for i in range(2000))
    got = mod.done_check_line(long_body + "\n" + DONE_LINE)
    check("done_check_line: a full-size brief still gives its Done check line", done_text(got) == CHECK, repr(got)[:120])
    scanners = 'Don\'t skip the "quoted line.\n/* open comment\n// line comment\n# heading'
    got = mod.done_check_line(scanners + "\n" + DONE_LINE)
    check("done_check_line: a lone quote or a comment opener in the body does not hide the Done check line",
          done_text(got) == CHECK, repr(got)[:120])


# ------------------------------------------------------------------ call_judge send_message site (hook, mocked claude)

def case_brief_gap_is_refused_and_names_the_case():
    repo = ask_repo("refuter-origin")
    r = tcj.run_hook(send_input(brief_text(), repo), answer=GAP_ANSWER)
    check("brief gap: exactly one model call", len(r.calls) == 1, detail(r))
    argv = r.calls[0]["argv"] if r.calls else []
    model_arg = argv[argv.index("--model") + 1] if "--model" in argv and argv.index("--model") + 1 < len(argv) else None
    check("brief gap: the call runs the sonnet model", model_arg == REFUTER_CALL_MODEL, "argv=%r" % (argv,))
    check("brief gap: the send is refused under rule check-refuter",
          r.deny() is not None and r.reason().startswith("check-refuter"), detail(r))
    check("brief gap: the refusal names the case", GAP_WHY in r.reason(), detail(r))


def case_brief_matching_check_is_allowed_with_one_call():
    repo = ask_repo("refuter-origin")
    r = tcj.run_hook(send_input(brief_text(), repo), answer=ALLOW_ANSWER)
    check("brief met: exactly one model call", len(r.calls) == 1, detail(r))
    check("brief met: after that one call the send is allowed, exit 0 with no output",
          len(r.calls) == 1 and r.code == 0 and r.deny() is None, detail(r))


def case_brief_model_error_is_refused_as_unknown():
    repo = ask_repo("refuter-origin")
    r = tcj.run_hook(send_input(brief_text(), repo), model_fail=True)
    check("brief model error: the send is refused under rule check-refuter",
          r.deny() is not None and r.reason().startswith("check-refuter"), detail(r))
    check("brief model error: the reason says unknown", "unknown" in r.reason().lower(), detail(r))


def case_brief_without_done_check_is_refused_with_no_call():
    repo = ask_repo("refuter-origin")
    r = tcj.run_hook(send_input(brief_text(done=None), repo), answer=ALLOW_ANSWER)
    check("brief with no Done check line: refused under rule check-refuter with no model call",
          r.deny() is not None and r.reason().startswith("check-refuter") and r.calls == [], detail(r))


def case_brief_missing_ask_is_refused_as_unknown():
    repo = ask_repo("refuter-no-ref", origin=False)
    r = tcj.run_hook(send_input(brief_text(), repo), answer=ALLOW_ANSWER)
    check("brief with no ask on the record: the send is refused under rule check-refuter",
          r.deny() is not None and r.reason().startswith("check-refuter"), detail(r))
    check("brief with no ask on the record: the reason says unknown", "unknown" in r.reason().lower(), detail(r))


def case_brief_prompt_is_blind():
    repo = ask_repo("refuter-origin")
    shown = tcj.git(repo, "show", "refs/remotes/origin/roadmap:roadmap/data/steps/%s.json" % STEP).stdout
    check("brief prompt: scope, the fixture step carries the note sentinel", NOTE_SENTINEL in shown, shown[:120])
    r = tcj.run_hook(send_input(brief_text(), repo), answer=ALLOW_ANSWER)
    prompt = r.calls[0]["prompt"] if len(r.calls) == 1 else ""
    check("brief prompt: the one model call holds the step's title, why and the check line",
          len(r.calls) == 1 and all(text in prompt for text in (TITLE, WHY, CHECK)), detail(r))
    check("brief prompt: the one model call carries no brief-body or step-note text",
          len(r.calls) == 1 and BODY_SENTINEL not in prompt and NOTE_SENTINEL not in prompt, detail(r))


def case_non_brief_send_is_not_judged():
    repo = ask_repo("refuter-origin")
    r = tcj.run_hook(send_input("Please check the diff when you can.", repo), answer=GAP_ANSWER)
    check("non-brief send: no model call", r.calls == [], detail(r))
    check("non-brief send: allowed with no output", r.code == 0 and r.deny() is None, detail(r))
    check("non-brief send: check_refuter is not imported", "check_refuter" not in r.imports, detail(r))
    r = tcj.run_hook(send_input("Background.\n" + brief_text(), repo), answer=GAP_ANSWER)
    check("marker off the first non-blank line: no model call and allowed",
          r.calls == [] and r.deny() is None, detail(r))
    r = tcj.run_hook(send_input("", repo), answer=GAP_ANSWER)
    check("empty send: no model call and allowed", r.calls == [] and r.deny() is None, detail(r))


def main():
    for case in (case_refuter_module_defines_the_contract, case_refuter_timeout_is_under_call_judge_timeout,
                 case_settings_matcher_includes_send_message,
                 case_refute_flag_is_a_gap_that_names_the_case, case_refute_allow_is_met,
                 case_refute_error_is_unknown, case_refute_odd_answer_is_unknown,
                 case_refute_one_call_with_the_contract_arguments, case_refute_prompt_holds_the_three_lines,
                 case_ask_for_step_reads_the_origin_ref, case_ask_for_step_missing_ref_is_unknown,
                 case_ask_for_step_missing_field_is_unknown, case_ask_for_step_record_branch_key,
                 case_done_check_line_reads_the_line_start_line,
                 case_brief_gap_is_refused_and_names_the_case, case_brief_matching_check_is_allowed_with_one_call,
                 case_brief_model_error_is_refused_as_unknown, case_brief_without_done_check_is_refused_with_no_call,
                 case_brief_missing_ask_is_refused_as_unknown, case_brief_prompt_is_blind,
                 case_non_brief_send_is_not_judged):
        try:
            case()
        except Exception as exc:
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    print("FAIL: %d failed" % len(tcj.FAILED) if tcj.FAILED else "all checks passed")
    return 1 if tcj.FAILED else 0


if __name__ == "__main__":
    sys.exit(main())

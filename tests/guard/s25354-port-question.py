# section 25354
FAMILY = "port-question"
#
# Decision port-keeps-behaviour: a waiting item about a port or
# redesign carries a "Departs from:" line and never holds work. The refusal reads the item the
# writer sets; the reason names what to add and no forbidden target.

PQ_TITLE = "What happens to Suspense cards when Card in Hand closes?"
PQ_CTX = "Duo Card in Hand ports the web app's Card in Hand screen."
PQ_DEPARTS = "Departs from: web/src/cardInHand.ts:closeCardInHand \u2014 Suspense cards stay in Suspense"
PQ_HOLDS = "Card in Hand plan is blocked on this."
PQ_URL = "https://claude.ai/artifact/pqpage"   # the waiting page of the fixture repo below
PQ_REPO = os.path.join(ROOT, "pqrepo")
os.makedirs(os.path.join(PQ_REPO, ".git"), exist_ok=True)
os.makedirs(os.path.join(PQ_REPO, ".claude"), exist_ok=True)
with open(os.path.join(PQ_REPO, ".claude", "layout-extras.json"), "w", encoding="utf-8") as _f:
    json.dump({"kinds": {}, "waiting-page": PQ_URL}, _f)


# The lines a waiting-page decision carries (rule question-form, its cases in the owner-judge section: the
# one form of hooks/question_form.py). Each decision fixture below starts its context with them and gives
# each option a gain and a lose, so a case stays on its own rule, as TN_WHY does for a task. The lines hold
# no port word and no press word.
OJ_GOAL = "Goal: keep the CI checks fast, and keep every check"
OJ_STAKE = "Problem (risk): a wrong pick here changes what the guard lets through, so it needs your word"
OJ_BASED = "Based on (read): the stamp check runs in the lint job today"
OJ_FORM = "\n".join((OJ_GOAL, OJ_STAKE, OJ_BASED))
# The Departs from line a question carries (rule question-departs, its cases in that section). A port item
# carries it too, so the port rule's own no-line cases build their item without it (pq_item's default).
QD_LINE = "Departs from: lint/stamp.py:run_stamp — the stamp check moves to the lint job"


def with_stake(item, departs=True):
    """The item with OJ_FORM on the lines before its context, a Departs from line after them unless `departs`
    is False, and a gain and a lose on each option that lacks one. An item with no context, or no options,
    stays as it is."""
    if isinstance(item.get("context"), str):
        lines = [OJ_FORM] + ([QD_LINE] if departs else [])
        item["context"] = "\n".join(lines) + "\n" + item["context"]
    if isinstance(item.get("options"), list):
        item["options"] = [dict({"gain": "g", "lose": "l"}, **o) if isinstance(o, dict) else o
                           for o in item["options"]]
    return with_shown(item)


def with_shown(data):
    """A copy of a waiting-page write's data with the fields a session's write carries when it writes options: `shown`,
    the options as first shown (key, id, label), and an id on each option that has none (opt-<n>, n its 1-based
    position). Data with no options list is returned as it is. The fill's one home is hooks/test_call_judge.py
    (with_frozen_fields). A section cannot import it, since that import makes and sweeps a run folder, so this copy
    holds the same fill for the guard's sections."""
    if not isinstance(data, dict) or not isinstance(data.get("options"), list):
        return data
    filled = []
    for i, option in enumerate(data["options"]):
        if isinstance(option, dict):
            option = dict(option)
            option.setdefault("id", "opt-%d" % (i + 1))
        filled.append(option)
    found = dict(data, options=filled)
    found["shown"] = [{"key": o.get("key"), "id": o.get("id"), "label": o.get("label")}
                      for o in filled if isinstance(o, dict)]
    return found


def pq_item(departs=False, **over):
    item = {"id": "suspense-cards", "kind": "decision", "status": "open", "title": PQ_TITLE,
            "context": PQ_CTX, "holds": PQ_HOLDS}
    item.update(over)
    return with_stake({k: v for k, v in item.items() if v is not None}, departs=departs)


def pq(name, expected, item, action="set", **extra):
    kw = dict(action=action, collection="items", doc_id="suspense-cards", data=item)
    kw.update(extra)
    add("port question: " + name, expected, "port-question" if expected == "deny" else None,
        tool="ArtifactData", cwd=PQ_REPO, **{"url": PQ_URL, **kw})


PQ_GOOD = pq_item(port=True, context=PQ_CTX + "\n" + PQ_DEPARTS, holds=None)

pq("today's item (port words, no Departs from, holds) is denied", "deny", pq_item())
pq("a port flagged true with no Departs from line is denied", "deny",
   pq_item(port=True, holds=None))
pq("a port flagged true with a Departs from line and holds is denied", "deny",
   pq_item(port=True, context=PQ_CTX + "\n" + PQ_DEPARTS))
pq("a port with a Departs from line and no holds is allowed", "allow", PQ_GOOD)
pq("the Departs from line is read in any case, at a line start", "allow",
   pq_item(port=True, context=PQ_CTX + "\ndeparts from: a.ts:f \u2014 x", holds=None))
pq("a Departs from phrase mid-line does not count", "deny",
   pq_item(port=True, context="This item departs from: a.ts:f", holds=None))
# A port's Departs from line names the file and symbol on main, or says main for a new thing: "main — adds X"
# (decision port-keeps-behaviour, the question-departs section). A line that says none, or names neither a
# file:symbol nor main with adds, is refused, and so is a second such line. The port word is read from the
# context when `port` is not set.
for _body in ("Departs from: none", "Departs from: the approval flow — adds a retry on timeout",
              "Departs from: agent-model-cap — adds a retry on timeout"):
    pq("a port whose line %r names no file:symbol on main is denied" % _body, "deny",
       pq_item(port=True, context=PQ_CTX + "\n" + _body, holds=None))
pq("a port found by its words, with no port flag, and Departs from none is denied", "deny",
   pq_item(context=PQ_CTX + "\nDeparts from: none", holds=None))
pq("an update that marks a port with Departs from none is denied", "deny",
   {"port": True, "kind": "decision", "context": OJ_FORM + "\n" + PQ_CTX + "\nDeparts from: none"},
   action="update")
pq("a task about a port with Departs from none is denied", "deny",
   pq_item(kind="task", context=PQ_CTX + "\nDeparts from: none", holds=None))
pq("a port with a good Departs from line and a second that says none is denied", "deny",
   pq_item(port=True, context=PQ_CTX + "\n" + PQ_DEPARTS + "\nDeparts from: none", holds=None))
pq("a port whose line names hooks/x.py:foo and a real change is allowed", "allow",
   pq_item(port=True, context=PQ_CTX + "\nDeparts from: hooks/x.py:foo — adds a retry on timeout", holds=None))
pq("a port whose line says main for a new thing, main — adds a retry button, is allowed", "allow",
   pq_item(port=True, context=PQ_CTX + "\nDeparts from: main — adds a retry button", holds=None))
pq("port false is the writer's word and allows today's item", "allow", pq_item(port=False, departs=True))
pq("a non-port item with holds is allowed", "allow",
   pq_item(title="Which logo colour?", context="Brand colours differ.", holds="Release waits.", departs=True))
pq("a database port question is not a port of an app", "allow",
   pq_item(title="Which port should Postgres use?", context="Postgres needs a port.", holds="Setup waits.",
           departs=True))
pq("switch ports in a rack are not a port of an app", "allow",
   pq_item(title="Patch switch ports in rack A3", context="Rack A3 needs patching.", holds="Cabling waits.",
           departs=True))
pq("a taken port is not a port of an app", "allow",
   pq_item(title="Dev setup", context="The port is taken.", holds="Setup waits.", departs=True))
pq("the incident's own wording is a known limit and is allowed", "allow",
   pq_item(title="Suspense cards when Card in Hand closes",
           context="Duo version of the web screen.", holds="Card in Hand plan waits.", departs=True))
pq("an item with no kind is allowed", "allow", pq_item(kind=None, departs=True))
pq("an items set to another artifact is allowed", "allow", pq_item(), url="https://claude.ai/artifact/other")
pq("an items set to the code form of the waiting page is denied", "deny", pq_item(),
   url="https://claude.ai/code/artifact/pqpage")
pq("a dev server port is not a port of an app", "allow",
   pq_item(title="Dev server port 8080 is taken", context="The dev server port 8080 clashes.", holds=None,
           departs=True))
pq("a port number is not a port of an app", "allow",
   pq_item(title="Pick the port number", context="Port 3000 clashes.", holds="Server waits.", departs=True))
pq("redesign with no Departs from line is denied", "deny",
   pq_item(title="Redesign of the login screen", context="The login screen is new.", holds=None))
pq("a task about a port with no Departs from line is denied", "deny",
   pq_item(kind="task", holds=None))
pq("a record that is neither a decision nor a task is allowed", "allow", pq_item(kind="note"))
pq("a set to another collection is allowed", "allow", pq_item(), collection="receipts")
pq("an update that adds holds on a port is denied", "deny", {"port": True, "holds": PQ_HOLDS},
   action="update")
pq("an update that changes a status only is allowed", "allow", {"status": "closed"},
   action="update")
pq("an update that carries no port fields is allowed on today's item", "allow",
   {"rank": 3}, action="update")
add("port question: a batch with today's item among the sets is denied", "deny", "port-question",
    tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="batch",
    writes=[{"op": "set", "collection": "receipts", "doc_id": "a", "data": {"note": "x"}},
            {"op": "set", "collection": "items", "doc_id": "suspense-cards", "data": pq_item()}])
add("port question: a batch of good sets is allowed", "allow", tool="ArtifactData", cwd=PQ_REPO,
    url=PQ_URL, action="batch",
    writes=[{"op": "set", "collection": "items", "doc_id": "suspense-cards", "data": PQ_GOOD}])
os.makedirs(os.path.join(ROOT, "pq"), exist_ok=True)
PQ_FILE_BAD = os.path.join(ROOT, "pq", "bad.json")
PQ_FILE_GOOD = os.path.join(ROOT, "pq", "good.json")
with open(PQ_FILE_BAD, "w", encoding="utf-8") as _f:
    json.dump(pq_item(), _f)
with open(PQ_FILE_GOOD, "w", encoding="utf-8") as _f:
    json.dump(PQ_GOOD, _f)
add("port question: file_path data with today's item is denied", "deny", "port-question",
    tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="set", collection="items",
    doc_id="suspense-cards", file_path=PQ_FILE_BAD)
add("port question: file_path data that departs is allowed", "allow", tool="ArtifactData", cwd=PQ_REPO,
    url=PQ_URL, action="set", collection="items", doc_id="suspense-cards", file_path=PQ_FILE_GOOD)
add("port question: an unreadable file_path fails open", "allow", tool="ArtifactData", cwd=PQ_REPO,
    url=PQ_URL, action="set", collection="items", doc_id="suspense-cards",
    file_path=os.path.join(ROOT, "pq", "missing.json"))
add("port question: the refusal says what to add", "deny", "port-question",
    carries=("Departs from:", "holds", "port"), tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="set",
    collection="items", doc_id="suspense-cards", data=pq_item())
add("port question: a read is allowed", "allow", tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="list",
    collection="items")


add("port question: a repo with no waiting page allows today's item", "allow", tool="ArtifactData",
    cwd=NOGIT, url=PQ_URL, action="set", collection="items", doc_id="suspense-cards", data=pq_item())


def port_get_logs_nothing_case():
    """An ArtifactData read starts the guard and is allowed, and the guard writes no log line."""
    path = os.path.join(LOGDIR, "guard.log")
    if os.path.exists(path):
        os.remove(path)
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env["CLAUDE_CONFIG_DIR"] = LOGDIR
    run = subprocess.run(
        [sys.executable, GUARD],
        input=json.dumps({"tool_name": "ArtifactData", "cwd": PQ_REPO,
                          "tool_input": {"action": "get", "url": PQ_URL, "collection": "items",
                                         "doc_id": "suspense-cards"}}),
        capture_output=True, text=True, env=env, timeout=60)
    if run.stdout.strip():
        return False, "the read printed %r" % run.stdout[:80]
    if os.path.exists(path) and open(path, encoding="utf-8").read().strip():
        return False, "the read wrote a guard.log line"
    return True, "the read is allowed and writes no line"


LOG_CHECKS_EXTRA.append(("port question: an ArtifactData get is allowed and writes no guard.log line",
                         port_get_logs_nothing_case))


# --------------------------------------------------------------------------- a waiting page behind main is not published

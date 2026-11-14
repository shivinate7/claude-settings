# section 43200
FAMILY = "ci-wait-cap"
#
# Rule ci-wait-cap (hooks/guard.py, the claude-code-remote send_later tool). A scheduled check-in whose message says it
# waits on CI is refused when that wait is more than the cap: delay_minutes over the cap, or an `at` time more than the
# cap from now. The cap is cap_minutes() in hooks/ci_wait_cap.py, which reads hooks/ci_wait_cap.json on each call, so a
# changed value moves the limit. Why: under the 1-hour prompt cache, a check-in that wakes after the cache ends pays a
# full context rewrite.
#
# THE CI READING, pinned here. A message says it waits on CI when it holds, in any letter case, the whole word CI or
# checks, or the phrase PR run or workflow run. A substring does not count (decision, specific), and neither does check
# alone (check in with the owner). The whole message is read, not only the first line. The `at` field is read as
# ISO-8601 with an offset and compared with LOCAL_TIME_NOW, which every case here fixes, so no case reads the real clock.
#
# The cap is read from this repository's own reader. A guard copy made by mutate_shared.guard_tree carries no data file,
# so the cases below that change the data file's value build their own copy, and the limit must move with it.

import importlib.util as _cap_ilu

CAP_RULE = "ci-wait-cap"
CAP_TOOL = "mcp__claude-code-remote__send_later"
CAP_CLOCK = "2026-11-14T11:04:00-06:00"  # 11:04 CST, the clock every case fixes


def _load_cap_names():
    spec = _cap_ilu.spec_from_file_location("ci_wait_cap_for_cases", os.path.join(HERE, "ci_wait_cap.py"))
    names = _cap_ilu.module_from_spec(spec)
    spec.loader.exec_module(names)
    return names


try:
    CAP = _load_cap_names().cap_minutes()
except Exception as exc:  # a missing or malformed data file stops the run; a silent default would hide it
    sys.exit("fixture setup failed: the CI-wait cap does not load from %s: %s" % (HERE, exc))
if isinstance(CAP, bool) or not isinstance(CAP, int) or CAP < 1 or CAP >= 90:
    sys.exit("fixture setup failed: the CI-wait cap is %r; the cases need a whole number from 1 to 89, "
             "so that 90 minutes is over it" % (CAP,))

CLOCK = datetime.fromisoformat(CAP_CLOCK)
OVER = CAP + 1
CI_MESSAGE = "CI run 4411 is still going"
# The remedy names the tool, the field and the cap the data file gives.
CAP_REMEDY = ("send_later", "delay_minutes", str(CAP))
# Full size: about 17,500 characters, with the CI word on the last line.
LONG_CI = "detail " * 2500 + "\nCI run 4411 is still going"


def cap_at(minutes):
    """An `at` text `minutes` after the fixed clock, in the clock's own offset."""
    return (CLOCK + timedelta(minutes=minutes)).isoformat()


def cap_at_z(minutes):
    """The instant cap_at names, written in UTC with a Z."""
    return (CLOCK + timedelta(minutes=minutes)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cap_case(name, expected, message, delay=None, at=None, guard=None, carries=(), lacks=()):
    """One send_later call from a session, with the clock fixed. A deny names the rule; an allow prints nothing."""
    fields = {"message": message}
    if delay is not None:
        fields["delay_minutes"] = delay
    if at is not None:
        fields["at"] = at
    add(name, expected, rule=CAP_RULE if expected == "deny" else None, tool=CAP_TOOL, cwd=NOGIT,
        env={"LOCAL_TIME_NOW": CAP_CLOCK}, guard=guard, silent=expected == "allow",
        carries=carries, lacks=lacks, **fields)


def ci_refuse(name, message):
    """A CI check-in of 90 minutes, which is over any cap the data file can hold."""
    cap_case(name, "deny", message, delay=90, carries=CAP_REMEDY)


# ---- Refused: a CI wait over the cap, by delay_minutes. The cap is CAP, and OVER is one minute past it.
cap_case("ci-wait-cap: a CI check-in one minute over the cap, %d minutes, is refused" % OVER, "deny",
         CI_MESSAGE, delay=OVER, carries=CAP_REMEDY)
cap_case("ci-wait-cap: a CI check-in of 90 minutes is refused", "deny", CI_MESSAGE, delay=90, carries=CAP_REMEDY)

# ---- Refused: each CI form the reading names, at 90 minutes.
ci_refuse("ci-wait-cap: a 90-minute check-in that waits on the checks is refused", "Waiting on the checks for PR 2839")
ci_refuse("ci-wait-cap: a 90-minute check-in on a PR run is refused", "PR run for the draft is still red")
ci_refuse("ci-wait-cap: a 90-minute check-in on a workflow run is refused", "workflow run 4411 is still going")
ci_refuse("ci-wait-cap: a 90-minute check-in with CI in lower case is refused", "ci run 4411 is still going")
# Scanner insurance: a lone quote and comment openers are plain text in a message, so each still counts.
ci_refuse("ci-wait-cap: a CI word beside a lone quote is refused", "CI run isn't done yet")
ci_refuse("ci-wait-cap: a CI word beside comment openers in text is refused", "CI run // still going /* ok */")
ci_refuse("ci-wait-cap: a CI word on the second line is refused: the whole message is read",
          "Check-in on PR 2839.\nCI still running")
ci_refuse("ci-wait-cap: a full-size message with the CI word last is refused", LONG_CI)

# ---- Refused: a CI wait over the cap, by an `at` time. The offset form and the Z form name the same instant.
cap_case("ci-wait-cap: a CI check-in at a time one minute over the cap, offset form, is refused", "deny",
         CI_MESSAGE, at=cap_at(OVER), carries=CAP_REMEDY)
cap_case("ci-wait-cap: a CI check-in at a time one minute over the cap, Z form, is refused", "deny",
         CI_MESSAGE, at=cap_at_z(OVER), carries=CAP_REMEDY)
cap_case("ci-wait-cap: a CI check-in at a time 90 minutes ahead is refused", "deny",
         CI_MESSAGE, at=cap_at(90), carries=CAP_REMEDY)

# ---- Allowed: a CI wait at or under the cap, by either field. These pass on the old code.
cap_case("ci-wait-cap: a CI check-in at the cap, %d minutes, is allowed: the limit is inclusive" % CAP, "allow",
         CI_MESSAGE, delay=CAP)
cap_case("ci-wait-cap: a short CI check-in of 5 minutes is allowed", "allow", CI_MESSAGE, delay=5)
cap_case("ci-wait-cap: a CI check-in at a time at the cap, offset form, is allowed", "allow",
         CI_MESSAGE, at=cap_at(CAP))
cap_case("ci-wait-cap: a CI check-in at a time at the cap, Z form, is allowed", "allow",
         CI_MESSAGE, at=cap_at_z(CAP))
cap_case("ci-wait-cap: a CI check-in at a time behind the clock is allowed", "allow",
         CI_MESSAGE, at=cap_at(-10))

# ---- Allowed: a call that is not about CI, at any delay. The words below hold a substring, a non-CI check, or nothing.
cap_case("ci-wait-cap: a 90-minute check-in that says check in with the owner is allowed", "allow",
         "Coordinator: pick 1 taken, check in with the owner", delay=90)
cap_case("ci-wait-cap: a 90-minute check-in with decision in it is allowed: a substring is not the word", "allow",
         "The decision record is updated", delay=90)
cap_case("ci-wait-cap: a 90-minute check-in with specific in it is allowed: a substring is not the word", "allow",
         "The specific pick is due at noon", delay=90)
cap_case("ci-wait-cap: a 500-minute check-in that is not about CI is allowed", "allow",
         "The owner's reply on the pick", delay=500)
cap_case("ci-wait-cap: a 1440-minute check-in that is not about CI is allowed", "allow",
         "The owner's reply on the pick", delay=1440)
cap_case("ci-wait-cap: an `at` time 180 minutes ahead that is not about CI is allowed", "allow",
         "The owner's reply on the pick", at=cap_at(180))
# The empty states: no message to read, and a CI message with no wait to measure.
cap_case("ci-wait-cap: an empty message at 90 minutes is allowed: there is no CI word", "allow", "", delay=90)
cap_case("ci-wait-cap: a CI check-in with neither delay_minutes nor at is allowed: there is no wait to measure",
         "allow", CI_MESSAGE)

# ---- The limit is read from the data file. Each copy below holds every hook module, and only its data file's cap
# differs. A literal in the rule would give the same answer for both copies, so each direction is pinned.
CAP_COPY_ROOT = os.path.join(ROOT, "ci-wait-cap")


def cap_copy_dir(cap):
    return os.path.join(CAP_COPY_ROOT, "cap-%d" % cap)


def build_cap_copy(cap):
    """A copy of every hook module, with the data file's cap set to `cap`. Built the first time a case names it."""
    def build():
        dest = cap_copy_dir(cap)
        mutate_shared.guard_tree(dest)  # every hook module beside the copied guard, as the guard finds its siblings
        with open(os.path.join(HERE, "ci_wait_cap.json"), encoding="utf-8") as handle:
            data = json.load(handle)
        data["cap_minutes"] = cap
        with open(os.path.join(dest, "ci_wait_cap.json"), "w", encoding="utf-8") as handle:
            json.dump(data, handle)
    build.__name__ = "build_ci_wait_cap_copy_%d" % cap
    return build


for _cap in (20, 90):
    lazy_fixture([cap_copy_dir(_cap)], build_cap_copy(_cap))

cap_case("ci-wait-cap: with the cap at 20, a CI check-in of 30 minutes is refused, and the reason names 20",
         "deny", CI_MESSAGE, delay=30, guard=os.path.join(cap_copy_dir(20), "guard.py"),
         carries=("send_later", "delay_minutes", "20"), lacks=(str(CAP),))
cap_case("ci-wait-cap: with the cap at 20, a CI check-in of 20 minutes is allowed: the limit is inclusive",
         "allow", CI_MESSAGE, delay=20, guard=os.path.join(cap_copy_dir(20), "guard.py"))
cap_case("ci-wait-cap: with the cap at 90, a CI check-in of 60 minutes is allowed, where a literal %d would refuse it"
         % CAP, "allow", CI_MESSAGE, delay=60, guard=os.path.join(cap_copy_dir(90), "guard.py"))

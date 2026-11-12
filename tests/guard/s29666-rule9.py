# section 29666
FAMILY = "rule9"  # the family the cases below had before this section

# ---- Lane effort pin. A lane session runs Sonnet at medium effort. A create_session that tags a lane
# names that effort in its `effort` field, and its prompt opens with the owner's grant: the first
# non-blank line is `Grant: <owner words>, <time>`, and the brief follows it. A prompt that is only
# the effort command is refused. Calls without the lane tag are not judged by this rule.
LANE_TOOL = "mcp__claude-code-remote__create_session"
# A lane call also tags the repo it works on (rule lane-repo-tag). Each lane case names its checkout by
# `cwd`, and carries the origin repo's tag, so this rule judges only the effort pin.
LANE_REPO = os.path.join(ROOT, "lanerepo")      # a checkout whose origin is claude-settings on GitHub
LANE_PROXY = os.path.join(ROOT, "laneproxy")    # the same repo, its origin behind the agent proxy's host
LANE_GIT = os.path.join(ROOT, "lanegit")        # the same repo, its origin with a `.git` suffix
LANE_LOCAL = os.path.join(ROOT, "lanelocal")    # the same repo, its origin a local path with no scheme
LANE_SCP = os.path.join(ROOT, "lanescp")        # the same repo, its origin in scp form
LANE_SSH = os.path.join(ROOT, "lanessh")        # the same repo, its origin an ssh URL with a port
LANE_ORIGINS = {
    LANE_REPO: "https://github.com/shivinate7/claude-settings",
    LANE_PROXY: "http://local_proxy@127.0.0.1:1234/git/shivinate7/claude-settings",
    LANE_GIT: "https://github.com/shivinate7/claude-settings.git",
    LANE_LOCAL: "/srv/repos/shivinate7/claude-settings.git",
    LANE_SCP: "git@github.com:shivinate7/claude-settings.git",
    LANE_SSH: "ssh://git@github.com:22/shivinate7/claude-settings",
}
# The container's global git config rewrites an scp origin to https, through GIT_CONFIG_* in the environment.
# A case that pins the scp parse arm clears those variables for its own guard run, so the raw origin is read.
RAW_ORIGIN_ENV = {name: None for name in os.environ if name.startswith("GIT_CONFIG_")}
OWN_LANE_TAGS = ["cs-build:lane", "cs-repo:shivinate7/claude-settings"]
# A lane call names the model it starts on and the repo it starts from. Each allow case below carries both.
LANE_SOURCE_URL = "https://github.com/shivinate7/claude-settings"
# The lane start's prompt: the owner's grant as its first non-blank line, then the brief. The lane's effort is
# the `effort` field. Every lane case below carries both, so a case that expects another rule names only its own cause.
LANE_GRANT = "Grant: B is good, 13:19 CST Nov 10"
LANE_PROMPT = LANE_GRANT + "\nDo the task in the brief file."
LANE_EFFORT_FIELD = "medium"


def _build_origins(origins):
    """Real checkouts, each with the origin `origins` names. A case names one by `cwd`."""
    for where, url in origins.items():
        make_repo(where, {"README.md": "# r\n"})
        added = run_vcs(where, "remote", "add", "origin", url)
        if added.returncode != 0:
            sys.exit("fixture setup failed in build_fixtures: `remote add origin` failed in %r. stderr: %s"
                     % (where, added.stderr.strip()))


def _build_lane_origins():
    """Three real checkouts, each with the origin LANE_ORIGINS names. A lane case names one by `cwd`."""
    _build_origins(LANE_ORIGINS)


lazy_fixture(list(LANE_ORIGINS), _build_lane_origins)
add("lane-effort-pin: lane tag with a grant line first and effort medium is allowed", "allow",
    tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-effort-pin: lane tag with blank lines before the grant line is allowed", "allow",
    tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS, prompt="\n  \n" + LANE_PROMPT,
    effort=LANE_EFFORT_FIELD, model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-effort-pin: lane tag with the effort command alone is denied, even at effort medium", "deny",
    "lane-effort-pin", tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS, prompt="/effort medium",
    effort=LANE_EFFORT_FIELD, model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-effort-pin: lane tag with a grant line that is not first is denied", "deny",
    "lane-effort-pin", tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS,
    prompt="Do the task in the brief file.\n" + LANE_GRANT, effort=LANE_EFFORT_FIELD,
    carries="Grant", model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-effort-pin: lane tag with a brief after the effort command is denied", "deny",
    "lane-effort-pin", tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS, prompt="/effort medium\nbrief",
    effort=LANE_EFFORT_FIELD, carries="Grant")
add("lane-effort-pin: lane tag with a prompt that is not the effort command is denied", "deny",
    "lane-effort-pin", tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS, prompt="do the task")
add("lane-effort-pin: lane tag with /effort high is denied", "deny",
    "lane-effort-pin", tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS, prompt="/effort high")
add("lane-effort-pin: lane tag with no prompt is denied", "deny", "lane-effort-pin",
    tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS)
# The refusal of a missing or other effort names the field, and never the old two-step start (the effort
# command, then the brief by send_message), which the owner disowned.
add("lane-effort-pin: lane tag with no effort field is denied, even with the grant line first", "deny",
    "lane-effort-pin", tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS, prompt=LANE_PROMPT,
    lacks="send_message", model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-effort-pin: lane tag with effort high is denied, even with the grant line first", "deny",
    "lane-effort-pin", tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS, prompt=LANE_PROMPT,
    effort="high", lacks="send_message", model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-effort-pin: lane tag with the effort command padded by space and a newline, and no grant, is denied",
    "deny", "lane-effort-pin", tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS, prompt="  /effort medium\n",
    effort=LANE_EFFORT_FIELD, carries="Grant")
add("lane-effort-pin: lane tag with the effort command and a trailing newline, and no grant, is denied", "deny",
    "lane-effort-pin", tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS, prompt="/effort medium\n",
    effort=LANE_EFFORT_FIELD, carries="Grant")
add("lane-effort-pin: lane tag with a trailing space and a wrong prompt is denied", "deny",
    "lane-effort-pin", tool=LANE_TOOL, cwd=LANE_REPO,
    tags=["cs-build:lane ", "cs-repo:shivinate7/claude-settings"], prompt="do the task")
add("lane-effort-pin: upper-case lane tag with a wrong prompt is denied", "deny",
    "lane-effort-pin", tool=LANE_TOOL, cwd=LANE_REPO,
    tags=["CS-BUILD:LANE", "cs-repo:shivinate7/claude-settings"], prompt="do the task")
add("lane-effort-pin: lane tag given as a string with a wrong prompt is denied", "deny",
    "lane-effort-pin", tool=LANE_TOOL, cwd=LANE_REPO, tags="cs-build:lane", prompt="do the task")
add("lane-effort-pin: triage tag with any prompt is allowed", "allow",
    tool=LANE_TOOL, tags=["cs-build:triage"], prompt="do the task")
add("lane-effort-pin: a create_session with no lane tag passes unchanged, with the effort command alone", "allow",
    tool=LANE_TOOL, tags=["cs-build:triage"], prompt="/effort medium")
add("lane-effort-pin: create_session with no tags is allowed", "allow",
    tool=LANE_TOOL, prompt="do the task")
# Grant start. The owner ruled ("B is good"): a lane starts with the effort field at
# medium and its whole brief as the prompt, opening with the Grant line. The brief's Topic must match the lane's cs-topic tag
# at create_session, as it must at send_message (rule lane-one-topic). A Grant line with no owner words is no grant: a
# template placeholder, or punctuation alone, is refused.
add("lane-one-topic: lane tag with cs-topic alpha and a brief for topic colors is denied", "deny",
    "lane-one-topic", tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS + ["cs-topic:alpha"],
    prompt=LANE_GRANT + "\nLane brief: icon-a. Topic: colors.", effort=LANE_EFFORT_FIELD,
    model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-one-topic: lane tag with cs-topic alpha and a brief for topic alpha is allowed", "allow",
    tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS + ["cs-topic:alpha"],
    prompt=LANE_GRANT + "\nLane brief: icon-a. Topic: alpha.", effort=LANE_EFFORT_FIELD,
    model="sonnet", source_url=LANE_SOURCE_URL)
# A start's brief marker must sit on the first line after the Grant line. A marker past a preamble line is read by
# no one, so this start names topic colors on a lane of topic alpha and passes. The marker-first starts above are
# its controls: topic alpha is allowed and topic colors is denied.
add("lane-one-topic: lane tag with cs-topic alpha and a marker past a preamble line, for topic colors, is denied",
    "deny", "lane-one-topic", tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS + ["cs-topic:alpha"],
    prompt=LANE_GRANT + "\nRead the brief file first.\nLane brief: icon-a. Topic: colors.", effort=LANE_EFFORT_FIELD,
    model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-effort-pin: lane tag with a grant line that holds a template placeholder is denied", "deny",
    "lane-effort-pin", tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS,
    prompt="Grant: <owner words>, <time>\nDo the task in the brief file.", effort=LANE_EFFORT_FIELD,
    model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-effort-pin: lane tag with a grant line that is only a comma is denied", "deny",
    "lane-effort-pin", tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS,
    prompt="Grant: ,\nDo the task in the brief file.", effort=LANE_EFFORT_FIELD,
    model="sonnet", source_url=LANE_SOURCE_URL)
# A start that carries only the lane tag names no cs-topic or cs-step tag to judge its brief by. Its refusal names
# the missing tag. It must not steer to create_session, because this call is the start.
add("lane-one-topic: a create_session start with only the lane tag is denied, and its reason names the missing tag",
    "deny", "lane-one-topic", tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS,
    prompt=LANE_GRANT + "\nLane brief: icon-a. Topic: alpha.", effort=LANE_EFFORT_FIELD,
    model="sonnet", source_url=LANE_SOURCE_URL,
    carries=(("cs-topic", "cs-step"),), lacks="start one with create_session")

# ---- Lane repo tag. A lane call tags the repo it works on: `cs-repo:<owner>/<name>`, equal (casefolded) to
# the calling checkout's origin repo. The origin repo is the last two segments of the origin's PATH, `.git`
# stripped; the host is never read, so the proxy's URL names the same repo. A lane call with no such tag is
# denied, whatever its other tags. Each case names its checkout by `cwd`, never the runner's own checkout.
# The proxy and `.git` origins each pair an allow with a deny for another repo, so a rule that fails open
# on an origin it cannot parse turns a case red.
add("lane-repo-tag: lane tag with no repo tag is denied", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=["cs-build:lane"])
add("lane-repo-tag: lane tag with the short repo form is denied", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=["cs-build:lane", "cs-repo:claude-settings"])
add("lane-repo-tag: lane tag with only another repo's tag is denied", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=["cs-build:lane", "cs-repo:shivinate7/q_max"])
add("lane-repo-tag: lane tag given as a string with no repo tag is denied", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags="cs-build:lane")
add("lane-repo-tag: origin repo tag is allowed", "allow",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", "cs-repo:shivinate7/claude-settings"], model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-repo-tag: origin repo tag in other case is allowed", "allow",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", "cs-repo:Shivinate7/Claude-Settings"], model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-repo-tag: roll-out lane with its target repo and the origin repo tag is allowed", "allow",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", "cs-repo:shivinate7/q_max", "cs-repo:shivinate7/claude-settings"],
    model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-repo-tag: non-lane call with no repo tag is allowed", "allow",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=["cs-build:triage"])
add("lane-repo-tag: proxy-host origin, origin repo tag is allowed", "allow",
    tool=LANE_TOOL, cwd=LANE_PROXY, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", "cs-repo:shivinate7/claude-settings"], model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-repo-tag: proxy-host origin, another repo's tag is denied", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=LANE_PROXY, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", "cs-repo:shivinate7/q_max"])
add("lane-repo-tag: origin with a .git suffix, origin repo tag is allowed", "allow",
    tool=LANE_TOOL, cwd=LANE_GIT, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", "cs-repo:shivinate7/claude-settings"], model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-repo-tag: origin with a .git suffix, another repo's tag is denied", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=LANE_GIT, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", "cs-repo:shivinate7/q_max"])

# No readable origin: a git checkout with no origin remote, and a folder that is no checkout at all (NOGIT).
# With no origin to compare to, a full `cs-repo:<owner>/<name>` tag passes; the short form and no repo tag
# are denied. Three cases per checkout: the full tag, the short form, and no repo tag.
LANE_NO_ORIGIN = os.path.join(ROOT, "lanenoorigin")  # a git checkout with no origin remote


def _build_lane_no_origin():
    """A real checkout that holds no `origin` remote. A lane case names it by `cwd`."""
    make_repo(LANE_NO_ORIGIN, {"README.md": "# r\n"})


lazy_fixture([LANE_NO_ORIGIN], _build_lane_no_origin)
add("lane-repo-tag: a checkout with no origin, full repo tag is allowed", "allow",
    tool=LANE_TOOL, cwd=LANE_NO_ORIGIN, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", "cs-repo:shivinate7/claude-settings"], model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-repo-tag: a checkout with no origin, short repo form is denied", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=LANE_NO_ORIGIN, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=["cs-build:lane", "cs-repo:claude-settings"])
add("lane-repo-tag: a checkout with no origin, no repo tag is denied", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=LANE_NO_ORIGIN, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=["cs-build:lane"])
add("lane-repo-tag: a folder that is not a checkout, full repo tag is allowed", "allow",
    tool=LANE_TOOL, cwd=NOGIT, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", "cs-repo:shivinate7/claude-settings"], model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-repo-tag: a folder that is not a checkout, short repo form is denied", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=NOGIT, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=["cs-build:lane", "cs-repo:claude-settings"])
add("lane-repo-tag: a folder that is not a checkout, no repo tag is denied", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=NOGIT, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=["cs-build:lane"])

# Strict tag reading, the one the roadmap uses (repo_tag_names): the exact prefix, no strip, owner/name
# without case. A stray space or an upper-case prefix names no repo, so it is denied, even the origin's own.
add("lane-repo-tag: origin repo tag with a trailing space is denied", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", "cs-repo:shivinate7/claude-settings "])
add("lane-repo-tag: origin repo tag with a leading space is denied", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", " cs-repo:shivinate7/claude-settings"])
add("lane-repo-tag: origin repo tag with an upper-case prefix is denied", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", "CS-REPO:shivinate7/claude-settings"])
add("lane-repo-tag: origin repo tag with a trailing space is denied, from a checkout with no origin", "deny",
    "lane-repo-tag", tool=LANE_TOOL, cwd=LANE_NO_ORIGIN, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", "cs-repo:shivinate7/claude-settings "])

# A local-path origin, with no scheme, names its repo by the path itself. Its own tag passes; another's does not.
add("lane-repo-tag: a local-path origin, origin repo tag is allowed", "allow",
    tool=LANE_TOOL, cwd=LANE_LOCAL, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", "cs-repo:shivinate7/claude-settings"], model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-repo-tag: a local-path origin, another repo's tag is denied", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=LANE_LOCAL, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", "cs-repo:shivinate7/q_max"])

# The origin forms that the parse arms read. Each pins its arm with the raw origin: see RAW_ORIGIN_ENV.
add("lane-repo-tag: an scp origin, origin repo tag is allowed", "allow",
    tool=LANE_TOOL, cwd=LANE_SCP, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, env=RAW_ORIGIN_ENV,
    tags=["cs-build:lane", "cs-repo:shivinate7/claude-settings"], model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-repo-tag: an scp origin, another repo's tag is denied", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=LANE_SCP, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, env=RAW_ORIGIN_ENV,
    tags=["cs-build:lane", "cs-repo:shivinate7/q_max"])
add("lane-repo-tag: an ssh origin with a port, origin repo tag is allowed", "allow",
    tool=LANE_TOOL, cwd=LANE_SSH, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, env=RAW_ORIGIN_ENV,
    tags=["cs-build:lane", "cs-repo:shivinate7/claude-settings"], model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-repo-tag: an ssh origin with a port, another repo's tag is denied", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=LANE_SSH, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, env=RAW_ORIGIN_ENV,
    tags=["cs-build:lane", "cs-repo:shivinate7/q_max"])

# An extras file names the GitHub repo: the roadmap reads its "roadmap" object's "github" first (skills/roadmap/build.py
# extras() and github_slug()), so that name wins over the origin's path. The origin here is not a GitHub URL.
LANE_EXTRAS = os.path.join(ROOT, "laneextras")  # a non-GitHub origin, and an extras file that names org/name


def _build_lane_extras():
    """A real checkout whose extras file names org/name, with a non-GitHub origin. A lane case names it by `cwd`."""
    make_repo(LANE_EXTRAS, {"README.md": "# r\n",
                            ".claude/layout-extras.json": json.dumps({"roadmap": {"github": "org/name"}}) + "\n"})
    added = run_vcs(LANE_EXTRAS, "remote", "add", "origin", "https://git.example.com/x/y")
    if added.returncode != 0:
        sys.exit("fixture setup failed in build_fixtures: `remote add origin` failed in %r. stderr: %s"
                 % (LANE_EXTRAS, added.stderr.strip()))


lazy_fixture([LANE_EXTRAS], _build_lane_extras)
add("lane-repo-tag: an extras file names the GitHub repo, its tag is allowed", "allow",
    tool=LANE_TOOL, cwd=LANE_EXTRAS, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", "cs-repo:org/name"], model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-repo-tag: an extras file names the GitHub repo, the origin's path is no repo tag", "deny",
    "lane-repo-tag", tool=LANE_TOOL, cwd=LANE_EXTRAS, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-build:lane", "cs-repo:x/y"])

# A denial names the tag the call must carry, so the agent can add it.
add("lane-repo-tag: a denied lane names the expected repo tag in its reason", "deny", "lane-repo-tag",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=["cs-build:lane"],
    carries="cs-repo:shivinate7/claude-settings")


# =========================================================================== 5h. the merge target's checkout
#
# Rule merge-confirm-repo (REPO_RULE). A cloud session's `merge <pr> --confirm` runs in the checkout the command names: the value of
# -C or --repo-dir (either spelling, glued or not, anywhere in the command, the last one wins), else the `cd X &&` directory, else the
# working directory. The guard reads that checkout's repo and allows the merge only when a tag of the own newest get_session record
# names the same cs-repo repo. A flag value that cannot be read, and a record that cannot be read, are denied. Outside the cloud, and
# --lane-lint (which merges nothing), are not judged.

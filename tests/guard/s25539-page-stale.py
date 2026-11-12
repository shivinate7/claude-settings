# section 25539
FAMILY = "page-stale"
#
# Rule page-stale (hooks/guard.py, the Artifact tool). A republish of this repo's waiting page is refused
# when its file is behind main's skills/waiting-page/page.html, and when it is main's own page (main's title)
# with designData and roadmap blocks that read as empty, white space aside, which would drop the page's live
# data. A page with its own title was built by --write from a live page, so its empty blocks drop nothing and
# it is allowed. A first publish, with no url, is never refused. Main is origin/main of the checkout that holds stale_pages.py, so each case runs a copy
# of the guard in a checkout whose origin/main this suite controls (WP_CHECK), never the real main. The
# copy finds stale_pages beside itself, as the guard does. An allowed publish writes main's full blob sha
# to <git common dir>/waiting-page-built. Unknown, when main or the file cannot be read, allows: the rule
# fails open.

WP_DIR = os.path.join(ROOT, "pagestale")
WP_CHECK = os.path.join(WP_DIR, "checkout")        # origin/main is its one commit: main's page.html
WP_NOMAIN = os.path.join(WP_DIR, "nomain")         # the same files, with no origin/main ref
WP_GUARD = os.path.join(WP_CHECK, "hooks", "guard.py")
WP_GUARD_NOMAIN = os.path.join(WP_NOMAIN, "hooks", "guard.py")
WP_CURRENT = os.path.join(WP_DIR, "current.html")  # main's page.html, byte for byte
WP_BEHIND = os.path.join(WP_DIR, "behind.html")    # main's page with one div after its style block
WP_WRITER = os.path.join(WP_DIR, "writer.html")    # main's page with the writer's designData, roadmap and title text
WP_DESIGN_LIVE = os.path.join(WP_DIR, "design-live.html")    # main's page with only the designData block live
WP_ROADMAP_LIVE = os.path.join(WP_DIR, "roadmap-live.html")  # main's page with only the roadmap block live
WP_TITLED_EMPTY = os.path.join(WP_DIR, "titled-empty.html")  # main's page with its own title and both blocks empty
WP_QUEUE_EMPTY = os.path.join(WP_DIR, "queue-empty.html")    # main's page titled with the old name Queue, both blocks empty
WP_SPACED = os.path.join(WP_DIR, "spaced-empty.html")        # main's raw page with designData written as "{ }"
WP_SOURCE = os.path.join(REPO, "skills", "waiting-page", "page.html")  # read at run time, not a fixed text
WP_STAMP = "waiting-page-built"
WP_OTHER_URL = "https://claude.ai/artifact/wpother"
WP_DESIGN = re.compile(r'(<script type="application/json" id="designData">).*?(</script>)', re.S)
WP_ROADMAP = re.compile(r"<!-- roadmap:data -->.*?<!-- /roadmap:data -->", re.S)
WP_TITLE = re.compile(r"<title>[^<]*</title>")
# The writer's parts hold comment openers, a lone quote and a multi-line template literal. The page
# text must still match main, because the designData body, the roadmap body and the title text are
# the parts a writer's --write leaves live.
WP_WRITER_DESIGN = '{"a": "\\u003cp>mock\\u003c/p>", "note": "a // b /* c don\'t"}'
WP_WRITER_ROADMAP = ("<!-- roadmap:data -->\n"
                     '<script>window.ROADMAP_DATA = {"steps": {"c1": {"note": "x // y /* z don\'t"}}};\n'
                     "const sample = `first line\nsecond // line`;\n"
                     'window.ROADMAP_BUILD = {"repo": "r"};</script>\n'
                     "<!-- /roadmap:data -->")


def wp_must(ok, why):
    """Stop the run unless a fixture step held. A fixture that did not build proves nothing."""
    if not ok:
        sys.exit("fixture setup failed in build_page_checkout: %s" % why)


def wp_writer(template, design=True, roadmap=True, title=True, design_text=WP_WRITER_DESIGN,
              title_text="Queue, renamed // not a comment"):
    """main's page with the parts a writer's --write keeps live swapped for new text, each part only when
    its flag is set. Each part must match exactly once in main's page."""
    def swap(pattern, text, repl):
        wp_must(len(pattern.findall(text)) == 1, "%s does not match once in main's page" % pattern.pattern[:40])
        return pattern.sub(repl, text, count=1)
    text = template
    if design:
        text = swap(WP_DESIGN, text, lambda m: m.group(1) + design_text + m.group(2))
    if roadmap:
        text = swap(WP_ROADMAP, text, lambda m: WP_WRITER_ROADMAP)
    if title:
        text = swap(WP_TITLE, text, lambda m: "<title>%s</title>" % title_text)
    return text


def wp_put(path, text):
    """Write `text` to `path` byte for byte, so a page keeps its line endings."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def wp_write_pages():
    """The three page files, built from main's page.html as this repository holds it now."""
    with open(WP_SOURCE, encoding="utf-8", newline="") as handle:
        template = handle.read()
    wp_must(template.count("</style>") == 1, "main's page has no single style block to add a div after")
    behind = template.replace("</style>", "</style>\n<div>x</div>", 1)
    pages = ((WP_CURRENT, template), (WP_BEHIND, behind), (WP_WRITER, wp_writer(template)),
             (WP_DESIGN_LIVE, wp_writer(template, roadmap=False, title=False)),
             (WP_ROADMAP_LIVE, wp_writer(template, design=False, title=False)),
             (WP_TITLED_EMPTY, wp_writer(template, design=False, roadmap=False, title_text="claude-settings Cockpit")),
             (WP_QUEUE_EMPTY, wp_writer(template, design=False, roadmap=False, title_text="Queue")),
             (WP_SPACED, wp_writer(template, roadmap=False, title=False, design_text="{ }")))
    for path, text in pages:
        wp_put(path, text)


def wp_git(where, *args):
    """One git call in a fixture checkout. A call that fails stops the run."""
    answer = run_vcs(where, *args)
    wp_must(answer.returncode == 0, "git %s in %r: %s" % (" ".join(args), where, answer.stderr.strip()))
    return answer


def wp_populate(folder):
    """The copy's files: the guard family, the layout lint reads, and the skill's scripts and page as this
    repository holds them. The copy's guard finds stale_pages.py beside its own folder."""
    os.makedirs(os.path.join(folder, "hooks"), exist_ok=True)
    copy_guard_family(os.path.join(folder, "hooks"))
    for rel in ("lint/layout.py", "lint/layout.json", "skills/waiting-page/stale_pages.py",
                "skills/waiting-page/splice.py", "skills/waiting-page/page.html"):
        dest = os.path.join(folder, *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy(os.path.join(REPO, *rel.split("/")), dest)
    wp_put(os.path.join(folder, ".claude", "layout-extras.json"),
             json.dumps({"kinds": {}, "waiting-page": PQ_URL}))


def wp_commit(folder, main):
    wp_git(folder, "init", "-q")
    wp_git(folder, "add", "-A")
    wp_git(folder, *IDENT, "commit", "-q", "-m", "fixture: main")
    if main:
        wp_git(folder, "update-ref", "refs/remotes/origin/main", "HEAD")


def wp_control(folder, main):
    """The copy's own stale_pages.py gives the verdicts the cases assume: main's page, the behind page and
    the writer's page against a controlled main, or unknown with no main. A miss stops the run."""
    script = os.path.join(folder, "skills", "waiting-page", "stale_pages.py")
    wants = ([(WP_CURRENT, 0), (WP_BEHIND, 1), (WP_WRITER, 0), (WP_DESIGN_LIVE, 0), (WP_ROADMAP_LIVE, 0),
              (WP_TITLED_EMPTY, 0), (WP_SPACED, 0)] if main else [(WP_CURRENT, 2)])
    for page, code in wants:
        run = subprocess.run([sys.executable, script, "--page", page], capture_output=True, text=True,
                             cwd=folder, timeout=120)
        named = ("origin/main" if main else "unknown") in run.stdout
        wp_must(run.returncode == code and named,
                "stale_pages in %r exits %d for %s, want %d: %s"
                % (folder, run.returncode, os.path.basename(page), code, (run.stdout + run.stderr).strip()[:200]))


def build_page_checkout():
    """The checkout whose origin/main is main's page.html: a copy of the guard and what stale_pages reads,
    committed, with origin/main at that commit. Then the page files, and a control that the copy reads it."""
    wp_populate(WP_CHECK)
    wp_commit(WP_CHECK, main=True)
    wp_write_pages()
    wp_control(WP_CHECK, main=True)


def build_page_nomain():
    """The same copy with no origin/main ref: main cannot be read, so every publish is unknown and allowed."""
    wp_populate(WP_NOMAIN)
    wp_commit(WP_NOMAIN, main=False)
    wp_write_pages()
    wp_control(WP_NOMAIN, main=False)


lazy_fixture([WP_GUARD, WP_CURRENT, WP_BEHIND, WP_WRITER, WP_DESIGN_LIVE, WP_ROADMAP_LIVE, WP_TITLED_EMPTY,
              WP_QUEUE_EMPTY, WP_SPACED], build_page_checkout)
lazy_fixture([WP_GUARD_NOMAIN], build_page_nomain)


def wp_publish(name, expected, page, rule=None, guard=None, url=PQ_URL, **extra):
    """One Artifact publish of `page`, judged by a copy of the guard in the controlled checkout. A url of
    None is a first publish: the call carries no url key at all."""
    if url is not None:
        extra["url"] = url
    add("page-stale: " + name, expected, rule, tool="Artifact", cwd=PQ_REPO, guard=guard or WP_GUARD,
        file_path=page, **extra)


wp_publish("a behind page with no action is refused", "deny", WP_BEHIND, rule="page-stale")
wp_publish("a behind page with action publish is refused", "deny", WP_BEHIND, rule="page-stale",
           action="publish")
wp_publish("a behind page published to the code form of the waiting page is refused", "deny", WP_BEHIND,
           rule="page-stale", url="https://claude.ai/code/artifact/pqpage")
wp_publish("a behind page published to another artifact's code form is allowed", "allow", WP_BEHIND,
           url="https://claude.ai/code/artifact/wpother")
wp_publish("main's page republished to the waiting page is refused: its designData and roadmap are empty",
           "deny", WP_CURRENT, rule="page-stale")
wp_publish("main's page republished to the code form of the waiting page is refused", "deny", WP_CURRENT,
           rule="page-stale", url="https://claude.ai/code/artifact/pqpage")
wp_publish("main's page with designData written as a space-padded empty object is refused", "deny", WP_SPACED,
           rule="page-stale")
wp_publish("main's page as a first publish, with no url, is allowed", "allow", WP_CURRENT, url=None)
wp_publish("a page with its own title and empty blocks, as a --write builds it, is allowed", "allow", WP_TITLED_EMPTY)
# Main's page with the old title and both blocks empty: its text matches main, so only its title differs. The
# title text alone must not count as data, or the empty page passes the rule main applies to its own page.
wp_publish("an untouched page titled Queue with empty blocks is refused, as main's page is", "deny", WP_QUEUE_EMPTY,
           rule="page-stale")
wp_publish("a page with live designData and an empty roadmap is allowed", "allow", WP_DESIGN_LIVE)
wp_publish("a page with an empty designData and a live roadmap is allowed", "allow", WP_ROADMAP_LIVE)
wp_publish("a page the writer's --write builds is allowed", "allow", WP_WRITER)
wp_publish("a behind page published to another url is allowed", "allow", WP_BEHIND, url=WP_OTHER_URL)
wp_publish("a read of the waiting page with a behind file is allowed", "allow", WP_BEHIND, action="read")
wp_publish("a behind file uploaded as an asset is allowed", "allow", WP_BEHIND, asset=True)
wp_publish("a file that cannot be read fails open", "allow", os.path.join(WP_DIR, "missing.html"))
wp_publish("a behind page is allowed when main cannot be read", "allow", WP_BEHIND, guard=WP_GUARD_NOMAIN)


def wp_publish_run(file_path, cwd=WP_CHECK, url=PQ_URL):
    """One Artifact publish of `file_path` to `url`, judged by the copy of the guard in the controlled checkout.
    Returns the printed stdout, empty when the guard allowed the call."""
    env = dict(os.environ, CLAUDE_CONFIG_DIR=CFG, CLAUDE_GUARD_ROOT_PID=str(os.getpid()))
    env.pop("CLAUDE_CODE_REMOTE", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
    run = subprocess.run([sys.executable, WP_GUARD],
                         input=json.dumps({"tool_name": "Artifact", "cwd": cwd,
                                           "tool_input": {"url": url, "file_path": file_path}}),
                         capture_output=True, text=True, env=env, timeout=120)
    return run.stdout.strip()


def wp_stamp_case():
    """An allowed publish of a page with live data writes main's blob sha to <git common dir>/waiting-page-built."""
    materialize(WP_GUARD)  # builds the one copy this check runs, not every lazy fixture
    stamp = os.path.join(WP_CHECK, ".git", WP_STAMP)
    if os.path.exists(stamp):
        os.remove(stamp)
    out = wp_publish_run(WP_WRITER)
    if out:
        return False, "the publish of a page with live data was refused: %r" % out[:100]
    if not os.path.isfile(stamp):
        return False, "no stamp was written at <git common dir>/%s" % WP_STAMP
    with open(stamp, encoding="utf-8") as handle:
        got = handle.read().strip()
    want = wp_git(WP_CHECK, "rev-parse", "origin/main:skills/waiting-page/page.html").stdout.strip()
    if got != want:
        return False, "the stamp holds %r, want main's page blob %s" % (got[:40], want)
    return True, "an allowed publish writes main's page blob sha"


FIXTURELESS_CHECKS.add(wp_stamp_case)  # builds only the copy it runs, so a family run does not build every fixture
LOG_CHECKS_EXTRA.append(("page-stale: an allowed publish of a page with live data writes the stamp", wp_stamp_case))


def page_empty_reason_names_the_page_case():
    """The remedy PAGE_EMPTY_REASON gives names the page "<repo> <page name>", the name in skills/waiting-page/splice.py
    The old "<repo> Queue" is checked first, so a failure names the old text, not a missing name."""
    guard = _load_guard_module()
    reason = guard.PAGE_EMPTY_REASON
    if "<repo> Queue" in reason:
        return False, "PAGE_EMPTY_REASON still tells the writer to title the page \"<repo> Queue\""
    with open(os.path.join(REPO, "skills", "waiting-page", "splice.py"), encoding="utf-8") as handle:
        found = re.search(r'^PAGE_NAME = "([^"]*)"', handle.read(), re.M)
    if not found:
        return False, "skills/waiting-page/splice.py has no PAGE_NAME line"
    want = "<repo> " + found.group(1)
    if want not in reason:
        return False, "PAGE_EMPTY_REASON does not name the page %r" % want
    return True, "PAGE_EMPTY_REASON names the page %r" % want


FIXTURELESS_CHECKS.add(page_empty_reason_names_the_page_case)  # loads the guard and reads one file, builds no fixture
LOG_CHECKS_EXTRA.append(("page-stale: the empty-page remedy names the page <repo> and the page name",
                         page_empty_reason_names_the_page_case))


# --------------------------------------------------------------------------- a design picture is checked at write
#
# Rule page-item-design (decision page-item-design). An ArtifactData set or update of a waiting item
# whose data carries `designs` or an option with `design` runs skills/waiting-page/check_designs.mjs against the
# published file stamped at <git common dir>/waiting-page-published. A miss denies, with the page's own
# sentence. Unknown (no stamp, the file gone, exit 3) allows and logs one `noted` line. A write with no designs
# never runs the checker: `_run_check_designs` is the seam, and the seam's call count is what the case reads.
# Each case gets a checkout and a config folder of its own, so no case reads another case's stamp.

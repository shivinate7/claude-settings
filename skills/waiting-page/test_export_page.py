"""Fixture suite for export_page.py. Run: python3 skills/waiting-page/test_export_page.py

EXPORT_PAGE_UNDER_TEST names the script to run (default: export_page.py beside this file), so the same
cases run red against a checkout that lacks it.

Secret-shaped values are joined at run time from parts. No token-shaped literal sits in this source, so a
secret scanner that reads the committed text finds none.
"""
import collections
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CMD = os.environ.get("EXPORT_PAGE_UNDER_TEST") or os.path.join(HERE, "export_page.py")
LINT = os.path.realpath(os.path.join(HERE, "..", "..", "lint"))
sys.path.insert(0, LINT)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

COLLECTIONS = ("items", "answers", "groups", "asks", "meta")
ARTIFACT = "https://claude.ai/artifact/RddcgXbB6SvTrFZHPmsvFx"
SENTINEL = 1000000000  # a fixed mtime for a file a run must not rewrite; no clock is read
TAIL = "aB3" * 12  # 36 characters, the body of a GitHub token
DESIGN = re.compile(r'(<script type="application/json" id="designData">)(.*?)(</script>)', re.S)
DESIGN_BODY = '{"a": "\\u003cp>mockup\\u003c/p>", "b": "<i>raw</i>"}'
META = {"title": "Queue", "version": 1}
RUN_FOLDER = None  # made in setUpModule

with open(os.path.join(HERE, "page.html"), encoding="utf-8") as f:
    PAGE = f.read()
assert len(DESIGN.findall(PAGE)) == 1, "page.html must hold one designData block: the fixture's shape"
DESIGN_ELEMENT = DESIGN.search(PAGE).group(0)

# (label, the note's value, the text that must never be printed). A dict or a list nests the secret.
RED = [
    ("GitHub token", "ghp_" + TAIL, "ghp_" + TAIL),
    ("GitHub OAuth token", "gho_" + TAIL, "gho_" + TAIL),
    ("GitHub user token", "ghu_" + TAIL, "ghu_" + TAIL),
    ("GitHub server token", "ghs_" + TAIL, "ghs_" + TAIL),
    ("GitHub refresh token", "ghr_" + TAIL, "ghr_" + TAIL),
    ("GitHub fine-grained token", "github_pat_" + "aB3" * 8, "github_pat_" + "aB3" * 8),
    ("Anthropic key", "sk-ant-" + "aB3" * 12, "sk-ant-" + "aB3" * 12),
    ("OpenAI-style key", "sk-proj-" + "aB3" * 10, "sk-proj-" + "aB3" * 10),
    ("AWS key id", "AKIA" + "ABCDEFGHIJKLMNOP", "AKIA" + "ABCDEFGHIJKLMNOP"),
    ("Slack token", "xoxb-" + "123456789012-abcdefABCDEF", "xoxb-" + "123456789012-abcdefABCDEF"),
    ("PEM private key header", "-----BEGIN " + "RSA " + "PRIVATE KEY-----", "-----BEGIN " + "RSA " + "PRIVATE KEY-----"),
    ("PEM OpenSSH key header", "-----BEGIN " + "OPENSSH " + "PRIVATE KEY-----", "-----BEGIN " + "OPENSSH " + "PRIVATE KEY-----"),
    ("JWT", "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiJ1c3IifQ" + "." + "c2lnbmF0dXJl",
     "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiJ1c3IifQ" + "." + "c2lnbmF0dXJl"),
    ("Authorization Bearer header", "Authorization: Bearer " + "xq7Lp2Vw9Rt4Ys8Zn1Mh", "xq7Lp2Vw9Rt4Ys8Zn1Mh"),
    ("Authorization Basic header", "Authorization: Basic " + "dXNlcjpwYXNz", "dXNlcjpwYXNz"),
    ("Cookie header", "Cookie: session=" + "abc123XYZ", "abc123XYZ"),
    ("Set-Cookie header", "Set-Cookie: sid=" + "q9W8e7R6t5Y", "q9W8e7R6t5Y"),
    ("password assignment", "password=" + "hunter2", "hunter2"),
    ("passwd assignment", "passwd=" + "hunter2", "hunter2"),
    ("pwd assignment", "pwd=" + "hunter2", "hunter2"),
    ("email address", "person.name" + "@" + "example.com", "person.name@example.com"),
    ("phone number", "+1 (555) 010-2345", "+1 (555) 010-2345"),
    ("phone number with dots", "555" + "." + "010" + "." + "2345", "555.010.2345"),
    ("token as a dict key", {"ghp_" + TAIL: "x"}, "ghp_" + TAIL),
    ("token nested in a list", ["fine", {"deep": "sk-ant-" + "aB3" * 12}], "sk-ant-" + "aB3" * 12),
    ("token after a comment opener", "see /* " + "ghp_" + TAIL, "ghp_" + TAIL),
    ("token after a lone quote", "Don't paste " + "ghp_" + TAIL, "ghp_" + TAIL),
    ("token in a multi-line string", "first line\nsecond line " + "ghp_" + TAIL + "\nthird line", "ghp_" + TAIL),
]

# (label, the note's value). Words, a URL, a time, an id and a number that are not secrets pass.
GREEN = [
    ("token budget", "token budget"),
    ("password manager", "password manager"),
    ("private key rotation", "rotate the private key"),
    ("owner's first name", "Shivam"),
    ("comment openers and a lone quote", "Don't use /* or // or # here"),
    ("multi-line text", "line one\nline two"),
    ("artifact link", ARTIFACT),
    ("ISO time", "2026-11-02T11:04:00Z"),
    ("date", "2026-11-02"),
    ("u_ id of 22 characters", "u_Qm4xT7bR2nKs9LfW0aZc"),
    ("u_ id of 24 characters", "u_Qm4xT7bR2nKs9LfW0aZcYe"),
    ("a key named token", {"token": "budget"}),
    ("a number with 14 digits, not a string", {"n": 20261102110400, "note": "budget"}),
]


def canonical(data):
    """The bytes a copy holds for `data`: sorted keys, two-space indent, a trailing newline."""
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def snapshot(folder):
    """Every file and folder under `folder` with its bytes, so a run that writes anything shows as a change."""
    found = {}
    if not os.path.isdir(folder):
        return found
    for dirpath, dirnames, names in os.walk(folder):
        for name in dirnames:
            found[os.path.relpath(os.path.join(dirpath, name), folder) + "/"] = None
        for name in names:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as f:
                found[os.path.relpath(path, folder)] = f.read()
    return found


def verdict_lines(r):
    """The stripped, non-empty lines the run printed on either stream."""
    return [line.strip() for line in (r.stdout + r.stderr).splitlines() if line.strip()]


def says(r, word):
    """True when a line the run printed starts with the verdict word, as `unknown` or `unknown - asks missing` does."""
    return any(re.match(re.escape(word) + r"\b", line) for line in verdict_lines(r))


def changed_count(r):
    """N of the first `changed N` line the run printed, or None."""
    for line in verdict_lines(r):
        found = re.match(r"changed\s+(\d+)\b", line)
        if found:
            return int(found.group(1))
    return None


def shown(r, secrets=()):
    """The run's output for a failure message, with each secret taken out so a red never prints one."""
    text = r.stdout + r.stderr
    for secret in secrets:
        text = text.replace(secret, "<redacted>")
    return text


def item(n):
    """An item shaped like a fetched one: the same keys, synthetic values."""
    return {"id": "item-%03d" % n, "n": n, "kind": "licence", "status": "open", "title": "Item %d" % n,
            "short": "Item %d" % n, "ref": "R-%03d" % n, "home": "queue", "owner": "Test Owner",
            "added": "2026-10-%02dT09:00:00Z" % (1 + n % 28),
            "context": "Synthetic item %d for the export round trip." % n, "why": "Synthetic reason %d." % n,
            "options": [{"key": k, "label": "Option " + k.upper(), "gain": "Gain", "lose": "Loss", "how": "Pick " + k}
                        for k in "ab"],
            "links": [{"label": "Record", "url": ARTIFACT}], "pick": "a",
            "lastAnswer": {"at": "2026-10-02T10:00:00Z", "note": "Synthetic"}}


def full_size():
    """The full-size export: 120 items, 7 answers, 3 groups, 2 asks and the page's meta. 133 docs in all."""
    items = {"item-%03d" % n: item(n) for n in range(1, 121)}
    answers = {"ans-%02d" % n: {"item": "item-%03d" % n, "pick": "a", "note": "Synthetic answer %d" % n}
               for n in range(1, 8)}
    groups = {"grp-%d" % n: {"name": "Group %d" % n, "items": ["item-%03d" % n]} for n in range(1, 4)}
    asks = {"ask-%d" % n: {"item": "item-%03d" % n, "question": "Which option?"} for n in range(1, 3)}
    return {"items": items, "answers": answers, "groups": groups, "asks": asks, "meta": {"page": META}}


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)  # test-temp-standard: never the system temp dir
        self.addCleanup(self.tmp.cleanup)

    def fetch(self, items=None, answers=None, groups=None, asks=None, meta=None):
        """A fetched folder: one folder per collection, each doc a JSON file. An empty collection is an empty folder."""
        root = tempfile.mkdtemp(prefix="fetched-", dir=self.tmp.name)
        docs = {"items": items, "answers": answers, "groups": groups, "asks": asks, "meta": meta}
        for name in COLLECTIONS:
            os.makedirs(os.path.join(root, name))
            for doc_id, data in (docs[name] or {}).items():
                write_text(os.path.join(root, name, doc_id + ".json"), canonical(data))
        return root

    def out(self, name="waiting"):
        return os.path.join(self.tmp.name, name)

    def run_cmd(self, *args, env=None):
        if not os.path.isfile(CMD):
            self.fail("export_page.py is not built: no file at %s" % CMD)
        env = env or dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, CMD, *args], capture_output=True, text=True, timeout=60, env=env)

    def export(self, fetched, out, page=None):
        args = ["--fetched", fetched, "--out", out]
        if page:
            args += ["--page", page]
        return self.run_cmd(*args)

    def assertVerdict(self, r, want, secrets=()):
        self.assertTrue(says(r, want), "verdict %r not printed. Output:\n%s" % (want, shown(r, secrets)))

    def assertChanged(self, r, n, secrets=()):
        self.assertEqual(changed_count(r), n, "`changed %d` not printed. Output:\n%s" % (n, shown(r, secrets)))

    def assertBatches(self, r, k, n):
        found = [m for m in (re.match(r"batches\s+(\d+)\s+docs\s+(\d+)\b", line) for line in verdict_lines(r)) if m]
        self.assertTrue(found, "no `batches <k> docs <n>` line. Output:\n" + shown(r))
        self.assertEqual((int(found[0].group(1)), int(found[0].group(2))), (k, n), shown(r))


class Scan(Base):
    def assert_refused(self, label, note, secret):
        fetched = self.fetch(items={"leak": {"id": "leak", "title": "Leak", "note": note}})
        out = self.out()
        before = snapshot(out)
        r = self.export(fetched, out)
        self.assertVerdict(r, "refused", [secret])
        self.assertEqual(r.returncode, 1, "%s: refused must exit 1. Output:\n%s" % (label, shown(r, [secret])))
        self.assertNotIn(secret, r.stdout + r.stderr, "%s: the matched value was printed" % label)
        self.assertEqual(snapshot(out), before, "%s: a refused run wrote into the copy" % label)

    def test_refuses_each_secret_shape_and_writes_nothing(self):
        for label, note, secret in RED:
            with self.subTest(label=label):
                self.assert_refused(label, note, secret)

    def test_each_find_is_one_line_that_names_its_file_and_field(self):
        note = "ok " + "sk-ant-" + "aB3" * 12
        fetched = self.fetch(items={"leak": {"id": "leak", "title": "ghp_" + TAIL, "note": note}})
        r = self.export(fetched, self.out())
        self.assertVerdict(r, "refused", [TAIL])
        finds = [line for line in (r.stdout + r.stderr).splitlines() if "leak" in line]
        self.assertEqual(sum("title" in line for line in finds), 1, "no one line names the title field:\n" + shown(r, [TAIL]))
        self.assertEqual(sum("note" in line for line in finds), 1, "no one line names the note field:\n" + shown(r, [TAIL]))

    def test_words_and_shapes_that_are_not_secrets_pass(self):
        for index, (label, value) in enumerate(GREEN):
            with self.subTest(label=label):
                doc = {"id": "ok", "title": "Ok", "note": value}
                out = self.out("waiting-%d" % index)
                r = self.export(self.fetch(items={"ok": doc}), out)
                self.assertEqual(r.returncode, 0, "%s: a non-secret was refused or failed. Output:\n%s" % (label, shown(r)))
                self.assertFalse(says(r, "refused"), label)
                self.assertEqual(read_text(os.path.join(out, "items", "ok.json")), canonical(doc), label)


class Mirror(Base):
    def test_counts_each_write_and_delete_and_keeps_the_rest(self):
        fetched = self.fetch(items={"a": {"id": "a"}, "b": {"id": "b"}, "c": {"id": "c"}},
                             answers={"x": {"id": "x"}}, meta={"page": META})
        out = self.out()
        self.assertChanged(self.export(fetched, out), 5)
        c_path = os.path.join(out, "items", "c.json")
        os.utime(c_path, (SENTINEL, SENTINEL))
        write_text(os.path.join(fetched, "items", "a.json"), canonical({"id": "a", "title": "new"}))
        write_text(os.path.join(fetched, "items", "d.json"), canonical({"id": "d"}))
        os.remove(os.path.join(fetched, "items", "b.json"))
        r = self.export(fetched, out)
        self.assertChanged(r, 3)
        self.assertEqual(r.returncode, 0, shown(r))
        self.assertEqual(os.stat(c_path).st_mtime, SENTINEL, "an unchanged doc was rewritten")
        self.assertFalse(os.path.exists(os.path.join(out, "items", "b.json")), "a doc no longer fetched was kept")
        self.assertEqual(read_text(os.path.join(out, "items", "a.json")), canonical({"id": "a", "title": "new"}))
        self.assertEqual(read_text(os.path.join(out, "items", "d.json")), canonical({"id": "d"}))

    def test_each_written_doc_is_canonical_json(self):
        fetched = self.fetch(items={"a": {"z": 1, "a": ["uni", 2]}}, meta={"page": META})
        out = self.out()
        self.assertEqual(self.export(fetched, out).returncode, 0)
        self.assertEqual(read_text(os.path.join(out, "items", "a.json")), canonical({"z": 1, "a": ["uni", 2]}))
        self.assertEqual(read_text(os.path.join(out, "meta", "page.json")), canonical(META))

    def test_a_rewrite_with_the_same_data_is_same(self):
        fetched = self.fetch(items={"a": {"id": "a", "n": 2}})
        out = self.out()
        self.export(fetched, out)
        self.assertVerdict(self.export(fetched, out), "same")
        # The same data, fetched again in another layout: the copy's bytes do not follow the fetch's layout.
        write_text(os.path.join(fetched, "items", "a.json"), json.dumps({"n": 2, "id": "a"}, indent=4))
        r = self.export(fetched, out)
        self.assertVerdict(r, "same")
        self.assertEqual(r.returncode, 0, shown(r))
        self.assertEqual(read_text(os.path.join(out, "items", "a.json")), canonical({"id": "a", "n": 2}))

    def test_an_emptied_collection_deletes_its_docs(self):
        fetched = self.fetch(items={"a": {"id": "a"}, "b": {"id": "b"}, "c": {"id": "c"}})
        out = self.out()
        self.export(fetched, out)
        for name in ("a", "b", "c"):
            os.remove(os.path.join(fetched, "items", name + ".json"))
        r = self.export(fetched, out)
        self.assertChanged(r, 3)
        self.assertEqual(r.returncode, 0, shown(r))
        self.assertEqual(glob.glob(os.path.join(out, "items", "*.json")), [], "the emptied collection kept docs")

    def test_all_empty_collections_into_an_empty_copy_are_same(self):
        fetched = self.fetch()
        out = self.out()
        r = self.export(fetched, out)
        self.assertVerdict(r, "same")
        self.assertEqual(r.returncode, 0, shown(r))

    def test_a_missing_collection_folder_is_unknown_and_writes_nothing(self):
        fetched = self.fetch(items={"a": {"id": "a"}}, meta={"page": META})
        os.rmdir(os.path.join(fetched, "asks"))
        out = self.out()
        write_text(os.path.join(out, "items", "old.json"), "{}\n")
        before = snapshot(out)
        r = self.export(fetched, out)
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))
        self.assertEqual(snapshot(out), before, "a run with a missing folder wrote into the copy")

    def test_a_refused_fetch_writes_nothing_and_keeps_the_old_copy(self):
        out = self.out()
        self.assertEqual(self.export(self.fetch(items={"a": {"id": "a", "t": "old"}, "c": {"id": "c"}}), out).returncode, 0)
        before = snapshot(out)
        # "z" sorts last, so a run that wrote as it read would change "a" before it reached the token.
        fetched = self.fetch(items={"a": {"id": "a", "t": "new"}, "c": {"id": "c"}, "z": {"id": "z", "note": "ghp_" + TAIL}})
        r = self.export(fetched, out)
        self.assertVerdict(r, "refused", [TAIL])
        self.assertEqual(r.returncode, 1, shown(r, [TAIL]))
        self.assertEqual(snapshot(out), before, "a refused fetch changed the old copy")

    def test_runs_with_no_git_on_the_path(self):
        fetched = self.fetch(items={"a": {"id": "a"}})
        empty = os.path.join(self.tmp.name, "no-bin")  # a PATH with no git in it
        os.makedirs(empty)
        out = self.out()
        r = self.run_cmd("--fetched", fetched, "--out", out, env=dict(os.environ, PATH=empty, PYTHONDONTWRITEBYTECODE="1"))
        self.assertChanged(r, 1)
        self.assertEqual(r.returncode, 0, shown(r))


class Page(Base):
    def test_design_block_lands_in_page_designdata(self):
        page = write_text(os.path.join(self.tmp.name, "page.html"), DESIGN.sub(lambda m: m.group(1) + DESIGN_BODY + m.group(3), PAGE, count=1))
        out = self.out()
        r = self.export(self.fetch(meta={"page": META}), out, page=page)
        self.assertEqual(r.returncode, 0, shown(r))
        with open(os.path.join(out, "page", "designData.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), json.loads(DESIGN_BODY), "the page's designData did not land as the block's JSON")

    def test_a_page_with_no_designdata_block_is_unknown(self):
        page = write_text(os.path.join(self.tmp.name, "page.html"), PAGE.replace(DESIGN_ELEMENT, "", 1))
        r = self.export(self.fetch(meta={"page": META}), self.out(), page=page)
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))

    def test_a_page_with_two_designdata_blocks_is_unknown(self):
        page = write_text(os.path.join(self.tmp.name, "page.html"), PAGE + DESIGN_ELEMENT)
        r = self.export(self.fetch(meta={"page": META}), self.out(), page=page)
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))

    def test_a_token_in_designdata_refuses_the_whole_export(self):
        body = '{"a": "' + "ghp_" + TAIL + '"}'
        page = write_text(os.path.join(self.tmp.name, "page.html"), DESIGN.sub(lambda m: m.group(1) + body + m.group(3), PAGE, count=1))
        out = self.out()
        before = snapshot(out)
        r = self.export(self.fetch(meta={"page": META}), out, page=page)
        self.assertVerdict(r, "refused", [TAIL])
        self.assertEqual(r.returncode, 1, shown(r, [TAIL]))
        self.assertNotIn(TAIL, r.stdout + r.stderr, "the matched value was printed")
        self.assertEqual(snapshot(out), before, "a refused page changed the copy")

    def test_a_mockup_change_alone_counts_one(self):
        first = write_text(os.path.join(self.tmp.name, "page-first.html"), DESIGN.sub(lambda m: m.group(1) + DESIGN_BODY + m.group(3), PAGE, count=1))
        second = write_text(os.path.join(self.tmp.name, "page-second.html"),
                            DESIGN.sub(lambda m: m.group(1) + '{"a": "changed mockup"}' + m.group(3), PAGE, count=1))
        fetched = self.fetch(meta={"page": META})
        out = self.out()
        self.assertEqual(self.export(fetched, out, page=first).returncode, 0)
        r = self.export(fetched, out, page=second)
        self.assertChanged(r, 1)
        self.assertEqual(r.returncode, 0, shown(r))


class Rebuild(Base):
    def batch_entries(self, batches):
        files = sorted(glob.glob(os.path.join(batches, "batch-*.json")))
        entries, sizes = [], []
        for path in files:
            with open(path, encoding="utf-8") as f:
                batch = json.load(f)
            self.assertIsInstance(batch, list, os.path.basename(path))
            sizes.append(len(batch))
            entries.extend(batch)
        return files, entries, sizes

    def rebuild(self, waiting, batches):
        os.makedirs(batches, exist_ok=True)
        return self.run_cmd("--rebuild", waiting, "--batches", batches)

    def exported(self, docs, page=True):
        fetched = self.fetch(**docs)
        waiting = self.out()
        page_path = write_text(os.path.join(self.tmp.name, "page.html"), DESIGN.sub(lambda m: m.group(1) + DESIGN_BODY + m.group(3), PAGE, count=1))
        r = self.export(fetched, waiting, page=page_path if page else None)
        self.assertEqual(r.returncode, 0, shown(r))
        return waiting

    def test_round_trip_of_a_full_size_export_is_exact(self):
        data = full_size()
        waiting = self.exported(data)
        batches = os.path.join(self.tmp.name, "batches")
        r = self.rebuild(waiting, batches)
        self.assertEqual(r.returncode, 0, shown(r))
        files, entries, sizes = self.batch_entries(batches)
        self.assertBatches(r, len(files), 133)
        self.assertTrue(all(size <= 50 for size in sizes), "a batch holds more than 50 entries: %s" % sizes)
        for entry in entries:
            self.assertEqual(set(entry), {"op", "collection", "doc_id", "data"}, "an entry has the wrong keys")
            self.assertEqual(entry["op"], "set")
        self.assertNotIn("page", {entry["collection"] for entry in entries}, "the page folder went into a batch")
        want = collections.Counter((name, doc_id, canonical(doc)) for name, docs in data.items()
                                   for doc_id, doc in docs.items())
        got = collections.Counter((e["collection"], e["doc_id"], canonical(e["data"])) for e in entries)
        self.assertEqual(len(entries), 133, "the batches hold %d entries, not 133" % len(entries))
        self.assertEqual(set(got), set(want), "the batches' docs are not the export's docs")
        self.assertEqual(max(got.values()), 1, "a doc is in the batches more than once")

    def test_fifty_docs_fit_one_batch(self):
        waiting = self.exported({"items": {"item-%03d" % n: item(n) for n in range(1, 51)}}, page=False)
        batches = os.path.join(self.tmp.name, "batches")
        r = self.rebuild(waiting, batches)
        self.assertBatches(r, 1, 50)
        self.assertEqual(self.batch_entries(batches)[2], [50])

    def test_fifty_one_docs_split_in_two(self):
        waiting = self.exported({"items": {"item-%03d" % n: item(n) for n in range(1, 52)}}, page=False)
        batches = os.path.join(self.tmp.name, "batches")
        r = self.rebuild(waiting, batches)
        self.assertBatches(r, 2, 51)
        files, entries, sizes = self.batch_entries(batches)
        self.assertEqual(len(files), 2)
        self.assertTrue(all(size <= 50 for size in sizes), sizes)
        self.assertEqual(sorted(e["doc_id"] for e in entries), sorted("item-%03d" % n for n in range(1, 52)))

    def test_an_empty_waiting_dir_is_unknown(self):
        waiting = self.out()
        os.makedirs(waiting)
        r = self.rebuild(waiting, os.path.join(self.tmp.name, "batches"))
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))

    def test_a_missing_waiting_dir_is_unknown(self):
        r = self.rebuild(self.out(), os.path.join(self.tmp.name, "batches"))
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""`merge --reviewed` reads the repo's comments since a cursor kept in the merge state file (reviewed_read in merge/merge.py).

Run: python3 merge/test_reviewed_cursor.py
The fixtures are test_merge.py's: PullsHost serves the repo's comments (honor_since answers `since` as GitHub does, now pins the Host
clock), and CloudSession gives each case its own config dir. Main reads every comment on every run, so the cursor facts are red there.
A case checks its scope (which read ran) before its subject (the lines printed). A check that main also passes is a green control.
"""
import datetime, json, os, shutil, unittest

import test_merge as tm  # noqa: E402  the git half's fixtures; importing it runs none of its cases

FLOOR = "2026-10-01T00:00:00Z"  # the open pull request's created_at (batch_pull's default): the oldest floor
OLD_PR = "2026-09-30T00:00:00Z"  # a pull request reopened older than the floor
T1 = "2026-10-02T00:00:00Z"  # the log and lint comments of a case: once read, the cursor is their updated_at
T2 = "2026-10-03T00:00:00Z"
T_NEWEST = "2026-10-04T00:00:00Z"
OVERLAP = datetime.timedelta(minutes=5)  # since = cursor less this overlap (reviewed_read)
CLOCK0 = int(datetime.datetime(2026, 11, 13, tzinfo=datetime.timezone.utc).timestamp())  # the Host clock of a case's first run
STALE_SECS = 1800  # a cache older than this is read in full (REVIEWED_FULL_REREAD_SECS)
FOLDER = object()  # a damage: the state path is a folder
ROUND_ONE_FAIL = ("Round 1: reviewer, sonnet, FAIL",)
REPO_NAME = "o/r"  # the repo the fixture's host names: its cache's key (reviewed_rows)
ALPHA, BETA = "o/alpha", "o/beta"  # two repos whose hosts have no name: each is named by the full_name its bare repo route reads
EARLY = "2026-10-01T12:00:00Z"  # before the cursor less the overlap: a warm read from the cursor never returns it
DEPTH = 100000  # a state file this deep makes json.loads raise RecursionError


def nested(head):
    """A state file's text: `head`, then a list nested DEPTH deep, then the object's close."""
    return head + "[" * DEPTH + "]" * DEPTH + "}"


DEEP_STATE = nested('{"reviewed_cursor": ')
DEEP_ROLE_STATE = nested('{"session": "%s", "role": "batch-runner", "reviewed_cursor": ' % tm.ROLE_SESSION)


def when(text):
    """The instant of an ISO time, or None when `text` is not one. The case's assert then names the mismatch."""
    try:
        return tm.iso_time(text)
    except ValueError:
        return None


def padding():
    """Full size: 60 plain comments on #8 before the overlap window (no rows)."""
    return [tm.review_comment(1000 + i, 8, "LGTM", created="2026-10-01T12:00:00Z") for i in range(60)]


def standard_comments(log=None, lint=None):
    """The padding, then #7's log and lint at T1, or the ones given."""
    log = log or tm.review_comment(1, 7, tm.record_text(rounds=tm.REVIEW_PASS), created=T1)
    return [*padding(), log, lint or tm.lint_of(7, tm.REVIEW_HEAD)]


def own_log(cid, rounds=tm.REVIEW_PASS, created=T1):
    """#7's review log at the live head, as the repo's comment list gives it."""
    return tm.review_comment(cid, 7, tm.record_text(rounds=rounds), created=created)


def alpha_comments():
    """ALPHA's comments: #7's log is open."""
    return [*padding(), own_log(1, rounds=ROUND_ONE_FAIL), tm.lint_of(7, tm.REVIEW_HEAD)]


def beta_comments():
    """BETA's comments: its own log is from before the cursor, and passes."""
    return [*padding(), own_log(21, created=EARLY), tm.lint_of(7, tm.REVIEW_HEAD)]


def log_row(cid=1):
    return {"id": cid, "issue": 7, "kind": "log", "body": tm.record_text(rounds=tm.REVIEW_PASS), "created": T1, "updated": T1}


def lint_row(cid=507):
    return {"id": cid, "issue": 7, "kind": "lint", "body": tm.lint_body(tm.REVIEW_HEAD), "created": T1, "updated": T1}


def without(row, key):
    return {k: v for k, v in row.items() if k != key}


def edited(**changes):
    """The state file's dict with this repo's cache in reviewed_read's shape, its fields changed by `changes`. The rest stays valid."""
    cache = {"floor": FLOOR, "cursor": T1, "full_at": CLOCK0, "rows": [log_row(), lint_row()]}
    cache.update(changes)
    return {"reviewed_cursor": {REPO_NAME: cache}}


# (name, content, rebuilds): the state file after one defect. content: None removes the file, FOLDER makes its path a folder, bytes or text
# is written as is, a callable gives a dict written as JSON. rebuilds: the next run after the full read reads from the cursor again.
DAMAGES = (
    ("the state file is missing", None, True),
    ("the state path is a folder", FOLDER, False),
    ("the state file is not JSON", "{not json", True),
    ("the state file is not UTF-8", b"\xff\xfe\x00{}", True),
    ("the top level is a list", "[]", True),
    ("reviewed_cursor is a list", lambda: {"reviewed_cursor": []}, True),
    ("this repo's entry is a string", lambda: {"reviewed_cursor": {REPO_NAME: "x"}}, True),
    ("floor is a number", lambda: edited(floor=5), True),
    ("cursor is not a time", lambda: edited(cursor="soon"), True),
    ("full_at is a string", lambda: edited(full_at="now"), True),
    ("rows is an object", lambda: edited(rows={}), True),
    ("a row is a string", lambda: edited(rows=[log_row(), "x"]), True),
    ("a row lacks its body", lambda: edited(rows=[without(log_row(), "body"), lint_row()]), True),
    ("a row has an unknown kind", lambda: edited(rows=[{**log_row(), "kind": "other"}, lint_row()]), True),
    ("a row id is a string", lambda: edited(rows=[log_row(), {**lint_row(), "id": "507"}]), True),
    ("the state file is nested 100000 deep", DEEP_STATE, True),
)


class ReviewedCursor(tm.CloudSession):
    """`merge --reviewed` with a cursor: the comment read it makes, the cache it keeps, and what the state file keeps of that cache."""

    def setUp(self):
        super().setUp()
        self.clock = CLOCK0  # the Host clock: a case moves it to age the cache

    def run_reviewed(self, comments, pulls=None, repo=REPO_NAME, full_name=None, cwd=None):
        """-> (host, out): one `merge --reviewed` over the open pulls (default: #7 at REVIEW_HEAD, created at FLOOR) and the repo's comments,
        which the host serves as `since` filters them. The host names its repo by `repo`, or, when that is None, by the full_name its bare
        repo route reads. The run exits 0 or the case fails; a crash fails the case, named by what raised it."""
        pulls = pulls or [tm.batch_pull(7, tm.REVIEW_HEAD, created_at=FLOOR)]
        host = tm.PullsHost(pulls, {}, comments=comments, honor_since=True, now=lambda: self.clock, repo=repo, full_name=full_name, cwd=cwd)
        try:
            rc, out, err = self.run_args("--reviewed", host=host)
        except Exception as e:
            self.fail(f"the run raised {type(e).__name__}: {e}")
        self.assertEqual(rc, 0, out + err)
        return host, out

    def run_as(self, name, comments, cwd=None):
        """A run of repo `name` by a host with no repo name: the name is the one its bare repo route reads."""
        return self.run_reviewed(comments, repo=None, full_name=name, cwd=cwd)

    def since_of(self, host):
        """The since of the run's comment read. The run reads the comments once: every check below stands on that scope."""
        reads = [f for rel, f in host.list_calls if rel == "issues/comments"]
        self.assertEqual(len(reads), 1, f"the run read the repo's comments {len(reads)} times, not once")
        return reads[0].get("since")

    def assert_full_read(self, host, floor=FLOOR):
        """The run read in full: since is the oldest open pull request's created_at."""
        got = self.since_of(host)
        self.assertEqual(when(got), when(floor), f"the run did not read in full: since is {got}, not the oldest open pull request's {floor}")

    def assert_from_cursor(self, host, cursor):
        """The run read from the cursor: since is the cursor less the overlap."""
        got = self.since_of(host)
        self.assertEqual(when(got), when(cursor) - OVERLAP, f"the run did not read from the cursor {cursor}: since is {got}")

    def state(self):
        """The state file's parsed content, or None when there is no file."""
        if not os.path.isfile(self.role_file):
            return None
        with open(self.role_file, encoding="utf-8") as f:
            return json.load(f)

    def caches(self):
        """The state file's reviewed_cursor: each repo's cache by its key, or {} when there is none."""
        data = self.state()
        caches = data.get("reviewed_cursor") if isinstance(data, dict) else None
        return caches if isinstance(caches, dict) else {}

    def cursor(self):
        """This repo's cache: reviewed_cursor's entry under REPO_NAME, or None."""
        return self.caches().get(REPO_NAME)

    def put_state(self, content):
        """Write the state file as `content` (see DAMAGES). The file is replaced whatever it was."""
        if os.path.isfile(self.role_file):
            os.remove(self.role_file)
        if content is None:
            return
        if content is FOLDER:
            os.makedirs(self.role_file)
            return
        if callable(content):
            content = content()
        os.makedirs(os.path.dirname(self.role_file), exist_ok=True)
        if isinstance(content, dict):
            content = json.dumps(content)
        if isinstance(content, bytes):
            with open(self.role_file, "wb") as f:
                f.write(content)
        else:
            with open(self.role_file, "w", encoding="utf-8") as f:
                f.write(content)

    def reset_state(self):
        """No state at all: the state folder and everything in it are removed, whichever of them is there."""
        folder = os.path.dirname(self.role_file)
        if os.path.isdir(folder):
            shutil.rmtree(folder)
        elif os.path.lexists(folder):
            os.remove(folder)

    def test_a_warm_run_reads_from_the_cursor_and_prints_the_cold_lines(self):
        comments = standard_comments()
        host, cold = self.run_reviewed(comments)
        self.assert_full_read(host)
        host, warm = self.run_reviewed(comments)
        self.assert_from_cursor(host, T1)
        self.assertEqual(warm, cold, "the warm run printed other lines than the cold run")

    def test_a_log_posted_on_the_live_head_after_the_cursor_shows_on_the_next_run(self):
        lint = tm.lint_of(7, tm.REVIEW_HEAD)
        host, before = self.run_reviewed([lint])
        self.assert_full_read(host)
        self.assertEqual(tm.no_record_numbers(before), {7}, before)
        log = tm.review_comment(2, 7, tm.record_text(rounds=tm.REVIEW_PASS), created=T2)
        host, after = self.run_reviewed([lint, log])
        self.assert_from_cursor(host, T1)
        self.assertRegex(tm.list_line(self, after, 7), rf"^#7 feat7 {tm.REVIEW_HEAD[:9]} done: ")

    def test_an_edited_log_replaces_its_cached_row(self):
        lint = tm.lint_of(7, tm.REVIEW_HEAD)
        log = tm.review_comment(1, 7, tm.record_text(rounds=tm.REVIEW_PASS), created=T1)
        host, first = self.run_reviewed([log, lint])
        self.assert_full_read(host)
        self.assertRegex(tm.list_line(self, first, 7), rf"^#7 feat7 {tm.REVIEW_HEAD[:9]} done: ")
        # The edit keeps created_at and moves updated_at past the cursor: only the updated time brings it back.
        edited_log = tm.review_comment(1, 7, "<!-- review-record -->\nPR: #7\n", created=T1, updated=T2)
        host, after = self.run_reviewed([edited_log, lint])
        self.assert_from_cursor(host, T1)
        self.assertRegex(tm.list_line(self, after, 7), rf"^#7 feat7 {tm.REVIEW_HEAD[:9]} bad: ")

    def test_a_cache_that_cannot_be_trusted_is_a_full_read_then_rebuilt(self):
        comments = standard_comments()
        for name, content, rebuilds in DAMAGES:
            with self.subTest(damage=name):
                self.reset_state()
                host, cold = self.run_reviewed(comments)
                self.assert_full_read(host)
                self.put_state(content)
                host, out = self.run_reviewed(comments)
                self.assert_full_read(host)
                self.assertEqual(out, cold, "the damaged state changed the printed lines")
                if rebuilds:
                    host, out = self.run_reviewed(comments)
                    self.assert_from_cursor(host, T1)
                    self.assertEqual(out, cold, "the rebuilt cache printed other lines than the cold run")

    def test_the_damage_table_baseline_reads_from_the_cursor(self):
        """The undamaged cache that DAMAGES damages is accepted: its warm read comes from the cursor. Without this, a damaged subtest could
        full-read on a baseline the validator rejects, and the damage would not be what forced the full read."""
        comments = standard_comments()
        host, cold = self.run_reviewed(comments)
        self.assert_full_read(host)
        self.put_state(edited())
        host, out = self.run_reviewed(comments)
        self.assert_from_cursor(host, T1)
        self.assertEqual(out, cold, "the undamaged baseline printed other lines than the cold run")

    def test_a_cache_with_no_rows_reads_from_the_cursor_and_prints_the_cold_lines(self):
        comments = standard_comments()
        host, cold = self.run_reviewed(comments)
        self.put_state(edited(rows=[]))
        host, out = self.run_reviewed(comments)
        self.assert_from_cursor(host, T1)
        self.assertEqual(out, cold, "an empty cache printed other lines than the cold run")

    def test_a_reopened_pull_request_older_than_the_floor_forces_a_full_read(self):
        pr7 = tm.batch_pull(7, tm.REVIEW_HEAD, created_at=FLOOR)
        pr9 = tm.batch_pull(9, tm.REVIEW_OLD_HEAD, created_at=OLD_PR)
        log7 = tm.review_comment(1, 7, tm.record_text(rounds=tm.REVIEW_PASS), created=T_NEWEST)
        lint7 = tm.lint_of(7, tm.REVIEW_HEAD)
        # PR 9's log predates the cursor, so only a read from the reopened pull request's created_at returns it.
        log9 = tm.review_comment(3, 9, tm.record_text(n=9, head=tm.REVIEW_OLD_HEAD, rounds=tm.REVIEW_PASS), created=T1)
        lint9 = tm.lint_of(9, tm.REVIEW_OLD_HEAD)
        host, first = self.run_reviewed([log7, lint7], pulls=[pr7])
        self.assert_full_read(host)
        comments, pulls = [log7, lint7, log9, lint9], [pr7, pr9]
        host, second = self.run_reviewed(comments, pulls=pulls)
        self.assert_full_read(host, floor=OLD_PR)
        self.assertRegex(tm.list_line(self, second, 9), rf"^#9 feat9 {tm.REVIEW_OLD_HEAD[:9]} done: ")
        host, third = self.run_reviewed(comments, pulls=pulls)
        self.assert_from_cursor(host, T_NEWEST)
        self.assertEqual(third, second, "the cache lost the reopened pull request's log on the next run")

    def stale_case_comments(self):
        """-> (open log, passing log, lint): the newest log fails round 1, so #7 is open until it is deleted."""
        lint = tm.lint_of(7, tm.REVIEW_HEAD)
        passing = tm.review_comment(1, 7, tm.record_text(rounds=tm.REVIEW_PASS), created=T1)
        failed = tm.review_comment(2, 7, tm.record_text(rounds=ROUND_ONE_FAIL), created=T2)
        return [passing, failed, lint], [passing, lint]

    def test_a_cache_younger_than_1800_seconds_is_read_from_the_cursor(self):
        both, _ = self.stale_case_comments()
        host, first = self.run_reviewed(both)
        self.assert_full_read(host)
        self.assertRegex(tm.list_line(self, first, 7), rf"^#7 feat7 {tm.REVIEW_HEAD[:9]} open: ")
        self.clock = CLOCK0 + STALE_SECS - 1  # 1799 seconds on: the cache is still fresh
        host, fresh = self.run_reviewed(both)
        self.assert_from_cursor(host, T2)
        self.assertEqual(fresh, first, "a fresh cache printed other lines than the full read")

    def test_a_cache_older_than_1800_seconds_is_a_full_read_and_drops_a_deleted_comment(self):
        both, after_delete = self.stale_case_comments()
        host, first = self.run_reviewed(both)
        self.assert_full_read(host)
        self.assertRegex(tm.list_line(self, first, 7), rf"^#7 feat7 {tm.REVIEW_HEAD[:9]} open: ")
        self.clock = CLOCK0 + STALE_SECS + 1  # 1801 seconds on: stale, and the failed log was deleted meanwhile
        host, stale = self.run_reviewed(after_delete)
        self.assert_full_read(host)
        self.assertRegex(tm.list_line(self, stale, 7), rf"^#7 feat7 {tm.REVIEW_HEAD[:9]} done: ")

    def test_write_merge_role_keeps_the_reviewed_cursor(self):
        cache = {"floor": FLOOR, "cursor": T1, "full_at": CLOCK0, "rows": [log_row(), lint_row()]}
        self.put_state({"session": tm.ROLE_SESSION, "role": "batch-runner", "reviewed_cursor": {REPO_NAME: cache}})
        with self.cloud():
            tm.merge.write_merge_role("batch-runner")
        data = self.state()
        self.assertEqual((data.get("session"), data.get("role")), (tm.ROLE_SESSION, "batch-runner"), "write_merge_role did not keep the session and role")
        self.assertEqual(data.get("reviewed_cursor"), {REPO_NAME: cache}, "write_merge_role dropped the reviewed_cursor key")

    def test_the_cursor_write_keeps_the_session_and_the_role(self):
        self.put_state({"session": tm.ROLE_SESSION, "role": "batch-runner"})
        self.run_reviewed(standard_comments())
        data = self.state()
        self.assertEqual((data.get("session"), data.get("role")), (tm.ROLE_SESSION, "batch-runner"), "the cursor write changed the session or the role")
        self.assertIsNotNone(self.cursor(), "the --reviewed run wrote no cursor under reviewed_cursor")

    def test_read_merge_role_reads_a_file_with_only_the_cursor_as_no_role(self):
        cache = {"floor": FLOOR, "cursor": T1, "full_at": CLOCK0, "rows": []}
        self.put_state({"reviewed_cursor": {REPO_NAME: cache}})
        with self.cloud():
            self.assertIsNone(tm.merge.read_merge_role())
        self.put_state({"session": tm.ROLE_SESSION, "role": "batch-runner", "reviewed_cursor": {REPO_NAME: cache}})
        with self.cloud():
            self.assertEqual(tm.merge.read_merge_role(), "batch-runner")

    def test_an_unwritable_state_folder_still_prints_the_full_read_lines(self):
        comments = standard_comments()
        self.reset_state()
        host, writable = self.run_reviewed(comments)
        self.assert_full_read(host)
        self.assertIsNotNone(self.cursor(), "a run with a writable state folder wrote no cursor")
        self.reset_state()
        with open(os.path.dirname(self.role_file), "w", encoding="utf-8") as f:  # the state folder is a file: nothing can be written in it
            f.write("not a folder\n")
        host, lines = self.run_reviewed(comments)
        self.assert_full_read(host)
        self.assertEqual(lines, writable, "an unwritable state folder changed the printed lines")

    def assert_second_repo_reads_in_full(self, first, second, cwd=None):
        """Shared step of the no-name cases: ALPHA runs and leaves its cache, then BETA runs with its own early log. BETA's run reads in
        full and prints its own log as done, never ALPHA's rows, which are open."""
        host, _ = self.run_as(ALPHA, first, cwd)
        self.assert_full_read(host)
        host, out = self.run_as(BETA, second, cwd)
        got = self.since_of(host)
        self.assertEqual(when(got), when(FLOOR), f"{BETA} read from {ALPHA}'s cache: its since is {got}, not the floor {FLOOR}")
        self.assertRegex(tm.list_line(self, out, 7), rf"^#7 feat7 {tm.REVIEW_HEAD[:9]} done: ", f"{BETA}'s run did not print its own log as done")

    def test_a_repo_with_no_name_in_the_run_never_reads_another_repos_cache(self):
        self.assert_second_repo_reads_in_full(alpha_comments(), beta_comments())

    def test_a_checkout_re_pointed_at_another_repo_never_reads_the_old_repos_cache(self):
        self.assert_second_repo_reads_in_full(alpha_comments(), beta_comments(), cwd=os.path.join(self.t, "checkout"))

    def test_a_run_whose_repo_has_no_name_keeps_no_cache_and_reads_in_full(self):
        comments = standard_comments()
        host, first = self.run_reviewed(comments, repo=None)
        self.assert_full_read(host)
        self.assertFalse(self.caches(), f"a run whose repo has no name wrote a cache under {sorted(self.caches())}")
        host, second = self.run_reviewed(comments, repo=None)
        self.assert_full_read(host)
        self.assertEqual(second, first, "a second run whose repo has no name printed other lines than the first")

    def assert_an_edit_drops_its_cached_row(self, before, after):
        """Shared step of the marker cases: the cache holds the comments `before`. Then `after` is read: one comment, edited past the cursor, no
        longer holds its marker on line 1. The warm run reads from the cursor and must print what a full read prints."""
        host, _ = self.run_reviewed(before)
        self.assert_full_read(host)
        host, warm = self.run_reviewed(after)
        self.assert_from_cursor(host, T1)
        self.reset_state()
        host, full = self.run_reviewed(after)
        self.assert_full_read(host)
        self.assertEqual(warm, full, "the edit that removed a marker left its cached row: the warm run printed other lines than a full read")

    def test_an_edit_that_removes_the_log_marker_drops_its_cached_row(self):
        unmarked = tm.review_comment(1, 7, tm.record_text(rounds=tm.REVIEW_PASS).split("\n", 1)[1], created=T1, updated=T2)
        self.assert_an_edit_drops_its_cached_row(standard_comments(), standard_comments(log=unmarked))

    def test_an_edit_that_removes_the_lint_marker_drops_its_cached_row(self):
        lint = tm.lint_of(7, tm.REVIEW_HEAD)
        unmarked = {**lint, "body": tm.lint_body(tm.REVIEW_HEAD).split("\n", 1)[1], "updated_at": T2}
        self.assert_an_edit_drops_its_cached_row(standard_comments(), standard_comments(lint=unmarked))

    def test_write_merge_role_survives_a_state_file_nested_too_deep(self):
        self.put_state(DEEP_STATE)
        with self.cloud():
            try:
                tm.merge.write_merge_role("batch-runner")
            except RecursionError as e:
                self.fail(f"write_merge_role crashed on a state file nested too deep: {e}")
        data = self.state()
        self.assertEqual((data.get("session"), data.get("role")), (tm.ROLE_SESSION, "batch-runner"), "write_merge_role did not record the role over a state file nested too deep")

    def test_read_merge_role_reads_a_state_file_nested_too_deep_as_no_role(self):
        self.put_state(DEEP_ROLE_STATE)
        with self.cloud():
            try:
                role = tm.merge.read_merge_role()
            except RecursionError as e:
                self.fail(f"read_merge_role crashed on a state file nested too deep: {e}")
        self.assertIsNone(role, "a state file nested too deep was read as a role: it is corrupt, so there is no role")


if __name__ == "__main__":
    unittest.main()

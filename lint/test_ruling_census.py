#!/usr/bin/env python3
"""Fixture tests for ruling_census.py.

Each test builds a fake `~/.claude/projects`-shaped root: project folders holding fake
transcript JSONL files and, where needed, a `memory/` folder and a temp git repo for the
reach test. Run with:

    python3 lint/test_ruling_census.py -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CENSUS = os.path.join(HERE, "ruling_census.py")

sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import ruling_census  # noqa: E402


def human(text, cwd=None):
    rec = {"type": "user", "isSidechain": False, "message": {"role": "user", "content": text}}
    if cwd is not None:
        rec["cwd"] = cwd
    return rec


def tool_use_msg(name, input_=None, id_="tu_1"):
    block = {"type": "tool_use", "id": id_, "name": name, "input": input_ or {}}
    return {"type": "assistant", "isSidechain": False,
            "message": {"role": "assistant", "content": [block]}}


def tool_result_msg(tool_use_id, content="ok"):
    block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    return {"type": "user", "isSidechain": False, "message": {"role": "user", "content": [block]}}


def assistant_text(text):
    return {"type": "assistant", "isSidechain": False,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def write_transcript(records, path):
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return path


def init_git_repo(path, committed_text):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True, capture_output=True, text=True)
    target = os.path.join(path, "f.txt")
    with open(target, "w", encoding="utf-8") as f:
        f.write(committed_text + "\n")
    subprocess.run(["git", "add", "f.txt"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=Test",
         "commit", "-q", "-m", "init"],
        cwd=path, check=True, capture_output=True, text=True,
    )


class RulingCensusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, "projects")
        os.makedirs(self.root)
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        init_git_repo(self.repo, "the repo already holds this exact spoken sentence here")

    def make_project(self, name):
        project_dir = os.path.join(self.root, name)
        os.makedirs(project_dir, exist_ok=True)
        return project_dir

    # ---------------------------------------------------------- each counter, plus reach test

    def test_01_every_counter_in_one_project(self):
        project_dir = self.make_project("proj1")
        os.makedirs(os.path.join(project_dir, "memory"), exist_ok=True)
        with open(os.path.join(project_dir, "memory", "notes.md"), "w", encoding="utf-8") as f:
            f.write("home: process-only\nhome:process-only\nhome: decisions/real.md\n")

        long_answer = "This is a fairly long answer with plenty of words in it"
        records = [
            human("start", cwd=self.repo),
            tool_use_msg("Write", {
                "file_path": os.path.join(project_dir, "memory", "plan.md"),
                "content": (
                    "the repo already holds this exact spoken sentence here\n"
                    "too short\n"
                    "this new sentence about a fresh ruling is not committed anywhere\n"
                ),
            }, id_="write_1"),
            tool_result_msg("write_1"),
            tool_use_msg("AskUserQuestion", {"questions": [{"question": "Q1?"}]}, id_="ask_1"),
            tool_result_msg(
                "ask_1",
                'Your questions have been answered: "Q1?"="%s", "Q2?"="Yes". '
                "You can now continue." % long_answer,
            ),
            tool_use_msg("Write", {
                "file_path": "/tmp/x/scratchpad/notes.txt",
                "content": "a scratch note",
            }, id_="write_2"),
            tool_result_msg("write_2"),
            assistant_text("This RULING changes things.\nA line about rulings, plural.\n"
                            "Nothing notable here."),
        ]
        path = write_transcript(records, os.path.join(project_dir, "s1.jsonl"))
        os.utime(path, None)

        timeouts = [0]
        counts = ruling_census.scan_transcript(path, project_dir, timeouts)

        self.assertEqual(counts["sessions"], 1)
        self.assertEqual(counts["memory_writes"], 1)
        self.assertEqual(counts["scratchpad_writes"], 1)
        self.assertEqual(counts["ruling_lines"], 2)
        self.assertEqual(counts["answers"], 2)
        # memory line 1 (committed) -> found, memory line 3 (not committed) -> not_found,
        # long_answer (not committed) -> not_found. Short answer "Yes" is under 8 words,
        # so it adds to `answers` but never reaches the reach test.
        self.assertEqual(counts["reach_found"], 1)
        self.assertEqual(counts["reach_not_found"], 2)
        self.assertEqual(counts["unknown"], 0)
        self.assertEqual(timeouts[0], 0)

        process_only, mem_unknown = ruling_census.scan_memory_folder(project_dir)
        self.assertEqual(process_only, 2)
        self.assertEqual(mem_unknown, 0)

    def test_02_missing_cwd_counts_as_unknown_never_not_found(self):
        # Rows: no cwd anywhere in the transcript (test_02), and a cwd that is not a git repo.
        # Named failure: a wrong count reads as "lost", never as not-found.
        not_a_repo = os.path.join(self.tmp.name, "plain-dir")
        os.makedirs(not_a_repo, exist_ok=True)
        cases = [
            ("no cwd", "proj_no_cwd", human("start")),
            ("cwd not a git repo", "proj_bad_cwd", human("start", cwd=not_a_repo)),
        ]
        for case, name, first in cases:
            with self.subTest(case):
                project_dir = self.make_project(name)
                os.makedirs(os.path.join(project_dir, "memory"), exist_ok=True)
                records = [
                    first,
                    tool_use_msg("Write", {
                        "file_path": os.path.join(project_dir, "memory", "plan.md"),
                        "content": "this sentence has plenty of words to clear the reach floor\n",
                    }, id_="write_1"),
                    tool_result_msg("write_1"),
                ]
                path = write_transcript(records, os.path.join(project_dir, "s1.jsonl"))
                timeouts = [0]
                counts = ruling_census.scan_transcript(path, project_dir, timeouts)
                self.assertEqual(counts["unknown"], 1)
                self.assertEqual(counts["reach_not_found"], 0)
                self.assertEqual(counts["reach_found"], 0)

    def test_09_whitespace_collapse_finds_a_differently_spaced_line(self):
        # The repo commit holds the phrase with single spaces. The memory-write line is
        # authored with irregular whitespace (double spaces, one tab). The reach test must
        # collapse both to the same run of single spaces before it asks git, or a line that
        # only differs in whitespace reads as lost when it is not.
        project_dir = self.make_project("proj_whitespace")
        os.makedirs(os.path.join(project_dir, "memory"), exist_ok=True)
        spaced_line = "the   repo  already\tholds this exact   spoken sentence here"
        records = [
            human("start", cwd=self.repo),
            tool_use_msg("Write", {
                "file_path": os.path.join(project_dir, "memory", "plan.md"),
                "content": spaced_line + "\n",
            }, id_="write_1"),
            tool_result_msg("write_1"),
        ]
        path = write_transcript(records, os.path.join(project_dir, "s1.jsonl"))
        timeouts = [0]
        counts = ruling_census.scan_transcript(path, project_dir, timeouts)
        self.assertEqual(counts["reach_found"], 1)
        self.assertEqual(counts["reach_not_found"], 0)
        self.assertEqual(counts["unknown"], 0)

    # ---------------------------------------------------------- --since filtering

    def test_03_since_filters_out_older_sessions(self):
        project_dir = self.make_project("proj_dates")
        old_path = write_transcript(
            [human("old", cwd=self.repo)], os.path.join(project_dir, "old.jsonl"))
        new_path = write_transcript(
            [human("new", cwd=self.repo)], os.path.join(project_dir, "new.jsonl"))
        old_epoch = 1_600_000_000  # 2020-09-13, well before any --since date this test uses
        os.utime(old_path, (old_epoch, old_epoch))

        timeouts = [0]
        rows_all, total_all = ruling_census.run_census(self.root, None, timeouts)
        self.assertEqual(dict(rows_all)["proj_dates"]["sessions"], 2)

        since = ruling_census.datetime.strptime("2026-01-01", "%Y-%m-%d").date()
        rows_since, total_since = ruling_census.run_census(self.root, since, timeouts)
        self.assertEqual(dict(rows_since)["proj_dates"]["sessions"], 1)
        self.assertEqual(total_since["sessions"], 1)
        del new_path  # only used to make the fixture explicit

    # ---------------------------------------------------------- CLI: --json shape, table run

    def test_04_json_output_shape(self):
        project_dir = self.make_project("proj_json")
        write_transcript([human("hi", cwd=self.repo)], os.path.join(project_dir, "s1.jsonl"))
        run = subprocess.run(
            [sys.executable, CENSUS, "--root", self.root, "--json"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        self.assertEqual(out["root"], self.root)
        self.assertIsNone(out["since"])
        self.assertIn("timed_out", out)
        self.assertIn("note", out)
        self.assertIn("total", out)
        self.assertEqual(out["total"]["project"], "TOTAL")
        names = [p["project"] for p in out["projects"]]
        self.assertIn("proj_json", names)
        for key in ("sessions", "agent_transcripts", "answers", "memory_writes",
                    "scratchpad_writes", "ruling_lines", "process_only_lines",
                    "reach_found", "reach_not_found", "unknown"):
            self.assertIn(key, out["total"])
        # An empty root still prints a zero TOTAL in table mode.
        # Named failure: an empty root crashes the census instead of printing its total.
        empty_root = os.path.join(self.tmp.name, "no-such-root")
        empty = subprocess.run(
            [sys.executable, CENSUS, "--root", empty_root],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(empty.returncode, 0)
        self.assertIn("TOTAL", empty.stdout)

    def test_05_table_run_prints_header_total_and_note(self):
        project_dir = self.make_project("proj_table")
        write_transcript([human("hi", cwd=self.repo)], os.path.join(project_dir, "s1.jsonl"))
        run = subprocess.run(
            [sys.executable, CENSUS, "--root", self.root],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(run.returncode, 0)
        self.assertIn("project", run.stdout)
        self.assertIn("agent transcripts", run.stdout)
        self.assertIn("TOTAL", run.stdout)
        self.assertIn(ruling_census.NOT_FOUND_NOTE, run.stdout)
        self.assertIn("Timed out:", run.stdout)

    def test_07_agent_transcript_folds_in_but_is_not_a_session(self):
        # An agent transcript lives at <project>/<session-id>/subagents/*.jsonl. Its memory
        # writes, scratchpad writes and answers count. Its own session slot does not: only
        # the top-level *.jsonl files are sessions. Its "ruling" lines are not folded in
        # either (see the module docstring).
        project_dir = self.make_project("proj_nested")
        write_transcript([human("top", cwd=self.repo)],
                          os.path.join(project_dir, "top.jsonl"))
        agent_dir = os.path.join(project_dir, "top", "subagents")
        os.makedirs(agent_dir, exist_ok=True)
        agent_records = [
            human("child", cwd=self.repo),
            tool_use_msg("Write", {
                "file_path": "/tmp/scratchpad/child.txt",
                "content": "an agent scratch note",
            }, id_="w_write_1"),
            tool_result_msg("w_write_1"),
            tool_use_msg("AskUserQuestion", {"questions": [{"question": "Q?"}]},
                         id_="w_ask_1"),
            tool_result_msg("w_ask_1",
                             'Your questions have been answered: "Q?"="Yes". Continue.'),
            assistant_text("An agent line about a ruling that should not be folded in."),
        ]
        write_transcript(agent_records, os.path.join(agent_dir, "child.jsonl"))

        timeouts = [0]
        rows, _total = ruling_census.run_census(self.root, None, timeouts)
        counts = dict(rows)["proj_nested"]
        self.assertEqual(counts["sessions"], 1)
        self.assertEqual(counts["agent_transcripts"], 1)
        self.assertEqual(counts["scratchpad_writes"], 1)
        self.assertEqual(counts["answers"], 1)
        self.assertEqual(counts["ruling_lines"], 0)

    # ---------------------------------------------------------- fix 1: no crash on bad input

    def test_10_non_utf8_transcript_counts_unknown_and_keeps_going(self):
        project_dir = self.make_project("proj_bad_transcript")
        bad_path = os.path.join(project_dir, "bad.jsonl")
        with open(bad_path, "wb") as f:
            f.write(b'{"type": "user", "message": {"content": "\xff\xfe broken"}}\n')
        good_path = write_transcript([human("ok", cwd=self.repo)],
                                      os.path.join(project_dir, "good.jsonl"))
        del good_path

        timeouts = [0]
        rows, total = ruling_census.run_census(self.root, None, timeouts)
        counts = dict(rows)["proj_bad_transcript"]
        self.assertEqual(counts["sessions"], 2)
        self.assertEqual(counts["unknown"], 1)

    def test_11_non_utf8_memory_file_and_ds_store_are_skipped_not_crashed(self):
        project_dir = self.make_project("proj_bad_memory")
        memory_dir = os.path.join(project_dir, "memory")
        os.makedirs(memory_dir, exist_ok=True)
        with open(os.path.join(memory_dir, ".DS_Store"), "wb") as f:
            f.write(b"\x00\x01\xff\xfe binary junk, not utf-8 and not markdown")
        with open(os.path.join(memory_dir, "bad.md"), "wb") as f:
            f.write(b"home: \xff\xfe process-only broken bytes")
        with open(os.path.join(memory_dir, "good.md"), "w", encoding="utf-8") as f:
            f.write("home: process-only\n")

        process_only, unknown = ruling_census.scan_memory_folder(project_dir)
        self.assertEqual(process_only, 1)
        self.assertEqual(unknown, 1)  # only bad.md, .DS_Store is never opened (not .md)

    def test_12b_tool_use_input_not_an_object_counts_unknown_not_crash(self):
        # Rows: an `input` that is a list (test_12b: must not crash the census with AttributeError on
        # `inp.get(...)`), and a `file_path` that is a list. Both are skipped and
        # counted as unknown. Named failure: a malformed tool use crashes the census or counts as a write.
        cases = [
            ("input not an object", "proj_bad_input", ["not", "an", "object"]),
            ("file_path not a string", "proj_bad_path", {"file_path": ["not", "a", "string"], "content": "x"}),
        ]
        for case, name, tool_input in cases:
            with self.subTest(case):
                project_dir = self.make_project(name)
                os.makedirs(os.path.join(project_dir, "memory"), exist_ok=True)
                records = [
                    human("start", cwd=self.repo),
                    tool_use_msg("Write", tool_input, id_="write_1"),
                    tool_result_msg("write_1"),
                ]
                path = write_transcript(records, os.path.join(project_dir, "s1.jsonl"))
                timeouts = [0]
                counts = ruling_census.scan_transcript(path, project_dir, timeouts)
                self.assertEqual(counts["memory_writes"], 0)
                self.assertEqual(counts["scratchpad_writes"], 0)
                self.assertEqual(counts["unknown"], 1)

    # ---------------------------------------------------------- fix 2: relative --root

    def test_13_relative_root_still_finds_memory_writes(self):
        project_dir = self.make_project("proj_relative")
        memory_dir = os.path.join(project_dir, "memory")
        os.makedirs(memory_dir, exist_ok=True)
        records = [
            human("start", cwd=self.repo),
            tool_use_msg("Write", {
                "file_path": os.path.join(memory_dir, "plan.md"),
                "content": "short note",
            }, id_="write_1"),
            tool_result_msg("write_1"),
        ]
        write_transcript(records, os.path.join(project_dir, "s1.jsonl"))

        parent = os.path.dirname(self.root)
        rel_root = os.path.relpath(self.root, parent)
        run = subprocess.run(
            [sys.executable, CENSUS, "--root", rel_root, "--json"],
            capture_output=True, text=True, timeout=30, cwd=parent,
        )
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        self.assertTrue(os.path.isabs(out["root"]))
        proj = dict((p["project"], p) for p in out["projects"])["proj_relative"]
        self.assertEqual(proj["memory_writes"], 1)

    # ---------------------------------------------------------- fix 3: scratchpad is writes only

    def test_14_bash_touching_scratchpad_is_not_counted(self):
        # Rows: a Bash command (test_14) and a Read of a scratchpad path.
        # Named failure: a read of a scratchpad counted as a scratchpad write.
        cases = [
            ("bash", "proj_bash_scratchpad",
             tool_use_msg("Bash", {"command": "cat /tmp/x/scratchpad/notes.txt"}, id_="bash_1"), "bash_1"),
            ("read", "proj_read_scratchpad",
             tool_use_msg("Read", {"file_path": "/tmp/x/scratchpad/notes.txt"}, id_="read_1"), "read_1"),
        ]
        for case, name, use, use_id in cases:
            with self.subTest(case):
                project_dir = self.make_project(name)
                records = [human("start", cwd=self.repo), use, tool_result_msg(use_id)]
                path = write_transcript(records, os.path.join(project_dir, "s1.jsonl"))
                timeouts = [0]
                counts = ruling_census.scan_transcript(path, project_dir, timeouts)
                self.assertEqual(counts["scratchpad_writes"], 0)

    def test_15_windows_scratchpad_path_is_normalized(self):
        project_dir = self.make_project("proj_windows_scratchpad")
        records = [
            human("start", cwd=self.repo),
            tool_use_msg("Write", {
                "file_path": r"C:\Users\x\scratchpad\notes.txt",
                "content": "a note",
            }, id_="write_1"),
            tool_result_msg("write_1"),
        ]
        path = write_transcript(records, os.path.join(project_dir, "s1.jsonl"))
        timeouts = [0]
        counts = ruling_census.scan_transcript(path, project_dir, timeouts)
        self.assertEqual(counts["scratchpad_writes"], 1)

    # ---------------------------------------------------------- fix 5: the hook's home: pattern

    def test_17_process_only_line_shapes(self):
        good = [
            "home: process-only",
            "home:process-only",
            "- home: process-only",
            "* home: `process-only`",
            '* home: "process-only"',
            "HOME: process-only",
        ]
        for line in good:
            self.assertTrue(ruling_census.is_process_only_line(line), line)
        bad = [
            "home: Process-Only",  # value case must match exactly
            "home: decisions/real.md",
            "not a home line",
            "home: ``process-only``",  # more than one pair of fences
        ]
        for line in bad:
            self.assertFalse(ruling_census.is_process_only_line(line), line)

    # ------------------------------------------ fix: symlinked root vs. real file_path
    # macOS puts TMPDIR under /var, itself a symlink to /private/var. A plain string
    # prefix match can see the project folder spelled one way and a memory write's own
    # file_path spelled the other way, and count a real memory write as none at all.

    def _make_symlink_pair(self, real_name, link_name):
        real_base = os.path.join(self.tmp.name, real_name)
        os.makedirs(real_base)
        link_base = os.path.join(self.tmp.name, link_name)
        try:
            os.symlink(real_base, link_base)
        except OSError:
            raise unittest.SkipTest(
                "os.symlink needs elevated privilege or Developer Mode on this platform")
        return real_base, link_base

    def test_18_root_via_symlink_file_path_via_real_path_still_matches(self):
        # Rows: the root through the symlink with the file path real (test_18), and the mirror
        # with the root real and the file path through the symlink.
        # Named failure: a memory write is missed when the root and file path are spelled differently.
        cases = [
            ("root via link, file via real", "real_projects", "link_projects", "proj_symlink", "real"),
            ("root real, file via link", "real_projects2", "link_projects2", "proj_symlink2", "link"),
        ]
        for case, real_name, link_name, proj, file_side in cases:
            with self.subTest(case):
                real_base, link_base = self._make_symlink_pair(real_name, link_name)
                root_base = link_base if file_side == "real" else real_base
                file_base = real_base if file_side == "real" else link_base
                project_dir = os.path.join(root_base, proj)
                os.makedirs(project_dir)
                memory_dir = os.path.join(file_base, proj, "memory")
                os.makedirs(memory_dir)
                records = [
                    human("start", cwd=self.repo),
                    tool_use_msg("Write", {
                        "file_path": os.path.join(memory_dir, "plan.md"),
                        "content": "a short note",
                    }, id_="write_1"),
                    tool_result_msg("write_1"),
                ]
                path = write_transcript(records, os.path.join(project_dir, "s1.jsonl"))
                timeouts = [0]
                counts = ruling_census.scan_transcript(path, project_dir, timeouts)
                self.assertEqual(counts["memory_writes"], 1)

    # ---------------------------------------------------------- --sample

    def test_20_sample_pairs_answer_with_its_own_question(self):
        # Two questions in one AskUserQuestion call. The result string carries both
        # "question"="answer" pairs. The right pairing is positional (answer i with
        # question i), read from the tool_use's own input, not by re-parsing the
        # flattened result text.
        project_dir = self.make_project("proj_sample_pair")
        records = [
            human("start", cwd=self.repo),
            tool_use_msg("AskUserQuestion", {
                "questions": [{"question": "Q_A?"}, {"question": "Q_B?"}],
            }, id_="ask_1"),
            tool_result_msg(
                "ask_1",
                'The user answered: "Q_A?"="Answer A", "Q_B?"="Answer B". Continue.',
            ),
        ]
        write_transcript(records, os.path.join(project_dir, "s1.jsonl"))
        pools = ruling_census.collect_sample_pools(self.root)
        items = pools["proj_sample_pair"]
        self.assertEqual(len(items), 2)
        by_answer = {item["answer"]: item["question"] for item in items}
        self.assertEqual(by_answer["Answer A"], "Q_A?")
        self.assertEqual(by_answer["Answer B"], "Q_B?")

    def test_21_same_seed_gives_the_same_sample(self):
        for i in range(6):
            project_dir = self.make_project("proj_seed_%d" % i)
            records = [
                human("start", cwd=self.repo),
                tool_use_msg("AskUserQuestion", {"questions": [{"question": "Q?"}]},
                             id_="ask_1"),
                tool_result_msg("ask_1", 'Answered: "Q?"="Answer %d". Continue.' % i),
            ]
            write_transcript(records, os.path.join(project_dir, "s1.jsonl"))
        pools = ruling_census.collect_sample_pools(self.root)
        first = ruling_census.pick_sample(pools, 4, seed=7)
        second = ruling_census.pick_sample(pools, 4, seed=7)
        self.assertEqual(first, second)
        third = ruling_census.pick_sample(pools, 4, seed=8)
        self.assertNotEqual(first, third)

    def test_22_picks_spread_across_two_projects(self):
        # Distinct answer text per project (the folder name is baked into it), so a pick
        # can be traced back to its own project without relying on dict identity.
        for name in ("proj_spread_a", "proj_spread_b"):
            project_dir = self.make_project(name)
            records = [human("start", cwd=self.repo)]
            for i in range(3):
                records.append(tool_use_msg(
                    "AskUserQuestion", {"questions": [{"question": "Q %s %d?" % (name, i)}]},
                    id_="ask_%d" % i))
                records.append(tool_result_msg(
                    "ask_%d" % i,
                    'Answered: "Q %s %d?"="A %s %d". Continue.' % (name, i, name, i)))
            write_transcript(records, os.path.join(project_dir, "s1.jsonl"))
        pools = ruling_census.collect_sample_pools(self.root)
        picked = ruling_census.pick_sample(pools, 4, seed=1)
        self.assertEqual(len(picked), 4)
        projects_seen = {item["project"] for item in picked}
        self.assertEqual(projects_seen, {self.repo})
        # both fixture projects contributed at least one of the four picks
        sessions_seen = {"proj_spread_a" if "proj_spread_a" in item["answer"]
                          else "proj_spread_b" for item in picked}
        self.assertEqual(sessions_seen, {"proj_spread_a", "proj_spread_b"})

    def test_23_missing_cwd_gives_remote_null(self):
        project_dir = self.make_project("proj_sample_no_cwd")
        records = [
            human("start"),  # no cwd anywhere
            tool_use_msg("AskUserQuestion", {"questions": [{"question": "Q?"}]},
                         id_="ask_1"),
            tool_result_msg("ask_1", 'Answered: "Q?"="Yes". Continue.'),
        ]
        write_transcript(records, os.path.join(project_dir, "s1.jsonl"))
        pools = ruling_census.collect_sample_pools(self.root)
        item = pools["proj_sample_no_cwd"][0]
        self.assertIsNone(item["project"])
        self.assertIsNone(item["remote"])

    def test_25_sample_cli_prints_capped_jsonl(self):
        project_dir = self.make_project("proj_sample_cli")
        long_answer = "y" * 2500
        records = [
            human("start", cwd=self.repo),
            tool_use_msg("AskUserQuestion", {"questions": [{"question": "Q?"}]},
                         id_="ask_1"),
            tool_result_msg("ask_1", 'Answered: "Q?"="%s". Continue.' % long_answer),
        ]
        write_transcript(records, os.path.join(project_dir, "s1.jsonl"))
        run = subprocess.run(
            [sys.executable, CENSUS, "--root", self.root, "--sample", "1"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(run.returncode, 0)
        lines = [ln for ln in run.stdout.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1)
        row = json.loads(lines[0])
        for key in ("project", "remote", "session", "timestamp", "question", "answer"):
            self.assertIn(key, row)
        self.assertEqual(row["project"], self.repo)
        self.assertEqual(row["question"], "Q?")
        self.assertTrue(row["answer"].endswith(ruling_census.SAMPLE_CUT_MARK))
        self.assertEqual(len(row["answer"]),
                          ruling_census.SAMPLE_TEXT_MAX + len(ruling_census.SAMPLE_CUT_MARK))
        # cap_text cuts a long field to the cap plus the mark, keeps a short one.
        # Named failure: a long answer printed whole, or a short one cut.
        self.assertEqual(len(ruling_census.cap_text("x" * 2500)),
                         ruling_census.SAMPLE_TEXT_MAX + len(ruling_census.SAMPLE_CUT_MARK))
        self.assertTrue(ruling_census.cap_text("x" * 2500).endswith(ruling_census.SAMPLE_CUT_MARK))
        self.assertEqual(ruling_census.cap_text("short text"), "short text")
        self.assertIsNone(ruling_census.cap_text(None))

    def test_26_sample_includes_agent_transcript_answers(self):
        project_dir = self.make_project("proj_sample_agent")
        write_transcript([human("top", cwd=self.repo)],
                          os.path.join(project_dir, "top.jsonl"))
        agent_dir = os.path.join(project_dir, "top", "subagents")
        os.makedirs(agent_dir, exist_ok=True)
        agent_records = [
            human("child", cwd=self.repo),
            tool_use_msg("AskUserQuestion", {"questions": [{"question": "WQ?"}]},
                         id_="w_ask_1"),
            tool_result_msg("w_ask_1", 'Answered: "WQ?"="Agent answer". Continue.'),
        ]
        write_transcript(agent_records, os.path.join(agent_dir, "child.jsonl"))
        pools = ruling_census.collect_sample_pools(self.root)
        answers = {item["answer"] for item in pools["proj_sample_agent"]}
        self.assertIn("Agent answer", answers)

    def test_27_present_only_keeps_only_the_present_project(self):
        # proj_present_missing's cwd points at a directory that does not exist on this
        # machine. proj_present_real's cwd is self.repo, a real git repo. --present-only
        # must keep every pick from proj_present_real and skip both of the other project's
        # answers, and report the skip count on stderr.
        gone_cwd = os.path.join(self.tmp.name, "gone-repo")
        for name, cwd, tag in (
            ("proj_present_missing", gone_cwd, "missing"),
            ("proj_present_real", self.repo, "real"),
        ):
            project_dir = self.make_project(name)
            records = [human("start", cwd=cwd)]
            for i in range(2):
                records.append(tool_use_msg(
                    "AskUserQuestion", {"questions": [{"question": "Q %s %d?" % (tag, i)}]},
                    id_="ask_%d" % i))
                records.append(tool_result_msg(
                    "ask_%d" % i, 'Answered: "Q %s %d?"="A %s %d". Continue.' % (
                        tag, i, tag, i)))
            write_transcript(records, os.path.join(project_dir, "s1.jsonl"))

        run = subprocess.run(
            [sys.executable, CENSUS, "--root", self.root, "--sample", "4",
             "--present-only"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(run.returncode, 0)
        lines = [ln for ln in run.stdout.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 2)  # only proj_present_real's 2 answers are present
        for line in lines:
            row = json.loads(line)
            self.assertEqual(row["project"], self.repo)
            self.assertIn("real", row["answer"])
        self.assertIn("Skipped 2 candidate answer(s)", run.stderr)

if __name__ == "__main__":
    unittest.main()

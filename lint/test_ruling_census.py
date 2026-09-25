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
            tool_use_msg("Bash", {"command": "cat /tmp/x/scratchpad/notes.txt"}, id_="bash_1"),
            tool_result_msg("bash_1"),
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

        process_only = ruling_census.scan_memory_folder(project_dir)
        self.assertEqual(process_only, 2)

    def test_02_missing_cwd_counts_as_unknown_never_not_found(self):
        project_dir = self.make_project("proj_no_cwd")
        os.makedirs(os.path.join(project_dir, "memory"), exist_ok=True)
        records = [
            human("start"),  # no cwd at all anywhere in this transcript
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

    def test_08_cwd_not_a_git_repo_counts_as_unknown(self):
        project_dir = self.make_project("proj_bad_cwd")
        os.makedirs(os.path.join(project_dir, "memory"), exist_ok=True)
        not_a_repo = os.path.join(self.tmp.name, "plain-dir")
        os.makedirs(not_a_repo, exist_ok=True)
        records = [
            human("start", cwd=not_a_repo),
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
        for key in ("sessions", "answers", "memory_writes", "scratchpad_writes",
                    "ruling_lines", "process_only_lines", "reach_found",
                    "reach_not_found", "unknown"):
            self.assertIn(key, out["total"])

    def test_05_table_run_prints_header_total_and_note(self):
        project_dir = self.make_project("proj_table")
        write_transcript([human("hi", cwd=self.repo)], os.path.join(project_dir, "s1.jsonl"))
        run = subprocess.run(
            [sys.executable, CENSUS, "--root", self.root],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(run.returncode, 0)
        self.assertIn("project", run.stdout)
        self.assertIn("TOTAL", run.stdout)
        self.assertIn(ruling_census.NOT_FOUND_NOTE, run.stdout)
        self.assertIn("Timed out:", run.stdout)

    def test_06_empty_root_still_prints_a_zero_total(self):
        empty_root = os.path.join(self.tmp.name, "no-such-root")
        run = subprocess.run(
            [sys.executable, CENSUS, "--root", empty_root],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(run.returncode, 0)
        self.assertIn("TOTAL", run.stdout)

    def test_07_nested_subagent_jsonl_is_not_a_second_session(self):
        # A project folder's own subagents/ subfolder holds child transcripts. Only the
        # `*.jsonl` files directly inside the project folder are sessions.
        project_dir = self.make_project("proj_nested")
        write_transcript([human("top", cwd=self.repo)], os.path.join(project_dir, "top.jsonl"))
        nested_dir = os.path.join(project_dir, "subagents")
        os.makedirs(nested_dir, exist_ok=True)
        write_transcript([human("child", cwd=self.repo)],
                          os.path.join(nested_dir, "child.jsonl"))
        timeouts = [0]
        rows, _total = ruling_census.run_census(self.root, None, timeouts)
        self.assertEqual(dict(rows)["proj_nested"]["sessions"], 1)


if __name__ == "__main__":
    unittest.main()

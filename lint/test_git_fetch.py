"""Fixture suite for lint/git_fetch.py: failure_message picks the line that says why a `git fetch` failed. Stdlib only.

    python3 lint/test_git_fetch.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import git_fetch  # noqa: E402  the one home of a git fetch (lint/git_fetch.py)


class FailureMessageTests(unittest.TestCase):
    """failure_message returns the first fatal: or error: line, else the whole short stderr. Git's last line is often a
    hint, so the last line is the wrong pick."""

    def test_a_fatal_line_before_two_hint_lines_returns_the_fatal_line(self):
        stderr = ("Cloning into 'mirror'...\n"
                  "fatal: repository 'https://example.invalid/none.git/' not found\n"
                  "hint: check the remote URL.\n"
                  "hint: and that the repository exists.\n")
        self.assertEqual(git_fetch.failure_message(stderr, 128),
                         "fatal: repository 'https://example.invalid/none.git/' not found",
                         "failure_message did not return the fatal line over the hint lines after it")

    def test_an_error_line_is_the_failure_line_too(self):
        stderr = "error: pathspec 'main' did not match any file(s) known to git\nhint: did you mean 'master'?\n"
        self.assertEqual(git_fetch.failure_message(stderr, 1),
                         "error: pathspec 'main' did not match any file(s) known to git",
                         "failure_message did not return the error line over the hint line after it")

    def test_the_first_fatal_or_error_line_wins_over_a_later_one(self):
        stderr = "error: first problem\nfatal: second problem\nhint: a hint\n"
        self.assertEqual(git_fetch.failure_message(stderr, 128), "error: first problem",
                         "failure_message did not keep the first fatal or error line")

    def test_without_a_fatal_or_error_line_the_whole_short_message_is_returned(self):
        stderr = "  warning: redirecting to a new host  \n  hint: pass --no-redirect to stay on this one\n"
        self.assertEqual(git_fetch.failure_message(stderr, 1),
                         "warning: redirecting to a new host hint: pass --no-redirect to stay on this one",
                         "failure_message did not join the stripped stderr lines when no fatal or error line exists")

    def test_a_long_stderr_without_a_fatal_or_error_line_is_joined_whole(self):
        lines = ["note: step %d" % number for number in range(60)]
        self.assertEqual(git_fetch.failure_message("\n".join(lines) + "\n", 1), " ".join(lines),
                         "failure_message did not join all 60 stderr lines when no fatal or error line exists")

    def test_empty_stderr_returns_the_exit_code_with_no_message(self):
        self.assertEqual(git_fetch.failure_message("", 128), "exit 128, no message",
                         "empty stderr did not return the exit code with no message")

    def test_blank_stderr_counts_as_empty(self):
        self.assertEqual(git_fetch.failure_message("\n   \n\t\n", 1), "exit 1, no message",
                         "whitespace-only stderr did not return the exit code with no message")


if __name__ == "__main__":
    unittest.main()

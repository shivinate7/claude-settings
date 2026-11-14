#!/usr/bin/env python3
"""Decision session-messages, "One route" (owner, 2026-11-10 09:33 CST, page item 482): every message between sessions goes
through the git mailbox, cloud to cloud included. A cloud `send_message` leaves no copy and "delivered" is not a read.
The route the skill gives a cloud session must be `mail send`; the timed check-in (page item 484) is the only wake it names.
The doorbell is open, so the skill must not build one into the route."""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROUTING = os.path.join(HERE, "reference", "routing-and-sessions.md")
DECISION = os.path.join(os.path.dirname(os.path.dirname(HERE)), "docs", "decisions", "session-messages.md")


def section(text, heading):
    start = text.index(heading)
    rest = text[start + len(heading):]
    stop = re.search(r"^## ", rest, re.M)
    return rest[:stop.start()] if stop else rest


class CloudRoute(unittest.TestCase):
    def cloud_item(self):
        with open(ROUTING, encoding="utf-8") as handle:
            block = section(handle.read(), "## Message another session")
        found = [item for item in re.split(r"\n(?=- )", block) if item.startswith("- Cloud to cloud")]
        self.assertEqual(len(found), 1, "the section has %d 'Cloud to cloud' bullets, not 1" % len(found))
        return found[0]

    def test_cloud_to_cloud_goes_by_mail_send(self):
        item = self.cloud_item()
        self.assertIn("mail send", item, "the cloud-to-cloud route does not name `mail send`: %r" % item)

    def test_cloud_to_cloud_does_not_route_by_send_message(self):
        item = self.cloud_item()
        self.assertNotRegex(item, r"send_message",
                            "the cloud-to-cloud route names cloud send_message, which leaves no copy: %r" % item)

    def test_cloud_to_cloud_names_the_check_in_and_the_open_doorbell(self):
        item = self.cloud_item()
        self.assertIn("send_later", item, "the cloud-to-cloud route names no timed check-in (page item 484): %r" % item)
        self.assertIn("doorbell", item.lower(), "the route does not say the doorbell is open: %r" % item)

    def test_the_address_is_found_without_the_device(self):
        item = self.cloud_item()
        self.assertIn("cloud/session_", item, "the route does not give the cloud address form: %r" % item)
        self.assertNotIn("cloud/session_<id>`, never", item)
        self.assertNotRegex(item, r"--to cloud/session_<id>.*from the `list_sessions` row", "the route doubles the session_ prefix")

    def test_the_route_says_it_needs_the_store(self):
        self.assertIn("MAILBOX_REPO", self.cloud_item(), "the route does not say it needs MAILBOX_REPO in the env")


class DecisionState(unittest.TestCase):
    def test_state_line_no_longer_says_the_code_sends_by_send_message(self):
        with open(DECISION, encoding="utf-8") as handle:
            text = handle.read()
        self.assertNotIn("the code still sends cloud to cloud by `send_message`", text,
                         "the decision's State line is stale: the build has landed")
        state = [line for line in text.splitlines() if line.startswith("State: `mail send`")]
        self.assertEqual(len(state), 1, "the State line is missing")
        self.assertIn("MAILBOX_REPO", state[0], "the State line claims the mailbox route without its env condition")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Pick the runner labels for the integration PR's CI run's macOS jobs (R58). Writes `mac_runner=<JSON list>` to $GITHUB_OUTPUT.

The owner's Mac (label claude-settings-mac) runs a macOS job only when all of these hold: the run is a pull request,
its head branch starts with batch-, its head repo is this repo (never a fork), and the runners list shows a runner
with that label online. Anything else, or a list that cannot be read, picks macos-latest: a job queued for an offline
self-hosted runner would wait for a day, so an unknown read must never pick it.

Env: EVENT, HEAD_REF, HEAD_REPO, REPO, RUNNER_TOKEN (a token that can read the repo's runners list).
A read that fails (a 403 means the token lacks Administration: read) falls back and says so: a ::warning:: line and a job-summary line naming the status. A read that works prints its status. No token makes no read and stays quiet.
RUNNERS_JSON stands in for the API answer, and API_URL for the API host, in tests.
"""
import json
import os
import sys
import urllib.error
import urllib.request

SELF_HOSTED = ["self-hosted", "macOS", "claude-settings-mac"]
FALLBACK = ["macos-latest"]


class NoToken(Exception):
    """No token is set, so no read is made. Quiet on purpose: it is the state before the owner adds the secret."""


def warn(text):
    """A GitHub warning annotation on stdout and a line in the job summary. The pick still falls back."""
    print("::warning::mac-runner: %s; falling back to macos-latest" % text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with open(summary, "a", encoding="utf-8") as f:
                f.write("mac-runner: %s; falling back to macos-latest\n" % text)
        except OSError as e:  # the summary is a courtesy; a bad path must not fail the pick
            print("mac-runner: job summary not written (%s)" % e)


def runners_json():
    given = os.environ.get("RUNNERS_JSON")
    if given:
        return given
    token = os.environ.get("RUNNER_TOKEN", "")
    if not token:
        raise NoToken("no RUNNER_TOKEN, so the runners list is not read")
    req = urllib.request.Request(
        "%s/repos/%s/actions/runners?per_page=100" % (os.environ.get("API_URL", "https://api.github.com"), os.environ["REPO"]),
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        print("mac-runner: runners read status %d" % r.status)
        return r.read().decode("utf-8")


def mac_online(text):
    runners = json.loads(text).get("runners")
    if not isinstance(runners, list):
        raise ValueError("the answer has no runners list")
    for runner in runners:
        names = {label.get("name") for label in runner.get("labels", [])}
        if runner.get("status") == "online" and "claude-settings-mac" in names:
            return True
    return False


def pick():
    env = os.environ
    if env.get("EVENT") != "pull_request":
        return FALLBACK, "not a pull request run"
    if not env.get("HEAD_REF", "").startswith("batch-"):
        return FALLBACK, "head branch does not start with batch-"
    if env.get("HEAD_REPO") != env.get("REPO"):
        return FALLBACK, "head repo is not this repo (a fork never reaches the self-hosted runner)"
    try:
        online = mac_online(runners_json())
    except NoToken as e:
        return FALLBACK, "runners list unknown (%s)" % e
    except urllib.error.HTTPError as e:  # 403 means the token lacks Administration: read
        warn("runners read status %d%s" % (e.code, " (the token needs Administration: read)" if e.code == 403 else ""))
        return FALLBACK, "runners list unknown (status %d)" % e.code
    except Exception as e:  # an unknown read falls back, and says why
        warn("runners read failed (%s)" % e)
        return FALLBACK, "runners list unknown (%s)" % e
    return (SELF_HOSTED, "claude-settings-mac is online") if online else (FALLBACK, "claude-settings-mac is offline")


def main():
    labels, why = pick()
    print("mac-runner: %s -> %s" % (why, json.dumps(labels)))
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write("mac_runner=%s\n" % json.dumps(labels))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Print the roadmap page as build.py writes it from a fixture repo, for tests/page.test.mjs.

    python3 skills/roadmap/tests/built_index.py [--data JSON] [--live JSON]

Builds page/index.html (skills/roadmap/build.py --out) from the fixture roadmap repo and prints the page. With
--data JSON the steps and meta docs are the ones the JSON names, {"steps": {file stem: step}, "meta": {file stem:
doc}}, in place of the built-in ones. With --live JSON the live-work file's text is written and handed to the build
with --live, as the publisher does. The fixture repo is the one in skills/roadmap/test_build.py (make_repo). Its
folder is this run's folder from lint/_test_temp.py, removed before the script ends (decision test-temp-standard).
A build that fails prints its stderr and exits 1, so a missing builder reads as that, not as a blank page.
"""
import argparse
import json
import os
import pathlib
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
GITHUB = "fixture-owner/roadmap-fixture"  # the fixture repo's GitHub name, as its origin remote gives it
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "skills" / "roadmap"))
sys.path.insert(1, str(ROOT / "lint"))
sys.path.insert(2, str(ROOT / "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
import _test_temp  # noqa: E402
import test_build  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help='the steps and meta docs to bake, as JSON {"steps": {file stem: step}, "meta": {file stem: doc}}')
    ap.add_argument("--live", help="the live-work file's text, as JSON: build.py --live reads it")
    args = ap.parse_args()
    fixture = json.loads(args.data) if args.data else {}
    folder = _test_temp.run_folder()
    try:
        repo = test_build.make_repo(folder, steps=fixture.get("steps"), meta=fixture.get("meta"))
        test_build.git(repo, "checkout", "-q", "main")
        # The build names the repo for the live file's sessions. Without a GitHub name the stalled read is unknown.
        test_build.git(repo, "remote", "add", "origin", "https://github.com/" + GITHUB + ".git")
        page = os.path.join(folder, "page.html")
        build = [sys.executable, str(ROOT / "skills" / "roadmap" / "build.py"), "--repo", str(repo), "--out", page]
        if args.live:
            live = os.path.join(folder, "live.json")
            with open(live, "w", encoding="utf-8") as f:
                f.write(args.live)
            build += ["--live", live]
        # Exit 1 is a red line (an unread or stalled part): the build still wrote the page.
        done = _nowindow.run(build, capture_output=True, text=True, encoding="utf-8")
        if done.returncode not in ((0, 1) if args.live else (0,)):
            sys.stderr.write("the roadmap build failed (exit %d): %s\n%s%s" % (done.returncode, " ".join(build), done.stdout, done.stderr))
            raise SystemExit(1)
        with open(page, "rb") as f:
            sys.stdout.buffer.write(f.read())
    finally:
        shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    main()

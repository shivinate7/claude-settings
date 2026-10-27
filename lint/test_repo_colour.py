#!/usr/bin/env python3
"""Cases for lint/repo_colour.py. Standard library only.

    python3 lint/test_repo_colour.py

The script gives each repo one colour: the registry's colour when the repo has one, else a hue
drawn from the name that keeps clear of the state hues and of every other repo's hue.
REPO_COLOUR_UNDER_TEST overrides the module path, so the cases run against another copy.
"""
import colorsys
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.environ.get("REPO_COLOUR_UNDER_TEST") or os.path.join(HERE, "repo_colour.py")
REGISTRY = os.path.join(os.path.dirname(HERE), "docs", "design", "repo-colours.json")
HEX = "0123456789abcdef"


def load():
    spec = importlib.util.spec_from_file_location("repo_colour", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def dist(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


class RepoColour(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rc = load()
        with open(REGISTRY, encoding="utf-8") as f:
            cls.reg = json.load(f)
        cls.rule = cls.reg["rule"]

    def write_registry(self, tmp, repos):
        path = os.path.join(tmp, "repo-colours.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"rule": self.rule, "repos": repos}, f)
        return path

    def test_registry_hit(self):
        self.assertEqual(self.rc.colour_for("banchi"), self.reg["repos"]["banchi"])
        self.assertEqual(self.rc.colour_for("shivinate7/banchi"), self.reg["repos"]["banchi"])

    def test_ten_repos_in_registry(self):
        for repo in ("claude-settings", "home-app", "home", "banchi", "q_max", "degen",
                     "ios-adblock", "adblock-lists", "mailaudit", "joyous"):
            c = self.reg["repos"][repo]
            self.assertTrue(len(c) == 7 and c[0] == "#" and all(ch in HEX for ch in c[1:]), (repo, c))

    def test_drawn_entries_match_the_wheel(self):
        # A repo the registry marks as drawn holds what the wheel gives it against every other repo.
        for repo in self.rule["drawn"]:
            others = {k: v for k, v in self.reg["repos"].items() if k != repo}
            with tempfile.TemporaryDirectory() as tmp:
                path = self.write_registry(tmp, others)
                self.assertEqual(self.rc.colour_for(repo, registry=path), self.reg["repos"][repo], repo)

    def test_drawn_hue_keeps_the_margins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_registry(tmp, self.reg["repos"])
            # Read each hue here, not through hue_of, so a colour hue_of wrongly calls grey still counts.
            taken = [colorsys.rgb_to_hls(*(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)))[0] * 360
                     for c in self.reg["repos"].values()]
            for name in ("a", "zz", "new-repo", "shop", "photos", "ledger", "x" * 40, "ü-repo"):
                h = round(self.rc.hue_of(self.rc.colour_for(name, registry=path), 0))
                for s in self.rule["state_hues"]:
                    self.assertGreaterEqual(dist(h, s), self.rule["state_gap"], (name, h, s))
                for t in taken:
                    self.assertGreaterEqual(dist(h, t), self.rule["repo_gap"], (name, h, t))

    def test_same_name_same_colour(self):
        first = self.rc.colour_for("some-new-repo")
        out = subprocess.run([sys.executable, MODULE, "some-new-repo"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), first)

    def test_wrap_at_zero_and_360(self):
        # 358 and 3 sit 5 degrees apart across 0, so a hue at 358 must count as near red at 5.
        self.assertEqual(self.rc.hue_gap(358, 3), 5)
        self.assertEqual(self.rc.hue_gap(0, 360), 0)
        self.assertEqual(self.rc.hue_gap(359, 1), 2)
        rule = dict(self.rule, state_hues=[5], state_gap=25, repo_gap=30)
        for start in (350, 355, 358, 0, 10, 20):
            h = self.rc.draw_hue(start, [], rule)
            self.assertGreaterEqual(self.rc.hue_gap(h, 5), 25, (start, h))
            self.assertTrue(0 <= h < 360, h)
        # A taken hue at 359 blocks 1 through 29 across the wrap.
        h = self.rc.draw_hue(15, [359], dict(rule, state_hues=[]))
        self.assertGreaterEqual(self.rc.hue_gap(h, 359), 30, h)

    def test_drawn_entries_keep_the_margins(self):
        # Each stored draw keeps its gaps to the state hues and to every other repo, greys aside.
        def hue(c):
            h, _, s = colorsys.rgb_to_hls(*(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)))
            return None if s < 0.1 else h * 360
        for repo in self.rule["drawn"]:
            h = round(hue(self.reg["repos"][repo]))
            for s in self.rule["state_hues"]:
                self.assertGreaterEqual(dist(h, s), self.rule["state_gap"], (repo, s))
            for other, c in self.reg["repos"].items():
                if other != repo and hue(c) is not None:
                    self.assertGreaterEqual(dist(h, hue(c)), self.rule["repo_gap"], (repo, other))

    def test_bad_registry_value_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_registry(tmp, {"banchi": "red"})
            out = subprocess.run([sys.executable, MODULE, "banchi", "--registry", path],
                                 capture_output=True, text=True)
            self.assertEqual((out.returncode, out.stdout), (2, ""))
            listed = os.path.join(tmp, "list.json")
            with open(listed, "w", encoding="utf-8") as f:
                json.dump([], f)
            out = subprocess.run([sys.executable, MODULE, "banchi", "--registry", listed],
                                 capture_output=True, text=True)
            self.assertEqual((out.returncode, out.stdout), (2, ""))

    def test_grey_takes_no_hue(self):
        self.assertIsNone(self.rc.hue_of("#808080"))
        self.assertAlmostEqual(self.rc.hue_of("#ff0000"), 0, places=3)

    def test_full_wheel_falls_back_to_widest_gap(self):
        # Every hue is closer than 30 degrees to some taken hue: the draw takes the widest gap left.
        taken = list(range(0, 360, 20))
        h = self.rc.draw_hue(7, taken, dict(self.rule, state_hues=[], repo_gap=30))
        self.assertEqual(min(self.rc.hue_gap(h, t) for t in taken), 10)

    def test_cli(self):
        out = subprocess.run([sys.executable, MODULE, "q_max"], capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout), (0, self.reg["repos"]["q_max"] + "\n"))
        out = subprocess.run([sys.executable, MODULE], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "missing.json")
            out = subprocess.run([sys.executable, MODULE, "banchi", "--registry", bad],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 2)
            self.assertEqual(out.stdout, "")


if __name__ == "__main__":
    unittest.main()

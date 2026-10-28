#!/usr/bin/env python3
"""Cases for lint/repo_colour.py. Standard library only.

    python3 lint/test_repo_colour.py

The script gives each repo one colour: the registry's colour when the repo has one, else a hue
drawn from the name that keeps clear of the state hues and of every other repo's hue.
REPO_COLOUR_UNDER_TEST overrides the module path, so the cases run against another copy.
"""
import base64
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


EXTRAS = os.path.join(".claude", "layout-extras.json")
PAGE = os.path.join(os.path.dirname(HERE), "skills", "waiting-page", "page.html")
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><rect width="8" height="8" fill="#123"/></svg>'
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360f8cfc0f01f0005000201e2216bc60000000049454e44ae426082")


def run(*args):
    return subprocess.run([sys.executable, MODULE, *args], capture_output=True, text=True)


class Checkout:
    """A fixture checkout named `name` under a temp folder, with no git: its name is the folder's."""

    def __init__(self, case, name):
        tmp = tempfile.TemporaryDirectory()
        case.addCleanup(tmp.cleanup)
        self.root = os.path.join(tmp.name, name)
        os.makedirs(self.root)

    def put(self, rel, data):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        return self

    def extras(self, **keys):
        return self.put(EXTRAS.replace(os.sep, "/"), json.dumps(dict({"kinds": {}}, **keys)))


class ExtrasColour(unittest.TestCase):
    """A repo's own extras colour wins, then the registry, then the draw (roadmap step c132)."""

    @classmethod
    def setUpClass(cls):
        cls.rc = load()

    def test_a_valid_extras_colour_wins(self):
        co = Checkout(self, "banchi").extras(**{"waiting-page-colour": "#12AB34"})
        self.assertEqual(self.rc.colour_for("banchi", root=co.root), "#12ab34")
        out = run("banchi", "--root", co.root)
        self.assertEqual((out.returncode, out.stdout), (0, "#12ab34\n"), out.stderr)

    def test_no_extras_colour_reads_the_registry(self):
        co = Checkout(self, "banchi")
        out = run("banchi", "--root", co.root)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, self.rc.colour_for("banchi")), out.stderr)
        co.extras()
        self.assertEqual(self.rc.colour_for("banchi", root=co.root), self.rc.colour_for("banchi"))

    def test_an_invalid_extras_colour_is_unknown_never_a_guess(self):
        for bad in ("red", "#abc", 12, "#12ab3"):
            with self.subTest(bad=bad):
                co = Checkout(self, "banchi").extras(**{"waiting-page-colour": bad})
                out = run("banchi", "--root", co.root)
                self.assertEqual((out.returncode, out.stdout), (2, ""))

    def test_root_flag_needs_a_path(self):
        out = run("banchi", "--root")
        self.assertEqual((out.returncode, out.stdout), (2, ""))


class Identity(unittest.TestCase):
    """`identity <root>` prints the page identity {brand, icon} with the icon embedded."""

    @classmethod
    def setUpClass(cls):
        cls.rc = load()

    def identity(self, co):
        out = run("identity", co.root)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout), out.stderr

    def test_icon_max_is_the_pages_constant(self):
        with open(PAGE, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("ICON_MAX = %d" % self.rc.icon_max(), text)

    def test_svg_icon_is_embedded_base64(self):
        co = Checkout(self, "degen").extras(**{"waiting-page-colour": "#a82830", "waiting-page-icon": "art/icon.svg"})
        co.put("art/icon.svg", SVG)
        got, _ = self.identity(co)
        self.assertEqual(got["brand"], "#a82830")
        head, body = got["icon"].split(",", 1)
        self.assertEqual(head, "data:image/svg+xml;base64")
        self.assertEqual(base64.b64decode(body), SVG)

    def test_png_icon_is_embedded_base64(self):
        co = Checkout(self, "degen").extras(**{"waiting-page-icon": "icon.png"}).put("icon.png", PNG)
        got, _ = self.identity(co)
        self.assertEqual(got["brand"], self.rc.colour_for("degen"))
        self.assertEqual(got["icon"], "data:image/png;base64," + base64.b64encode(PNG).decode())

    def test_no_icon_key_gives_brand_only(self):
        got, err = self.identity(Checkout(self, "banchi"))
        self.assertEqual(got, {"brand": self.rc.colour_for("banchi")})

    def test_a_bad_icon_is_left_out_with_a_line(self):
        big = b"<svg>" + b" " * 13000 + b"</svg>"  # base64 of this passes ICON_MAX
        cases = {"missing": ("icon.svg", None), "jpeg": ("icon.jpg", PNG),
                 "png that is not a png": ("icon.png", SVG), "too big": ("icon.svg", big),
                 "outside": ("../icon.svg", None)}
        for why, (rel, data) in cases.items():
            with self.subTest(why=why):
                co = Checkout(self, "banchi").extras(**{"waiting-page-icon": rel})
                if data is not None:
                    co.put(rel, data)
                got, err = self.identity(co)
                self.assertNotIn("icon", got)
                self.assertIn("icon", err)

    def test_an_unreadable_page_loses_only_the_icon(self):
        from unittest import mock
        co = Checkout(self, "degen").extras(**{"waiting-page-colour": "#a82830", "waiting-page-icon": "i.svg"}).put("i.svg", SVG)
        no_const = os.path.join(co.root, "page.html")
        with open(no_const, "w", encoding="utf-8") as f:
            f.write("<p>no constant</p>")
        for page in (os.path.join(co.root, "missing.html"), no_const):
            with self.subTest(page=page), mock.patch.object(self.rc, "PAGE", page):
                found, why = self.rc.identity(co.root)
                self.assertEqual(found, {"brand": "#a82830"})
                self.assertIn("ICON_MAX", why)

    def test_an_invalid_extras_colour_is_unknown(self):
        co = Checkout(self, "banchi").extras(**{"waiting-page-colour": "blue"})
        out = run("identity", co.root)
        self.assertEqual((out.returncode, out.stdout), (2, ""))


class Drift(unittest.TestCase):
    """`drift <root>...` compares each checkout's own accent with the registry."""

    @classmethod
    def setUpClass(cls):
        cls.rc = load()
        with open(REGISTRY, encoding="utf-8") as f:
            cls.reg = json.load(f)

    def banchi(self, value):
        return Checkout(self, "banchi").put("app/src/tokens.css", ":root {\n  --bn-accent-soft: #000000;\n  --bn-accent: %s;\n}\n" % value)

    def test_every_named_source_is_structured_and_in_the_registry(self):
        accents = self.reg["accents"]
        for repo in ("home-app", "banchi", "q_max", "mailaudit", "joyous"):
            self.assertIn(repo, accents)
        for repo, src in accents.items():
            self.assertIn(repo, self.reg["repos"])
            self.assertEqual(sorted(src), ["file", "token"], repo)
        for repo in self.reg["rule"]["drawn"] + ["degen"]:
            self.assertNotIn(repo, accents)

    def test_clean_is_0(self):
        out = run("drift", self.banchi(self.reg["repos"]["banchi"].upper()).root)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_comments_and_strings_never_give_a_false_value(self):
        # Each file's first raw "--bn-accent:" is #ff0000 inside a comment; the real one matches the registry.
        reg = self.reg["repos"]["banchi"]
        files = {
            "block comment": "/* old --bn-accent: #ff0000; */\n:root { --bn-accent: %s; }\n",
            "line comment": "// --bn-accent: #ff0000;\n:root { --bn-accent: %s; }\n",
            "comment opener in a string": ':root { content: "/*"; }\n:root { --bn-accent: %s; }\n',
            "multi-line template literal": "const s = `a\n/* not a comment\n`;\n:root { --bn-accent: %s; }\n",
            "lone quote in text": "<p>Don't</p>\n<!-- --bn-accent: #ff0000; -->\n<style>:root { --bn-accent: %s; }</style>\n",
        }
        for why, text in files.items():
            with self.subTest(why=why):
                co = Checkout(self, "banchi").put("app/src/tokens.css", text % reg)
                out = run("drift", co.root)
                self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_a_changed_accent_is_1_and_named(self):
        out = run("drift", self.banchi("#ff0000").root)
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("banchi", out.stdout)
        self.assertIn("#ff0000", out.stdout)

    def test_a_json_source_reads_its_key(self):
        reg = self.reg["repos"]["mailaudit"]
        co = Checkout(self, "mailaudit").put("shared/tokens.json", json.dumps({"accent": reg}))
        self.assertEqual(run("drift", co.root).returncode, 0)
        co.put("shared/tokens.json", json.dumps({"accent": "#000000"}))
        self.assertEqual(run("drift", co.root).returncode, 1)

    def test_an_extras_colour_that_differs_is_drift(self):
        co = self.banchi(self.reg["repos"]["banchi"]).extras(**{"waiting-page-colour": "#010203"})
        out = run("drift", co.root)
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("#010203", out.stdout)

    def test_a_repo_with_no_source_compares_its_extras_colour(self):
        reg = self.reg["repos"]["degen"]
        co = Checkout(self, "degen")
        self.assertEqual(run("drift", co.root).returncode, 0)
        co.extras(**{"waiting-page-colour": reg})
        self.assertEqual(run("drift", co.root).returncode, 0)

    def test_unreadable_is_2_never_clear(self):
        cases = {"no file": Checkout(self, "banchi"), "no token": Checkout(self, "banchi").put("app/src/tokens.css", ":root {}"),
                 "not a hex": self.banchi("var(--blue)"), "bad extras": self.banchi("#3d5af1").extras(**{"waiting-page-colour": "x"}),
                 "not in the registry": Checkout(self, "never-heard-of-it"),
                 "json not a string": Checkout(self, "mailaudit").put("shared/tokens.json", '{"accent": {"light": "#000000"}}')}
        for why, co in cases.items():
            with self.subTest(why=why):
                out = run("drift", co.root)
                self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertEqual(run("drift").returncode, 2)

    def test_drift_wins_over_unknown_and_each_root_gets_a_line(self):
        a, b = self.banchi("#ff0000"), Checkout(self, "q_max")
        out = run("drift", a.root, b.root)
        self.assertEqual(out.returncode, 1)
        self.assertEqual(len(out.stdout.strip().splitlines()), 2, out.stdout)

    def test_cost_reads_only_no_process_no_write(self):
        # The docstring's cost: no process starts and no file is written; it reads on demand.
        from unittest import mock
        co = self.banchi("#ff0000")
        modes, real_open = [], open

        def watch(path, mode="r", *a, **k):
            modes.append(mode)
            return real_open(path, mode, *a, **k)
        with mock.patch("builtins.open", watch), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("process started")), \
                mock.patch("os.system", side_effect=AssertionError("process started")):
            self.assertEqual(self.rc.main(["repo_colour.py", "drift", co.root]), 1)
        self.assertTrue(modes)
        self.assertTrue(all(set(m) <= set("rbt") for m in modes), modes)

if __name__ == "__main__":
    unittest.main()

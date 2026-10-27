#!/usr/bin/env python3
"""Cases for lint/label_once.py. Standard library only.

    python3 lint/test_label_once.py

The probe reads a saved page and names each short label that shows more than once (ux-label-once,
a label shows once per screen). Each case writes a page to a temp folder and runs the real script.
LABEL_ONCE_UNDER_TEST overrides the module path, so the cases run against another copy.
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.environ.get("LABEL_ONCE_UNDER_TEST") or os.path.join(HERE, "label_once.py")

THREE_BLOCKING = """<!doctype html><main>
<h2>Blocking</h2><ul>
<li><span class="tag">blocking</span> Merge the batch</li>
<li><span class="tag">BLOCKING</span> Answer the waiting page</li>
</ul></main>"""

ONCE_EACH = """<!doctype html><main>
<section><h2>Blocking</h2><ul>
<li><span class="dot red"></span> Merge the batch</li>
<li><span class="dot red"></span> Answer the waiting page</li></ul></section>
<section><h2>Upcoming</h2><p>Nothing yet.</p></section>
</main>"""


class LabelOnce(unittest.TestCase):
    def run_probe(self, *pages):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i, html in enumerate(pages):
                p = os.path.join(tmp, f"page{i}.html")
                with open(p, "w", encoding="utf-8") as f:
                    f.write(html)
                paths.append(p)
            r = subprocess.run([sys.executable, MODULE, *paths], capture_output=True, text=True)
            return r.returncode, r.stdout

    def test_three_blocking_is_red(self):
        code, out = self.run_probe(THREE_BLOCKING)
        self.assertEqual(code, 1, out)
        self.assertIn('"blocking" shows 3 times', out)

    def test_counts_and_colons_are_the_same_label(self):
        page = "<main><h2>Upcoming</h2><span>Upcoming (3)</span><span>upcoming</span><b>2</b><p>Upcoming:</p><i>Upcoming (1):</i></main>"
        code, out = self.run_probe(page)
        self.assertEqual(code, 1, out)
        self.assertIn('"upcoming" shows 5 times', out)

    def test_open_skip_tag_at_the_end_is_unknown(self):
        page = "<main><button>Go<p>x</p><div>Blocking</div><div>Blocking</div>"  # cut off: never closed
        code, out = self.run_probe(page)
        self.assertEqual(code, 2, out)
        self.assertIn("UNKNOWN", out)

    def test_each_label_once_is_green(self):
        code, out = self.run_probe(ONCE_EACH)
        self.assertEqual((code, out), (0, ""))

    def test_controls_cells_and_hidden_text_do_not_count(self):
        page = """<main><h2>Orders</h2><table>
<tr><th>State</th></tr><tr><td>Sent</td></tr><tr><td>Sent</td></tr></table>
<label>Name</label><label>Name</label><span>A</span><span>A</span>
<button>Edit</button><button>Edit</button><a href="#">Open</a><a href="#">Open</a>
<p>Sent</p><span hidden>Sent</span><span aria-hidden="true">Sent</span>
<svg><text>Mon</text><text>Mon</text></svg>
<script>var s = "Sent"; // Sent</script><style>.x::after{content:"Sent"}</style></main>"""
        self.assertEqual(self.run_probe(page), (0, ""))

    def test_sentences_numbers_and_dates_do_not_count(self):
        page = """<main><p>Merge the batch before noon today.</p><p>Merge the batch before noon today.</p>
<span>12</span><span>12</span><span>Oct 27</span><span>Oct 27</span><span>$4.00</span><span>$4.00</span></main>"""
        self.assertEqual(self.run_probe(page), (0, ""))

    def test_scanner_traps(self):
        # building-scanner-respects-strings: comment openers inside text, a lone quote, a comment.
        page = """<main><p>Don't stop</p><p>Don't stop</p><p>Go /* Blocking</p><p>// Blocking</p>
<p># Blocking</p><!-- <p>Blocking</p><p>Blocking</p> --><p>Blocking</p>
<pre>line one
line two</pre><pre>line one
line two</pre></main>"""
        code, out = self.run_probe(page)
        self.assertEqual(code, 1, out)
        self.assertEqual(out.count("shows"), 1, out)  # the two-line pre text is four words, not a label
        self.assertIn('"don\'t stop" shows 2 times', out)
        self.assertNotIn('"blocking"', out)

    def test_void_tags_and_unclosed_tags_keep_the_stack(self):
        # A void tag inside a button must not leave the probe stuck inside the button.
        page = """<main><button><img src=x>Go</button><p>Waiting<br>
<p>Waiting</main>"""
        code, out = self.run_probe(page)
        self.assertEqual(code, 1, out)
        self.assertIn('"waiting" shows 2 times', out)

    def test_each_page_is_its_own_screen(self):
        page = "<main><h2>Blocking</h2></main>"
        self.assertEqual(self.run_probe(page, page), (0, ""))

    def test_unreadable_page_is_unknown_not_clear(self):
        r = subprocess.run([sys.executable, MODULE, os.path.join(HERE, "no-such-page.html")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stdout)

    def test_no_page_is_usage(self):
        r = subprocess.run([sys.executable, MODULE], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stdout)


if __name__ == "__main__":
    unittest.main()

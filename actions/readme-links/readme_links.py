#!/usr/bin/env python3
"""Check README.md's external https links. Weekly, never per pull request.

    scripts/readme_links.py [FILE]    exit 1, listing each dead link
"""
import re
import sys
import urllib.error
import urllib.request

# Inline links, autolinks and bare URLs. Trailing punctuation is not part of a URL.
URL = re.compile(r"https?://[^\s)>\]\"'`]+")


def links(text):
    return sorted({u.rstrip(".,;:*_") for u in URL.findall(text)})


def alive(url, tries=2):
    """HEAD, then GET when HEAD is refused. One retry. Returns None or the failure."""
    err = None
    for _ in range(tries):
        for method in ("HEAD", "GET"):
            req = urllib.request.Request(url, method=method, headers={"User-Agent": "claude-settings-readme-links"})
            try:
                with urllib.request.urlopen(req, timeout=20):
                    return None
            except urllib.error.HTTPError as e:
                err = f"HTTP {e.code}"
            except Exception as e:  # DNS, TLS, timeout
                err = type(e).__name__
    return err


def main(path="README.md"):
    with open(path, encoding="utf-8") as f:
        dead = [(u, e) for u in links(f.read()) if (e := alive(u))]
    for u, e in dead:
        print(f"DEAD {u} ({e})")
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))

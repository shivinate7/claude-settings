#!/usr/bin/env python3
"""Check README.md's external https links. Weekly, never per pull request.

    scripts/readme_links.py [FILE]    exit 1, listing each dead link
"""
import ipaddress
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# Inline links, autolinks and bare URLs. Trailing punctuation is not part of a URL.
URL = re.compile(r"https?://[^\s)>\]\"'`]+")


# Hosts CI cannot reach by design. Matched on the whole host or its trailing labels, never a substring.
LOCAL_SUFFIXES = (".localhost", ".local", ".home.arpa", ".internal")


def split_joined(match):
    """`https://a,https://b` is one regex match: split it into its URLs. A comma after `?` or `#`
    belongs to the URL (`?u=https://b,https://c`), so only the part before it is split."""
    q = re.search(r"[?#]", match)
    head, rest = (match[:q.start()], match[q.start():]) if q else (match, "")
    parts = re.split(r",(?=https?://)", head)
    parts[-1] += rest
    return parts


def links(text):
    found = (u for m in URL.findall(text) for u in split_joined(m))
    return sorted({u.rstrip(".,;:*_") for u in found})


def skip_reason(url):
    """Why CI cannot check this link by design, or None for a host it should reach."""
    host = (urllib.parse.urlsplit(url).hostname or "").rstrip(".").lower()
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if host == "localhost" or host.endswith(LOCAL_SUFFIXES):
            return "local-only host"
        return None
    return "private address" if ip.is_private or ip.is_loopback or ip.is_link_local else None


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


def main(path="README.md", skip=skip_reason):
    with open(path, encoding="utf-8") as f:
        urls = links(f.read())
    checked = []
    for u in urls:
        if why := skip(u):
            print(f"SKIP {u} ({why})")
        else:
            checked.append(u)
    dead = [(u, e) for u in checked if (e := alive(u))]
    for u, e in dead:
        print(f"DEAD {u} ({e})")
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))

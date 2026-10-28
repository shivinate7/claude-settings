"""Offline: a dead link exits 1 and is named; a live one exits 0 (local http server).
Links CI cannot reach by design are skipped, each named on one line."""
import contextlib, http.server, io, os, subprocess, sys, tempfile, threading

HERE = os.path.dirname(os.path.abspath(__file__))


class H(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200 if self.path == "/ok" else 404)
        self.end_headers()

    do_GET = do_HEAD

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"


def readme(text):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(text)
    return f.name


def run(text):
    return subprocess.run([sys.executable, os.path.join(HERE, "readme_links.py"), readme(text)],
                          capture_output=True, text=True)


sys.path.insert(0, HERE)
import readme_links


def run_checked(text):
    """In-process with the skip off: the test server itself is a loopback host."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = readme_links.main(readme(text), skip=lambda url: None)
    return rc, out.getvalue()


good_rc, good_out = run_checked(f"[a]({base}/ok)")
assert good_rc == 0, good_out
bad_rc, bad_out = run_checked(f"[a]({base}/ok) and [b]({base}/gone).")
assert bad_rc == 1 and f"DEAD {base}/gone (HTTP 404)" in bad_out, bad_out
print("ok   readme_links: live passes, dead fails and is named")

# The degen README lines: local-only URLs, one comma-joined pair. Nothing is dropped silently.
degen = run("Open https://localhost:8443 or https://feed.home.arpa:8443 (default: "
            "`https://localhost:8443,https://feed.home.arpa:8443`).")
assert degen.returncode == 0, degen.stdout
for u in ("https://localhost:8443", "https://feed.home.arpa:8443"):
    assert f"SKIP {u}" in degen.stdout, degen.stdout
assert "DEAD" not in degen.stdout, degen.stdout
assert readme_links.links("x https://localhost:8443,https://feed.home.arpa:8443 y") == [
    "https://feed.home.arpa:8443", "https://localhost:8443"]
# A comma inside a query string stays in its URL; a dead link still exits 1 through the CLI.
assert readme_links.links("https://a.com/s?u=https://b.com,https://c.com") == [
    "https://a.com/s?u=https://b.com,https://c.com"]
assert readme_links.links("https://a.com/x,https://b.com/s?q=1") == ["https://a.com/x", "https://b.com/s?q=1"]
dead = run("[x](https://readme-links-test.invalid/)")
assert dead.returncode == 1 and "DEAD https://readme-links-test.invalid/" in dead.stdout, dead.stdout
print("ok   readme_links: local-only links skipped and named, comma pair split")

# Hosts CI cannot reach by design are skipped.
for u in ("https://localhost/", "http://127.0.0.1:9/", "http://[::1]/", "http://10.1.2.3/",
          "http://192.168.0.5/", "http://172.16.0.1/", "http://169.254.1.1/", "https://nas.local/",
          "https://feed.home.arpa:8443", "https://svc.internal/x", "https://LOCALHOST./", "https://app.localhost/"):
    assert readme_links.skip_reason(u), u

# A public host is never skipped, even when its name merely contains "local" and the like.
for u in ("https://localhost.example.com/", "https://notlocal.com/", "https://local.dev/",
          "https://internal.example.com/", "https://home.arpa.example.org/", "https://example.com/local",
          "http://8.8.8.8/", "http://172.32.0.1/", "https://mylocalhost.io/", "https://example.local.com/"):
    assert not readme_links.skip_reason(u), u
print("ok   readme_links: private hosts skipped, public hosts with 'local' in the name kept")

"""Red proof, offline: a dead link exits 1 and is named; a live one exits 0. Local http server."""
import http.server, os, subprocess, sys, tempfile, threading

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


def run(text):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(text)
    return subprocess.run([sys.executable, os.path.join(HERE, "readme_links.py"), f.name],
                          capture_output=True, text=True)


good = run(f"[a]({base}/ok)")
assert good.returncode == 0, good.stdout
bad = run(f"[a]({base}/ok) and [b]({base}/gone).")
assert bad.returncode == 1 and f"DEAD {base}/gone (HTTP 404)" in bad.stdout, bad.stdout
print("ok   readme_links: live passes, dead fails and is named")

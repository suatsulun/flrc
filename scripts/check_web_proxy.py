"""Exercise the real Caddyfile against a local, synthetic upstream (Linux/Docker)."""

import json
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socket import socket

ROOT = Path(__file__).resolve().parents[1]
GATEWAY = "ci-only-synthetic-gateway"
IMMUTABLE = "public, max-age=31536000, immutable"
# SPA shells must be revalidated on every load; hashed bundles are cached forever.
CACHE_CONTROL = {
    "/": "no-cache",
    "/classes/1": "no-cache",
    "/assets/app.js": IMMUTABLE,
    "/admin/": "no-cache",
    "/admin/lifecycle": "no-cache",
    "/admin/assets/app.js": IMMUTABLE,
}


class Upstream(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(
            {
                "path": self.path,
                "gateway": self.headers.get_all("X-Flrc-Gateway"),
                "cloudflare_ip": self.headers.get("Cf-Connecting-Ip"),
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def main():
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    with socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        proxy_port = reservation.getsockname()[1]
    name = "flrc-proxy-test-" + uuid.uuid4().hex[:12]
    static = Path(tempfile.mkdtemp(prefix="flrc-proxy-static-"))
    for app in ("teacher", "admin"):
        (static / app / "assets").mkdir(parents=True)
        (static / app / "index.html").write_text(f"<!doctype html><title>{app}</title>")
        (static / app / "assets/app.js").write_text("export {};")
    static.chmod(0o755)
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
                "--name",
                name,
                "--network",
                "host",
                "--env",
                f"SITE_ADDRESS=http://127.0.0.1:{proxy_port}",
                "--env",
                f"API_UPSTREAM=127.0.0.1:{upstream.server_port}",
                "--env",
                f"GATEWAY_SECRET={GATEWAY}",
                "--volume",
                f"{ROOT / 'infra/web/Caddyfile'}:/etc/caddy/Caddyfile:ro",
                "--volume",
                f"{static / 'teacher'}:/srv/teacher:ro",
                "--volume",
                f"{static / 'admin'}:/srv/admin:ro",
                "caddy:2-alpine",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        url = f"http://127.0.0.1:{proxy_port}/api/me"
        for attempt in range(100):
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    response.read()
                break
            except (urllib.error.URLError, TimeoutError):
                if attempt == 99:
                    raise
                time.sleep(0.1)
        for headers in (
            {},
            {"X-Flrc-Gateway": "forged", "Cf-Connecting-Ip": "192.0.2.1"},
        ):
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=3
            ) as response:
                actual = json.load(response)
            assert actual["path"] == "/api/me", actual
            assert actual["gateway"] == [GATEWAY], (
                "Caddy must replace all client gateway values"
            )
            assert actual["cloudflare_ip"] is None, (
                "Caddy must strip untrusted client IP headers"
            )
        for path, expected in CACHE_CONTROL.items():
            with urllib.request.urlopen(
                f"http://127.0.0.1:{proxy_port}{path}", timeout=3
            ) as response:
                actual = response.headers.get("Cache-Control")
            assert actual == expected, f"{path}: Cache-Control {actual!r}, expected {expected!r}"
        print(
            "Caddy forwards the gateway secret, replaces forged values, strips untrusted IP"
            " headers, revalidates SPA shells, and caches hashed bundles."
        )
    finally:
        subprocess.run(
            ["docker", "rm", "--force", name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        upstream.shutdown()
        upstream.server_close()
        thread.join()
        shutil.rmtree(static, ignore_errors=True)


if __name__ == "__main__":
    main()

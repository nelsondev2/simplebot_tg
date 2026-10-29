"""Minimal HTTP health endpoint.

Hosting providers like Render require web services to bind a port and answer
HTTP requests; this tiny server is started by start.sh only when the PORT
environment variable is set (i.e. when the bot runs as a web service).
"""

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OK_PATHS = ("/", "/health", "/healthz")


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in OK_PATHS:
            self._reply(200, b"ok")
        else:
            self._reply(404, b"not found")

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def log_message(self, *_args):
        pass


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Health check listening at http://0.0.0.0:{port}/healthz", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

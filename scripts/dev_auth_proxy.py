import argparse
import http.server
import socketserver
import urllib.error
import urllib.request


class _ProxyHandler(http.server.BaseHTTPRequestHandler):
    backend_base_url = "http://localhost:8501"
    trusted_user = "alice@example.com"

    def _forward(self) -> None:
        target_url = f"{self.backend_base_url}{self.path}"
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length) if content_length else None

        forwarded_headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "connection"}
        }
        forwarded_headers["X-Forwarded-Authenticated"] = "true"
        forwarded_headers["X-Authenticated-User"] = self.trusted_user

        request = urllib.request.Request(
            target_url,
            data=body,
            headers=forwarded_headers,
            method=self.command,
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() in {"transfer-encoding", "connection"}:
                        continue
                    self.send_header(key, value)
                self.end_headers()
                payload = response.read()
                if payload:
                    self.wfile.write(payload)
        except urllib.error.HTTPError as exc:
            self.send_response(exc.code)
            for key, value in exc.headers.items():
                if key.lower() in {"transfer-encoding", "connection"}:
                    continue
                self.send_header(key, value)
            self.end_headers()
            payload = exc.read()
            if payload:
                self.wfile.write(payload)

    def do_GET(self) -> None:
        self._forward()

    def do_POST(self) -> None:
        self._forward()

    def do_PUT(self) -> None:
        self._forward()

    def do_PATCH(self) -> None:
        self._forward()

    def do_DELETE(self) -> None:
        self._forward()

    def do_OPTIONS(self) -> None:
        self._forward()

    def do_HEAD(self) -> None:
        self._forward()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a local proxy that injects trusted auth headers."
    )
    parser.add_argument(
        "--listen-port",
        type=int,
        default=8601,
        help="Local port to listen on.",
    )
    parser.add_argument(
        "--backend-url",
        default="http://localhost:8501",
        help="Backend Streamlit base URL.",
    )
    parser.add_argument(
        "--user",
        default="alice@example.com",
        help="User value to inject into X-Authenticated-User.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    handler_class = type(
        "ConfiguredProxyHandler",
        (_ProxyHandler,),
        {
            "backend_base_url": args.backend_url.rstrip("/"),
            "trusted_user": args.user,
        },
    )

    with socketserver.ThreadingTCPServer(("127.0.0.1", args.listen_port), handler_class) as server:
        print(
            f"Trusted auth proxy listening on http://127.0.0.1:{args.listen_port} -> {args.backend_url} as {args.user}"
        )
        print("Note: this is a simple HTTP proxy for local testing and does not proxy WebSockets.")
        server.serve_forever()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

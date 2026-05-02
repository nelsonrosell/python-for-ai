import argparse
from pathlib import Path
import sys
import urllib.request


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send trusted-auth headers to a local Streamlit instance."
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8501/",
        help="Target Streamlit URL.",
    )
    parser.add_argument(
        "--user",
        default="alice@example.com",
        help="Principal value to send in X-Authenticated-User.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    request = urllib.request.Request(
        args.url,
        headers={
            "X-Forwarded-Authenticated": "true",
            "X-Authenticated-User": args.user,
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        print(f"Status: {response.status}")
        print(f"URL: {args.url}")
        print(f"Sent X-Authenticated-User: {args.user}")
        print("Trusted headers were sent successfully.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

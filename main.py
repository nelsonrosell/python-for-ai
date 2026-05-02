import argparse

from app import SqlAgentApp
from app.logging_utils import configure_logging


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the earthquake SQL agent from the command line."
    )
    parser.add_argument(
        "question",
        nargs="*",
        help="Optional one-shot question. If omitted, starts the interactive CLI.",
    )
    return parser


def main() -> int:
    configure_logging()
    parser = _build_parser()
    args = parser.parse_args()

    app = SqlAgentApp()
    if args.question:
        prompt = " ".join(args.question).strip()
        if prompt:
            print(app.ask(prompt))
        return 0

    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

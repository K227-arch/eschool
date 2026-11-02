"""CLI — command-line interface for the eSchool Assistant."""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Ensure UTF-8 output on Windows (for ✓ ✗ ? symbols)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

from .pipeline import search_schools
from .presenter import present


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.  Returns an exit code (0 = success)."""
    load_dotenv()  # load .env if present

    parser = argparse.ArgumentParser(
        prog="eschool-search",
        description="AI-powered school search assistant for eSchool Uganda.",
    )
    parser.add_argument(
        "request",
        nargs="?",
        default=None,
        help="The parent's search request in natural language. "
        "If omitted, enters interactive mode.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=1,
        help="Maximum number of result pages to fetch (default: 1).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    args = parser.parse_args(argv)

    # Logging
    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    if args.request:
        # One-shot mode
        return _run_search(args.request, args.max_pages)
    else:
        # Interactive mode
        return _interactive_loop(args.max_pages)


def _run_search(request: str, max_pages: int) -> int:
    """Run a single search and print the result."""
    try:
        response = search_schools(request, max_pages=max_pages)
        print(present(response))
        return 0
    except Exception as exc:
        print(f"An unexpected error occurred: {exc}", file=sys.stderr)
        logging.exception("Unexpected error in CLI")
        return 1


def _interactive_loop(max_pages: int) -> int:
    """Run an interactive prompt loop."""
    import os
    has_key = bool(os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY"))
    print("=" * 60)
    print("  eSchool Assistant — Interactive Mode")
    print("  Type your school search request, or 'quit' to exit.")
    print("=" * 60)
    print()

    while True:
        try:
            request = input("Search> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            return 0

        if not request:
            continue
        if request.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            return 0

        try:
            response = search_schools(request, max_pages=max_pages)
            print()
            print(present(response))
            print()
        except Exception as exc:
            print(f"An error occurred: {exc}", file=sys.stderr)
            print()
            logging.exception("Unexpected error in interactive mode")


if __name__ == "__main__":
    sys.exit(main())

"""CLI — command-line interface for the eSchool Assistant.

Usage
-----
::

    # One-shot search
    python -m eschool_assistant "I'm looking for a girls' boarding school in Kampala"

    # Interactive mode
    python -m eschool_assistant

    # Via the installed entry point
    eschool-search "mixed primary school in Wakiso"

Environment
-----------
Works out of the box.  If ``OPENAI_API_KEY`` is set, the AI interpreter
is used; otherwise a built-in rule-based interpreter handles common
requests.  See ``.env.example`` for all options.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

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
    has_groq = bool(os.getenv("GROQ_API_KEY"))
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    if has_groq:
        key_status = "AI mode (Groq)"
    elif has_openai:
        key_status = "AI mode (OpenAI)"
    else:
        key_status = "rule-based mode (no API key)"
    print("=" * 60)
    print("  eSchool Assistant — Interactive Mode")
    print(f"  Interpretation: {key_status}")
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

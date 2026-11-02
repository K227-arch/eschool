"""Entry point for ``python -m eschool_assistant``.

Usage:
    python -m eschool_assistant              # interactive CLI
    python -m eschool_assistant "request"    # one-shot CLI
    python -m eschool_assistant --web        # start web UI on http://localhost:5000
"""
import sys


def main():
    if "--web" in sys.argv:
        from .app import app
        print("Starting eSchool Assistant web UI at http://localhost:5000")
        print("Press Ctrl+C to stop.")
        app.run(debug=False, port=5000)
    else:
        from .cli import main as cli_main
        sys.exit(cli_main())


main()

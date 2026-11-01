"""Entry point: no arguments -> GUI, otherwise CLI."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    # No arguments, or a single PDF path (e.g. "Open with" / drag onto the exe) -> GUI.
    if not args or (len(args) == 1 and args[0].lower().endswith(".pdf")):
        from .gui.app import run

        return run(args)
    from .cli import main as cli_main

    return cli_main(args)


if __name__ == "__main__":
    sys.exit(main())

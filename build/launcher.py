"""PyInstaller entry point (absolute import so relative imports in the package work)."""

import sys

from clear_pdf_properties.__main__ import main

if __name__ == "__main__":
    sys.exit(main())

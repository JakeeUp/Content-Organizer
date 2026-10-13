"""PyInstaller entry point for the windowed GUI build.

PyInstaller needs a script, not a ``module:function`` reference, so this tiny shim imports
the GUI's ``main()`` and exits with its return code. Build locally with::

    pip install -e ".[gui]" pyinstaller
    pyinstaller --noconfirm --clean --onefile --windowed --name ContentOrganizer \
        --collect-data content_organizer packaging/pyinstaller_entry.py

The executable lands in ``dist/ContentOrganizer.exe`` (Windows) or
``dist/ContentOrganizer.app`` (macOS).
"""

from __future__ import annotations

import sys

from content_organizer.gui.app import main

if __name__ == "__main__":
    sys.exit(main())

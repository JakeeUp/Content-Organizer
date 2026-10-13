"""Allow ``python -m content_organizer``."""

import sys

from content_organizer.cli import main

if __name__ == "__main__":
    sys.exit(main())

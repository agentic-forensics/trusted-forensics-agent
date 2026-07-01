"""Enable `python -m tfa` to run the command-line demo."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())

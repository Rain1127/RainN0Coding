"""Trusted entry point mounted read-only into the browser worker."""
import json
from pathlib import Path
import sys

from runtime_validation import validate_page


if __name__ == '__main__':
    root, contract = json.loads(sys.stdin.read())
    validate_page(Path('/workspace') / root, contract, report_dir=Path('/report'))

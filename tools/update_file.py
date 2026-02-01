from __future__ import annotations

import argparse
from pathlib import Path
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="Path to write")
    ap.add_argument("--stdin", action="store_true", help="Read content from stdin")
    args = ap.parse_args()

    p = Path(args.path)
    p.parent.mkdir(parents=True, exist_ok=True)

    if not args.stdin:
        raise SystemExit("Use --stdin and pipe content.")

    data = sys.stdin.read()
    p.write_text(data, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

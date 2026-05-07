"""Tiny helper to read scalar fields from spec.yaml for shell scripts.

Usage:
  python3 _spec_read.py spec.yaml server.port
  python3 _spec_read.py spec.yaml benchmark.ready_check_timeout_sec 900

If the path does not exist and a default is given, prints the default. Otherwise
exits 1.
"""

import sys
from pathlib import Path

import yaml


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: _spec_read.py <spec.yaml> <dotted.path> [default]", file=sys.stderr)
        return 2
    spec_path, dotted = sys.argv[1], sys.argv[2]
    default = sys.argv[3] if len(sys.argv) > 3 else None

    data = yaml.safe_load(Path(spec_path).read_text())
    node = data
    for key in dotted.split("."):
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            if default is not None:
                print(default)
                return 0
            print(f"spec key not found: {dotted}", file=sys.stderr)
            return 1
    # Print scalar; for dict/list, use JSON.
    if isinstance(node, (dict, list)):
        import json
        print(json.dumps(node))
    else:
        print(node)
    return 0


if __name__ == "__main__":
    sys.exit(main())

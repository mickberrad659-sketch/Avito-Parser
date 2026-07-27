#!/usr/bin/env python3
"""Save one complete response body from a HAR entry."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("har", type=Path)
    parser.add_argument("entry", type=int)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    har = json.loads(args.har.read_text(encoding="utf-8"))
    entry = har["log"]["entries"][args.entry]
    content = entry["response"]["content"]
    body = content.get("text")
    if not isinstance(body, str):
        raise RuntimeError(f"HAR entry {args.entry} has no response text")
    if content.get("encoding") == "base64":
        data = base64.b64decode(body)
    else:
        data = body.encode("utf-8")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(
        f"saved entry {args.entry} HTTP {entry['response']['status']} "
        f"({len(data)} bytes) to {args.output.resolve()}"
    )


if __name__ == "__main__":
    main()

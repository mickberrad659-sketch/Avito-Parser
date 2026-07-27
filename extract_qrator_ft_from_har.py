#!/usr/bin/env python3
"""Extract and decrypt Qrator /web/2/ft fields from a HAR."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from qrator_payload_codec import decode_field, encode_field


def _field(post_data: str, name: str) -> str:
    match = re.search(
        rf'Content-Disposition: form-data; name="{re.escape(name)}"'
        rf"\r\n\r\n([^\r]+)",
        post_data,
    )
    if not match:
        raise ValueError(f"multipart field {name!r} not found")
    return match.group(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("har", type=Path)
    parser.add_argument("--output-prefix", default="qrator-har")
    args = parser.parse_args()

    har = json.loads(args.har.read_text(encoding="utf-8"))
    entries = [
        entry
        for entry in har["log"]["entries"]
        if "/web/2/ft" in entry["request"]["url"]
    ]
    if not entries:
        raise RuntimeError("HAR contains no /web/2/ft request")

    for number, entry in enumerate(entries, start=1):
        post_data = entry["request"]["postData"]["text"]
        f_value = _field(post_data, "f")
        s_value = _field(post_data, "s")
        raw_f = decode_field(f_value, "f")
        raw_s = decode_field(s_value, "s")
        suffix = f"-{number}" if len(entries) > 1 else ""
        f_path = Path(f"{args.output_prefix}{suffix}-raw-f.txt")
        s_path = Path(f"{args.output_prefix}{suffix}-raw-s.json")

        f_path.write_text(raw_f + "\n", encoding="utf-8")
        parsed_s = json.loads(raw_s)
        s_path.write_text(
            json.dumps(parsed_s, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        print(
            f"entry {number}: f raw={len(raw_f)} chars, "
            f"s raw={len(raw_s)} chars, "
            f"f round-trip={encode_field(raw_f, 'f') == f_value}, "
            f"s round-trip={encode_field(raw_s, 's') == s_value}"
        )
        print(f"saved {f_path} and {s_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Extract the GeeTest /load JSONP data from a browser HAR, offline.

Usage:
    python3 extract_geetest_load_from_har.py \
        '/path/to/archive.har' geetest_load_response.json

No request is sent. The program only reads a HAR already captured by a browser.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


def parse_jsonp(text: str) -> dict:
    """Parse a single JSONP call such as ``geetest_123({...})``."""
    match = re.fullmatch(r"\s*[A-Za-z_$][\w$]*\((.*)\)\s*;?\s*", text, re.DOTALL)
    if not match:
        raise ValueError("response is not a single JSONP callback")
    return json.loads(match.group(1))


def extract_load_response(har_path: Path) -> dict:
    """Return request parameters plus the relevant successful /load response."""
    har = json.loads(har_path.read_text(encoding="utf-8"))
    matches: list[dict] = []

    for index, entry in enumerate(har["log"]["entries"]):
        url = entry["request"]["url"]
        parsed_url = urlsplit(url)
        if parsed_url.path != "/load":
            continue

        body = entry["response"].get("content", {}).get("text")
        if not body:
            continue

        response = parse_jsonp(body)
        if response.get("status") != "success" or not isinstance(response.get("data"), dict):
            continue

        data = response["data"]
        if "payload" not in data or "payload_protocol" not in data:
            continue

        params = {key: values[-1] for key, values in parse_qs(parsed_url.query).items()}
        matches.append(
            {
                "har_entry": index,
                "url": url,
                "request_parameters": params,
                "load_response": {
                    "lot_number": data.get("lot_number"),
                    "captcha_type": data.get("captcha_type"),
                    "payload": data["payload"],
                    "payload_protocol": data["payload_protocol"],
                    "process_token": data.get("process_token"),
                    "pow_detail": data.get("pow_detail"),
                },
            }
        )

    if not matches:
        raise ValueError("no successful GeeTest /load response with payload fields found")
    return matches[-1]


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(f"Usage: {Path(sys.argv[0]).name} INPUT.har OUTPUT.json")

    result = extract_load_response(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()

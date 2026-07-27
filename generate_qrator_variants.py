#!/usr/bin/env python3
"""Generate conservative Qrator f variants from an encode-ready base."""

from __future__ import annotations

import argparse
import json
import random
import secrets
import sys
import time
from collections.abc import Callable
from pathlib import Path

from qrator_payload_codec import encode_field


ROOT = Path(__file__).resolve().parent
DEFAULT_BASE_F = ROOT / "base.txt"
DEFAULT_BASE_S = ROOT / "base-s.json"
CANVAS_HASH_INDEX = 106
UNIX_TIME_INDEX = 128
F_VALUE_COUNT = 141
MIN_SYNTHETIC_HASH = 4
MAX_UINT32 = 0xFFFFFFFF


def load_f_base(path: Path) -> list[int]:
    raw = path.read_text(encoding="utf-8").strip()
    values = raw.split(";")
    if len(values) != F_VALUE_COUNT:
        raise ValueError(
            f"{path} must contain {F_VALUE_COUNT} semicolon-separated values, "
            f"received {len(values)}"
        )
    try:
        numbers = [int(value) for value in values]
    except ValueError as error:
        raise ValueError(f"{path} contains a non-integer value") from error
    return numbers


def load_s_base(path: Path) -> str:
    raw = path.read_text(encoding="utf-8").strip()
    parsed = json.loads(raw)
    required = {
        "monospace",
        "readOnly",
        "noLengthPlugins",
        "installedExtensions",
    }
    if set(parsed) != required:
        raise ValueError(
            f"{path} must contain exactly these keys: {sorted(required)}"
        )
    # Qrator encrypts compact JSON.stringify output, not pretty JSON.
    return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))


def random_source(seed: int | None) -> Callable[[], int]:
    if seed is None:
        return lambda: MIN_SYNTHETIC_HASH + secrets.randbelow(
            MAX_UINT32 - MIN_SYNTHETIC_HASH + 1
        )
    generator = random.Random(seed)
    return lambda: generator.randrange(
        MIN_SYNTHETIC_HASH,
        MAX_UINT32 + 1,
    )


def generate_variants(
    base_values: list[int],
    raw_s: str,
    *,
    count: int,
    timestamp: int,
    seed: int | None = None,
    include_raw: bool = False,
) -> list[dict[str, object]]:
    if count < 1:
        raise ValueError("count must be positive")
    available_hashes = MAX_UINT32 - MIN_SYNTHETIC_HASH + 1
    if count > available_hashes:
        raise ValueError(f"count cannot exceed {available_hashes}")

    next_hash = random_source(seed)
    used_hashes: set[int] = set()
    encoded_s = encode_field(raw_s, "s")
    variants: list[dict[str, object]] = []

    while len(variants) < count:
        canvas_hash = next_hash()
        if canvas_hash in used_hashes:
            continue
        used_hashes.add(canvas_hash)

        values = base_values.copy()
        values[CANVAS_HASH_INDEX] = canvas_hash
        values[UNIX_TIME_INDEX] = timestamp
        raw_f = ";".join(map(str, values))
        item: dict[str, object] = {
            "f": encode_field(raw_f, "f"),
            "s": encoded_s,
            "canvasHash": canvas_hash,
            "timestamp": timestamp,
        }
        if include_raw:
            item["rawF"] = raw_f
            item["rawS"] = raw_s
        variants.append(item)

    return variants


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--base-f", type=Path, default=DEFAULT_BASE_F)
    parser.add_argument("--base-s", type=Path, default=DEFAULT_BASE_S)
    parser.add_argument(
        "--output",
        type=Path,
        help="NDJSON output file; omit to write to stdout",
    )
    parser.add_argument(
        "--timestamp",
        type=int,
        help="Unix seconds; defaults to the current time",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="reproducible PRNG seed; default uses secrets",
    )
    parser.add_argument("--include-raw", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timestamp = int(time.time()) if args.timestamp is None else args.timestamp
    variants = generate_variants(
        load_f_base(args.base_f),
        load_s_base(args.base_s),
        count=args.count,
        timestamp=timestamp,
        seed=args.seed,
        include_raw=args.include_raw,
    )
    output = "".join(
        json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
        for item in variants
    )
    if args.output:
        args.output.write_text(output, encoding="utf-8")
        print(
            f"saved {len(variants)} variants to {args.output}; "
            f"static s={variants[0]['s']}",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Offline encoder/decoder for Qrator /web/2/ft fields f and s."""

from __future__ import annotations

import argparse
import struct
from collections.abc import Sequence


DELTA = 0x9E3779B9
ROUNDS = 32
DEFAULT_KEY = (1901231474, 1081891380, 1433695566, 978402641)


def _validate_key(key: Sequence[int]) -> tuple[int, int, int, int]:
    if len(key) != 4:
        raise ValueError("XTEA key must contain exactly four uint32 words")
    words = tuple(int(word) for word in key)
    if any(word < 0 or word > 0xFFFFFFFF for word in words):
        raise ValueError("XTEA key words must be in uint32 range")
    return words  # type: ignore[return-value]


def _encrypt_block(block: bytes, key: Sequence[int]) -> bytes:
    if len(block) != 8:
        raise ValueError("XTEA block must be exactly 8 bytes")
    key_words = _validate_key(key)
    left, right = struct.unpack("<2I", block)
    total = 0

    for _ in range(ROUNDS):
        left = (
            left
            + (
                ((((right << 4) & 0xFFFFFFFF) ^ (right >> 5)) + right)
                ^ ((total + key_words[total & 3]) & 0xFFFFFFFF)
            )
        ) & 0xFFFFFFFF
        total = (total + DELTA) & 0xFFFFFFFF
        right = (
            right
            + (
                ((((left << 4) & 0xFFFFFFFF) ^ (left >> 5)) + left)
                ^ ((total + key_words[(total >> 11) & 3]) & 0xFFFFFFFF)
            )
        ) & 0xFFFFFFFF

    return struct.pack("<2I", left, right)


def _decrypt_block(block: bytes, key: Sequence[int]) -> bytes:
    if len(block) != 8:
        raise ValueError("XTEA block must be exactly 8 bytes")
    key_words = _validate_key(key)
    left, right = struct.unpack("<2I", block)
    total = (DELTA * ROUNDS) & 0xFFFFFFFF

    for _ in range(ROUNDS):
        right = (
            right
            - (
                ((((left << 4) & 0xFFFFFFFF) ^ (left >> 5)) + left)
                ^ ((total + key_words[(total >> 11) & 3]) & 0xFFFFFFFF)
            )
        ) & 0xFFFFFFFF
        total = (total - DELTA) & 0xFFFFFFFF
        left = (
            left
            - (
                ((((right << 4) & 0xFFFFFFFF) ^ (right >> 5)) + right)
                ^ ((total + key_words[total & 3]) & 0xFFFFFFFF)
            )
        ) & 0xFFFFFFFF

    return struct.pack("<2I", left, right)


def encrypt_bytes(raw: bytes, key: Sequence[int] = DEFAULT_KEY) -> str:
    """Encrypt bytes with the exact block/padding format used by the bundle."""
    if not raw:
        return ""
    padded = raw + b"\0" * (-len(raw) % 8)
    return "".join(
        _encrypt_block(padded[offset : offset + 8], key).hex()
        for offset in range(0, len(padded), 8)
    )


def encrypt_js_text(raw_text: str, key: Sequence[int] = DEFAULT_KEY) -> str:
    """Replicate the bundle's charCodeAt/bit-shift packing exactly.

    JavaScript works on UTF-16 code units and ORs four units into one uint32.
    For the observed ASCII payload this is identical to encrypt_bytes().
    """
    utf16 = raw_text.encode("utf-16-le", errors="surrogatepass")
    code_units = [
        int.from_bytes(utf16[offset : offset + 2], "little")
        for offset in range(0, len(utf16), 2)
    ]
    if not code_units:
        return ""
    code_units.extend([0] * (-len(code_units) % 8))
    output: list[str] = []

    for offset in range(0, len(code_units), 8):
        words = []
        for word_offset in (0, 4):
            word = 0
            for index in range(4):
                word |= (
                    code_units[offset + word_offset + index] << (index * 8)
                ) & 0xFFFFFFFF
            words.append(word & 0xFFFFFFFF)
        block = struct.pack("<2I", *words)
        output.append(_encrypt_block(block, key).hex())

    return "".join(output)


def decrypt_hex(
    encoded: str,
    key: Sequence[int] = DEFAULT_KEY,
    *,
    strip_zero_padding: bool = True,
) -> bytes:
    """Decrypt Qrator hex blocks; optionally remove the bundle's zero padding."""
    if len(encoded) % 16:
        raise ValueError("ciphertext must contain complete 8-byte hex blocks")
    try:
        ciphertext = bytes.fromhex(encoded)
    except ValueError as error:
        raise ValueError("ciphertext is not valid hex") from error

    raw = b"".join(
        _decrypt_block(ciphertext[offset : offset + 8], key)
        for offset in range(0, len(ciphertext), 8)
    )
    return raw.rstrip(b"\0") if strip_zero_padding else raw


def encode_field(
    raw_text: str,
    field: str,
    key: Sequence[int] = DEFAULT_KEY,
) -> str:
    """Encode an f or s value using the bundle's JS UTF-16 packing."""
    encrypted = encrypt_js_text(raw_text, key)
    if field == "f":
        return f"5.{encrypted}"
    if field == "s":
        return encrypted
    raise ValueError("field must be 'f' or 's'")


def decode_field(
    value: str,
    field: str,
    key: Sequence[int] = DEFAULT_KEY,
) -> str:
    """Decode an f or s value back to its pre-encryption ASCII text."""
    if field == "f":
        try:
            version, value = value.split(".", 1)
        except ValueError as error:
            raise ValueError("f must start with a version prefix") from error
        if version != "5":
            raise ValueError(f"unsupported f version: {version}")
    elif field != "s":
        raise ValueError("field must be 'f' or 's'")

    # The cipher reverses to packed bytes. This exactly restores observed
    # ASCII inputs. The preceding JS packing is not injective for UTF-16 code
    # units above 0xff, so arbitrary non-ASCII source text cannot be recovered.
    return decrypt_hex(value, key).decode("latin-1")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("encode", "decode"))
    parser.add_argument("field", choices=("f", "s"))
    parser.add_argument("value", help="raw text for encode or field value for decode")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.operation == "encode":
        print(encode_field(args.value, args.field))
    else:
        print(decode_field(args.value, args.field))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Offline reference for the firewallPow payload construction seen in the HAR.

This reproduces only the client-side transformation:

    challenge_jwt -> {"challenge": challenge_jwt, "nonce": valid_nonce}

It makes no network requests and does not attempt to handle cookies, retries, or
server-side verification. The JWT must be obtained legitimately by the browser
flow; this file only documents how the captured JavaScript consumes it.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PowParameters:
    """The only JWT-payload values used for the local PoW calculation."""

    challenge_id: str
    complexity: int


def build_get_payload(pow_challenge: str) -> dict[str, str]:
    """Build the first request body exactly as seen in the JavaScript bundle.

    The ``pow_challenge`` comes from the preceding HTTP 439 response and is not
    decoded or otherwise modified by the client.
    """
    if not isinstance(pow_challenge, str) or not pow_challenge:
        raise ValueError("pow_challenge must be a non-empty string")
    return {"challenge": pow_challenge}


def decode_challenge_jwt(challenge_jwt: str) -> PowParameters:
    """Extract ``id`` and ``compl`` from the JWT payload.

    This matches the JavaScript bundle's parsing behavior: it base64url-decodes
    JWT segment 2 and validates that ``id`` is a string and ``compl`` is a
    number. It does not validate the JWT signature; server-side verification is
    still required when a real browser sends the verify request.
    """
    parts = challenge_jwt.split(".")
    if len(parts) < 2:
        raise ValueError("invalid JWT: expected at least header and payload")

    encoded_payload = parts[1]
    padded_payload = encoded_payload + "=" * (-len(encoded_payload) % 4)
    try:
        raw_payload = base64.urlsafe_b64decode(padded_payload)
        payload: dict[str, Any] = json.loads(raw_payload)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid JWT payload") from exc

    challenge_id = payload.get("id")
    complexity = payload.get("compl")
    if not isinstance(challenge_id, str) or isinstance(complexity, bool) or not isinstance(complexity, (int, float)):
        raise ValueError("invalid JWT payload: expected string id and numeric compl")

    # The observed JavaScript uses ``"0".repeat(compl)``. The service's captured
    # value is an integer; requiring that here keeps the Python representation
    # unambiguous.
    if not isinstance(complexity, int) or complexity < 0:
        raise ValueError("invalid JWT payload: compl must be a non-negative integer")

    return PowParameters(challenge_id=challenge_id, complexity=complexity)


def sha256_hex(challenge_id: str, nonce: int) -> str:
    """Return SHA-256 hex for the exact input used by the JavaScript bundle."""
    candidate = f"{challenge_id}:{nonce}".encode("utf-8")
    return hashlib.sha256(candidate).hexdigest()


def find_nonce(parameters: PowParameters, *, start: int = 0) -> int:
    """Find the first nonce whose hash starts with ``compl`` zero hex digits.

    JavaScript equivalent:

        target = "0".repeat(compl)
        nonce = 0
        while (!sha256(`${id}:${nonce}`).startsWith(target)) nonce += 1
    """
    if start < 0:
        raise ValueError("start must be non-negative")

    target_prefix = "0" * parameters.complexity
    nonce = start
    while not sha256_hex(parameters.challenge_id, nonce).startswith(target_prefix):
        nonce += 1
    return nonce


def build_verify_payload(challenge_jwt: str) -> dict[str, str | int]:
    """Build the JSON object that the captured code sends to ``verify``.

    ``challenge`` is the original JWT string, unchanged.  Only ``nonce`` is
    derived locally from its decoded ``id`` and ``compl`` fields.
    """
    parameters = decode_challenge_jwt(challenge_jwt)
    nonce = find_nonce(parameters)
    return {"challenge": challenge_jwt, "nonce": nonce}


if __name__ == "__main__":
    # Intentionally no embedded real challenge/JWT and no HTTP client. Import
    # this module in an analysis environment and pass a captured JWT explicitly.
    print("Import this module and call build_verify_payload(challenge_jwt).")

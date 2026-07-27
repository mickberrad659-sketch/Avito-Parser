#!/usr/bin/env python3
"""Build a stability/range matrix for all 141 decoded Qrator f values."""

from __future__ import annotations

import json
import re
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

from camoufox.sync_api import Camoufox

from qrator_payload_codec import decode_field


ROOT = Path(__file__).resolve().parent
BUNDLE = (ROOT / "f1b0f8f3fb96fe30a8e6.js").read_text(encoding="utf-8")
OUTPUT_JSON = ROOT / "qrator-fingerprint-matrix.json"
OUTPUT_MD = ROOT / "QRATOR-FIELD-MATRIX.md"
PROFILE_COUNT = 8
PAGES_PER_PROFILE = 2
BASE_URL = "https://www.avito.ru/qrator-matrix"

KNOWN_FIELDS = {
    0: "screen.width",
    1: "screen.height",
    2: "screen.colorDepth",
    3: "screen.pixelDepth",
    **{index: "timezone offset probe" for index in range(4, 24)},
    36: "WebSocket support flag",
    43: "normalized navigator.doNotTrack",
    45: "navigator.hardwareConcurrency",
    46: "hash(navigator.platform)",
    47: "hash(navigator.languages)",
    106: "canvas fingerprint/hash (profile-stable)",
    108: "composite navigator hash",
    109: "composite screen hash",
    110: "WebGL/GPU renderer fingerprint/hash",
    111: "navigator.maxTouchPoints",
    128: "floor(Date.now()/1000)",
    132: "navigator.webdriver",
    140: "audio fingerprint/hash",
}


def multipart_field(post_data: str, name: str) -> str:
    match = re.search(
        rf'Content-Disposition: form-data; name="{name}"'
        rf"\r\n\r\n([^\r]+)",
        post_data,
    )
    if not match:
        raise RuntimeError(f"missing multipart field {name}")
    return match.group(1)


def browser_metadata(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => {
            let webgl = {};
            try {
                const canvas = document.createElement("canvas");
                const gl = canvas.getContext("webgl2") ||
                           canvas.getContext("webgl");
                if (gl) {
                    const ext = gl.getExtension("WEBGL_debug_renderer_info");
                    webgl = {
                        vendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : null,
                        renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null,
                        version: gl.getParameter(gl.VERSION),
                        shadingLanguageVersion:
                            gl.getParameter(gl.SHADING_LANGUAGE_VERSION)
                    };
                }
            } catch (error) {
                webgl = {error: String(error)};
            }
            return {
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                languages: Array.from(navigator.languages || []),
                hardwareConcurrency: navigator.hardwareConcurrency,
                deviceMemory: navigator.deviceMemory ?? null,
                maxTouchPoints: navigator.maxTouchPoints,
                webdriver: navigator.webdriver,
                cookieEnabled: navigator.cookieEnabled,
                doNotTrack: navigator.doNotTrack,
                devicePixelRatio,
                timezoneOffset: new Date().getTimezoneOffset(),
                screen: {
                    width: screen.width,
                    height: screen.height,
                    availWidth: screen.availWidth,
                    availHeight: screen.availHeight,
                    colorDepth: screen.colorDepth,
                    pixelDepth: screen.pixelDepth
                },
                webgl
            };
        }"""
    )


def capture_profile(profile_index: int) -> list[dict[str, Any]]:
    measurements: list[dict[str, Any]] = []
    html = (
        "<!doctype html><html><head><meta charset=\"utf-8\"></head>"
        f"<body><script>{BUNDLE}</script></body></html>"
    )

    with Camoufox(headless=True, humanize=False) as browser:
        page = browser.new_page()
        posts: list[str] = []

        def route_request(route: Any) -> None:
            request = route.request
            if request.url.startswith(BASE_URL):
                route.fulfill(status=200, content_type="text/html", body=html)
            elif "/web/2/ft" in request.url:
                posts.append(request.post_data or "")
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='"TRACE_FT_VALUE"',
                )
            elif "/web/1/u?" in request.url:
                route.abort()
            else:
                route.abort()

        page.route("**/*", route_request)
        for page_index in range(PAGES_PER_PROFILE):
            page.context.clear_cookies()
            expected_posts = len(posts) + 1
            page.goto(
                f"{BASE_URL}/{profile_index}/{page_index}",
                wait_until="domcontentloaded",
            )
            deadline = time.monotonic() + 10
            while len(posts) < expected_posts and time.monotonic() < deadline:
                page.wait_for_timeout(100)
            if len(posts) < expected_posts:
                raise RuntimeError(
                    f"profile {profile_index}, page {page_index}: no /web/2/ft"
                )

            f_value = multipart_field(posts[-1], "f")
            s_value = multipart_field(posts[-1], "s")
            raw_f = decode_field(f_value, "f")
            values = [int(value) for value in raw_f.split(";")]
            if len(values) != 141:
                raise RuntimeError(
                    f"expected 141 f values, received {len(values)}"
                )
            measurements.append(
                {
                    "profile": profile_index,
                    "page": page_index,
                    "capturedAt": int(time.time()),
                    "browser": browser_metadata(page),
                    "f": f_value,
                    "s": s_value,
                    "rawF": raw_f,
                    "rawS": decode_field(s_value, "s"),
                    "values": values,
                }
            )
            if page_index + 1 < PAGES_PER_PROFILE:
                page.wait_for_timeout(1100)

    return measurements


def analyze(measurements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matrix: list[dict[str, Any]] = []
    profiles = sorted({item["profile"] for item in measurements})

    for index in range(141):
        all_values = [item["values"][index] for item in measurements]
        per_profile = {
            profile: [
                item["values"][index]
                for item in measurements
                if item["profile"] == profile
            ]
            for profile in profiles
        }
        within_profile_changes = {
            str(profile): len(set(values)) > 1
            for profile, values in per_profile.items()
        }
        representative_values = [values[0] for values in per_profile.values()]
        unique = sorted(set(all_values))
        counts = Counter(all_values)

        if any(within_profile_changes.values()):
            stability = (
                "deterministic_time"
                if index == 128
                else "changes_within_same_profile"
            )
        elif len(set(representative_values)) > 1:
            stability = "fingerprint_dependent"
        else:
            stability = "constant_across_samples"

        matrix.append(
            {
                "index": index,
                "knownMeaning": KNOWN_FIELDS.get(index),
                "stability": stability,
                "uniqueCount": len(unique),
                "minimum": min(all_values),
                "maximum": max(all_values),
                "median": statistics.median(all_values),
                "values": unique,
                "counts": {str(value): count for value, count in counts.items()},
                "withinProfileChanges": within_profile_changes,
            }
        )

    return matrix


def markdown_report(
    measurements: list[dict[str, Any]],
    matrix: list[dict[str, Any]],
) -> str:
    counts = Counter(row["stability"] for row in matrix)
    lines = [
        "# Матрица decoded Qrator `f`",
        "",
        f"Профилей: {PROFILE_COUNT}. Измерений на профиль: {PAGES_PER_PROFILE}.",
        "",
        "Классификация:",
        "",
        f"- constant_across_samples: {counts['constant_across_samples']};",
        f"- fingerprint_dependent: {counts['fingerprint_dependent']};",
        f"- changes_within_same_profile: {counts['changes_within_same_profile']};",
        f"- deterministic_time: {counts['deterministic_time']}.",
        "",
        "Повторные страницы одного профиля разделены паузой более одной секунды.",
        "",
        "| idx | назначение | класс | unique | min | max | значения |",
        "|---:|---|---|---:|---:|---:|---|",
    ]
    for row in matrix:
        values = ", ".join(str(value) for value in row["values"][:8])
        if len(row["values"]) > 8:
            values += ", …"
        lines.append(
            f"| {row['index']} | {row['knownMeaning'] or ''} | "
            f"{row['stability']} | {row['uniqueCount']} | "
            f"{row['minimum']} | {row['maximum']} | {values} |"
        )

    lines.extend(
        [
            "",
            "## Профили",
            "",
            "Полные UA, platform, languages, screen, CPU, touch, timezone и "
            "WebGL metadata для каждого измерения находятся в JSON:",
            "",
            "`qrator-fingerprint-matrix.json`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    measurements: list[dict[str, Any]] = []
    for profile_index in range(PROFILE_COUNT):
        profile = capture_profile(profile_index)
        measurements.extend(profile)
        print(
            f"profile {profile_index + 1}/{PROFILE_COUNT}: "
            f"{len(profile)} measurements"
        )

    matrix = analyze(measurements)
    output = {
        "profileCount": PROFILE_COUNT,
        "pagesPerProfile": PAGES_PER_PROFILE,
        "measurements": measurements,
        "matrix": matrix,
    }
    OUTPUT_JSON.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    OUTPUT_MD.write_text(
        markdown_report(measurements, matrix) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {OUTPUT_JSON}")
    print(f"Saved {OUTPUT_MD}")


if __name__ == "__main__":
    main()

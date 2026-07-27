#!/usr/bin/env python3
"""Differentially map Qrator f-vector indexes in one Camoufox context."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from camoufox.sync_api import Camoufox

from qrator_payload_codec import decode_field


ROOT = Path(__file__).resolve().parent
BUNDLE = (ROOT / "f1b0f8f3fb96fe30a8e6.js").read_text(encoding="utf-8")
OUTPUT = ROOT / "qrator-camoufox-field-probes.json"

PROBES = {
    "baseline": "",
    "screen_geometry": """
        for (const [name, value] of Object.entries({
            width: 1234, height: 777, colorDepth: 17, pixelDepth: 19
        })) {
            Object.defineProperty(screen, name, {get: () => value});
        }
    """,
    "hardware_concurrency": """
        Object.defineProperty(navigator, "hardwareConcurrency", {get: () => 13});
    """,
    "max_touch_points": """
        Object.defineProperty(navigator, "maxTouchPoints", {get: () => 9});
    """,
    "device_pixel_ratio": """
        Object.defineProperty(window, "devicePixelRatio", {get: () => 3});
    """,
    "webdriver": """
        Object.defineProperty(navigator, "webdriver", {get: () => true});
    """,
    "platform": """
        Object.defineProperty(navigator, "platform", {get: () => "TRACE_PLATFORM"});
    """,
    "user_agent": """
        Object.defineProperty(navigator, "userAgent", {get: () => "TRACE_UA/1.0"});
    """,
    "languages": """
        Object.defineProperty(navigator, "language", {get: () => "zz-ZZ"});
        Object.defineProperty(navigator, "languages", {get: () => ["zz-ZZ", "zz"]});
    """,
    "screen_available": """
        Object.defineProperty(screen, "availWidth", {get: () => 1111});
        Object.defineProperty(screen, "availHeight", {get: () => 666});
    """,
    "window_geometry": """
        Object.defineProperty(window, "innerWidth", {get: () => 1110});
        Object.defineProperty(window, "innerHeight", {get: () => 665});
        Object.defineProperty(window, "outerWidth", {get: () => 1120});
        Object.defineProperty(window, "outerHeight", {get: () => 700});
    """,
    "timezone_offset": """
        Date.prototype.getTimezoneOffset = () => 777;
    """,
    "cookie_enabled": """
        Object.defineProperty(navigator, "cookieEnabled", {get: () => false});
    """,
    "do_not_track": """
        Object.defineProperty(navigator, "doNotTrack", {get: () => "TRACE_DNT"});
    """,
    "no_local_storage": """
        Object.defineProperty(window, "localStorage", {get: () => undefined});
    """,
    "no_session_storage": """
        Object.defineProperty(window, "sessionStorage", {get: () => undefined});
    """,
    "no_indexed_db": """
        Object.defineProperty(window, "indexedDB", {get: () => undefined});
    """,
    "no_websocket": """
        Object.defineProperty(window, "WebSocket", {get: () => undefined});
    """,
    "no_worker": """
        Object.defineProperty(window, "Worker", {get: () => undefined});
    """,
    "no_webgl": """
        Object.defineProperty(window, "WebGLRenderingContext", {
            get: () => undefined
        });
        const originalGetContext = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function(type, ...args) {
            if (String(type).startsWith("webgl")) return null;
            return originalGetContext.call(this, type, ...args);
        };
    """,
    "no_canvas_context": """
        HTMLCanvasElement.prototype.getContext = () => null;
    """,
    "no_audio_context": """
        Object.defineProperty(window, "AudioContext", {get: () => undefined});
        Object.defineProperty(window, "OfflineAudioContext", {
            get: () => undefined
        });
    """,
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


def run_probe(page: Any, name: str, override: str) -> dict[str, Any]:
    url = f"https://www.avito.ru/qrator-field-probe/{name}"
    post_data: list[str] = []
    errors: list[str] = []
    html = (
        "<!doctype html><html><body>"
        f"<script>{override}</script>"
        f"<script>{BUNDLE}</script>"
        "</body></html>"
    )
    page.on("pageerror", lambda error: errors.append(str(error)))

    def route_request(route: Any) -> None:
        request = route.request
        if request.url == url:
            route.fulfill(status=200, content_type="text/html", body=html)
        elif "/web/2/ft" in request.url:
            post_data.append(request.post_data or "")
            route.fulfill(
                status=200,
                content_type="application/json",
                body='"TRACE_FT_VALUE"',
            )
        elif "/web/1/u?" in request.url:
            route.abort()
        else:
            route.abort()

    page.unroute_all()
    page.route("**/*", route_request)
    page.goto(url, wait_until="domcontentloaded")
    deadline = time.monotonic() + 10
    while not post_data and time.monotonic() < deadline:
        page.wait_for_timeout(100)

    runtime = page.evaluate(
        """() => ({
            screen: {
                width: screen.width, height: screen.height,
                colorDepth: screen.colorDepth, pixelDepth: screen.pixelDepth
            },
            hardwareConcurrency: navigator.hardwareConcurrency,
            maxTouchPoints: navigator.maxTouchPoints,
            devicePixelRatio: devicePixelRatio,
            webdriver: navigator.webdriver,
            platform: navigator.platform
        })"""
    )
    if not post_data:
        raise RuntimeError(f"probe {name} produced no /web/2/ft request: {errors}")
    f_value = multipart_field(post_data[0], "f")
    raw = decode_field(f_value, "f")
    return {
        "runtime": runtime,
        "f": f_value,
        "raw": raw,
        "values": raw.split(";"),
        "errors": errors,
    }


def main() -> None:
    results: dict[str, Any] = {}
    with Camoufox(headless=True, humanize=False) as browser:
        page = browser.new_page()
        for name, override in PROBES.items():
            page.context.clear_cookies()
            results[name] = run_probe(page, name, override)
            print(f"{name}: {len(results[name]['values'])} values")

    baseline = results["baseline"]["values"]
    for name, result in results.items():
        if name == "baseline":
            result["changedIndexes"] = []
            continue
        result["changedIndexes"] = [
            {
                "index": index,
                "baseline": before,
                "probe": after,
            }
            for index, (before, after) in enumerate(zip(baseline, result["values"]))
            if before != after
        ]

    OUTPUT.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {OUTPUT}")
    for name, result in results.items():
        if name != "baseline":
            print(name, result["changedIndexes"])


if __name__ == "__main__":
    main()

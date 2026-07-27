#!/usr/bin/env python3
"""Capture Qrator f/s plaintext inside a real Camoufox runtime."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from camoufox.sync_api import Camoufox

from qrator_payload_codec import decode_field, encode_field


ROOT = Path(__file__).resolve().parent
BUNDLE_PATH = ROOT / "f1b0f8f3fb96fe30a8e6.js"
OUTPUT_PATH = ROOT / "qrator-camoufox-trace.json"
RAW_F_PATH = ROOT / "qrator-camoufox-raw-f.txt"
RAW_S_PATH = ROOT / "qrator-camoufox-raw-s.json"
TRACE_URL = "https://www.avito.ru/qrator-runtime-trace"

PRE_ENCODE_HOOK = r"""
window.__qratorPreEncodeTrace = {f: [], s: []};
window.__qratorDynamicSources = [];
{
    const rememberSource = (kind, args) => {
        try {
            window.__qratorDynamicSources.push({
                kind,
                args: Array.from(args, value => String(value))
            });
        } catch (_) {}
    };
    const NativeFunction = Function;
    window.Function = new Proxy(NativeFunction, {
        apply(target, thisArg, args) {
            rememberSource("Function.apply", args);
            return Reflect.apply(target, thisArg, args);
        },
        construct(target, args, newTarget) {
            rememberSource("Function.construct", args);
            return Reflect.construct(target, args, newTarget);
        }
    });
    const nativeEval = window.eval;
    window.eval = new Proxy(nativeEval, {
        apply(target, thisArg, args) {
            rememberSource("eval", args);
            return Reflect.apply(target, thisArg, args);
        }
    });

    const nativeJoin = Array.prototype.join;
    Array.prototype.join = function(separator) {
        const result = nativeJoin.apply(this, arguments);
        if (separator === ";" && this.length === 141) {
            window.__qratorPreEncodeTrace.f.push(result);
        }
        return result;
    };

    const nativeStringify = JSON.stringify;
    JSON.stringify = function(value) {
        const result = nativeStringify.apply(this, arguments);
        if (
            value && typeof value === "object" &&
            Object.prototype.hasOwnProperty.call(value, "monospace") &&
            Object.prototype.hasOwnProperty.call(value, "readOnly") &&
            Object.prototype.hasOwnProperty.call(value, "noLengthPlugins") &&
            Object.prototype.hasOwnProperty.call(value, "installedExtensions")
        ) {
            window.__qratorPreEncodeTrace.s.push(result);
        }
        return result;
    };
}
"""


def instrument_bundle(source: str) -> str:
    marker = "function g(B3,f_){"
    if source.count(marker) != 1:
        raise RuntimeError(
            f"expected exactly one Qrator XTEA function, found {source.count(marker)}"
        )
    hook = "".join(
        (
            marker,
            "window.__qratorCipherTrace=window.__qratorCipherTrace||[];",
            "window.__qratorCipherTrace.push({",
            "raw:''+B3,key:[f_[0],f_[1],f_[2],f_[3]]",
            "});",
        )
    )
    return source.replace(marker, hook)


def parse_multipart(post_data: str | None) -> dict[str, str]:
    if not post_data:
        return {}
    return {
        match.group("name"): match.group("value")
        for match in re.finditer(
            r'Content-Disposition: form-data; name="(?P<name>[^"]+)"'
            r"\r\n\r\n(?P<value>.*?)\r\n--",
            post_data,
            re.DOTALL,
        )
    }


def main() -> None:
    instrumented = instrument_bundle(BUNDLE_PATH.read_text(encoding="utf-8"))
    html = (
        "<!doctype html><html><head><meta charset=\"utf-8\"></head>"
        f"<body><script>{PRE_ENCODE_HOOK}</script>"
        f"<script>{instrumented}</script></body></html>"
    )
    ft_requests: list[dict[str, Any]] = []
    cipher_snapshots: list[list[dict[str, Any]]] = []
    pre_encode_snapshots: list[dict[str, list[str]]] = []
    dynamic_source_snapshots: list[list[dict[str, Any]]] = []
    console_messages: list[str] = []
    page_errors: list[str] = []

    with Camoufox(headless=True, humanize=False) as browser:
        page = browser.new_page()
        page.on("console", lambda message: console_messages.append(message.text))
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        def route_request(route: Any) -> None:
            request = route.request
            if request.url == TRACE_URL:
                route.fulfill(status=200, content_type="text/html", body=html)
                return
            if "/web/2/ft" in request.url:
                try:
                    cipher_snapshots.append(
                        request.frame.evaluate(
                            "() => Array.from(window.__qratorCipherTrace || [])"
                        )
                    )
                    pre_encode_snapshots.append(
                        request.frame.evaluate(
                            "() => window.__qratorPreEncodeTrace || {f: [], s: []}"
                        )
                    )
                    dynamic_source_snapshots.append(
                        request.frame.evaluate(
                            "() => window.__qratorDynamicSources || []"
                        )
                    )
                except Exception as error:
                    page_errors.append(f"cipher snapshot failed: {error}")
                ft_requests.append(
                    {
                        "method": request.method,
                        "url": request.url,
                        "headers": dict(request.headers),
                        "postData": request.post_data,
                        "fields": parse_multipart(request.post_data),
                    }
                )
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='"TRACE_FT_VALUE"',
                )
                return
            if "/web/1/u?" in request.url:
                route.fulfill(
                    status=200,
                    content_type="image/gif",
                    body=b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
                    b"\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00"
                    b"\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
                )
                return
            route.abort()

        page.route("**/*", route_request)
        page.goto(TRACE_URL, wait_until="domcontentloaded")

        deadline = time.monotonic() + 10
        while not ft_requests and time.monotonic() < deadline:
            page.wait_for_timeout(100)

        cipher_calls = (
            cipher_snapshots[-1]
            if cipher_snapshots
            else page.evaluate(
                "() => Array.from(globalThis.__qratorCipherTrace || [])"
            )
        )
        pre_encode_trace = (
            pre_encode_snapshots[-1]
            if pre_encode_snapshots
            else page.evaluate(
                "() => window.__qratorPreEncodeTrace || {f: [], s: []}"
            )
        )
        dynamic_sources = (
            dynamic_source_snapshots[-1]
            if dynamic_source_snapshots
            else page.evaluate("() => window.__qratorDynamicSources || []")
        )
        browser_info = page.evaluate(
            """() => ({
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                languages: Array.from(navigator.languages || []),
                hardwareConcurrency: navigator.hardwareConcurrency,
                deviceMemory: navigator.deviceMemory ?? null,
                screen: {
                    width: screen.width,
                    height: screen.height,
                    availWidth: screen.availWidth,
                    availHeight: screen.availHeight,
                    colorDepth: screen.colorDepth,
                    pixelDepth: screen.pixelDepth
                }
            })"""
        )
        cookies = page.context.cookies()

    fields = ft_requests[0]["fields"] if ft_requests else {}
    traced_raw_f_call = next(
        (
            call
            for call in cipher_calls
            if fields.get("f", "").removeprefix("5.")
            and len(call["raw"]) > 200
        ),
        None,
    )
    traced_raw_s_call = next(
        (
            call
            for call in cipher_calls
            if call["raw"].startswith("{") and "installedExtensions" in call["raw"]
        ),
        None,
    )
    decoded_raw_f = decode_field(fields["f"], "f") if fields.get("f") else None
    decoded_raw_s = decode_field(fields["s"], "s") if fields.get("s") else None
    raw_f = decoded_raw_f or (
        traced_raw_f_call["raw"] if traced_raw_f_call else None
    )
    raw_s = decoded_raw_s or (
        traced_raw_s_call["raw"] if traced_raw_s_call else None
    )
    round_trip = {
        "f": bool(raw_f and encode_field(raw_f, "f") == fields.get("f")),
        "s": bool(raw_s and encode_field(raw_s, "s") == fields.get("s")),
    }
    direct_capture_matches_decode = {
        "f": bool(
            raw_f
            and pre_encode_trace["f"]
            and pre_encode_trace["f"][-1] == raw_f
        ),
        "s": bool(
            raw_s
            and pre_encode_trace["s"]
            and pre_encode_trace["s"][-1] == raw_s
        ),
    }

    output = {
        "note": (
            "Camoufox ciphertext decoded with the extracted XTEA key. "
            "roundTripMatches proves that the recovered text is the exact "
            "pre-encode plaintext. The bundle bypassed direct intrinsic hooks "
            "in this runtime; see directCaptureMatchesDecode."
        ),
        "bundle": BUNDLE_PATH.name,
        "url": TRACE_URL,
        "browser": browser_info,
        "cipherCalls": cipher_calls,
        "ftRequests": ft_requests,
        "decoded": {"f": raw_f, "s": raw_s},
        "directPreEncodeCapture": pre_encode_trace,
        "dynamicSources": dynamic_sources,
        "roundTripMatches": round_trip,
        "directCaptureMatchesDecode": direct_capture_matches_decode,
        "cookies": cookies,
        "console": console_messages,
        "pageErrors": page_errors,
    }
    OUTPUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if raw_f:
        RAW_F_PATH.write_text(raw_f + "\n", encoding="utf-8")
    if raw_s:
        parsed_s = json.loads(raw_s)
        RAW_S_PATH.write_text(
            json.dumps(parsed_s, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(f"Saved trace to {OUTPUT_PATH}")
    print(f"Captured {len(cipher_calls)} cipher calls")
    print(f"Captured {len(ft_requests)} /web/2/ft requests")
    if raw_f:
        print(f"Saved f plaintext ({len(raw_f)} chars) to {RAW_F_PATH}")
    if raw_s:
        print(f"Saved s plaintext ({len(raw_s)} chars) to {RAW_S_PATH}")
    print(f"Offline encode round-trip: f={round_trip['f']}, s={round_trip['s']}")
    print(
        "Direct pre-encode capture matches decode: "
        f"f={direct_capture_matches_decode['f']}, "
        f"s={direct_capture_matches_decode['s']}"
    )
    if page_errors:
        print(f"Runtime reported {len(page_errors)} page errors; see trace JSON")


if __name__ == "__main__":
    main()

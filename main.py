#!/usr/bin/env python3
"""Run the firewallPow ``get -> verify`` flow recorded in the HAR.

The first request reproduces the blocked items XHR from the HAR and obtains a
fresh ``pow_challenge``.  The PoW portion then performs ``firewallPow/get`` and
``firewallPow/verify`` using the same HTTP session.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from curl_cffi import requests

from firewallpow_payload_reference import build_get_payload, build_verify_payload
from generate_qrator_variants import (
    DEFAULT_BASE_F,
    DEFAULT_BASE_S,
    generate_variants,
    load_f_base,
    load_s_base,
)

BASE_URL = "https://www.avito.ru"
GET_URL = f"{BASE_URL}/web/3/firewallPow/get"
VERIFY_URL = f"{BASE_URL}/web/3/firewallPow/verify"
FIREWALL_CAPTCHA_GET_URL = f"{BASE_URL}/web/5/firewallCaptcha/get"
GEETEST_LOAD_URL = "https://gcaptcha4.geevisit.com/load"
QRATOR_FT_URL = f"{BASE_URL}/web/2/ft"
QRATOR_PIXEL_URL = f"{BASE_URL}/web/1/u"
REFERER = (
    f"{BASE_URL}/volgograd/bytovaya_elektronika?"
    "context=H4sIAAAAAAAA_wEmANn_YToxOntzOjE6InkiO3M6MTY6ImpKSFd2M2hLSlIzWWJFMHQiO30fldpuJgAAAA"
    "&p=18&q=%D0%BD%D0%BE%D1%83%D1%82%D0%B1%D1%83%D0%BA"
)
CHALLENGE_SOURCE_URL = (
    f"{BASE_URL}/web/1/js/items?categoryId=6&locationId=624840"
    "&name=%D0%BD%D0%BE%D1%83%D1%82%D0%B1%D1%83%D0%BA"
    "&geoCoords=48.707103%2C44.516939&cd=0&p=100&verticalCategoryId=4"
    "&localPriority=0&updateListOnly=true"
    "&context=H4sIAAAAAAAA_wEmANn_YToxOntzOjE6InkiO3M6MTY6ImpKSFd2M2hLSlIzWWJFMHQiO30fldpuJgAAAA"
)
PAGES_URL = (
    f"{BASE_URL}/moskva_i_mo/tovary_dlya_kompyutera/komplektuyuschie/"
    "operativnaya_pamyat-ASgBAgICAkTGB~pm7gnYZw"
    "?cd=1&context=H4sIAAAAAAAA_wEmANn_YToxOntzOjE6InkiO3M6MTY6"
    "Ind2TXcyM1NoT1F4Rm1pUkQiO31XsWX_JgAAAA&q=ddr5+32gb"
)
PAGES_TO_REQUEST = 10
MAX_PROTECTION_TRANSITIONS = 3
MAX_QRATOR_RETRIES_PER_REQUEST = 2
REQUEST_TIMEOUT_SECONDS = 5
LOGGER = logging.getLogger(__name__)
LOG_BODY_PREVIEW_LENGTH = 4_000
LOG_HEADERS_PREVIEW_LENGTH = 2_000
DEBUG_RESPONSE_DIR = Path("firewall-debug-responses")

# Headers sent by the browser XHR in the source HAR.  Content-Type is supplied
# by ``json=...`` and Cookie is managed by the session's cookie jar.
REQUEST_HEADERS = {
    "Origin": BASE_URL,
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-GPC": "1",
    "TE": "trailers",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0"
    ),
}

# Headers of the ordinary document-navigation request from the HAR.  This
# request context is distinct from the same-origin XHR context above.
PAGE_REQUEST_HEADERS = {
    "Referer": (
        "https://www.avito.ru/moskva_i_mo/tovary_dlya_kompyutera/"
        "komplektuyuschie/operativnaya_pamyat-ASgBAgICAkTGB~pm7gnYZw"
        "?cd=1&context=H4sIAAAAAAAA_wEmANn_YToxOntzOjE6InkiO3M6MTY6"
        "Ind2TXcyM1NoT1F4Rm1pUkQiO31XsWX_JgAAAA&localPriority=0&q=ddr5+32gb"
    ),
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-GPC": "1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0"
    ),
}

CHALLENGE_REQUEST_HEADERS = {
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "X-Source": "client-browser",
}

QRATOR_FT_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": BASE_URL,
    "Referer": PAGE_REQUEST_HEADERS["Referer"],
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-GPC": "1",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
    "TE": "trailers",
    "User-Agent": PAGE_REQUEST_HEADERS["User-Agent"],
}

QRATOR_PIXEL_HEADERS = {
    "Accept": (
        "image/avif,image/webp,image/png,image/svg+xml,"
        "image/*;q=0.8,*/*;q=0.5"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": PAGE_REQUEST_HEADERS["Referer"],
    "Sec-Fetch-Dest": "image",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-GPC": "1",
    "Priority": "u=5, i",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
    "TE": "trailers",
    "User-Agent": PAGE_REQUEST_HEADERS["User-Agent"],
}


@dataclass(frozen=True)
class GeeTestLoad:
    """The initial GeeTest task returned after an HTTP 429 firewall page."""

    captcha_id: str
    challenge: str
    callback: str
    lot_number: str | None
    captcha_type: str | None


@dataclass(frozen=True)
class PageRequestResult:
    """HTTP result from one page request made after a successful PoW/no-op."""

    page: int
    status_code: int
    redirect_location: str | None = None


@dataclass(frozen=True)
class CompletedFlow:
    """A completed no-firewall or PoW flow plus the following page requests."""

    pow_unblock_ttl: int | None
    page_requests: tuple[PageRequestResult, ...]


def response_json(response: Any, *, endpoint: str) -> dict[str, Any]:
    """Raise a useful error for a non-JSON or unsuccessful endpoint response."""
    response.raise_for_status()
    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"{endpoint}: response is not JSON") from exc
    if not isinstance(body, dict):
        raise RuntimeError(f"{endpoint}: JSON response must be an object")
    return body


def challenge_jwt_from_get(body: dict[str, Any]) -> str:
    """Return ``success.result.challenge_jwt`` from ``firewallPow/get``."""
    try:
        challenge_jwt = body["success"]["result"]["challenge_jwt"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("firewallPow/get: no success.result.challenge_jwt") from exc
    if not isinstance(challenge_jwt, str) or not challenge_jwt:
        raise RuntimeError("firewallPow/get: challenge_jwt must be a non-empty string")
    return challenge_jwt


def verified_from_response(body: dict[str, Any]) -> tuple[bool, int | None]:
    """Read the verification status without accepting a truthy non-boolean."""
    try:
        result = body["success"]["result"]
        verified = result["verified"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("firewallPow/verify: no success.result.verified") from exc
    if verified is not True:
        return False, None
    unblock_ttl = result.get("unblock_ttl")
    return True, unblock_ttl if isinstance(unblock_ttl, int) else None


def pow_challenge_from_response(response: Any) -> str:
    """Read the fresh challenge issued by the captured HTTP 439 response."""
    try:
        pow_challenge = response.json()["pow_challenge"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "challenge source: no pow_challenge in JSON response"
        ) from exc
    if not isinstance(pow_challenge, str) or not pow_challenge:
        raise RuntimeError("challenge source: pow_challenge must be a non-empty string")
    return pow_challenge


def geetest_captcha_id_from_html(html: str) -> str:
    """Extract the GeeTest id embedded in the HTTP 429 firewall HTML."""
    match = re.search(r"const\s+captchaId\s*=\s*['\"]([^'\"]+)['\"]", html)
    if not match:
        raise RuntimeError("HTTP 429 firewall page: no GeeTest captchaId in HTML")
    return match.group(1)


def is_geetest_firewall_html(html: str) -> bool:
    """Return whether a firewall HTML page explicitly selects GeeTest.

    The 429 page can contain markup for several captcha providers.  The
    additional HAR selects GeeTest only when its dedicated container, loader,
    initializer, and dynamically inserted captcha id are all present.
    """
    return (
        re.search(r'id\s*=\s*["\']geetest_captcha["\']', html, re.IGNORECASE)
        is not None
        and re.search(r"initGeetest4\s*\(", html) is not None
        and re.search(
            r'(?:src\s*=\s*["\'])https://www\.avito\.st/s/captcha/gt4\.js',
            html,
            re.IGNORECASE,
        )
        is not None
        and re.search(r"const\s+captchaId\s*=\s*['\"][^'\"]+['\"]", html) is not None
    )


def parse_jsonp(body: str, *, callback: str) -> dict[str, Any]:
    """Parse the single callback invocation returned by GeeTest ``/load``."""
    match = re.fullmatch(rf"\s*{re.escape(callback)}\((.*)\)\s*;?\s*", body, re.DOTALL)
    if not match:
        raise RuntimeError("GeeTest /load: unexpected JSONP response")
    try:
        result = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise RuntimeError("GeeTest /load: invalid JSONP payload") from exc
    if not isinstance(result, dict):
        raise RuntimeError("GeeTest /load: response must contain an object")
    return result


def start_geetest(session: requests.Session, firewall_html: str) -> GeeTestLoad:
    """Perform the 429 branch through the GeeTest initial ``/load`` request.

    The page gives the captcha id.  The captured ``gt4.js`` generates the UUID
    challenge and JSONP callback client-side, which is reproduced here.
    """
    if not is_geetest_firewall_html(firewall_html):
        raise RuntimeError("HTTP 429 firewall page does not select the GeeTest branch")
    set_session_headers(session, {**REQUEST_HEADERS, "Referer": REFERER})
    captcha_id = geetest_captcha_id_from_html(firewall_html)
    captcha_response = response_json(
        session.post(
            FIREWALL_CAPTCHA_GET_URL,
            json={"refreshInternalCaptcha": False},
            timeout=REQUEST_TIMEOUT_SECONDS,
        ),
        endpoint="firewallCaptcha/get",
    )
    try:
        captcha_type = captcha_response["success"]["result"]["captcha"]["geeTest"][
            "type"
        ]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("firewallCaptcha/get: GeeTest was not selected") from exc
    if captcha_type != "geeTest":
        raise RuntimeError(
            f"firewallCaptcha/get: unsupported captcha type {captcha_type!r}"
        )

    challenge = str(uuid.uuid4())
    callback = f"geetest_{int(time.time() * 1000) + secrets.randbelow(10_000)}"
    load_response = session.get(
        GEETEST_LOAD_URL,
        params={
            "callback": callback,
            "captcha_id": captcha_id,
            "challenge": challenge,
            "client_type": "web",
            "lang": "rus",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    load_response.raise_for_status()
    load_body = parse_jsonp(load_response.text, callback=callback)
    if load_body.get("status") != "success" or not isinstance(
        load_body.get("data"), dict
    ):
        raise RuntimeError("GeeTest /load: server did not return a successful task")
    data = load_body["data"]
    return GeeTestLoad(
        captcha_id=captcha_id,
        challenge=challenge,
        callback=callback,
        lot_number=data.get("lot_number")
        if isinstance(data.get("lot_number"), str)
        else None,
        captcha_type=data.get("captcha_type")
        if isinstance(data.get("captcha_type"), str)
        else None,
    )


def log_forbidden_response(response: Any, *, context: str) -> None:
    """Log enough of a 403 body to identify the server-side protection page."""
    body = preview(response.text, limit=LOG_BODY_PREVIEW_LENGTH)
    LOGGER.warning("%s: HTTP 403; details are in firewall-debug.log", context)
    LOGGER.debug(
        "%s: HTTP 403; headers=%s; response body preview:\n%s",
        context,
        preview(repr(dict(response.headers)), limit=LOG_HEADERS_PREVIEW_LENGTH),
        body,
    )


def preview(value: str, *, limit: int) -> str:
    """Keep diagnostics useful without flooding the terminal with HTML."""
    return value if len(value) <= limit else f"{value[:limit]} … [truncated]"


def set_session_headers(session: requests.Session, headers: dict[str, str]) -> None:
    """Replace headers instead of mixing document and XHR request contexts."""
    session.headers.clear()
    session.headers.update(headers)


def is_qrator_redirect(response: Any) -> bool:
    """Return whether a 302 response belongs to the Qrator cookie flow."""
    return (
        response.status_code == 302
        and response.headers.get("server", "").strip().upper() == "QRATOR"
    )


def build_qrator_multipart(
    f_value: str,
    s_value: str,
    *,
    boundary: str | None = None,
) -> tuple[str, bytes]:
    """Build the exact two-field multipart body emitted by the Qrator bundle."""
    boundary = boundary or f"{secrets.randbelow(10**16):016d}"
    if not re.fullmatch(r"\d{16}", boundary):
        raise ValueError("Qrator multipart boundary must contain 16 digits")
    body = (
        f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="f"'
        f"\r\n\r\n{f_value}"
        f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="s"'
        f"\r\n\r\n{s_value}"
        f"\r\n--{boundary}--\r\n"
    ).encode("ascii")
    return f'multipart/form-data;boundary="{boundary}"', body


def qrator_ft_token(response: Any) -> str:
    """Read the JSON string which the bundle stores verbatim as cookie ``ft``."""
    response.raise_for_status()
    try:
        token = response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("Qrator /web/2/ft: response is not JSON") from exc
    if not isinstance(token, str) or not token:
        raise RuntimeError("Qrator /web/2/ft: response must be a non-empty string")
    return token


def qrator_pixel_id() -> int:
    """Reproduce ``floor(Math.random() * 4294967295)`` from the bundle."""
    return secrets.randbelow(0xFFFFFFFF)


def run_qrator_cookie_flow(session: requests.Session, *, context: str) -> None:
    """Perform ``/web/2/ft -> /web/1/u`` and retain every resulting cookie."""
    variant = generate_variants(
        load_f_base(DEFAULT_BASE_F),
        load_s_base(DEFAULT_BASE_S),
        count=1,
        timestamp=int(time.time()),
    )[0]
    f_value = variant["f"]
    s_value = variant["s"]
    if not isinstance(f_value, str) or not isinstance(s_value, str):
        raise RuntimeError("Qrator payload generator returned invalid f/s values")

    session.cookies.delete("f")
    session.cookies.delete("ft")
    session.cookies.set("f", f_value, domain=".avito.ru", path="/")
    content_type, multipart_body = build_qrator_multipart(f_value, s_value)
    set_session_headers(
        session,
        {**QRATOR_FT_HEADERS, "Content-Type": content_type},
    )
    ft_response = session.post(
        QRATOR_FT_URL,
        data=multipart_body,
        timeout=REQUEST_TIMEOUT_SECONDS,
        allow_redirects=False,
    )
    if ft_response.status_code != 200:
        if ft_response.status_code == 403:
            log_forbidden_response(
                ft_response,
                context=f"{context}: Qrator /web/2/ft",
            )
        else:
            LOGGER.debug(
                "%s: Qrator /web/2/ft headers=%r; body=%s",
                context,
                dict(ft_response.headers),
                preview(ft_response.text, limit=LOG_BODY_PREVIEW_LENGTH),
            )
        raise RuntimeError(
            f"{context}: Qrator /web/2/ft returned HTTP "
            f"{ft_response.status_code}"
        )
    token = qrator_ft_token(ft_response)
    # The bundle assigns responseText rather than parsed JSON. Consequently
    # the cookie value contains the JSON string's surrounding quotes.
    session.cookies.set(
        "ft",
        json.dumps(token, ensure_ascii=False, separators=(",", ":")),
        domain=".avito.ru",
        path="/",
    )

    pixel_id = qrator_pixel_id()
    set_session_headers(session, QRATOR_PIXEL_HEADERS)
    pixel_response = session.get(
        f"{QRATOR_PIXEL_URL}?{pixel_id}",
        timeout=REQUEST_TIMEOUT_SECONDS,
        allow_redirects=False,
    )
    if pixel_response.status_code != 200:
        if pixel_response.status_code == 403:
            log_forbidden_response(
                pixel_response,
                context=f"{context}: Qrator /web/1/u",
            )
        raise RuntimeError(
            f"{context}: Qrator /web/1/u returned HTTP "
            f"{pixel_response.status_code}"
        )
    content_type = pixel_response.headers.get("content-type", "").lower()
    if content_type and "image/gif" not in content_type:
        raise RuntimeError(
            f"{context}: Qrator /web/1/u returned unexpected "
            f"Content-Type {content_type!r}"
        )
    LOGGER.info(
        "%s: Qrator cookies initialized; pixel_id=%s; ft_length=%s",
        context,
        pixel_id,
        len(token),
    )


def get_with_qrator_recovery(
    session: requests.Session,
    url: str,
    *,
    session_headers: dict[str, str],
    request_headers: dict[str, str] | None = None,
    context: str,
) -> Any:
    """GET a URL and retry the exact request after a Qrator 302 flow."""
    for attempt in range(MAX_QRATOR_RETRIES_PER_REQUEST + 1):
        set_session_headers(session, session_headers)
        response = session.get(
            url,
            headers=request_headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
        if not is_qrator_redirect(response):
            return response
        log_redirect_response(response, context=context)
        if attempt == MAX_QRATOR_RETRIES_PER_REQUEST:
            raise RuntimeError(
                f"{context}: Qrator HTTP 302 remained after "
                f"{MAX_QRATOR_RETRIES_PER_REQUEST} cookie flows"
            )
        LOGGER.info(
            "%s: HTTP 302 from QRATOR, starting /web/2/ft -> /web/1/u",
            context,
        )
        run_qrator_cookie_flow(session, context=context)

    raise AssertionError("unreachable")


def redirect_target(response: Any) -> str | None:
    """Return the redirect destination exposed by curl_cffi, if any."""
    return (
        response.headers.get("location")
        or getattr(response, "redirect_url", None)
        or None
    )


def save_html_response(response: Any, *, context: str) -> Path:
    """Save the complete decoded HTML response under a filesystem-safe name."""
    DEBUG_RESPONSE_DIR.mkdir(parents=True, exist_ok=True)
    safe_context = re.sub(r"[^a-zA-Z0-9._-]+", "-", context).strip("-")
    filename = f"{safe_context or 'response'}-http-{response.status_code}.html"
    path = DEBUG_RESPONSE_DIR / filename
    path.write_text(response.text, encoding=getattr(response, "encoding", None) or "utf-8")
    return path.resolve()


def log_redirect_response(response: Any, *, context: str) -> None:
    """Log malformed or opaque 3xx responses whose destination is unavailable."""
    if redirect_target(response):
        return
    body = preview(response.text, limit=LOG_BODY_PREVIEW_LENGTH)
    meta_refresh = bool(
        re.search(r'<meta\s+http-equiv=["\']refresh["\']', response.text, re.IGNORECASE)
    )
    kind = "QRATOR meta-refresh" if meta_refresh and response.headers.get("server") == "QRATOR" else "no Location"
    html_path = save_html_response(response, context=context)
    LOGGER.warning(
        "%s: HTTP %s (%s); HTML saved to %s",
        context,
        response.status_code,
        kind,
        html_path,
    )
    LOGGER.debug(
        "%s: HTTP %s without Location; url=%s; redirect_url=%r; headers=%r; body follows:\n%s",
        context,
        response.status_code,
        response.url,
        getattr(response, "redirect_url", None),
        preview(repr(dict(response.headers)), limit=LOG_HEADERS_PREVIEW_LENGTH),
        body,
    )


def run_pow_verification(session: requests.Session, response: Any) -> int | None:
    """Complete ``firewallPow/get -> verify`` using an HTTP 439 response."""
    set_session_headers(session, {**REQUEST_HEADERS, "Referer": REFERER})
    pow_challenge = pow_challenge_from_response(response)
    get_response = session.post(
        GET_URL,
        json=build_get_payload(pow_challenge),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    challenge_jwt = challenge_jwt_from_get(
        response_json(get_response, endpoint="firewallPow/get")
    )
    verify_payload = build_verify_payload(challenge_jwt)
    verify_response = session.post(
        VERIFY_URL,
        json=verify_payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    verified, unblock_ttl = verified_from_response(
        response_json(verify_response, endpoint="firewallPow/verify")
    )
    if not verified:
        raise RuntimeError("firewallPow/verify: server returned verified=false")
    return unblock_ttl


def handle_firewall_response(
    session: requests.Session, response: Any, *, context: str
) -> int | GeeTestLoad | None:
    """Classify and handle the protection response from any request.

    HTTP 439 is the JSON PoW branch; HTTP 429 is considered GeeTest only after
    its response HTML passes the dedicated GeeTest classifier.
    """
    if response.status_code == 200:
        return None
    if response.status_code == 403:
        log_forbidden_response(response, context=context)
        raise RuntimeError(f"{context}: HTTP 403; inspect firewall-debug.log")
    if response.status_code == 439:
        LOGGER.info("%s: HTTP 439, starting firewallPow", context)
        return run_pow_verification(session, response)
    if response.status_code == 429:
        if not is_geetest_firewall_html(response.text):
            LOGGER.warning(
                "%s: HTTP 429 is not a recognized GeeTest HTML branch", context
            )
            raise RuntimeError(
                "HTTP 429 firewall page does not select the GeeTest branch"
            )
        LOGGER.info("%s: HTTP 429, starting GeeTest", context)
        return start_geetest(session, response.text)
    raise RuntimeError(
        f"{context}: expected HTTP 200, 403, 429, or 439; "
        f"received HTTP {response.status_code}"
    )


def page_url(page: int) -> str:
    """Replace only the ``p`` query parameter in the constant page URL."""
    parsed = urlsplit(PAGES_URL)
    query = [(key, value) for key, value in parse_qsl(parsed.query) if key != "p"]
    query.append(("p", str(page)))
    return urlunsplit(parsed._replace(query=urlencode(query)))


def request_pages(
    session: requests.Session,
) -> tuple[tuple[PageRequestResult, ...], Any | None]:
    """Request pages 1 through 10 after the firewall path is clear."""
    set_session_headers(session, PAGE_REQUEST_HEADERS)
    results = []
    for index in range(PAGES_TO_REQUEST):
        page = index + 1
        response = get_with_qrator_recovery(
            session,
            page_url(page),
            session_headers=PAGE_REQUEST_HEADERS,
            context=f"page p={page}",
        )
        results.append(
            PageRequestResult(
                page=page,
                status_code=response.status_code,
                redirect_location=redirect_target(response),
            )
        )
        if 300 <= response.status_code < 400:
            log_redirect_response(response, context=f"page p={page}")
        if response.status_code == 403:
            log_forbidden_response(response, context=f"page p={page}")
        if response.status_code in (429, 439):
            return tuple(results), response
    return tuple(results), None


def run() -> CompletedFlow | GeeTestLoad:
    """Obtain a challenge, then execute the recorded ``get -> verify`` flow."""
    session = requests.Session()
    set_session_headers(session, {**REQUEST_HEADERS, "Referer": REFERER})

    challenge_response = get_with_qrator_recovery(
        session,
        CHALLENGE_SOURCE_URL,
        session_headers={**REQUEST_HEADERS, "Referer": REFERER},
        request_headers=CHALLENGE_REQUEST_HEADERS,
        context="challenge source",
    )
    stage_result = handle_firewall_response(
        session, challenge_response, context="challenge source"
    )
    if isinstance(stage_result, GeeTestLoad):
        return stage_result
    pow_unblock_ttl = stage_result

    for transition in range(MAX_PROTECTION_TRANSITIONS + 1):
        page_requests, protection_response = request_pages(session)
        if protection_response is None:
            return CompletedFlow(
                pow_unblock_ttl=pow_unblock_ttl, page_requests=page_requests
            )
        if transition == MAX_PROTECTION_TRANSITIONS:
            raise RuntimeError("too many firewall transitions while requesting pages")
        page = page_requests[-1].page
        LOGGER.info("page p=%s returned a protection response; classifying it", page)
        stage_result = handle_firewall_response(
            session, protection_response, context=f"page p={page}"
        )
        if isinstance(stage_result, GeeTestLoad):
            return stage_result
        if stage_result is not None:
            pow_unblock_ttl = stage_result

    raise AssertionError("unreachable")


if __name__ == "__main__":
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    file_handler = logging.FileHandler("firewall-debug.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[console_handler, file_handler],
    )
    result = run()
    if isinstance(result, GeeTestLoad):
        print(
            "GeeTest task loaded; "
            f"captcha_id={result.captcha_id}; "
            f"lot_number={result.lot_number}; type={result.captcha_type}"
        )
    else:
        if result.pow_unblock_ttl is None:
            message = "challenge source returned HTTP 200; no firewall verification is required"
        else:
            message = "firewallPow verification succeeded"
            message += f"; unblock_ttl={result.pow_unblock_ttl}"
        print(message)
        for page_result in result.page_requests:
            message = f"page p={page_result.page}: HTTP {page_result.status_code}"
            if page_result.redirect_location:
                message += f" -> {page_result.redirect_location}"
            elif 300 <= page_result.status_code < 400:
                message += " -> Location is absent; inspect firewall-debug.log"
            print(message)

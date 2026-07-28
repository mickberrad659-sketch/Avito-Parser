import json
import re
import sys
import types
from unittest.mock import patch
from urllib.parse import parse_qsl, urlsplit

from curl_cffi.requests.cookies import Cookies

import main


class FakeResponse:
    def __init__(
        self,
        status_code,
        *,
        headers=None,
        json_value=None,
        text="",
        url="https://www.avito.ru/test",
    ):
        self.status_code = status_code
        self.headers = headers or {}
        self._json_value = json_value
        self.text = text
        self.content = text.encode()
        self.url = url
        self.redirect_url = ""
        self.closed = False

    def json(self):
        return self._json_value

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self):
        yield self.content

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, target_responses=None):
        self.headers = {}
        self.cookies = Cookies()
        self.posts = []
        self.gets = []
        self.target_responses = list(target_responses or [])

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs, dict(self.headers)))
        self.cookies.set(
            "gMltIuegZN2COuSe",
            "SERVER_COOKIE",
            domain=".avito.ru",
            path="/",
        )
        return FakeResponse(
            200,
            headers={"server": "QRATOR", "content-type": "application/json"},
            json_value="FT_TOKEN==",
            url=url,
        )

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs, dict(self.headers)))
        if re.fullmatch(r"https://www\.avito\.ru/[0-9a-f]{20}\.js", url):
            return FakeResponse(
                200,
                headers={
                    "server": "QRATOR",
                    "content-type": "application/javascript",
                },
                url=url,
            )
        if url == main.QRATOR_FAVICON_URL:
            self.cookies.set(
                "v",
                "FAVICON_COOKIE",
                domain=".avito.ru",
                path="/",
            )
            return FakeResponse(
                200,
                headers={"server": "QRATOR", "content-type": "image/x-icon"},
                url=url,
            )
        if "/web/1/u?" in url:
            self.cookies.set(
                "_adcc",
                "PIXEL_COOKIE",
                domain=".avito.ru",
                path="/",
            )
            return FakeResponse(
                200,
                headers={"server": "QRATOR", "content-type": "image/gif"},
                url=url,
            )
        if not self.target_responses:
            raise AssertionError(f"unexpected GET {url}")
        return self.target_responses.pop(0)


def test_items_url_has_exact_query_and_only_replaces_page() -> None:
    expected = [
        (key, "17" if key == "p" else value)
        for key, value in main.ITEMS_QUERY_PARAMETERS
    ]
    parsed = urlsplit(main.page_url(17))

    assert parsed.scheme == "https"
    assert parsed.netloc == "www.avito.ru"
    assert parsed.path == "/web/1/js/items"
    assert parse_qsl(parsed.query) == expected
    assert dict(expected)["categoryId"] == "98"
    assert dict(expected)["rootCategoryId"] == "6"
    assert dict(expected)["features[suggestParams][categoryID]"] == "98"
    assert dict(expected)["features[ivaItemRedesign]"] == "true"
    assert "name" not in dict(expected)


def test_qrator_cookie_flow_matches_har_shape() -> None:
    session = FakeSession()
    page_url = "https://www.avito.ru/catalog?p=1"
    qrator_html = (
        '<meta http-equiv="refresh" content="1">'
        '<script src="/f1b0f8f3fb96fe30a8e6.js"></script>'
    )
    with patch.object(main.time, "sleep") as sleep:
        main.run_qrator_cookie_flow(
            session,
            qrator_html=qrator_html,
            page_url=page_url,
            context="test",
        )

    assert len(session.posts) == 1
    post_url, post_kwargs, post_headers = session.posts[0]
    assert post_url == "https://www.avito.ru/web/2/ft"
    assert re.fullmatch(
        r'multipart/form-data;boundary="\d{16}"',
        post_headers["Content-Type"],
    )
    body = post_kwargs["data"].decode("ascii")
    f_value = re.search(r'name="f"\r\n\r\n([^\r]+)', body).group(1)
    s_value = re.search(r'name="s"\r\n\r\n([^\r]+)', body).group(1)
    assert len(f_value) == 882
    assert len(s_value) == 176
    assert session.cookies.get("f") == f_value
    assert session.cookies.get("ft") == json.dumps("FT_TOKEN==")
    assert session.cookies.get("gMltIuegZN2COuSe") == "SERVER_COOKIE"
    assert session.cookies.get("v") == "FAVICON_COOKIE"

    assert len(session.gets) == 3
    script_url, _, script_headers = session.gets[0]
    favicon_url, _, favicon_headers = session.gets[1]
    assert script_url == "https://www.avito.ru/f1b0f8f3fb96fe30a8e6.js"
    assert favicon_url == main.QRATOR_FAVICON_URL
    assert script_headers["Referer"] == page_url
    assert favicon_headers["Priority"] == "u=6"

    pixel_url, pixel_kwargs, pixel_headers = session.gets[2]
    match = re.fullmatch(r"https://www\.avito\.ru/web/1/u\?(\d+)", pixel_url)
    assert match
    assert 0 <= int(match.group(1)) < 0xFFFFFFFF
    assert "=" not in pixel_url
    assert pixel_headers["Sec-Fetch-Dest"] == "image"
    assert session.cookies.get("_adcc") == "PIXEL_COOKIE"
    assert sleep.call_count == 2


def test_original_get_is_retried_after_qrator_flow() -> None:
    target_url = "https://www.avito.ru/catalog?p=1"
    session = FakeSession(
        [
            FakeResponse(
                302,
                headers={"server": "QRATOR", "content-type": "text/html"},
                text=(
                    '<meta http-equiv="refresh" content="1">'
                    '<script src="/f1b0f8f3fb96fe30a8e6.js"></script>'
                ),
                url=target_url,
            ),
            FakeResponse(
                200,
                headers={"server": "QRATOR", "content-type": "text/html"},
                url=target_url,
            ),
        ]
    )

    with (
        patch.object(main, "log_redirect_response"),
        patch.object(main.time, "sleep"),
    ):
        result = main.get_with_qrator_recovery(
            session,
            target_url,
            session_headers=main.PAGE_REQUEST_HEADERS,
            context="page p=1",
        )

    assert result.status_code == 200
    target_gets = [call for call in session.gets if call[0] == target_url]
    assert len(target_gets) == 2
    assert len(session.posts) == 1
    assert any("/web/1/u?" in call[0] for call in session.gets)
    assert target_gets[1][2]["Referer"] == main.PAGE_REQUEST_HEADERS["Referer"]


def test_forbidden_response_is_classified_as_ip_problem() -> None:
    response = FakeResponse(
        403,
        headers={"server": "QRATOR", "content-type": "text/html; charset=utf-8"},
        text="<html><head><title>Доступ ограничен: проблема с IP</title></head></html>",
    )
    assert (
        main.forbidden_response_reason(response)
        == "Доступ ограничен: проблема с IP"
    )


def test_unknown_json_protection_body_is_saved_with_json_extension(
    tmp_path,
) -> None:
    body = (
        '{"too-many-requests":{"message":'
        '"Доступ с вашего IP-адреса временно ограничен",'
        '"link":"ru.avito:\\/\\/1\\/firewall\\/captcha\\/show"}}'
    )
    response = FakeResponse(
        429,
        headers={"content-type": "application/json; charset=utf-8"},
        text=body,
    )

    with patch.object(main, "DEBUG_RESPONSE_DIR", tmp_path):
        main.log_unrecognized_protection_response(
            response,
            context="page p=13",
        )

    saved = tmp_path / "page-p-13-http-429.json"
    assert saved.read_text(encoding="utf-8") == body


def test_json_captcha_dispatcher_is_recognized() -> None:
    response = FakeResponse(
        429,
        headers={
            "content-type": "application/json",
            "x-firewall-show-captcha": "true",
        },
        json_value={
            "too-many-requests": {
                "message": "Доступ временно ограничен",
                "link": "ru.avito://1/firewall/captcha/show",
            }
        },
    )

    assert main.is_firewall_captcha_dispatcher_response(response) is True


def test_http_429_dispatcher_is_routed_to_captcha_flow(tmp_path) -> None:
    body = (
        '{"too-many-requests":{"message":"Доступ временно ограничен",'
        '"link":"ru.avito://1/firewall/captcha/show"}}'
    )
    response = FakeResponse(
        429,
        headers={
            "content-type": "application/json",
            "x-firewall-show-captcha": "true",
        },
        json_value={
            "too-many-requests": {
                "message": "Доступ временно ограничен",
                "link": "ru.avito://1/firewall/captcha/show",
            }
        },
        text=body,
        url="https://www.avito.ru/web/1/js/items?p=13",
    )
    verified = main.GeeTestVerified(lot_number="lot")
    session = FakeSession()

    with (
        patch.object(main, "DEBUG_RESPONSE_DIR", tmp_path),
        patch.object(
            main,
            "run_firewall_captcha_dispatcher",
            return_value=verified,
        ) as dispatcher,
    ):
        result = main.handle_firewall_response(
            session,
            response,
            context="page p=13",
        )

    assert result is verified
    dispatcher.assert_called_once_with(
        session,
        referer=response.url,
    )
    assert (tmp_path / "page-p-13-http-429.json").read_text() == body


def test_firewall_captcha_get_selects_geetest_with_exact_request() -> None:
    class CaptchaSession(FakeSession):
        def post(self, url, **kwargs):
            self.posts.append((url, kwargs, dict(self.headers)))
            return FakeResponse(
                200,
                headers={"content-type": "application/json"},
                json_value={
                    "success": {
                        "result": {
                            "captcha": {
                                "geeTest": {"type": "geeTest"},
                            }
                        }
                    }
                },
                url=url,
            )

    session = CaptchaSession()
    selected = main.fetch_firewall_captcha(
        session,
        referer="https://www.avito.ru/web/1/js/items?p=13",
    )

    assert selected == {"type": "geeTest"}
    url, kwargs, headers = session.posts[0]
    assert url == main.FIREWALL_CAPTCHA_GET_URL
    assert kwargs["json"] == {"refreshInternalCaptcha": False}
    assert kwargs["allow_redirects"] is False
    assert headers["Accept"] == "*/*"
    assert headers["Priority"] == "u=4"
    assert headers["Referer"].endswith("/web/1/js/items?p=13")


def test_captcha_dispatcher_uses_bundle_geetest_id() -> None:
    load, _ = geetest_fixture()
    verified = main.GeeTestVerified(lot_number=load.lot_number)
    session = FakeSession()

    with (
        patch.object(
            main,
            "fetch_firewall_captcha",
            return_value={"type": "geeTest"},
        ),
        patch.object(
            main,
            "load_geetest_task",
            return_value=load,
        ) as load_task,
        patch.object(
            main,
            "complete_geetest_verification",
            return_value=verified,
        ) as complete,
    ):
        result = main.run_firewall_captcha_dispatcher(
            session,
            referer="https://www.avito.ru/items?p=13",
        )

    assert result is verified
    load_task.assert_called_once_with(
        session,
        captcha_id=main.GEETEST_CAPTCHA_ID,
    )
    complete.assert_called_once_with(
        session,
        load,
        referer="https://www.avito.ru/items?p=13",
    )


def test_qrator_html_is_recognized_when_status_is_429() -> None:
    response = FakeResponse(
        429,
        headers={"server": "QRATOR", "content-type": "text/html"},
        text=(
            '<meta http-equiv="refresh" content="1">'
            '<script src="/f1b0f8f3fb96fe30a8e6.js"></script>'
        ),
    )
    assert main.is_qrator_challenge_response(response)


def test_page_loop_stops_immediately_on_first_403() -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                headers={"server": "QRATOR", "content-type": "text/html"},
                url=main.page_url(1),
            ),
            FakeResponse(
                403,
                headers={"server": "QRATOR", "content-type": "text/html"},
                text="<title>Доступ ограничен: проблема с IP</title>",
                url=main.page_url(2),
            ),
        ]
    )
    with patch.object(main.time, "sleep") as sleep:
        results, protection_response = main.request_pages(session)

    assert [result.status_code for result in results] == [200, 403]
    assert protection_response is not None
    assert protection_response.status_code == 403
    first_url, first_kwargs, first_session_headers = session.gets[0]
    assert first_url == main.page_url(1)
    assert first_kwargs["headers"]["X-Source"] == "client-browser"
    assert first_kwargs["headers"]["X-Requested-With"] == "XMLHttpRequest"
    assert first_session_headers["Sec-Fetch-Mode"] == "cors"
    sleep.assert_called_once_with(main.PAGE_REQUEST_DELAY_SECONDS)


def test_document_get_retries_one_incomplete_read() -> None:
    target_url = "https://www.avito.ru/catalog?p=3"

    class InterruptedSession(FakeSession):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        def get(self, url, **kwargs):
            self.attempts += 1
            self.gets.append((url, kwargs, dict(self.headers)))
            if self.attempts == 1:
                partial = FakeResponse(
                    200,
                    headers={"content-type": "text/html"},
                    text="<html>",
                    url=url,
                )
                partial.content = b"<html>"
                raise main.IncompleteRead(
                    "partial response",
                    code=18,
                    response=partial,
                )
            return FakeResponse(
                200,
                headers={"content-type": "text/html"},
                text="<html>complete</html>",
                url=url,
            )

    session = InterruptedSession()
    with patch.object(main.time, "sleep") as sleep:
        response = main.get_with_qrator_recovery(
            session,
            target_url,
            session_headers=main.PAGE_REQUEST_HEADERS,
            context="page p=3",
        )

    assert response.status_code == 200
    assert session.attempts == 2
    sleep.assert_called_once_with(main.TRANSPORT_RETRY_DELAY_SECONDS)


def test_complete_streamed_html_is_kept_after_curl_trailer_error() -> None:
    target_url = "https://www.avito.ru/catalog?p=4"

    class CompleteThenErrorResponse(FakeResponse):
        def iter_content(self):
            yield b"<html><body>complete</body></html>"
            raise main.CurlConnectionError(
                "connection ended after body",
                code=55,
                response=self,
            )

    response = CompleteThenErrorResponse(
        200,
        headers={"content-type": "text/html"},
        url=target_url,
    )
    session = FakeSession([response])

    result = main.get_with_qrator_recovery(
        session,
        target_url,
        session_headers=main.PAGE_REQUEST_HEADERS,
        context="page p=4",
        stream_response_body=True,
    )

    assert result is response
    assert result.content == b"<html><body>complete</body></html>"
    assert len(session.gets) == 1
    assert session.gets[0][1]["stream"] is True


def geetest_fixture() -> tuple[main.GeeTestLoad, dict[str, str]]:
    seccode = {
        "captcha_id": "2d9c743cf7d63dbc9db578a608196bcd",
        "lot_number": "c622cb37692d4428b8992da29908e3ba",
        "pass_token": "p" * 64,
        "gen_time": "1785169913",
        "captcha_output": "output",
    }
    data = {
        "lot_number": seccode["lot_number"],
        "captcha_type": "slide",
        "payload": "payload",
        "process_token": "process-token",
        "pt": "1",
    }
    load = main.GeeTestLoad(
        captcha_id=seccode["captcha_id"],
        challenge="challenge",
        callback="geetest_1",
        lot_number=seccode["lot_number"],
        captcha_type="slide",
        data=data,
    )
    return load, seccode


def test_existing_geetest_load_data_is_passed_to_geeked_submit() -> None:
    load, seccode = geetest_fixture()
    observed = {}

    class SolverSession:
        base_url = ""

        def __init__(self):
            self.cookies = Cookies()

        def close(self):
            observed["closed"] = True

    class FakeGeeked:
        def __init__(self, captcha_id, lang):
            observed["captcha_id"] = captcha_id
            observed["lang"] = lang
            self.lot_number = None
            self.session = SolverSession()

        def submit_captcha(self, data):
            observed["data"] = data
            observed["lot_number"] = self.lot_number
            observed["solver_cookie"] = self.session.cookies.get(
                "captcha_v4_user"
            )
            return seccode

    fake_module = types.ModuleType("geeked")
    fake_module.Geeked = FakeGeeked
    source_session = FakeSession()
    source_session.cookies.set(
        "captcha_v4_user",
        "GEETEST_COOKIE",
        domain="gcaptcha4.geevisit.com",
        path="/",
    )
    with patch.dict(sys.modules, {"geeked": fake_module}):
        result = main.solve_geetest_load(
            load,
            source_session=source_session,
        )

    assert result == seccode
    assert observed["data"] is load.data
    assert observed["lot_number"] == load.lot_number
    assert observed["closed"] is True
    assert observed["solver_cookie"] == "GEETEST_COOKIE"


def test_avito_geetest_verify_payload_matches_bundle() -> None:
    load, seccode = geetest_fixture()

    class VerifySession(FakeSession):
        def post(self, url, **kwargs):
            self.posts.append((url, kwargs, dict(self.headers)))
            return FakeResponse(
                200,
                headers={"content-type": "application/json"},
                json_value={"success": {"result": {"verified": True}}},
                url=url,
            )

    session = VerifySession()
    verified = main.verify_geetest_with_avito(
        session,
        load,
        seccode,
        referer="https://www.avito.ru/catalog?p=1",
    )

    assert verified.lot_number == seccode["lot_number"]
    url, kwargs, headers = session.posts[0]
    assert url == main.FIREWALL_CAPTCHA_VERIFY_URL
    assert list(kwargs["json"]) == [
        "captcha",
        "hCaptchaResponse",
        "captcha_id",
        "lot_number",
        "pass_token",
        "gen_time",
        "captcha_output",
    ]
    assert kwargs["json"]["captcha"] == ""
    assert kwargs["json"]["hCaptchaResponse"] == ""
    assert re.fullmatch(r"\d{2}", headers["X-Cube"])
    assert headers["Priority"] == "u=4"
    assert headers["Referer"] == "https://www.avito.ru/catalog?p=1"

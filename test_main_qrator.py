import json
import re
from unittest.mock import patch

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
        self.url = url
        self.redirect_url = ""

    def json(self):
        return self._json_value

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


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


def test_qrator_cookie_flow_matches_har_shape() -> None:
    session = FakeSession()
    main.run_qrator_cookie_flow(session, context="test")

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

    assert len(session.gets) == 1
    pixel_url, pixel_kwargs, pixel_headers = session.gets[0]
    match = re.fullmatch(r"https://www\.avito\.ru/web/1/u\?(\d+)", pixel_url)
    assert match
    assert 0 <= int(match.group(1)) < 0xFFFFFFFF
    assert "=" not in pixel_url
    assert pixel_headers["Sec-Fetch-Dest"] == "image"
    assert session.cookies.get("_adcc") == "PIXEL_COOKIE"


def test_original_get_is_retried_after_qrator_flow() -> None:
    target_url = "https://www.avito.ru/catalog?p=1"
    session = FakeSession(
        [
            FakeResponse(
                302,
                headers={"server": "QRATOR", "content-type": "text/html"},
                text='<meta http-equiv="refresh" content="1">',
                url=target_url,
            ),
            FakeResponse(
                200,
                headers={"server": "QRATOR", "content-type": "text/html"},
                url=target_url,
            ),
        ]
    )

    with patch.object(main, "log_redirect_response"):
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

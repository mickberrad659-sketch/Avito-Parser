from uuid import uuid4
from curl_cffi import requests
import random, time, json
from geeked.sign import Signer


class CaptchaSolveRejected(Exception):
    """GeeTest accepted the verify request but rejected its solution."""

    def __init__(self, response: dict):
        self.response = response
        super().__init__(f"Failed to submit captcha: {response}")


class Geeked:
    def __init__(
        self,
        captcha_id: str,
        lang: str = "rus",
        *,
        session=None,
        request_headers=None,
        **kwargs,
    ):
        self.pass_token = None
        self.lot_number = None
        self.captcha_id = captcha_id
        self.challenge = str(uuid4())
        self.lang = lang
        self.callback = Geeked.random()
        self.session = session or requests.Session(
            impersonate="chrome124",
            **kwargs,
        )
        self.owns_session = session is None
        self.base_url = "https://gcaptcha4.geetest.com"
        self.request_headers = request_headers or {
            "connection": "keep-alive",
            "sec-ch-ua-platform": "\"Windows\"",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "sec-ch-ua-mobile": "?0",
            "accept": "*/*",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "no-cors",
            "sec-fetch-dest": "script",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9"
        }
        if self.owns_session:
            self.session.headers = dict(self.request_headers)

    @staticmethod
    def random() -> str:
        return f"geetest_{int(random.random() * 10000) + int(time.time() * 1000)}"

    def format_response(self, response: str) -> dict:
        # print(json.loads(response.split(f"{self.callback}(")[1][:-1]))
        return json.loads(response.split(f"{self.callback}(")[1][:-1])["data"]

    def load_captcha(self):
        params = {
            "captcha_id": self.captcha_id,
            "challenge": self.challenge,
            "client_type": "web",
            "lang": self.lang,
            "callback": self.callback,
        }
        res = self.session.get(
            f"{self.base_url}/load",
            params=params,
            headers=self.request_headers,
        )
        return self.format_response(res.text)

    def submit_captcha(self, data: dict) -> dict:
        self.callback = Geeked.random()

        params = {
            "callback": self.callback,
            "captcha_id": self.captcha_id,
            "client_type": "web",
            "lot_number": self.lot_number,
            "payload": data["payload"],
            "process_token": data["process_token"],
            "payload_protocol": "1",
            "pt": "1",
            "w": Signer.generate_w(
                data,
                self.captcha_id,
                data["captcha_type"],
                session=self.session,
            ),
        }
        res = self.session.get(
            f"{self.base_url}/verify",
            params=params,
            headers=self.request_headers,
        ).text
        res = self.format_response(res)

        if res.get("seccode") is None:
            raise CaptchaSolveRejected(res)

        return res["seccode"]

    def solve(self) -> dict:
        data = self.load_captcha()
        self.lot_number = data["lot_number"]
        seccode = self.submit_captcha(data)
        return seccode

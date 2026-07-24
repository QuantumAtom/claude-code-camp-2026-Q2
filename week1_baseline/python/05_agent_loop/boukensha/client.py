import http.client
import json
import socket
import ssl
import time
from urllib.parse import urlparse

from .errors import ApiError

RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
TRANSIENT_ERRORS = (
    http.client.HTTPException,
    ConnectionResetError,
    ConnectionRefusedError,
    ssl.SSLError,
    socket.gaierror,
    socket.timeout,
    TimeoutError,
)
MAX_RETRIES = 3
BASE_RETRY_DELAY = 0.5


class Client:
    def __init__(self, builder):
        self.builder = builder

    def call(self, max_output_tokens=1024, tools=None):
        parsed = urlparse(self.builder.url())
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        headers = self.builder.headers()
        body = json.dumps(
            self.builder.to_api_payload(max_output_tokens=max_output_tokens, tools=tools)
        )

        attempts = 0
        response = None
        response_body = None

        while True:
            attempts += 1
            conn = self._open_connection(parsed)
            try:
                try:
                    conn.request("POST", path, body=body, headers=headers)
                    response = conn.getresponse()
                    response_body = response.read()
                except TRANSIENT_ERRORS as e:
                    if attempts > MAX_RETRIES:
                        raise ApiError(
                            f"API request failed after {attempts} attempts: {type(e).__name__}: {e}"
                        ) from e
                    time.sleep(self._retry_delay(attempts))
                    continue
            finally:
                conn.close()

            if response.status in RETRYABLE_STATUS_CODES and attempts <= MAX_RETRIES:
                time.sleep(self._retry_delay(attempts))
                continue

            break

        if not (200 <= response.status < 300):
            suffix = "" if attempts == 1 else "s"
            raise ApiError(
                f"API request failed after {attempts} attempt{suffix} "
                f"({response.status}): {response_body.decode('utf-8', errors='replace')}"
            )

        return json.loads(response_body)

    @staticmethod
    def _open_connection(parsed):
        # 60s matches Net::HTTP's default open_timeout/read_timeout, which Ruby
        # never overrides; http.client has no default timeout (blocks forever)
        # so this is set explicitly for parity.
        if parsed.scheme == "https":
            context = ssl.create_default_context()
            return http.client.HTTPSConnection(parsed.hostname, parsed.port, timeout=60, context=context)
        return http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=60)

    @staticmethod
    def _retry_delay(attempt):
        return BASE_RETRY_DELAY * (2 ** (attempt - 1))

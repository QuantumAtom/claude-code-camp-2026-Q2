import http.client
import json
import socket
import ssl
import time
from urllib.parse import urlparse

from .errors import ApiError
from .telemetry import tracer

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
        with tracer().start_as_current_span("llm.call") as span:
            span.set_attribute("llm.url", self.builder.url())
            span.set_attribute("llm.max_output_tokens", max_output_tokens)
            span.set_attribute("gen_ai.request.model", self.builder.backend.model)
            span.set_attribute("gen_ai.operation.name", "chat")

            try:
                parsed = urlparse(self.builder.url())
                path = parsed.path or "/"
                if parsed.query:
                    path = f"{path}?{parsed.query}"

                headers = self.builder.headers()
                body = json.dumps(
                    self.builder.to_api_payload(max_output_tokens=max_output_tokens, tools=tools)
                )
                span.set_attribute("gen_ai.prompt", body)

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

                span.set_attribute("llm.attempts", attempts)
                span.set_attribute("llm.status_code", response.status)

                if response.status == 401:
                    raise ApiError("authentication failed (401) — check your API key")

                if not (200 <= response.status < 300):
                    suffix = "" if attempts == 1 else "s"
                    raise ApiError(
                        f"API request failed after {attempts} attempt{suffix} "
                        f"({response.status}): {response_body.decode('utf-8', errors='replace')}"
                    )

                span.set_attribute("gen_ai.completion", response_body.decode("utf-8", errors="replace"))

                result = json.loads(response_body)
                usage = result.get("usage") or {}
                if usage.get("input_tokens") is not None:
                    span.set_attribute("gen_ai.usage.input_tokens", usage["input_tokens"])
                if usage.get("output_tokens") is not None:
                    span.set_attribute("gen_ai.usage.output_tokens", usage["output_tokens"])
                # result["model"]/result["stop_reason"] are Anthropic's response
                # shape -- same caveat as gen_ai.usage.* above: OpenAI's
                # Responses API happens to match, but Gemini
                # (usageMetadata/finishReason nested under candidates) and
                # Ollama (no stop_reason field at all) won't populate these
                # two attributes.
                if result.get("model"):
                    span.set_attribute("gen_ai.response.model", result["model"])
                if result.get("stop_reason"):
                    span.set_attribute("gen_ai.response.finish_reasons", [result["stop_reason"]])

                return result
            except Exception:
                # start_as_current_span already records the exception and
                # sets the span's error status for anything that escapes
                # this block -- no need to duplicate that here. This except
                # exists only to guarantee gen_ai.response.finish_reasons is
                # present even on failure; the success path above only
                # reaches its own finish_reasons line after a full round
                # trip, so this and that are mutually exclusive.
                span.set_attribute("gen_ai.response.finish_reasons", ["error"])
                raise

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

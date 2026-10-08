"""Provider backends: Jev (TypeSafe) and the OpenAI Decisions API.

A backend turns a state and a validated question set into a provider request,
sends it through a transport, and parses the response into a `Decision`. The
transport is a plain callable so tests, proxies, and gateways can replace the
standard-library HTTP client.

Jev is also served by gateways under other paths (for example `/v1/decisions`
with model `typesafe/jev`); set `base_url`, `path`, and `model` for those.
"""

import json
import math
import os
import time
import urllib.error
import urllib.request

from .answers import Decision, parse_answers
from .errors import APIError, DecisionError, ResponseError
from .questions import Choice, Noul, Score

DEFAULT_TIMEOUT = 30.0


def urllib_transport(url, headers, body, timeout):
    """POST `body` (bytes) as JSON and return the decoded JSON response."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        text = error.read().decode("utf-8", "replace")
        raise APIError(f"HTTP {error.code} from {url}: {text[:500]}", error.code, text) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise APIError(f"could not reach {url}: {error}") from error
    try:
        return json.loads(payload)
    except json.JSONDecodeError as error:
        raise ResponseError(f"response from {url} is not JSON: {error}") from error


def _state_text(state):
    """Render a state for providers that take text input."""
    if isinstance(state, str):
        return state
    if isinstance(state, dict):
        return json.dumps(state, sort_keys=True, ensure_ascii=False)
    return "\n\n".join(state)


def _check_state(state):
    if isinstance(state, str):
        ok = bool(state.strip())
    elif isinstance(state, dict):
        ok = bool(state)
    elif isinstance(state, (list, tuple)):
        ok = bool(state) and all(isinstance(item, str) and item.strip() for item in state)
    else:
        ok = False
    if not ok:
        raise DecisionError("state must be non-empty text, a JSON object, or a list of non-empty strings")
    return list(state) if isinstance(state, tuple) else state


class HTTPBackend:
    """Shared request, retry, and response handling."""

    name = "http"
    default_base_url = ""
    default_path = ""
    default_model = ""
    api_key_env = ""
    model_env = ""

    def __init__(self, api_key=None, model=None, base_url=None, path=None, timeout=DEFAULT_TIMEOUT,
                 max_retries=2, backoff=0.5, transport=None, sleep=time.sleep, env=None):
        env = os.environ if env is None else env
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not (
                math.isfinite(timeout) and timeout > 0):
            raise DecisionError(f"{self.name}: timeout must be a positive number of seconds")
        self.api_key = api_key if api_key is not None else env.get(self.api_key_env)
        self.model = model or env.get(self.model_env) or self.default_model
        self.base_url = (base_url or self.default_base_url).rstrip("/")
        self.path = path or self.default_path
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.transport = transport or urllib_transport
        self._sleep = sleep

    @property
    def url(self):
        return self.base_url + self.path

    def build_request(self, state, questions):
        raise NotImplementedError

    def headers(self):
        if not self.api_key:
            raise DecisionError(f"{self.name}: no API key; set {self.api_key_env} or pass api_key")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def decide(self, state, questions):
        state = _check_state(state)
        body = json.dumps(self.build_request(state, questions)).encode("utf-8")
        headers = self.headers()
        attempt = 0
        while True:
            try:
                raw = self.transport(self.url, headers, body, self.timeout)
                break
            except APIError as error:
                if not error.retryable or attempt >= self.max_retries:
                    raise
                self._sleep(self.backoff * (2 ** attempt))
                attempt += 1
        return self.parse_response(raw, questions)

    def parse_response(self, raw, questions):
        if not isinstance(raw, dict):
            raise ResponseError(f"{self.name}: response must be a JSON object")
        if "error" in raw and "answers" not in raw:
            raise APIError(f"{self.name}: provider error: {raw['error']}", body=raw)
        if "answers" not in raw:
            raise ResponseError(f"{self.name}: response has no answers")
        usage = raw.get("usage")
        if usage is None and "credits_used" in raw:
            usage = {"credits_used": raw["credits_used"]}
        return Decision(
            answers=parse_answers(raw["answers"], questions),
            backend=self.name,
            model=raw.get("model", self.model),
            usage=usage if isinstance(usage, dict) else {},
            id=raw.get("id"),
            raw=raw,
        )


class JevBackend(HTTPBackend):
    """TypeSafe's Jev System One model: POST /v1/systemone with a question map."""

    name = "jev"
    default_base_url = "https://api.typesafe.ai"
    default_path = "/v1/systemone"
    default_model = "jev-latest"
    api_key_env = "TYPESAFE_API_KEY"
    model_env = "JEV_MODEL"

    def build_request(self, state, questions):
        encoded = {}
        for question in questions:
            item = {"type": question.type, "instructions": question.instructions}
            if isinstance(question, Choice):
                item["criteria"] = dict(question.options)
            elif isinstance(question, Score):
                item["criteria"] = list(question.levels)
            encoded[question.name] = item
        return {"model": self.model, "state": state, "questions": encoded}


class OpenAIDecisionsBackend(HTTPBackend):
    """OpenAI Decisions API: POST /v1/decisions with a named question list."""

    name = "openai"
    default_base_url = "https://api.openai.com"
    default_path = "/v1/decisions"
    default_model = "gpt-6-luna"
    api_key_env = "OPENAI_API_KEY"
    model_env = "OPENAI_DECISIONS_MODEL"

    def build_request(self, state, questions):
        encoded = []
        for question in questions:
            item = {"name": question.name, "instructions": question.instructions}
            if isinstance(question, Noul):
                item["type"] = "predicate"
            elif isinstance(question, Choice):
                item["type"] = "choice"
                item["choices"] = [
                    {"value": label, "description": description}
                    for label, description in question.options.items()
                ]
            else:
                item["type"] = "score"
                item["levels"] = [{"label": level} for level in question.levels]
            encoded.append(item)
        return {"model": self.model, "input": _state_text(state), "questions": encoded}


BACKENDS = {"jev": JevBackend, "openai": OpenAIDecisionsBackend}


def create_backend(name, **options):
    """Create a backend by name (`jev` or `openai`)."""
    try:
        cls = BACKENDS[name]
    except KeyError:
        raise DecisionError(f"unknown backend {name!r}; choose one of {sorted(BACKENDS)}") from None
    return cls(**options)

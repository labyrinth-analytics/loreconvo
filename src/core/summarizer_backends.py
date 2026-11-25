"""Provider-swappable LLM backend registry for the session summarizer (SH-107043).

One registry answers "which LLM summarizes, and how is it called": built-in
entries plus an optional overlay under the ``summarizer`` key of the existing
``~/.loreconvo/config.json``. Exactly two wire protocols exist
(``anthropic-messages`` and ``openai-chat``); a new provider is a config entry,
never a code branch.

Invariants (architecture proposal loreconvo_summarizer-provider-backends_20261123):

- Default behavior is unchanged: with nothing configured the backend is
  ``anthropic-haiku`` and the request is byte-identical to the pre-registry
  code (golden fixture test).
- No ambient provider key is ever read. Built-ins carry fixed key envs; an
  overlay entry's key env is DERIVED from its id
  (``LORECONVO_<ID>_API_KEY``), so config cannot point at another secret.
- A bad or incomplete configuration FAILS CLOSED: ``BackendConfigError`` is
  raised before any network call and the caller skips summarization. There
  is never a silent fallback to a different provider.
- Logging never includes URLs, keys, request or response bodies: ids and
  model names are regex-validated before use, error reasons are fixed
  literals or exception class names.
- Transport is stdlib ``urllib`` only: HTTP redirects are refused (an auth
  header is never forwarded to another host); loopback ``http://`` targets
  bypass environment proxies; the default Anthropic backend keeps the
  environment-proxy behavior it always had.

Diagnostic (no network): ``python -m loreconvo.core.summarizer_backends --check``.
"""

import argparse
import dataclasses
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .config import SUMMARIZER_API_KEY_ENV

PROTOCOL_ANTHROPIC = "anthropic-messages"
PROTOCOL_OPENAI = "openai-chat"
PROTOCOLS = frozenset({PROTOCOL_ANTHROPIC, PROTOCOL_OPENAI})

DEFAULT_BACKEND_ID = "anthropic-haiku"
BACKEND_ENV = "LORECONVO_SUMMARIZER_BACKEND"
CONFIG_KEY = "summarizer"

# The only request-body knobs an overlay may add. A provider needing another
# one is a reviewed one-line change here, not an open channel. model,
# messages, system, stream, tools and the token-limit fields are never allowed.
EXTRA_BODY_ALLOWED = frozenset({"store", "reasoning_effort", "temperature", "top_p", "seed"})
MAX_TOKENS_FIELDS = frozenset({"max_tokens", "max_completion_tokens"})

_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,128}$")
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_OVERLAY_FIELDS = frozenset({
    "protocol", "base_url", "model", "extra_body", "max_input_chars",
    "max_output_tokens", "timeout_s", "max_tokens_field", "key_optional",
})
_MAX_BODY_BYTES = 1024 * 1024
_MAX_EXTRA_STR_LEN = 256
_ANTHROPIC_VERSION = "2023-06-01"


class BackendConfigError(ValueError):
    """The selected backend configuration is invalid or unknown. Fail closed."""


class BackendResponseError(RuntimeError):
    """The provider answered, but not with a usable summary."""


class BackendTransportError(RuntimeError):
    """The request did not complete. ``str()`` is a class name or fixed reason
    plus an optional HTTP status -- never provider error text."""

    def __init__(self, reason, status=None):
        self.reason = reason
        self.status = status
        super().__init__(reason if status is None else f"{reason}:{status}")


def derive_key_env(backend_id):
    """Key env for an overlay backend: LORECONVO_<ID>_API_KEY (hyphens -> underscores)."""
    return "LORECONVO_" + backend_id.upper().replace("-", "_") + "_API_KEY"


@dataclasses.dataclass(frozen=True)
class SummarizerBackend:
    id: str
    protocol: str
    base_url: str
    model: str
    key_env: str
    extra_body: dict
    max_input_chars: int
    max_output_tokens: int
    timeout_s: float
    max_tokens_field: str = "max_tokens"
    key_optional: bool = False

    @property
    def host(self):
        return urllib.parse.urlsplit(self.base_url).hostname or ""

    @property
    def is_loopback(self):
        return self.host in _LOOPBACK_HOSTS

    @property
    def endpoint(self):
        """Full request URL. anthropic-messages: base_url IS the Messages
        endpoint; openai-chat: base_url + /chat/completions."""
        if self.protocol == PROTOCOL_ANTHROPIC:
            return self.base_url
        return self.base_url + "/chat/completions"


BUILTIN_BACKENDS = {
    DEFAULT_BACKEND_ID: SummarizerBackend(
        id=DEFAULT_BACKEND_ID,
        protocol=PROTOCOL_ANTHROPIC,
        base_url="https://api.anthropic.com/v1/messages",
        model="claude-haiku-4-5-20251001",
        key_env=SUMMARIZER_API_KEY_ENV,
        extra_body={},
        max_input_chars=40000,
        max_output_tokens=1024,
        timeout_s=60,
    ),
    "ollama-local": SummarizerBackend(
        id="ollama-local",
        protocol=PROTOCOL_OPENAI,
        base_url="http://127.0.0.1:11434/v1",
        model="llama3.1",
        key_env=derive_key_env("ollama-local"),
        extra_body={},
        max_input_chars=40000,
        max_output_tokens=1024,
        timeout_s=120,
        key_optional=True,
    ),
}
_BUILTIN_KEY_ENVS = frozenset(b.key_env for b in BUILTIN_BACKENDS.values())
_DEFAULTS = BUILTIN_BACKENDS[DEFAULT_BACKEND_ID]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _int_in_range(value, lo, hi, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise BackendConfigError(f"{name} must be an integer")
    if not lo <= value <= hi:
        raise BackendConfigError(f"{name} out of range [{lo}, {hi}]")
    return value


def _number_in_range(value, lo, hi, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BackendConfigError(f"{name} must be a number")
    if not math.isfinite(value) or not lo <= value <= hi:
        raise BackendConfigError(f"{name} out of range [{lo}, {hi}]")
    return value


def _validate_base_url(url):
    if not isinstance(url, str) or not url:
        raise BackendConfigError("base_url missing")
    if url != url.strip() or not url.isascii() or not url.isprintable():
        raise BackendConfigError("base_url contains whitespace or non-ASCII characters")
    if "?" in url or "#" in url:
        raise BackendConfigError("base_url must not carry a query or fragment")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("https", "http"):
        raise BackendConfigError("base_url scheme must be https (http only for loopback)")
    if "@" in parts.netloc:
        raise BackendConfigError("base_url must not contain userinfo")
    if parts.netloc != parts.netloc.lower():
        raise BackendConfigError("base_url host must be lowercase")
    host = parts.hostname
    if not host:
        raise BackendConfigError("base_url has no host")
    try:
        parts.port
    except ValueError:
        raise BackendConfigError("base_url port is invalid") from None
    if parts.scheme == "http" and host not in _LOOPBACK_HOSTS:
        raise BackendConfigError("http base_url is only allowed for 127.0.0.1, ::1 or localhost")
    path = parts.path
    if path.endswith("/"):
        path = path[:-1]
        if path.endswith("/"):
            raise BackendConfigError("base_url has repeated trailing slashes")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _validate_extra_body(raw):
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise BackendConfigError("extra_body must be an object")
    out = {}
    for key, value in raw.items():
        if key not in EXTRA_BODY_ALLOWED:
            raise BackendConfigError("extra_body contains a key outside the allowlist")
        if isinstance(value, bool):
            pass
        elif isinstance(value, (int, float)):
            if not math.isfinite(value):
                raise BackendConfigError("extra_body numbers must be finite")
        elif isinstance(value, str):
            if len(value) > _MAX_EXTRA_STR_LEN or not value.isprintable():
                raise BackendConfigError("extra_body string value too long or not printable")
        else:
            raise BackendConfigError("extra_body values must be bool, number or string")
        out[key] = value
    return out


def validate_backend(backend_id, raw):
    """Build a validated, frozen SummarizerBackend from one overlay entry.

    Raises BackendConfigError on any problem. Only the SELECTED entry is ever
    validated; a typo in an unselected entry surfaces when it is selected.
    """
    if not isinstance(backend_id, str) or not _ID_RE.match(backend_id):
        raise BackendConfigError("backend id must match ^[a-z][a-z0-9-]{0,31}$")
    if backend_id in BUILTIN_BACKENDS:
        raise BackendConfigError("config overlay may not redefine a built-in backend")
    key_env = derive_key_env(backend_id)
    if key_env in _BUILTIN_KEY_ENVS:
        raise BackendConfigError("backend id derives a reserved key env")
    if not isinstance(raw, dict):
        raise BackendConfigError("backend entry must be an object")
    if set(raw) - _OVERLAY_FIELDS:
        raise BackendConfigError("backend entry contains an unknown field")

    protocol = raw.get("protocol")
    if protocol not in PROTOCOLS:
        raise BackendConfigError("protocol must be anthropic-messages or openai-chat")
    model = raw.get("model")
    if not isinstance(model, str) or not _MODEL_RE.match(model):
        raise BackendConfigError("model missing or not in ^[A-Za-z0-9._:/-]{1,128}$")
    base_url = _validate_base_url(raw.get("base_url"))

    max_input_chars = _int_in_range(
        raw.get("max_input_chars", _DEFAULTS.max_input_chars), 1000, 2000000, "max_input_chars")
    max_output_tokens = _int_in_range(
        raw.get("max_output_tokens", _DEFAULTS.max_output_tokens), 64, 8192, "max_output_tokens")
    timeout_s = _number_in_range(
        raw.get("timeout_s", _DEFAULTS.timeout_s), 1, 300, "timeout_s")

    max_tokens_field = raw.get("max_tokens_field", "max_tokens")
    if max_tokens_field not in MAX_TOKENS_FIELDS:
        raise BackendConfigError("max_tokens_field must be max_tokens or max_completion_tokens")
    if protocol == PROTOCOL_ANTHROPIC and max_tokens_field != "max_tokens":
        raise BackendConfigError("anthropic-messages only supports max_tokens")

    key_optional = raw.get("key_optional", False)
    if not isinstance(key_optional, bool):
        raise BackendConfigError("key_optional must be true or false")
    host = urllib.parse.urlsplit(base_url).hostname
    if key_optional and (protocol != PROTOCOL_OPENAI or host not in _LOOPBACK_HOSTS):
        raise BackendConfigError("key_optional is only allowed for openai-chat loopback backends")

    extra_body = _validate_extra_body(raw.get("extra_body"))

    return SummarizerBackend(
        id=backend_id,
        protocol=protocol,
        base_url=base_url,
        model=model,
        key_env=key_env,
        extra_body=extra_body,
        max_input_chars=max_input_chars,
        max_output_tokens=max_output_tokens,
        timeout_s=timeout_s,
        max_tokens_field=max_tokens_field,
        key_optional=key_optional,
    )


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def _config_path():
    from .config import Config
    try:
        return Path(os.fspath(Config().config_path))
    except Exception as exc:
        raise BackendConfigError("cannot locate config.json") from exc


def _load_summarizer_section(config_path):
    config_path = Path(config_path)
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BackendConfigError("config.json is unreadable or not valid JSON") from exc
    if not isinstance(data, dict):
        raise BackendConfigError("config.json root must be an object")
    section = data.get(CONFIG_KEY)
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise BackendConfigError("summarizer config must be an object")
    return section


def resolve_backend_id(section):
    """Selection precedence: env LORECONVO_SUMMARIZER_BACKEND > config
    summarizer.backend > anthropic-haiku."""
    env_value = os.environ.get(BACKEND_ENV, "").strip()
    if env_value:
        return env_value
    configured = section.get("backend")
    if configured is None:
        return DEFAULT_BACKEND_ID
    if not isinstance(configured, str):
        raise BackendConfigError("summarizer.backend must be a string")
    return configured


def get_active_backend(config_path=None):
    """Return the validated active backend. Raises BackendConfigError when the
    selection is unknown or its configuration is invalid (fail closed)."""
    if config_path is None:
        config_path = _config_path()
    section = _load_summarizer_section(config_path)
    backend_id = resolve_backend_id(section)
    if not _ID_RE.match(backend_id):
        raise BackendConfigError("backend id must match ^[a-z][a-z0-9-]{0,31}$")
    overlay = section.get("backends")
    if overlay is None:
        overlay = {}
    if not isinstance(overlay, dict):
        raise BackendConfigError("summarizer.backends must be an object")
    if backend_id in BUILTIN_BACKENDS:
        if backend_id in overlay:
            raise BackendConfigError("config overlay may not redefine a built-in backend")
        return BUILTIN_BACKENDS[backend_id]
    if backend_id not in overlay:
        raise BackendConfigError("unknown backend id")
    return validate_backend(backend_id, overlay[backend_id])


def get_api_key(backend):
    """The active backend's key from the environment only; '' when unset."""
    return os.environ.get(backend.key_env, "")


def summarizer_configured(config_path=None):
    """Hook-dispatch gate: should the summarizer subprocess be spawned?

    True when the active backend resolves and has its key (or needs none).
    Also True when the configuration is INVALID, so the subprocess runs and
    writes the reason to summarizer.log instead of the hook skipping silently.
    False only in the unconfigured state: a selected backend whose key is unset
    (for a fresh install that is anthropic-haiku without
    LORECONVO_ANTHROPIC_API_KEY, exactly today's behavior).
    """
    try:
        backend = get_active_backend(config_path)
    except BackendConfigError:
        return True
    return bool(get_api_key(backend)) or backend.key_optional


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would forward the auth header to a host the customer did not
    configure. Refuse it; the caller treats it as a transport failure."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BackendTransportError("redirect_refused", status=code)


def build_opener(backend):
    handlers = [_RefuseRedirect()]
    if backend.is_loopback:
        # A local server must not be routed through HTTP(S)_PROXY. The default
        # Anthropic backend keeps urllib's environment-proxy behavior.
        handlers.insert(0, urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


def build_request(backend, api_key, prompt, excerpt):
    """Build the POST request. Body key order and serialization are part of
    the default-backend golden contract: model, <tokens field>, messages,
    then extra_body; json.dumps default separators."""
    content = f"{prompt}\n\n<transcript>\n{excerpt}\n</transcript>"
    messages = [{"role": "user", "content": content}]
    if backend.protocol == PROTOCOL_ANTHROPIC:
        body = {"model": backend.model, "max_tokens": backend.max_output_tokens,
                "messages": messages}
        headers = {
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
    else:
        body = {"model": backend.model, backend.max_tokens_field: backend.max_output_tokens,
                "messages": messages}
        headers = {"content-type": "application/json"}
        if api_key:
            headers["authorization"] = "Bearer " + api_key
        elif not backend.key_optional:
            raise BackendConfigError("api key required for this backend")
    body.update(backend.extra_body)
    payload = json.dumps(body).encode("utf-8")
    return urllib.request.Request(backend.endpoint, data=payload, headers=headers, method="POST")


def _urlopen(opener, req, timeout):
    """The single network seam. Tests patch this; nothing else opens sockets."""
    return opener.open(req, timeout=timeout)


def _send(backend, req):
    opener = build_opener(backend)
    try:
        with _urlopen(opener, req, backend.timeout_s) as resp:
            body = resp.read(_MAX_BODY_BYTES + 1)
    except BackendTransportError:
        raise
    except urllib.error.HTTPError as exc:
        raise BackendTransportError("http_error", status=exc.code) from exc
    except Exception as exc:
        raise BackendTransportError(type(exc).__name__) from exc
    if not isinstance(body, (bytes, bytearray)) or len(body) > _MAX_BODY_BYTES:
        raise BackendResponseError("response_too_large")
    return bytes(body)


# ---------------------------------------------------------------------------
# Response parsing -- one function per protocol, typed, never index-blind
# ---------------------------------------------------------------------------

def _extract_anthropic_text(data):
    blocks = data.get("content")
    if not isinstance(blocks, list):
        raise BackendResponseError("no_text_block")
    parts = [
        block["text"] for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    if not parts:
        raise BackendResponseError("no_text_block")
    return "".join(parts)


def _has_reasoning(message):
    for field in ("reasoning", "reasoning_content"):
        value = message.get(field)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _extract_openai_text(data):
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise BackendResponseError("no_text_content")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise BackendResponseError("no_text_content")
    content = message.get("content")
    # SH-107231: list-form content is a valid shape handled by the elif below;
    # only raise reasoning_exhausted_output when content is genuinely
    # empty/whitespace/absent (string or None), not when it's a list.
    if not isinstance(content, list) and not (isinstance(content, str) and content.strip()) and _has_reasoning(message):
        # Reasoning model spent the whole output budget on hidden reasoning
        # (SH-107219). Only the presence of the field is checked, never its text.
        raise BackendResponseError("reasoning_exhausted_output")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = [
            part["text"] for part in content
            if isinstance(part, dict) and part.get("type") == "text"
            and isinstance(part.get("text"), str)
        ]
        if not parts:
            raise BackendResponseError("no_text_content")
        text = "".join(parts)
    else:
        # null, missing, refusal-only or tool-call-only. Provider reasoning /
        # reasoning_content fields are never read.
        raise BackendResponseError("no_text_content")
    if not text.strip():
        raise BackendResponseError("no_text_content")
    return text


def _parse_summary_json(text):
    text = text.strip()
    if text.startswith("```"):
        pieces = text.split("\n", 1)
        text = pieces[1] if len(pieces) > 1 else ""
        text = text.rsplit("```", 1)[0].strip()
    try:
        result = json.loads(text)
    except ValueError:
        raise BackendResponseError("invalid_json") from None
    if not isinstance(result, dict):
        raise BackendResponseError("non_object_result")
    return result


def parse_response(backend, body):
    return _parse_summary_json(_extract_text(backend, body))


def call(backend, api_key, prompt, excerpt):
    """One attempt: build, send, parse. Raises BackendConfigError,
    BackendTransportError or BackendResponseError; never retries."""
    req = build_request(backend, api_key, prompt, excerpt)
    body = _send(backend, req)
    return parse_response(backend, body)


_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
SYNC_TIMEOUT_CAP_S = 30


def _extract_text(backend, body):
    try:
        data = json.loads(body)
    except ValueError:
        raise BackendResponseError("non_json_body") from None
    if not isinstance(data, dict):
        raise BackendResponseError("non_object_body")
    if backend.protocol == PROTOCOL_ANTHROPIC:
        return _extract_anthropic_text(data)
    return _extract_openai_text(data)


def call_text(backend, api_key, prompt, excerpt, *, max_chars):
    """One plain-text attempt: build, send, extract, sanitize. Never returns "".

    Output contract (SH-107219): stripped; control characters other than
    newline and tab removed; empty after that -> BackendResponseError
    ("empty_text"); longer than max_chars -> truncated. Raises
    BackendConfigError, BackendTransportError or BackendResponseError;
    never retries.
    """
    req = build_request(backend, api_key, prompt, excerpt)
    text = _extract_text(backend, _send(backend, req))
    text = _CONTROL_CHARS_RE.sub("", text).strip()
    if not text:
        raise BackendResponseError("empty_text")
    return text[:max_chars]


# ---------------------------------------------------------------------------
# --check diagnostic
# ---------------------------------------------------------------------------

def _installed_version():
    try:
        from importlib.metadata import version
        return version("loreconvo")
    except Exception:
        return "unknown (not installed as a package)"


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m loreconvo.core.summarizer_backends",
        description="Validate the summarizer backend configuration. Makes no request "
                    "and never prints a key value.")
    parser.add_argument("--check", action="store_true", required=True,
                        help="resolve and validate the active backend")
    parser.add_argument("--config", default=None,
                        help="path to config.json (default: the LoreConvo data directory)")
    args = parser.parse_args(argv)

    print(f"loreconvo version: {_installed_version()}")
    print(f"{BACKEND_ENV}: {'SET' if os.environ.get(BACKEND_ENV, '').strip() else 'unset'}")
    try:
        backend = get_active_backend(args.config)
    except BackendConfigError as exc:
        print(f"backend: INVALID -- {exc}")
        print("summarization will be skipped (fail closed); no request was made")
        return 1
    print(f"backend: {backend.id}")
    print(f"protocol: {backend.protocol}")
    print(f"host: {backend.host}")
    print(f"model: {backend.model}")
    if os.environ.get(backend.key_env):
        key_state, rc = "SET", 0
    elif backend.key_optional:
        key_state, rc = "unset (optional for this backend)", 0
    else:
        key_state, rc = "UNSET -- summarization will be skipped", 1
    print(f"key env: {backend.key_env} {key_state}")
    if backend.protocol == PROTOCOL_OPENAI and "reasoning_effort" not in backend.extra_body:
        print("note: reasoning models (for example qwen3.5) may return empty output "
              "unless the overlay sets extra_body {\"reasoning_effort\": \"none\"}")
    print("no request was made")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

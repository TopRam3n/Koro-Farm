"""Model provider clients for the optional recovery decider. No business logic lives here.

A client sends one request (system prompt, user content, the decision JSON schema) and returns a `RawCompletion`:
answer text with any model reasoning removed, token usage, latency and identifiers. Model reasoning is never
returned, stored or logged; only its token count is kept.

Providers (AGENT_MODEL_PROVIDER): none (default), minimax, nebius, anthropic. Exactly one provider is used; after an
error the decider falls back to deterministic rules and never switches to another paid provider.

Configuration is per provider, from the environment only:
  MINIMAX_API_KEY, MINIMAX_MODEL (required), MINIMAX_BASE_URL, MINIMAX_TIMEOUT_SECONDS, MINIMAX_REASONING_EFFORT,
  MINIMAX_SERVICE_TIER
  NEBIUS_API_KEY, NEBIUS_MODEL (required), NEBIUS_BASE_URL, NEBIUS_TIMEOUT_SECONDS, NEBIUS_STRUCTURED_OUTPUT
  ANTHROPIC_API_KEY (or another Anthropic SDK credential source), ANTHROPIC_MODEL, ANTHROPIC_TIMEOUT_SECONDS
Base URLs must be https on the provider's documented host unless AGENT_MODEL_ALLOW_CUSTOM_ENDPOINT=true.
SDKs are optional: pip install "./src/backend[model]" (openai, for MiniMax and Nebius) or "[anthropic]".
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field, replace
from typing import Protocol
from urllib.parse import urlparse

log = logging.getLogger("korofarm.recovery.model")

PROVIDERS = ("minimax", "nebius", "anthropic")
DEFAULT_ENDPOINTS = {"minimax": "https://api.minimax.io/v1", "nebius": "https://api.tokenfactory.nebius.com/v1/",
                     "anthropic": "https://api.anthropic.com"}
ALLOWED_HOSTS = {"minimax": {"api.minimax.io"}, "nebius": {"api.tokenfactory.nebius.com"}, "anthropic": {"api.anthropic.com"}}
DEFAULT_TIMEOUTS = {"minimax": 60.0, "nebius": 45.0, "anthropic": 60.0}
MAX_OUTPUT_TOKENS = 4000


class ProviderError(RuntimeError):
    """The provider could not produce an answer (configuration, network, timeout, refusal, truncation, format)."""

    def __init__(self, message: str, kind: str = "error", completion: "RawCompletion | None" = None):
        super().__init__(message)
        self.kind = kind            # unavailable | configuration | timeout | refusal | truncated | format | error
        self.completion = completion


class ModelUnavailable(ProviderError):
    """The configured model is not offered to this account or region."""

    def __init__(self, message: str):
        super().__init__(message, "unavailable")


# --- Secrets ----------------------------------------------------------------------------------------------------

_SECRET_PATTERNS = [re.compile(p) for p in (r"sk-[A-Za-z0-9_\-]{8,}", r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}",
                                             r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")]


def scrub(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Remove anything that looks like a credential before a message is logged or stored."""
    for secret in secrets:
        if secret and len(secret) >= 6:
            text = text.replace(secret, "[redacted]")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text


# --- Configuration and capability profiles ----------------------------------------------------------------------

@dataclass(frozen=True)
class ModelProfile:
    """How to ask one model for structured output and how it returns reasoning.

    structured: modes tried in order. json_schema (strict, wrapped), json_object, tool (single function), prompt
    (schema in the prompt only). Every mode is followed by our own strict parsing and validation.
    """
    structured: tuple[str, ...] = ("prompt",)
    reasoning_split: bool = False           # MiniMax: return thinking in reasoning_content, not in content
    reasoning_effort: str | None = None     # MiniMax-M3.1-Flash only (low ... max); None: not sent
    service_tier: str | None = None         # MiniMax-M3 only: standard | priority
    notes: str = ""


PROFILES: dict[tuple[str, str], ModelProfile] = {
    # MiniMax's chat API does not document response_format; the schema goes in the prompt. Thinking is split out.
    ("minimax", "MiniMax-M3"): ModelProfile(("prompt",), reasoning_split=True, service_tier="standard",
                                            notes="response_format not documented; thinking adaptive; temperature ignored"),
    ("minimax", "MiniMax-M3.1-Flash"): ModelProfile(("prompt",), reasoning_split=True, reasoning_effort="low",
                                                    notes="always thinks; effort low by default; temperature ignored"),
    # Nebius documents json_schema and json_object for models tagged "JSON mode"; fall back in that order.
    ("nebius", "Qwen/Qwen3-30B-A3B-Instruct-2507"): ModelProfile(("json_schema", "json_object", "prompt")),
    ("nebius", "Qwen/Qwen3.5-397B-A17B"): ModelProfile(("json_schema", "json_object", "prompt"),
                                                       notes="may return reasoning in <think> tags; stripped"),
}


def profile_for(provider: str, model: str) -> ModelProfile:
    if (provider, model) in PROFILES:
        return PROFILES[(provider, model)]
    if provider == "nebius":
        return ModelProfile(("json_schema", "json_object", "prompt"), notes="unprofiled Nebius model")
    if provider == "minimax":
        return ModelProfile(("prompt",), reasoning_split=True, notes="unprofiled MiniMax model")
    return ModelProfile(("json_schema",))


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    base_url: str
    timeout: float
    profile: ModelProfile
    api_key: str | None = field(default=None, repr=False)  # never printed, logged or stored

    @property
    def host(self) -> str:
        return urlparse(self.base_url).hostname or ""

    def describe(self) -> dict:
        """Safe to log and store: no credential."""
        return {"provider": self.provider, "model": self.model, "host": self.host, "timeout_s": self.timeout,
                "structured": list(self.profile.structured), "reasoning_effort": self.profile.reasoning_effort,
                "service_tier": self.profile.service_tier, "key_present": bool(self.api_key)}


class ConfigurationError(ValueError):
    pass


def _check_endpoint(provider: str, url: str, env) -> None:
    parsed = urlparse(url)
    if env.get("AGENT_MODEL_ALLOW_CUSTOM_ENDPOINT", "").lower() == "true":
        if parsed.scheme != "https":
            raise ConfigurationError(f"{provider} base URL must use https")
        return
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS[provider]:
        raise ConfigurationError(f"{provider} base URL must be https on {sorted(ALLOWED_HOSTS[provider])}; "
                                 "set AGENT_MODEL_ALLOW_CUSTOM_ENDPOINT=true to override deliberately")


def load_config(provider: str, env=None, model: str | None = None) -> ProviderConfig:
    """Read one provider's configuration. `model` overrides <PROVIDER>_MODEL (used by the evaluation harness)."""
    env = os.environ if env is None else env
    if provider not in PROVIDERS:
        raise ConfigurationError(f"unknown model provider {provider!r} (expected one of {', '.join(PROVIDERS)})")
    prefix = provider.upper()
    model = model or env.get(f"{prefix}_MODEL", "").strip() or ("claude-opus-5-5" if provider == "anthropic" else "")
    if not model:
        raise ConfigurationError(f"{prefix}_MODEL is required when the {provider} provider is used")
    base_url = env.get(f"{prefix}_BASE_URL", "").strip() or DEFAULT_ENDPOINTS[provider]
    _check_endpoint(provider, base_url, env)
    timeout = float(env.get(f"{prefix}_TIMEOUT_SECONDS", DEFAULT_TIMEOUTS[provider]))
    profile = profile_for(provider, model)
    if provider == "minimax":
        effort = env.get("MINIMAX_REASONING_EFFORT", "").strip().lower()
        if effort and profile.reasoning_effort is not None:
            if effort not in ("low", "medium", "high", "xhigh", "max"):
                raise ConfigurationError("MINIMAX_REASONING_EFFORT must be low, medium, high, xhigh or max")
            profile = replace(profile, reasoning_effort=effort)
        tier = env.get("MINIMAX_SERVICE_TIER", "").strip().lower()
        if tier and profile.service_tier is not None:
            if tier not in ("standard", "priority"):
                raise ConfigurationError("MINIMAX_SERVICE_TIER must be standard or priority")
            profile = replace(profile, service_tier=tier)
    if provider == "nebius" and (mode := env.get("NEBIUS_STRUCTURED_OUTPUT", "").strip().lower()):
        order = {"json_schema": ("json_schema", "json_object", "prompt"), "json_object": ("json_object", "prompt"),
                 "prompt": ("prompt",)}
        if mode not in order:
            raise ConfigurationError("NEBIUS_STRUCTURED_OUTPUT must be json_schema, json_object or prompt")
        profile = replace(profile, structured=order[mode])
    key = env.get(f"{prefix}_API_KEY") or None
    return ProviderConfig(provider, model, base_url, timeout, profile, key)


# --- Completions --------------------------------------------------------------------------------------------------

@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None

    def as_dict(self) -> dict:
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "reasoning_tokens": self.reasoning_tokens, "cached_tokens": self.cached_tokens}


@dataclass
class RawCompletion:
    provider: str
    model: str
    text: str
    usage: Usage
    latency_ms: int
    structured_mode: str
    finish_reason: str | None = None
    request_id: str | None = None
    attempts: list[dict] = field(default_factory=list)  # earlier structured modes the model rejected


class ProviderClient(Protocol):
    config: ProviderConfig

    def complete(self, system: str, user: str, schema: dict) -> RawCompletion: ...


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Remove <think>...</think> reasoning. An unterminated <think> block means the answer is missing."""
    cleaned = _THINK.sub("", text or "")
    if re.search(r"<think>", cleaned, re.IGNORECASE):
        raise ProviderError("the model's reasoning was cut off before an answer", "truncated")
    return cleaned.strip()


def _schema_prompt(user: str, schema: dict) -> str:
    return (user + "\n\nReturn only one JSON object matching this JSON Schema, with no other text:\n"
            + json.dumps(schema, sort_keys=True))


_UNAVAILABLE_HINTS = ("not found", "does not exist", "unknown model", "invalid model", "no such model", "not available")


def classify(exc: Exception, secrets: tuple[str, ...] = ()) -> tuple[str, str]:
    """Map an SDK exception to (kind, scrubbed message) by HTTP status and exception name, so the logic does not
    depend on one SDK's exception classes. Kinds: unavailable, rejected, timeout, configuration, error."""
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    message = scrub(f"{name}: {exc}", secrets)[:300]
    lowered = message.lower()
    if status == 404 or name == "NotFoundError":
        return "unavailable", message
    if status in (401, 403) or name in ("AuthenticationError", "PermissionDeniedError"):
        return "configuration", "authentication failed or access denied (check the API key and account)"
    if "timeout" in name.lower():
        return "timeout", message
    if status in (400, 422) or name in ("BadRequestError", "UnprocessableEntityError"):
        if "model" in lowered and any(hint in lowered for hint in _UNAVAILABLE_HINTS) and "response_format" not in lowered:
            return "unavailable", message
        return "rejected", message
    return "error", message


def _int(value) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


class OpenAICompatibleClient:
    """MiniMax and Nebius Token Factory, through the official OpenAI Python SDK both providers document."""

    def __init__(self, config: ProviderConfig, sdk_client=None):
        self.config = config
        self._client = sdk_client

    def _sdk(self):
        if self._client is None:
            if not self.config.api_key:
                raise ProviderError(f"{self.config.provider.upper()}_API_KEY is not set", "configuration")
            try:
                import openai
            except ImportError as exc:
                raise ProviderError('the openai package is not installed (pip install "./src/backend[model]")', "configuration") from exc
            logging.getLogger("openai").setLevel(logging.WARNING)  # never log request headers
            logging.getLogger("httpx").setLevel(logging.WARNING)
            self._client = openai.OpenAI(api_key=self.config.api_key, base_url=self.config.base_url,
                                         timeout=self.config.timeout, max_retries=1)
        return self._client

    def _request(self, mode: str, system: str, user: str, schema: dict) -> dict:
        profile = self.config.profile
        request = {"model": self.config.model, "max_completion_tokens": MAX_OUTPUT_TOKENS,
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": _schema_prompt(user, schema)}]}
        extra = {}
        if profile.reasoning_split:
            extra["reasoning_split"] = True
        if profile.reasoning_effort:
            request["reasoning_effort"] = profile.reasoning_effort
        if profile.service_tier and profile.service_tier != "standard":
            request["service_tier"] = profile.service_tier
        if mode == "json_schema":
            request["response_format"] = {"type": "json_schema",
                                          "json_schema": {"name": "recovery_decision", "schema": schema, "strict": True}}
        elif mode == "json_object":
            request["response_format"] = {"type": "json_object"}
        elif mode == "tool":
            request["tools"] = [{"type": "function", "function": {"name": "record_decision", "parameters": schema,
                                                                   "description": "Record the recovery decision"}}]
        if extra:
            request["extra_body"] = extra
        return request

    def complete(self, system: str, user: str, schema: dict) -> RawCompletion:
        client = self._sdk()
        secrets = (self.config.api_key or "",)
        attempts: list[dict] = []
        modes = self.config.profile.structured
        for index, mode in enumerate(modes):
            started = time.monotonic()
            try:
                response = client.chat.completions.create(**self._request(mode, system, user, schema))
            except Exception as exc:
                kind, message = classify(exc, secrets)
                if kind == "unavailable":
                    raise ModelUnavailable(f"model {self.config.model} not available: {message}") from exc
                if kind == "rejected" and mode != "prompt" and index < len(modes) - 1:
                    # Documented capability fallback: the same model, the next structured-output mode. Never another provider.
                    attempts.append({"mode": mode, "error": message})
                    log.info("%s/%s rejected %s; trying %s", self.config.provider, self.config.model, mode, modes[index + 1])
                    continue
                raise ProviderError(message, "error" if kind == "rejected" else kind) from exc
            return self._completion(response, mode, int((time.monotonic() - started) * 1000), attempts)
        raise ProviderError("no structured-output mode succeeded", "error")

    def _completion(self, response, mode: str, latency: int, attempts: list[dict]) -> RawCompletion:
        choice = response.choices[0]
        message = choice.message
        usage = getattr(response, "usage", None)
        details_in = getattr(usage, "prompt_tokens_details", None)
        details_out = getattr(usage, "completion_tokens_details", None)
        result = RawCompletion(
            provider=self.config.provider, model=getattr(response, "model", None) or self.config.model, text="",
            usage=Usage(_int(getattr(usage, "prompt_tokens", None)), _int(getattr(usage, "completion_tokens", None)),
                        _int(getattr(details_out, "reasoning_tokens", None)), _int(getattr(details_in, "cached_tokens", None))),
            latency_ms=latency, structured_mode=mode, finish_reason=choice.finish_reason,
            request_id=getattr(response, "id", None), attempts=attempts)
        if getattr(message, "refusal", None):
            raise ProviderError("the model refused", "refusal", result)
        if choice.finish_reason == "length":
            raise ProviderError("the answer was cut off at the token limit", "truncated", result)
        if mode == "tool" and getattr(message, "tool_calls", None):
            result.text = message.tool_calls[0].function.arguments or ""
        else:
            result.text = strip_reasoning(message.content or "")  # reasoning_content, if present, is ignored
        if not result.text:
            raise ProviderError("the model returned no answer text", "format", result)
        return result


class AnthropicClient:
    """Optional adapter, disabled unless AGENT_MODEL_PROVIDER=anthropic. Needs the [anthropic] extra."""

    def __init__(self, config: ProviderConfig, sdk_client=None):
        self.config = config
        self._client = sdk_client

    def _sdk(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise ProviderError('the anthropic package is not installed (pip install "./src/backend[anthropic]")', "configuration") from exc
            kwargs = {"timeout": self.config.timeout, "max_retries": 1}
            if self.config.api_key:
                kwargs["api_key"] = self.config.api_key
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def complete(self, system: str, user: str, schema: dict) -> RawCompletion:
        client = self._sdk()
        started = time.monotonic()
        try:
            response = client.messages.create(
                model=self.config.model, max_tokens=MAX_OUTPUT_TOKENS, system=system,
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": user}])
        except Exception as exc:  # network, auth, rate limit, timeout
            raise ProviderError(scrub(f"{type(exc).__name__}: {str(exc)[:200]}", (self.config.api_key or "",)), "error") from exc
        usage = getattr(response, "usage", None)
        result = RawCompletion(
            provider="anthropic", model=self.config.model, text="",
            usage=Usage(_int(getattr(usage, "input_tokens", None)), _int(getattr(usage, "output_tokens", None)), None,
                        _int(getattr(usage, "cache_read_input_tokens", None))),
            latency_ms=int((time.monotonic() - started) * 1000), structured_mode="json_schema",
            finish_reason=response.stop_reason, request_id=getattr(response, "id", None))
        if response.stop_reason == "refusal":
            raise ProviderError("the model refused", "refusal", result)
        if response.stop_reason == "max_tokens":
            raise ProviderError("the answer was cut off at the token limit", "truncated", result)
        result.text = next((block.text for block in response.content if block.type == "text"), "") or ""
        if not result.text:
            raise ProviderError("the model returned no answer text", "format", result)
        return result


def build_client(config: ProviderConfig, sdk_client=None) -> ProviderClient:
    if config.provider == "anthropic":
        return AnthropicClient(config, sdk_client)
    return OpenAICompatibleClient(config, sdk_client)


def list_models(config: ProviderConfig) -> list[str]:
    """Model ids offered to this account (GET /models), for availability checks. Raises ProviderError."""
    client = OpenAICompatibleClient(config)._sdk()
    try:
        return sorted(model.id for model in client.models.list())
    except Exception as exc:
        raise ProviderError(scrub(f"could not list models: {type(exc).__name__}: {exc}", (config.api_key or "",))[:300]) from exc

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .extraction import Compensation, Evidence


class CitedFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str | int
    quote: str = Field(min_length=1)
    confidence: Literal["high", "medium", "low"]


class CitedCompensation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minimum: int | None = Field(default=None, ge=0)
    maximum: int | None = Field(default=None, ge=0)
    currency: Literal["USD", "CAD"]
    period: Literal["year", "hour"]
    quote: str = Field(min_length=1)
    confidence: Literal["high", "medium", "low"]


class FallbackPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experience_min: CitedFact | None = None
    workplace: CitedFact | None = None
    compensation: CitedCompensation | None = None
    benefits: list[CitedFact] = Field(default_factory=list)


@dataclass(frozen=True)
class FallbackResult:
    experience_min: Evidence | None = None
    workplace: Evidence | None = None
    compensation: Compensation | None = None
    benefits: tuple[Evidence, ...] = ()


class ExtractionFallback(Protocol):
    def extract(self, text: str, missing_fields: set[str]) -> FallbackResult: ...


def _validated_result(payload: dict, source_text: str) -> FallbackResult:
    """Reject uncited model output and normalize accepted fields to local evidence objects."""
    parsed = FallbackPayload.model_validate(payload)

    def evidence(fact: CitedFact | None) -> Evidence | None:
        if not fact or fact.quote not in source_text:
            return None
        return Evidence(
            value=str(fact.value),
            quote=fact.quote,
            method="llm_fallback",
            confidence=fact.confidence,
        )

    comp = parsed.compensation
    accepted_comp = None
    if comp and comp.quote in source_text:
        accepted_comp = Compensation(
            minimum=comp.minimum,
            maximum=comp.maximum,
            currency=comp.currency,
            period=comp.period,
            evidence=Evidence(
                value=comp.quote,
                quote=comp.quote,
                method="llm_fallback",
                confidence=comp.confidence,
            ),
        )
    accepted_benefits = tuple(
        item for fact in parsed.benefits if (item := evidence(fact)) is not None
    )
    return FallbackResult(
        experience_min=evidence(parsed.experience_min),
        workplace=evidence(parsed.workplace),
        compensation=accepted_comp,
        benefits=accepted_benefits,
    )


class ChatCompletionsFallback:
    """Small adapter for APIs that support the OpenAI-compatible chat-completions shape."""

    def __init__(self, endpoint: str, model: str, api_key: str, timeout: float = 45):
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def extract(self, text: str, missing_fields: set[str]) -> FallbackResult:
        schema = FallbackPayload.model_json_schema()
        prompt = (
            "Extract only the requested missing job fields. Every fact must include an exact, "
            "verbatim quote from the supplied posting. Use null or [] when unsupported. "
            f"Requested fields: {sorted(missing_fields)}\n\nPosting:\n{text}"
        )
        response = httpx.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "job_facts", "strict": True, "schema": schema},
                },
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return _validated_result(FallbackPayload.model_validate_json(content).model_dump(), text)


def fallback_from_config(settings: dict) -> ExtractionFallback | None:
    """Remain fully local unless the user explicitly enables and configures transmission."""
    config = settings.get("llm_fallback", {})
    if not config.get("enabled", False):
        return None
    endpoint = config.get("endpoint")
    model = config.get("model")
    key_env = config.get("api_key_env")
    api_key = os.getenv(key_env, "") if key_env else ""
    if not endpoint or not model or not api_key:
        raise ValueError(
            "LLM fallback is enabled but endpoint, model, or the configured API-key environment "
            "variable is missing"
        )
    return ChatCompletionsFallback(endpoint, model, api_key)


__all__ = [
    "ChatCompletionsFallback",
    "ExtractionFallback",
    "FallbackResult",
    "ValidationError",
    "_validated_result",
    "fallback_from_config",
]

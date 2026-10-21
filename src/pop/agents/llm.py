"""Language-model interface. Offline stub for tests; Microsoft Foundry in the cloud.

The model is only ever asked to phrase facts it is handed. It never computes a number, and any
failure (timeout, rate limit, refusal, empty reply) returns "" so the Explainer publishes the grounded
draft instead. A model problem can slow the words down; it can never stop the broadcast.

POP_LLM selects the backend:
  stub     deterministic, offline (default)
  foundry  an OpenAI-format deployment on Microsoft Foundry (e.g. gpt-5-mini), Entra ID auth
  claude   a Claude deployment on Microsoft Foundry (e.g. claude-sonnet-5-5), Entra ID auth, prompt caching
"""

from __future__ import annotations

import json
import logging
import os
import random
import threading
from dataclasses import dataclass, field
from typing import Protocol

log = logging.getLogger("pop.llm")
_SCOPE = "https://cognitiveservices.azure.com/.default"


class LLM(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


@dataclass
class Usage:
    """Token accounting for the producer console's cost meter."""

    calls: int = 0
    failures: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, inp: int = 0, out: int = 0, cached: int = 0, failed: bool = False) -> None:
        with self.lock:
            self.calls += 1
            self.failures += failed
            self.input_tokens += inp
            self.output_tokens += out
            self.cached_input_tokens += cached

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("calls", "failures", "input_tokens", "output_tokens",
                                                "cached_input_tokens")}


class StubLLM:
    """Returns the 'draft' field of the JSON payload it is given. Deterministic."""

    name = "stub"

    def __init__(self) -> None:
        self.usage = Usage()

    def complete(self, system: str, user: str) -> str:
        self.usage.add()
        try:
            return json.loads(user).get("draft", "")
        except json.JSONDecodeError:
            return user


class FoundryLLM:
    """OpenAI-format model on Microsoft Foundry (gpt-5-mini by default)."""

    def __init__(self) -> None:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import AzureOpenAI

        self.deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT", "gpt-5-mini")
        self.name = f"foundry:{self.deployment}"
        self.reasoning = self.deployment.startswith(("gpt-5", "o"))
        self.client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], api_version="2025-04-01-preview",
            azure_ad_token_provider=get_bearer_token_provider(DefaultAzureCredential(), _SCOPE),
            timeout=20.0, max_retries=2,
        )
        self.usage = Usage()

    def complete(self, system: str, user: str) -> str:
        try:
            kw: dict = {"model": self.deployment,
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            if self.reasoning:  # reasoning models: no temperature; keep thinking short for live use
                kw.update(max_completion_tokens=1200, reasoning_effort="minimal")
            else:
                kw.update(max_tokens=180, temperature=0.3)
            r = self.client.chat.completions.create(**kw)
            u = r.usage
            cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
            self.usage.add(u.prompt_tokens, u.completion_tokens, cached)
            return (r.choices[0].message.content or "").strip()
        except Exception as e:  # noqa: BLE001 - any model failure falls back to the grounded draft
            log.warning("foundry call failed: %s", type(e).__name__)
            self.usage.add(failed=True)
            return ""


class ClaudeFoundryLLM:
    """Claude on Microsoft Foundry via the Anthropic SDK's Foundry client, Entra ID auth, no keys.

    The style guide (system prompt) is identical on every call and carries a cache breakpoint, so after the
    first call each request pays the cache-read rate for it. Sonnet 5.5's minimum cacheable prefix is 512
    tokens; the style guide is well above that. Thinking stays on (Sonnet 5.5 rejects "disabled") at low
    effort to keep live latency down. A refusal or any error returns "" and the grounded draft is published.
    """

    def __init__(self) -> None:
        from anthropic import AnthropicFoundry
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        self.deployment = os.environ.get("POP_CLAUDE_DEPLOYMENT", "claude-sonnet-5-5")
        self.name = f"foundry:{self.deployment}"
        self.client = AnthropicFoundry(
            resource=os.environ["POP_CLAUDE_RESOURCE"],
            azure_ad_token_provider=get_bearer_token_provider(DefaultAzureCredential(), _SCOPE),
            timeout=30.0, max_retries=2,
        )
        self.usage = Usage()

    def complete(self, system: str, user: str) -> str:
        try:
            r = self.client.messages.create(
                model=self.deployment,
                max_tokens=2000,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": user}],
            )
            u = r.usage
            self.usage.add(u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0),
                           u.output_tokens, u.cache_read_input_tokens or 0)
            if r.stop_reason == "refusal":
                return ""
            return "".join(b.text for b in r.content if b.type == "text").strip()
        except Exception as e:  # noqa: BLE001 - any model failure falls back to the grounded draft
            log.warning("claude call failed: %s", type(e).__name__)
            self.usage.add(failed=True)
            return ""


class ChaosLLM:
    """Demo only: makes the wrapped model invent a statistic on a set share of rewrites.

    Lets the producer console show the Verifier catching a hallucination live. Never on by default.
    """

    INVENTIONS = ("his 3rd of the season", "the 7th time this month", "at 41 km/h", "a 92% success rate")

    def __init__(self, inner: LLM, rate: float, seed: int = 0) -> None:
        self.inner, self.rate, self.rng = inner, rate, random.Random(seed)
        self.name = f"{inner.name}+chaos"
        self.usage = getattr(inner, "usage", Usage())

    def complete(self, system: str, user: str) -> str:
        text = self.inner.complete(system, user)
        if text and self.rng.random() < self.rate:
            return text.rstrip(".") + ", " + self.rng.choice(self.INVENTIONS) + "."
        return text


def get_llm() -> LLM:
    which = os.environ.get("POP_LLM", "stub")
    base: LLM = {"foundry": FoundryLLM, "claude": ClaudeFoundryLLM}.get(which, StubLLM)()
    rate = float(os.environ.get("POP_DEMO_CHAOS", "0") or 0)
    return ChaosLLM(base, rate) if rate > 0 else base

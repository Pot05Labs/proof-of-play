"""Language-model interface. Offline stub for tests and demos; Microsoft Foundry in the cloud.

The model is only ever asked to phrase facts it is handed. It never computes a number.
"""

from __future__ import annotations

import json
import os
from typing import Protocol


class LLM(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


class StubLLM:
    """Returns the 'draft' field of the JSON payload it is given. Deterministic."""

    name = "stub"

    def complete(self, system: str, user: str) -> str:
        try:
            return json.loads(user).get("draft", "")
        except json.JSONDecodeError:
            return user


class FoundryLLM:
    """Chat completions against a Microsoft Foundry model deployment (OpenAI-compatible endpoint).

    Requires AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT, authenticated with
    DefaultAzureCredential. Imported lazily so offline tests never need the Azure SDK.
    """

    name = "foundry"

    def __init__(self) -> None:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import AzureOpenAI

        endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
        self.deployment = os.environ["AZURE_AI_MODEL_DEPLOYMENT"]
        token = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")
        self.client = AzureOpenAI(azure_endpoint=endpoint, azure_ad_token_provider=token, api_version="2024-10-21")

    def complete(self, system: str, user: str) -> str:
        r = self.client.chat.completions.create(
            model=self.deployment, temperature=0.3, max_tokens=180,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return (r.choices[0].message.content or "").strip()


def get_llm() -> LLM:
    return FoundryLLM() if os.environ.get("POP_LLM") == "foundry" else StubLLM()

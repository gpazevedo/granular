"""LLM abstraction layer supporting OpenAI, Anthropic (Claude), and AWS Bedrock (Nova).

Provides a unified interface for concept extraction and embeddings,
automatically detecting provider from model ID or environment variables.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    def chat_completion(
        self,
        system: str,
        user_message: str,
        model: str,
        temperature: float = 0.0,
        response_format: Optional[dict] = None,
    ) -> str:
        """Send a chat message and return the response text."""
        pass

    @abstractmethod
    def embedding(self, text: str, model: str) -> list[float]:
        """Embed text and return the vector."""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI API provider (GPT models)."""

    def __init__(self) -> None:
        try:
            from openai import OpenAI
            self._client = OpenAI()
        except ImportError:
            raise ImportError("openai package required: pip install openai")

    def chat_completion(
        self,
        system: str,
        user_message: str,
        model: str,
        temperature: float = 0.0,
        response_format: Optional[dict] = None,
    ) -> str:
        response = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            response_format=response_format or {"type": "json_object"},
        )
        return response.choices[0].message.content or ""

    def embedding(self, text: str, model: str) -> list[float]:
        response = self._client.embeddings.create(input=text, model=model)
        return response.data[0].embedding


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""

    def __init__(self) -> None:
        try:
            import anthropic
            self._client = anthropic.Anthropic()
        except ImportError:
            raise ImportError("anthropic package required: pip install anthropic")

    def chat_completion(
        self,
        system: str,
        user_message: str,
        model: str,
        temperature: float = 0.0,
        response_format: Optional[dict] = None,
    ) -> str:
        # Anthropic doesn't natively support JSON response format like OpenAI,
        # so we instruct it via system prompt
        system_with_json = (
            system
            + "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown code blocks, no extra text."
        )
        response = self._client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_with_json,
            messages=[
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
        )
        return response.content[0].text if response.content else ""

    def embedding(self, text: str, model: str) -> list[float]:
        # Anthropic does not provide an embedding API. Use a placeholder or fallback.
        # For production, you'd integrate with a separate embedding service (e.g., Voyage AI).
        raise NotImplementedError(
            "Anthropic does not provide embeddings. Use OpenAI for embeddings "
            "or configure a separate embedding service."
        )


class BedrockProvider(LLMProvider):
    """AWS Bedrock provider (Nova, Claude, etc.)."""

    def __init__(self) -> None:
        try:
            import boto3
            self._client = boto3.client("bedrock-runtime")
        except ImportError:
            raise ImportError("boto3 package required: pip install boto3")

    def chat_completion(
        self,
        system: str,
        user_message: str,
        model: str,
        temperature: float = 0.0,
        response_format: Optional[dict] = None,
    ) -> str:
        # Bedrock uses the same Message format as Anthropic
        # For Nova (which is Anthropic-compatible) or Claude models via Bedrock
        system_with_json = (
            system
            + "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown code blocks, no extra text."
        )
        response = self._client.converse(
            modelId=model,
            messages=[
                {"role": "user", "content": [{"text": user_message}]},
            ],
            system=[{"text": system_with_json}],
            inferenceConfig={
                "temperature": temperature,
                "maxTokens": 2048,
            },
        )
        # Extract text from response
        if response.get("output", {}).get("message", {}).get("content"):
            content = response["output"]["message"]["content"]
            if content and isinstance(content, list) and len(content) > 0:
                if "text" in content[0]:
                    return content[0]["text"]
        return ""

    def embedding(self, text: str, model: str) -> list[float]:
        # Bedrock embeddings via Titan Embeddings or other embedding models
        # For now, raise NotImplementedError. Can be added if needed.
        raise NotImplementedError(
            "Bedrock embeddings not yet implemented. Use OpenAI for embeddings."
        )


def get_provider(model_id: str) -> LLMProvider:
    """Detect provider from model ID or environment and return provider instance.

    Model ID format: "provider/model-name"
    Examples:
      - "openai/gpt-4o-mini"
      - "anthropic/claude-3-5-haiku-20241022"
      - "bedrock/us.amazon.nova-lite-v1:0"
      - "bedrock/us.anthropic.claude-3-haiku-20250301-v1:0"
      - "gpt-4o-mini" (defaults to OpenAI)
      - "claude-3-5-haiku-20241022" (defaults to Anthropic)
    """
    if "/" in model_id:
        provider_name, _ = model_id.split("/", 1)
    else:
        # Auto-detect from model name
        if "claude" in model_id.lower():
            provider_name = "anthropic"
        elif "nova" in model_id.lower():
            provider_name = "bedrock"
        elif "gpt" in model_id.lower():
            provider_name = "openai"
        else:
            provider_name = "openai"  # default

    if provider_name.lower() == "anthropic":
        return AnthropicProvider()
    elif provider_name.lower() == "openai":
        return OpenAIProvider()
    elif provider_name.lower() == "bedrock":
        return BedrockProvider()
    else:
        raise ValueError(f"Unknown LLM provider: {provider_name}")


def get_model_name(model_id: str) -> str:
    """Extract the actual model name from a model_id string.

    Examples:
      - "openai/gpt-4o-mini" -> "gpt-4o-mini"
      - "anthropic/claude-3-5-haiku-20241022" -> "claude-3-5-haiku-20241022"
      - "gpt-4o-mini" -> "gpt-4o-mini"
    """
    return model_id.split("/")[-1]

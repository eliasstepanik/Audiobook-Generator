"""Unified LLM client supporting Ollama, OpenAI, and Anthropic backends."""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass
class ProcessingResult:
    """Result from LLM text processing."""

    original_text: str
    processed_text: str
    batch_index: int
    metadata: Optional[Dict[str, Any]] = None


DEFAULT_SYSTEM_PROMPT = """You are an expert text processor for audiobook generation.

CRITICAL RULES:
- Return the COMPLETE text with ALL sentences preserved
- DO NOT summarize, shorten, or remove ANY content
- DO NOT add explanations, comments, or metadata
- The output must be approximately the SAME LENGTH as the input

Your task:
1. Fix obvious typos and formatting issues
2. Expand abbreviations (e.g. "Dr." -> "Doctor", "Mr." -> "Mister")
3. Convert numbers to words (e.g. "3" -> "three")
4. Add appropriate punctuation for natural speech pauses
5. Preserve the author's voice, style, and ALL content exactly

Return ONLY the processed text. Nothing else."""


class LLMClient:
    """
    Unified LLM client supporting multiple providers.

    Supports:
    - Ollama (local, OpenAI-compatible API)
    - OpenAI (ChatGPT, GPT-4, etc.)
    - Anthropic (Claude)

    All providers expose the same interface via process_text().
    """

    def __init__(
        self,
        provider: str = "ollama",
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        system_prompt: Optional[str] = None,
        timeout: int = 600,
    ):
        """
        Initialize LLM client.

        Args:
            provider: "ollama", "openai", or "anthropic"
            model: Model name (provider-specific defaults if None)
            base_url: API base URL (provider-specific defaults if None)
            api_key: API key (required for openai/anthropic)
            system_prompt: Custom system prompt
            timeout: Request timeout in seconds
        """
        self.provider = LLMProvider(provider.lower())
        self.timeout = timeout
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.api_key = api_key

        # Set provider-specific defaults
        if self.provider == LLMProvider.OLLAMA:
            self.model = model or "gpt-oss:20b"
            self.base_url = (base_url or "http://192.168.178.166:11434/v1").rstrip("/")
        elif self.provider == LLMProvider.OPENAI:
            self.model = model or "gpt-4o"
            self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
            if not api_key:
                import os

                self.api_key = os.getenv("OPENAI_API_KEY")
                if not self.api_key:
                    raise ValueError(
                        "OpenAI API key required. Set api_key or OPENAI_API_KEY env var."
                    )
        elif self.provider == LLMProvider.ANTHROPIC:
            self.model = model or "claude-sonnet-4-20250514"
            self.base_url = (base_url or "https://api.anthropic.com").rstrip("/")
            if not api_key:
                import os

                self.api_key = os.getenv("ANTHROPIC_API_KEY")
                if not self.api_key:
                    raise ValueError(
                        "Anthropic API key required. Set api_key or ANTHROPIC_API_KEY env var."
                    )

        logger.info(
            f"Initialized LLMClient: provider={self.provider.value}, model={self.model}"
        )

        # Verify connection (non-blocking)
        self._verify_connection()

    def _verify_connection(self) -> None:
        """Verify that the API endpoint is accessible."""
        import requests

        try:
            if self.provider == LLMProvider.OLLAMA:
                response = requests.get(
                    f"{self.base_url}/models", timeout=10, verify=False
                )
                if response.status_code == 200:
                    logger.info(f"Connected to Ollama at {self.base_url}")
                else:
                    logger.warning(
                        f"Ollama responded with status {response.status_code}"
                    )
            elif self.provider == LLMProvider.OPENAI:
                response = requests.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10,
                )
                if response.status_code == 200:
                    logger.info("Connected to OpenAI API")
                else:
                    logger.warning(
                        f"OpenAI API responded with status {response.status_code}"
                    )
            elif self.provider == LLMProvider.ANTHROPIC:
                # Anthropic doesn't have a simple health check, just log
                logger.info("Anthropic API configured (will verify on first request)")
        except Exception as e:
            logger.warning(f"Could not verify API connection: {e}")
            logger.warning("Will attempt to proceed anyway")

    def process_text(
        self,
        text: str,
        batch_index: int = 0,
        custom_prompt: Optional[str] = None,
        temperature: float = 0.3,
        **kwargs,
    ) -> ProcessingResult:
        """
        Process text through the configured LLM provider.

        Args:
            text: Text to process
            batch_index: Index of the batch
            custom_prompt: Override system prompt for this request
            temperature: Model temperature
            **kwargs: Additional arguments (e.g. max_tokens)

        Returns:
            ProcessingResult with processed text
        """
        logger.info(
            f"Processing batch {batch_index} ({len(text)} chars) via {self.provider.value}"
        )

        if self.provider == LLMProvider.ANTHROPIC:
            return self._process_anthropic(
                text, batch_index, custom_prompt, temperature, **kwargs
            )
        else:
            # Both Ollama and OpenAI use OpenAI-compatible API
            return self._process_openai_compatible(
                text, batch_index, custom_prompt, temperature, **kwargs
            )

    def _process_openai_compatible(
        self,
        text: str,
        batch_index: int,
        custom_prompt: Optional[str],
        temperature: float,
        **kwargs,
    ) -> ProcessingResult:
        """Process text via OpenAI-compatible API (works for Ollama and OpenAI)."""
        import requests

        system_prompt = custom_prompt or self.system_prompt

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": temperature,
        }

        # Add max_tokens if provided
        if "max_tokens" in kwargs:
            payload["max_tokens"] = kwargs["max_tokens"]

        headers = {"Content-Type": "application/json"}
        if self.api_key and self.provider == LLMProvider.OPENAI:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            # Only disable SSL verification for local/private network URLs
            is_local = any(
                x in self.base_url
                for x in ["localhost", "127.0.0.1", "192.168.", "10.", "172.16."]
            )
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self.timeout,
                verify=not is_local,
            )

            if response.status_code != 200:
                logger.error(f"LLM error (status {response.status_code})")
                logger.error(f"Response: {response.text[:500]}")

            response.raise_for_status()

            result = response.json()
            processed_text = result["choices"][0]["message"]["content"].strip()

            metadata = {
                "provider": self.provider.value,
                "model": result.get("model"),
                "usage": result.get("usage"),
                "finish_reason": result["choices"][0].get("finish_reason"),
            }

            logger.info(
                f"Batch {batch_index} processed: {len(text)} -> {len(processed_text)} chars"
            )

            return ProcessingResult(
                original_text=text,
                processed_text=processed_text,
                batch_index=batch_index,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Error processing batch {batch_index}: {e}")
            raise

    def _process_anthropic(
        self,
        text: str,
        batch_index: int,
        custom_prompt: Optional[str],
        temperature: float,
        **kwargs,
    ) -> ProcessingResult:
        """Process text via Anthropic Messages API."""
        import requests

        system_prompt = custom_prompt or self.system_prompt

        payload = {
            "model": self.model,
            "max_tokens": kwargs.get("max_tokens", 8192),
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": text},
            ],
            "temperature": temperature,
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )

            if response.status_code != 200:
                logger.error(f"Anthropic error (status {response.status_code})")
                logger.error(f"Response: {response.text[:500]}")

            response.raise_for_status()

            result = response.json()

            # Anthropic returns content as a list of blocks
            content_blocks = result.get("content", [])
            processed_text = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    processed_text += block.get("text", "")
            processed_text = processed_text.strip()

            metadata = {
                "provider": self.provider.value,
                "model": result.get("model"),
                "usage": result.get("usage"),
                "stop_reason": result.get("stop_reason"),
            }

            logger.info(
                f"Batch {batch_index} processed: {len(text)} -> {len(processed_text)} chars"
            )

            return ProcessingResult(
                original_text=text,
                processed_text=processed_text,
                batch_index=batch_index,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Error processing batch {batch_index}: {e}")
            raise

    def process_batches(
        self, texts: List[str], temperature: float = 0.3, **kwargs
    ) -> List[ProcessingResult]:
        """Process multiple text batches sequentially."""
        results = []
        for idx, text in enumerate(texts):
            result = self.process_text(
                text=text, batch_index=idx, temperature=temperature, **kwargs
            )
            results.append(result)
        return results

    def health_check(self) -> bool:
        """Check if LLM service is accessible."""
        import requests

        try:
            if self.provider == LLMProvider.OLLAMA:
                response = requests.get(
                    f"{self.base_url}/models", timeout=10, verify=False
                )
                return response.status_code == 200
            elif self.provider == LLMProvider.OPENAI:
                response = requests.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10,
                )
                return response.status_code == 200
            elif self.provider == LLMProvider.ANTHROPIC:
                # Simple test request
                result = self.process_text("Say 'ok'", temperature=0, max_tokens=10)
                return bool(result.processed_text)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False


# Backward compatibility alias
OllamaClient = LLMClient

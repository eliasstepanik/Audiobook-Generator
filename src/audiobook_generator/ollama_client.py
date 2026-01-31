"""Ollama client for processing text batches with gpt-oss:20b."""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import logging
import requests

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result from Ollama text processing."""

    original_text: str
    processed_text: str
    batch_index: int
    metadata: Optional[Dict[str, Any]] = None


class OllamaClient:
    """Client for interacting with Ollama gpt-oss:20b model via OpenAI-compatible API."""

    def __init__(
        self,
        model: str = "gpt-oss:20b",
        base_url: str = "http://192.168.178.166:11434/v1",
        system_prompt: Optional[str] = None,
        timeout: int = 600,
    ):
        """
        Initialize Ollama client.

        Args:
            model: Model name (default: gpt-oss-16k:120b)
            base_url: Base URL for OpenAI-compatible API
            system_prompt: Custom system prompt for processing
            timeout: Request timeout in seconds
        """
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.chat_url = f"{self.base_url}/chat/completions"

        self.system_prompt = system_prompt or self._default_system_prompt()

        logger.info(f"Initialized OllamaClient: {self.chat_url}")

        # Verify connection
        self._verify_connection()

    def _default_system_prompt(self) -> str:
        """Default system prompt for audiobook processing."""
        return """You are an expert text processor for audiobook generation.

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

    def _verify_connection(self) -> None:
        """Verify that the API endpoint is accessible."""
        try:
            response = requests.get(f"{self.base_url}/models", timeout=10, verify=False)
            if response.status_code == 200:
                logger.info("Successfully connected to Ollama API")
            else:
                logger.warning(f"API responded with status {response.status_code}")
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
        Process text through Ollama model.

        Args:
            text: Text to process
            batch_index: Index of the batch
            custom_prompt: Override system prompt for this request
            temperature: Model temperature (lower = more deterministic)
            **kwargs: Additional arguments to pass to ollama.generate

        Returns:
            ProcessingResult with processed text

        Raises:
            Exception: If processing fails
        """
        try:
            logger.info(f"Processing batch {batch_index} ({len(text)} chars)")

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": custom_prompt or self.system_prompt},
                    {"role": "user", "content": text},
                ],
                "temperature": temperature,
                **kwargs,
            }

            response = requests.post(
                self.chat_url, json=payload, timeout=self.timeout, verify=False
            )

            # Log error details before raising
            if response.status_code != 200:
                logger.error(f"Ollama server error (status {response.status_code})")
                logger.error(f"Response: {response.text[:500]}")

            response.raise_for_status()

            result = response.json()
            processed_text = result["choices"][0]["message"]["content"].strip()

            # Extract metadata if available
            metadata = {
                "model": result.get("model"),
                "usage": result.get("usage"),
                "finish_reason": result["choices"][0].get("finish_reason"),
            }

            logger.info(
                f"Batch {batch_index} processed: "
                f"{len(text)} -> {len(processed_text)} chars"
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
        """
        Process multiple text batches.

        Args:
            texts: List of text strings to process
            temperature: Model temperature
            **kwargs: Additional arguments to pass to ollama.generate

        Returns:
            List of ProcessingResult objects
        """
        results = []

        for idx, text in enumerate(texts):
            result = self.process_text(
                text=text, batch_index=idx, temperature=temperature, **kwargs
            )
            results.append(result)

        return results

    def health_check(self) -> bool:
        """
        Check if Ollama service is accessible.

        Returns:
            True if service is healthy
        """
        try:
            response = requests.get(f"{self.base_url}/models", timeout=10, verify=False)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

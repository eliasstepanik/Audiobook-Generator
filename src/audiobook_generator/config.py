"""Configuration management for audiobook generator."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import os


@dataclass
class OllamaConfig:
    """Configuration for Ollama service."""

    model: str = "gpt-oss-16k:120b"
    base_url: str = "http://192.168.178.166:11434/v1"
    temperature: float = 0.3
    timeout: int = 300

    @classmethod
    def from_env(cls) -> "OllamaConfig":
        """Create config from environment variables."""
        return cls(
            model=os.getenv("OLLAMA_MODEL", "gpt-oss-16k:120b"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://192.168.178.166:11434/v1"),
            temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.3")),
            timeout=int(os.getenv("OLLAMA_TIMEOUT", "300")),
        )


@dataclass
class VoiceDesignConfig:
    """Configuration for voice design."""

    design_text: str = "Hello, welcome to this audiobook. I hope you enjoy the story."
    design_instruct: str = (
        "Male, 30 years old, clear and warm narrator voice, "
        "professional tone, natural pacing"
    )
    language: str = "English"

    @classmethod
    def from_env(cls) -> "VoiceDesignConfig":
        """Create config from environment variables."""
        return cls(
            design_text=os.getenv(
                "VOICE_DESIGN_TEXT",
                "Hello, welcome to this audiobook. I hope you enjoy the story.",
            ),
            design_instruct=os.getenv(
                "VOICE_DESIGN_INSTRUCT",
                "Male, 30 years old, clear and warm narrator voice, professional tone",
            ),
            language=os.getenv("VOICE_LANGUAGE", "English"),
        )


@dataclass
class TTSConfig:
    """Configuration for TTS synthesis."""

    device: str = "cuda:0"
    dtype: str = "bfloat16"
    use_flash_attention: bool = True
    batch_size: int = 5

    @classmethod
    def from_env(cls) -> "TTSConfig":
        """Create config from environment variables."""
        return cls(
            device=os.getenv("TTS_DEVICE", "cuda:0"),
            dtype=os.getenv("TTS_DTYPE", "bfloat16"),
            use_flash_attention=os.getenv("TTS_FLASH_ATTENTION", "true").lower()
            == "true",
            batch_size=int(os.getenv("TTS_BATCH_SIZE", "5")),
        )


@dataclass
class ProcessingConfig:
    """Configuration for text processing."""

    max_chars_per_batch: int = 16000
    enable_ollama_processing: bool = True
    save_intermediate: bool = False

    @classmethod
    def from_env(cls) -> "ProcessingConfig":
        """Create config from environment variables."""
        return cls(
            max_chars_per_batch=int(os.getenv("MAX_CHARS_PER_BATCH", "16000")),
            enable_ollama_processing=os.getenv("ENABLE_OLLAMA", "true").lower()
            == "true",
            save_intermediate=os.getenv("SAVE_INTERMEDIATE", "false").lower() == "true",
        )


@dataclass
class AudiobookConfig:
    """Complete configuration for audiobook generation."""

    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    voice_design: VoiceDesignConfig = field(default_factory=VoiceDesignConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)

    @classmethod
    def from_env(cls) -> "AudiobookConfig":
        """Create complete config from environment variables."""
        return cls(
            ollama=OllamaConfig.from_env(),
            voice_design=VoiceDesignConfig.from_env(),
            tts=TTSConfig.from_env(),
            processing=ProcessingConfig.from_env(),
        )

    @classmethod
    def default(cls) -> "AudiobookConfig":
        """Create default configuration."""
        return cls()


def load_config(env_file: Optional[str] = None) -> AudiobookConfig:
    """
    Load configuration from environment or .env file.

    Args:
        env_file: Optional path to .env file

    Returns:
        AudiobookConfig instance
    """
    if env_file:
        from dotenv import load_dotenv

        load_dotenv(env_file)

    return AudiobookConfig.from_env()

"""Configuration management for audiobook generator.

Loads settings from (in order of priority):
1. config.yml file (if present)
2. Environment variables
3. Defaults
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List
import os
import logging

logger = logging.getLogger(__name__)

# Try to import yaml, fall back gracefully
try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    logger.info("PyYAML not installed - config.yml support disabled")


def _load_yaml_config(config_path: Optional[Path] = None) -> dict:
    """Load configuration from YAML file."""
    if not YAML_AVAILABLE:
        return {}

    if config_path is None:
        # Look for config.yml in project root
        config_path = Path(__file__).parent.parent.parent / "config.yml"

    if not config_path.exists():
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            logger.info(f"Loaded configuration from {config_path}")
            return data
    except Exception as e:
        logger.error(f"Failed to load {config_path}: {e}")
        return {}


# Load YAML once at module level
_yaml_config = _load_yaml_config()


def _get(yaml_section: str, yaml_key: str, env_var: str, default, cast=None):
    """Get config value from YAML -> env -> default."""
    # 1. Try YAML
    section = _yaml_config.get(yaml_section, {})
    if isinstance(section, dict) and yaml_key in section:
        val = section[yaml_key]
        if val is not None:
            return cast(val) if cast else val

    # 2. Try environment variable
    env_val = os.getenv(env_var)
    if env_val is not None:
        if cast == bool:
            return env_val.lower() in ("true", "1", "yes")
        return cast(env_val) if cast else env_val

    # 3. Default
    return default


@dataclass
class AppConfig:
    """Application server configuration."""

    host: str = field(
        default_factory=lambda: _get("app", "host", "APP_HOST", "0.0.0.0")
    )
    port: int = field(
        default_factory=lambda: _get("app", "port", "APP_PORT", 8000, int)
    )
    debug: bool = field(
        default_factory=lambda: _get("app", "debug", "APP_DEBUG", False, bool)
    )
    title: str = field(
        default_factory=lambda: _get("app", "title", "APP_TITLE", "Audiobook Generator")
    )


@dataclass
class LLMConfig:
    """Configuration for LLM service (Ollama, OpenAI, or Anthropic)."""

    provider: str = field(
        default_factory=lambda: _get("llm", "provider", "LLM_PROVIDER", "ollama")
    )
    model: str = field(
        default_factory=lambda: _get("llm", "model", "LLM_MODEL", "gpt-oss:20b")
    )
    base_url: str = field(
        default_factory=lambda: _get(
            "llm", "base_url", "LLM_BASE_URL", "http://localhost:11434/v1"
        )
    )
    api_key: Optional[str] = field(
        default_factory=lambda: _get("llm", "api_key", "LLM_API_KEY", None)
    )
    temperature: float = field(
        default_factory=lambda: _get(
            "llm", "temperature", "LLM_TEMPERATURE", 0.3, float
        )
    )
    timeout: int = field(
        default_factory=lambda: _get("llm", "timeout", "LLM_TIMEOUT", 600, int)
    )
    max_tokens: int = field(
        default_factory=lambda: _get("llm", "max_tokens", "LLM_MAX_TOKENS", 2000, int)
    )


# Backward compatibility
OllamaConfig = LLMConfig


@dataclass
class VoiceDesignConfig:
    """Configuration for voice design."""

    design_text: str = field(
        default_factory=lambda: _get(
            "tts",
            "voice_design_text",
            "VOICE_DESIGN_TEXT",
            "Hello, welcome to this audiobook. I hope you enjoy the story.",
        )
    )
    design_instruct: str = field(
        default_factory=lambda: _get(
            "tts",
            "voice_design_instruct",
            "VOICE_DESIGN_INSTRUCT",
            "Male, 30 years old, clear and warm narrator voice, professional tone, natural pacing",
        )
    )
    language: str = field(
        default_factory=lambda: _get(
            "tts", "default_language", "VOICE_LANGUAGE", "English"
        )
    )


@dataclass
class TTSConfig:
    """Configuration for TTS synthesis."""

    device: Optional[str] = field(
        default_factory=lambda: _get("tts", "device", "TTS_DEVICE", None)
    )
    dtype: str = field(
        default_factory=lambda: _get("tts", "dtype", "TTS_DTYPE", "bfloat16")
    )
    use_flash_attention: Optional[bool] = field(
        default_factory=lambda: _get(
            "tts", "use_flash_attention", "TTS_FLASH_ATTENTION", None
        )
    )
    batch_size: int = field(
        default_factory=lambda: _get("tts", "batch_size", "TTS_BATCH_SIZE", 5, int)
    )


@dataclass
class ProcessingConfig:
    """Configuration for text processing."""

    max_chars_per_batch: int = field(
        default_factory=lambda: _get(
            "text_processing", "batch_size", "MAX_CHARS_PER_BATCH", 16000, int
        )
    )
    enable_ollama_processing: bool = field(
        default_factory=lambda: _get(
            "text_processing", "enable_ollama", "ENABLE_OLLAMA", True, bool
        )
    )
    save_intermediate: bool = field(
        default_factory=lambda: _get(
            "text_processing", "save_intermediate", "SAVE_INTERMEDIATE", False, bool
        )
    )


@dataclass
class AudioConfig:
    """Configuration for audio output."""

    output_format: str = field(
        default_factory=lambda: _get("audio", "output_format", "AUDIO_FORMAT", "mp3")
    )
    bitrate: int = field(
        default_factory=lambda: _get("audio", "bitrate", "AUDIO_BITRATE", 192000, int)
    )
    sample_rate: int = field(
        default_factory=lambda: _get(
            "audio", "sample_rate", "AUDIO_SAMPLE_RATE", 22050, int
        )
    )
    channels: int = field(
        default_factory=lambda: _get("audio", "channels", "AUDIO_CHANNELS", 1, int)
    )


@dataclass
class SecurityConfig:
    """Security configuration."""

    max_input_length: int = field(
        default_factory=lambda: _get(
            "security", "max_input_length", "MAX_INPUT_LENGTH", 1000000, int
        )
    )
    max_file_size: int = field(
        default_factory=lambda: _get(
            "security", "max_file_size", "MAX_FILE_SIZE", 104857600, int
        )
    )
    cors_origins: List[str] = field(
        default_factory=lambda: _get("security", "cors_origins", "CORS_ORIGINS", ["*"])
    )


@dataclass
class DatabaseConfig:
    """Database configuration."""

    url: str = field(
        default_factory=lambda: _get(
            "database", "url", "DATABASE_URL", "sqlite:///audiobook_jobs.db"
        )
    )
    echo: bool = field(
        default_factory=lambda: _get("database", "echo", "DATABASE_ECHO", False, bool)
    )


@dataclass
class WorkerConfig:
    """Configuration for background worker and job processing."""

    # Job timeout in seconds (default: 30 minutes)
    job_timeout: int = field(
        default_factory=lambda: _get(
            "worker", "job_timeout", "WORKER_JOB_TIMEOUT", 1800, int
        )
    )
    # Heartbeat interval in seconds (how often worker updates job heartbeat)
    heartbeat_interval: int = field(
        default_factory=lambda: _get(
            "worker", "heartbeat_interval", "WORKER_HEARTBEAT_INTERVAL", 30, int
        )
    )
    # Stuck detection threshold in seconds (job considered stuck if no heartbeat for this long)
    stuck_threshold: int = field(
        default_factory=lambda: _get(
            "worker", "stuck_threshold", "WORKER_STUCK_THRESHOLD", 120, int
        )
    )
    # Maximum number of retries for failed/stuck jobs
    max_retries: int = field(
        default_factory=lambda: _get(
            "worker", "max_retries", "WORKER_MAX_RETRIES", 3, int
        )
    )
    # Poll interval in seconds
    poll_interval: int = field(
        default_factory=lambda: _get(
            "worker", "poll_interval", "WORKER_POLL_INTERVAL", 5, int
        )
    )
    # TTS operation timeout in seconds (for individual synthesis calls)
    tts_operation_timeout: int = field(
        default_factory=lambda: _get(
            "worker", "tts_operation_timeout", "WORKER_TTS_TIMEOUT", 300, int
        )
    )
    # Enable automatic recovery of stale jobs on startup
    recover_stale_jobs: bool = field(
        default_factory=lambda: _get(
            "worker", "recover_stale_jobs", "WORKER_RECOVER_STALE", True, bool
        )
    )


@dataclass
class AudiobookConfig:
    """Complete configuration for audiobook generation."""

    app: AppConfig = field(default_factory=AppConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    voice_design: VoiceDesignConfig = field(default_factory=VoiceDesignConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    worker: WorkerConfig = field(default_factory=WorkerConfig)

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "AudiobookConfig":
        """Load configuration from YAML file, env vars, or defaults."""
        global _yaml_config
        if config_path:
            _yaml_config = _load_yaml_config(Path(config_path))
        return cls()

    def log_config(self):
        """Log the current configuration."""
        logger.info("=== Audiobook Generator Configuration ===")
        logger.info(f"Server: {self.app.host}:{self.app.port}")
        logger.info(
            f"LLM: provider={self.llm.provider}, model={self.llm.model}, url={self.llm.base_url}, timeout={self.llm.timeout}s"
        )
        logger.info(
            f"TTS: device={self.tts.device or 'auto'}, dtype={self.tts.dtype}, flash_attn={self.tts.use_flash_attention or 'auto'}"
        )
        logger.info(
            f"Text Processing: batch_size={self.processing.max_chars_per_batch}"
        )
        logger.info(f"Audio: {self.audio.output_format}, bitrate={self.audio.bitrate}")
        logger.info(f"Database: {self.database.url}")
        logger.info("=" * 42)


def load_config(config_path: Optional[str] = None) -> AudiobookConfig:
    """
    Load configuration from config.yml, environment variables, or defaults.

    Args:
        config_path: Optional path to config.yml file

    Returns:
        AudiobookConfig instance
    """
    config = AudiobookConfig.load(config_path)
    config.log_config()
    return config

"""Audiobook Generator - Convert text files to multi-speaker audiobooks using LLM + Qwen3-TTS."""

from .text_processor import TextProcessor, TextBatch
from .llm_client import LLMClient, ProcessingResult
from .ollama_client import OllamaClient  # backward compat alias
from .tts_synthesizer import TTSSynthesizer, VoiceConfig
from .speaker_detector import SpeakerDetector
from .audio_combiner import AudioCombiner
from .multi_speaker_generator import MultiSpeakerAudiobookGenerator
from .config import AudiobookConfig, LLMConfig, TTSConfig, VoiceDesignConfig

# Backward compat aliases
OllamaConfig = LLMConfig

__version__ = "0.1.0"

__all__ = [
    "TextProcessor",
    "TextBatch",
    "LLMClient",
    "OllamaClient",
    "ProcessingResult",
    "TTSSynthesizer",
    "VoiceConfig",
    "SpeakerDetector",
    "AudioCombiner",
    "MultiSpeakerAudiobookGenerator",
    "AudiobookConfig",
    "LLMConfig",
    "OllamaConfig",
    "TTSConfig",
    "VoiceDesignConfig",
]

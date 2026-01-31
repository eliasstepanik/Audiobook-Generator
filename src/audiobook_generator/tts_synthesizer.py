"""TTS synthesis module using Qwen3-TTS models."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List, Union
import torch
import soundfile as sf
import numpy as np
import logging

logger = logging.getLogger(__name__)

try:
    from qwen_tts import Qwen3TTSModel

    QWEN_TTS_AVAILABLE = True
except ImportError:
    logger.warning("qwen_tts not installed. TTS functionality will be limited.")
    QWEN_TTS_AVAILABLE = False

# Auto-detect Flash Attention availability
# Note: flash_attn import can fail at runtime (not just ImportError) if GPU not available
FLASH_ATTENTION_AVAILABLE = False
try:
    import flash_attn

    FLASH_ATTENTION_AVAILABLE = True
    logger.info("Flash Attention 2 detected and available")
except ImportError:
    logger.info("Flash Attention 2 not installed - using standard attention")
except Exception as e:
    # Catch RuntimeError from Triton driver detection, etc.
    logger.info(f"Flash Attention 2 not available: {e}")


@dataclass
class VoiceConfig:
    """Configuration for voice synthesis."""

    # Voice design parameters
    design_text: str = "Hello, welcome to this audiobook. I hope you enjoy the story."
    design_instruct: str = (
        "Male, 30 years old, clear and warm narrator voice, professional tone"
    )
    language: str = "English"

    # Model parameters
    # Auto-detect CUDA/ROCm/CPU - ROCm uses same "cuda" namespace in PyTorch
    device: Optional[str] = None  # Auto-detect if None: cuda:0 if available, else cpu
    dtype: str = "bfloat16"
    use_flash_attention: Optional[bool] = None  # Auto-detect if None

    # Voice reference (set after generation)
    reference_audio_path: Optional[str] = None
    reference_audio_data: Optional[Tuple[np.ndarray, int]] = None


class TTSSynthesizer:
    """Handles text-to-speech synthesis using Qwen3-TTS."""

    def __init__(
        self, voice_config: Optional[VoiceConfig] = None, use_voice_design: bool = True
    ):
        """
        Initialize TTS synthesizer.

        Args:
            voice_config: Voice configuration
            use_voice_design: Whether to use voice design model

        Raises:
            ImportError: If qwen_tts is not available
        """
        if not QWEN_TTS_AVAILABLE:
            raise ImportError(
                "qwen_tts is not installed. Please install it to use TTS functionality."
            )

        self.voice_config = voice_config or VoiceConfig()
        self.use_voice_design = use_voice_design

        # Auto-detect device (CUDA/ROCm/CPU) if not explicitly set
        # Note: ROCm uses same "cuda" namespace in PyTorch
        if self.voice_config.device is None:
            if torch.cuda.is_available():
                self.voice_config.device = "cuda:0"
                device_name = torch.cuda.get_device_name(0)
                # Detect if it's ROCm or CUDA
                try:
                    # ROCm builds have torch.version.hip attribute
                    if (
                        hasattr(torch.version, "hip")
                        and getattr(torch.version, "hip", None) is not None
                    ):
                        hip_version = getattr(torch.version, "hip", "unknown")
                        logger.info(
                            f"Auto-detected ROCm GPU: {device_name} (ROCm {hip_version})"
                        )
                    elif (
                        hasattr(torch.version, "cuda")
                        and getattr(torch.version, "cuda", None) is not None
                    ):
                        cuda_version = getattr(torch.version, "cuda", "unknown")
                        logger.info(
                            f"Auto-detected CUDA GPU: {device_name} (CUDA {cuda_version})"
                        )
                    else:
                        logger.info(f"Auto-detected GPU: {device_name}")
                except (AttributeError, Exception):
                    logger.info(f"Auto-detected GPU: {device_name}")
            else:
                self.voice_config.device = "cpu"
                logger.info("No GPU detected - using CPU (will be slower)")

        # Auto-detect Flash Attention if not explicitly set
        if self.voice_config.use_flash_attention is None:
            self.voice_config.use_flash_attention = FLASH_ATTENTION_AVAILABLE
            if FLASH_ATTENTION_AVAILABLE:
                logger.info("Flash Attention enabled (auto-detected)")
            else:
                logger.info("Flash Attention disabled (not installed)")

        # Models (loaded lazily)
        self.design_model = None
        self.clone_model = None
        self.voice_clone_prompt = None

        # Configure torch dtype
        self.torch_dtype = getattr(torch, self.voice_config.dtype)

        logger.info(f"Initialized TTSSynthesizer (device: {self.voice_config.device})")

    def _load_design_model(self):
        """Load voice design model."""
        if self.design_model is None:
            logger.info("Loading Qwen3-TTS VoiceDesign model...")

            kwargs = {
                "device_map": self.voice_config.device,
                "dtype": self.torch_dtype,
            }

            if self.voice_config.use_flash_attention:
                kwargs["attn_implementation"] = "flash_attention_2"

            self.design_model = Qwen3TTSModel.from_pretrained(
                "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", **kwargs
            )

            logger.info("VoiceDesign model loaded successfully")

    def _load_clone_model(self):
        """Load voice cloning model."""
        if self.clone_model is None:
            logger.info("Loading Qwen3-TTS Base model...")

            kwargs = {
                "device_map": self.voice_config.device,
                "dtype": self.torch_dtype,
            }

            if self.voice_config.use_flash_attention:
                kwargs["attn_implementation"] = "flash_attention_2"

            self.clone_model = Qwen3TTSModel.from_pretrained(
                "Qwen/Qwen3-TTS-12Hz-1.7B-Base", **kwargs
            )

            logger.info("Base model loaded successfully")

    def create_voice(
        self,
        output_path: Optional[str] = None,
        design_text: Optional[str] = None,
        design_instruct: Optional[str] = None,
    ) -> Tuple[np.ndarray, int]:
        """
        Create a reference voice using voice design.

        Args:
            output_path: Optional path to save reference audio
            design_text: Override design text
            design_instruct: Override design instructions

        Returns:
            Tuple of (audio_array, sample_rate)
        """
        self._load_design_model()

        text = design_text or self.voice_config.design_text
        instruct = design_instruct or self.voice_config.design_instruct

        logger.info(f"Generating reference voice: '{instruct}'")

        ref_wavs, sr = self.design_model.generate_voice_design(
            text=text, language=self.voice_config.language, instruct=instruct
        )

        audio_data = ref_wavs[0]

        # Save if path provided
        if output_path:
            sf.write(output_path, audio_data, sr)
            logger.info(f"Reference voice saved to: {output_path}")
            self.voice_config.reference_audio_path = output_path

        # Store reference
        self.voice_config.reference_audio_data = (audio_data, sr)

        return audio_data, sr

    def prepare_voice_clone(
        self,
        reference_audio: Optional[Union[str, Tuple[np.ndarray, int]]] = None,
        reference_text: Optional[str] = None,
    ):
        """
        Prepare voice cloning prompt from reference audio.

        Args:
            reference_audio: Path to audio file or (audio_array, sample_rate) tuple
            reference_text: Text corresponding to reference audio
        """
        self._load_clone_model()

        # Get reference audio
        if reference_audio is None:
            if self.voice_config.reference_audio_data is None:
                # Create voice if not exists
                logger.info("No reference audio found, creating one...")
                self.create_voice()
            reference_audio = self.voice_config.reference_audio_data

        # Handle different input types
        if isinstance(reference_audio, str):
            ref_audio_input = reference_audio
        else:
            ref_audio_input = reference_audio

        ref_text = reference_text or self.voice_config.design_text

        logger.info("Creating voice clone prompt...")

        self.voice_clone_prompt = self.clone_model.create_voice_clone_prompt(
            ref_audio=ref_audio_input,
            ref_text=ref_text,
        )

        logger.info("Voice clone prompt ready")

    def synthesize(
        self,
        text: Union[str, List[str]],
        output_path: Optional[Union[str, List[str]]] = None,
        language: Optional[Union[str, List[str]]] = None,
        delivery: Optional[str] = None,
    ) -> Tuple[Union[np.ndarray, List[np.ndarray]], int]:
        """
        Synthesize speech from text with optional per-segment delivery style.

        Args:
            text: Single text or list of texts
            output_path: Optional path(s) to save audio
            language: Language(s) for synthesis
            delivery: Optional delivery instruction (e.g. "slow, tense, whispered")
                     Prepended as context hint for TTS model to control speaking style.

        Returns:
            Tuple of (audio_data, sample_rate)
            audio_data is either a single array or list of arrays
        """
        # Apply delivery style instruction if provided
        if delivery:
            if isinstance(text, list):
                text = [f"[{delivery}] {t}" for t in text]
            else:
                text = f"[{delivery}] {text}"
            logger.info(f"Applied delivery style: {delivery}")
        # Ensure voice clone prompt is ready
        if self.voice_clone_prompt is None:
            self.prepare_voice_clone()

        is_batch = isinstance(text, list)

        if not is_batch:
            text = [text]
            if output_path:
                output_path = [output_path]

        # Prepare language parameter
        if language is None:
            language = [self.voice_config.language] * len(text)
        elif isinstance(language, str):
            language = [language] * len(text)

        logger.info(f"Synthesizing {len(text)} text segment(s)...")

        # Generate audio
        wavs, sr = self.clone_model.generate_voice_clone(
            text=text if is_batch else text[0],
            language=language if is_batch else language[0],
            voice_clone_prompt=self.voice_clone_prompt,
        )

        # Save if paths provided
        if output_path:
            for idx, (audio, path) in enumerate(
                zip(wavs if is_batch else [wavs[0]], output_path)
            ):
                if path:
                    sf.write(path, audio, sr)
                    logger.info(f"Audio saved to: {path}")

        if not is_batch:
            return wavs[0], sr

        return wavs, sr

    def synthesize_batches(
        self,
        texts: List[str],
        output_dir: str,
        filename_prefix: str = "segment",
        batch_size: int = 10,
    ) -> List[str]:
        """
        Synthesize multiple texts in batches and save to files.

        Args:
            texts: List of text segments
            output_dir: Directory to save audio files
            filename_prefix: Prefix for output filenames
            batch_size: Number of texts to process at once

        Returns:
            List of output file paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_paths = []

        # Process in batches
        for batch_start in range(0, len(texts), batch_size):
            batch_end = min(batch_start + batch_size, len(texts))
            batch_texts = texts[batch_start:batch_end]

            # Generate paths for this batch
            batch_paths = [
                str(output_dir / f"{filename_prefix}_{i:04d}.wav")
                for i in range(batch_start, batch_end)
            ]

            logger.info(
                f"Processing batch {batch_start // batch_size + 1} "
                f"({batch_start + 1}-{batch_end} of {len(texts)})"
            )

            # Synthesize
            self.synthesize(text=batch_texts, output_path=batch_paths)

            output_paths.extend(batch_paths)

        return output_paths

    def cleanup(self):
        """Free GPU memory by deleting models."""
        logger.info("Cleaning up TTS models...")

        if self.design_model is not None:
            del self.design_model
            self.design_model = None

        if self.clone_model is not None:
            del self.clone_model
            self.clone_model = None

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        logger.info("Cleanup complete")

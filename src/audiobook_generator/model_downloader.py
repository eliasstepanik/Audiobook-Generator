"""Automatic model downloader and verifier."""

import logging
from pathlib import Path
import torch
from tqdm import tqdm

logger = logging.getLogger(__name__)


class ModelDownloader:
    """Downloads and verifies required models on startup."""

    def __init__(self):
        """Initialize model downloader."""
        self.models_to_download = [
            {
                "name": "Qwen3-TTS VoiceDesign",
                "repo": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                "size": "~1.7GB",
            },
            {
                "name": "Qwen3-TTS Base",
                "repo": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                "size": "~1.7GB",
            },
        ]

    def check_and_download_models(
        self, device: str = "cuda:0", dtype: str = "bfloat16"
    ):
        """
        Check if models are available and download if needed.

        Args:
            device: Device to use for models
            dtype: Data type for models
        """
        logger.info("=" * 60)
        logger.info("MODEL VERIFICATION AND DOWNLOAD")
        logger.info("=" * 60)

        try:
            from qwen_tts import Qwen3TTSModel
        except ImportError:
            logger.error("qwen_tts not installed! Please install: pip install qwen-tts")
            return False

        # Determine actual device and dtype for verification
        # Use CPU for verification if GPU is not available to avoid startup failures
        verification_device = device
        verification_dtype = getattr(torch, dtype)

        if device != "cpu" and not torch.cuda.is_available():
            logger.warning("GPU not available for verification, using CPU instead")
            logger.warning(
                "Models will be loaded on GPU when actually used (if available)"
            )
            verification_device = "cpu"
            # bfloat16 on CPU can be slow, use float32 for verification
            verification_dtype = torch.float32

        for idx, model_info in enumerate(self.models_to_download):
            logger.info(
                f"\n[{idx + 1}/{len(self.models_to_download)}] Checking {model_info['name']}..."
            )
            logger.info(f"Repository: {model_info['repo']}")
            logger.info(f"Size: {model_info['size']}")

            try:
                # Check if model exists in cache
                cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
                model_cache = (
                    cache_dir / f"models--{model_info['repo'].replace('/', '--')}"
                )

                if model_cache.exists():
                    logger.info(f"✓ {model_info['name']} found in cache")
                else:
                    logger.info(f"⬇ Downloading {model_info['name']}...")
                    logger.info(
                        "This may take a few minutes depending on your connection..."
                    )

                # Load model (will download if not cached)
                kwargs = {
                    "device_map": verification_device,
                    "dtype": verification_dtype,
                }

                logger.info(f"Loading {model_info['name']} on {verification_device}...")
                model = Qwen3TTSModel.from_pretrained(model_info["repo"], **kwargs)

                # Verify model loaded successfully
                logger.info(f"✓ {model_info['name']} loaded successfully!")

                # Clean up to free memory
                del model
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

            except Exception as e:
                logger.error(f"✗ Failed to load {model_info['name']}: {e}")
                logger.error("Please check your internet connection and try again.")
                return False

        logger.info("\n" + "=" * 60)
        logger.info("ALL MODELS VERIFIED AND READY!")
        logger.info("=" * 60)
        logger.info("")

        return True

    def get_model_info(self):
        """Get information about required models."""
        total_size = 0
        info = []

        for model in self.models_to_download:
            info.append(f"- {model['name']}: {model['size']}")
            # Extract size in GB (rough estimate)
            if "GB" in model["size"]:
                size_gb = float(model["size"].replace("~", "").replace("GB", ""))
                total_size += size_gb

        info.append(f"\nTotal download size: ~{total_size:.1f}GB")
        info.append("Models are downloaded once and cached for future use.")

        return "\n".join(info)


def verify_models_on_startup(
    device: str = "cuda:0", dtype: str = "bfloat16", skip_verification: bool = False
) -> bool:
    """
    Verify and download models on startup.

    Args:
        device: Device to use
        dtype: Data type
        skip_verification: Skip model verification (for testing)

    Returns:
        True if models are ready, False otherwise
    """
    if skip_verification:
        logger.warning("Model verification skipped!")
        return True

    downloader = ModelDownloader()

    logger.info("\n")
    logger.info("Required models:")
    logger.info(downloader.get_model_info())
    logger.info("\n")

    return downloader.check_and_download_models(device, dtype)

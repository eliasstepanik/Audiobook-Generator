"""Example without Ollama text processing (direct TTS)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audiobook_generator import MultiSpeakerAudiobookGenerator
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def main():
    """Generate audiobook without text processing."""

    # Initialize with processing disabled
    generator = MultiSpeakerAudiobookGenerator(
        max_chars_per_batch=16000,
        tts_device="cuda:0",
        enable_text_processing=False,  # Skip Ollama processing
        enable_speaker_detection=False,
    )

    # Generate audiobook (much faster without LLM processing)
    metadata = generator.generate(
        input_file="../data/input/sample.txt",
        output_dir="../data/output/no_processing",
        output_filename="audiobook.mp3",
        save_intermediate=True,
        tts_batch_size=10,
    )

    print(f"\nGenerated audiobook: {metadata['output_file']}")


if __name__ == "__main__":
    main()

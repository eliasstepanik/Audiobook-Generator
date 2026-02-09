"""Single speaker (narrator only) example."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audiobook_generator import MultiSpeakerAudiobookGenerator
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def main():
    """Generate single-speaker audiobook."""

    # Initialize with speaker detection disabled
    generator = MultiSpeakerAudiobookGenerator(
        ollama_model="gpt-oss-16k:120b",
        ollama_base_url="http://localhost:11434/v1",
        max_chars_per_batch=16000,
        tts_device="cuda:0",
        enable_text_processing=True,
        enable_speaker_detection=False,  # Disable multi-speaker
    )

    # Generate audiobook
    metadata = generator.generate(
        input_file="../data/input/sample.txt",
        output_dir="../data/output/single_speaker",
        output_filename="audiobook.mp3",
        save_intermediate=True,
        tts_batch_size=10,  # Larger batches for single speaker
    )

    print(f"\nGenerated audiobook: {metadata['output_file']}")


if __name__ == "__main__":
    main()

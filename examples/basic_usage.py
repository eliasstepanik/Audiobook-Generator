"""Basic usage example for audiobook generator."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audiobook_generator import MultiSpeakerAudiobookGenerator
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def main():
    """Generate audiobook from a text file."""

    # Initialize generator
    generator = MultiSpeakerAudiobookGenerator(
        ollama_model="gpt-oss-16k:120b",
        ollama_base_url="http://localhost:11434/v1",
        max_chars_per_batch=16000,
        tts_device="cuda:0",
        tts_dtype="bfloat16",
        enable_text_processing=True,
        enable_speaker_detection=True,
    )

    # Generate audiobook
    input_file = "../data/input/sample.txt"
    output_dir = "../data/output/sample_audiobook"

    metadata = generator.generate(
        input_file=input_file,
        output_dir=output_dir,
        output_filename="audiobook.mp3",
        save_intermediate=True,
        tts_batch_size=5,
    )

    print("\n" + "=" * 60)
    print("Generation complete!")
    print(f"Audiobook: {metadata['output_file']}")
    print(f"Speakers: {metadata['num_speakers']}")
    print(f"Segments: {metadata['num_segments']}")
    print("=" * 60)


if __name__ == "__main__":
    main()

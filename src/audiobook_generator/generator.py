"""Main audiobook generator orchestrator."""

from pathlib import Path
from typing import Optional, List, Dict, Any
import logging
from tqdm import tqdm
import json

from .text_processor import TextProcessor, TextBatch
from .ollama_client import OllamaClient, ProcessingResult
from .tts_synthesizer import TTSSynthesizer, VoiceConfig

logger = logging.getLogger(__name__)


class AudiobookGenerator:
    """Orchestrates the audiobook generation pipeline."""

    def __init__(
        self,
        ollama_model: str = "gpt-oss:120b",
        ollama_host: Optional[str] = None,
        voice_config: Optional[VoiceConfig] = None,
        max_chars_per_batch: int = 16000,
        enable_text_processing: bool = True,
    ):
        """
        Initialize audiobook generator.

        Args:
            ollama_model: Ollama model name
            ollama_host: Ollama API endpoint
            voice_config: Voice configuration for TTS
            max_chars_per_batch: Maximum characters per batch
            enable_text_processing: Whether to process text through Ollama
        """
        self.enable_text_processing = enable_text_processing

        # Initialize components
        self.text_processor = TextProcessor(max_chars=max_chars_per_batch)

        if enable_text_processing:
            self.ollama_client = OllamaClient(model=ollama_model, host=ollama_host)
        else:
            self.ollama_client = None

        self.tts_synthesizer = TTSSynthesizer(voice_config=voice_config)

        logger.info("AudiobookGenerator initialized")

    def setup_voice(
        self,
        reference_audio_path: Optional[str] = None,
        design_text: Optional[str] = None,
        design_instruct: Optional[str] = None,
        output_path: Optional[str] = None,
    ):
        """
        Set up the voice for synthesis.

        Args:
            reference_audio_path: Path to existing reference audio
            design_text: Text for voice design
            design_instruct: Instructions for voice design
            output_path: Where to save generated reference audio
        """
        if reference_audio_path:
            # Use existing reference
            logger.info(f"Using reference audio: {reference_audio_path}")
            self.tts_synthesizer.prepare_voice_clone(
                reference_audio=reference_audio_path, reference_text=design_text
            )
        else:
            # Create new voice
            logger.info("Creating new reference voice...")
            self.tts_synthesizer.create_voice(
                output_path=output_path,
                design_text=design_text,
                design_instruct=design_instruct,
            )
            self.tts_synthesizer.prepare_voice_clone()

    def generate(
        self,
        input_file: str,
        output_dir: str,
        voice_reference_path: Optional[str] = None,
        voice_design_instruct: Optional[str] = None,
        save_metadata: bool = True,
        tts_batch_size: int = 5,
    ) -> Dict[str, Any]:
        """
        Generate audiobook from text file.

        Args:
            input_file: Path to input text file
            output_dir: Directory for output files
            voice_reference_path: Optional path to voice reference audio
            voice_design_instruct: Optional voice design instructions
            save_metadata: Whether to save processing metadata
            tts_batch_size: Number of segments to synthesize at once

        Returns:
            Dictionary with generation results and metadata
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Starting audiobook generation for: {input_file}")
        logger.info(f"Output directory: {output_dir}")

        # Step 1: Read and batch text
        logger.info("Step 1: Reading and batching text...")
        batches = self.text_processor.process_file(input_file)
        logger.info(f"Created {len(batches)} batches")

        # Step 2: Process through Ollama (optional)
        if self.enable_text_processing and self.ollama_client:
            logger.info("Step 2: Processing text through Ollama...")
            processed_texts = []
            processing_metadata = []

            for batch in tqdm(batches, desc="Processing batches"):
                result = self.ollama_client.process_text(
                    text=batch.text, batch_index=batch.batch_index
                )
                processed_texts.append(result.processed_text)
                processing_metadata.append(result.metadata)
        else:
            logger.info("Step 2: Skipping Ollama processing (disabled)")
            processed_texts = [batch.text for batch in batches]
            processing_metadata = []

        # Step 3: Set up voice
        logger.info("Step 3: Setting up voice...")
        ref_voice_path = output_dir / "reference_voice.wav"

        self.setup_voice(
            reference_audio_path=voice_reference_path,
            design_instruct=voice_design_instruct,
            output_path=str(ref_voice_path) if not voice_reference_path else None,
        )

        # Step 4: Synthesize audio
        logger.info("Step 4: Synthesizing audio...")
        audio_files = self.tts_synthesizer.synthesize_batches(
            texts=processed_texts,
            output_dir=str(output_dir),
            filename_prefix="segment",
            batch_size=tts_batch_size,
        )

        logger.info(f"Generated {len(audio_files)} audio segments")

        # Step 5: Save metadata
        metadata = {
            "input_file": str(input_file),
            "output_dir": str(output_dir),
            "num_batches": len(batches),
            "num_audio_files": len(audio_files),
            "text_processing_enabled": self.enable_text_processing,
            "batches": [
                {
                    "index": batch.batch_index,
                    "start_char": batch.start_char,
                    "end_char": batch.end_char,
                    "length": batch.length,
                    "audio_file": audio_files[batch.batch_index]
                    if batch.batch_index < len(audio_files)
                    else None,
                }
                for batch in batches
            ],
        }

        if processing_metadata:
            metadata["ollama_metadata"] = processing_metadata

        if save_metadata:
            metadata_path = output_dir / "metadata.json"
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
            logger.info(f"Metadata saved to: {metadata_path}")

        logger.info("Audiobook generation complete!")

        return metadata

    def generate_quick(
        self, text: str, output_path: str, process_text: bool = False
    ) -> str:
        """
        Quick generation for short text without batching.

        Args:
            text: Text to synthesize
            output_path: Path for output audio file
            process_text: Whether to process through Ollama

        Returns:
            Path to generated audio file
        """
        logger.info("Quick generation mode")

        # Process if enabled
        if process_text and self.ollama_client:
            result = self.ollama_client.process_text(text)
            text = result.processed_text

        # Ensure voice is ready
        if self.tts_synthesizer.voice_clone_prompt is None:
            self.setup_voice()

        # Synthesize
        self.tts_synthesizer.synthesize(text=text, output_path=output_path)

        logger.info(f"Audio saved to: {output_path}")
        return output_path

    def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up AudiobookGenerator...")
        self.tts_synthesizer.cleanup()
        logger.info("Cleanup complete")

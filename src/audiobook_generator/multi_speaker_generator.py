"""Multi-speaker audiobook generator with complete pipeline."""

from pathlib import Path
from typing import Optional, Dict, Any, List
import logging
from tqdm import tqdm
import json

from .text_processor import TextProcessor
from .ollama_client import OllamaClient
from .speaker_detector import SpeakerDetector
from .tts_synthesizer import TTSSynthesizer, VoiceConfig
from .audio_combiner import AudioCombiner

logger = logging.getLogger(__name__)


class MultiSpeakerAudiobookGenerator:
    """Complete pipeline for generating multi-speaker audiobooks."""

    def __init__(
        self,
        ollama_model: str = "gpt-oss-16k:120b",
        ollama_base_url: str = "http://192.168.178.166:11434/v1",
        max_chars_per_batch: int = 16000,
        tts_device: str = "cuda:0",
        tts_dtype: str = "bfloat16",
        enable_text_processing: bool = True,
        enable_speaker_detection: bool = True,
    ):
        """
        Initialize multi-speaker audiobook generator.

        Args:
            ollama_model: Ollama model name (default: gpt-oss-16k:120b)
            ollama_base_url: Ollama API base URL
            max_chars_per_batch: Maximum characters per batch
            tts_device: TTS device (cuda:0, cpu, etc.)
            tts_dtype: TTS dtype (bfloat16, float32, etc.)
            enable_text_processing: Whether to process text through Ollama
            enable_speaker_detection: Whether to detect and use multiple speakers
        """
        self.enable_text_processing = enable_text_processing
        self.enable_speaker_detection = enable_speaker_detection

        # Initialize components
        self.text_processor = TextProcessor(max_chars=max_chars_per_batch)

        if enable_text_processing:
            self.ollama_client = OllamaClient(
                model=ollama_model, base_url=ollama_base_url
            )

            if enable_speaker_detection:
                self.speaker_detector = SpeakerDetector(self.ollama_client)
            else:
                self.speaker_detector = None
        else:
            self.ollama_client = None
            self.speaker_detector = None

        # TTS components (initialized per speaker)
        self.tts_device = tts_device
        self.tts_dtype = tts_dtype
        self.speaker_synthesizers: Dict[str, TTSSynthesizer] = {}

        # Audio combiner
        self.audio_combiner = AudioCombiner(
            silence_between_segments=500,
            normalize_audio=True,
            target_format="mp3",
            bitrate="192k",
        )

        logger.info("MultiSpeakerAudiobookGenerator initialized")

    def generate(
        self,
        input_file: str,
        output_dir: str,
        output_filename: str = "audiobook.mp3",
        save_intermediate: bool = True,
        tts_batch_size: int = 5,
    ) -> Dict[str, Any]:
        """
        Generate complete audiobook with full pipeline.

        Pipeline:
        1. Read and batch text file
        2. Process batches through Ollama
        3. Detect speakers in processed text
        4. Generate voice for each speaker
        5. Assign speakers to text segments
        6. Synthesize audio per speaker (batched)
        7. Combine all audio into single MP3

        Args:
            input_file: Path to input text file
            output_dir: Directory for output files
            output_filename: Name for final audiobook file
            save_intermediate: Whether to save intermediate files
            tts_batch_size: Number of segments to synthesize at once per speaker

        Returns:
            Dictionary with generation metadata
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        segments_dir = output_dir / "segments"
        segments_dir.mkdir(exist_ok=True)

        logger.info("=" * 60)
        logger.info("AUDIOBOOK GENERATION PIPELINE")
        logger.info("=" * 60)
        logger.info(f"Input: {input_file}")
        logger.info(f"Output: {output_dir / output_filename}")
        logger.info("")

        # STEP 1: Read and batch text
        logger.info("STEP 1: Reading and batching text...")
        batches = self.text_processor.process_file(input_file)
        logger.info(f"✓ Created {len(batches)} batches\n")

        # STEP 2: Process through Ollama
        processed_texts = []
        if self.enable_text_processing and self.ollama_client:
            logger.info("STEP 2: Processing text through Ollama...")

            for batch in tqdm(batches, desc="Processing batches"):
                result = self.ollama_client.process_text(
                    text=batch.text, batch_index=batch.batch_index
                )
                processed_texts.append(result.processed_text)

            # Combine all processed text
            full_processed_text = " ".join(processed_texts)

            if save_intermediate:
                processed_file = output_dir / "processed_text.txt"
                with open(processed_file, "w", encoding="utf-8") as f:
                    f.write(full_processed_text)
                logger.info(f"✓ Processed text saved to: {processed_file}")

            logger.info(f"✓ Processed {len(processed_texts)} batches\n")
        else:
            logger.info("STEP 2: Skipping Ollama processing (disabled)\n")
            processed_texts = [batch.text for batch in batches]
            full_processed_text = " ".join(processed_texts)

        # STEP 3: Detect speakers
        detected_speakers = []
        if self.enable_speaker_detection and self.speaker_detector:
            logger.info("STEP 3: Detecting speakers in text...")
            detected_speakers = self.speaker_detector.detect_speakers(
                full_processed_text
            )

            logger.info(f"✓ Detected {len(detected_speakers)} speakers:")
            for speaker in detected_speakers:
                logger.info(
                    f"  - {speaker['name']}: {speaker['voice_characteristics']}"
                )

            if save_intermediate:
                speakers_file = output_dir / "detected_speakers.json"
                with open(speakers_file, "w", encoding="utf-8") as f:
                    json.dump(detected_speakers, f, indent=2)
                logger.info(f"✓ Speakers saved to: {speakers_file}")

            logger.info("")
        else:
            logger.info("STEP 3: Using single narrator (speaker detection disabled)\n")
            detected_speakers = [
                {
                    "id": "narrator",
                    "name": "Narrator",
                    "description": "Main narrative voice",
                    "voice_characteristics": (
                        "Male, 35 years old, warm and engaging narrator voice, "
                        "clear articulation, professional audiobook narrator tone"
                    ),
                }
            ]

        # STEP 4: Generate voices for each speaker
        logger.info("STEP 4: Generating voices for speakers...")
        for speaker in tqdm(detected_speakers, desc="Creating voices"):
            voice_config = VoiceConfig(
                design_text=f"Hello, I am {speaker['name']}. Let me tell you this story.",
                design_instruct=speaker["voice_characteristics"],
                device=self.tts_device,
                dtype=self.tts_dtype,
            )

            synthesizer = TTSSynthesizer(voice_config=voice_config)

            # Create reference voice
            ref_path = segments_dir / f"voice_{speaker['id']}.wav"
            synthesizer.create_voice(output_path=str(ref_path))
            synthesizer.prepare_voice_clone()

            self.speaker_synthesizers[speaker["id"]] = synthesizer

        logger.info(f"✓ Generated {len(self.speaker_synthesizers)} voices\n")

        # STEP 5: Assign speakers to segments
        logger.info("STEP 5: Assigning speakers to text segments...")
        if (
            self.enable_speaker_detection
            and self.speaker_detector
            and len(detected_speakers) > 1
        ):
            segment_assignments = self.speaker_detector.assign_speakers_to_segments(
                processed_texts, detected_speakers
            )
        else:
            # Single speaker mode
            segment_assignments = [
                {"text": text, "speaker_id": "narrator", "segment_index": idx}
                for idx, text in enumerate(processed_texts)
            ]

        logger.info(f"✓ Assigned speakers to {len(segment_assignments)} segments\n")

        # STEP 6: Synthesize audio per speaker (batched)
        logger.info("STEP 6: Synthesizing audio...")

        # Group segments by speaker
        speaker_segments = {}
        for assignment in segment_assignments:
            speaker_id = assignment["speaker_id"]
            if speaker_id not in speaker_segments:
                speaker_segments[speaker_id] = []
            speaker_segments[speaker_id].append(assignment)

        # Track all audio files in order
        all_audio_files = [None] * len(segment_assignments)

        # Process each speaker's segments
        for speaker_id, segments in speaker_segments.items():
            logger.info(f"  Synthesizing {len(segments)} segments for {speaker_id}...")

            synthesizer = self.speaker_synthesizers.get(speaker_id)
            if not synthesizer:
                logger.warning(f"  No synthesizer for {speaker_id}, using narrator")
                synthesizer = self.speaker_synthesizers.get("narrator")

            # Process in batches
            for i in range(0, len(segments), tts_batch_size):
                batch = segments[i : i + tts_batch_size]
                texts = [seg["text"] for seg in batch]

                # Generate audio for this batch
                wavs, sr = synthesizer.synthesize(text=texts)

                # Save individual files
                for j, (segment, audio) in enumerate(
                    zip(batch, wavs if isinstance(wavs, list) else [wavs])
                ):
                    seg_idx = segment["segment_index"]
                    output_path = (
                        segments_dir / f"segment_{seg_idx:04d}_{speaker_id}.wav"
                    )

                    import soundfile as sf

                    sf.write(str(output_path), audio, sr)

                    all_audio_files[seg_idx] = str(output_path)

        logger.info(f"✓ Generated {len(all_audio_files)} audio segments\n")

        # STEP 7: Combine into single MP3
        logger.info("STEP 7: Combining audio into final audiobook...")
        final_output = output_dir / output_filename

        self.audio_combiner.combine_wav_files(
            input_files=all_audio_files, output_path=str(final_output)
        )

        logger.info(f"✓ Final audiobook: {final_output}\n")

        # Clean up synthesizers
        for synthesizer in self.speaker_synthesizers.values():
            synthesizer.cleanup()

        # Create metadata
        metadata = {
            "input_file": str(input_file),
            "output_file": str(final_output),
            "num_batches": len(batches),
            "num_segments": len(segment_assignments),
            "num_speakers": len(detected_speakers),
            "speakers": detected_speakers,
            "text_processing_enabled": self.enable_text_processing,
            "speaker_detection_enabled": self.enable_speaker_detection,
        }

        if save_intermediate:
            metadata_path = output_dir / "metadata.json"
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
            logger.info(f"Metadata saved to: {metadata_path}")

        logger.info("=" * 60)
        logger.info("AUDIOBOOK GENERATION COMPLETE!")
        logger.info("=" * 60)

        return metadata

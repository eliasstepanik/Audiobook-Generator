"""Background worker with detailed progress reporting."""

import logging
import time
import requests
from pathlib import Path
from typing import Optional
import traceback

from .job_queue import JobQueue
from .models import JobStatus
from .multi_speaker_generator import MultiSpeakerAudiobookGenerator
from .voice_control import DetailedVoiceProfile

logger = logging.getLogger(__name__)


class AudiobookWorkerWithProgress:
    """Background worker that processes jobs with detailed progress updates."""

    def __init__(
        self,
        job_queue: JobQueue,
        output_base_dir: str = "./data/output",
        ollama_model: str = "gpt-oss-16k:120b",
        ollama_base_url: str = "http://192.168.178.166:11434/v1",
        tts_device: str = "cuda:0",
        tts_dtype: str = "bfloat16",
        poll_interval: int = 5,
    ):
        """
        Initialize worker.

        Args:
            job_queue: Job queue instance
            output_base_dir: Base directory for output files
            ollama_model: Ollama model name
            ollama_base_url: Ollama API base URL
            tts_device: TTS device
            tts_dtype: TTS dtype
            poll_interval: Seconds to wait between polling for jobs
        """
        self.job_queue = job_queue
        self.output_base_dir = Path(output_base_dir)
        self.output_base_dir.mkdir(parents=True, exist_ok=True)

        self.ollama_model = ollama_model
        self.ollama_base_url = ollama_base_url
        self.tts_device = tts_device
        self.tts_dtype = tts_dtype
        self.poll_interval = poll_interval

        self.running = False
        self.current_job_id = None

        logger.info("AudiobookWorkerWithProgress initialized")

    def update_progress(
        self, progress: int, message: str, details: Optional[dict] = None
    ):
        """Update job progress with detailed message and optional JSON details."""
        import json

        if self.current_job_id:
            # Prepare update data
            update_data = {
                "progress": progress,
                "progress_message": message,
            }

            # Add detailed progress if provided
            if details:
                update_data["progress_details"] = json.dumps(details)

            self.job_queue.update_job_status(
                self.current_job_id, JobStatus.PROCESSING, **update_data
            )
            logger.info(f"Progress {progress}%: {message}")

    def send_webhook(self, webhook_url: str, job_id: str, status: str):
        """
        Send webhook notification.

        Args:
            webhook_url: Webhook URL
            job_id: Job ID
            status: Job status
        """
        try:
            payload = {"job_id": job_id, "status": status, "timestamp": time.time()}

            response = requests.post(webhook_url, json=payload, timeout=10)

            if response.status_code == 200:
                logger.info(f"Webhook sent successfully: {webhook_url}")
            else:
                logger.warning(
                    f"Webhook returned status {response.status_code}: {webhook_url}"
                )

        except Exception as e:
            logger.error(f"Failed to send webhook to {webhook_url}: {e}")

    def process_job(self, job_id: str):
        """
        Process a single job with detailed progress updates.

        Args:
            job_id: Job ID to process
        """
        self.current_job_id = job_id
        logger.info(f"Processing job: {job_id}")

        # Get job details
        job = self.job_queue.get_job(job_id)
        if not job:
            logger.error(f"Job not found: {job_id}")
            return

        # Update status to processing
        self.update_progress(0, "Initializing...")

        try:
            # Create output directory for this job
            job_output_dir = self.output_base_dir / job_id
            job_output_dir.mkdir(parents=True, exist_ok=True)

            # Save input text to file
            input_file = job_output_dir / "input.txt"
            with open(input_file, "w", encoding="utf-8") as f:
                f.write(job.input_text)

            # Initialize generator with progress callbacks
            self.update_progress(5, "Loading models...")

            from .text_processor import TextProcessor
            from .ollama_client import OllamaClient
            from .speaker_detector import SpeakerDetector
            from .tts_synthesizer import TTSSynthesizer, VoiceConfig
            from .audio_combiner import AudioCombiner

            text_processor = TextProcessor(max_chars=16000)

            # Step 1: Read and batch
            self.update_progress(10, "Reading and batching text...")
            batches = text_processor.process_file(str(input_file))
            total_batches = len(batches)
            self.update_progress(15, f"Created {total_batches} text batches")

            # Step 2: Process through Ollama
            processed_texts = []
            if job.enable_text_processing:
                ollama_client = OllamaClient(
                    model=self.ollama_model, base_url=self.ollama_base_url
                )

                for idx, batch in enumerate(batches):
                    progress = 15 + int((idx / total_batches) * 30)
                    self.update_progress(
                        progress,
                        f"Processing batch {idx + 1}/{total_batches} through Ollama...",
                    )
                    result = ollama_client.process_text(
                        text=batch.text, batch_index=batch.batch_index
                    )
                    processed_texts.append(result.processed_text)

                self.update_progress(
                    45, f"Text processing complete ({total_batches} batches)"
                )
            else:
                processed_texts = [batch.text for batch in batches]
                self.update_progress(45, "Skipped text processing")

            full_processed_text = " ".join(processed_texts)

            # Step 3: Detect speakers
            detected_speakers = []
            if job.enable_speaker_detection:
                self.update_progress(50, "Detecting speakers...")
                speaker_detector = (
                    SpeakerDetector(ollama_client)
                    if job.enable_text_processing
                    else None
                )

                if speaker_detector:
                    detected_speakers = speaker_detector.detect_speakers(
                        full_processed_text
                    )
                    self.update_progress(
                        55, f"Detected {len(detected_speakers)} speakers"
                    )
                else:
                    detected_speakers = [
                        {
                            "id": "narrator",
                            "name": "Narrator",
                            "description": "Main narrative voice",
                            "voice_characteristics": "Male, 35 years old, warm narrator voice",
                        }
                    ]
                    self.update_progress(55, "Using single narrator")
            else:
                detected_speakers = [
                    {
                        "id": "narrator",
                        "name": "Narrator",
                        "description": "Main narrative voice",
                        "voice_characteristics": "Male, 35 years old, warm narrator voice",
                    }
                ]
                self.update_progress(55, "Using single narrator (detection disabled)")

            # Step 4: Generate voices with detailed voice control
            speaker_synthesizers = {}
            for idx, speaker in enumerate(detected_speakers):
                progress = 55 + int((idx / len(detected_speakers)) * 10)

                # Parse detailed voice characteristics
                voice_chars = speaker["voice_characteristics"]
                try:
                    # Use DetailedVoiceProfile to parse and enhance voice characteristics
                    voice_profile = DetailedVoiceProfile.from_natural_language(
                        voice_chars
                    )
                    enhanced_instruction = voice_profile.to_instruction()
                    logger.info(f"Voice for {speaker['name']}: {enhanced_instruction}")
                except Exception as e:
                    logger.warning(
                        f"Failed to parse voice profile, using original: {e}"
                    )
                    enhanced_instruction = voice_chars

                self.update_progress(
                    progress,
                    f"Generating voice for {speaker['name']}\n🎤 {enhanced_instruction}",
                )

                voice_config = VoiceConfig(
                    design_text=f"Hello, I am {speaker['name']}.",
                    design_instruct=enhanced_instruction,
                    device=self.tts_device,
                    dtype=self.tts_dtype,
                )

                synthesizer = TTSSynthesizer(voice_config=voice_config)
                ref_path = job_output_dir / "segments" / f"voice_{speaker['id']}.wav"
                ref_path.parent.mkdir(exist_ok=True)
                synthesizer.create_voice(output_path=str(ref_path))
                synthesizer.prepare_voice_clone()
                speaker_synthesizers[speaker["id"]] = synthesizer

            self.update_progress(
                65,
                f"Generated {len(speaker_synthesizers)} voices with detailed control",
            )

            # Step 5: Synthesize audio
            self.update_progress(70, "Synthesizing audio...")

            audio_files = []
            for idx, text in enumerate(processed_texts):
                progress = 70 + int((idx / len(processed_texts)) * 25)
                self.update_progress(
                    progress,
                    f"Synthesizing segment {idx + 1}/{len(processed_texts)}...",
                )

                synthesizer = speaker_synthesizers.get("narrator")
                output_path = job_output_dir / "segments" / f"segment_{idx:04d}.wav"

                wavs, sr = synthesizer.synthesize(
                    text=text, output_path=str(output_path)
                )
                audio_files.append(str(output_path))

            self.update_progress(95, "Combining audio into MP3...")

            # Step 6: Combine audio
            audio_combiner = AudioCombiner(
                silence_between_segments=500,
                normalize_audio=True,
                target_format="mp3",
                bitrate="192k",
            )

            final_output = job_output_dir / job.output_filename
            audio_combiner.combine_wav_files(
                input_files=audio_files, output_path=str(final_output)
            )

            # Update job as completed
            self.job_queue.update_job_status(
                job_id,
                JobStatus.COMPLETED,
                progress=100,
                progress_message="Complete! Audiobook ready for download",
                output_path=str(final_output),
            )

            logger.info(f"Job completed: {job_id}")

            # Cleanup
            for synthesizer in speaker_synthesizers.values():
                synthesizer.cleanup()

            # Send webhook if configured
            if job.webhook_url:
                self.send_webhook(job.webhook_url, job_id, "completed")

        except Exception as e:
            error_msg = f"Job failed: {str(e)}\n{traceback.format_exc()}"
            logger.error(f"Job {job_id} failed: {error_msg}")

            # Update job as failed
            self.job_queue.update_job_status(
                job_id,
                JobStatus.FAILED,
                progress_message=f"Failed: {str(e)}",
                error_message=error_msg,
            )

            # Send webhook if configured
            if job.webhook_url:
                self.send_webhook(job.webhook_url, job_id, "failed")

        finally:
            self.current_job_id = None

    def run(self):
        """Run the worker loop."""
        self.running = True
        logger.info("Worker started")

        while self.running:
            try:
                # Get next pending job
                job = self.job_queue.get_next_pending_job()

                if job:
                    self.process_job(job.job_id)
                else:
                    # No jobs, wait before polling again
                    time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                logger.info("Worker interrupted by user")
                self.running = False
                break

            except Exception as e:
                logger.error(f"Worker error: {e}")
                time.sleep(self.poll_interval)

        logger.info("Worker stopped")

    def stop(self):
        """Stop the worker."""
        self.running = False

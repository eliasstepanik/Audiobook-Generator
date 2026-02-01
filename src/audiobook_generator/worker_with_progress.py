"""Background worker with detailed progress reporting."""

import json
import logging
import time
import requests
from pathlib import Path
from typing import Optional, Dict, List
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
        llm_provider: str = "ollama",
        llm_model: str = "gpt-oss:20b",
        llm_base_url: str = "http://192.168.178.166:11434/v1",
        llm_api_key: Optional[str] = None,
        tts_device: str = "cuda:0",
        tts_dtype: str = "bfloat16",
        poll_interval: int = 5,
        # Backward compat
        ollama_model: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
    ):
        """
        Initialize worker.

        Args:
            job_queue: Job queue instance
            output_base_dir: Base directory for output files
            llm_provider: LLM provider ("ollama", "openai", "anthropic")
            llm_model: LLM model name
            llm_base_url: LLM API base URL
            llm_api_key: API key (required for openai/anthropic)
            tts_device: TTS device
            tts_dtype: TTS dtype
            poll_interval: Seconds to wait between polling for jobs
        """
        self.job_queue = job_queue
        self.output_base_dir = Path(output_base_dir)
        self.output_base_dir.mkdir(parents=True, exist_ok=True)

        # LLM config (with backward compat for ollama_model/ollama_base_url)
        self.llm_provider = llm_provider
        self.llm_model = ollama_model or llm_model
        self.llm_base_url = ollama_base_url or llm_base_url
        self.llm_api_key = llm_api_key
        self.tts_device = tts_device
        self.tts_dtype = tts_dtype
        self.poll_interval = poll_interval

        self.running = False
        self.current_job_id = None

        logger.info(
            f"AudiobookWorkerWithProgress initialized (LLM: {self.llm_provider}/{self.llm_model})"
        )

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

    def process_job(
        self,
        job_id: str,
        shared_synthesizers: Optional[Dict] = None,
        shared_speakers: Optional[List] = None,
    ):
        """
        Process a single job with detailed progress updates.

        Args:
            job_id: Job ID to process
            shared_synthesizers: Pre-built speaker synthesizers (for batch mode)
            shared_speakers: Pre-detected speakers (for batch mode)
        """
        self.current_job_id = job_id
        logger.info(f"Processing job: {job_id}")

        job = self.job_queue.get_job(job_id)
        if not job:
            logger.error(f"Job not found: {job_id}")
            return

        self.update_progress(0, "Initializing...")

        try:
            job_output_dir = self.output_base_dir / job_id
            job_output_dir.mkdir(parents=True, exist_ok=True)

            input_file = job_output_dir / "input.txt"
            with open(input_file, "w", encoding="utf-8") as f:
                f.write(job.input_text)

            self.update_progress(5, "Loading models...")

            from .text_processor import TextProcessor
            from .llm_client import LLMClient
            from .speaker_detector import SpeakerDetector
            from .tts_synthesizer import TTSSynthesizer, VoiceConfig
            from .audio_combiner import AudioCombiner

            text_processor = TextProcessor(max_chars=16000)

            # Step 1: Read and batch
            self.update_progress(10, "Reading and batching text...")
            batches = text_processor.process_file(str(input_file))
            total_batches = len(batches)
            self.update_progress(15, f"Created {total_batches} text batches")

            # Step 2: Process through LLM
            processed_texts = []
            llm_client = LLMClient(
                provider=self.llm_provider,
                model=self.llm_model,
                base_url=self.llm_base_url,
                api_key=self.llm_api_key,
            )

            if job.enable_text_processing:
                for idx, batch in enumerate(batches):
                    progress = 15 + int((idx / total_batches) * 30)
                    self.update_progress(
                        progress,
                        f"Processing batch {idx + 1}/{total_batches} through LLM...",
                    )
                    result = llm_client.process_text(
                        text=batch.text, batch_index=batch.batch_index
                    )
                    if len(result.processed_text) < len(batch.text) * 0.5:
                        logger.warning(
                            f"LLM returned much shorter text ({len(result.processed_text)} vs {len(batch.text)} chars), using original"
                        )
                        processed_texts.append(batch.text)
                    else:
                        processed_texts.append(result.processed_text)

                self.update_progress(
                    45, f"Text processing complete ({total_batches} batches)"
                )
            else:
                processed_texts = [batch.text for batch in batches]
                self.update_progress(45, "Skipped text processing")

            full_processed_text = " ".join(processed_texts)

            # Step 3: Detect speakers (skip if shared from batch)
            using_shared = (
                shared_synthesizers is not None and shared_speakers is not None
            )

            if using_shared:
                detected_speakers = shared_speakers
                self.update_progress(
                    52, f"Using shared voices ({len(detected_speakers)} speakers)"
                )
            elif job.enable_speaker_detection:
                self.update_progress(48, "Detecting speakers...")
                speaker_detector = SpeakerDetector(llm_client)
                detected_speakers = speaker_detector.detect_speakers(
                    full_processed_text
                )
                speaker_names = [s["name"] for s in detected_speakers]
                self.update_progress(
                    52,
                    f"Detected {len(detected_speakers)} speakers: {', '.join(speaker_names)}",
                )
            else:
                detected_speakers = [
                    {
                        "id": "narrator",
                        "name": "Narrator",
                        "description": "Main narrative voice",
                        "voice_characteristics": "Male, 35 years old, normal pitch, normal pace, clear articulation, warm and engaging narrator voice",
                    }
                ]
                self.update_progress(52, "Using single narrator (detection disabled)")

            # Step 4: Split text into per-speaker segments
            self.update_progress(54, "Splitting text into speaker segments...")

            if job.enable_speaker_detection and len(detected_speakers) > 1:
                if not using_shared:
                    speaker_detector = SpeakerDetector(llm_client)
                else:
                    speaker_detector = SpeakerDetector(llm_client)
                segments = speaker_detector.split_text_into_segments(
                    full_processed_text, detected_speakers
                )
            else:
                segments = [
                    {
                        "text": full_processed_text,
                        "speaker_id": "narrator",
                        "speaker_name": "Narrator",
                        "segment_index": 0,
                    }
                ]

            total_segments = len(segments)
            unique_speakers = list(set(s["speaker_id"] for s in segments))
            self.update_progress(
                56,
                f"Split into {total_segments} segments across {len(unique_speakers)} speakers",
            )

            # Step 5: Generate voices (skip if shared from batch)
            if using_shared:
                speaker_synthesizers = shared_synthesizers
                self.update_progress(
                    70, f"Using {len(speaker_synthesizers)} shared voices"
                )
            else:
                speaker_synthesizers = {}
                speakers_to_generate = [
                    s for s in detected_speakers if s["id"] in unique_speakers
                ]

                for idx, speaker in enumerate(speakers_to_generate):
                    progress = 56 + int((idx / max(len(speakers_to_generate), 1)) * 14)

                    voice_chars = speaker["voice_characteristics"]
                    try:
                        voice_profile = DetailedVoiceProfile.from_natural_language(
                            voice_chars
                        )
                        enhanced_instruction = voice_profile.to_instruction()
                        logger.info(
                            f"Voice for {speaker['name']}: {enhanced_instruction}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to parse voice profile, using original: {e}"
                        )
                        enhanced_instruction = voice_chars

                    self.update_progress(
                        progress,
                        f"Generating voice {idx + 1}/{len(speakers_to_generate)}: {speaker['name']}\n"
                        f"Voice: {enhanced_instruction}",
                    )

                    voice_config = VoiceConfig(
                        design_text=f"Hello, I am {speaker['name']}.",
                        design_instruct=enhanced_instruction,
                        device=self.tts_device,
                        dtype=self.tts_dtype,
                    )

                    synthesizer = TTSSynthesizer(voice_config=voice_config)
                    ref_path = (
                        job_output_dir / "segments" / f"voice_{speaker['id']}.wav"
                    )
                    ref_path.parent.mkdir(parents=True, exist_ok=True)
                    synthesizer.create_voice(output_path=str(ref_path))
                    synthesizer.prepare_voice_clone()
                    speaker_synthesizers[speaker["id"]] = synthesizer

                self.update_progress(
                    70, f"Generated {len(speaker_synthesizers)} unique voices"
                )

            # Step 6: Synthesize each segment
            self.update_progress(71, "Synthesizing audio segments...")

            audio_files = []
            for idx, segment in enumerate(segments):
                progress = 71 + int((idx / max(total_segments, 1)) * 24)

                speaker_id = segment["speaker_id"]
                speaker_name = segment["speaker_name"]
                text_preview = (
                    segment["text"][:60] + "..."
                    if len(segment["text"]) > 60
                    else segment["text"]
                )

                self.update_progress(
                    progress,
                    f"Synthesizing segment {idx + 1}/{total_segments}\n"
                    f"Speaker: {speaker_name}\n"
                    f"Text: {text_preview}",
                )

                synthesizer = speaker_synthesizers.get(speaker_id)
                if not synthesizer:
                    logger.warning(
                        f"No synthesizer for speaker '{speaker_id}', using narrator"
                    )
                    synthesizer = speaker_synthesizers.get("narrator")

                if not synthesizer:
                    logger.error(f"No synthesizer available for segment {idx}")
                    continue

                output_path = job_output_dir / "segments" / f"segment_{idx:04d}.wav"
                output_path.parent.mkdir(parents=True, exist_ok=True)

                wavs, sr = synthesizer.synthesize(
                    text=segment["text"],
                    output_path=str(output_path),
                )
                audio_files.append(str(output_path))

            self.update_progress(95, "Combining audio into MP3...")

            # Step 7: Combine audio
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

            # Only cleanup synthesizers if we own them (not shared)
            if not using_shared:
                for synth in speaker_synthesizers.values():
                    synth.cleanup()

            if job.webhook_url:
                self.send_webhook(job.webhook_url, job_id, "completed")

        except Exception as e:
            error_msg = f"Job failed: {str(e)}\n{traceback.format_exc()}"
            logger.error(f"Job {job_id} failed: {error_msg}")

            self.job_queue.update_job_status(
                job_id,
                JobStatus.FAILED,
                progress_message=f"Failed: {str(e)}",
                error_message=error_msg,
            )

            if job.webhook_url:
                self.send_webhook(job.webhook_url, job_id, "failed")

        finally:
            self.current_job_id = None

    def process_batch_job(self, parent_job_id: str):
        """
        Process a batch (book) job: detect all characters across the entire book,
        create consistent voices, then process each chapter with shared voices.
        Exports a characters.json manifest with the audio.
        """
        self.current_job_id = parent_job_id
        logger.info(f"Processing batch job: {parent_job_id}")

        parent_job = self.job_queue.get_job(parent_job_id)
        if not parent_job:
            logger.error(f"Batch job not found: {parent_job_id}")
            return

        self.job_queue.update_job_status(
            parent_job_id,
            JobStatus.PROCESSING,
            progress=0,
            progress_message="Starting batch processing...",
        )

        speaker_synthesizers = {}

        try:
            from .text_processor import TextProcessor
            from .llm_client import LLMClient
            from .speaker_detector import SpeakerDetector
            from .tts_synthesizer import TTSSynthesizer, VoiceConfig

            children = self.job_queue.get_child_jobs(parent_job_id)
            total_chapters = len(children)

            if total_chapters == 0:
                raise RuntimeError("Batch job has no chapters")

            # --- Phase 1: Unified speaker detection across the whole book ---
            self.job_queue.update_job_status(
                parent_job_id,
                JobStatus.PROCESSING,
                progress=2,
                progress_message="Analyzing entire book for characters...",
            )

            # Combine text from all chapters (limit to first 100k chars for detection)
            combined_text = ""
            for child in children:
                combined_text += f"\n\n--- {child.title} ---\n\n{child.input_text}"

            # Detect speakers from combined book text
            llm_client = LLMClient(
                provider=self.llm_provider,
                model=self.llm_model,
                base_url=self.llm_base_url,
                api_key=self.llm_api_key,
            )

            detected_speakers = []
            if parent_job.enable_speaker_detection:
                speaker_detector = SpeakerDetector(llm_client)
                detected_speakers = speaker_detector.detect_speakers(
                    combined_text[:100000]
                )
                speaker_names = [s["name"] for s in detected_speakers]
                logger.info(
                    f"Batch: detected {len(detected_speakers)} speakers across book: {speaker_names}"
                )
                self.job_queue.update_job_status(
                    parent_job_id,
                    JobStatus.PROCESSING,
                    progress=5,
                    progress_message=f"Found {len(detected_speakers)} characters: {', '.join(speaker_names)}",
                )
            else:
                detected_speakers = [
                    {
                        "id": "narrator",
                        "name": "Narrator",
                        "description": "Main narrative voice",
                        "voice_characteristics": "Male, 35 years old, normal pitch, normal pace, clear articulation, warm and engaging narrator voice",
                    }
                ]
                self.job_queue.update_job_status(
                    parent_job_id,
                    JobStatus.PROCESSING,
                    progress=5,
                    progress_message="Using single narrator (detection disabled)",
                )

            # --- Phase 2: Create voices for all characters ---
            batch_output_dir = self.output_base_dir / parent_job_id
            batch_output_dir.mkdir(parents=True, exist_ok=True)
            voices_dir = batch_output_dir / "voices"
            voices_dir.mkdir(parents=True, exist_ok=True)

            for idx, speaker in enumerate(detected_speakers):
                progress = 5 + int((idx / max(len(detected_speakers), 1)) * 10)

                voice_chars = speaker["voice_characteristics"]
                try:
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

                self.job_queue.update_job_status(
                    parent_job_id,
                    JobStatus.PROCESSING,
                    progress=progress,
                    progress_message=f"Creating voice {idx + 1}/{len(detected_speakers)}: {speaker['name']}",
                )

                voice_config = VoiceConfig(
                    design_text=f"Hello, I am {speaker['name']}.",
                    design_instruct=enhanced_instruction,
                    device=self.tts_device,
                    dtype=self.tts_dtype,
                )

                synthesizer = TTSSynthesizer(voice_config=voice_config)
                ref_path = voices_dir / f"voice_{speaker['id']}.wav"
                synthesizer.create_voice(output_path=str(ref_path))
                synthesizer.prepare_voice_clone()
                speaker_synthesizers[speaker["id"]] = synthesizer

            self.job_queue.update_job_status(
                parent_job_id,
                JobStatus.PROCESSING,
                progress=15,
                progress_message=f"Created {len(speaker_synthesizers)} character voices. Processing chapters...",
            )

            # --- Phase 3: Process each chapter with shared voices ---
            for idx, child in enumerate(children):
                chapter_num = idx + 1
                logger.info(
                    f"Batch {parent_job_id}: chapter {chapter_num}/{total_chapters} ({child.title})"
                )

                # Parent progress: chapters span from 15% to 95%
                chapter_progress = 15 + int((idx / total_chapters) * 80)
                self.job_queue.update_job_status(
                    parent_job_id,
                    JobStatus.PROCESSING,
                    progress=chapter_progress,
                    progress_message=f"Chapter {chapter_num}/{total_chapters}: {child.title}",
                )

                # Process child with shared voices and speakers
                self.process_job(
                    child.job_id,
                    shared_synthesizers=speaker_synthesizers,
                    shared_speakers=detected_speakers,
                )

                # Check result
                child_result = self.job_queue.get_job(child.job_id)
                if child_result and child_result.status == JobStatus.FAILED:
                    raise RuntimeError(
                        f"Chapter {chapter_num} ({child.title}) failed: {child_result.error_message}"
                    )

            # --- Phase 4: Export character manifest ---
            characters_manifest = {
                "book_title": parent_job.title,
                "total_chapters": total_chapters,
                "characters": [],
            }
            for speaker in detected_speakers:
                char_info = {
                    "id": speaker["id"],
                    "name": speaker["name"],
                    "description": speaker.get("description", ""),
                    "voice_characteristics": speaker.get("voice_characteristics", ""),
                    "voice_reference_file": f"voices/voice_{speaker['id']}.wav",
                }
                characters_manifest["characters"].append(char_info)

            manifest_path = batch_output_dir / "characters.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(characters_manifest, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved character manifest to {manifest_path}")

            # All chapters done
            self.job_queue.update_job_status(
                parent_job_id,
                JobStatus.COMPLETED,
                progress=100,
                progress_message=f"All {total_chapters} chapters completed",
                output_path=str(batch_output_dir),
            )

            logger.info(f"Batch job completed: {parent_job_id}")

            if parent_job.webhook_url:
                self.send_webhook(parent_job.webhook_url, parent_job_id, "completed")

        except Exception as e:
            error_msg = f"Batch job failed: {str(e)}\n{traceback.format_exc()}"
            logger.error(f"Batch job {parent_job_id} failed: {error_msg}")

            self.job_queue.update_job_status(
                parent_job_id,
                JobStatus.FAILED,
                progress_message=f"Failed: {str(e)}",
                error_message=error_msg,
            )

            if parent_job.webhook_url:
                self.send_webhook(parent_job.webhook_url, parent_job_id, "failed")

        finally:
            # Cleanup shared synthesizers
            for synth in speaker_synthesizers.values():
                synth.cleanup()
            self.current_job_id = None

    def run(self):
        """Run the worker loop."""
        self.running = True
        logger.info("Worker started")

        while self.running:
            try:
                # Get next pending job (parent-level only, children are excluded from queue)
                job = self.job_queue.get_next_pending_job()

                if job:
                    if job.is_batch:
                        self.process_batch_job(job.job_id)
                    else:
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

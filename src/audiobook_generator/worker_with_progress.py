"""Background worker with detailed progress reporting."""

import json
import logging
import re
import time
import requests
import threading
import concurrent.futures
from pathlib import Path
from typing import Optional, Dict, List
import traceback
from datetime import datetime

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
        llm_base_url: str = "http://localhost:11434/v1",
        llm_api_key: Optional[str] = None,
        tts_device: str = "cuda:0",
        tts_dtype: str = "bfloat16",
        poll_interval: int = 5,
        # Stuck detection and retry settings
        job_timeout: int = 1800,  # 30 minutes
        heartbeat_interval: int = 30,  # 30 seconds
        stuck_threshold: int = 120,  # 2 minutes
        max_retries: int = 3,
        tts_operation_timeout: int = 300,  # 5 minutes
        recover_stale_jobs: bool = True,
        # Backward compat
        ollama_model: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
    ):
        self.job_queue = job_queue
        self.output_base_dir = Path(output_base_dir)
        self.output_base_dir.mkdir(parents=True, exist_ok=True)

        self.llm_provider = llm_provider
        self.llm_model = ollama_model or llm_model
        self.llm_base_url = ollama_base_url or llm_base_url
        self.llm_api_key = llm_api_key
        self.tts_device = tts_device
        self.tts_dtype = tts_dtype
        self.poll_interval = poll_interval

        # Stuck detection and retry settings
        self.job_timeout = job_timeout
        self.heartbeat_interval = heartbeat_interval
        self.stuck_threshold = stuck_threshold
        self.max_retries = max_retries
        self.tts_operation_timeout = tts_operation_timeout
        self.recover_stale_jobs = recover_stale_jobs

        self.running = False
        self.current_job_id = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop_event = threading.Event()
        self._job_start_time: Optional[float] = None

        logger.info(
            f"AudiobookWorkerWithProgress initialized (LLM: {self.llm_provider}/{self.llm_model})"
        )
        logger.info(
            f"Stuck detection: timeout={self.job_timeout}s, heartbeat={self.heartbeat_interval}s, "
            f"stuck_threshold={self.stuck_threshold}s, max_retries={self.max_retries}"
        )

    def _start_heartbeat(self, job_id: str):
        """Start the heartbeat thread for a job."""
        self._heartbeat_stop_event.clear()
        self._job_start_time = time.time()

        def heartbeat_loop():
            while not self._heartbeat_stop_event.is_set():
                try:
                    self.job_queue.update_heartbeat(job_id)
                    logger.debug(f"Heartbeat sent for job {job_id}")
                except Exception as e:
                    logger.warning(f"Failed to send heartbeat for job {job_id}: {e}")

                # Check job timeout
                if self._job_start_time:
                    elapsed = time.time() - self._job_start_time
                    if elapsed > self.job_timeout:
                        logger.error(
                            f"Job {job_id} exceeded timeout of {self.job_timeout}s "
                            f"(elapsed: {elapsed:.1f}s)"
                        )
                        # The main thread will handle the timeout

                self._heartbeat_stop_event.wait(self.heartbeat_interval)

        self._heartbeat_thread = threading.Thread(
            target=heartbeat_loop, daemon=True, name=f"heartbeat-{job_id}"
        )
        self._heartbeat_thread.start()
        logger.debug(f"Started heartbeat thread for job {job_id}")

    def _stop_heartbeat(self):
        """Stop the heartbeat thread."""
        self._heartbeat_stop_event.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2)
        self._heartbeat_thread = None
        self._job_start_time = None
        logger.debug("Stopped heartbeat thread")

    def _check_job_timeout(self) -> bool:
        """Check if the current job has exceeded its timeout."""
        if self._job_start_time:
            elapsed = time.time() - self._job_start_time
            return elapsed > self.job_timeout
        return False

    def _run_with_timeout(self, func, timeout: int, *args, **kwargs):
        """
        Run a function with a timeout. Raises TimeoutError if it takes too long.

        Args:
            func: The function to run
            timeout: Timeout in seconds
            *args, **kwargs: Arguments to pass to the function

        Returns:
            The function's return value

        Raises:
            TimeoutError: If the function times out
            Exception: Any exception raised by the function
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(f"Operation timed out after {timeout} seconds")

    def update_progress(
        self, progress: int, message: str, details: Optional[dict] = None
    ):
        """Update job progress with detailed message."""
        if self.current_job_id:
            update_data = {
                "progress": progress,
                "progress_message": message,
            }
            if details:
                update_data["progress_details"] = json.dumps(details)

            self.job_queue.update_job_status(
                self.current_job_id, JobStatus.PROCESSING, **update_data
            )
            # Also update heartbeat on progress updates
            self.job_queue.update_heartbeat(self.current_job_id)
            logger.info(f"Progress {progress}%: {message}")

    def send_webhook(self, webhook_url: str, job_id: str, status: str):
        """Send webhook notification."""
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

    # =========================================================================
    # Phase 1: Text processing + speaker detection → AWAITING_REVIEW
    # =========================================================================

    def _run_text_processing(self, job, job_output_dir):
        """Run text processing and speaker detection. Returns (processed_text, detected_speakers)."""
        from .text_processor import TextProcessor
        from .llm_client import LLMClient
        from .speaker_detector import SpeakerDetector

        input_file = job_output_dir / "input.txt"
        with open(input_file, "w", encoding="utf-8") as f:
            f.write(job.input_text)

        text_processor = TextProcessor(max_chars=16000)

        self.update_progress(10, "Reading and batching text...")
        batches = text_processor.process_file(str(input_file))
        total_batches = len(batches)
        self.update_progress(15, f"Created {total_batches} text batches")

        # LLM processing
        processed_texts = []
        llm_client = LLMClient(
            provider=self.llm_provider,
            model=self.llm_model,
            base_url=self.llm_base_url,
            api_key=self.llm_api_key,
        )

        if job.enable_text_processing:
            for idx, batch in enumerate(batches):
                progress = 15 + int((idx / total_batches) * 20)
                self.update_progress(
                    progress,
                    f"Processing batch {idx + 1}/{total_batches} through LLM...",
                )
                result = llm_client.process_text(
                    text=batch.text, batch_index=batch.batch_index
                )
                if len(result.processed_text) < len(batch.text) * 0.5:
                    logger.warning(f"LLM returned much shorter text, using original")
                    processed_texts.append(batch.text)
                else:
                    processed_texts.append(result.processed_text)
            self.update_progress(
                35, f"Text processing complete ({total_batches} batches)"
            )
        else:
            processed_texts = [batch.text for batch in batches]
            self.update_progress(35, "Skipped text processing")

        full_processed_text = " ".join(processed_texts)

        # Save processed text for phase 2
        processed_file = job_output_dir / "processed_text.txt"
        with open(processed_file, "w", encoding="utf-8") as f:
            f.write(full_processed_text)

        # Speaker detection
        if job.enable_speaker_detection:
            self.update_progress(38, "Detecting speakers...")
            speaker_detector = SpeakerDetector(llm_client)
            detected_speakers = speaker_detector.detect_speakers(full_processed_text)
            speaker_names = [s["name"] for s in detected_speakers]
            self.update_progress(
                45,
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
            self.update_progress(45, "Using single narrator (detection disabled)")

        return detected_speakers

    def process_job_phase1(self, job_id: str):
        """
        Phase 1: Text processing + speaker detection.
        Saves detected characters and pauses at AWAITING_REVIEW for user to review/edit.
        """
        self.current_job_id = job_id
        logger.info(f"Processing job phase 1: {job_id}")

        job = self.job_queue.get_job(job_id)
        if not job:
            logger.error(f"Job not found: {job_id}")
            return

        self.update_progress(0, "Initializing...")

        try:
            job_output_dir = self.output_base_dir / job_id
            job_output_dir.mkdir(parents=True, exist_ok=True)

            detected_speakers = self._run_text_processing(job, job_output_dir)

            # Store detected characters in DB and pause for review
            self.job_queue.update_job_status(
                job_id,
                JobStatus.AWAITING_REVIEW,
                progress=50,
                progress_message=f"Review {len(detected_speakers)} detected characters",
                detected_characters=json.dumps(detected_speakers),
            )

            logger.info(
                f"Job {job_id} paused for character review ({len(detected_speakers)} speakers)"
            )

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

    def process_batch_phase1(self, parent_job_id: str):
        """
        Phase 1 for batch jobs: detect all characters across the entire book.
        Saves detected characters on the PARENT job and pauses at AWAITING_REVIEW.
        """
        self.current_job_id = parent_job_id
        logger.info(f"Processing batch phase 1: {parent_job_id}")

        parent_job = self.job_queue.get_job(parent_job_id)
        if not parent_job:
            logger.error(f"Batch job not found: {parent_job_id}")
            return

        self.job_queue.update_job_status(
            parent_job_id,
            JobStatus.PROCESSING,
            progress=0,
            progress_message="Starting batch analysis...",
        )

        try:
            from .llm_client import LLMClient
            from .speaker_detector import SpeakerDetector

            children = self.job_queue.get_child_jobs(parent_job_id)
            total_chapters = len(children)

            if total_chapters == 0:
                raise RuntimeError("Batch job has no chapters")

            self.job_queue.update_job_status(
                parent_job_id,
                JobStatus.PROCESSING,
                progress=2,
                progress_message="Analyzing entire book for characters...",
            )

            # Collect text from all chapters for iterative analysis
            chapter_texts = []
            for child in children:
                chapter_texts.append(f"--- {child.title} ---\n\n{child.input_text}")

            llm_client = LLMClient(
                provider=self.llm_provider,
                model=self.llm_model,
                base_url=self.llm_base_url,
                api_key=self.llm_api_key,
            )

            if parent_job.enable_speaker_detection:
                speaker_detector = SpeakerDetector(llm_client)

                # Use iterative detection to analyze the ENTIRE book
                def progress_callback(batch_num, total_batches, speakers_found):
                    progress = 2 + int((batch_num / total_batches) * 45)  # 2-47%
                    self.job_queue.update_job_status(
                        parent_job_id,
                        JobStatus.PROCESSING,
                        progress=progress,
                        progress_message=f"Analyzing book for characters... (batch {batch_num}/{total_batches}, {speakers_found} found)",
                    )

                detected_speakers = speaker_detector.detect_speakers_iterative(
                    text_chunks=chapter_texts,
                    batch_size_chars=50000,
                    progress_callback=progress_callback,
                )
                speaker_names = [s["name"] for s in detected_speakers]
                logger.info(
                    f"Batch: detected {len(detected_speakers)} speakers across entire book: {speaker_names}"
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

            # Store detected characters and pause for review
            self.job_queue.update_job_status(
                parent_job_id,
                JobStatus.AWAITING_REVIEW,
                progress=50,
                progress_message=f"Review {len(detected_speakers)} detected characters across {total_chapters} chapters",
                detected_characters=json.dumps(detected_speakers),
            )

            logger.info(f"Batch {parent_job_id} paused for character review")

        except Exception as e:
            error_msg = f"Batch phase 1 failed: {str(e)}\n{traceback.format_exc()}"
            logger.error(f"Batch {parent_job_id} failed: {error_msg}")
            self.job_queue.update_job_status(
                parent_job_id,
                JobStatus.FAILED,
                progress_message=f"Failed: {str(e)}",
                error_message=error_msg,
            )
            if parent_job.webhook_url:
                self.send_webhook(parent_job.webhook_url, parent_job_id, "failed")
        finally:
            self.current_job_id = None

    # =========================================================================
    # Phase 2: Voice creation + synthesis → COMPLETED
    # =========================================================================

    def _create_synthesizers_from_characters(
        self, detected_speakers: List[Dict], job_id: str, voices_dir: Path
    ) -> Dict:
        """
        Create synthesizers for each speaker.
        Priority: 1) .pt voice prompt file, 2) .wav voice clone, 3) generate via VoiceDesign.
        """
        from .tts_synthesizer import TTSSynthesizer, VoiceConfig

        voice_clones_dir = self.output_base_dir / job_id / "voice_clones"
        speaker_synthesizers = {}

        for idx, speaker in enumerate(detected_speakers):
            speaker_id = speaker["id"]
            pt_path = voice_clones_dir / f"{speaker_id}.pt"
            clone_path = voice_clones_dir / f"{speaker_id}.wav"

            if pt_path.exists():
                # User uploaded a .pt voice prompt file — load it directly
                logger.info(f"Using .pt voice prompt for {speaker['name']}: {pt_path}")
                voice_config = VoiceConfig(
                    device=self.tts_device,
                    dtype=self.tts_dtype,
                )
                synthesizer = TTSSynthesizer(
                    voice_config=voice_config, use_voice_design=False
                )
                synthesizer.load_voice_prompt(str(pt_path))
            elif clone_path.exists():
                # User uploaded a voice clone — use it directly
                logger.info(
                    f"Using uploaded voice clone for {speaker['name']}: {clone_path}"
                )
                voice_config = VoiceConfig(
                    device=self.tts_device,
                    dtype=self.tts_dtype,
                    reference_audio_path=str(clone_path),
                )
                synthesizer = TTSSynthesizer(
                    voice_config=voice_config, use_voice_design=False
                )
                # Load reference text from file if uploaded, fall back to character data or generic
                ref_text_path = voice_clones_dir / f"{speaker_id}_ref_text.txt"
                if ref_text_path.exists():
                    ref_text = ref_text_path.read_text(encoding="utf-8").strip()
                    logger.info(
                        f"Using uploaded reference text for {speaker['name']}: {ref_text[:80]}..."
                    )
                else:
                    ref_text = speaker.get(
                        "voice_clone_text", "Hello, welcome to this story."
                    )
                synthesizer.prepare_voice_clone(
                    reference_audio=str(clone_path),
                    reference_text=ref_text,
                )
            else:
                # Generate voice from description via VoiceDesign model
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

                voice_config = VoiceConfig(
                    design_text=f"Hello, I am {speaker['name']}.",
                    design_instruct=enhanced_instruction,
                    device=self.tts_device,
                    dtype=self.tts_dtype,
                )

                synthesizer = TTSSynthesizer(voice_config=voice_config)
                ref_path = voices_dir / f"voice_{speaker_id}.wav"
                ref_path.parent.mkdir(parents=True, exist_ok=True)
                synthesizer.create_voice(output_path=str(ref_path))
                synthesizer.prepare_voice_clone()

            speaker_synthesizers[speaker_id] = synthesizer

        return speaker_synthesizers

    def process_job_phase2(
        self,
        job_id: str,
        shared_synthesizers: Optional[Dict] = None,
        shared_speakers: Optional[List] = None,
    ):
        """
        Phase 2: Voice creation + synthesis + combining.
        Uses the (possibly edited) detected_characters from DB.
        """
        self.current_job_id = job_id
        logger.info(f"Processing job phase 2: {job_id}")

        job = self.job_queue.get_job(job_id)
        if not job:
            logger.error(f"Job not found: {job_id}")
            return

        self.job_queue.update_job_status(
            job_id,
            JobStatus.PROCESSING,
            progress=50,
            progress_message="Resuming - creating voices...",
        )

        try:
            from .llm_client import LLMClient
            from .speaker_detector import SpeakerDetector
            from .tts_synthesizer import TTSSynthesizer, VoiceConfig
            from .audio_combiner import AudioCombiner

            job_output_dir = self.output_base_dir / job_id

            # Load processed text from phase 1
            processed_file = job_output_dir / "processed_text.txt"
            if processed_file.exists():
                with open(processed_file, "r", encoding="utf-8") as f:
                    full_processed_text = f.read()
            else:
                # Fallback: re-process
                full_processed_text = job.input_text

            # Get characters (possibly edited by user)
            using_shared = (
                shared_synthesizers is not None and shared_speakers is not None
            )

            if using_shared:
                detected_speakers = shared_speakers
                self.update_progress(
                    52, f"Using shared voices ({len(detected_speakers)} speakers)"
                )
            elif job.detected_characters:
                detected_speakers = json.loads(job.detected_characters)
                self.update_progress(
                    52, f"Using {len(detected_speakers)} reviewed characters"
                )
            else:
                detected_speakers = [
                    {
                        "id": "narrator",
                        "name": "Narrator",
                        "description": "Main narrative voice",
                        "voice_characteristics": "Male, 35 years old, normal pitch, normal pace, clear articulation",
                    }
                ]

            # Split text into segments
            self.update_progress(54, "Splitting text into speaker segments...")

            if job.enable_speaker_detection and len(detected_speakers) > 1:
                llm_client = LLMClient(
                    provider=self.llm_provider,
                    model=self.llm_model,
                    base_url=self.llm_base_url,
                    api_key=self.llm_api_key,
                )
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

            # Create voices
            if using_shared:
                speaker_synthesizers = shared_synthesizers
                self.update_progress(
                    70, f"Using {len(speaker_synthesizers)} shared voices"
                )
            else:
                voices_dir = job_output_dir / "voices"
                voices_dir.mkdir(parents=True, exist_ok=True)

                speakers_to_generate = [
                    s for s in detected_speakers if s["id"] in unique_speakers
                ]

                for idx, speaker in enumerate(speakers_to_generate):
                    progress = 56 + int((idx / max(len(speakers_to_generate), 1)) * 14)
                    self.update_progress(
                        progress,
                        f"Creating voice {idx + 1}/{len(speakers_to_generate)}: {speaker['name']}",
                    )

                speaker_synthesizers = self._create_synthesizers_from_characters(
                    speakers_to_generate, job_id, voices_dir
                )

                self.update_progress(70, f"Created {len(speaker_synthesizers)} voices")

            # Synthesize segments
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

            self.job_queue.update_job_status(
                job_id,
                JobStatus.COMPLETED,
                progress=100,
                progress_message="Complete! Audiobook ready for download",
                output_path=str(final_output),
            )

            logger.info(f"Job completed: {job_id}")

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

    def process_batch_phase2(self, parent_job_id: str):
        """
        Phase 2 for batch jobs: create voices from (edited) characters,
        process each chapter with shared voices, export manifest + ZIP.
        """
        self.current_job_id = parent_job_id
        logger.info(f"Processing batch phase 2: {parent_job_id}")

        parent_job = self.job_queue.get_job(parent_job_id)
        if not parent_job:
            logger.error(f"Batch job not found: {parent_job_id}")
            return

        self.job_queue.update_job_status(
            parent_job_id,
            JobStatus.PROCESSING,
            progress=50,
            progress_message="Resuming - creating character voices...",
        )

        speaker_synthesizers = {}

        try:
            children = self.job_queue.get_child_jobs(parent_job_id)
            total_chapters = len(children)

            if total_chapters == 0:
                raise RuntimeError("Batch job has no chapters")

            # Get characters (possibly edited by user)
            if parent_job.detected_characters:
                detected_speakers = json.loads(parent_job.detected_characters)
            else:
                detected_speakers = [
                    {
                        "id": "narrator",
                        "name": "Narrator",
                        "description": "Main narrative voice",
                        "voice_characteristics": "Male, 35 years old, normal pitch, normal pace, clear articulation",
                    }
                ]

            # Create voices
            batch_output_dir = self.output_base_dir / parent_job_id
            batch_output_dir.mkdir(parents=True, exist_ok=True)
            voices_dir = batch_output_dir / "voices"
            voices_dir.mkdir(parents=True, exist_ok=True)

            for idx, speaker in enumerate(detected_speakers):
                progress = 5 + int((idx / max(len(detected_speakers), 1)) * 10)
                self.job_queue.update_job_status(
                    parent_job_id,
                    JobStatus.PROCESSING,
                    progress=progress,
                    progress_message=f"Creating voice {idx + 1}/{len(detected_speakers)}: {speaker['name']}",
                )

            speaker_synthesizers = self._create_synthesizers_from_characters(
                detected_speakers, parent_job_id, voices_dir
            )

            self.job_queue.update_job_status(
                parent_job_id,
                JobStatus.PROCESSING,
                progress=15,
                progress_message=f"Created {len(speaker_synthesizers)} character voices. Processing chapters...",
            )

            # Process each chapter with shared voices
            for idx, child in enumerate(children):
                chapter_num = idx + 1
                logger.info(
                    f"Batch {parent_job_id}: chapter {chapter_num}/{total_chapters} ({child.title})"
                )

                chapter_progress = 15 + int((idx / total_chapters) * 80)
                self.job_queue.update_job_status(
                    parent_job_id,
                    JobStatus.PROCESSING,
                    progress=chapter_progress,
                    progress_message=f"Chapter {chapter_num}/{total_chapters}: {child.title}",
                )

                # For batch children, run phase1 inline (text processing) then phase2 with shared voices
                # Phase 1 for child: text processing only
                child_job = self.job_queue.get_job(child.job_id)
                child_output_dir = self.output_base_dir / child.job_id
                child_output_dir.mkdir(parents=True, exist_ok=True)

                self.current_job_id = child.job_id
                self.job_queue.update_job_status(
                    child.job_id,
                    JobStatus.PROCESSING,
                    progress=0,
                    progress_message="Starting chapter processing...",
                )

                # Run phase 2 directly with shared synthesizers
                self.process_job_phase2(
                    child.job_id,
                    shared_synthesizers=speaker_synthesizers,
                    shared_speakers=detected_speakers,
                )

                self.current_job_id = parent_job_id

                # Check result
                child_result = self.job_queue.get_job(child.job_id)
                if child_result and child_result.status == JobStatus.FAILED:
                    raise RuntimeError(
                        f"Chapter {chapter_num} ({child.title}) failed: {child_result.error_message}"
                    )

            # Export character manifest
            characters_manifest = {
                "book_title": parent_job.title,
                "total_chapters": total_chapters,
                "characters": [],
            }
            for speaker in detected_speakers:
                clone_path = (
                    self.output_base_dir
                    / parent_job_id
                    / "voice_clones"
                    / f"{speaker['id']}.wav"
                )
                char_info = {
                    "id": speaker["id"],
                    "name": speaker["name"],
                    "description": speaker.get("description", ""),
                    "voice_characteristics": speaker.get("voice_characteristics", ""),
                    "voice_source": "clone" if clone_path.exists() else "generated",
                    "voice_reference_file": f"voices/voice_{speaker['id']}.wav",
                }
                characters_manifest["characters"].append(char_info)

            manifest_path = batch_output_dir / "characters.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(characters_manifest, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved character manifest to {manifest_path}")

            # Combine all chapter audio files into one full audiobook
            self.job_queue.update_job_status(
                parent_job_id,
                JobStatus.PROCESSING,
                progress=96,
                progress_message="Combining all chapters into full audiobook...",
            )

            from .audio_combiner import AudioCombiner

            # Collect all chapter audio files in order
            chapter_audio_files = []
            for child in children:
                child_result = self.job_queue.get_job(child.job_id)
                if (
                    child_result
                    and child_result.output_path
                    and Path(child_result.output_path).exists()
                ):
                    chapter_audio_files.append(child_result.output_path)

            if chapter_audio_files:
                audio_combiner = AudioCombiner(
                    silence_between_segments=1500,  # 1.5 seconds between chapters
                    normalize_audio=True,
                    target_format="mp3",
                    bitrate="192k",
                )

                # Generate combined audiobook filename
                safe_title = re.sub(
                    r'[<>:"/\\|?*]', "_", parent_job.title or "audiobook"
                )
                combined_output_filename = f"{safe_title}_complete.mp3"
                combined_output_path = batch_output_dir / combined_output_filename

                audio_combiner.combine_wav_files(
                    input_files=chapter_audio_files,
                    output_path=str(combined_output_path),
                )

                logger.info(
                    f"Combined {len(chapter_audio_files)} chapters into {combined_output_path}"
                )

                # Update parent job output path to point to combined audiobook
                self.job_queue.update_job_status(
                    parent_job_id,
                    JobStatus.COMPLETED,
                    progress=100,
                    progress_message=f"All {total_chapters} chapters completed + full audiobook generated",
                    output_path=str(combined_output_path),
                    output_filename=combined_output_filename,
                )
            else:
                logger.warning("No chapter audio files found for combining")
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
            for synth in speaker_synthesizers.values():
                synth.cleanup()
            self.current_job_id = None

    # =========================================================================
    # Legacy single-call methods (kept for backward compat / batch children)
    # =========================================================================

    def process_job(
        self,
        job_id: str,
        shared_synthesizers: Optional[Dict] = None,
        shared_speakers: Optional[List] = None,
    ):
        """Full single-pass processing (used for batch children with shared voices)."""
        if shared_synthesizers is not None:
            # Batch child: go straight to phase 2 with shared resources
            self.process_job_phase2(job_id, shared_synthesizers, shared_speakers)
        else:
            # Should not reach here in normal flow, but handle gracefully
            self.process_job_phase1(job_id)

    # =========================================================================
    # Worker loop
    # =========================================================================

    def _recover_stale_jobs(self):
        """Recover jobs that were stuck in PROCESSING status from a previous run."""
        if not self.recover_stale_jobs:
            return

        stale_jobs = self.job_queue.get_stale_processing_jobs()
        if not stale_jobs:
            return

        logger.info(f"Found {len(stale_jobs)} stale jobs from previous run")

        for job in stale_jobs:
            retry_count = job.retry_count or 0
            max_retries = job.max_retries or self.max_retries

            if retry_count < max_retries:
                # Reset job for retry
                new_retry_count = self.job_queue.increment_retry_count(job.job_id)
                self.job_queue.reset_job_for_retry(job.job_id)
                logger.info(
                    f"Recovered stale job {job.job_id} for retry "
                    f"(attempt {new_retry_count}/{max_retries})"
                )
            else:
                # Max retries exceeded, mark as failed
                self.job_queue.mark_job_stuck(
                    job.job_id,
                    f"Job exceeded maximum retries ({max_retries}) after server restart",
                )
                logger.warning(
                    f"Stale job {job.job_id} exceeded max retries, marked as failed"
                )

    def _check_and_handle_stuck_jobs(self):
        """Check for stuck jobs and handle them (retry or fail)."""
        stuck_jobs = self.job_queue.get_stuck_jobs(self.stuck_threshold)

        for job in stuck_jobs:
            # Don't handle if it's the current job (we're still processing it)
            if job.job_id == self.current_job_id:
                continue

            retry_count = job.retry_count or 0
            max_retries = job.max_retries or self.max_retries

            if retry_count < max_retries:
                # Retry the stuck job
                new_retry_count = self.job_queue.increment_retry_count(job.job_id)
                self.job_queue.reset_job_for_retry(job.job_id)
                logger.warning(
                    f"Detected stuck job {job.job_id}, resetting for retry "
                    f"(attempt {new_retry_count}/{max_retries})"
                )

                if job.webhook_url:
                    self.send_webhook(job.webhook_url, job.job_id, "retrying")
            else:
                # Max retries exceeded
                self.job_queue.mark_job_stuck(
                    job.job_id,
                    f"Job stuck with no heartbeat for {self.stuck_threshold}s "
                    f"and exceeded maximum retries ({max_retries})",
                )
                logger.error(
                    f"Job {job.job_id} stuck and exceeded max retries, marked as failed"
                )

                if job.webhook_url:
                    self.send_webhook(job.webhook_url, job.job_id, "failed")

    def _process_with_heartbeat(self, job, process_func, *args):
        """
        Process a job with heartbeat monitoring and timeout handling.

        Args:
            job: The job to process
            process_func: The processing function to call
            *args: Arguments to pass to process_func
        """
        job_id = job.job_id
        self._start_heartbeat(job_id)

        try:
            process_func(*args)
        except TimeoutError as e:
            # Job timed out
            retry_count = job.retry_count or 0
            max_retries = job.max_retries or self.max_retries

            if retry_count < max_retries:
                new_retry_count = self.job_queue.increment_retry_count(job_id)
                self.job_queue.reset_job_for_retry(job_id)
                logger.warning(
                    f"Job {job_id} timed out, resetting for retry "
                    f"(attempt {new_retry_count}/{max_retries}): {e}"
                )

                if job.webhook_url:
                    self.send_webhook(job.webhook_url, job_id, "retrying")
            else:
                self.job_queue.mark_job_stuck(
                    job_id,
                    f"Job timed out after {self.job_timeout}s and exceeded maximum retries ({max_retries})",
                )
                logger.error(f"Job {job_id} timed out and exceeded max retries")

                if job.webhook_url:
                    self.send_webhook(job.webhook_url, job_id, "failed")
        finally:
            self._stop_heartbeat()

    def run(self):
        """Run the worker loop."""
        self.running = True
        logger.info("Worker started")

        # Recover any stale jobs from previous run
        self._recover_stale_jobs()

        last_stuck_check = time.time()
        stuck_check_interval = 30  # Check for stuck jobs every 30 seconds

        while self.running:
            try:
                # Periodically check for stuck jobs
                if time.time() - last_stuck_check > stuck_check_interval:
                    self._check_and_handle_stuck_jobs()
                    last_stuck_check = time.time()

                # Check for confirmed jobs waiting to resume (AWAITING_REVIEW → confirmed)
                confirmed_job = self.job_queue.get_next_confirmed_job()
                if confirmed_job:
                    if confirmed_job.is_batch:
                        self._process_with_heartbeat(
                            confirmed_job,
                            self.process_batch_phase2,
                            confirmed_job.job_id,
                        )
                    else:
                        self._process_with_heartbeat(
                            confirmed_job, self.process_job_phase2, confirmed_job.job_id
                        )
                    continue

                # Check for new pending jobs
                job = self.job_queue.get_next_pending_job()
                if job:
                    if job.is_batch:
                        self._process_with_heartbeat(
                            job, self.process_batch_phase1, job.job_id
                        )
                    else:
                        self._process_with_heartbeat(
                            job, self.process_job_phase1, job.job_id
                        )
                else:
                    time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                logger.info("Worker interrupted by user")
                self.running = False
                self._stop_heartbeat()
                break

            except Exception as e:
                logger.error(f"Worker error: {e}")
                self._stop_heartbeat()
                time.sleep(self.poll_interval)

        logger.info("Worker stopped")

    def stop(self):
        """Stop the worker."""
        self.running = False

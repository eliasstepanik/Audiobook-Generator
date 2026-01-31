"""Background worker for processing audiobook jobs."""

import logging
import time
import requests
from pathlib import Path
from typing import Optional
import traceback

from .job_queue import JobQueue
from .models import JobStatus
from .multi_speaker_generator import MultiSpeakerAudiobookGenerator

logger = logging.getLogger(__name__)


class AudiobookWorker:
    """Background worker that processes jobs from the queue."""

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
    ):
        """
        Initialize worker.

        Args:
            job_queue: Job queue instance
            output_base_dir: Base directory for output files
            llm_provider: LLM provider (ollama, openai, anthropic)
            llm_model: Model name for the provider
            llm_base_url: API base URL
            llm_api_key: API key (required for openai/anthropic)
            tts_device: TTS device
            tts_dtype: TTS dtype
            poll_interval: Seconds to wait between polling for jobs
        """
        self.job_queue = job_queue
        self.output_base_dir = Path(output_base_dir)
        self.output_base_dir.mkdir(parents=True, exist_ok=True)

        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.llm_base_url = llm_base_url
        self.llm_api_key = llm_api_key
        self.tts_device = tts_device
        self.tts_dtype = tts_dtype
        self.poll_interval = poll_interval

        self.running = False

        logger.info("AudiobookWorker initialized")

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
        Process a single job.

        Args:
            job_id: Job ID to process
        """
        logger.info(f"Processing job: {job_id}")

        # Get job details
        job = self.job_queue.get_job(job_id)
        if not job:
            logger.error(f"Job not found: {job_id}")
            return

        # Update status to processing
        self.job_queue.update_job_status(job_id, JobStatus.PROCESSING, progress=0)

        try:
            # Create output directory for this job
            job_output_dir = self.output_base_dir / job_id
            job_output_dir.mkdir(parents=True, exist_ok=True)

            # Save input text to file
            input_file = job_output_dir / "input.txt"
            with open(input_file, "w", encoding="utf-8") as f:
                f.write(job.input_text)

            # Initialize generator
            generator = MultiSpeakerAudiobookGenerator(
                llm_provider=self.llm_provider,
                llm_model=self.llm_model,
                llm_base_url=self.llm_base_url,
                llm_api_key=self.llm_api_key,
                tts_device=self.tts_device,
                tts_dtype=self.tts_dtype,
                enable_text_processing=job.enable_text_processing,
                enable_speaker_detection=job.enable_speaker_detection,
            )

            # Update progress
            self.job_queue.update_job_status(job_id, JobStatus.PROCESSING, progress=10)

            # Generate audiobook
            metadata = generator.generate(
                input_file=str(input_file),
                output_dir=str(job_output_dir),
                output_filename=job.output_filename,
                save_intermediate=True,
                tts_batch_size=5,
            )

            # Final output path
            output_path = job_output_dir / job.output_filename

            # Update job as completed
            self.job_queue.update_job_status(
                job_id,
                JobStatus.COMPLETED,
                progress=100,
                output_path=str(output_path),
                metadata=metadata,
            )

            logger.info(f"Job completed: {job_id}")

            # Send webhook if configured
            if job.webhook_url:
                self.send_webhook(job.webhook_url, job_id, "completed")

        except Exception as e:
            error_msg = f"Job failed: {str(e)}\n{traceback.format_exc()}"
            logger.error(f"Job {job_id} failed: {error_msg}")

            # Update job as failed
            self.job_queue.update_job_status(
                job_id, JobStatus.FAILED, error_message=error_msg
            )

            # Send webhook if configured
            if job.webhook_url:
                self.send_webhook(job.webhook_url, job_id, "failed")

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

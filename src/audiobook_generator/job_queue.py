"""Job queue management."""

from typing import Optional, List
from pathlib import Path
import uuid
import json
import logging
from datetime import datetime

from .models import AudiobookJob, JobStatus
from .database import Database

logger = logging.getLogger(__name__)


class JobQueue:
    """Manages audiobook generation jobs."""

    def __init__(self, database: Database):
        """
        Initialize job queue.

        Args:
            database: Database instance
        """
        self.database = database

    def create_job(
        self,
        input_text: str,
        title: Optional[str] = None,
        input_filename: Optional[str] = None,
        enable_text_processing: bool = True,
        enable_speaker_detection: bool = True,
        output_filename: str = "audiobook.mp3",
        webhook_url: Optional[str] = None,
    ) -> dict:
        """
        Create a new job.

        Args:
            input_text: Text content to convert
            title: Audiobook title (optional, defaults to "Untitled Audiobook")
            input_filename: Original filename (optional)
            enable_text_processing: Whether to use Ollama processing
            enable_speaker_detection: Whether to detect multiple speakers
            output_filename: Name for output file
            webhook_url: URL to call when job completes

        Returns:
            Created job
        """
        job_id = str(uuid.uuid4())

        # Use title or generate from filename or default
        if not title:
            if input_filename:
                # Extract title from filename (remove extension)
                title = Path(input_filename).stem
            else:
                title = "Untitled Audiobook"

        with self.database.get_session() as session:
            job = AudiobookJob(
                job_id=job_id,
                input_text=input_text,
                title=title,
                input_filename=input_filename,
                enable_text_processing=enable_text_processing,
                enable_speaker_detection=enable_speaker_detection,
                output_filename=output_filename,
                webhook_url=webhook_url,
                status=JobStatus.PENDING,
            )

            session.add(job)
            session.commit()
            session.refresh(job)

            logger.info(f"Created job: {job_id}")

            # Make a detached copy to return
            job_dict = job.to_dict()

        # Return dict instead of session-bound object
        return job_dict

    def get_job(self, job_id: str) -> Optional[AudiobookJob]:
        """
        Get job by ID.

        Args:
            job_id: Job ID

        Returns:
            Job or None if not found
        """
        with self.database.get_session() as session:
            job = (
                session.query(AudiobookJob)
                .filter(AudiobookJob.job_id == job_id)
                .first()
            )

            if job:
                session.expunge(job)

            return job

    def get_next_pending_job(self) -> Optional[AudiobookJob]:
        """
        Get next pending top-level job from queue (excludes child jobs).

        Returns:
            Next pending job or None
        """
        with self.database.get_session() as session:
            job = (
                session.query(AudiobookJob)
                .filter(AudiobookJob.status == JobStatus.PENDING)
                .filter(AudiobookJob.parent_job_id == None)
                .order_by(AudiobookJob.created_at)
                .first()
            )

            if job:
                session.expunge(job)

            return job

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: Optional[int] = None,
        progress_message: Optional[str] = None,
        progress_details: Optional[str] = None,  # JSON string
        error_message: Optional[str] = None,
        output_path: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        """
        Update job status.

        Args:
            job_id: Job ID
            status: New status
            progress: Progress percentage (0-100)
            progress_message: Simple progress message
            progress_details: Detailed progress JSON string
            error_message: Error message if failed
            output_path: Path to output file
            metadata: Job metadata
        """
        with self.database.get_session() as session:
            job = (
                session.query(AudiobookJob)
                .filter(AudiobookJob.job_id == job_id)
                .first()
            )

            if not job:
                logger.warning(f"Job not found: {job_id}")
                return

            job.status = status

            if progress is not None:
                job.progress = progress

            if progress_message is not None:
                job.progress_message = progress_message

            if progress_details is not None:
                job.progress_details = progress_details

            if error_message:
                job.error_message = error_message

            if output_path:
                job.output_path = output_path

            if metadata:
                job.job_metadata = json.dumps(metadata)

            # Update timestamps
            if status == JobStatus.PROCESSING and not job.started_at:
                job.started_at = datetime.utcnow()

            if status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                job.completed_at = datetime.utcnow()
                job.progress = 100 if status == JobStatus.COMPLETED else job.progress

            session.commit()

            logger.info(f"Updated job {job_id}: {status} ({progress}%)")

    def delete_job(self, job_id: str) -> bool:
        """
        Delete job.

        Args:
            job_id: Job ID

        Returns:
            True if deleted, False if not found
        """
        with self.database.get_session() as session:
            job = (
                session.query(AudiobookJob)
                .filter(AudiobookJob.job_id == job_id)
                .first()
            )

            if not job:
                return False

            session.delete(job)
            session.commit()

            logger.info(f"Deleted job: {job_id}")

            return True

    def get_job_count(self, status: Optional[JobStatus] = None) -> int:
        """
        Get total number of jobs (excludes child jobs from count).

        Args:
            status: Filter by status

        Returns:
            Job count
        """
        with self.database.get_session() as session:
            query = session.query(AudiobookJob).filter(
                AudiobookJob.parent_job_id == None
            )

            if status:
                query = query.filter(AudiobookJob.status == status)

            return query.count()

    def create_batch_job(
        self,
        title: str,
        chapters: list,
        enable_text_processing: bool = True,
        enable_speaker_detection: bool = True,
        webhook_url: Optional[str] = None,
    ) -> dict:
        """
        Create a batch parent job with chapter child jobs.

        Args:
            title: Book title
            chapters: List of dicts with 'filename' and 'text' keys, sorted by chapter order
            enable_text_processing: Whether to use LLM processing
            enable_speaker_detection: Whether to detect multiple speakers
            webhook_url: URL to call when batch completes

        Returns:
            Parent job dict with child_jobs list
        """
        parent_id = str(uuid.uuid4())

        with self.database.get_session() as session:
            # Create parent batch job (input_text stores chapter count info)
            parent_job = AudiobookJob(
                job_id=parent_id,
                input_text=f"[Batch job: {len(chapters)} chapters]",
                title=title,
                input_filename=None,
                is_batch=True,
                enable_text_processing=enable_text_processing,
                enable_speaker_detection=enable_speaker_detection,
                output_filename=f"{title}.zip",
                webhook_url=webhook_url,
                status=JobStatus.PENDING,
            )
            session.add(parent_job)

            child_jobs = []
            for idx, chapter in enumerate(chapters):
                child_id = str(uuid.uuid4())
                child_job = AudiobookJob(
                    job_id=child_id,
                    input_text=chapter["text"],
                    title=chapter["filename"],
                    input_filename=chapter["filename"],
                    parent_job_id=parent_id,
                    chapter_index=idx,
                    enable_text_processing=enable_text_processing,
                    enable_speaker_detection=enable_speaker_detection,
                    output_filename=Path(chapter["filename"]).stem + ".mp3",
                    status=JobStatus.PENDING,
                )
                session.add(child_job)
                child_jobs.append(child_job)

            session.commit()
            session.refresh(parent_job)
            for cj in child_jobs:
                session.refresh(cj)

            result = parent_job.to_dict()
            result["child_jobs"] = [cj.to_dict() for cj in child_jobs]

            logger.info(f"Created batch job {parent_id} with {len(chapters)} chapters")

        return result

    def get_child_jobs(self, parent_job_id: str) -> List[AudiobookJob]:
        """Get all child jobs for a batch parent, ordered by chapter_index."""
        with self.database.get_session() as session:
            jobs = (
                session.query(AudiobookJob)
                .filter(AudiobookJob.parent_job_id == parent_job_id)
                .order_by(AudiobookJob.chapter_index)
                .all()
            )
            for job in jobs:
                session.expunge(job)
            return jobs

    def get_all_jobs(
        self, status: Optional[JobStatus] = None, limit: int = 100, offset: int = 0
    ) -> List[AudiobookJob]:
        """
        Get all top-level jobs (excludes child jobs).

        Args:
            status: Filter by status
            limit: Maximum number of jobs to return
            offset: Pagination offset

        Returns:
            List of jobs
        """
        with self.database.get_session() as session:
            query = session.query(AudiobookJob).filter(
                AudiobookJob.parent_job_id == None
            )

            if status:
                query = query.filter(AudiobookJob.status == status)

            query = query.order_by(AudiobookJob.created_at.desc())
            query = query.limit(limit).offset(offset)

            jobs = query.all()

            for job in jobs:
                session.expunge(job)

            return jobs

"""Database models for job queue."""

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum

Base = declarative_base()


class JobStatus(str, Enum):
    """Job status enumeration."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AudiobookJob(Base):
    """Database model for audiobook generation jobs."""

    __tablename__ = "audiobook_jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(36), unique=True, index=True, nullable=False)

    # Input
    input_text = Column(Text, nullable=False)
    input_filename = Column(String(255), nullable=True)

    # Audiobook title
    title = Column(String(255), nullable=True, default="Untitled Audiobook")

    # Configuration
    enable_text_processing = Column(Boolean, default=True)
    enable_speaker_detection = Column(Boolean, default=True)
    output_filename = Column(String(255), default="audiobook.mp3")

    # Webhook
    webhook_url = Column(String(512), nullable=True)

    # Status
    status = Column(String(20), default=JobStatus.PENDING, index=True)
    progress = Column(Integer, default=0)
    progress_message = Column(Text, nullable=True)  # Detailed progress info
    error_message = Column(Text, nullable=True)

    # Output
    output_path = Column(String(512), nullable=True)
    job_metadata = Column(
        Text, nullable=True
    )  # JSON - renamed from 'metadata' to avoid SQLAlchemy conflict

    # Detailed progress tracking (JSON)
    progress_details = Column(
        Text, nullable=True
    )  # JSON with batches, speakers, segments

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self):
        """Convert to dictionary."""
        import json

        # Parse progress_details if it's JSON string
        progress_details = None
        if self.progress_details:
            try:
                progress_details = json.loads(self.progress_details)
            except (json.JSONDecodeError, TypeError):
                progress_details = None

        return {
            "job_id": self.job_id,
            "title": self.title,
            "status": self.status,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "progress_details": progress_details,  # Parsed JSON
            "input_filename": self.input_filename,
            "output_filename": self.output_filename,
            "enable_text_processing": self.enable_text_processing,
            "enable_speaker_detection": self.enable_speaker_detection,
            "webhook_url": self.webhook_url,
            "error_message": self.error_message,
            "output_path": self.output_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
        }

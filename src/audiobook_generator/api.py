"""FastAPI REST API for audiobook generation service."""

from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from typing import Optional, List
from pathlib import Path
import logging

from .database import get_database
from .job_queue import JobQueue
from .models import JobStatus

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Audiobook Generator API",
    description="Convert text to audiobooks with multi-speaker support using Ollama and Qwen3-TTS",
    version="0.1.0",
)

# Mount static files
frontend_dir = Path(__file__).parent.parent.parent / "frontend"
if frontend_dir.exists():
    app.mount(
        "/static", StaticFiles(directory=str(frontend_dir / "static")), name="static"
    )

# Initialize database and job queue
database = get_database()
job_queue = JobQueue(database)


# Pydantic models for requests/responses
class CreateJobRequest(BaseModel):
    """Request to create a new audiobook job."""

    text: str
    title: Optional[str] = None
    filename: Optional[str] = None
    enable_text_processing: bool = True
    enable_speaker_detection: bool = True
    output_filename: str = "audiobook.mp3"
    webhook_url: Optional[HttpUrl] = None


class JobResponse(BaseModel):
    """Job information response."""

    job_id: str
    title: Optional[str]
    status: str
    progress: int
    input_filename: Optional[str]
    output_filename: str
    enable_text_processing: bool
    enable_speaker_detection: bool
    webhook_url: Optional[str]
    error_message: Optional[str]
    created_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]


class JobListResponse(BaseModel):
    """List of jobs response."""

    jobs: List[JobResponse]
    total: int
    limit: int
    offset: int


# API Endpoints


@app.get("/", response_class=HTMLResponse)
def root():
    """Serve the web frontend."""
    frontend_dir = Path(__file__).parent.parent.parent / "frontend"
    index_path = frontend_dir / "templates" / "index.html"

    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        # Fallback to API info
        return """
        <html>
            <head><title>Audiobook Generator API</title></head>
            <body>
                <h1>Audiobook Generator API</h1>
                <p>Version: 0.1.0</p>
                <h2>API Documentation</h2>
                <ul>
                    <li><a href="/docs">Swagger UI</a></li>
                    <li><a href="/redoc">ReDoc</a></li>
                </ul>
            </body>
        </html>
        """


@app.get("/api")
def api_info():
    """API information endpoint."""
    return {
        "message": "Audiobook Generator API",
        "version": "0.1.0",
        "endpoints": {
            "POST /jobs": "Create new audiobook job",
            "POST /jobs/upload": "Upload text file and create job",
            "GET /jobs": "List all jobs",
            "GET /jobs/{job_id}": "Get job details",
            "GET /jobs/{job_id}/download": "Download completed audiobook",
            "DELETE /jobs/{job_id}": "Cancel/delete job",
        },
    }


@app.post("/jobs", response_model=JobResponse, status_code=201)
def create_job(request: CreateJobRequest):
    """
    Create a new audiobook generation job.

    The job will be added to the queue and processed in order.
    If a webhook URL is provided, it will be called when the job completes.

    **Webhook Payload:**
    ```json
    {
        "job_id": "uuid",
        "status": "completed",
        "timestamp": 1234567890
    }
    ```
    """
    try:
        job = job_queue.create_job(
            input_text=request.text,
            title=request.title,
            input_filename=request.filename,
            enable_text_processing=request.enable_text_processing,
            enable_speaker_detection=request.enable_speaker_detection,
            output_filename=request.output_filename,
            webhook_url=str(request.webhook_url) if request.webhook_url else None,
        )

        return JobResponse(**job)

    except Exception as e:
        logger.error(f"Failed to create job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/jobs/upload", response_model=JobResponse, status_code=201)
async def create_job_from_file(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    enable_text_processing: bool = Form(True),
    enable_speaker_detection: bool = Form(True),
    output_filename: str = Form("audiobook.mp3"),
    webhook_url: Optional[str] = Form(None),
):
    """
    Upload a text file and create an audiobook generation job.

    Accepts text files (.txt, .md, etc.) and creates a job to process them.
    """
    try:
        # Read file content
        content = await file.read()
        text = content.decode("utf-8")

        # Create job
        job = job_queue.create_job(
            input_text=text,
            title=title,
            input_filename=file.filename,
            enable_text_processing=enable_text_processing,
            enable_speaker_detection=enable_speaker_detection,
            output_filename=output_filename,
            webhook_url=webhook_url,
        )

        return JobResponse(**job)

    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be valid UTF-8 text")
    except Exception as e:
        logger.error(f"Failed to create job from file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs", response_model=JobListResponse)
def list_jobs(status: Optional[str] = None, limit: int = 100, offset: int = 0):
    """
    Get list of all jobs with optional filtering.

    **Parameters:**
    - `status`: Filter by status (pending, processing, completed, failed, cancelled)
    - `limit`: Maximum number of jobs to return (default 100)
    - `offset`: Pagination offset (default 0)
    """
    try:
        # Validate status if provided
        job_status = None
        if status:
            try:
                job_status = JobStatus(status.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status. Must be one of: {', '.join([s.value for s in JobStatus])}",
                )

        # Get jobs
        jobs = job_queue.get_all_jobs(status=job_status, limit=limit, offset=offset)

        total = job_queue.get_job_count(status=job_status)

        return JobListResponse(
            jobs=[JobResponse(**job.to_dict()) for job in jobs],
            total=total,
            limit=limit,
            offset=offset,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    """
    Get details of a specific job.

    **Parameters:**
    - `job_id`: UUID of the job
    """
    job = job_queue.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse(**job.to_dict())


@app.get("/jobs/{job_id}/download")
def download_job(job_id: str):
    """
    Download the completed audiobook file.

    **Parameters:**
    - `job_id`: UUID of the job

    **Returns:** MP3 file download
    """
    job = job_queue.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed. Current status: {job.status}",
        )

    if not job.output_path or not Path(job.output_path).exists():
        raise HTTPException(status_code=404, detail="Output file not found")

    return FileResponse(
        path=job.output_path, media_type="audio/mpeg", filename=job.output_filename
    )


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    """
    Cancel or delete a job.

    **Parameters:**
    - `job_id`: UUID of the job

    **Note:** Jobs that are currently processing cannot be cancelled immediately.
    """
    job = job_queue.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Update status to cancelled if pending/processing
    if job.status in [JobStatus.PENDING, JobStatus.PROCESSING]:
        job_queue.update_job_status(job_id, JobStatus.CANCELLED)
        return {"message": "Job cancelled", "job_id": job_id}

    # Delete completed/failed jobs
    success = job_queue.delete_job(job_id)

    if success:
        return {"message": "Job deleted", "job_id": job_id}
    else:
        raise HTTPException(status_code=500, detail="Failed to delete job")


@app.get("/stats")
def get_stats():
    """
    Get service statistics.

    **Returns:** Statistics about jobs and queue
    """
    try:
        stats = {
            "total_jobs": job_queue.get_job_count(),
            "pending": job_queue.get_job_count(JobStatus.PENDING),
            "processing": job_queue.get_job_count(JobStatus.PROCESSING),
            "completed": job_queue.get_job_count(JobStatus.COMPLETED),
            "failed": job_queue.get_job_count(JobStatus.FAILED),
            "cancelled": job_queue.get_job_count(JobStatus.CANCELLED),
        }

        return stats

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Health check endpoint
@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

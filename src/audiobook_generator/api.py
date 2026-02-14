"""FastAPI REST API for audiobook generation service."""

from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl, field_validator
from typing import Optional, List, Dict, Any
from pathlib import Path
import logging
import zipfile
import io
import json
import re

from .database import get_database
from .job_queue import JobQueue
from .models import JobStatus, VoicePreset
from .config import load_config
import uuid
import shutil

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


# Get config for validation limits
config = load_config()

# Regex for sanitizing filenames (removes dangerous characters)
UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str) -> str:
    """Sanitize a filename by removing unsafe characters."""
    # Remove dangerous characters
    safe = UNSAFE_FILENAME_CHARS.sub("_", name)
    # Collapse multiple underscores
    safe = re.sub(r"_+", "_", safe)
    # Remove leading/trailing underscores and whitespace
    safe = safe.strip("_ ")
    # Limit length
    return safe[:200] if safe else "untitled"


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

    @field_validator("text")
    @classmethod
    def validate_text_length(cls, v: str) -> str:
        """Validate text is not empty and within size limits."""
        if not v or not v.strip():
            raise ValueError("Text cannot be empty")
        max_length = config.security.max_input_length
        if len(v) > max_length:
            raise ValueError(
                f"Text exceeds maximum length of {max_length:,} characters"
            )
        return v

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize title for safe filesystem use."""
        if v is None:
            return None
        return sanitize_filename(v)

    @field_validator("output_filename")
    @classmethod
    def sanitize_output_filename(cls, v: str) -> str:
        """Sanitize output filename for safe filesystem use."""
        sanitized = sanitize_filename(v)
        # Ensure it has .mp3 extension
        if not sanitized.lower().endswith(".mp3"):
            sanitized += ".mp3"
        return sanitized


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
    parent_job_id: Optional[str] = None
    chapter_index: Optional[int] = None
    is_batch: bool = False
    detected_characters: Optional[List[Dict[str, Any]]] = None
    child_jobs: Optional[List["JobResponse"]] = None
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

        job_responses = []
        for job in jobs:
            job_dict = job.to_dict()
            if job.is_batch:
                children = job_queue.get_child_jobs(job.job_id)
                job_dict["child_jobs"] = [c.to_dict() for c in children]
            job_responses.append(JobResponse(**job_dict))

        return JobListResponse(
            jobs=job_responses,
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

    job_dict = job.to_dict()
    if job.is_batch:
        children = job_queue.get_child_jobs(job.job_id)
        job_dict["child_jobs"] = [c.to_dict() for c in children]

    return JobResponse(**job_dict)


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


# =========================================================================
# Character review endpoints
# =========================================================================


@app.get("/jobs/{job_id}/characters")
def get_characters(job_id: str):
    """Get detected characters for a job (available after AWAITING_REVIEW)."""
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.detected_characters:
        raise HTTPException(status_code=400, detail="No characters detected yet")

    characters = json.loads(job.detected_characters)
    # Check which characters have uploaded voice clones and ref_text
    for char in characters:
        clone_dir = Path("./data/output") / job_id / "voice_clones"
        clone_path = clone_dir / f"{char['id']}.wav"
        ref_text_path = clone_dir / f"{char['id']}_ref_text.txt"
        char["has_voice_clone"] = clone_path.exists()
        if ref_text_path.exists():
            char["ref_text"] = ref_text_path.read_text(encoding="utf-8")
        elif "ref_text" not in char:
            char["ref_text"] = ""

    return {"job_id": job_id, "characters": characters}


@app.put("/jobs/{job_id}/characters")
def update_characters(job_id: str, characters: List[Dict[str, Any]]):
    """
    Update detected characters for a job (edit names, descriptions, voice traits).
    Only allowed when job is in AWAITING_REVIEW status.
    """
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.AWAITING_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Can only edit characters when status is awaiting_review, current: {job.status}",
        )

    # Validate structure
    for char in characters:
        if "id" not in char or "name" not in char:
            raise HTTPException(
                status_code=400,
                detail="Each character must have 'id' and 'name' fields",
            )

    job_queue.update_job_status(
        job_id,
        JobStatus.AWAITING_REVIEW,
        detected_characters=json.dumps(characters),
    )

    return {"job_id": job_id, "characters": characters}


@app.post("/jobs/{job_id}/characters/{character_id}/voice-clone")
async def upload_voice_clone(
    job_id: str,
    character_id: str,
    file: UploadFile = File(...),
    ref_text: Optional[str] = Form(None),
):
    """
    Upload a voice clone WAV file for a specific character.
    Optionally include ref_text (transcript of the audio sample) for better voice cloning.
    Only allowed when job is in AWAITING_REVIEW status.
    """
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.AWAITING_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Can only upload voice clones when status is awaiting_review",
        )

    # Verify character exists
    if not job.detected_characters:
        raise HTTPException(status_code=400, detail="No characters detected")

    characters = json.loads(job.detected_characters)
    char_ids = [c["id"] for c in characters]
    if character_id not in char_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Character '{character_id}' not found. Available: {char_ids}",
        )

    if not file.filename or not file.filename.lower().endswith(".wav"):
        raise HTTPException(status_code=400, detail="File must be a .wav audio file")

    # Save voice clone
    clone_dir = Path("./data/output") / job_id / "voice_clones"
    clone_dir.mkdir(parents=True, exist_ok=True)
    clone_path = clone_dir / f"{character_id}.wav"

    content = await file.read()
    with open(clone_path, "wb") as f:
        f.write(content)

    # Save reference text alongside the WAV if provided
    ref_text_path = clone_dir / f"{character_id}_ref_text.txt"
    if ref_text and ref_text.strip():
        with open(ref_text_path, "w", encoding="utf-8") as f:
            f.write(ref_text.strip())
        logger.info(f"Reference text saved for {character_id}: {len(ref_text)} chars")
    elif ref_text_path.exists():
        ref_text_path.unlink()  # Remove stale ref_text if re-uploading without one

    logger.info(
        f"Voice clone uploaded for {character_id} in job {job_id}: {len(content)} bytes"
    )

    return {
        "job_id": job_id,
        "character_id": character_id,
        "voice_clone_path": str(clone_path),
        "has_ref_text": bool(ref_text and ref_text.strip()),
        "size_bytes": len(content),
    }


@app.delete("/jobs/{job_id}/characters/{character_id}/voice-clone")
def delete_voice_clone(job_id: str, character_id: str):
    """Remove an uploaded voice clone for a character."""
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    clone_dir = Path("./data/output") / job_id / "voice_clones"
    clone_path = clone_dir / f"{character_id}.wav"
    ref_text_path = clone_dir / f"{character_id}_ref_text.txt"
    if clone_path.exists():
        clone_path.unlink()
        if ref_text_path.exists():
            ref_text_path.unlink()
        return {"job_id": job_id, "character_id": character_id, "deleted": True}

    raise HTTPException(
        status_code=404, detail="No voice clone found for this character"
    )


@app.delete("/jobs/{job_id}/characters/{character_id}")
def delete_character(job_id: str, character_id: str):
    """
    Delete a character/speaker from the detected characters list.
    Only allowed when job is in AWAITING_REVIEW status.
    """
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.AWAITING_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Can only delete characters when status is awaiting_review",
        )

    if not job.detected_characters:
        raise HTTPException(status_code=400, detail="No characters detected")

    characters = json.loads(job.detected_characters)
    original_count = len(characters)

    # Filter out the character to delete
    characters = [c for c in characters if c["id"] != character_id]

    if len(characters) == original_count:
        raise HTTPException(
            status_code=404,
            detail=f"Character '{character_id}' not found",
        )

    # Update the job with the new character list
    job_queue.update_detected_characters(job_id, characters)

    # Also delete any voice clone files for this character
    clone_dir = Path("./data/output") / job_id / "voice_clones"
    for ext in [".wav", ".mp3", ".pt"]:
        clone_path = clone_dir / f"{character_id}{ext}"
        if clone_path.exists():
            clone_path.unlink()
    ref_text_path = clone_dir / f"{character_id}_ref_text.txt"
    if ref_text_path.exists():
        ref_text_path.unlink()

    logger.info(f"Deleted character {character_id} from job {job_id}")

    return {
        "job_id": job_id,
        "character_id": character_id,
        "deleted": True,
        "remaining_characters": len(characters),
    }


@app.post("/jobs/{job_id}/confirm")
def confirm_characters(job_id: str):
    """
    Confirm characters and resume processing.
    Transitions job from AWAITING_REVIEW → PENDING (with detected_characters set),
    which the worker picks up for phase 2.
    """
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.AWAITING_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Can only confirm when status is awaiting_review, current: {job.status}",
        )

    if not job.detected_characters:
        raise HTTPException(status_code=400, detail="No characters to confirm")

    # Set back to PENDING - the worker's get_next_confirmed_job() will pick it up
    job_queue.update_job_status(
        job_id,
        JobStatus.PENDING,
        progress=50,
        progress_message="Characters confirmed, waiting to resume...",
    )

    return {
        "job_id": job_id,
        "status": "confirmed",
        "message": "Processing will resume shortly",
    }


@app.post("/jobs/upload-book", status_code=201)
async def create_batch_job_from_zip(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    enable_text_processing: bool = Form(True),
    enable_speaker_detection: bool = Form(True),
    webhook_url: Optional[str] = Form(None),
):
    """
    Upload a ZIP file containing chapter .txt files to create a batch audiobook job.

    The ZIP must contain .txt files named with numeric prefixes for ordering:
    0000_chapter1.txt, 0001_chapter2.txt, etc.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a .zip archive")

    try:
        content = await file.read()
        zip_buffer = io.BytesIO(content)

        if not zipfile.is_zipfile(zip_buffer):
            raise HTTPException(status_code=400, detail="Invalid ZIP file")

        zip_buffer.seek(0)
        chapters = []

        with zipfile.ZipFile(zip_buffer, "r") as zf:
            txt_files = sorted(
                [
                    f
                    for f in zf.namelist()
                    if f.lower().endswith(".txt")
                    and not f.startswith("__MACOSX")
                    and not f.startswith(".")
                ]
            )

            if not txt_files:
                raise HTTPException(
                    status_code=400, detail="ZIP file contains no .txt files"
                )

            for txt_file in txt_files:
                text = zf.read(txt_file).decode("utf-8")
                # Use just the filename, not the full path inside ZIP
                filename = Path(txt_file).name
                chapters.append({"filename": filename, "text": text})

        book_title = title or Path(file.filename).stem

        result = job_queue.create_batch_job(
            title=book_title,
            chapters=chapters,
            enable_text_processing=enable_text_processing,
            enable_speaker_detection=enable_speaker_detection,
            webhook_url=webhook_url,
        )

        return result

    except HTTPException:
        raise
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400, detail="All .txt files in the ZIP must be valid UTF-8 text"
        )
    except Exception as e:
        logger.error(f"Failed to create batch job from ZIP: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_id}/download-book")
def download_batch_job(job_id: str):
    """
    Download all completed chapter audio files as a ZIP.

    Only available for batch jobs that have completed.
    """
    job = job_queue.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.is_batch:
        raise HTTPException(status_code=400, detail="Not a batch job")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Batch job is not completed. Current status: {job.status}",
        )

    children = job_queue.get_child_jobs(job_id)
    if not children:
        raise HTTPException(status_code=404, detail="No chapter jobs found")

    batch_output_dir = Path("./data/output") / job_id

    # Build ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add chapter audio files
        for child in children:
            if child.output_path and Path(child.output_path).exists():
                zf.write(child.output_path, f"audio/{child.output_filename}")

        # Add combined full audiobook if it exists
        if job.output_path and Path(job.output_path).exists():
            combined_filename = Path(job.output_path).name
            zf.write(job.output_path, f"audio/{combined_filename}")

        # Add characters.json manifest
        manifest_path = batch_output_dir / "characters.json"
        if manifest_path.exists():
            zf.write(str(manifest_path), "characters.json")

        # Add voice reference WAV files
        voices_dir = batch_output_dir / "voices"
        if voices_dir.exists():
            for voice_file in voices_dir.glob("*.wav"):
                zf.write(str(voice_file), f"voices/{voice_file.name}")

    zip_buffer.seek(0)

    # Write to temp file for FileResponse
    zip_filename = f"{job.title or 'audiobook'}.zip"
    batch_output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = batch_output_dir / zip_filename

    with open(zip_path, "wb") as f:
        f.write(zip_buffer.getvalue())

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=zip_filename,
    )


@app.get("/jobs/{job_id}/download-full")
def download_full_audiobook(job_id: str):
    """
    Download the combined full audiobook for a batch job.

    Only available for batch jobs that have completed.
    Returns the single MP3 file containing all chapters combined.
    """
    job = job_queue.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.is_batch:
        raise HTTPException(
            status_code=400,
            detail="Not a batch job. Use /jobs/{job_id}/download for single audiobooks.",
        )

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Batch job is not completed. Current status: {job.status}",
        )

    if not job.output_path or not Path(job.output_path).exists():
        raise HTTPException(status_code=404, detail="Combined audiobook file not found")

    return FileResponse(
        path=job.output_path,
        media_type="audio/mpeg",
        filename=job.output_filename or "audiobook_complete.mp3",
    )


@app.get("/jobs/{job_id}/chapters/{chapter_index}/download")
def download_chapter(job_id: str, chapter_index: int):
    """
    Download a specific chapter audio file from a batch job.

    **Parameters:**
    - `job_id`: UUID of the parent batch job
    - `chapter_index`: Index of the chapter (0-based)

    **Returns:** MP3 file download for the specific chapter
    """
    job = job_queue.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.is_batch:
        raise HTTPException(
            status_code=400,
            detail="Not a batch job. Use /jobs/{job_id}/download for single audiobooks.",
        )

    children = job_queue.get_child_jobs(job_id)
    if not children:
        raise HTTPException(status_code=404, detail="No chapter jobs found")

    # Find the chapter with matching index
    chapter_job = None
    for child in children:
        if child.chapter_index == chapter_index:
            chapter_job = child
            break

    if not chapter_job:
        raise HTTPException(
            status_code=404,
            detail=f"Chapter {chapter_index} not found. Available chapters: 0-{len(children) - 1}",
        )

    if chapter_job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Chapter {chapter_index} is not completed. Current status: {chapter_job.status}",
        )

    if not chapter_job.output_path or not Path(chapter_job.output_path).exists():
        raise HTTPException(
            status_code=404, detail=f"Audio file for chapter {chapter_index} not found"
        )

    return FileResponse(
        path=chapter_job.output_path,
        media_type="audio/mpeg",
        filename=chapter_job.output_filename,
    )


@app.get("/jobs/{job_id}/chapters")
def list_chapters(job_id: str):
    """
    List all chapters in a batch job with their download status.

    **Parameters:**
    - `job_id`: UUID of the parent batch job

    **Returns:** List of chapters with their status and download availability
    """
    job = job_queue.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.is_batch:
        raise HTTPException(status_code=400, detail="Not a batch job")

    children = job_queue.get_child_jobs(job_id)

    chapters = []
    for child in children:
        chapter_info = {
            "job_id": child.job_id,
            "chapter_index": child.chapter_index,
            "title": child.title,
            "status": child.status,
            "progress": child.progress,
            "output_filename": child.output_filename,
            "downloadable": child.status == JobStatus.COMPLETED
            and child.output_path
            and Path(child.output_path).exists(),
            "download_url": f"/jobs/{job_id}/chapters/{child.chapter_index}/download"
            if child.status == JobStatus.COMPLETED
            else None,
        }
        chapters.append(chapter_info)

    return {
        "job_id": job_id,
        "book_title": job.title,
        "total_chapters": len(chapters),
        "completed_chapters": sum(
            1 for c in chapters if c["status"] == JobStatus.COMPLETED
        ),
        "full_audiobook_available": job.status == JobStatus.COMPLETED
        and job.output_path
        and Path(job.output_path).exists(),
        "full_audiobook_download_url": f"/jobs/{job_id}/download-full"
        if job.status == JobStatus.COMPLETED
        else None,
        "chapters": chapters,
    }


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
            "awaiting_review": job_queue.get_job_count(JobStatus.AWAITING_REVIEW),
            "completed": job_queue.get_job_count(JobStatus.COMPLETED),
            "failed": job_queue.get_job_count(JobStatus.FAILED),
            "cancelled": job_queue.get_job_count(JobStatus.CANCELLED),
        }

        return stats

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# Voice Preset endpoints (pre-created voices)
# =========================================================================

VOICE_PRESETS_DIR = Path("./data/voice_presets")


@app.get("/voices")
def list_voice_presets():
    """
    List all available voice presets.

    Returns both system presets and user-created voice presets.
    """
    try:
        with database.get_session() as session:
            presets = session.query(VoicePreset).all()
            return {
                "voice_presets": [p.to_dict() for p in presets],
                "total": len(presets),
            }
    except Exception as e:
        logger.error(f"Failed to list voice presets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/voices", status_code=201)
async def create_voice_preset(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    age: Optional[str] = Form(None),
    voice_characteristics: Optional[str] = Form(None),
    reference_text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    voice_prompt_file: Optional[UploadFile] = File(None),
):
    """
    Create a new voice preset.

    Can be created with:
    - Just voice characteristics (for generation)
    - A reference audio file (.wav) (for voice cloning)
    - A voice prompt file (.pt) (pre-extracted voice embeddings)
    """
    try:
        voice_id = str(uuid.uuid4())
        reference_audio_path = None
        voice_prompt_path = None

        voice_dir = VOICE_PRESETS_DIR / voice_id
        voice_dir.mkdir(parents=True, exist_ok=True)

        # Save reference audio if provided
        if file and file.filename:
            if not file.filename.lower().endswith(".wav"):
                raise HTTPException(
                    status_code=400, detail="Reference audio must be a .wav file"
                )

            reference_audio_path = str(voice_dir / "reference.wav")

            content = await file.read()
            with open(reference_audio_path, "wb") as f:
                f.write(content)

        # Save voice prompt file if provided
        if voice_prompt_file and voice_prompt_file.filename:
            if not voice_prompt_file.filename.lower().endswith(".pt"):
                raise HTTPException(
                    status_code=400, detail="Voice prompt must be a .pt file"
                )

            voice_prompt_path = str(voice_dir / "voice_prompt.pt")

            content = await voice_prompt_file.read()
            with open(voice_prompt_path, "wb") as f:
                f.write(content)

        with database.get_session() as session:
            preset = VoicePreset(
                voice_id=voice_id,
                name=name,
                description=description,
                gender=gender,
                age=age,
                voice_characteristics=voice_characteristics,
                reference_audio_path=reference_audio_path,
                reference_text=reference_text,
                voice_prompt_path=voice_prompt_path,
                is_system=False,
            )
            session.add(preset)
            session.commit()
            session.refresh(preset)

            return preset.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create voice preset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/voices/{voice_id}")
def get_voice_preset(voice_id: str):
    """Get details of a specific voice preset."""
    try:
        with database.get_session() as session:
            preset = (
                session.query(VoicePreset)
                .filter(VoicePreset.voice_id == voice_id)
                .first()
            )
            if not preset:
                raise HTTPException(status_code=404, detail="Voice preset not found")
            return preset.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get voice preset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/voices/{voice_id}/preview")
def preview_voice_preset(voice_id: str):
    """Download the reference audio file for a voice preset."""
    try:
        with database.get_session() as session:
            preset = (
                session.query(VoicePreset)
                .filter(VoicePreset.voice_id == voice_id)
                .first()
            )
            if not preset:
                raise HTTPException(status_code=404, detail="Voice preset not found")

            if (
                not preset.reference_audio_path
                or not Path(preset.reference_audio_path).exists()
            ):
                raise HTTPException(
                    status_code=404,
                    detail="No reference audio available for this preset",
                )

            return FileResponse(
                path=preset.reference_audio_path,
                media_type="audio/wav",
                filename=f"{preset.name}.wav",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to preview voice preset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/voices/{voice_id}")
def delete_voice_preset(voice_id: str):
    """Delete a user-created voice preset. System presets cannot be deleted."""
    try:
        with database.get_session() as session:
            preset = (
                session.query(VoicePreset)
                .filter(VoicePreset.voice_id == voice_id)
                .first()
            )
            if not preset:
                raise HTTPException(status_code=404, detail="Voice preset not found")

            if preset.is_system:
                raise HTTPException(
                    status_code=403, detail="Cannot delete system voice presets"
                )

            # Delete audio files
            voice_dir = VOICE_PRESETS_DIR / voice_id
            if voice_dir.exists():
                shutil.rmtree(voice_dir)

            session.delete(preset)
            session.commit()

            return {"voice_id": voice_id, "deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete voice preset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/voices/generate")
async def generate_voice_preset(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    gender: str = Form("male"),
    age: str = Form("30"),
    voice_characteristics: str = Form(...),
    sample_text: Optional[str] = Form(None),
):
    """
    Generate a new voice using Qwen VoiceDesign model.

    Uses the voice_characteristics to generate a reference audio file
    that can be used for voice cloning in future audiobook jobs.
    """
    from .tts_synthesizer import TTSSynthesizer
    from .voice_control import VoiceConfig, DetailedVoiceProfile
    import soundfile as sf

    try:
        voice_id = str(uuid.uuid4())
        voice_dir = VOICE_PRESETS_DIR / voice_id
        voice_dir.mkdir(parents=True, exist_ok=True)
        reference_audio_path = str(voice_dir / "reference.wav")

        # Default sample text if not provided
        if not sample_text:
            sample_text = "Hello, welcome to this audiobook. I hope you enjoy listening to this story as much as I enjoyed narrating it for you."

        # Create voice config with the characteristics
        voice_config = VoiceConfig(
            profile=DetailedVoiceProfile.from_natural_language(voice_characteristics)
        )

        # Create synthesizer and generate voice
        logger.info(f"Generating voice with characteristics: {voice_characteristics}")
        synthesizer = TTSSynthesizer(voice_config)

        # Generate the voice using VoiceDesign model
        audio_data, sample_rate = synthesizer.create_voice(
            output_path=reference_audio_path,
            design_text=sample_text,
            design_instruct=voice_characteristics,
        )

        logger.info(f"Voice generated and saved to: {reference_audio_path}")

        # Save to database
        with database.get_session() as session:
            preset = VoicePreset(
                voice_id=voice_id,
                name=name,
                description=description or f"Generated voice: {voice_characteristics}",
                gender=gender,
                age=age,
                voice_characteristics=voice_characteristics,
                reference_audio_path=reference_audio_path,
                reference_text=sample_text,
                is_system=False,
            )
            session.add(preset)
            session.commit()
            session.refresh(preset)

            return {
                **preset.to_dict(),
                "generated": True,
                "message": "Voice generated successfully using Qwen VoiceDesign",
            }

    except Exception as e:
        # Clean up on error
        if voice_dir.exists():
            shutil.rmtree(voice_dir)
        logger.error(f"Failed to generate voice preset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/jobs/{job_id}/characters/{character_id}/assign-voice")
def assign_voice_preset_to_character(
    job_id: str, character_id: str, voice_preset_id: str = Form(...)
):
    """
    Assign a pre-created voice preset to a character.

    This copies the voice preset's reference audio to the character's voice clone directory,
    making it behave like an uploaded voice clone.
    """
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.AWAITING_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Can only assign voices when status is awaiting_review, current: {job.status}",
        )

    # Verify character exists
    if not job.detected_characters:
        raise HTTPException(status_code=400, detail="No characters detected")

    characters = json.loads(job.detected_characters)
    char_idx = None
    for i, c in enumerate(characters):
        if c["id"] == character_id:
            char_idx = i
            break

    if char_idx is None:
        raise HTTPException(
            status_code=404,
            detail=f"Character '{character_id}' not found",
        )

    # Get voice preset
    try:
        with database.get_session() as session:
            preset = (
                session.query(VoicePreset)
                .filter(VoicePreset.voice_id == voice_preset_id)
                .first()
            )
            if not preset:
                raise HTTPException(status_code=404, detail="Voice preset not found")

            # Copy reference audio to voice clone directory
            clone_dir = Path("./data/output") / job_id / "voice_clones"
            clone_dir.mkdir(parents=True, exist_ok=True)
            clone_path = clone_dir / f"{character_id}.wav"

            if (
                preset.reference_audio_path
                and Path(preset.reference_audio_path).exists()
            ):
                shutil.copy2(preset.reference_audio_path, clone_path)

            # Save reference text if available
            if preset.reference_text:
                ref_text_path = clone_dir / f"{character_id}_ref_text.txt"
                with open(ref_text_path, "w", encoding="utf-8") as f:
                    f.write(preset.reference_text)

            # Update character with voice preset info
            characters[char_idx]["voice_preset_id"] = voice_preset_id
            characters[char_idx]["voice_preset_name"] = preset.name
            if preset.voice_characteristics:
                characters[char_idx]["voice_characteristics"] = (
                    preset.voice_characteristics
                )

            job_queue.update_job_status(
                job_id,
                JobStatus.AWAITING_REVIEW,
                detected_characters=json.dumps(characters),
            )

            return {
                "job_id": job_id,
                "character_id": character_id,
                "voice_preset_id": voice_preset_id,
                "voice_preset_name": preset.name,
                "assigned": True,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to assign voice preset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Health check endpoint
@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

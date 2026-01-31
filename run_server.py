"""Run the audiobook generation API server and worker."""

import logging
import threading
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from audiobook_generator.config import load_config
from audiobook_generator.database import get_database
from audiobook_generator.job_queue import JobQueue
from audiobook_generator.worker_with_progress import AudiobookWorkerWithProgress

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Load configuration from config.yml / env vars / defaults
config = load_config()


def run_worker():
    """Run the background worker."""
    database = get_database()
    job_queue = JobQueue(database)

    worker = AudiobookWorkerWithProgress(
        job_queue=job_queue,
        output_base_dir="./data/output",
        llm_provider=config.llm.provider,
        llm_model=config.llm.model,
        llm_base_url=config.llm.base_url,
        llm_api_key=config.llm.api_key,
        tts_device=config.tts.device,
        tts_dtype=config.tts.dtype,
        poll_interval=5,
    )

    worker.run()


def run_api():
    """Run the FastAPI server."""
    import uvicorn
    from audiobook_generator.api import app

    uvicorn.run(app, host=config.app.host, port=config.app.port, log_level="info")


def main():
    """Run both API server and worker."""
    logger.info("Starting Audiobook Generator Service")

    # Verify and download models
    logger.info("Verifying TTS models...")
    from audiobook_generator.model_downloader import verify_models_on_startup

    models_ready = verify_models_on_startup(
        device=config.tts.device or "cuda:0",
        dtype=config.tts.dtype,
        skip_verification=False,
    )

    if not models_ready:
        logger.error("Model verification failed! Please check the errors above.")
        logger.error("You can set skip_verification=True to start anyway.")
        return

    # Start worker in separate thread
    worker_thread = threading.Thread(target=run_worker, daemon=True)
    worker_thread.start()
    logger.info("Worker thread started")

    # Run API in main thread
    logger.info(f"Starting API server on http://{config.app.host}:{config.app.port}")
    run_api()


if __name__ == "__main__":
    main()

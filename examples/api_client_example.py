"""Example API client for audiobook generation service."""

import requests
import time
import json


class AudiobookClient:
    """Client for interacting with the Audiobook Generator API."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize client.

        Args:
            base_url: API base URL
        """
        self.base_url = base_url.rstrip("/")

    def create_job(
        self,
        text: str,
        enable_text_processing: bool = True,
        enable_speaker_detection: bool = True,
        webhook_url: str = None,
    ) -> dict:
        """
        Create a new audiobook job.

        Args:
            text: Text content to convert
            enable_text_processing: Use Ollama processing
            enable_speaker_detection: Detect multiple speakers
            webhook_url: Webhook URL to call on completion

        Returns:
            Job information
        """
        response = requests.post(
            f"{self.base_url}/jobs",
            json={
                "text": text,
                "enable_text_processing": enable_text_processing,
                "enable_speaker_detection": enable_speaker_detection,
                "webhook_url": webhook_url,
            },
        )
        response.raise_for_status()
        return response.json()

    def upload_file(
        self,
        file_path: str,
        enable_text_processing: bool = True,
        enable_speaker_detection: bool = True,
        webhook_url: str = None,
    ) -> dict:
        """
        Upload a text file and create job.

        Args:
            file_path: Path to text file
            enable_text_processing: Use Ollama processing
            enable_speaker_detection: Detect multiple speakers
            webhook_url: Webhook URL to call on completion

        Returns:
            Job information
        """
        with open(file_path, "rb") as f:
            files = {"file": f}
            data = {
                "enable_text_processing": enable_text_processing,
                "enable_speaker_detection": enable_speaker_detection,
            }

            if webhook_url:
                data["webhook_url"] = webhook_url

            response = requests.post(
                f"{self.base_url}/jobs/upload", files=files, data=data
            )
            response.raise_for_status()
            return response.json()

    def get_job(self, job_id: str) -> dict:
        """Get job details."""
        response = requests.get(f"{self.base_url}/jobs/{job_id}")
        response.raise_for_status()
        return response.json()

    def list_jobs(self, status: str = None, limit: int = 100) -> dict:
        """List all jobs."""
        params = {"limit": limit}
        if status:
            params["status"] = status

        response = requests.get(f"{self.base_url}/jobs", params=params)
        response.raise_for_status()
        return response.json()

    def download_audiobook(self, job_id: str, output_path: str):
        """Download completed audiobook."""
        response = requests.get(f"{self.base_url}/jobs/{job_id}/download", stream=True)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

    def wait_for_completion(
        self, job_id: str, poll_interval: int = 5, timeout: int = 3600
    ):
        """
        Wait for job to complete.

        Args:
            job_id: Job ID
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait

        Returns:
            Final job status

        Raises:
            TimeoutError: If job doesn't complete in time
            RuntimeError: If job fails
        """
        start_time = time.time()

        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError(
                    f"Job {job_id} did not complete within {timeout} seconds"
                )

            job = self.get_job(job_id)
            status = job["status"]
            progress = job["progress"]

            print(f"Status: {status} ({progress}%)")

            if status == "completed":
                return job

            if status == "failed":
                error = job.get("error_message", "Unknown error")
                raise RuntimeError(f"Job failed: {error}")

            if status == "cancelled":
                raise RuntimeError("Job was cancelled")

            time.sleep(poll_interval)

    def delete_job(self, job_id: str):
        """Delete or cancel a job."""
        response = requests.delete(f"{self.base_url}/jobs/{job_id}")
        response.raise_for_status()
        return response.json()

    def get_stats(self) -> dict:
        """Get service statistics."""
        response = requests.get(f"{self.base_url}/stats")
        response.raise_for_status()
        return response.json()


def example_text_job():
    """Example: Create job with text content."""
    client = AudiobookClient()

    # Create job
    print("Creating job...")
    job = client.create_job(
        text="The quick brown fox jumps over the lazy dog. " * 50,
        enable_text_processing=True,
        enable_speaker_detection=False,
    )

    job_id = job["job_id"]
    print(f"Created job: {job_id}")

    # Wait for completion
    print("Waiting for job to complete...")
    try:
        final_job = client.wait_for_completion(job_id)
        print(f"Job completed!")

        # Download audiobook
        output_file = f"audiobook_{job_id}.mp3"
        print(f"Downloading to {output_file}...")
        client.download_audiobook(job_id, output_file)
        print(f"Download complete!")

    except Exception as e:
        print(f"Error: {e}")


def example_file_upload():
    """Example: Upload file and create job."""
    client = AudiobookClient()

    # Upload file
    print("Uploading file...")
    job = client.upload_file(
        file_path="../data/input/sample.txt",
        enable_text_processing=True,
        enable_speaker_detection=True,
    )

    job_id = job["job_id"]
    print(f"Created job: {job_id}")

    # Wait for completion
    print("Waiting for job to complete...")
    try:
        final_job = client.wait_for_completion(job_id)
        print(f"Job completed!")

        # Download audiobook
        output_file = "audiobook_from_file.mp3"
        print(f"Downloading to {output_file}...")
        client.download_audiobook(job_id, output_file)
        print(f"Download complete!")

    except Exception as e:
        print(f"Error: {e}")


def example_list_jobs():
    """Example: List all jobs."""
    client = AudiobookClient()

    # Get all jobs
    result = client.list_jobs()
    print(f"\nTotal jobs: {result['total']}")

    for job in result["jobs"]:
        print(f"\nJob: {job['job_id']}")
        print(f"  Status: {job['status']} ({job['progress']}%)")
        print(f"  Created: {job['created_at']}")
        if job["completed_at"]:
            print(f"  Completed: {job['completed_at']}")

    # Get only completed jobs
    completed = client.list_jobs(status="completed")
    print(f"\nCompleted jobs: {completed['total']}")


def example_stats():
    """Example: Get service statistics."""
    client = AudiobookClient()

    stats = client.get_stats()
    print("\nService Statistics:")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    print("Audiobook API Client Examples")
    print("=" * 60)

    # Uncomment the example you want to run

    # example_text_job()
    # example_file_upload()
    example_list_jobs()
    # example_stats()

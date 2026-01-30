# Audiobook Generator API Documentation

REST API for generating audiobooks with multi-speaker support.

## Base URL

```
http://localhost:8000
```

## Endpoints

### 1. Create Job (JSON)

Create a new audiobook generation job with text content.

**Endpoint:** `POST /jobs`

**Request Body:**
```json
{
  "text": "Your text content here...",
  "filename": "optional_original_filename.txt",
  "enable_text_processing": true,
  "enable_speaker_detection": true,
  "output_filename": "audiobook.mp3",
  "webhook_url": "https://your-server.com/webhook"
}
```

**Response:** `201 Created`
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "progress": 0,
  "input_filename": "optional_original_filename.txt",
  "output_filename": "audiobook.mp3",
  "enable_text_processing": true,
  "enable_speaker_detection": true,
  "webhook_url": "https://your-server.com/webhook",
  "error_message": null,
  "created_at": "2024-01-30T12:00:00Z",
  "started_at": null,
  "completed_at": null
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "text": "The quick brown fox jumps over the lazy dog.",
    "enable_text_processing": true,
    "enable_speaker_detection": false,
    "webhook_url": "https://your-server.com/webhook"
  }'
```

---

### 2. Create Job (File Upload)

Upload a text file and create an audiobook generation job.

**Endpoint:** `POST /jobs/upload`

**Request:** `multipart/form-data`
- `file`: Text file (required)
- `enable_text_processing`: boolean (default: true)
- `enable_speaker_detection`: boolean (default: true)
- `output_filename`: string (default: "audiobook.mp3")
- `webhook_url`: string (optional)

**Response:** `201 Created` (same as above)

**cURL Example:**
```bash
curl -X POST http://localhost:8000/jobs/upload \
  -F "file=@/path/to/book.txt" \
  -F "enable_text_processing=true" \
  -F "enable_speaker_detection=true" \
  -F "webhook_url=https://your-server.com/webhook"
```

---

### 3. List Jobs

Get a list of all jobs with optional filtering.

**Endpoint:** `GET /jobs`

**Query Parameters:**
- `status`: Filter by status (pending, processing, completed, failed, cancelled)
- `limit`: Maximum results (default: 100)
- `offset`: Pagination offset (default: 0)

**Response:** `200 OK`
```json
{
  "jobs": [
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "completed",
      "progress": 100,
      "input_filename": "book.txt",
      "output_filename": "audiobook.mp3",
      "enable_text_processing": true,
      "enable_speaker_detection": true,
      "webhook_url": null,
      "error_message": null,
      "created_at": "2024-01-30T12:00:00Z",
      "started_at": "2024-01-30T12:00:05Z",
      "completed_at": "2024-01-30T12:15:00Z"
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

**cURL Examples:**
```bash
# Get all jobs
curl http://localhost:8000/jobs

# Get only completed jobs
curl http://localhost:8000/jobs?status=completed

# Pagination
curl http://localhost:8000/jobs?limit=10&offset=0
```

---

### 4. Get Job Details

Get details of a specific job.

**Endpoint:** `GET /jobs/{job_id}`

**Response:** `200 OK`
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "progress": 100,
  "input_filename": "book.txt",
  "output_filename": "audiobook.mp3",
  "enable_text_processing": true,
  "enable_speaker_detection": true,
  "webhook_url": "https://your-server.com/webhook",
  "error_message": null,
  "created_at": "2024-01-30T12:00:00Z",
  "started_at": "2024-01-30T12:00:05Z",
  "completed_at": "2024-01-30T12:15:00Z"
}
```

**cURL Example:**
```bash
curl http://localhost:8000/jobs/550e8400-e29b-41d4-a716-446655440000
```

---

### 5. Download Audiobook

Download the completed audiobook file.

**Endpoint:** `GET /jobs/{job_id}/download`

**Response:** `200 OK` (MP3 file)

**cURL Example:**
```bash
curl -O http://localhost:8000/jobs/550e8400-e29b-41d4-a716-446655440000/download
```

**Browser:**
```
http://localhost:8000/jobs/550e8400-e29b-41d4-a716-446655440000/download
```

---

### 6. Delete Job

Cancel or delete a job.

**Endpoint:** `DELETE /jobs/{job_id}`

**Response:** `200 OK`
```json
{
  "message": "Job cancelled",
  "job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**cURL Example:**
```bash
curl -X DELETE http://localhost:8000/jobs/550e8400-e29b-41d4-a716-446655440000
```

---

### 7. Get Statistics

Get service statistics.

**Endpoint:** `GET /stats`

**Response:** `200 OK`
```json
{
  "total_jobs": 10,
  "pending": 2,
  "processing": 1,
  "completed": 6,
  "failed": 1,
  "cancelled": 0
}
```

**cURL Example:**
```bash
curl http://localhost:8000/stats
```

---

### 8. Health Check

Check if the service is running.

**Endpoint:** `GET /health`

**Response:** `200 OK`
```json
{
  "status": "healthy"
}
```

---

## Webhook Notifications

When a job completes (success or failure), the API will send a POST request to the webhook URL you provided.

**Webhook Payload:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "timestamp": 1706616000.123
}
```

**Status Values:**
- `completed`: Job finished successfully
- `failed`: Job failed with an error

**Example Webhook Handler (Flask):**
```python
from flask import Flask, request

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    data = request.json
    job_id = data['job_id']
    status = data['status']
    
    if status == 'completed':
        # Download the audiobook
        download_url = f"http://localhost:8000/jobs/{job_id}/download"
        # Process download...
    
    return {'status': 'ok'}
```

---

## Job Status Flow

```
PENDING → PROCESSING → COMPLETED
                     ↘ FAILED
                     ↘ CANCELLED
```

- **PENDING**: Job is in queue waiting to be processed
- **PROCESSING**: Job is currently being processed
- **COMPLETED**: Job finished successfully, audiobook ready for download
- **FAILED**: Job failed with an error (check error_message)
- **CANCELLED**: Job was cancelled by user

---

## Configuration Options

### Text Processing
- `enable_text_processing: true` - Use Ollama to clean and optimize text
- `enable_text_processing: false` - Skip processing, use raw text

### Speaker Detection
- `enable_speaker_detection: true` - Detect multiple speakers and generate unique voices
- `enable_speaker_detection: false` - Use single narrator voice

### Recommended Combinations

1. **Full Pipeline** (Best Quality)
   - `enable_text_processing: true`
   - `enable_speaker_detection: true`
   - Use for: Novels, stories with dialogue

2. **Single Narrator** (Faster)
   - `enable_text_processing: true`
   - `enable_speaker_detection: false`
   - Use for: Non-fiction, essays, articles

3. **Direct TTS** (Fastest)
   - `enable_text_processing: false`
   - `enable_speaker_detection: false`
   - Use for: Pre-processed text, quick tests

---

## Error Handling

**404 Not Found:**
```json
{
  "detail": "Job not found"
}
```

**400 Bad Request:**
```json
{
  "detail": "Job is not completed. Current status: processing"
}
```

**500 Internal Server Error:**
```json
{
  "detail": "Error message here"
}
```

---

## Complete Workflow Example

### 1. Create a job
```bash
JOB_ID=$(curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Your book content here...",
    "enable_text_processing": true,
    "enable_speaker_detection": true,
    "webhook_url": "https://your-server.com/webhook"
  }' | jq -r '.job_id')

echo "Created job: $JOB_ID"
```

### 2. Check job status
```bash
curl http://localhost:8000/jobs/$JOB_ID | jq
```

### 3. Wait for webhook or poll for completion
```bash
# Poll until completed
while true; do
  STATUS=$(curl -s http://localhost:8000/jobs/$JOB_ID | jq -r '.status')
  echo "Status: $STATUS"
  
  if [ "$STATUS" = "completed" ]; then
    break
  fi
  
  if [ "$STATUS" = "failed" ]; then
    echo "Job failed!"
    exit 1
  fi
  
  sleep 5
done
```

### 4. Download the audiobook
```bash
curl -O http://localhost:8000/jobs/$JOB_ID/download
```

---

## Interactive API Documentation

Once the server is running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

These provide interactive API documentation where you can test endpoints directly.

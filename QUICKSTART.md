# Quick Start Guide

## Installation

1. **Install Dependencies**
```bash
pip install -r requirements.txt
```

2. **Configure Environment (Optional)**
```bash
cp .env.example .env
# Edit .env with your settings
```

## Running the Service

### Start Everything (API + Worker + Web Interface)

```bash
python run_server.py
```

This starts:
- ✅ REST API server on http://localhost:8000
- ✅ Background worker for processing jobs
- ✅ Web interface at http://localhost:8000

## Using the Web Interface

### 1. Open Browser
Navigate to: **http://localhost:8000**

### 2. Create an Audiobook

**Option A: Text Input**
1. Click "Text Input" tab
2. Paste your text
3. Configure options:
   - ✅ Enable Text Processing (AI cleanup)
   - ✅ Enable Speaker Detection (multi-voice)
4. (Optional) Add webhook URL
5. Click "Generate Audiobook"

**Option B: File Upload**
1. Click "File Upload" tab
2. Select a .txt or .md file
3. Configure options
4. Click "Upload and Generate"

### 3. Monitor Progress

The dashboard shows:
- **Statistics**: Total, Pending, Processing, Completed, Failed jobs
- **Job List**: All jobs with status and progress bars
- **Real-time Updates**: Auto-refreshes every 5 seconds

### 4. Download Audiobook

When status shows "COMPLETED":
1. Click the "⬇️ Download" button
2. Audiobook downloads as MP3

## Using the API

See [API.md](API.md) for complete REST API documentation.

### Quick API Example

```bash
# Create job
curl -X POST http://localhost:8000/jobs/upload \
  -F "file=@book.txt" \
  -F "enable_text_processing=true" \
  -F "enable_speaker_detection=true"

# Get job status
curl http://localhost:8000/jobs/{job_id}

# Download when complete
curl -O http://localhost:8000/jobs/{job_id}/download
```

## Configuration

### Default Settings
- **Ollama Model**: gpt-oss-16k:120b
- **Ollama Endpoint**: https://192.168.178.166/v1
- **Batch Size**: 16,000 characters
- **TTS Device**: cuda:0
- **TTS Batch**: 5 segments per speaker

### Customize Settings

Edit `.env` file or modify `run_server.py`:

```python
worker = AudiobookWorker(
    job_queue=job_queue,
    ollama_model="gpt-oss-16k:120b",
    ollama_base_url="https://192.168.178.166/v1",
    tts_device="cuda:0",
    tts_dtype="bfloat16",
    poll_interval=5,
)
```

## Features

### Processing Options

**Text Processing (Ollama)**
- Cleans and normalizes text
- Fixes formatting issues
- Optimizes for natural speech
- Uses gpt-oss-16k:120b model

**Speaker Detection**
- Automatically detects characters
- Generates unique voices for each speaker
- Analyzes dialogue and narration
- Creates professional multi-voice audiobooks

### Job Management

- **Queue System**: Jobs processed one at a time
- **Progress Tracking**: Real-time progress updates
- **Webhooks**: Get notified when jobs complete
- **Persistence**: Jobs saved in SQLite database
- **Cancellation**: Cancel pending/processing jobs
- **History**: View all completed and failed jobs

## Troubleshooting

### Port Already in Use
```bash
# Change port in run_server.py
uvicorn.run(app, host="0.0.0.0", port=8001)
```

### Ollama Connection Failed
- Verify Ollama is running at configured endpoint
- Check `OLLAMA_BASE_URL` in settings
- Test: `curl https://192.168.178.166/v1/models`

### CUDA Out of Memory
- Reduce `tts_batch_size` in worker settings
- Use CPU: `tts_device="cpu"`
- Use float32: `tts_dtype="float32"`

### Jobs Stuck in Processing
- Restart the worker
- Check worker logs for errors
- Verify GPU is accessible

## Directory Structure

```
Audiobook-Generator/
├── run_server.py              # Start server + worker
├── frontend/                  # Web interface
│   ├── templates/index.html   # Main page
│   └── static/
│       ├── css/style.css      # Styling
│       └── js/app.js          # Frontend logic
├── src/audiobook_generator/   # Core library
│   ├── api.py                 # FastAPI endpoints
│   ├── worker.py              # Background processor
│   ├── job_queue.py           # Job management
│   ├── multi_speaker_generator.py  # Main pipeline
│   └── ...
├── data/
│   ├── input/                 # Input text files
│   └── output/                # Generated audiobooks
├── audiobook_jobs.db          # Job database (auto-created)
└── examples/                  # Usage examples
```

## Next Steps

- Read [README.md](README.md) for detailed information
- See [API.md](API.md) for API documentation
- Check `examples/` for code samples
- Explore configuration options in `.env.example`

## Support

For issues or questions:
- Check logs in console output
- Review error messages in web interface
- Verify all dependencies are installed
- Ensure Ollama and GPU are accessible

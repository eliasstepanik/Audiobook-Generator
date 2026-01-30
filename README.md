# Audiobook Generator

A powerful audiobook generator that combines Ollama's gpt-oss:120b for intelligent text processing and Qwen3-TTS for high-quality voice synthesis. Supports multi-speaker detection, automatic voice generation, and produces professional-quality audiobooks.

## Features

### Core Features
- **Intelligent Text Processing**: Uses Ollama gpt-oss-16k:120b to clean, normalize, and optimize text for natural speech
- **Multi-Speaker Support**: Automatically detects characters/speakers and generates unique voices
- **Batch Processing**: Handles large texts by processing in configurable chunks (16k context by default)
- **High-Quality TTS**: Qwen3-TTS-12Hz-1.7B for natural-sounding voice synthesis
- **Voice Design**: Automatically creates voices based on character descriptions
- **Audio Combining**: Merges all segments into a single MP3 file
- **Flexible Pipeline**: Enable/disable text processing and speaker detection as needed

### API Features
- **REST API**: Full-featured FastAPI-based REST API
- **Job Queue**: Background processing with SQLite-based job queue
- **Webhooks**: Automatic notifications when jobs complete
- **File Upload**: Upload text files directly via API
- **Download Endpoint**: Download completed audiobooks
- **Job Management**: List, track, and cancel jobs
- **Auto Documentation**: Interactive Swagger UI and ReDoc

## Installation

### Prerequisites

- Python 3.9+
- CUDA-compatible GPU (recommended for TTS)
- Ollama server running with gpt-oss-16k:120b model
- FFmpeg (for audio processing)

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Optional: Flash Attention

For faster TTS inference, install Flash Attention 2:

```bash
pip install flash-attn
```

## Quick Start

### Option 1: Web Interface (Easiest)

#### 1. Start the Server

```bash
python run_server.py
```

#### 2. Open Web Interface

Open your browser and navigate to:
```
http://localhost:8000
```

#### 3. Use the Web Interface

- **Create Jobs**: Enter text or upload files directly in the browser
- **Monitor Progress**: See real-time job status and progress bars
- **Download**: Click download button when jobs complete
- **View Statistics**: Dashboard shows pending, processing, and completed jobs

Features:
- 📝 Text input or file upload
- 📊 Real-time job monitoring
- ⬇️ One-click downloads
- 🔄 Auto-refresh every 5 seconds
- 🎨 Clean, modern interface

### Option 2: REST API

#### 1. Start the Server

```bash
python run_server.py
```

This starts both the API server (port 8000) and background worker.

#### 2. Create a Job

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -F "file=@data/input/sample.txt" \
  -F "enable_text_processing=true" \
  -F "enable_speaker_detection=true" \
  -F "webhook_url=https://your-server.com/webhook"
```

#### 3. Check Status

```bash
curl http://localhost:8000/jobs/{job_id}
```

#### 4. Download Audiobook

```bash
curl -O http://localhost:8000/jobs/{job_id}/download
```

See [API.md](API.md) for complete API documentation.

### Option 3: Direct Python Usage

#### 1. Prepare Your Text File

Place your text file in `data/input/`:

```
data/input/my_book.txt
```

#### 2. Run the Generator

```python
from audiobook_generator import MultiSpeakerAudiobookGenerator

generator = MultiSpeakerAudiobookGenerator(
    ollama_model="gpt-oss-16k:120b",
    ollama_base_url="https://192.168.178.166/v1",
    max_chars_per_batch=16000,
    tts_device="cuda:0",
    enable_text_processing=True,
    enable_speaker_detection=True,
)

metadata = generator.generate(
    input_file="data/input/my_book.txt",
    output_dir="data/output/my_audiobook",
    output_filename="audiobook.mp3",
    save_intermediate=True,
    tts_batch_size=5,
)
```

#### 3. Get Your Audiobook

The final audiobook will be at:
```
data/output/my_audiobook/audiobook.mp3
```

## API Server

### Running the Server

```bash
# Run both API server and worker
python run_server.py

# Or run separately:
# Terminal 1: API Server
uvicorn audiobook_generator.api:app --host 0.0.0.0 --port 8000

# Terminal 2: Background Worker
python -c "from audiobook_generator.worker import AudiobookWorker; from audiobook_generator.job_queue import JobQueue; from audiobook_generator.database import get_database; worker = AudiobookWorker(JobQueue(get_database())); worker.run()"
```

### API Endpoints

- `POST /jobs` - Create new job with JSON
- `POST /jobs/upload` - Upload text file and create job
- `GET /jobs` - List all jobs
- `GET /jobs/{job_id}` - Get job details
- `GET /jobs/{job_id}/download` - Download audiobook
- `DELETE /jobs/{job_id}` - Cancel/delete job
- `GET /stats` - Get service statistics
- `GET /health` - Health check

### Interactive Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Webhooks

Configure webhook URLs to receive notifications when jobs complete:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "timestamp": 1706616000.123
}
```

See [API.md](API.md) for complete webhook documentation.

## Pipeline Overview

The generator follows a 7-step pipeline:

1. **Read and Batch Text**: Splits text into 16k character chunks
2. **Process Through Ollama**: Cleans and optimizes text for TTS
3. **Detect Speakers**: Identifies characters and their voice characteristics
4. **Generate Voices**: Creates unique voice for each speaker using Qwen3-TTS VoiceDesign
5. **Assign Speakers**: Maps text segments to appropriate voices
6. **Synthesize Audio**: Generates audio per speaker in batches
7. **Combine Audio**: Merges all segments into single MP3

## Configuration

### Ollama Settings

```python
ollama_model="gpt-oss-16k:120b"          # Model name
ollama_base_url="https://192.168.178.166/v1"  # OpenAI-compatible API endpoint
max_chars_per_batch=16000                # Characters per batch (context limit)
```

### TTS Settings

```python
tts_device="cuda:0"      # Device: "cuda:0", "cuda:1", or "cpu"
tts_dtype="bfloat16"     # Data type: "bfloat16" or "float32"
tts_batch_size=5         # Segments to process at once per speaker
```

### Processing Options

```python
enable_text_processing=True    # Use Ollama to clean/optimize text
enable_speaker_detection=True  # Detect and use multiple speakers
save_intermediate=True         # Save intermediate files for debugging
```

## Usage Examples

### Multi-Speaker Audiobook (Full Pipeline)

```python
generator = MultiSpeakerAudiobookGenerator(
    enable_text_processing=True,
    enable_speaker_detection=True,
)

generator.generate(
    input_file="data/input/novel.txt",
    output_dir="data/output/novel",
    output_filename="novel.mp3",
)
```

### Single Narrator

```python
generator = MultiSpeakerAudiobookGenerator(
    enable_text_processing=True,
    enable_speaker_detection=False,  # Single voice
)

generator.generate(
    input_file="data/input/essay.txt",
    output_dir="data/output/essay",
)
```

### Direct TTS (No Processing)

```python
generator = MultiSpeakerAudiobookGenerator(
    enable_text_processing=False,  # Skip Ollama processing
    enable_speaker_detection=False,
)

generator.generate(
    input_file="data/input/clean_text.txt",
    output_dir="data/output/fast",
)
```

## Output Structure

```
output_dir/
├── audiobook.mp3              # Final combined audiobook
├── metadata.json              # Generation metadata
├── processed_text.txt         # Ollama-processed text (if enabled)
├── detected_speakers.json     # Speaker information (if enabled)
└── segments/                  # Individual audio segments
    ├── voice_narrator.wav
    ├── voice_character1.wav
    ├── segment_0000_narrator.wav
    ├── segment_0001_narrator.wav
    └── ...
```

## Advanced Configuration

### Environment Variables

Create a `.env` file:

```env
# Ollama
OLLAMA_MODEL=gpt-oss-16k:120b
OLLAMA_BASE_URL=https://192.168.178.166/v1
OLLAMA_TEMPERATURE=0.3

# TTS
TTS_DEVICE=cuda:0
TTS_DTYPE=bfloat16
TTS_BATCH_SIZE=5

# Processing
MAX_CHARS_PER_BATCH=16000
ENABLE_OLLAMA=true
```

Load configuration:

```python
from audiobook_generator import load_config

config = load_config(".env")
```

### Custom Voice Characteristics

The LLM automatically generates voice characteristics, but you can customize:

```python
# Example detected speaker
{
  "id": "detective",
  "name": "Detective Morrison",
  "description": "Hard-boiled detective",
  "voice_characteristics": "Male, 45 years old, gravelly voice, world-weary tone, Brooklyn accent"
}
```

## Performance Tips

1. **GPU Memory**: Use `tts_dtype="bfloat16"` to reduce memory usage
2. **Batch Size**: Increase `tts_batch_size` for faster processing (if GPU memory allows)
3. **Context Size**: Adjust `max_chars_per_batch` based on Ollama model capacity
4. **Skip Processing**: Disable `enable_text_processing` for pre-cleaned text
5. **Single Speaker**: Disable `enable_speaker_detection` for faster generation

## Troubleshooting

### SSL Certificate Errors

If you get SSL errors with Ollama:
- The client uses `verify=False` for HTTPS requests
- Ensure your Ollama endpoint is correct

### Out of Memory

- Reduce `tts_batch_size`
- Use `tts_dtype="float32"` instead of `bfloat16`
- Process on CPU: `tts_device="cpu"`

### Speaker Detection Issues

- Ensure text has clear dialogue markers (quotes)
- Check `detected_speakers.json` to see what was detected
- Fallback: Use single speaker mode

## License

MIT License

## Credits

- **Ollama**: Text processing with gpt-oss-16k:120b
- **Qwen3-TTS**: Voice synthesis by Alibaba
- **Pydub**: Audio processing and combining

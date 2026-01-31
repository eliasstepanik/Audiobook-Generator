# Audiobook Generator

A powerful multi-speaker audiobook generator that uses LLM-powered text analysis and Qwen3-TTS for high-quality voice synthesis. Supports multiple LLM providers (Ollama, OpenAI, Anthropic), automatic speaker detection, unique voice generation per character, and produces professional-quality audiobooks.

[![Build Docker Images](https://github.com/YOUR_USERNAME/Audiobook-Generator/actions/workflows/docker-build.yml/badge.svg)](https://github.com/YOUR_USERNAME/Audiobook-Generator/actions/workflows/docker-build.yml)

## Features

### Core Features
- **Multi-Provider LLM Support**: Ollama, OpenAI (GPT-4o), and Anthropic (Claude) for text analysis
- **Multi-Speaker Detection**: Automatically detects characters and generates unique voices
- **Detailed Voice Control**: 9 voice parameters (gender, age, pitch, pace, tone, mood, energy, clarity, formality)
- **Per-Segment Delivery Styles**: Same speaker can shift between tense/calm/excited/whispered
- **High-Quality TTS**: Qwen3-TTS for natural-sounding voice synthesis
- **Batch Processing**: Handles large texts by processing in configurable chunks
- **Audio Combining**: Merges all segments into a single MP3 file

### API & Web Features
- **Web Interface**: Clean, modern UI for creating and monitoring jobs
- **REST API**: Full-featured FastAPI-based REST API
- **Job Queue**: Background processing with SQLite-based job queue
- **Real-time Progress**: Live progress tracking with detailed status messages
- **Webhooks**: Automatic notifications when jobs complete
- **Job Titles**: Name your audiobooks for easy identification

### Deployment
- **Docker Support**: NVIDIA CUDA and AMD ROCm images available
- **GitHub Actions**: Automated builds and publishing to GitHub Container Registry
- **YAML Configuration**: Simple `config.yml` for all settings

## Quick Start

### Option 1: Docker (Recommended)

#### NVIDIA GPU
```bash
# Pull from GitHub Container Registry
docker pull ghcr.io/YOUR_USERNAME/audiobook-generator:latest

# Or use docker-compose
docker-compose up -d
```

#### AMD GPU (ROCm)
```bash
docker pull ghcr.io/YOUR_USERNAME/audiobook-generator:rocm

# Or use docker-compose
docker-compose -f docker-compose.rocm.yml up -d
```

### Option 2: Local Installation

#### Prerequisites
- Python 3.10+
- CUDA-compatible GPU (recommended) or AMD GPU with ROCm
- FFmpeg (for audio processing)

#### Install
```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/Audiobook-Generator.git
cd Audiobook-Generator

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Copy and edit config
cp config.sample.yml config.yml
# Edit config.yml with your LLM provider settings
```

#### Configure LLM Provider

Edit `config.yml`:

```yaml
# For OpenAI
llm:
  provider: openai
  model: gpt-4o
  base_url: https://api.openai.com/v1
  api_key: sk-your-api-key

# For Anthropic
llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key: sk-ant-your-api-key

# For Ollama (local)
llm:
  provider: ollama
  model: llama3:70b
  base_url: http://localhost:11434/v1
```

#### Run
```bash
python run_server.py
```

Open http://localhost:8000 in your browser.

## Web Interface

The web interface provides:
- **Text Input**: Paste text directly or upload files
- **Title Input**: Name your audiobooks
- **Processing Options**: Enable/disable text processing and speaker detection
- **Real-time Progress**: Watch jobs process with detailed status
- **One-click Download**: Download completed audiobooks

## REST API

### Create Job with Text
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Your story text here...",
    "title": "My Audiobook",
    "enable_text_processing": true,
    "enable_speaker_detection": true
  }'
```

### Upload File
```bash
curl -X POST http://localhost:8000/jobs/upload \
  -F "file=@story.txt" \
  -F "title=My Story" \
  -F "enable_speaker_detection=true"
```

### Check Status
```bash
curl http://localhost:8000/jobs/{job_id}
```

### Download Audiobook
```bash
curl -O http://localhost:8000/jobs/{job_id}/download
```

### API Documentation
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Configuration

### Full config.yml Example

```yaml
# Application Settings
app:
  host: 0.0.0.0
  port: 8000
  debug: false

# LLM Settings
llm:
  provider: openai          # ollama | openai | anthropic
  model: gpt-4o
  base_url: https://api.openai.com/v1
  api_key: your-api-key
  timeout: 600
  temperature: 0.1

# TTS Settings
tts:
  device: null              # Auto-detect (cuda:0 or cpu)
  dtype: bfloat16
  use_flash_attention: null # Auto-detect

# Database
database:
  url: sqlite:///audiobook_jobs.db
```

### Environment Variables

All config options can be overridden via environment variables:
```bash
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_API_KEY=sk-...
TTS_DEVICE=cuda:0
```

## Docker Deployment

### Build Locally

```bash
# NVIDIA CUDA
docker build -t audiobook-generator .

# AMD ROCm
docker build -f Dockerfile.rocm -t audiobook-generator-rocm .
```

### Run with Docker

```bash
# NVIDIA
docker run --gpus all -p 8000:8000 \
  -v ./data:/app/data \
  -v ./config.yml:/app/config.yml:ro \
  audiobook-generator

# AMD
docker run --device=/dev/kfd --device=/dev/dri \
  -p 8000:8000 \
  -v ./data:/app/data \
  -v ./config.yml:/app/config.yml:ro \
  audiobook-generator-rocm
```

### Docker Compose

```bash
# NVIDIA
docker-compose up -d

# AMD ROCm
docker-compose -f docker-compose.rocm.yml up -d
```

## Pipeline Overview

1. **Text Batching**: Splits text into manageable chunks
2. **LLM Processing**: Cleans and optimizes text for TTS (optional)
3. **Speaker Detection**: Identifies characters with detailed voice profiles
4. **Text Splitting**: Assigns segments to speakers with delivery styles
5. **Voice Generation**: Creates unique TTS voice per speaker
6. **Audio Synthesis**: Generates audio for each segment
7. **Audio Combining**: Merges all segments into final MP3

## Output Structure

```
data/output/{job_id}/
├── audiobook.mp3              # Final combined audiobook
├── metadata.json              # Generation metadata
├── processed_text.txt         # LLM-processed text
├── detected_speakers.json     # Speaker information
└── segments/                  # Individual audio segments
    ├── voice_narrator.wav
    ├── voice_character1.wav
    ├── segment_0000.wav
    └── ...
```

## Python API

```python
from audiobook_generator import MultiSpeakerAudiobookGenerator

generator = MultiSpeakerAudiobookGenerator(
    llm_provider="openai",
    llm_model="gpt-4o",
    llm_api_key="sk-...",
    tts_device="cuda:0",
    enable_text_processing=True,
    enable_speaker_detection=True,
)

metadata = generator.generate(
    input_file="story.txt",
    output_dir="output/my_audiobook",
    output_filename="audiobook.mp3",
)
```

## Performance Tips

1. **GPU**: Use CUDA or ROCm for 10x faster TTS
2. **Flash Attention**: Install `flash-attn` for faster inference
3. **Skip Processing**: Disable `enable_text_processing` for clean text
4. **Single Speaker**: Disable `enable_speaker_detection` for narration-only

## Troubleshooting

### Out of Memory
- Use `tts_dtype: float32` instead of `bfloat16`
- Reduce batch size in config
- Use CPU: `tts_device: cpu`

### LLM Returns Empty Text
- The system automatically falls back to original text
- Check your API key and model access
- Try a different model

### Speaker Detection Issues
- Ensure text has clear dialogue markers (quotes)
- Check `detected_speakers.json` for results
- Fallback: Disable speaker detection for single narrator

## License

MIT License

## Credits

- **Qwen3-TTS**: Voice synthesis by Alibaba
- **OpenAI/Anthropic/Ollama**: LLM providers for text analysis
- **FastAPI**: Web framework
- **Pydub**: Audio processing

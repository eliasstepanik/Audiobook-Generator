# Audiobook Generator - Complete Documentation

## Table of Contents
1. [Quick Start](#quick-start)
2. [Features](#features)
3. [Voice Control System](#voice-control-system)
4. [API Reference](#api-reference)
5. [System Architecture](#system-architecture)
6. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Installation

1. **Install Python 3.12** (PyTorch doesn't support 3.13 yet)
2. **Create virtual environment**:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install PyTorch with CUDA**:
   ```bash
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
   ```

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Install FFmpeg** (for MP3 export):
   ```bash
   winget install ffmpeg
   ```

### First Run

```bash
# Delete old database (if exists)
del audiobook_jobs.db

# Start server
python run_server.py

# Open browser
# http://localhost:8000
```

### Create Your First Audiobook

1. Open `http://localhost:8000`
2. Enter text or upload file
3. Choose options:
   - **Enable Text Processing** - Process text through Ollama LLM
   - **Enable Speaker Detection** - Auto-detect characters and assign voices
4. Click "Generate Audiobook"
5. Download MP3 when complete

---

## Features

### Core Features

- ✅ **Multi-speaker audiobook generation** - Automatic character detection
- ✅ **Detailed voice control** - 9 controllable parameters per voice
- ✅ **LLM text processing** - Optional text enhancement via Ollama
- ✅ **Automatic speaker detection** - Uses LLM to identify characters
- ✅ **Voice synthesis** - Qwen3-TTS with voice cloning
- ✅ **MP3 export** - Combined audio output with pydub
- ✅ **Job queue system** - Background processing with progress tracking
- ✅ **Webhook support** - Notifications on completion
- ✅ **Web interface** - Real-time progress monitoring

### Hardware Support

- ✅ **NVIDIA GPUs** (CUDA) - Fully supported
- ✅ **AMD GPUs** (ROCm) - Auto-detected, supported
- ✅ **CPU-only** - Fallback mode (slower)
- ✅ **Flash Attention** - Auto-detected for 2-3x speedup (optional)

---

## Voice Control System

### Overview

The system provides **granular control** over every aspect of voice generation through 9 controllable parameters.

### Controllable Parameters

| Parameter | Options | Example |
|-----------|---------|---------|
| **Gender** | male, female, neutral | "Female" |
| **Age** | 0-100 years | "25 years old", "elderly" |
| **Pitch** | very low → very high | "Low-pitched", "high-pitched" |
| **Pace** | very slow → very fast | "Fast pace", "slow pace" |
| **Tone** | 13 options | upbeat, calm, serious, mysterious |
| **Mood** | 10 options | happy, tired, energetic, confident |
| **Energy** | low, medium, high | "High energy" |
| **Clarity** | clear, unclear | "Clear articulation" |
| **Formality** | casual, neutral, formal | "Formal style" |

### Usage Examples

#### Natural Language Input (Automatic with Speaker Detection)

When you enable **Speaker Detection**, the system automatically generates detailed voice profiles:

```
Input text: "Hello," said the young princess cheerfully.

Detected: Princess character
Generated voice: "Female, young, high-pitched, fast pace, upbeat tone, cheerful mood"
```

#### Manual Voice Control (Python)

```python
from audiobook_generator.voice_control import DetailedVoiceProfile

# Example 1: Young energetic female
profile = DetailedVoiceProfile.from_natural_language(
    "Young female voice, fast pace, upbeat tone"
)
instruction = profile.to_instruction()
# Output: "Female, young, fast pace, upbeat tone"

# Example 2: Tired old male
profile = DetailedVoiceProfile.from_natural_language(
    "Low-pitched male voice, slow pace, restrained tone, tired mood"
)
instruction = profile.to_instruction()
# Output: "Male, low-pitched, slow pace, restrained tone, tired mood"
```

### Preset Voices

Six professional voice profiles ready to use:

1. **narrator_professional** - Male, 40, formal narrator
2. **narrator_friendly** - Female, 35, warm and cheerful
3. **character_young_energetic** - Female, 22, fast and upbeat
4. **character_old_wise** - Male, 65, slow and calm
5. **character_villain** - Male, 45, mysterious and menacing
6. **child_playful** - Child, 10, playful and energetic

---

## API Reference

### Base URL
```
http://localhost:8000
```

### Endpoints

#### Create Job (Text Input)
```http
POST /jobs
Content-Type: application/json

{
  "text": "Your text here",
  "enable_text_processing": true,
  "enable_speaker_detection": true,
  "webhook_url": "https://optional-webhook.com/notify"
}
```

#### Create Job (File Upload)
```http
POST /jobs/upload
Content-Type: multipart/form-data

file: <text file>
enable_text_processing: true
enable_speaker_detection: true
webhook_url: <optional>
```

#### Get Job Status
```http
GET /jobs/{job_id}

Response:
{
  "job_id": "uuid",
  "status": "processing",
  "progress": 75,
  "progress_message": "Synthesizing segment 5/10...",
  "created_at": "2026-01-30T01:00:00",
  "started_at": "2026-01-30T01:00:05",
  ...
}
```

#### List Jobs
```http
GET /jobs?status=processing&limit=100

Response: [<job objects>]
```

#### Download Audiobook
```http
GET /jobs/{job_id}/download

Response: MP3 file download
```

#### Delete/Cancel Job
```http
DELETE /jobs/{job_id}

Response: {"message": "Job deleted"}
```

#### Get Statistics
```http
GET /stats

Response:
{
  "total": 42,
  "by_status": {
    "pending": 2,
    "processing": 1,
    "completed": 35,
    "failed": 4
  }
}
```

---

## System Architecture

### Pipeline Flow

```
User Input (Text/File)
     ↓
FastAPI Server
     ↓
Job Queue (SQLite)
     ↓
Worker Thread
     ↓
┌────────────────────────────────┐
│  1. Text Processor             │ → Batches (16k chars)
│  2. Ollama Client (optional)   │ → Enhanced text
│  3. Speaker Detector (optional)│ → Speaker list + voices
│  4. Voice Generator            │ → TTS voices (Qwen3-TTS)
│  5. Audio Synthesizer          │ → Segment audio files
│  6. Audio Combiner             │ → Final MP3
└────────────────────────────────┘
     ↓
Output: audiobook.mp3
     ↓
Webhook (optional)
```

### Technology Stack

**Backend:**
- FastAPI - Web framework
- SQLAlchemy - Database ORM
- SQLite - Job queue database
- PyTorch - Deep learning framework
- Qwen3-TTS - Voice synthesis
- Pydub + FFmpeg - Audio processing

**Frontend:**
- Vanilla JavaScript
- HTML5 + CSS3
- Real-time updates (polling)

**LLM Integration:**
- Ollama - LLM server
- gpt-oss-16k:120b - Text processing model

---

## Troubleshooting

### Common Issues

#### Issue: Database Schema Error
```
sqlite3.OperationalError: no such column: progress_message
```

**Solution:**
```bash
del audiobook_jobs.db
python run_server.py
```

#### Issue: CUDA Not Available
```
RuntimeError: Torch not compiled with CUDA enabled
```

**Solution:**
```bash
pip uninstall torch torchvision torchaudio -y
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

#### Issue: Ollama 500 Error
```
500 Server Error: Internal Server Error
```

**Solution:**
- Check Ollama server is running: `curl http://192.168.178.166:11434/api/tags`
- Check model is loaded: Should show gpt-oss-16k:120b
- Fixed with `max_tokens=2000` in speaker detection

#### Issue: Flash Attention Error
```
FlashAttention2 has been toggled on, but it cannot be used
```

**Solution:**
System auto-disables Flash Attention if not installed. This is normal.
Optional: `pip install flash-attn --no-build-isolation` for 2-3x speedup

#### Issue: FFmpeg Not Found
```
FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'
```

**Solution:**
```bash
winget install ffmpeg
# Restart terminal after installation
```

### Debug Commands

```bash
# Check GPU
nvidia-smi

# Check PyTorch CUDA
python -c "import torch; print(torch.cuda.is_available())"

# Test Ollama
curl http://192.168.178.166:11434/api/tags

# Check models cache
dir "C:\Users\Elias Stepanik\.cache\huggingface\hub"

# Test voice control
python -m src.audiobook_generator.voice_control
```

### Performance Notes

**Without Flash Attention (current):**
- Voice generation: ~30-60 seconds per voice
- Audio synthesis: ~5-10 seconds per segment
- Ollama processing: ~20-30 seconds per batch

**With Flash Attention (optional):**
- Voice generation: ~10-20 seconds (2-3x faster)
- Audio synthesis: ~2-4 seconds (2-3x faster)

---

## Configuration

### Server Configuration

Edit `run_server.py` to change settings:

```python
# Ollama settings
ollama_model = "gpt-oss-16k:120b"
ollama_base_url = "http://192.168.178.166:11434/v1"

# TTS settings
tts_device = None  # Auto-detect (cuda:0 or cpu)
tts_dtype = "bfloat16"

# Server settings
host = "0.0.0.0"
port = 8000
```

### Environment Variables

```bash
# Optional: Brave Search API
BRAVE_API_KEY=your_api_key

# Optional: Disable symlink warning
HF_HUB_DISABLE_SYMLINKS_WARNING=1
```

---

## Advanced Usage

### Custom Voice Profiles

```python
from audiobook_generator.voice_control import DetailedVoiceProfile, VoiceGender, VoicePace, VoiceTone

# Create custom profile
villain = DetailedVoiceProfile(
    gender=VoiceGender.MALE,
    age=45,
    pace=VoicePace.VERY_SLOW,
    tone=VoiceTone.MYSTERIOUS,
    pitch=VoicePitch.VERY_LOW,
    mood=VoiceMood.TENSE
)

instruction = villain.to_instruction()
# Use instruction with TTS synthesizer
```

### Integration with External Systems

Use webhooks to notify external systems:

```python
POST /jobs
{
  "text": "...",
  "webhook_url": "https://your-system.com/audiobook-complete"
}

# When job completes, sends:
POST https://your-system.com/audiobook-complete
{
  "job_id": "uuid",
  "status": "completed",
  "output_path": "/path/to/audiobook.mp3"
}
```

---

## File Structure

```
Audiobook-Generator/
├── run_server.py                    # Main entry point
├── requirements.txt                 # Dependencies
├── DOCUMENTATION.md                 # This file
├── src/audiobook_generator/
│   ├── models.py                    # Database models
│   ├── database.py                  # SQLite connection
│   ├── job_queue.py                 # Job management
│   ├── worker_with_progress.py      # Background worker
│   ├── api.py                       # FastAPI endpoints
│   ├── voice_control.py             # ⭐ Detailed voice control
│   ├── speaker_detector.py          # LLM speaker detection
│   ├── text_processor.py            # Text batching
│   ├── ollama_client.py             # Ollama integration
│   ├── tts_synthesizer.py           # Qwen3-TTS voice synthesis
│   ├── audio_combiner.py            # MP3 combining
│   └── multi_speaker_generator.py   # Main pipeline
├── frontend/
│   ├── templates/index.html         # Web UI
│   └── static/
│       ├── css/style.css            # Styling
│       └── js/
│           ├── app.js               # Basic UI
│           └── app_enhanced.js      # Enhanced UI (optional)
└── data/
    └── output/                      # Generated audiobooks
```

---

## Credits

**Author:** Audiobook Generator System
**TTS Model:** Qwen3-TTS by Alibaba Cloud
**LLM:** Ollama with gpt-oss-16k:120b
**Framework:** FastAPI, PyTorch

---

## License

See project repository for license information.

---

## Support

For issues and questions:
1. Check this documentation
2. Review error logs in console
3. Test with simple job (no LLM processing)
4. Verify GPU/CUDA setup
5. Check Ollama connection

**System Status Check:**
```bash
python run_server.py
# Should show:
# ✓ GPU detected
# ✓ Flash Attention status
# ✓ TTS models ready
# ✓ Ollama connected
# ✓ Server started
```

---

**Last Updated:** January 30, 2026
**Version:** 2.0 (with Detailed Voice Control)

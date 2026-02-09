# Audiobook Generator - Development Commands
# Usage: just <command>
# Install just: https://github.com/casey/just

# Default: show available commands
default:
    @just --list

# =============================================================================
# SETUP
# =============================================================================

# Install all dependencies
install:
    pip install -r requirements.txt

# Install with flash attention (requires CUDA)
install-flash:
    pip install -r requirements.txt
    pip install flash-attn

# Create virtual environment and install
setup:
    python -m venv venv
    venv\Scripts\activate && pip install -r requirements.txt

# Download TTS model
download-model:
    python -c "from audiobook_generator import TTSSynthesizer; TTSSynthesizer()"

# =============================================================================
# RUN
# =============================================================================

# Start the API server (default: localhost:8000)
serve:
    python run_server.py

# Start server on custom host/port
serve-custom host="0.0.0.0" port="8000":
    python -c "import uvicorn; uvicorn.run('audiobook_generator.api:app', host='{{host}}', port={{port}}, reload=True)"

# Start with auto-reload for development
dev:
    PYTHONPATH=src python -m uvicorn audiobook_generator.api:app --host 127.0.0.1 --port 8000 --reload

# =============================================================================
# EXAMPLES
# =============================================================================

# Run basic usage example
example-basic:
    python examples/basic_usage.py

# Run single speaker example
example-single:
    python examples/single_speaker.py

# Run API client example
example-api:
    python examples/api_client_example.py

# =============================================================================
# API SHORTCUTS
# =============================================================================

# Check API health
health:
    curl -s http://localhost:8000/health | python -m json.tool

# Get API stats
stats:
    curl -s http://localhost:8000/stats | python -m json.tool

# List all jobs
jobs:
    curl -s http://localhost:8000/jobs | python -m json.tool

# Create a test job
test-job:
    curl -s -X POST http://localhost:8000/jobs \
        -H "Content-Type: application/json" \
        -d '{"text": "Hello world. This is a test audiobook.", "title": "Test Book"}' \
        | python -m json.tool

# =============================================================================
# DEVELOPMENT
# =============================================================================

# Run type checking
typecheck:
    python -m mypy src/audiobook_generator --ignore-missing-imports

# Format code
format:
    python -m black src/ examples/
    python -m isort src/ examples/

# Lint code
lint:
    python -m ruff check src/ examples/

# Run all checks
check: typecheck lint

# Clean generated files
clean:
    rm -rf __pycache__ .pytest_cache .mypy_cache
    rm -rf src/**/__pycache__
    rm -rf data/output/*
    rm -rf *.db

# Clean everything including models
clean-all: clean
    rm -rf models/

# =============================================================================
# DATABASE
# =============================================================================

# Show database info
db-info:
    python -c "from audiobook_generator.database import get_engine; from sqlalchemy import inspect; i = inspect(get_engine()); print('Tables:', i.get_table_names())"

# Reset database
db-reset:
    rm -f audiobook_jobs.db
    python -c "from audiobook_generator.database import init_db; init_db()"

# =============================================================================
# DOCKER (if using)
# =============================================================================

# Build docker image
docker-build:
    docker build -t audiobook-generator .

# Run docker container
docker-run:
    docker run -p 8000:8000 -v ./data:/app/data audiobook-generator

# =============================================================================
# QUICK GENERATE
# =============================================================================

# Generate audiobook from file
generate file:
    python -c "from audiobook_generator import MultiSpeakerAudiobookGenerator; g = MultiSpeakerAudiobookGenerator(); g.generate('{{file}}', 'data/output')"

# Generate with custom output directory
generate-to file output:
    python -c "from audiobook_generator import MultiSpeakerAudiobookGenerator; g = MultiSpeakerAudiobookGenerator(); g.generate('{{file}}', '{{output}}')"

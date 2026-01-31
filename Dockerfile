# Audiobook Generator - Multi-stage Docker build
# Supports NVIDIA GPU acceleration for TTS with Flash Attention

# Build stage for Flash Attention (requires CUDA devel image)
FROM nvidia/cuda:12.1.0-devel-ubuntu22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3-pip \
    git \
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Install PyTorch first (required for flash-attn build)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu121

# Build Flash Attention (this takes a while but is cached)
ENV MAX_JOBS=4
ENV FLASH_ATTENTION_SKIP_CUDA_BUILD=FALSE
RUN pip install --no-cache-dir packaging wheel setuptools \
    && pip install --no-cache-dir flash-attn --no-build-isolation

# Runtime stage
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04 AS base

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3-pip \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Create app user for security
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy Flash Attention from builder stage
COPY --from=builder /usr/local/lib/python3.11/dist-packages/flash_attn* /usr/local/lib/python3.11/dist-packages/

# Copy application code
COPY src/ ./src/
COPY frontend/ ./frontend/
COPY run_server.py .
COPY config.sample.yml .

# Create data directories
RUN mkdir -p /app/data/input /app/data/output /app/data/temp \
    && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/stats')" || exit 1

# Default command
CMD ["python", "run_server.py"]

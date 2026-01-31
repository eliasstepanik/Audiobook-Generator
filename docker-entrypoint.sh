#!/bin/bash
set -e

# Install Flash Attention on first run if GPU is available and not already installed
install_flash_attention() {
    if python -c "import flash_attn" 2>/dev/null; then
        echo "Flash Attention already installed"
        return 0
    fi

    echo "Checking for GPU availability..."
    
    # Check for NVIDIA GPU
    if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
        echo "NVIDIA GPU detected, installing Flash Attention..."
        pip install --no-cache-dir flash-attn --no-build-isolation && \
            echo "Flash Attention installed successfully" || \
            echo "Flash Attention installation failed, continuing without it"
        return 0
    fi

    # Check for AMD GPU (ROCm)
    if [ -d "/opt/rocm" ] && [ -e "/dev/kfd" ]; then
        echo "AMD GPU (ROCm) detected, attempting Flash Attention installation..."
        pip install --no-cache-dir flash-attn --no-build-isolation && \
            echo "Flash Attention installed successfully" || \
            echo "Flash Attention not available for ROCm, continuing without it"
        return 0
    fi

    echo "No GPU detected, skipping Flash Attention installation"
}

# Only install if INSTALL_FLASH_ATTN is set to true (default: true)
if [ "${INSTALL_FLASH_ATTN:-true}" = "true" ]; then
    install_flash_attention
fi

# Execute the main command
exec "$@"

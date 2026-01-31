#!/bin/bash
set -e

# Fix AMD GPU permissions (GID mapping issue between host and container)
fix_amd_gpu_permissions() {
    if [ -e "/dev/kfd" ] && [ -d "/opt/rocm" ]; then
        echo "Fixing AMD GPU device permissions..."
        # The render group GID from host may map to a different group in container
        # Make devices accessible to all users in the container
        chmod 666 /dev/kfd /dev/dri/* 2>/dev/null || true
    fi
}

# Run GPU permission fix (needs to run as root or with appropriate capabilities)
fix_amd_gpu_permissions

# Drop privileges to appuser if running as root (for ROCm builds)
drop_privileges() {
    if [ "$(id -u)" = "0" ] && id appuser &>/dev/null; then
        echo "Dropping privileges to appuser..."
        exec gosu appuser "$@"
    fi
}

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

# Fix data directory permissions (bind-mounted host dirs may not be writable by appuser)
fix_data_permissions() {
    if [ "$(id -u)" = "0" ] && id appuser &>/dev/null; then
        echo "Fixing data directory permissions..."
        for dir in /app/data /app/data/input /app/data/output /app/data/temp; do
            if [ -d "$dir" ]; then
                chown appuser:appuser "$dir" 2>/dev/null || true
            else
                mkdir -p "$dir" && chown appuser:appuser "$dir" 2>/dev/null || true
            fi
        done
    fi
}

fix_data_permissions

# Drop privileges to appuser if running as root (for ROCm builds that need root for GPU permissions)
if [ "$(id -u)" = "0" ] && id appuser &>/dev/null; then
    echo "Dropping privileges to appuser..."
    exec gosu appuser "$@"
fi

# Execute the main command (if not dropping privileges)
exec "$@"

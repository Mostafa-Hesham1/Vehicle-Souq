# ==============================================================
# VehicleSouq - HuggingFace Spaces Dockerfile
# Free CPU tier: 2 vCPU, 16GB RAM - enough for all models
# ==============================================================

FROM python:3.10-slim

# ── System dependencies (OpenCV, torch, build tools) ──────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    ffmpeg \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# ── Set working directory ──────────────────────────────────────
WORKDIR /app

# ── Install CPU-only PyTorch first (saves ~4GB vs CUDA build) ─
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        torch==2.1.0+cpu \
        torchvision==0.16.0+cpu \
        --extra-index-url https://download.pytorch.org/whl/cpu

# ── Copy backend requirements and install ─────────────────────
# Filter out torch/torchvision — already installed as CPU-only above
COPY backend/requirements.txt /app/requirements.txt
RUN grep -vE '^torch|^torchvision' /app/requirements.txt > /app/requirements_filtered.txt && \
    pip install --no-cache-dir -r /app/requirements_filtered.txt

# ── Copy full backend code ─────────────────────────────────────
COPY backend/ /app/backend/

# ── Install mmdetection from the included source ──────────────
RUN pip install --no-cache-dir openmim && \
    mim install mmengine && \
    mim install "mmcv>=2.0.0" && \
    cd /app/backend/mmdetection && pip install -e . --no-deps && \
    cd /app

# ── Create runtime directories ────────────────────────────────
RUN mkdir -p /app/backend/uploads \
             /app/backend/uploaded_images \
             /app/backend/reports \
             /app/backend/ML-Models/CarDamageModels \
             /app/backend/ML-Models/Price-predection

# ── HuggingFace runs containers as user 1000 ─────────────────
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# ── Expose port 7860 (HuggingFace Spaces required port) ───────
EXPOSE 7860

# ── Start FastAPI backend ──────────────────────────────────────
WORKDIR /app/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]

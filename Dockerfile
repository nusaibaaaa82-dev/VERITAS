# ==============================================================================
# VERITAS — Unified Hugging Face Space Dockerfile
#
# Multi-stage build:
# Stage 1: Build the React frontend with Vite & TypeScript
# Stage 2: Serve FastAPI backend + built frontend static assets on port 7860
#
# Meets all Hugging Face Spaces requirements:
# - Non-root execution: runs under user "user" (UID 1000)
# - Default exposed port: 7860
# - Hugging Face cache directory configured under /home/user/.cache/huggingface
# - Ephemeral SQLite database baked into image from seed data
# - Single Uvicorn worker for PyTorch CPU multi-threading and in-memory rate limiting
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Frontend Build
# ------------------------------------------------------------------------------
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend

# Copy frontend dependency manifests
COPY frontend/package*.json ./

# Install exact npm dependencies
RUN npm ci

# Copy frontend source code and configuration
COPY frontend/ ./

# Build production bundle into /app/frontend/dist
RUN npm run build

# ------------------------------------------------------------------------------
# Stage 2: Production Python Backend + Static Frontend
# ------------------------------------------------------------------------------
FROM python:3.11-slim

# Hugging Face Spaces environment configuration
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860 \
    HOST=0.0.0.0 \
    HF_HOME=/home/user/.cache/huggingface \
    TRANSFORMERS_CACHE=/home/user/.cache/huggingface

# Create non-root user "user" with UID 1000 (standard for Hugging Face Spaces)
RUN useradd -m -u 1000 user

WORKDIR /app

# Install minimal OS dependencies for health checking and build integrity
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Pre-create writable cache and data directories for UID 1000
RUN mkdir -p /home/user/.cache/huggingface && \
    chown -R user:user /home/user

# Install Python backend dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r backend/requirements.txt

# Copy backend application source and baked-in seed SQLite database
COPY backend/ ./backend/

# Copy built frontend assets from Stage 1 into /app/frontend/dist
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Set full ownership of /app to non-root user (UID 1000) for SQLite WAL and cache access
RUN chown -R user:user /app

# Switch to non-root user
USER user

# Expose default Hugging Face Spaces port
EXPOSE 7860

# Launch Uvicorn with a single worker (enforces in-memory rate limiting and avoids RAM duplication)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]


FROM python:3.11-slim

WORKDIR /app

# Install FFmpeg and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    stress-ng \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Copy shared module first
COPY shared/ /app/shared/

# Copy worker requirements and install
COPY worker/requirements.txt /app/worker/
RUN pip install --no-cache-dir -r /app/worker/requirements.txt

# Copy worker application
COPY worker/ /app/worker/

# Create data directory for database
RUN mkdir -p /data

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV METRICS_PORT=8001

# Expose metrics port
EXPOSE 8001

# Health check (check if process is running)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8001/ || exit 1

# Run the worker
CMD ["python", "-m", "worker.worker"]
